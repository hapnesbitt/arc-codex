#!/usr/bin/env python3
"""
mastodon_poster.py — Arc Codex auto-poster for Mastodon
v1.0 — modeled after bluesky_poster.py

On/off:  redis-cli set mastodon:autopost 1|0
Posted set: mastodon:posted (SET of article IDs, prevents duplicates)
Post format:
  {title}

  {counter-analyst comment — normalized}

  {article URL}

Fallback: purple_team_analysis excerpt if no counter-analyst within 60s
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

MASTODON_INSTANCE    = os.getenv("MASTODON_INSTANCE", "https://mastodon.social")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN", "")
REDIS_URL            = os.environ['REDIS_URL']
ARTICLE_BASE_URL     = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")

POLL_INTERVAL  = 15          # seconds between Redis scans
CA_WAIT        = 120         # seconds to wait for counter-analyst comment
                             # Floor, not ceiling — CA generation is async
                             # (shed-and-yield tiering, ~72s measured, may
                             # exceed 120s under load). Real fix: event-
                             # driven posting (see ops/RUNBOOK.md 2026-07-15).
POLL_KEY       = "mastodon:autopost"
POSTED_SET     = "mastodon:posted"
MAX_CHARS      = 500         # Mastodon default character limit

# ── logging ────────────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mastodon_poster] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "mastodon_poster.log")),
    ],
)
log = logging.getLogger("mastodon_poster")

# ── Redis ──────────────────────────────────────────────────────────────────────
import redis as redis_lib
from comment_utils import get_counter_analyst_comment
from redis_readiness import wait_for_redis

def make_redis():
    # Every caller inherits the boot-adjacent readiness retry via this
    # factory. See redis_readiness for the "started != ready" race.
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    wait_for_redis(r, log=log)
    return r

r = make_redis()

# ── Mastodon API ───────────────────────────────────────────────────────────────
def mastodon_headers() -> dict:
    return {
        "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

def mastodon_upload_image(og_image_url: str) -> str | None:
    """Download og_image and upload to Mastodon media store. Returns media_id or None."""
    if not og_image_url:
        return None
    try:
        img_resp = requests.get(og_image_url, timeout=10, stream=True)
        img_resp.raise_for_status()
        content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            return None
        img_bytes = img_resp.content

        # Convert PNG to JPEG for consistency
        if content_type == "image/png":
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            img_bytes = buf.getvalue()
            content_type = "image/jpeg"

        upload_resp = requests.post(
            f"{MASTODON_INSTANCE}/api/v1/media",
            headers={"Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"},
            files={"file": ("image.jpg", img_bytes, content_type)},
            timeout=30,
        )
        upload_resp.raise_for_status()
        media_id = upload_resp.json().get("id")
        if media_id:
            log.info("Media uploaded to Mastodon: id=%s", media_id)
        return media_id
    except Exception as exc:
        log.warning("Mastodon media upload failed: %s", exc)
        return None

def mastodon_post(text: str, og_image_url: str = "", article_url: str = "") -> bool:
    """
    Create a Mastodon post with optional image attachment.
    URL is appended to post text (Mastodon doesn't have embed cards like Bluesky).
    """
    if not MASTODON_ACCESS_TOKEN:
        log.error("MASTODON_ACCESS_TOKEN not set")
        return False

    # Upload image if available
    media_ids = []
    if not og_image_url:
        og_image_url = f"{ARTICLE_BASE_URL}/uploads/arc-codex-default.jpg"
    media_id = mastodon_upload_image(og_image_url)
    if media_id:
        media_ids.append(media_id)

    # Build status text — URL appended (Mastodon counts URLs as 23 chars)
    url_suffix = f"\n\n{article_url}" if article_url else ""
    max_text = MAX_CHARS - 23 - 2  # 23 for URL, 2 for \n\n
    if len(text) > max_text:
        text = text[:max_text - 1] + "…"
    status = text + url_suffix

    payload = {"status": status}
    if media_ids:
        payload["media_ids"] = media_ids

    try:
        resp = requests.post(
            f"{MASTODON_INSTANCE}/api/v1/statuses",
            headers=mastodon_headers(),
            json=payload,
            timeout=15,
        )
        if resp.status_code == 401:
            log.error("Mastodon 401 — check MASTODON_ACCESS_TOKEN")
            return False
        resp.raise_for_status()
        post_url = resp.json().get("url", "")
        log.info("Posted to Mastodon: %s", post_url)
        return True
    except Exception as exc:
        log.error("Mastodon post error: %s", exc)
        return False

# ── helpers (shared pattern with bluesky_poster) ───────────────────────────────
def get_article(article_id: str) -> dict | None:
    try:
        data = r.hgetall(f"article:{article_id}")
        return data if data else None
    except Exception as exc:
        log.error("Redis hgetall %s: %s", article_id, exc)
        return None


def build_post_text(article: dict, comment: str | None) -> tuple[str, str]:
    """Returns (post_text, article_url)."""
    title = article.get("title", "").strip()
    # Use stored url field directly — slug is not always populated in Redis
    url   = article.get("url") or f"{ARTICLE_BASE_URL}/article/{article.get('id', '')}"

    if comment:
        body = comment
    else:
        purple = article.get("purple_team_analysis", "")
        body = (purple[:200] + "…") if len(purple) > 200 else purple

    max_body = MAX_CHARS - 23 - 2 - len(title) - 2  # title + \n\n + URL
    if len(body) > max_body:
        body = body[:max_body - 1] + "…"

    return f"{title}\n\n{body}", url

def seed_posted_set():
    try:
        keys = r.zrange('feed', 0, -1)
        if not keys:
            return
        pipe = r.pipeline()
        for article_id in keys:
            pipe.sadd(POSTED_SET, article_id)
        pipe.execute()
        log.info("Seeded mastodon:posted with %d existing articles", len(keys))
    except Exception as exc:
        log.error("Seed failed: %s", exc)

def all_article_ids() -> list[str]:
    try:
        return r.zrange('feed', 0, -1)
    except Exception:
        return []

def autopost_enabled() -> bool:
    try:
        return r.get(POLL_KEY) == "1"
    except Exception:
        return False

# ── main loop ──────────────────────────────────────────────────────────────────
def main():
    log.info("mastodon_poster v1.0 starting — instance: %s", MASTODON_INSTANCE)
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

                comment = get_counter_analyst_comment(r, article_id, wait_seconds=CA_WAIT)
                if not comment:
                    log.warning("No counter-analyst for %s after %ds — using purple excerpt",
                                article_id, CA_WAIT)

                text, url = build_post_text(article, comment)
                og_image  = article.get("imageUrl", "")
                if og_image and og_image.startswith("/"):
                    og_image = f"{ARTICLE_BASE_URL}{og_image}"

                success = mastodon_post(text, og_image_url=og_image, article_url=url)

                if success:
                    log.info("Posted article %s to Mastodon", article_id)
                else:
                    log.error("Failed to post article %s — will retry next cycle", article_id)
                    continue

                r.sadd(POSTED_SET, article_id)

        except Exception as exc:
            log.exception("Outer loop error: %s", exc)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
