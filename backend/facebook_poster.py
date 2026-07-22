#!/usr/bin/env python3
"""
facebook_poster.py — Arc Codex auto-poster for Facebook Pages
v1.2 — 368 rate-limit cooldown; automatic token refresh on OAuthException 190/463

On/off:  redis-cli set facebook:autopost 1|0
Posted set: facebook:posted (SET of article IDs, prevents duplicates)
Rate-limit cooldown: facebook:rate_limit_cooldown (STRING, TTL) — when set,
  the main loop skips all posting until it expires. Set on OAuthException 368
  ("We limit how often you can post..."). Prevents burning a photo upload
  per new article into a live block.

Post format:
  {title}

  {counter-analyst comment — normalized, or purple_team excerpt fallback}

  {article URL}

Image: downloaded from article imageUrl, uploaded to the Page via Graph API
       (staged as unpublished photo, then attached to the feed post).
Jitter: 30–180s after article detection to avoid burst-posting on restart.
Seeds all existing articles on startup to prevent spam.

Token refresh: on OAuthException code 190 or 463, exchanges the current token
  for a long-lived token via oauth/access_token (grant_type=fb_exchange_token),
  persists the new token to .env and retries the failed request once.

Requires in .env:
  FACEBOOK_APP_ID         — Meta app ID
  FACEBOOK_APP_SECRET     — Meta app secret
  FACEBOOK_PAGE_ID        — numeric Page ID
  FACEBOOK_ACCESS_TOKEN   — Page access token (refreshed automatically)
"""

import io
import os
import sys
import time
import json
import random
import logging
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# ── env ────────────────────────────────────────────────────────────────────────
_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_ENV_PATH)

APP_ID           = os.getenv("FACEBOOK_APP_ID", "")
APP_SECRET       = os.getenv("FACEBOOK_APP_SECRET", "")
PAGE_ID          = os.getenv("FACEBOOK_PAGE_ID", "")
ACCESS_TOKEN     = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
USER_ACCESS_TOKEN = os.getenv("FACEBOOK_USER_ACCESS_TOKEN", "")
REDIS_URL        = os.environ['REDIS_URL']
ARTICLE_BASE_URL = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")
DEFAULT_IMAGE    = f"{ARTICLE_BASE_URL}/uploads/arc-codex-default.jpg"

POLL_INTERVAL = 15          # seconds between Redis scans
JITTER_MIN    = 30          # seconds
JITTER_MAX    = 180
CA_WAIT       = 120         # seconds to wait for counter-analyst comment
                            # Floor, not ceiling — CA generation is async
                            # (shed-and-yield tiering, ~72s measured, may
                            # exceed 120s under load). Real fix: event-
                            # driven posting (see ops/RUNBOOK.md 2026-07-15).
POLL_KEY      = "facebook:autopost"
POSTED_SET    = "facebook:posted"
SEEDED_KEY    = "facebook:seeded"
COOLDOWN_KEY  = "facebook:rate_limit_cooldown"
COOLDOWN_TTL  = 6 * 60 * 60   # 6h — matches typical FB 368 block windows

GRAPH_API     = "https://graph.facebook.com/v19.0"

# ── logging ────────────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
_log_path = os.path.join(log_dir, "facebook_poster.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [facebook_poster] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(_log_path),
    ],
)
log = logging.getLogger("facebook_poster")

# Log can contain Graph API error bodies — tighten perms so a future leak
# (or any historical one) isn't world-readable.
try:
    os.chmod(_log_path, 0o600)
except OSError:
    pass

# Backoff state for refresh_access_token — prevents a bad user token from
# burning thousands of /me/accounts calls per day. min(prev*2+60, 1800),
# mirrored from bluesky_poster.
_last_refresh_ts: float = 0.0
_refresh_backoff: int   = 0

# ── Redis ──────────────────────────────────────────────────────────────────────
import redis as redis_lib
from comment_utils import get_counter_analyst_comment

def make_redis():
    return redis_lib.from_url(REDIS_URL, decode_responses=True)

r = make_redis()

# ── Graph API helpers ──────────────────────────────────────────────────────────
def _graph_url(path: str) -> str:
    return f"{GRAPH_API}/{path}"


def _is_oauth_error(resp: requests.Response) -> bool:
    """Return True if the response is a Facebook OAuthException 190 or 463."""
    try:
        err = resp.json().get("error", {})
        return err.get("type") == "OAuthException" and err.get("code") in (190, 463)
    except Exception:
        return False


def _is_rate_limit_error(resp: requests.Response) -> bool:
    """Return True if the response is a Facebook OAuthException 368 (spam/rate block)."""
    try:
        err = resp.json().get("error", {})
        return err.get("type") == "OAuthException" and err.get("code") == 368
    except Exception:
        return False


def _engage_rate_limit_cooldown() -> None:
    """Set the multi-hour cooldown key so the main loop stops posting."""
    try:
        r.setex(COOLDOWN_KEY, COOLDOWN_TTL, str(int(time.time())))
    except Exception as exc:
        log.warning("Could not persist rate-limit cooldown: %s", exc)
    log.warning("Facebook rate-limit (code 368) — cooling down for %ds", COOLDOWN_TTL)


def rate_limit_active() -> bool:
    try:
        return bool(r.exists(COOLDOWN_KEY))
    except Exception:
        return False


def _persist_token(new_token: str) -> None:
    """Write the refreshed token back to .env so it survives restarts."""
    try:
        with open(_ENV_PATH, "r") as fh:
            lines = fh.readlines()
        with open(_ENV_PATH, "w") as fh:
            for line in lines:
                if line.startswith("FACEBOOK_ACCESS_TOKEN="):
                    fh.write(f"FACEBOOK_ACCESS_TOKEN={new_token}\n")
                else:
                    fh.write(line)
        log.info("Persisted refreshed Facebook token to .env")
    except Exception as exc:
        log.warning("Could not persist token to .env: %s", exc)


def _do_refresh() -> bool:
    """API work for refresh_access_token; no backoff bookkeeping.

    Re-derives the Page access token by calling GET /me/accounts with the
    long-lived user token and selecting the entry whose id matches PAGE_ID.
    Page tokens derived from a long-lived user token inherit its ~60-day
    lifetime (System User tokens don't expire), so this replaces the old
    fb_exchange_token dance."""
    global ACCESS_TOKEN
    if not USER_ACCESS_TOKEN:
        log.error("FACEBOOK_USER_ACCESS_TOKEN not set — cannot derive Page token")
        return False
    if not PAGE_ID:
        log.error("FACEBOOK_PAGE_ID not set — cannot derive Page token")
        return False
    try:
        resp = requests.get(
            f"{GRAPH_API}/me/accounts",
            params={"access_token": USER_ACCESS_TOKEN, "fields": "id,access_token"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for page in data:
            if str(page.get("id")) == str(PAGE_ID):
                new_token = page.get("access_token")
                if not new_token:
                    log.error("Page %s present in /me/accounts but no access_token field", PAGE_ID)
                    return False
                ACCESS_TOKEN = new_token
                _persist_token(new_token)
                log.info("Re-derived Page access token for %s via /me/accounts", PAGE_ID)
                return True
        log.error("Page id %s not found in /me/accounts (%d pages visible to user token)",
                  PAGE_ID, len(data))
        return False
    except requests.HTTPError as exc:
        # Never log exc or the URL — query string contains the user token
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", "?")
        body = (getattr(resp, "text", "") or "")[:200]
        log.error("Page token derivation failed: HTTP %s — %s", status, body)
        return False
    except Exception as exc:
        log.error("Page token derivation failed: %s", type(exc).__name__)
        return False


def refresh_access_token() -> bool:
    """
    Re-derive the Page access token via /me/accounts (see _do_refresh).

    Failures engage an exponential backoff (60s → 1800s cap) so a bad
    user token doesn't drive thousands of requests per day; callers
    inside the backoff window get a fast False without an API hit.
    Success resets the backoff.
    """
    global _last_refresh_ts, _refresh_backoff
    now = time.time()
    if _refresh_backoff > 0 and (now - _last_refresh_ts) < _refresh_backoff:
        return False
    _last_refresh_ts = now

    if _do_refresh():
        _refresh_backoff = 0
        return True
    _refresh_backoff = min(_refresh_backoff * 2 + 60, 1800)
    log.warning("Refresh failed — backing off %ds before next attempt", _refresh_backoff)
    return False


def upload_photo_unpublished(image_url: str) -> str | None:
    """
    Download image_url and stage it as an unpublished Page photo.
    Returns the photo ID string on success, None on failure.
    The unpublished photo can then be attached to a feed post via attached_media.
    """
    try:
        img_resp = requests.get(image_url, timeout=15, stream=True)
        img_resp.raise_for_status()
        content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            log.warning("Non-image content-type '%s' from %s", content_type, image_url)
            return None
        img_bytes = img_resp.content

        # Convert PNG → JPEG (smaller, universally supported)
        if content_type == "image/png":
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            img_bytes = buf.getvalue()
            content_type = "image/jpeg"

        for attempt in range(2):
            resp = requests.post(
                _graph_url(f"{PAGE_ID}/photos"),
                params={"access_token": ACCESS_TOKEN, "published": "false"},
                files={"source": ("photo.jpg", img_bytes, content_type)},
                timeout=30,
            )
            if resp.status_code in (400, 401) and attempt == 0 and _is_oauth_error(resp):
                log.warning("OAuth error on photo upload (code %s) — refreshing token",
                            resp.json().get("error", {}).get("code"))
                if not refresh_access_token():
                    return None
                continue
            resp.raise_for_status()
            photo_id = resp.json().get("id")
            if photo_id:
                log.info("Uploaded unpublished photo: %s", photo_id)
            return photo_id
        return None
    except requests.HTTPError as exc:
        # Avoid str(exc) — URL contains ?access_token=...
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", "?")
        log.warning("Photo upload failed (%s): HTTP %s", image_url, status)
        return None
    except Exception as exc:
        log.warning("Photo upload failed (%s): %s", image_url, type(exc).__name__)
        return None


def post_to_page(message: str, article_url: str, image_url: str) -> bool:
    """
    Create a Facebook Page feed post with message, link, and image.
    Strategy:
      1. Upload image as unpublished photo → attach via attached_media
      2. If upload fails, fall back to link-only post (no image)
    """
    if not PAGE_ID or not ACCESS_TOKEN:
        log.error("FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not configured")
        return False

    # Try uploading the article image; fall back to default if it fails
    photo_id = upload_photo_unpublished(image_url)
    if photo_id is None and image_url != DEFAULT_IMAGE:
        log.info("Retrying photo upload with default image")
        photo_id = upload_photo_unpublished(DEFAULT_IMAGE)

    params: dict = {"access_token": ACCESS_TOKEN}
    payload: dict = {
        "message": message,
        "link":    article_url,
    }
    if photo_id:
        payload["attached_media"] = json.dumps([{"media_fbid": photo_id}])

    for attempt in range(2):
        try:
            params["access_token"] = ACCESS_TOKEN  # use current token on each attempt
            resp = requests.post(
                _graph_url(f"{PAGE_ID}/feed"),
                params=params,
                data=payload,
                timeout=20,
            )
            if resp.status_code in (400, 401) and attempt == 0 and _is_oauth_error(resp):
                log.warning("OAuth error on feed post (code %s) — refreshing token",
                            resp.json().get("error", {}).get("code"))
                if not refresh_access_token():
                    return False
                continue
            if resp.status_code == 400 and _is_rate_limit_error(resp):
                _engage_rate_limit_cooldown()
                return False
            resp.raise_for_status()
            post_id = resp.json().get("id", "unknown")
            log.info("Posted to Facebook Page: %s", post_id)
            return True
        except requests.HTTPError as exc:
            # Never log exc — its message includes the URL with ?access_token=...
            resp = getattr(exc, "response", None)
            status = getattr(resp, "status_code", "?")
            body = (getattr(resp, "text", "") or "")[:400]
            log.error("Facebook API error: HTTP %s — %s", status, body)
            return False
        except Exception as exc:
            log.error("Facebook post error: %s", type(exc).__name__)
            return False
    return False

# ── Article / Redis helpers ────────────────────────────────────────────────────
def get_article(article_id: str) -> dict | None:
    try:
        data = r.hgetall(f"article:{article_id}")
        return data if data else None
    except Exception as exc:
        log.error("Redis hgetall %s: %s", article_id, exc)
        return None




def build_post_text(article: dict, comment: str | None) -> tuple[str, str]:
    """Returns (message, article_url). URL also passed separately for the link field."""
    title = article.get("title", "").strip()
    url   = article.get("url") or f"{ARTICLE_BASE_URL}/article/{article.get('id', '')}"

    if comment:
        body = comment
    else:
        purple = article.get("purple_team_analysis", "")
        body = (purple[:300] + "…") if len(purple) > 300 else purple

    # Facebook allows up to 63,206 chars in message; keep it readable
    MAX_BODY = 500
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY - 1] + "…"

    return f"{title}\n\n{body}", url


def seed_posted_set():
    """
    On the *first* run only, mark every existing article as already-posted
    so we don't flood the Page with a backlog. Subsequent restarts skip
    this — otherwise an outage would silently drop every article queued
    while the poster was down (same bug class as the character posted-set).

    To force a re-seed (e.g. after wiping POSTED_SET): DEL facebook:seeded.
    """
    try:
        if r.exists(SEEDED_KEY):
            return
        keys = r.zrange("feed", 0, -1)
        if keys:
            pipe = r.pipeline()
            for article_id in keys:
                pipe.sadd(POSTED_SET, article_id)
            pipe.execute()
            log.info("First-run seed of facebook:posted with %d existing articles", len(keys))
        r.set(SEEDED_KEY, "1")
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
def log_data_access_expiry():
    """Log Graph API data_access_expires_at at startup so the renewal runway
    is visible in logs. The page token itself never expires (expires_at=0)
    but data access does — 90-day window renewed by re-auth. Visibility must
    never break posting: any failure here logs and continues."""
    if not (APP_ID and APP_SECRET):
        log.warning("FACEBOOK_APP_ID / FACEBOOK_APP_SECRET not set — cannot check data-access expiry")
        return
    try:
        resp = requests.get(
            f"{GRAPH_API}/debug_token",
            params={"input_token": ACCESS_TOKEN,
                    "access_token": f"{APP_ID}|{APP_SECRET}"},
            timeout=10,
        )
        exp_ts = resp.json().get("data", {}).get("data_access_expires_at")
        if exp_ts:
            exp = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            days = (exp - datetime.now(timezone.utc)).days
            log.info("Graph data access expires %s (%d days remaining) — re-auth before then",
                     exp.strftime("%Y-%m-%d"), days)
        else:
            log.warning("debug_token returned no data_access_expires_at — check token manually")
    except Exception as e:
        log.warning("data-access expiry check failed (%s: %s) — posting continues", type(e).__name__, e)


def main():
    log.info("facebook_poster v1.3 starting — page_id: %s", PAGE_ID or "(not set)")
    if not PAGE_ID:
        log.error("FACEBOOK_PAGE_ID must be set in .env — exiting")
        sys.exit(1)

    can_refresh = bool(USER_ACCESS_TOKEN)
    if can_refresh:
        # Re-derive Page token at startup so the cached one in .env is never stale.
        if refresh_access_token():
            log.info("Startup: Page token freshly derived from user token")
        elif ACCESS_TOKEN:
            log.warning("Startup refresh failed — falling back to cached FACEBOOK_ACCESS_TOKEN")
        else:
            log.error("Startup refresh failed and no cached Page token available — exiting")
            sys.exit(1)
    else:
        # Arc's .env has no FACEBOOK_USER_ACCESS_TOKEN yet — keep posting with the
        # cached Page token, but auto-re-derivation (the ~Aug 6 cliff protection)
        # stays OFF until the user token is provisioned.
        log.warning("FACEBOOK_USER_ACCESS_TOKEN not set — Page-token auto-re-derivation DISABLED; "
                    "using cached FACEBOOK_ACCESS_TOKEN. Provision the user token to enable "
                    "automatic refresh before Graph data access expires.")
        if not ACCESS_TOKEN:
            log.error("No cached FACEBOOK_ACCESS_TOKEN either — exiting")
            sys.exit(1)

    log_data_access_expiry()

    seed_posted_set()

    REFRESH_INTERVAL = 12 * 60 * 60  # proactive Page-token re-derivation cycle
    last_refresh = time.time()

    while True:
        try:
            if can_refresh and time.time() - last_refresh > REFRESH_INTERVAL:
                log.info("Proactive Page token refresh")
                if refresh_access_token():
                    last_refresh = time.time()
                # On failure, backoff state inside refresh_access_token gates
                # the next attempt; we just retry next loop iteration.

            if not autopost_enabled():
                time.sleep(POLL_INTERVAL)
                continue

            if rate_limit_active():
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

                message, url = build_post_text(article, comment)
                image_url = article.get("imageUrl", "") or DEFAULT_IMAGE
                if image_url.startswith("/"):
                    image_url = f"{ARTICLE_BASE_URL}{image_url}"

                success = post_to_page(message, url, image_url)

                if success:
                    log.info("Posted article %s to Facebook", article_id)
                    r.sadd(POSTED_SET, article_id)
                elif rate_limit_active():
                    # 368 tripped inside post_to_page — stop processing new_ids
                    # this cycle; the outer-loop cooldown gate handles the wait.
                    log.warning("Rate-limit cooldown active — deferring article %s and skipping remaining new IDs",
                                article_id)
                    break
                else:
                    log.error("Failed to post article %s — will retry next cycle", article_id)
                    continue

        except Exception as exc:
            log.exception("Outer loop error: %s", exc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
