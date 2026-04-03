#!/usr/bin/env python3
"""
facebook_poster.py — Arc Codex auto-poster for Facebook Pages
v1.1 — automatic token refresh on OAuthException 190/463

On/off:  redis-cli set facebook:autopost 1|0
Posted set: facebook:posted (SET of article IDs, prevents duplicates)

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
from dotenv import load_dotenv

# ── env ────────────────────────────────────────────────────────────────────────
_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_ENV_PATH)

APP_ID           = os.getenv("FACEBOOK_APP_ID", "")
APP_SECRET       = os.getenv("FACEBOOK_APP_SECRET", "")
PAGE_ID          = os.getenv("FACEBOOK_PAGE_ID", "")
ACCESS_TOKEN     = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
REDIS_URL        = os.getenv("REDIS_URL", "redis://:simplenes@localhost:6379/0")
ARTICLE_BASE_URL = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")
DEFAULT_IMAGE    = f"{ARTICLE_BASE_URL}/uploads/arc-codex-default.jpg"

POLL_INTERVAL = 15          # seconds between Redis scans
JITTER_MIN    = 30          # seconds
JITTER_MAX    = 180
CA_WAIT       = 60          # seconds to wait for counter-analyst comment
POLL_KEY      = "facebook:autopost"
POSTED_SET    = "facebook:posted"

GRAPH_API     = "https://graph.facebook.com/v19.0"

# ── logging ────────────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [facebook_poster] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "facebook_poster.log")),
    ],
)
log = logging.getLogger("facebook_poster")

# ── Redis ──────────────────────────────────────────────────────────────────────
import redis as redis_lib

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


def refresh_access_token() -> bool:
    """
    Exchange the current ACCESS_TOKEN for a long-lived token via
    oauth/access_token (grant_type=fb_exchange_token).
    Updates the global ACCESS_TOKEN and persists to .env.
    Returns True on success.
    """
    global ACCESS_TOKEN
    if not APP_ID or not APP_SECRET:
        log.error("FACEBOOK_APP_ID / FACEBOOK_APP_SECRET not set — cannot refresh token")
        return False
    try:
        resp = requests.get(
            f"{GRAPH_API}/oauth/access_token",
            params={
                "grant_type":        "fb_exchange_token",
                "client_id":         APP_ID,
                "client_secret":     APP_SECRET,
                "fb_exchange_token": ACCESS_TOKEN,
            },
            timeout=15,
        )
        resp.raise_for_status()
        new_token = resp.json().get("access_token")
        if not new_token:
            log.error("Token refresh response missing access_token: %s", resp.text[:200])
            return False
        ACCESS_TOKEN = new_token
        _persist_token(new_token)
        log.info("Facebook access token refreshed successfully")
        return True
    except Exception as exc:
        log.error("Token refresh failed: %s", exc)
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
    except Exception as exc:
        log.warning("Photo upload failed (%s): %s", image_url, exc)
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
            resp.raise_for_status()
            post_id = resp.json().get("id", "unknown")
            log.info("Posted to Facebook Page: %s", post_id)
            return True
        except requests.HTTPError as exc:
            body = exc.response.text[:400] if exc.response is not None else str(exc)
            log.error("Facebook API error: %s — %s", exc, body)
            return False
        except Exception as exc:
            log.error("Facebook post error: %s", exc)
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
    try:
        keys = r.zrange("feed", 0, -1)
        if not keys:
            return
        pipe = r.pipeline()
        for article_id in keys:
            pipe.sadd(POSTED_SET, article_id)
        pipe.execute()
        log.info("Seeded facebook:posted with %d existing articles", len(keys))
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
    log.info("facebook_poster v1.1 starting — page_id: %s  app_id: %s",
             PAGE_ID or "(not set)", APP_ID or "(not set)")
    if not PAGE_ID or not ACCESS_TOKEN:
        log.error("FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN must be set in .env — exiting")
        sys.exit(1)
    if not APP_ID or not APP_SECRET:
        log.warning("FACEBOOK_APP_ID / FACEBOOK_APP_SECRET not set — token auto-refresh disabled")

    seed_posted_set()

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

                message, url = build_post_text(article, comment)
                image_url = article.get("imageUrl", "") or DEFAULT_IMAGE
                if image_url.startswith("/"):
                    image_url = f"{ARTICLE_BASE_URL}{image_url}"

                success = post_to_page(message, url, image_url)

                if success:
                    log.info("Posted article %s to Facebook", article_id)
                else:
                    log.error("Failed to post article %s — will retry next cycle", article_id)
                    continue

                r.sadd(POSTED_SET, article_id)

        except Exception as exc:
            log.exception("Outer loop error: %s", exc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
