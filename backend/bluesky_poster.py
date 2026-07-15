#!/usr/bin/env python3
"""
bluesky_poster.py — Arc Codex auto-poster for Bluesky
v1.5 — Redis session persistence; uses refreshSession instead of createSession
        on restart/proactive refresh — prevents burning the createSession rate
        limit (shared per home IP) which was locking out mobile logins.

On/off:  redis-cli set bluesky:autopost 1|0
Posted set: bluesky:posted (SET of article IDs, prevents duplicates)
Session key: BLUESKY_SESSION_KEY (default: arc:bluesky_session)
             Set to huntaegis:bluesky_session in Huntaegis .env

Post format:
  {title}

  {counter-analyst comment — normalized}

  {article URL}

Fallback: purple_team_analysis excerpt if no counter-analyst within 60s
Jitter: 30–180s after article detection
Seeds all existing articles on startup to prevent spam
"""

import os
import sys
import time
import json
import random
import logging
import requests
from dotenv import load_dotenv

# ── env ────────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BLUESKY_HANDLE       = os.getenv("BLUESKY_HANDLE", "hapenez.bsky.social")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD", "")
REDIS_URL            = os.environ['REDIS_URL']
BACKEND_URL          = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:5005")
ARTICLE_BASE_URL     = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")

# Namespaced per-stack so Arc and Huntaegis don't share a session key.
# Set BLUESKY_SESSION_KEY=huntaegis:bluesky_session in Huntaegis .env
SESSION_KEY    = os.getenv("BLUESKY_SESSION_KEY", "arc:bluesky_session")

POLL_INTERVAL  = 15          # seconds between Redis scans
JITTER_MIN     = 0
JITTER_MAX     = 0
CA_WAIT        = 120         # seconds to wait for counter-analyst comment
                             # Floor, not ceiling — CA generation is async
                             # (shed-and-yield tiering, ~72s measured, may
                             # exceed 120s under load). Real fix: event-
                             # driven posting (see ops/RUNBOOK.md 2026-07-15).
POLL_KEY       = "bluesky:autopost"
POSTED_SET     = "bluesky:posted"

BSKY_API       = "https://bsky.social/xrpc"

# ── logging ────────────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bluesky_poster] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "bluesky_poster.log")),
    ],
)
log = logging.getLogger("bluesky_poster")

# ── Redis ──────────────────────────────────────────────────────────────────────
import redis as redis_lib
from comment_utils import get_counter_analyst_comment

def make_redis():
    return redis_lib.from_url(REDIS_URL, decode_responses=True)

r = make_redis()

# ── Bluesky AT Protocol auth ───────────────────────────────────────────────────
_session: dict = {}

def _save_session() -> None:
    """Persist accessJwt + refreshJwt to Redis so restarts skip createSession."""
    try:
        payload = json.dumps({
            "did":        _session.get("did"),
            "accessJwt":  _session.get("accessJwt"),
            "refreshJwt": _session.get("refreshJwt"),
        })
        r.set(SESSION_KEY, payload, ex=7 * 24 * 3600)  # 7-day TTL
        log.debug("Session saved to Redis key: %s", SESSION_KEY)
    except Exception as exc:
        log.warning("Failed to save session to Redis: %s", exc)

def _load_session() -> bool:
    """Load persisted session from Redis into _session. Returns True if found."""
    global _session
    try:
        raw = r.get(SESSION_KEY)
        if not raw:
            return False
        data = json.loads(raw)
        if data.get("accessJwt") and data.get("refreshJwt"):
            _session = data
            log.info("Loaded persisted Bluesky session (DID: %s)", _session.get("did"))
            return True
    except Exception as exc:
        log.warning("Failed to load session from Redis: %s", exc)
    return False

def bsky_refresh() -> bool:
    """
    Call refreshSession with the stored refreshJwt to get a new accessJwt.
    This does NOT count against the createSession rate limit.
    Returns True on success.
    """
    global _session
    refresh_token = _session.get("refreshJwt")
    if not refresh_token:
        log.debug("bsky_refresh: no refreshJwt available")
        return False
    try:
        resp = requests.post(
            f"{BSKY_API}/com.atproto.server.refreshSession",
            headers={
                "Authorization": f"Bearer {refresh_token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        _session.update(resp.json())
        _save_session()
        log.info("Bluesky session refreshed via refreshSession (DID: %s)", _session.get("did"))
        return True
    except Exception as exc:
        log.warning("refreshSession failed: %s", exc)
        return False

def bsky_login() -> bool:
    """
    Full createSession with handle + app password.
    Rate-limited to ~30/5min per IP — only call this when refresh fails
    or no persisted session exists.
    """
    global _session
    try:
        resp = requests.post(
            f"{BSKY_API}/com.atproto.server.createSession",
            json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
            timeout=15,
        )
        resp.raise_for_status()
        _session = resp.json()
        _save_session()
        log.info("Bluesky createSession OK (DID: %s)", _session.get("did"))
        return True
    except Exception as exc:
        log.error("Bluesky createSession failed: %s", exc)
        return False

def bsky_ensure_session() -> bool:
    """
    Preferred startup/refresh entry point. Resolution order:
      1. Load persisted session from Redis, then refresh it  → no createSession call
      2. If no persisted session, call createSession          → counts against limit
    """
    if not _session:
        _load_session()

    if _session.get("refreshJwt"):
        if bsky_refresh():
            return True
        log.warning("refreshSession failed — falling back to createSession")

    return bsky_login()

def bsky_headers() -> dict:
    return {
        "Authorization": f"Bearer {_session.get('accessJwt', '')}",
        "Content-Type": "application/json",
    }

# ── Image upload ───────────────────────────────────────────────────────────────
def bsky_upload_thumb(og_image_url: str) -> dict | None:
    """Download og_image and upload to Bluesky blob store. Returns blob ref or None."""
    if not og_image_url:
        return None
    try:
        img_resp = requests.get(og_image_url, timeout=10, stream=True)
        img_resp.raise_for_status()
        content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            return None
        img_bytes = img_resp.content
        # Convert PNG to JPEG — Bluesky corrupts large PNG thumbnails
        if content_type == "image/png":
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            img_bytes = buf.getvalue()
            content_type = "image/jpeg"
        if len(img_bytes) > 1_000_000:
            img_bytes = img_bytes[:1_000_000]  # Bluesky 1MB blob limit
        upload_resp = requests.post(
            f"{BSKY_API}/com.atproto.repo.uploadBlob",
            headers={
                "Authorization": f"Bearer {_session.get('accessJwt', '')}",
                "Content-Type": content_type,
            },
            data=img_bytes,
            timeout=15,
        )
        upload_resp.raise_for_status()
        blob = upload_resp.json().get("blob")
        if blob:
            log.info("Thumb uploaded: %s", og_image_url)
        return blob
    except Exception as exc:
        log.warning("Thumb upload failed: %s", exc)
        return None

# ── Post ───────────────────────────────────────────────────────────────────────
def bsky_post(text: str, og_image_url: str = "", article_url: str = "") -> bool:
    if not og_image_url:
        og_image_url = "https://arc-codex.com/uploads/arc-codex-default.jpg"
    """
    Create a Bluesky post with optional image thumbnail in the link card.
    On 401/ExpiredToken: tries refreshSession first, falls back to createSession.
    """
    if not _session:
        if not bsky_ensure_session():
            return False

    DEFAULT_IMAGE = "https://arc-codex.com/uploads/arc-codex-default.jpg"
    thumb = bsky_upload_thumb(og_image_url)
    if thumb is None and og_image_url != DEFAULT_IMAGE:
        log.info("Thumb failed for external URL — retrying with default image")
        thumb = bsky_upload_thumb(DEFAULT_IMAGE)

    article_uri = article_url
    if article_uri:
        external = {
            "$type":       "app.bsky.embed.external#external",
            "uri":         article_uri,
            "title":       "",
            "description": "",
        }
        if thumb:
            external["thumb"] = thumb
        embed = {
            "$type":    "app.bsky.embed.external",
            "external": external,
        }
    else:
        embed = None

    record = {
        "$type":     "app.bsky.feed.post",
        "text":      text[:300],
        "createdAt": _utcnow(),
    }
    if embed:
        record["embed"] = embed
    payload = {
        "repo":       _session.get("did"),
        "collection": "app.bsky.feed.post",
        "record":     record,
    }

    for attempt in range(2):
        try:
            resp = requests.post(
                f"{BSKY_API}/com.atproto.repo.createRecord",
                headers=bsky_headers(),
                json=payload,
                timeout=15,
            )
            if resp.status_code in (400, 401) and attempt == 0:
                body_text = resp.text[:300]
                log.error("Bluesky %d response: %s", resp.status_code, body_text)
                if resp.status_code == 401 or "ExpiredToken" in body_text or "Token" in body_text:
                    log.warning("Bluesky token expired — attempting refreshSession first")
                    # Prefer refresh over full re-login to protect the createSession quota
                    if not bsky_refresh():
                        log.warning("refreshSession failed on 401 — falling back to createSession")
                        bsky_login()
                    payload["repo"] = _session.get("did")
                    # re-upload thumb with fresh token
                    if thumb:
                        new_thumb = bsky_upload_thumb(og_image_url)
                        if new_thumb and embed:
                            payload["record"]["embed"]["external"]["thumb"] = new_thumb
                    continue
                resp.raise_for_status()
            if resp.status_code == 400:
                log.error("Bluesky 400 response: %s", resp.text[:300])
            resp.raise_for_status()
            log.info("Posted to Bluesky: %s", resp.json().get("uri"))
            return True
        except Exception as exc:
            log.error("Bluesky post error (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                continue
    return False

# ── helpers ────────────────────────────────────────────────────────────────────
def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

def _extract_url(text: str) -> str:
    """Pull the arc-codex.com URL from the post text."""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("https://"):
            return line
    return ""

def get_article(article_id: str) -> dict | None:
    try:
        data = r.hgetall(f"article:{article_id}")
        return data if data else None
    except Exception as exc:
        log.error("Redis hgetall %s: %s", article_id, exc)
        return None


def build_post_text(article: dict, comment: str | None) -> tuple[str, str]:
    """Returns (post_text, article_url). URL is NOT in post_text — embed card handles it."""
    title = article.get("title", "").strip()
    url   = article.get("url") or f"{ARTICLE_BASE_URL}/article/{article.get('id', '')}"

    if comment:
        body = comment
    else:
        purple = article.get("purple_team_analysis", "")
        body = (purple[:200] + "…") if len(purple) > 200 else purple

    MAX_BODY = 295 - len(title)
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY - 1] + "…"

    return f"{title}\n\n{body}", url

def seed_posted_set():
    try:
        keys = r.zrange("feed", 0, -1)
        if not keys:
            return
        pipe = r.pipeline()
        for article_id in keys:
            pipe.sadd(POSTED_SET, article_id)
        pipe.execute()
        log.info("Seeded bluesky:posted with %d existing articles", len(keys))
    except Exception as exc:
        log.error("Seed failed: %s", exc)

def all_article_ids() -> list[str]:
    try:
        return r.zrange("feed", 0, -1)
    except Exception:
        return []

def autopost_enabled() -> bool:
    try:
        return r.get(POLL_KEY) == "1"
    except Exception:
        return False

# ── main loop ──────────────────────────────────────────────────────────────────
def main():
    log.info("bluesky_poster v1.5 starting — handle: %s  session_key: %s",
             BLUESKY_HANDLE, SESSION_KEY)
    seed_posted_set()

    # Startup auth: load persisted session + refresh (avoids createSession on restart)
    if bsky_ensure_session():
        last_login = time.time()
        log.info("Initial session ready")
    else:
        last_login = time.time() - (80 * 60)
        log.warning("Initial session failed — will retry in ~10 minutes")

    LOGIN_INTERVAL = 90 * 60  # proactive refresh every 90 minutes
    login_backoff  = 0

    while True:
        try:
            # Proactive token refresh — prefer refreshSession, fall back to createSession
            if time.time() - last_login > LOGIN_INTERVAL:
                if login_backoff > 0:
                    log.info("Login backoff active — waiting %ds before retry", login_backoff)
                    time.sleep(min(login_backoff, POLL_INTERVAL))
                    login_backoff = max(0, login_backoff - POLL_INTERVAL)
                else:
                    log.info("Proactive token refresh")
                    if bsky_refresh() or bsky_login():
                        last_login = time.time()
                        login_backoff = 0
                    else:
                        login_backoff = min(login_backoff * 2 + 60, 1800)
                        log.warning("Refresh/login failed — backing off %ds", login_backoff)
                        last_login = time.time() - (LOGIN_INTERVAL - login_backoff)

            if not autopost_enabled():
                time.sleep(POLL_INTERVAL)
                continue

            current_ids = set(all_article_ids())
            posted_ids  = r.smembers(POSTED_SET)
            new_ids     = current_ids - posted_ids

            for article_id in new_ids:
                article = get_article(article_id)
                if not article:
                    r.sadd(POSTED_SET, article_id)
                    continue

                jitter = random.randint(JITTER_MIN, JITTER_MAX)
                log.info("New article %s — waiting %ds before posting", article_id, jitter)
                time.sleep(jitter)

                comment = get_counter_analyst_comment(r, article_id, wait_seconds=CA_WAIT)
                if not comment:
                    log.warning("No counter-analyst for %s after %ds — using purple excerpt",
                                article_id, CA_WAIT)

                text, url = build_post_text(article, comment)
                og_image  = article.get("imageUrl", "")
                if og_image and og_image.startswith("/"):
                    og_image = f"{ARTICLE_BASE_URL}{og_image}"
                success   = bsky_post(text, og_image_url=og_image, article_url=url)

                if success:
                    log.info("Posted article %s to Bluesky", article_id)
                else:
                    log.error("Failed to post article %s — will retry next cycle", article_id)
                    continue

                r.sadd(POSTED_SET, article_id)

        except Exception as exc:
            log.exception("Outer loop error: %s", exc)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
