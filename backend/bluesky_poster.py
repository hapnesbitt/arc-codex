#!/usr/bin/env python3
"""
bluesky_poster.py — Arc Codex auto-poster for Bluesky
v1.1 — og_image thumb upload via uploadBlob

On/off:  redis-cli set bluesky:autopost 1|0
Posted set: bluesky:posted (SET of article IDs, prevents duplicates)
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
REDIS_URL            = os.getenv("REDIS_URL", "redis://:simplenes@localhost:6379/0")
BACKEND_URL          = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:5005")
ARTICLE_BASE_URL     = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")

POLL_INTERVAL  = 15          # seconds between Redis scans
JITTER_MIN     = 0
JITTER_MAX     = 0 
CA_WAIT        = 60          # seconds to wait for counter-analyst comment
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

def make_redis():
    return redis_lib.from_url(REDIS_URL, decode_responses=True)

r = make_redis()

# ── Bluesky AT Protocol auth ───────────────────────────────────────────────────
_session: dict = {}

def bsky_login() -> bool:
    global _session
    try:
        resp = requests.post(
            f"{BSKY_API}/com.atproto.server.createSession",
            json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
            timeout=15,
        )
        resp.raise_for_status()
        _session = resp.json()
        log.info("Bluesky login OK — DID: %s", _session.get("did"))
        return True
    except Exception as exc:
        log.error("Bluesky login failed: %s", exc)
        return False

def bsky_headers() -> dict:
    return {"Authorization": f"Bearer {_session.get('accessJwt', '')}",
            "Content-Type": "application/json"}

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
def bsky_post(text: str, og_image_url: str = "") -> bool:
    """
    Create a Bluesky post with optional image thumbnail in the link card.
    Re-authenticates once on 401 before giving up.
    """
    if not _session:
        if not bsky_login():
            return False

    # Build embed card with thumb if available
    thumb = bsky_upload_thumb(og_image_url)
    article_uri = _extract_url(text)
    if article_uri:
        external = {
            "$type": "app.bsky.embed.external#external",
            "uri": article_uri,
            "title": text.split("\n")[0][:300],
            "description": "",
        }
        if thumb:
            external["thumb"] = thumb
        embed = {
            "$type": "app.bsky.embed.external",
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
            if resp.status_code == 401 and attempt == 0:
                log.warning("Bluesky 401 — re-authenticating")
                bsky_login()
                payload["repo"] = _session.get("did")
                # refresh thumb upload token too
                if thumb:
                    new_thumb = bsky_upload_thumb(og_image_url)
                    if new_thumb:
                        payload["record"]["embed"]["external"]["thumb"] = new_thumb
                continue
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

def get_counter_analyst_comment(article_id: str, wait: bool = True) -> str | None:
    deadline = time.time() + (CA_WAIT if wait else 0)
    while True:
        try:
            raw = r.lrange(f"comments:{article_id}", 0, -1)
            for item in raw:
                try:
                    c = json.loads(item)
                    if c.get("author") == "A.R.C. Counter-Analyst":
                        body = c.get("body", "")
                        if body.startswith("The article"):
                            body = "This article" + body[len("The article"):]
                        return body
                except json.JSONDecodeError:
                    continue
        except Exception as exc:
            log.error("Redis lrange comments:%s: %s", article_id, exc)

        if time.time() >= deadline:
            return None
        time.sleep(5)

def build_post_text(article: dict, comment: str | None) -> str:
    title = article.get("title", "").strip()
    slug  = article.get("slug", article.get("id", ""))
    url   = f"{ARTICLE_BASE_URL}/article/{slug}"

    if comment:
        body = comment
    else:
        purple = article.get("purple_team_analysis", "")
        body = (purple[:200] + "…") if len(purple) > 200 else purple

    MAX_BODY = 300 - len(url) - 4
    if len(title) + 2 + len(body) > MAX_BODY:
        body = body[:MAX_BODY - len(title) - 5] + "…"

    return f"{title}\n\n{body}\n\n{url}"

def seed_posted_set():
    try:
        keys = r.keys("article:*")
        if not keys:
            return
        pipe = r.pipeline()
        for k in keys:
            article_id = k.split(":", 1)[1]
            pipe.sadd(POSTED_SET, article_id)
        pipe.execute()
        log.info("Seeded bluesky:posted with %d existing articles", len(keys))
    except Exception as exc:
        log.error("Seed failed: %s", exc)

def all_article_ids() -> list[str]:
    try:
        keys = r.keys("article:*")
        return [k.split(":", 1)[1] for k in keys]
    except Exception:
        return []

def autopost_enabled() -> bool:
    try:
        return r.get(POLL_KEY) == "1"
    except Exception:
        return False

# ── main loop ──────────────────────────────────────────────────────────────────
def main():
    log.info("bluesky_poster v1.1 starting — handle: %s", BLUESKY_HANDLE)
    seed_posted_set()
    bsky_login()

    while True:
        try:
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

                comment = get_counter_analyst_comment(article_id, wait=True)
                if not comment:
                    log.warning("No counter-analyst for %s after %ds — using purple excerpt",
                                article_id, CA_WAIT)

                text      = build_post_text(article, comment)
                og_image  = article.get("imageUrl", "")
                success   = bsky_post(text, og_image_url=og_image)

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
