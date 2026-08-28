# Filename: stream_utils.py
# Shared Redis Streams utility for HapEnews analysis pipeline
# Used by scribe.py and manual_publisher.py to publish analysis events
#
# STREAM: analysis:pending
# PAYLOAD: {article_id, mission, analysis}
# CONSUMER GROUP: analysis_workers
#
# This replaces the filesystem-based JSON approach (pending_comments directory)
# with instant Redis Stream delivery.

import redis
import os
import logging

from redis_readiness import wait_for_redis

logger = logging.getLogger(__name__)

STREAM_NAME = "analysis:pending"
CONSUMER_GROUP = "analysis_workers"

def get_redis_connection():
    """Get a Redis connection using environment variables.

    Blocks up to 60s during a boot-adjacent start until Redis has finished
    loading its dataset — every caller of this factory (manual_publisher,
    stream_consumer, quiz_generator, scribe's stream side, and any new
    daemon that follows the pattern) inherits the readiness gate for free.
    On a Redis that has already finished loading the extra PING is
    sub-millisecond. See redis_readiness for the "started != ready" race
    this closes.
    """
    password = os.environ['REDIS_PASSWORD']
    host = os.getenv('REDIS_HOST', 'localhost')
    port = int(os.getenv('REDIS_PORT', 6379))
    db = int(os.getenv('REDIS_DB', 0))
    r = redis.Redis(host=host, port=port, password=password, db=db, decode_responses=True)
    wait_for_redis(r, log=logger)
    return r


def ensure_stream_group(r):
    """
    Create the consumer group if it doesn't exist.
    Safe to call multiple times — ignores 'group already exists' errors.
    """
    try:
        r.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id='0', mkstream=True)
        logger.info(f"✅ Created consumer group '{CONSUMER_GROUP}' on stream '{STREAM_NAME}'")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass  # Group already exists, that's fine
        else:
            raise


def publish_analysis(r, article_id: str, mission: str, analysis: str):
    """
    Publish an analysis result to the Redis Stream.
    
    Args:
        r: Redis connection
        article_id: The article hash ID
        mission: Team name (red, blue, purple)
        analysis: The analysis text
    
    Returns:
        The stream message ID, or None on failure
    """
    try:
        # MAXLEN ~10k (approximate): the consumer group reads only new
        # entries ('>'), so processed history is dead weight. Without a cap
        # the stream grew unbounded (85k entries / ~5 months by 2026-07-18).
        # Approximate trimming (~) trims in whole macro-nodes — cheap, and the
        # working set here is tiny (pending stays ~0).
        msg_id = r.xadd(STREAM_NAME, {
            "article_id": article_id,
            "mission": mission,
            "analysis": analysis
        }, maxlen=10000, approximate=True)
        logger.info(f"📡 Published {mission} analysis for {article_id[:12]}... → stream {msg_id}")
        return msg_id
    except Exception as e:
        logger.error(f"🔥 Failed to publish {mission} analysis for {article_id}: {e}")
        return None
