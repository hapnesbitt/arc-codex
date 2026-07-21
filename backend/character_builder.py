#!/usr/bin/env python3
"""
character_builder.py — Arc Codex Character Comment Daemon
v1.0 — Mar 16, 2026

Reads characters.yaml, monitors Redis for fully-analyzed articles,
and posts character comments to the Redis comment store.

Characters run AFTER the full analysis pipeline — they read the entire
dossier (article + red + blue + purple + sentinel + counter-analyst)
and comment on the whole picture.

On/off:  redis-cli set characters:enabled 1|0

Article state per character (three-state, replaces the old posted-on-pickup
model that permanently dropped articles whose analysis timed out):
  characters:pending:{handle}  SET  — picked up, no terminal state yet
  characters:posted:{handle}   SET  — comment landed, or deliberate drop
  characters:skipped:{handle}  ZSET — retryable skip (score = last attempt
                                      time); the sweep retries once analysis
                                      lands, idempotently

Architecture:
  - Polls Redis feed for new articles every POLL_INTERVAL seconds
  - Waits for analysis to complete (all 5 fields populated)
  - Determines which characters are on shift per schedule
  - Calls Ollama with character instruction + full dossier
  - Posts comment to Redis under character name
"""

import os
import sys
import time
import json
import random
import logging
import hashlib
import yaml
import redis
from datetime import datetime, timezone
from dotenv import load_dotenv

import requests

import ollama_client  # transport-layer primary/fallback host failover (cloud models only here)
from domain_registry import domain_matches, matching_domains  # domain predicates (domains.yaml)
from escalation import resolve_character_model, record_cloud_call
from ollama_utils import is_cloud_reachable

# ── env ────────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── site config (schema v2) ────────────────────────────────────────────────────
# Per-site tunables come from the stack-root cfg; committed cfg values are
# canonical. Fails loud if the cfg is missing or incomplete.
from site_config import load_site_config
site = load_site_config()
_pipeline = site["pipeline"]

REDIS_URL        = os.environ['REDIS_URL']
OLLAMA_MODEL     = site["models"]["character"]
ARTICLE_BASE_URL = site.base_url

# Shed-and-yield (2026-07-12): council LOCAL generation runs on the cfg's
# council_url (the Z230's own Ollama) so the M1 belongs to the analyzers.
# Cloud models stay pinned to the M1 via ollama_client (cloud creds live only
# there). Rollback to the M1 is now a cfg edit: [inference].council_url.
COUNCIL_OLLAMA_HOST    = site.council_url
COUNCIL_OLLAMA_TIMEOUT = int(os.getenv("COUNCIL_OLLAMA_TIMEOUT", "120"))  # 24s typical + serialized-queue margin
COUNCIL_MAX_LOAD       = _pipeline["council_load_gate"]  # 1-min loadavg gate — spare-cycles host

POLL_INTERVAL        = _pipeline["character_feed_poll_s"]
ANALYSIS_WAIT        = _pipeline["character_analysis_wait_s"]
ANALYSIS_CHECK_EVERY = _pipeline["character_analysis_poll_s"]
ENABLED_KEY          = "characters:enabled"   # generic — isolated by unique Redis DB
RETRY_BACKOFF        = _pipeline["character_retry_backoff_s"]
RETRY_MAX_AGE        = _pipeline["character_giveup_days"] * 24 * 3600
SWEEP_BATCH          = 3              # skipped retries per character per cycle
MAX_GENERATION_ATTEMPTS = _pipeline["character_max_attempts"]
                                      # real generation failures before give-up;
                                      # quota/429 failures do NOT consume attempts

CHARACTERS_YAML = os.path.join(os.path.dirname(__file__), "..", "characters.yaml")

# ── logging ────────────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [character_builder] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "character_builder.log")),
    ],
)
log = logging.getLogger("character_builder")

# ── Redis ──────────────────────────────────────────────────────────────────────
r = redis.from_url(REDIS_URL, decode_responses=True)
# Fail loud if the .env Redis URL disagrees with the cfg's DB — pointing one
# site's council at a sibling's DB is the failure the cfg exists to prevent.
_env_db = r.connection_pool.connection_kwargs.get("db", 0)
if _env_db != site.redis_db:
    raise SystemExit(
        f"REDIS_URL points at DB {_env_db} but {site.path} says redis_db = "
        f"{site.redis_db} — refusing to start"
    )

# ── Config ─────────────────────────────────────────────────────────────────────
def load_characters() -> dict:
    with open(CHARACTERS_YAML) as f:
        return yaml.safe_load(f)

# ── Analysis completion check ──────────────────────────────────────────────────
REQUIRED_FIELDS = ["red_team_analysis", "blue_team_analysis", "purple_team_analysis", "sentinel_analysis"]

def is_analysis_complete(article_id: str) -> bool:
    """Return True if all analysis fields are populated."""
    try:
        pipe = r.pipeline()
        for field in REQUIRED_FIELDS:
            pipe.hget(f"article:{article_id}", field)
        values = pipe.execute()
        return all(v and len(v) > 20 for v in values)
    except Exception:
        return False

def wait_for_analysis(article_id: str) -> bool:
    """Wait up to ANALYSIS_WAIT seconds for analysis to complete."""
    deadline = time.time() + ANALYSIS_WAIT
    while time.time() < deadline:
        if is_analysis_complete(article_id):
            return True
        time.sleep(ANALYSIS_CHECK_EVERY)
    return False

# ── Dossier builder ────────────────────────────────────────────────────────────
def build_dossier_text(article_id: str) -> str:
    """Assemble the full dossier for a character to read."""
    try:
        article = r.hgetall(f"article:{article_id}")
        if not article:
            return ""

        # Get existing comments including Counter-Analyst
        raw_comments = r.lrange(f"comments:{article_id}", 0, -1)
        comments = []
        for raw in raw_comments:
            try:
                c = json.loads(raw)
                comments.append(f"[{c.get('author', 'Unknown')}]: {c.get('body', '')}")
            except Exception:
                continue

        parts = [
            f"ARTICLE TITLE: {article.get('title', '')}",
            f"\nARTICLE TEXT:\n{article.get('original_text', '')[:2000]}",
        ]

        if article.get("red_team_analysis"):
            parts.append(f"\nRED TEAM (facts):\n{article['red_team_analysis'][:800]}")

        if article.get("blue_team_analysis"):
            parts.append(f"\nBLUE TEAM (summary):\n{article['blue_team_analysis'][:800]}")

        if article.get("purple_team_analysis"):
            parts.append(f"\nPURPLE TEAM (analysis):\n{article['purple_team_analysis'][:1200]}")

        if article.get("sentinel_analysis"):
            try:
                sentinel = json.loads(article["sentinel_analysis"])
                parts.append(f"\nSENTINEL VERDICT: {sentinel.get('assessment', '')} "
                             f"(confidence: {sentinel.get('synthetic_confidence', 0):.2f})")
                parts.append(f"Summary: {sentinel.get('summary', '')}")
            except Exception:
                pass

        if comments:
            parts.append(f"\nEXISTING COMMENTS:\n" + "\n".join(comments))

        return "\n".join(parts)

    except Exception as e:
        log.error("Failed to build dossier for %s: %s", article_id, e)
        return ""

# ── Ollama call ────────────────────────────────────────────────────────────────
def _council_payload(model: str, system_prompt: str, prompt: str) -> dict:
    """The ONE place a council generation payload is built.

    think=False is mandatory on every host, not a per-call nicety: thinking
    models silently burn the entire num_predict budget on hidden reasoning and
    return an empty response (the analyzer local-path bug fixed in
    ollama_utils._apply_spec_following_options), and on the CPU-only Z230 a
    thinking pass measured 76s vs 24s without — a host that forgets the flag
    runs 3× slower. Add future knobs here so every host inherits them.
    """
    return {
        "model":  model,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "think":  False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1024,
            "num_ctx":     8192,
        },
    }


def call_ollama(system_prompt: str, dossier: str, model: str | None = None) -> str | None:
    """Call Ollama with character instruction + dossier.

    Returns (comment_text | None, quota_blocked). quota_blocked marks a 429 —
    callers must not count those failures toward the give-up limit.

    When `model` is None, the global OLLAMA_MODEL is used (legacy behavior).
    Per-character overrides come in via characters.yaml `model:` field
    (e.g. gpt-oss:20b-cloud), resolved through the council gate first.

    Host routing: cloud models go through ollama_client (pinned to the M1 —
    cloud creds live only there). Local models go to COUNCIL_OLLAMA_HOST (the
    Z230) with deliberately NO failover to the M1 — the M1's e2b is no longer
    the council's landing zone; if the Z230 is down the comment is skipped and
    the env default rolls the council back to the M1 wholesale.
    """
    actual_model = model or OLLAMA_MODEL
    log.info("Calling Ollama model=%s for character", actual_model)
    prompt = f"{dossier}\n\n---\n\nBased on the above, write your comment now."
    payload = _council_payload(actual_model, system_prompt, prompt)
    try:
        if actual_model.strip().lower().endswith("-cloud"):
            resp = ollama_client.post("/api/generate", json=payload, read_timeout=180)
        else:
            resp = requests.post(
                f"{COUNCIL_OLLAMA_HOST.rstrip('/')}/api/generate",
                json=payload,
                timeout=(3, COUNCIL_OLLAMA_TIMEOUT),
            )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        return (text if len(text) > 20 else None), False
    except requests.exceptions.HTTPError as e:
        if getattr(e.response, "status_code", None) == 429:
            # Quota exhaustion is the environment's fault, not the article's.
            log.warning("Ollama quota/429 (model=%s): %s", actual_model, e)
            return None, True
        log.error("Ollama call failed (model=%s): %s", actual_model, e)
        return None, False
    except Exception as e:
        log.error("Ollama call failed (model=%s): %s", actual_model, e)
        return None, False

# ── Comment posting ────────────────────────────────────────────────────────────
def post_comment(article_id: str, author: str, body: str) -> bool:
    """Post character comment to Redis comment store.
    Matches Counter-Analyst format exactly:
      - comment:{id} hash with fields: id, author, text, article_id, parent_id, timestamp
      - comments:{article_id} list stores UUID string only (not full JSON)
    """
    try:
        import uuid
        comment_id = str(uuid.uuid4())

        mapping = {
            "id":         comment_id,
            "author":     author,
            "text":       body,
            "article_id": article_id,
            "parent_id":  "",
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        }

        pipe = r.pipeline()
        pipe.hset(f"comment:{comment_id}", mapping=mapping)
        pipe.rpush(f"comments:{article_id}", comment_id)
        pipe.execute()
        return True
    except Exception as e:
        log.error("Failed to post comment for %s: %s", article_id, e)
        return False

# ── Article state transitions ──────────────────────────────────────────────────
# pending → posted   comment landed, or the article is a deliberate drop
# pending → skipped  retryable failure (analysis missing, model down, post failed)

def mark_posted(handle: str, article_id: str):
    pipe = r.pipeline()
    pipe.sadd(f"characters:posted:{handle}", article_id)
    pipe.srem(f"characters:pending:{handle}", article_id)
    pipe.zrem(f"characters:skipped:{handle}", article_id)
    pipe.hdel(f"characters:skip_attempts:{handle}", article_id)
    pipe.execute()

def mark_skipped(handle: str, article_id: str):
    pipe = r.pipeline()
    pipe.zadd(f"characters:skipped:{handle}", {article_id: time.time()})
    pipe.srem(f"characters:pending:{handle}", article_id)
    pipe.execute()

def has_comment_by(article_id: str, author: str) -> bool:
    """Retry idempotency guard: a crash between post_comment and mark_posted
    must not produce a second comment on retry."""
    try:
        for entry in r.lrange(f"comments:{article_id}", 0, -1):
            author_name = r.hget(f"comment:{entry}", "author")
            if author_name is None:
                # Legacy entries stored full JSON in the list instead of a UUID
                try:
                    author_name = json.loads(entry).get("author")
                except Exception:
                    continue
            if author_name == author:
                return True
    except Exception as e:
        log.error("Comment idempotency check failed for %s: %s", article_id, e)
    return False

# ── Topic triggers ─────────────────────────────────────────────────────────────
def should_character_speak(character: dict, article_data: dict) -> bool:
    """Return True if character has no triggers (always speaks when on shift),
    or if any trigger matches the article."""
    triggers = character.get("triggers")
    if not triggers:
        return True  # No triggers = always eligible

    # Directive match (exact, case-sensitive — directives are canonical strings)
    article_directive = (article_data.get("directive") or "").strip()
    trigger_directives = triggers.get("directives") or []
    if trigger_directives and article_directive in trigger_directives:
        return True

    # Domain match — precision predicate from the shared domain registry
    # (domains.yaml, the SAME _passes_selector courses use), replacing the old
    # coarse substring match against the 5-value article.category.
    trigger_domains = triggers.get("domains") or []
    for d in trigger_domains:
        if domain_matches(d, article_data):
            return True

    # Cross-domain match — fire when the article sits at the intersection of
    # >= N distinct registry domains. This is the synthesizer's lane: a story no
    # single specialist owns cleanly (finance meets ethics, sports meets economics).
    # Reuses the registry predicates — just counts distinct matches. Threshold is
    # a tunable field (triggers.cross_domain: N), default 2.
    threshold = triggers.get("cross_domain")
    if threshold:
        if len(matching_domains(article_data)) >= int(threshold):
            return True

    return False


# ── Shift logic ────────────────────────────────────────────────────────────────
def get_active_characters(cfg: dict) -> list[str]:
    """Return list of character handles that should post on this article."""
    schedule   = cfg.get("schedule", {})
    characters = cfg.get("characters", {})
    active     = []

    # Always-on characters
    for handle in schedule.get("always", []):
        if handle in characters:
            active.append(handle)

    # Random characters — pick based on weight
    weights = schedule.get("random_weight", {})
    for handle in schedule.get("random", []):
        if handle not in characters:
            continue
        weight = weights.get(handle, 0.5)
        if random.random() < weight:
            active.append(handle)

    return active

# ── Seed ───────────────────────────────────────────────────────────────────────
def seed_posted_sets(cfg: dict):
    """Mark all existing articles as already posted for each character."""
    try:
        article_ids = r.zrange('feed', 0, -1)
        if not article_ids:
            return
        characters = cfg.get("characters", {})
        for handle in characters:
            posted_key = f"characters:posted:{handle}"
            pipe = r.pipeline()
            for article_id in article_ids:
                pipe.sadd(posted_key, article_id)
            pipe.execute()
        log.info("Seeded posted sets for %d characters, %d articles",
                 len(characters), len(article_ids))
    except Exception as e:
        log.error("Seed failed: %s", e)

def recover_pending(cfg: dict):
    """Crash recovery: anything still pending at startup was in flight when the
    daemon died. Park it in skipped so the sweep retries it (idempotently — the
    comment may or may not have landed). Must run BEFORE seed_posted_sets,
    which would otherwise bury these as posted without a comment."""
    try:
        for handle in cfg.get("characters", {}):
            leftovers = r.smembers(f"characters:pending:{handle}")
            for article_id in leftovers:
                mark_skipped(handle, article_id)
            if leftovers:
                log.warning("Recovered %d in-flight articles for %s into skipped",
                            len(leftovers), handle)
    except Exception as e:
        log.error("Pending recovery failed: %s", e)

# ── Per-article processing ─────────────────────────────────────────────────────
def process_article(handle: str, character: dict, article_id: str) -> None:
    """Run one character over one article, ending in exactly one terminal
    state: posted (comment landed or deliberate drop) or skipped (retryable)."""
    # Topic-trigger gate — directive/category fields are set by
    # scribe at publish time, so they're available without
    # waiting on analysis. Skip off-topic articles cheaply.
    article_data = r.hgetall(f"article:{article_id}")
    if not should_character_speak(character, article_data):
        log.info("Character %s skipping %s — triggers do not match",
                 handle, article_id)
        mark_posted(handle, article_id)
        return

    # Wait for full analysis if character is eager
    if character.get("eager", True):
        if not wait_for_analysis(article_id):
            log.warning("Analysis incomplete for %s after %ds — parking %s for retry",
                        article_id, ANALYSIS_WAIT, handle)
            mark_skipped(handle, article_id)
            return

    if has_comment_by(article_id, character["name"]):
        log.info("Character %s already commented on %s — marking posted",
                 handle, article_id)
        mark_posted(handle, article_id)
        return

    dossier = build_dossier_text(article_id)
    if not dossier:
        log.warning("Empty dossier for %s — parking for retry", article_id)
        mark_skipped(handle, article_id)
        return

    # Council gate — cloud characters downgrade to local unless
    # the article's escalation_score meets the council threshold
    # AND the weekly cloud cap has capacity. Council still runs
    # locally; only the voice weakens on non-escalated articles.
    resolved_model = resolve_character_model(
        character,
        {'id': article_id},
        r,
    )
    if resolved_model.endswith('-cloud'):
        # Reachability BEFORE record — an unreachable cloud
        # host must never increment the weekly cap counter.
        if is_cloud_reachable():
            record_cloud_call(r)
        else:
            # INFO, not WARNING: a closed cloud valve is a
            # normal degraded state (council lands on the Z230
            # local tier), not an actionable failure.
            log.info("Council gate: cloud host unreachable — "
                     "downgrading %s to local", resolved_model)
            resolved_model = OLLAMA_MODEL
    if resolved_model != character.get("model"):
        log.info("Council gate: %s → %s for article %s",
                 character.get("model"), resolved_model, article_id)
    comment_text, quota_blocked = call_ollama(
        character["instruction"],
        dossier,
        model=resolved_model,
    )
    if not comment_text:
        if quota_blocked:
            # Park without consuming an attempt — quota failures don't count.
            log.warning("Generation quota-blocked for %s by %s — parking for retry",
                        article_id, handle)
            mark_skipped(handle, article_id)
            return
        attempts = r.hincrby(f"characters:skip_attempts:{handle}", article_id, 1)
        if attempts >= MAX_GENERATION_ATTEMPTS:
            log.error("Giving up on %s for %s after %d real generation attempts "
                      "— marking posted", article_id, handle, attempts)
            mark_posted(handle, article_id)
        else:
            log.error("No comment generated for %s by %s (attempt %d/%d) — "
                      "parking for retry", article_id, handle, attempts,
                      MAX_GENERATION_ATTEMPTS)
            mark_skipped(handle, article_id)
        return

    if post_comment(article_id, character["name"], comment_text):
        log.info("✅ %s commented on %s", character["name"], article_id)
        mark_posted(handle, article_id)
    else:
        log.error("Failed to post comment by %s on %s — parking for retry",
                  handle, article_id)
        mark_skipped(handle, article_id)

# ── Retry sweep ────────────────────────────────────────────────────────────────
def sweep_skipped(cfg: dict):
    """Second chance for skipped articles. Each cycle, take the oldest few per
    character; retry when the backoff has elapsed and analysis has landed; drop
    for good past RETRY_MAX_AGE (analysis is never coming or the article is
    gone). mark_skipped stamps the current time, so a failed retry re-arms its
    own backoff."""
    now = time.time()
    for handle, character in cfg.get("characters", {}).items():
        skipped_key = f"characters:skipped:{handle}"
        due = r.zrangebyscore(skipped_key, 0, now - RETRY_BACKOFF,
                              start=0, num=SWEEP_BATCH, withscores=True)
        for article_id, ts in due:
            if now - ts > RETRY_MAX_AGE:
                log.warning("Giving up on %s for %s after %d days in skipped",
                            article_id, handle, RETRY_MAX_AGE // 86400)
                mark_posted(handle, article_id)
                continue
            if not is_analysis_complete(article_id):
                continue  # keeps its original score; ages out at RETRY_MAX_AGE
            log.info("Retry sweep: %s retrying %s", handle, article_id)
            process_article(handle, character, article_id)

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    # Cross-site isolation validation at startup (spec: run in CI and at
    # service startup) — refuse to run against colliding site cfgs.
    import validate_sites
    _cfg_errors = validate_sites.check(
        validate_sites.discover(os.environ.get("SITES_ROOT", "/home/www")))
    if _cfg_errors:
        for _e in _cfg_errors:
            log.critical("site cfg violation: %s", _e)
        raise SystemExit(1)

    log.info("character_builder v1.0 starting [%s]", site.path)

    cfg = load_characters()
    log.info("Loaded %d characters", len(cfg.get("characters", {})))

    recover_pending(cfg)
    seed_posted_sets(cfg)

    while True:
        try:
            # Reload config each cycle — live edits to characters.yaml take effect
            cfg = load_characters()

            if r.get(ENABLED_KEY) != "1":
                time.sleep(POLL_INTERVAL)
                continue

            # The Z230 is a spare-cycles host (two stacks, Redis, Solr, Docker),
            # not a dedicated inference box. Yield to its tenants: skip this
            # poll cycle while the box is busy. DEBUG on purpose — a yielded
            # cycle is the system working, not something to page about.
            load1 = os.getloadavg()[0]
            if load1 >= COUNCIL_MAX_LOAD:
                log.debug("host busy (1m load %.2f >= %.2f) — yielding poll cycle",
                          load1, COUNCIL_MAX_LOAD)
                time.sleep(POLL_INTERVAL)
                continue

            all_ids    = set(r.zrange('feed', 0, -1))
            characters = cfg.get("characters", {})

            # Find articles not yet processed by any active character
            for handle in characters:
                posted_key  = f"characters:posted:{handle}"
                pending_key = f"characters:pending:{handle}"
                skipped_key = f"characters:skipped:{handle}"
                posted_ids  = r.smembers(posted_key)
                pending_ids = r.smembers(pending_key)
                skipped_ids = set(r.zrange(skipped_key, 0, -1))
                new_ids     = all_ids - posted_ids - pending_ids - skipped_ids

                if not new_ids:
                    continue

                active = get_active_characters(cfg)
                if handle not in active:
                    # Mark as posted anyway to avoid backlog buildup
                    pipe = r.pipeline()
                    for article_id in new_ids:
                        pipe.sadd(posted_key, article_id)
                    pipe.execute()
                    continue

                character = characters[handle]

                for article_id in new_ids:
                    # Pending until process_article reaches a terminal state —
                    # a crash here is recovered into skipped at next startup
                    r.sadd(pending_key, article_id)
                    log.info("Character %s processing article %s", handle, article_id)
                    process_article(handle, character, article_id)

            # Second chance for parked articles whose analysis has since landed
            sweep_skipped(cfg)

        except Exception as e:
            log.exception("Outer loop error: %s", e)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
