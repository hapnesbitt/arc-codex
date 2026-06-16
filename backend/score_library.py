#!/usr/bin/env python3
"""
Arc Codex — score_library.py

One-shot Chimera Difficulty scorer for the library:works zset.

For each English-language work:
  1. Read the full body from library:work:<id>:text
  2. Compute Flesch-Kincaid grade, Coleman-Liau index, SMOG, and Dale-Chall
     on the first 30,000 characters (stable readability estimate, bounded
     memory — works like the CIA World Factbook are 9M+ chars).
  3. Synthesize the four grade metrics into the Chimera score (0-100) and
     map to a plain-language reading label, using the SAME formulas as
     main.py's pre_analyze (compute_chimera, chimera_reading_label).
  4. Write back to library:work:<id> hash.

For non-English works:
  Set chimera_score = "" and reading_label = "—" with chimera_skip_reason
  set to "non-english" so the frontend can render appropriately.

Idempotent: a work scored within the last 30 days is skipped (unless
SCORE_LIBRARY_FORCE=1 is set).

Usage:
    cd /home/www/arc_stack/backend && source venv/bin/activate
    python3 score_library.py
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import redis
import textstat
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
SCORING_CHAR_LIMIT      = 30000          # First N chars used for readability
RESCORE_AFTER_SECONDS   = 30 * 24 * 60 * 60
REDIS_PASSWORD          = os.environ['REDIS_PASSWORD']
FORCE_RESCORE           = os.environ.get("SCORE_LIBRARY_FORCE") == "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [score_library] %(levelname)s %(message)s",
)
log = logging.getLogger("score_library")


# ---------------------------------------------------------------------------
# Chimera formulas — copied verbatim from backend/main.py:796-811. Keep in
# sync; main.py is the source of truth for article scoring.
# ---------------------------------------------------------------------------

def compute_chimera(fk_grade: float, coleman_liau: float, smog: float, dale_chall: float) -> int:
    avg_grade = (fk_grade + coleman_liau + smog + dale_chall) / 4.0
    return round(min(avg_grade / 20.0, 1.0) * 100)


def chimera_reading_label(score: int) -> str:
    if score <= 10:  return 'Kindergarten'
    if score <= 20:  return 'Elementary'
    if score <= 30:  return 'Middle School'
    if score <= 40:  return 'High School'
    if score <= 50:  return 'College'
    if score <= 60:  return 'Graduate'
    if score <= 70:  return 'Academic'
    if score <= 80:  return 'Expert'
    if score <= 90:  return 'Specialist'
    return 'Quantum Electrodynamics'


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def get_redis() -> redis.Redis:
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis.from_url(redis_url, decode_responses=True)
    return redis.Redis(decode_responses=True, password=REDIS_PASSWORD)


def is_recently_scored(scored_at: str | None) -> bool:
    if FORCE_RESCORE or not scored_at:
        return False
    try:
        ts = datetime.fromisoformat(scored_at)
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - ts
    return age < timedelta(seconds=RESCORE_AFTER_SECONDS)


# ---------------------------------------------------------------------------
# Per-work scoring
# ---------------------------------------------------------------------------

def score_work(r: redis.Redis, gid: str) -> str:
    """
    Returns one of: 'scored', 'skipped_non_english', 'skipped_recent',
    'failed', 'missing'.
    """
    key = f"library:work:{gid}"
    meta = r.hgetall(key)
    if not meta:
        log.warning("[%s] no hash found", gid)
        return 'missing'

    language = (meta.get('language') or '').strip().lower()
    title    = (meta.get('title') or '').strip()
    scored_at_existing = meta.get('scored_at')

    if is_recently_scored(scored_at_existing):
        log.info("[%s] %s — fresh score (%s), skipping", gid, title[:48], scored_at_existing)
        return 'skipped_recent'

    now_iso = datetime.now(timezone.utc).isoformat()

    # Non-English works: stamp with skip reason and move on.
    if language != 'en':
        r.hset(key, mapping={
            'chimera_score':        '',
            'reading_label':        '—',
            'fk_grade':             '',
            'coleman_liau':         '',
            'smog':                 '',
            'dale_chall':           '',
            'chimera_skip_reason':  'non-english',
            'scored_at':            now_iso,
        })
        log.info("[%s] %s — non-english (%s), marked", gid, title[:48], language or '?')
        return 'skipped_non_english'

    # English work — score it.
    body = r.get(f"{key}:text") or ""
    if not body.strip():
        log.warning("[%s] %s — empty body, cannot score", gid, title[:48])
        return 'failed'

    try:
        snippet = body[:SCORING_CHAR_LIMIT]
        fk_grade     = float(textstat.flesch_kincaid_grade(snippet))
        coleman_liau = round(float(textstat.coleman_liau_index(snippet)), 2)
        smog         = round(float(textstat.smog_index(snippet)), 2)
        dale_chall   = round(float(textstat.dale_chall_readability_score(snippet)), 2)

        chimera_score = compute_chimera(fk_grade, coleman_liau, smog, dale_chall)
        reading_label = chimera_reading_label(chimera_score)
    except Exception as e:
        log.error("[%s] %s — scoring failed: %s", gid, title[:48], e)
        return 'failed'

    r.hset(key, mapping={
        'chimera_score':       str(chimera_score),
        'reading_label':       reading_label,
        'fk_grade':            f"{fk_grade:.1f}",
        'coleman_liau':        str(coleman_liau),
        'smog':                str(smog),
        'dale_chall':          str(dale_chall),
        'scored_at':           now_iso,
    })
    # Clear any stale skip reason left over from a prior language detection.
    r.hdel(key, 'chimera_skip_reason')

    log.info(
        "[%s] %s — chimera=%d (%s) · fk=%.1f cl=%.1f smog=%.1f dc=%.1f",
        gid, title[:48], chimera_score, reading_label,
        fk_grade, coleman_liau, smog, dale_chall,
    )
    return 'scored'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    r = get_redis()
    try:
        r.ping()
    except redis.RedisError as e:
        log.error("Redis ping failed: %s", e)
        return 1

    ids = r.zrange('library:works', 0, -1)
    if not ids:
        log.warning("library:works zset is empty — run library_fetcher.py first")
        return 0

    log.info("Scoring %d works (char_limit=%d, force=%s)", len(ids), SCORING_CHAR_LIMIT, FORCE_RESCORE)

    counts = {
        'scored':              0,
        'skipped_non_english': 0,
        'skipped_recent':      0,
        'failed':              0,
        'missing':             0,
    }

    for i, gid in enumerate(ids, 1):
        outcome = score_work(r, gid)
        counts[outcome] = counts.get(outcome, 0) + 1
        if i % 25 == 0:
            log.info("Progress: %d/%d", i, len(ids))

    log.info(
        "Done. scored=%d skipped_non_english=%d skipped_recent=%d failed=%d missing=%d",
        counts['scored'],
        counts['skipped_non_english'],
        counts['skipped_recent'],
        counts['failed'],
        counts['missing'],
    )
    return 0 if counts['failed'] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
