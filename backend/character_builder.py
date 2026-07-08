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
Posted set: characters:posted:{character_handle} (SET of article IDs)

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

import ollama_client  # transport-layer primary/fallback host failover (owns requests)
from domain_registry import domain_matches, matching_domains  # domain predicates (domains.yaml)
from escalation import resolve_character_model, record_cloud_call
from ollama_utils import is_cloud_reachable

# ── env ────────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

REDIS_URL        = os.environ['REDIS_URL']
OLLAMA_HOST      = os.getenv("OLLAMA_HOST", "http://192.168.1.185:11434")
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "gemma3:4b")
ARTICLE_BASE_URL = os.getenv("NEXT_PUBLIC_BACKEND_URL", "https://arc-codex.com")

POLL_INTERVAL        = 20    # seconds between feed scans
ANALYSIS_WAIT        = 120   # seconds to wait for full analysis before giving up
ANALYSIS_CHECK_EVERY = 10    # seconds between analysis completion checks
ENABLED_KEY          = "characters:enabled"

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
def call_ollama(system_prompt: str, dossier: str, model: str | None = None) -> str | None:
    """Call Ollama with character instruction + dossier. Returns comment text.

    When `model` is None, the global OLLAMA_MODEL is used (legacy behavior).
    Per-character overrides come in via characters.yaml `model:` field —
    e.g. devstral-2:123b-cloud for the school librarian and Torchy Blane.
    """
    actual_model = model or OLLAMA_MODEL
    log.info("Calling Ollama model=%s for character", actual_model)
    prompt = f"{dossier}\n\n---\n\nBased on the above, write your comment now."
    try:
        # think=false is critical for gemma4-family models. Without it, thinking
        # models silently burn the entire num_predict budget on hidden reasoning
        # and return an empty response — same root cause as the analyzer local-
        # path bug fixed in ollama_utils._apply_spec_following_options.
        # See that helper's docstring for the full diagnosis.
        resp = ollama_client.post(
            "/api/generate",
            json={
                "model":  actual_model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "think":  False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 1024,
                    "num_ctx":     32768,
                },
            },
            read_timeout=180,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        return text if len(text) > 20 else None
    except Exception as e:
        log.error("Ollama call failed (model=%s): %s", actual_model, e)
        return None

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

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    log.info("character_builder v1.0 starting")

    cfg = load_characters()
    log.info("Loaded %d characters", len(cfg.get("characters", {})))

    seed_posted_sets(cfg)

    while True:
        try:
            # Reload config each cycle — live edits to characters.yaml take effect
            cfg = load_characters()

            if r.get(ENABLED_KEY) != "1":
                time.sleep(POLL_INTERVAL)
                continue

            all_ids    = set(r.zrange('feed', 0, -1))
            characters = cfg.get("characters", {})

            # Find articles not yet processed by any active character
            for handle in characters:
                posted_key  = f"characters:posted:{handle}"
                posted_ids  = r.smembers(posted_key)
                new_ids     = all_ids - posted_ids

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
                    # Mark immediately to prevent double-posting
                    r.sadd(posted_key, article_id)

                    log.info("Character %s processing article %s", handle, article_id)

                    # Topic-trigger gate — directive/category fields are set by
                    # scribe at publish time, so they're available without
                    # waiting on analysis. Skip off-topic articles cheaply.
                    article_data = r.hgetall(f"article:{article_id}")
                    if not should_character_speak(character, article_data):
                        log.info("Character %s skipping %s — triggers do not match",
                                 handle, article_id)
                        # already marked posted above, just continue
                        continue

                    # Wait for full analysis if character is eager
                    if character.get("eager", True):
                        if not wait_for_analysis(article_id):
                            log.warning("Analysis incomplete for %s after %ds — skipping %s",
                                        article_id, ANALYSIS_WAIT, handle)
                            continue

                    dossier = build_dossier_text(article_id)
                    if not dossier:
                        log.warning("Empty dossier for %s — skipping", article_id)
                        continue

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
                            log.warning("Council gate: cloud host unreachable — "
                                        "downgrading %s to local", resolved_model)
                            resolved_model = OLLAMA_MODEL
                    if resolved_model != character.get("model"):
                        log.info("Council gate: %s → %s for article %s",
                                 character.get("model"), resolved_model, article_id)
                    comment_text = call_ollama(
                        character["instruction"],
                        dossier,
                        model=resolved_model,
                    )
                    if not comment_text:
                        log.error("No comment generated for %s by %s", article_id, handle)
                        continue

                    success = post_comment(article_id, character["name"], comment_text)
                    if success:
                        log.info("✅ %s commented on %s", character["name"], article_id)
                    else:
                        log.error("Failed to post comment by %s on %s", handle, article_id)

        except Exception as e:
            log.exception("Outer loop error: %s", e)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
