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

logger = logging.getLogger(__name__)

STREAM_NAME = "analysis:pending"
CONSUMER_GROUP = "analysis_workers"

def get_redis_connection():
    """Get a Redis connection using environment variables."""
    password = os.environ['REDIS_PASSWORD']
    host = os.getenv('REDIS_HOST', 'localhost')
    port = int(os.getenv('REDIS_PORT', 6379))
    db = int(os.getenv('REDIS_DB', 0))
    return redis.Redis(host=host, port=port, password=password, db=db, decode_responses=True)


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
        msg_id = r.xadd(STREAM_NAME, {
            "article_id": article_id,
            "mission": mission,
            "analysis": analysis
        })
        logger.info(f"📡 Published {mission} analysis for {article_id[:12]}... → stream {msg_id}")
        return msg_id
    except Exception as e:
        logger.error(f"🔥 Failed to publish {mission} analysis for {article_id}: {e}")
        return None
