#!/usr/bin/env python3
"""
linkedin_poster.py — Arc Codex LinkedIn Auto-Poster v1.0
Watches Redis for newly published articles and posts them to LinkedIn.

On/off switch (Redis key):
    redis-cli -a $REDIS_PASSWORD set linkedin:autopost 1   # enable
    redis-cli -a $REDIS_PASSWORD set linkedin:autopost 0   # disable

Post format:
    {title}

    {counter-analyst comment}  (falls back to purple_team excerpt if not yet posted)

    {article URL}

Token refresh:
    LinkedIn tokens expire ~60 days. Re-run linkedin_auth.py to refresh.
    The poster will log a warning when posting fails with 401.
"""

import os
import time
import json
import random
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from dotenv import load_dotenv
import redis

load_dotenv()

# ==============================================================================
# CONFIG
# ==============================================================================
REDIS_URL         = os.getenv("REDIS_URL", "redis://:simplenes@localhost:6379/0")
ACCESS_TOKEN      = os.getenv("LINKEDIN_ACCESS_TOKEN")
MEMBER_ID         = os.getenv("LINKEDIN_MEMBER_ID")
ARTICLE_BASE_URL  = "https://arc-codex.com/article"

# Jitter: wait between MIN and MAX seconds after a new article is detected
JITTER_MIN_SEC    = 30
JITTER_MAX_SEC    = 180

# Poll interval — how often to check for new articles
POLL_INTERVAL_SEC = 15

# Redis keys
AUTOPOST_KEY      = "linkedin:autopost"
POSTED_SET_KEY    = "linkedin:posted"   # SET of article IDs already posted

LOG_FORMAT = "%(asctime)s - [LINKEDIN_POSTER] - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

# ==============================================================================
# LINKEDIN API
# ==============================================================================

def post_to_linkedin(title: str, comment: str, article_id: str) -> bool:
    """Post an article share to LinkedIn. Returns True on success."""
    url = f"{ARTICLE_BASE_URL}/{article_id}"
    post_text = f"{title}\n\n{comment}\n\n{url}"

    # UGC Posts API
    payload = {
        "author": f"urn:li:person:{MEMBER_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": post_text
                },
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "originalUrl": url,
                    }
                ]
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.linkedin.com/v2/ugcPosts",
        data=data,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            log.info(f"✅ Posted to LinkedIn: {result.get('id', 'unknown id')}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            log.error(f"❌ LinkedIn 401 Unauthorized — token expired. Re-run linkedin_auth.py to refresh.")
        elif e.code == 422:
            log.error(f"❌ LinkedIn 422 Unprocessable — {body}")
        else:
            log.error(f"❌ LinkedIn HTTP {e.code}: {body}")
        return False
    except Exception as e:
        log.error(f"❌ LinkedIn post failed: {e}")
        return False


# ==============================================================================
# REDIS HELPERS
# ==============================================================================

def get_counter_analyst_comment(r: redis.Redis, article_id: str) -> str | None:
    """Fetch the Counter-Analyst comment for an article.
    Comments list stores UUIDs; actual data is in comment:{uuid} hashes.
    """
    try:
        comment_ids = r.lrange(f"comments:{article_id}", 0, -1)
        for cid in comment_ids:
            cid_str = cid.decode() if isinstance(cid, bytes) else cid
            data = r.hgetall(f"comment:{cid_str}")
            if not data:
                continue
            decoded = {k.decode(): v.decode() for k, v in data.items()}
            if decoded.get("author") == "A.R.C. Counter-Analyst":
                text = decoded.get("text", "")
                # Normalize "The article" -> "This article"
                if text.lower().startswith("the article"):
                    text = "This article" + text[11:]
                return text
    except Exception as e:
        log.warning(f"Could not fetch comments for {article_id}: {e}")
    return None


def get_article(r: redis.Redis, article_id: str) -> dict | None:
    """Fetch article hash from Redis."""
    try:
        data = r.hgetall(f"article:{article_id}")
        if not data:
            return None
        return {k.decode(): v.decode() for k, v in data.items()}
    except Exception as e:
        log.warning(f"Could not fetch article {article_id}: {e}")
        return None


def get_all_article_ids(r: redis.Redis) -> list[str]:
    """Scan all article:* keys from Redis."""
    try:
        ids = []
        for key in r.scan_iter("article:*", count=500):
            article_id = key.decode().replace("article:", "")
            ids.append(article_id)
        return ids
    except Exception as e:
        log.warning(f"Could not scan article IDs: {e}")
        return []


def get_article_timestamp(r: redis.Redis, article_id: str) -> str:
    """Get the timestamp field of an article."""
    try:
        ts = r.hget(f"article:{article_id}", "timestamp")
        return ts.decode() if ts else ""
    except Exception:
        return ""


def is_autopost_enabled(r: redis.Redis) -> bool:
    try:
        val = r.get(AUTOPOST_KEY)
        return val is not None and val.decode().strip() == "1"
    except Exception:
        return False


def mark_posted(r: redis.Redis, article_id: str):
    r.sadd(POSTED_SET_KEY, article_id)


def already_posted(r: redis.Redis, article_id: str) -> bool:
    return bool(r.sismember(POSTED_SET_KEY, article_id))


# ==============================================================================
# MAIN LOOP
# ==============================================================================

def main():
    if not ACCESS_TOKEN or not MEMBER_ID:
        log.error("❌ LINKEDIN_ACCESS_TOKEN and LINKEDIN_MEMBER_ID must be set in .env")
        return

    log.info("🚀 Arc Codex LinkedIn Auto-Poster v1.0")
    log.info(f"   Poll interval: {POLL_INTERVAL_SEC}s")
    log.info(f"   Jitter: {JITTER_MIN_SEC}–{JITTER_MAX_SEC}s after detection")
    log.info(f"   On/off: redis-cli set {AUTOPOST_KEY} 1|0")
    log.info(f"   Member: urn:li:person:{MEMBER_ID}")

    # Connect to Redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=False)
    try:
        r.ping()
        log.info("✅ Redis connection successful")
    except Exception as e:
        log.error(f"❌ Redis connection failed: {e}")
        return

    # Seed posted set with ALL existing articles on first run
    # so we don't spam LinkedIn with old articles
    log.info("🌱 Seeding existing articles to prevent spam on startup...")
    existing_ids = get_all_article_ids(r)
    seeded = 0
    for aid in existing_ids:
        if not already_posted(r, aid):
            mark_posted(r, aid)
            seeded += 1
    log.info(f"🌱 Seeded {seeded} existing articles as already-posted ({len(existing_ids)} total)")

    log.info("👀 Watching for new articles...")

    while True:
        try:
            time.sleep(POLL_INTERVAL_SEC)

            if not is_autopost_enabled(r):
                continue

            # Check for new articles — any article:* key not in posted set
            current_ids = get_all_article_ids(r)
            new_ids = [aid for aid in current_ids if not already_posted(r, aid)]

            if not new_ids:
                continue

            for article_id in new_ids:
                # Mark immediately to prevent double-posting across poll cycles
                mark_posted(r, article_id)

                article = get_article(r, article_id)
                if not article:
                    log.warning(f"Could not load article {article_id} — skipping")
                    continue

                title = article.get("title", "").strip()
                if not title:
                    log.warning(f"Article {article_id} has no title — skipping")
                    continue

                # Wait for Counter-Analyst comment (posted async after article)
                comment = None
                for attempt in range(12):  # up to 60s
                    comment = get_counter_analyst_comment(r, article_id)
                    if comment:
                        break
                    log.info(f"⏳ Waiting for Counter-Analyst comment on {article_id[:12]}... ({attempt+1}/12)")
                    time.sleep(5)

                if not comment:
                    # Fallback to purple team excerpt
                    purple = article.get("purple_team_analysis", "")
                    comment = purple[:280].strip() if purple else ""
                    if comment:
                        log.info(f"⚠️  No Counter-Analyst comment — using purple team excerpt")
                    else:
                        log.warning(f"No comment or analysis for {article_id} — skipping")
                        continue

                # Natural jitter
                jitter = random.randint(JITTER_MIN_SEC, JITTER_MAX_SEC)
                log.info(f"📰 New article detected: {title[:60]}...")
                log.info(f"   Waiting {jitter}s before posting (jitter)...")
                time.sleep(jitter)

                # Re-check autopost in case it was disabled during jitter
                if not is_autopost_enabled(r):
                    log.info(f"⏸️  Autopost disabled during jitter — skipping {article_id[:12]}")
                    continue

                post_to_linkedin(title, comment, article_id)

        except KeyboardInterrupt:
            log.info("👋 LinkedIn poster stopped.")
            break
        except Exception as e:
            log.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(30)


if __name__ == "__main__":
    main()
