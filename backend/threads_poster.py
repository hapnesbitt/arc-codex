#!/usr/bin/env python3
"""
threads_poster.py — Arc Codex auto-poster for Threads
v1.0

On/off:  redis-cli set threads:autopost 1|0
Posted set: threads:posted (SET of article IDs, prevents duplicates)
Post format:
  {title}

  {article URL}

Threads renders OG link preview from the URL — no separate image upload needed.
Seeds all existing articles on startup to prevent spam.

Env vars (backend/.env):
  THREADS_ACCESS_TOKEN  — long-lived token (expires ~60 days, re-run threads_auth.py to refresh)
  THREADS_USER_ID       — numeric Threads user ID
"""

import os
import time
import json
import logging
import requests
from dotenv import load_dotenv

# ── env ────────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID      = os.getenv("THREADS_USER_ID", "")
REDIS_URL            = os.environ['REDIS_URL']
ARTICLE_BASE_URL     = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")

THREADS_API_BASE = "https://graph.threads.net/v1.0"
POLL_INTERVAL    = 15       # seconds between Redis scans
POLL_KEY         = "threads:autopost"
POSTED_SET       = "threads:posted"
MAX_CHARS        = 500      # Threads character limit

# ── logging ────────────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [threads_poster] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "threads_poster.log")),
    ],
)
log = logging.getLogger("threads_poster")

# ── Redis ──────────────────────────────────────────────────────────────────────
import redis as redis_lib

def make_redis():
    return redis_lib.from_url(REDIS_URL, decode_responses=True)

r = make_redis()

# ── Threads API ────────────────────────────────────────────────────────────────
def _threads_params(**kwargs) -> dict:
    """Base params injected into every Threads API call."""
    return {"access_token": THREADS_ACCESS_TOKEN, **kwargs}


def threads_create_container(text: str) -> str | None:
    """
    Step 1: create a TEXT media container.
    Returns container ID or None on failure.
    """
    url = f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads"
    try:
        resp = requests.post(
            url,
            params=_threads_params(media_type="TEXT", text=text),
            timeout=20,
        )
        if not resp.ok:
            log.error("Container creation failed %s: %s", resp.status_code, resp.text[:200])
            return None
        container_id = resp.json().get("id")
        log.info("Container created: %s", container_id)
        return container_id
    except Exception as exc:
        log.error("threads_create_container error: %s", exc)
        return None


def threads_publish_container(container_id: str) -> bool:
    """
    Step 2: publish the container.
    Brief pause between create and publish recommended by Threads API docs.
    """
    url = f"{THREADS_API_BASE}/{THREADS_USER_ID}/threads_publish"
    try:
        resp = requests.post(
            url,
            params=_threads_params(creation_id=container_id),
            timeout=20,
        )
        if not resp.ok:
            log.error("Publish failed %s: %s", resp.status_code, resp.text[:200])
            return False
        post_id = resp.json().get("id", "")
        log.info("Published to Threads: post_id=%s", post_id)
        return True
    except Exception as exc:
        log.error("threads_publish_container error: %s", exc)
        return False


def threads_post(text: str) -> bool:
    """Full two-step post. Returns True on success."""
    if not THREADS_ACCESS_TOKEN or not THREADS_USER_ID:
        log.error("THREADS_ACCESS_TOKEN and THREADS_USER_ID must be set in .env")
        return False

    container_id = threads_create_container(text)
    if not container_id:
        return False

    time.sleep(2)   # Threads API recommendation between create and publish
    return threads_publish_container(container_id)

# ── helpers (shared pattern with bluesky/mastodon posters) ────────────────────
def get_article(article_id: str) -> dict | None:
    try:
        data = r.hgetall(f"article:{article_id}")
        return data if data else None
    except Exception as exc:
        log.error("Redis hgetall %s: %s", article_id, exc)
        return None


def build_post_text(article: dict) -> str:
    """
    Returns post text: title + URL only (per spec).
    URL triggers Threads link preview which renders OG image automatically.
    """
    title = article.get("title", "").strip()
    # Use stored url field directly — slug is not always populated in Redis
    url   = article.get("url") or f"{ARTICLE_BASE_URL}/article/{article.get('id', '')}"

    url_suffix = f"\n\n{url}"
    max_title  = MAX_CHARS - len(url_suffix)
    if len(title) > max_title:
        title = title[:max_title - 1] + "…"

    return f"{title}{url_suffix}"


def seed_posted_set():
    try:
        article_ids = r.zrange('feed', 0, -1)
        if not article_ids:
            return
        pipe = r.pipeline()
        for article_id in article_ids:
            pipe.sadd(POSTED_SET, article_id)
        pipe.execute()
        log.info("Seeded threads:posted with %d existing articles", len(article_ids))
    except Exception as exc:
        log.error("Seed failed: %s", exc)


def all_article_ids() -> list[str]:
    try:
        return list(r.zrange('feed', 0, -1))
    except Exception:
        return []


def autopost_enabled() -> bool:
    try:
        return r.get(POLL_KEY) == "1"
    except Exception:
        return False

# ── main loop ──────────────────────────────────────────────────────────────────
def main():
    log.info("threads_poster v1.0 starting — user_id: %s", THREADS_USER_ID)
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

                # Skip private articles
                if article.get("visibility") == "private":
                    r.sadd(POSTED_SET, article_id)
                    continue

                text    = build_post_text(article)
                success = threads_post(text)

                if success:
                    log.info("Posted article %s to Threads", article_id)
                    r.sadd(POSTED_SET, article_id)
                else:
                    log.error("Failed to post article %s — will retry next cycle", article_id)
                    # don't sadd — retry next cycle

        except Exception as exc:
            log.exception("Outer loop error: %s", exc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
