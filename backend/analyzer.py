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
import threading
import yaml
import redis
from urllib.parse import urlparse
from datetime import datetime, timezone
from dotenv import load_dotenv
from stream_utils import publish_analysis, ensure_stream_group
from ollama_utils import (
    call_ollama_with_fallback,
    call_ollama_local_only,
    is_cloud_available,
    is_cloud_reachable,
    OLLAMA_CLOUD_MODEL,
    OLLAMA_LOCAL_FALLBACK,
)
from escalation import (
    decide_escalate,
    get_source_stats,
    update_source_stats,
    cloud_capacity_available,
    record_cloud_call,
    label_local_analyses,
)
from operational_state import (
    AnalyzerOperationalState,
    reconcile_analyzer_dequeue,
    reinitialize_analyzer_queue_tracking,
    run_analyzer_heartbeat_loop,
)

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
# --- SITE CONFIG (schema v2) ---
# Per-site tunables come from the stack-root cfg; committed cfg values are
# canonical. Fails loud if the cfg is missing or incomplete.
from site_config import load_site_config
site = load_site_config()
_pipeline = site["pipeline"]

QUEUE_KEY = 'analyzer:queue'          # generic — isolated by unique Redis DB
REPLY_QUEUE_KEY = 'counteranalyst:reply_queue'
BLOCK_TIMEOUT = _pipeline["analyzer_pop_s"]  # seconds to block on BRPOP
# Crash-safe expiry for the dedup flag held during a run — sized ~2x worst
# observed inference so a dead analyzer releases the article promptly.
ANALYSIS_HOLD_TTL = _pipeline["analysis_hold_ttl_s"]
# Truncation caps (2026-07-21, decided): analysis_max_chars covers the p95
# truncated article (94k) and fits the 32k-token num_ctx with prompt +
# output budget. Above the garbage line it's a page dump — analyzing the
# first N chars of one produces confident noise, so skip analysis and leave
# the article published. num_ctx stays 32768: raising it balloons KV-cache
# memory on the inference Macs (tuning-pass experiment, not a default).
ANALYSIS_MAX_CHARS = _pipeline["analysis_max_chars"]
ANALYSIS_GARBAGE_CHARS = _pipeline["analysis_garbage_chars"]

# --- LOGGING ---
log_formatter = logging.Formatter('%(asctime)s - [ANALYZER v1.0] - %(levelname)s - %(message)s')
logger = logging.getLogger('analyzer')
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()

# Add errors='replace' so invalid bytes (like 0x96 en-dashes) display as replacement characters instead of crashing
fh = logging.FileHandler(LOG_FILE, encoding='utf-8', errors='replace')
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
    r = redis.Redis(decode_responses=True, password=os.environ['REDIS_PASSWORD'], db=site.redis_db)
    # Boot-adjacent readiness gate — see redis_readiness. Without this the
    # first PING here would raise BusyLoadingError during the load window
    # and the CRITICAL branch below would kill analyzer.
    from redis_readiness import wait_for_redis
    wait_for_redis(r, log=logger)
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
    """Parse <BLUE>, <RED>, <PURPLE> tagged response into dict.

    Accepts open-ended sections: `<TAG>...</TAG>` OR `<TAG>...<end of string>`.
    gemma4:e2b (and similar local models) sometimes stop mid-generation without
    emitting a closing tag — usually on PURPLE, since it's the last section.
    The section content IS there; the old regex just discarded it because it
    required </TAG>. Accepting `$` as an alternative terminator recovers those
    analyses without changing behavior on well-formed responses.
    """
    analyses = {'blue': '', 'red': '', 'purple': ''}
    if not response_text:
        return analyses

    blue_match = re.search(r'<BLUE>(.*?)(?:</BLUE>|$)', response_text, re.DOTALL | re.IGNORECASE)
    red_match = re.search(r'<RED>(.*?)(?:</RED>|$)', response_text, re.DOTALL | re.IGNORECASE)
    purple_match = re.search(r'<PURPLE>(.*?)(?:</PURPLE>|$)', response_text, re.DOTALL | re.IGNORECASE)

    if blue_match:
        analyses['blue'] = sanitize_text(blue_match.group(1))
    if red_match:
        analyses['red'] = sanitize_text(red_match.group(1))
    if purple_match:
        analyses['purple'] = sanitize_text(purple_match.group(1))

    return analyses


# --- CLUSTER-FAILURE DETECTION ---
# A single article can fail for legitimate content reasons (empty scrape,
# oversized prompt, model timeout on a specific piece). We do NOT want to page
# on those. But a run of consecutive failures means the analysis pipeline is
# systemically broken (model unavailable, config bug, network partition) —
# that's page-worthy. Reset on any success.

CLUSTER_FAILURE_COUNTER_KEY = "arc:analyzer:consecutive_total_failures"
CLUSTER_FAILURE_THRESHOLD   = 5   # N consecutive analysis-total-failures → alert

def _record_analysis_failure(article_id: str, reason: str) -> None:
    """Increment the consecutive-failure counter, escalate if past threshold."""
    try:
        count = r.incr(CLUSTER_FAILURE_COUNTER_KEY)
        # 6h TTL so the counter self-clears if the analyzer is idle overnight
        r.expire(CLUSTER_FAILURE_COUNTER_KEY, 21600)
    except Exception:
        return
    if count == CLUSTER_FAILURE_THRESHOLD:
        # Log the ONE escalation line the mailer will match. Distinct wording
        # so the mailer regex doesn't false-positive on individual failures.
        logger.error(
            f"🚨 CLUSTER FAILURE: {count} consecutive analysis-total-failures "
            f"(last: {article_id}, reason: {reason}) — pipeline unhealthy"
        )

def _reset_analysis_failure_counter() -> None:
    try:
        r.delete(CLUSTER_FAILURE_COUNTER_KEY)
    except Exception:
        pass


def analyze_article(article_id: str) -> bool:
    """Run full red/blue/purple analysis on an article.
    
    Returns True if analysis was produced and published.
    """
    global _analysis_outcome, _analysis_failure_stage
    _analysis_outcome = "completed"
    _analysis_failure_stage = None

    def fail(stage):
        global _analysis_outcome, _analysis_failure_stage
        _analysis_outcome = "failed"
        _analysis_failure_stage = stage
        return False

    # Check if article exists
    redis_key = f"article:{article_id}"
    if not r.exists(redis_key):
        logger.warning(f"🚫 Article {article_id} not found in Redis — skipping")
        return fail("missing_article")

    # Check if all three analyses already exist (avoid re-running)
    existing_blue = r.hget(redis_key, 'blue_team_analysis') or ''
    existing_red = r.hget(redis_key, 'red_team_analysis') or ''
    existing_purple = r.hget(redis_key, 'purple_team_analysis') or ''
    if len(existing_blue) > 10 and len(existing_red) > 10 and len(existing_purple) > 10:
        logger.info(f"✅ Article {article_id} already fully analyzed — skipping")
        _analysis_outcome = "skipped"
        return True
    if existing_blue or existing_red or existing_purple:
        logger.info(f"⚠️  Article {article_id} partially analyzed (blue={len(existing_blue)}, red={len(existing_red)}, purple={len(existing_purple)}) — re-running")

    # Get article text
    article_text = r.hget(redis_key, 'original_text') or ''
    if not article_text or len(article_text) < 100:
        logger.warning(f"⚠️  Article {article_id} has insufficient text ({len(article_text)} chars)")
        return fail("invalid_text")

    # Cap what goes to Ollama so the model doesn't run out of context and
    # return a truncated response with missing closing tags. Source domain in
    # the log lines so oversized offenders are attributable without
    # archaeology (three past monsters aged out of Redis unnamed).
    _source_url = r.hget(redis_key, 'sourceUrl') or ''
    _source_domain = urlparse(_source_url).netloc or 'unknown-source'
    if len(article_text) > ANALYSIS_GARBAGE_CHARS:
        logger.warning(
            f"🗑️  Article {article_id} is {len(article_text)} chars "
            f"(> {ANALYSIS_GARBAGE_CHARS}) — page dump, skipping analysis; "
            f"source: {_source_domain} ({_source_url[:100]})"
        )
        return fail("oversize")
    if len(article_text) > ANALYSIS_MAX_CHARS:
        logger.warning(
            f"⚠️  Article {article_id} text ({len(article_text)} chars) truncated "
            f"to {ANALYSIS_MAX_CHARS} for Ollama; source: {_source_domain}"
        )
        article_text = article_text[:ANALYSIS_MAX_CHARS]

    logger.info(f"🧠 Analyzing article {article_id} ({len(article_text)} chars)")
    analysis_start = time.perf_counter()

    analyses = {'blue': None, 'red': None, 'purple': None}
    analysis_source = None
    escalation_score = 0
    escalation_reason = ''

    # Try ensemble first if available (unchanged — ensemble is opt-in and owns
    # its own model selection). Local-first Option A-tightened applies to the
    # single-model path below.
    if ENSEMBLE_AVAILABLE and is_ensemble_enabled():
        try:
            analyses = run_ensemble_analysis(article_text, PROMPTS)
            analyses.pop('_ensemble_meta', None)
            analysis_source = 'ensemble'
            logger.info(f"🧬 Ensemble analysis complete for {article_id}")
        except Exception as e:
            logger.error(f"🔥 Ensemble failed: {e} — falling back to single model")
            analyses = {'blue': None, 'red': None, 'purple': None}

    # Single-model path — Option A-tightened: local first, escalate to cloud
    # only when decide_escalate flags a signal (parser-fail, vendor advertorial
    # heuristics, or local pattern flag). Weekly cloud cap is a hard backstop:
    # once hit, escalation degrades gracefully to local (labelled local_full
    # or local_partial) instead of failing.
    if not any(analyses.values()):
        try:
            unified_instruction = build_unified_prompt()
            final_prompt = f"--- ARTICLE TEXT ---\n{article_text}\n\n--- ANALYSIS INSTRUCTIONS ---\n{unified_instruction}"

            # Phase 1 — local run (call_ollama_local_only skips cloud entirely)
            local_analyses = {'blue': '', 'red': '', 'purple': ''}
            try:
                raw_local, dur_local, model_local = call_ollama_local_only(final_prompt, timeout=900)
                local_analyses = parse_unified_response(raw_local)
                logger.info(
                    f"🖥️  Local analysis {article_id} via {model_local} in {dur_local:.0f}ms "
                    f"(sections: {sum(1 for v in local_analyses.values() if v)}/3)"
                )
            except Exception as e:
                logger.warning(f"⚠️  Local model failed for {article_id}: {e} — will attempt cloud via escalation")

            # Phase 2 — decide whether to escalate
            article_data = r.hgetall(redis_key)
            article_data['id'] = article_id
            source_stats = get_source_stats(r, article_data)
            decision = decide_escalate(local_analyses, article_data, source_stats=source_stats)
            escalation_score = decision.score
            escalation_reason = decision.reason

            # Order matters: capacity → breaker → REACHABILITY → record → HTTP.
            # Reachability must precede record_cloud_call so an unreachable
            # cloud host never increments the cap (2026-07-07: 2,755 doomed
            # escalations recorded against a dead M1).
            if (decision.escalate and cloud_capacity_available(r)
                    and is_cloud_available() and is_cloud_reachable()):
                logger.info(
                    f"⬆️  Escalating {article_id} to cloud "
                    f"(score={decision.score}, reason={decision.reason})"
                )
                # Record BEFORE the call so a mid-flight crash can't under-count.
                # Over-counting a failed call is safer than under-counting a
                # successful one when the counter is the cap-enforcing signal.
                record_cloud_call(r)
                try:
                    raw_cloud, dur_cloud, model_cloud = call_ollama_with_fallback(
                        final_prompt,
                        timeout=900,
                        models=[(OLLAMA_CLOUD_MODEL, "cloud")],
                    )
                    cloud_analyses = parse_unified_response(raw_cloud)
                    if any(cloud_analyses.values()):
                        analyses = cloud_analyses
                        analysis_source = 'cloud'
                        logger.info(f"☁️  Cloud analysis {article_id} via {model_cloud} in {dur_cloud:.0f}ms")
                except Exception as e:
                    logger.warning(f"⚠️  Cloud escalation failed for {article_id}: {e} — keeping local")
            elif decision.escalate:
                # A-relaxed graceful degradation: signal fired but the cloud
                # valve is closed. Continue with local, honestly labelled —
                # never page. Say WHICH condition closed the valve: during the
                # July cap exhaustion this read "cap, breaker, or unreachable"
                # for 5 days and the answer was archaeology. Checks ordered
                # cheap-first; reachability (an HTTP probe) runs only when the
                # first two pass.
                if not cloud_capacity_available(r):
                    valve = "weekly cap exhausted"
                elif not is_cloud_available():
                    valve = "429 circuit breaker open"
                elif not is_cloud_reachable():
                    valve = "cloud host unreachable"
                else:
                    valve = "transient (condition cleared between checks)"
                logger.info(
                    f"🛑 {article_id} escalation triggered (score={decision.score}, "
                    f"reason={decision.reason}) but cloud valve closed: {valve} "
                    f"— degrading to local"
                )

            # If cloud didn't take over, use local. Label according to shape.
            if analysis_source is None:
                analyses = local_analyses
                analysis_source = label_local_analyses(local_analyses)

            # Update rolling source stats (best-effort — never breaks analysis)
            update_source_stats(
                r,
                article_data,
                escalated=(analysis_source == 'cloud'),
                reasons=escalation_reason,
            )

        except Exception as e:
            logger.warning(f"⚠️  Analysis skipped for {article_id}: {e}")
            _record_analysis_failure(article_id, reason=str(e))
            return fail("inference")

    # Persist escalation metadata alongside the article. Frontend keys off
    # analysis_source='local_partial' to render a transparency badge; 'cloud'
    # and 'local_full' are silent (publication-quality doesn't invite doubt).
    try:
        meta = {
            'analysis_source': analysis_source or 'unknown',
            'escalation_score': str(escalation_score),
        }
        if escalation_reason:
            meta['escalation_reason'] = escalation_reason
        r.hset(redis_key, mapping=meta)
    except Exception:
        pass

    # Publish results via stream → stream_consumer applies them to Redis
    published = 0
    try:
        for mission, analysis_text in analyses.items():
            if analysis_text:
                publish_analysis(r, article_id, mission, analysis_text)
                published += 1
    except Exception:
        fail("publish")
        raise

    total_ms = (time.perf_counter() - analysis_start) * 1000
    logger.info(
        f"✅ Published {published}/3 analyses for {article_id} in {total_ms:.0f}ms "
        f"(source={analysis_source or 'unknown'})"
    )
    if published > 0:
        _reset_analysis_failure_counter()
    else:
        _record_analysis_failure(article_id, reason="published 0/3 sections")
    return published > 0 if published else fail("publish")


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
        raw_response, duration, model_used = call_ollama_with_fallback(reply_prompt, timeout=600, num_ctx=8192)
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
    # Cross-site isolation validation at startup (spec: run in CI and at
    # service startup) — refuse to run against colliding site cfgs.
    import validate_sites
    _cfg_errors = validate_sites.check(
        validate_sites.discover(os.environ.get("SITES_ROOT", "/home/www")))
    if _cfg_errors:
        for _e in _cfg_errors:
            logger.critical(f"🔥 site cfg violation: {_e}")
        raise SystemExit(1)

    logger.info(f"🚀 {site.name} Analyzer v1.0 - On-Demand Analysis Worker [{site.path}]")
    if ENSEMBLE_AVAILABLE and is_ensemble_enabled():
        cfg = get_ensemble_config()
        logger.info(f"🧬 ENSEMBLE MODE: {cfg['analyst_1']} + {cfg['analyst_2']} + {cfg['analyst_3']} → {cfg['synthesizer']}")
    else:
        logger.info(f"📡 SINGLE MODEL: {OLLAMA_CLOUD_MODEL} → {OLLAMA_LOCAL_FALLBACK}")
    logger.info(f"📋 Watching queues: {QUEUE_KEY}, {REPLY_QUEUE_KEY}")

    analyzer_ops = AnalyzerOperationalState(r, logger=logger)
    analyzer_ops.set_status("starting")
    threading.Thread(
        target=run_analyzer_heartbeat_loop,
        args=(analyzer_ops,),
        daemon=True,
        name="analyzer-operational-heartbeat",
    ).start()
    reinitialize_analyzer_queue_tracking(r)
    analyzer_ops.set_status("idle")

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
                analyzer_ops.set_status("idle")
                reinitialize_analyzer_queue_tracking(r)
                continue

            queue_name, payload = result

            if queue_name == QUEUE_KEY:
                # Article analysis request
                article_id = payload.strip()
                reconcile_analyzer_dequeue(r, article_id or "malformed")
                if article_id:
                    # Hold the dedup flag through the whole run so page views
                    # during a slow analysis can't re-enqueue the same ID.
                    # Deleted only on a successful publish; on failure or a
                    # crash the TTL is the release.
                    dedup_key = f"analyzer:queued:{article_id}"
                    r.set(dedup_key, '1', ex=ANALYSIS_HOLD_TTL)
                    logger.info(f"📥 Received article {article_id} from analysis queue")
                    started = time.monotonic()
                    analyzer_ops.start_job(article_id)
                    try:
                        success = analyze_article(article_id)
                        outcome = globals().get("_analysis_outcome", "completed" if success else "failed")
                        stage = globals().get("_analysis_failure_stage")
                        if success:
                            r.delete(dedup_key)
                        analyzer_ops.finish_job(
                            article_id, outcome, time.monotonic() - started, stage=stage)
                    except Exception as e:
                        logger.error(f"🔥 Error analyzing {article_id}: {e}", exc_info=True)
                        analyzer_ops.finish_job(
                            article_id, "failed", time.monotonic() - started,
                            stage=globals().get("_analysis_failure_stage") or "unexpected")
                else:
                    analyzer_ops.start_job("malformed")
                    analyzer_ops.finish_job("malformed", "failed", 0, stage="malformed_payload")

            elif queue_name == REPLY_QUEUE_KEY:
                # AI reply request
                analyzer_ops.set_status("active")
                try:
                    reply_data = json.loads(payload)
                    logger.info(f"📥 Received reply request for article {reply_data.get('article_id', '?')}")
                    generate_ai_reply(reply_data)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️  Malformed reply payload — skipping")
                except Exception as e:
                    logger.error(f"🔥 Error generating reply: {e}", exc_info=True)
                finally:
                    analyzer_ops.set_status("idle")

        except redis.exceptions.ConnectionError as e:
            logger.error(f"🔥 Redis connection lost: {e} — reconnecting in 5s")
            analyzer_ops.set_status("failed")
            time.sleep(5)
        except Exception as e:
            logger.error(f"🔥 Unexpected error: {e}", exc_info=True)
            analyzer_ops.set_status("failed")
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n🛑 Analyzer shutting down gracefully.")
