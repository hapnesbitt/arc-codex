#!/usr/bin/env python3
# Filename: stream_consumer.py
# Version 1.0 - "Stream Consumer v1.0" - Redis Streams replacement for cleaner.py
#
# Replaces filesystem polling (pending_comments directory) with Redis Streams.
# Blocks on XREADGROUP — processes analysis events instantly with zero polling delay.
#
# Usage: python3 stream_consumer.py
# Ctrl+C to stop gracefully.

import redis
import os
import sys
import logging
import time
from dotenv import load_dotenv
from stream_utils import (
    STREAM_NAME, CONSUMER_GROUP, 
    get_redis_connection, ensure_stream_group
)

load_dotenv()

# --- Configuration ---
CONSUMER_NAME = os.getenv("STREAM_CONSUMER_NAME", "consumer-1")
BLOCK_MS = 5000  # Block for 5 seconds waiting for new messages, then loop
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "stream_consumer.log")

# --- Logging Setup ---
logger = logging.getLogger('stream_consumer')
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - [STREAM_CONSUMER] - %(levelname)s - %(message)s')
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

# --- Field mapping ---
FIELD_MAP = {
    "blue": "blue_team_analysis",
    "red": "red_team_analysis",
    "purple": "purple_team_analysis",
    "gray": "dossier",
    "sentinel": "sentinel_analysis"
}


def apply_analysis(r, article_id: str, mission: str, analysis: str):
    """Apply a single analysis to its article in Redis."""
    process_start = time.perf_counter()

    redis_field = FIELD_MAP.get(mission)
    if not redis_field:
        logger.warning(f"❓ Unknown mission '{mission}' for article {article_id[:12]}... — skipping")
        return False

    redis_key = f"article:{article_id}"
    if not r.exists(redis_key):
        logger.warning(f"🚫 Article {article_id} not found in Redis — skipping")
        return False

    redis_start = time.perf_counter()
    r.hset(redis_key, redis_field, analysis)
    redis_ms = (time.perf_counter() - redis_start) * 1000
    total_ms = (time.perf_counter() - process_start) * 1000

    logger.info(
        f"✅ Applied '{mission}' analysis to article {article_id[:12]}... "
        f"in {total_ms:.0f}ms (Redis: {redis_ms:.0f}ms)"
    )

    return True


def process_messages(r):
    """
    Main consumer loop. Blocks on XREADGROUP waiting for new messages.
    Acknowledges each message after successful processing.
    """
    logger.info(f"🚀 Stream Consumer '{CONSUMER_NAME}' active")
    logger.info(f"   Stream: {STREAM_NAME}")
    logger.info(f"   Group: {CONSUMER_GROUP}")
    logger.info(f"   Blocking: {BLOCK_MS}ms per read cycle")

    # First, recover any unacknowledged messages from previous runs
    recover_pending(r)

    while True:
        try:
            # Block waiting for new messages
            results = r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_NAME: '>'},  # '>' means only new, undelivered messages
                count=10,
                block=BLOCK_MS
            )

            if not results:
                continue  # Timeout, loop back and block again

            for stream_name, messages in results:
                for msg_id, data in messages:
                    article_id = data.get("article_id", "")
                    mission = data.get("mission", "")
                    analysis = data.get("analysis", "")

                    if not all([article_id, mission, analysis]):
                        logger.warning(f"⚠️  Malformed message {msg_id}: missing fields — acknowledging to skip")
                        r.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
                        continue

                    success = apply_analysis(r, article_id, mission, analysis)

                    # Acknowledge regardless — if the article doesn't exist,
                    # retrying won't help
                    r.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)

                    if not success:
                        logger.warning(f"⚠️  Message {msg_id} processed but not applied — acknowledged anyway")

        except redis.exceptions.ConnectionError as e:
            logger.error(f"🔥 Redis connection lost: {e} — reconnecting in 5s")
            time.sleep(5)
        except Exception as e:
            logger.error(f"🔥 Unexpected error: {e}", exc_info=True)
            time.sleep(5)


def recover_pending(r):
    """
    Check for any messages claimed by this consumer but not yet acknowledged
    (e.g. from a previous crash). Process them before reading new messages.
    """
    logger.info("🔍 Checking for unacknowledged messages from previous run...")
    try:
        results = r.xreadgroup(
            CONSUMER_GROUP,
            CONSUMER_NAME,
            {STREAM_NAME: '0'},  # '0' means re-read pending messages for this consumer
            count=100
        )

        if not results:
            logger.info("   No pending messages found — clean start")
            return

        recovered = 0
        for stream_name, messages in results:
            for msg_id, data in messages:
                if not data:
                    # Empty data means already acknowledged, skip
                    r.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
                    continue

                article_id = data.get("article_id", "")
                mission = data.get("mission", "")
                analysis = data.get("analysis", "")

                if all([article_id, mission, analysis]):
                    apply_analysis(r, article_id, mission, analysis)
                
                r.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
                recovered += 1

        if recovered:
            logger.info(f"   ♻️  Recovered and processed {recovered} pending message(s)")

    except Exception as e:
        logger.warning(f"   ⚠️  Pending recovery failed: {e} — continuing with new messages")


def stream_health(r):
    """Print stream health info on startup."""
    try:
        info = r.xinfo_stream(STREAM_NAME)
        groups = r.xinfo_groups(STREAM_NAME)
        logger.info(f"📊 Stream health: {info.get('length', 0)} messages, {len(groups)} consumer group(s)")
        for g in groups:
            logger.info(f"   Group '{g['name']}': {g['pending']} pending, {g['consumers']} consumer(s)")
    except redis.exceptions.ResponseError:
        logger.info("📊 Stream not yet created — will be created on first publish")


def main():
    logger.info("--- Arc Codex Stream Consumer v1.0 (Stream Consumer v1.0) ---")
    
    r = get_redis_connection()
    try:
        r.ping()
        logger.info("✅ Redis connection successful")
    except Exception as e:
        logger.critical(f"🔥 Redis connection failed: {e}")
        sys.exit(1)

    ensure_stream_group(r)
    stream_health(r)
    process_messages(r)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nShutdown signal received. Stream Consumer shutting down gracefully.")
