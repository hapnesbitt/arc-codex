#!/usr/bin/env python3
# Filename: analyzer.py
# Arc Codex Analyzer v1.0 - On-Demand Red/Blue/Purple Analysis Worker
#
# Watches Redis queue 'analyzer:queue' for article IDs.
# When triggered (by article view or scribe publish), runs the full
# ensemble or single-model analysis pipeline and publishes results
# via stream_utils → stream_consumer.
#
# This decouples analysis from ingestion: scribe.py publishes articles
# instantly with sentinel + counter-analyst, then queues them here.
# Analysis only runs when someone actually looks at the article.
#
# Usage: python3 analyzer.py
# Ctrl+C to stop gracefully.

import os
import sys
import re
import json
import time
import uuid
import logging
import yaml
import redis
from datetime import datetime, timezone
from dotenv import load_dotenv
from stream_utils import publish_analysis, ensure_stream_group
from ollama_utils import call_ollama_with_fallback, OLLAMA_CLOUD_MODEL, OLLAMA_LOCAL_FALLBACK
from ollama_utils import call_ollama_with_fallback, OLLAMA_CLOUD_MODEL, OLLAMA_LOCAL_FALLBACK

# Try ensemble import — graceful if not available
try:
    from ensemble import is_ensemble_enabled, run_ensemble_analysis, get_ensemble_config
    ENSEMBLE_AVAILABLE = True
except ImportError:
    ENSEMBLE_AVAILABLE = False

load_dotenv()

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_FILE = os.path.join(BASE_DIR, 'prompts.yaml')
LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'analyzer.log')
QUEUE_KEY = 'analyzer:queue'
REPLY_QUEUE_KEY = 'counteranalyst:reply_queue'
BLOCK_TIMEOUT = 5  # seconds to block on BRPOP before looping

# --- LOGGING ---
log_formatter = logging.Formatter('%(asctime)s - [ANALYZER v1.0] - %(levelname)s - %(message)s')
logger = logging.getLogger('analyzer')
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()
fh = logging.FileHandler(LOG_FILE)
fh.setFormatter(log_formatter)
logger.addHandler(fh)

# --- LOAD PROMPTS ---
PROMPTS = {}
try:
    with open(PROMPTS_FILE, 'r') as f:
        PROMPTS = yaml.safe_load(f)
    logger.info(f"✅ Loaded prompts from {PROMPTS_FILE}")
except Exception as e:
    logger.critical(f"🔥 PROMPTS FAILED TO LOAD: {e}")

# --- REDIS ---
r = None
try:
    r = redis.Redis(decode_responses=True, password=os.environ.get("REDIS_PASSWORD", "simplenes"))
    r.ping()
    logger.info("✅ Redis connection successful")
    ensure_stream_group(r)
except redis.exceptions.ConnectionError as e:
    logger.critical(f"🔥 Cannot connect to Redis: {e}")
    sys.exit(1)


# --- ANALYSIS FUNCTIONS ---

def build_unified_prompt():
    """Build the red/blue/purple analysis prompt from prompts.yaml."""
    if not PROMPTS:
        raise Exception("prompts.yaml not loaded!")

    mission = PROMPTS.get('mission', '')
    teams = PROMPTS.get('teams', {})
    constraints = PROMPTS.get('constraints', [])

    blue_instruction = teams.get('blue', {}).get('instruction', '')
    red_instruction = teams.get('red', {}).get('instruction', '')
    purple_instruction = teams.get('purple', {}).get('instruction', '')

    constraints_text = '\n'.join(f"- {c}" for c in constraints) if isinstance(constraints, list) else str(constraints)

    return f"""{mission}

RED TEAM (Facts Only):
{red_instruction}

BLUE TEAM (Executive Summary):
{blue_instruction}

PURPLE TEAM (Full Take):
{purple_instruction}

CONSTRAINTS:
{constraints_text}

CRITICAL: Format your response EXACTLY like this with XML tags:

<BLUE>
Your balanced summary here.
</BLUE>

<RED>
Your factual brief here.
</RED>

<PURPLE>
Your deeper analysis here.
</PURPLE>"""


def sanitize_text(text: str) -> str:
    """Clean up analysis text — strip markdown headers, bullets, underscores."""
    if not text:
        return ""
    lines = [line.lstrip('#-+ ').strip() for line in text.replace('_', '').splitlines() if line.lstrip('#-+ ').strip()]
    return "\n".join(lines)


def parse_unified_response(response_text: str) -> dict:
    """Parse <BLUE>, <RED>, <PURPLE> tagged response into dict."""
    analyses = {'blue': '', 'red': '', 'purple': ''}
    if not response_text:
        return analyses

    blue_match = re.search(r'<BLUE>(.*?)</BLUE>', response_text, re.DOTALL | re.IGNORECASE)
    red_match = re.search(r'<RED>(.*?)</RED>', response_text, re.DOTALL | re.IGNORECASE)
    purple_match = re.search(r'<PURPLE>(.*?)</PURPLE>', response_text, re.DOTALL | re.IGNORECASE)

    if blue_match:
        analyses['blue'] = sanitize_text(blue_match.group(1))
    if red_match:
        analyses['red'] = sanitize_text(red_match.group(1))
    if purple_match:
        analyses['purple'] = sanitize_text(purple_match.group(1))

    return analyses


def analyze_article(article_id: str) -> bool:
    """Run full red/blue/purple analysis on an article.
    
    Returns True if analysis was produced and published.
    """
    # Check if article exists
    redis_key = f"article:{article_id}"
    if not r.exists(redis_key):
        logger.warning(f"🚫 Article {article_id} not found in Redis — skipping")
        return False

    # Check if all three analyses already exist (avoid re-running)
    existing_blue = r.hget(redis_key, 'blue_team_analysis') or ''
    existing_red = r.hget(redis_key, 'red_team_analysis') or ''
    existing_purple = r.hget(redis_key, 'purple_team_analysis') or ''
    if len(existing_blue) > 10 and len(existing_red) > 10 and len(existing_purple) > 10:
        logger.info(f"✅ Article {article_id} already fully analyzed — skipping")
        return True
    if existing_blue or existing_red or existing_purple:
        logger.info(f"⚠️  Article {article_id} partially analyzed (blue={len(existing_blue)}, red={len(existing_red)}, purple={len(existing_purple)}) — re-running")

    # Get article text
    article_text = r.hget(redis_key, 'original_text') or ''
    if not article_text or len(article_text) < 100:
        logger.warning(f"⚠️  Article {article_id} has insufficient text ({len(article_text)} chars)")
        return False

    # Truncate to a safe size for local model context windows.
    # Stored original_text can be larger; we cap what goes to Ollama so the
    # model doesn't run out of context and return a truncated response that
    # only contains <BLUE> with missing </RED> and </PURPLE> closing tags.
    OLLAMA_MAX_CHARS = 20_000
    if len(article_text) > OLLAMA_MAX_CHARS:
        logger.warning(f"⚠️  Article text ({len(article_text)} chars) truncated to {OLLAMA_MAX_CHARS} chars for Ollama")
        article_text = article_text[:OLLAMA_MAX_CHARS]

    logger.info(f"🧠 Analyzing article {article_id} ({len(article_text)} chars)")
    analysis_start = time.perf_counter()

    analyses = {'blue': None, 'red': None, 'purple': None}

    # Try ensemble first if available
    if ENSEMBLE_AVAILABLE and is_ensemble_enabled():
        try:
            analyses = run_ensemble_analysis(article_text, PROMPTS)
            analyses.pop('_ensemble_meta', None)
            logger.info(f"🧬 Ensemble analysis complete for {article_id}")
        except Exception as e:
            logger.error(f"🔥 Ensemble failed: {e} — falling back to single model")
            analyses = {'blue': None, 'red': None, 'purple': None}

    # Single-model fallback
    if not any(analyses.values()):
        try:
            unified_instruction = build_unified_prompt()
            final_prompt = f"--- ARTICLE TEXT ---\n{article_text}\n\n--- ANALYSIS INSTRUCTIONS ---\n{unified_instruction}"

            raw_response, duration, model_used = call_ollama_with_fallback(final_prompt, timeout=900)
            logger.info(f"Analysis complete using {model_used} in {duration:.0f}ms")

            analyses = parse_unified_response(raw_response)

        except Exception as e:
            logger.error(f"🔥 Analysis failed for {article_id}: {e}")
            return False

    # Publish results via stream → stream_consumer applies them to Redis
    published = 0
    for mission, analysis_text in analyses.items():
        if analysis_text:
            publish_analysis(r, article_id, mission, analysis_text)
            published += 1

    total_ms = (time.perf_counter() - analysis_start) * 1000
    logger.info(f"✅ Published {published}/3 analyses for {article_id} in {total_ms:.0f}ms")
    return published > 0


def generate_ai_reply(payload: dict) -> bool:
    """Generate a follow-up reply when a user responds to the counter-analyst.
    
    One reply only — does not reply to its own replies (loop prevention).
    """
    article_id = payload.get('article_id', '')
    user_comment = payload.get('user_comment_text', '')
    ai_comment = payload.get('ai_comment_text', '')
    user_comment_id = payload.get('user_comment_id', '')
    user_author = payload.get('user_author', 'User')

    if not all([article_id, user_comment, ai_comment]):
        logger.warning("⚠️  AI reply payload missing fields — skipping")
        return False

    # Check: has the counter-analyst already replied to this user comment? (loop prevention)
    comment_ids = r.lrange(f"comments:{article_id}", 0, -1)
    for cid in comment_ids:
        c = r.hgetall(f"comment:{cid}")
        if c.get('author') == 'A.R.C. Counter-Analyst' and c.get('parent_id') == user_comment_id:
            logger.info(f"✅ AI already replied to comment {user_comment_id} — skipping")
            return True

    # Get article title for context
    article_data = r.hgetall(f"article:{article_id}")
    article_title = article_data.get('title', 'Unknown article')
    article_text = (article_data.get('original_text', '') or '')[:3000]

    reply_prompt = f"""You are the A.R.C. Counter-Analyst on Arc Codex, a platform for building cognitive resilience.

You previously posted this comment on an article titled "{article_title}":
"{ai_comment}"

A reader ({user_author}) replied to you:
"{user_comment}"

Write a brief, thoughtful follow-up (2-3 sentences max). Engage directly with their point. 
If they asked a question, answer it substantively using context from the article below.
If they made a good point, acknowledge it and build on it.
Stay civil, specific, and genuinely curious. End with a follow-up question only if natural.
Do NOT start with "Great question" or any generic praise.

--- ARTICLE CONTEXT (abbreviated) ---
{article_text}"""

    try:
        logger.info(f"🤖 Generating AI reply for article {article_id}...")
        raw_response, duration, model_used = call_ollama_with_fallback(reply_prompt, timeout=600)
        logger.info(f"🤖 AI reply generated via {model_used} in {duration:.0f}ms")

        reply_text = raw_response.strip()
        # Clean up common AI prefixes
        for prefix in ['Reply:', 'Response:', 'Follow-up:', 'Counter-Analyst:']:
            if reply_text.startswith(prefix):
                reply_text = reply_text[len(prefix):].strip()

        # Validate length
        if len(reply_text) < 15:
            logger.warning(f"⚠️  AI reply too short ({len(reply_text)} chars)")
            return False
        if len(reply_text) > 1500:
            sentences = reply_text.split('. ')
            reply_text = '. '.join(sentences[:3])
            if not reply_text.endswith(('.', '?')):
                reply_text += '.'

        # Post as a reply to the user's comment
        comment_id = str(uuid.uuid4())
        comment_data = {
            'id': comment_id,
            'article_id': article_id,
            'author': 'A.R.C. Counter-Analyst',
            'text': reply_text,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'parent_id': user_comment_id  # Reply to the user's comment
        }

        pipe = r.pipeline()
        pipe.hset(f"comment:{comment_id}", mapping=comment_data)
        pipe.rpush(f"comments:{article_id}", comment_id)
        pipe.execute()

        logger.info(f"🤖 AI reply posted for {article_id} ({len(reply_text)} chars)")
        return True

    except Exception as e:
        logger.error(f"🤖 AI reply failed: {e}")
        return False


# --- MAIN WORKER LOOP ---

def main():
    logger.info("🚀 Arc Codex Analyzer v1.0 - On-Demand Analysis Worker")
    if ENSEMBLE_AVAILABLE and is_ensemble_enabled():
        cfg = get_ensemble_config()
        logger.info(f"🧬 ENSEMBLE MODE: {cfg['analyst_1']} + {cfg['analyst_2']} + {cfg['analyst_3']} → {cfg['synthesizer']}")
    else:
        logger.info(f"📡 SINGLE MODEL: {OLLAMA_CLOUD_MODEL} → {OLLAMA_LOCAL_FALLBACK}")
    logger.info(f"📋 Watching queues: {QUEUE_KEY}, {REPLY_QUEUE_KEY}")

    # Process any backlog first
    backlog = r.llen(QUEUE_KEY)
    reply_backlog = r.llen(REPLY_QUEUE_KEY)
    if backlog > 0 or reply_backlog > 0:
        logger.info(f"📋 Backlog: {backlog} articles, {reply_backlog} reply requests")

    while True:
        try:
            # BRPOP watches both queues — returns (key, value) or None
            result = r.brpop([QUEUE_KEY, REPLY_QUEUE_KEY], timeout=BLOCK_TIMEOUT)

            if result is None:
                continue

            queue_name, payload = result

            if queue_name == QUEUE_KEY:
                # Article analysis request
                article_id = payload.strip()
                if article_id:
                    logger.info(f"📥 Received article {article_id} from analysis queue")
                    try:
                        analyze_article(article_id)
                    except Exception as e:
                        logger.error(f"🔥 Error analyzing {article_id}: {e}", exc_info=True)

            elif queue_name == REPLY_QUEUE_KEY:
                # AI reply request
                try:
                    reply_data = json.loads(payload)
                    logger.info(f"📥 Received reply request for article {reply_data.get('article_id', '?')}")
                    generate_ai_reply(reply_data)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️  Malformed reply payload — skipping")
                except Exception as e:
                    logger.error(f"🔥 Error generating reply: {e}", exc_info=True)

        except redis.exceptions.ConnectionError as e:
            logger.error(f"🔥 Redis connection lost: {e} — reconnecting in 5s")
            time.sleep(5)
        except Exception as e:
            logger.error(f"🔥 Unexpected error: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n🛑 Analyzer shutting down gracefully.")
