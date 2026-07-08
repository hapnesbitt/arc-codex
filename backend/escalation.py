#!/usr/bin/env python3
"""
Arc Codex — cloud escalation gate (Option A-tightened).

Called by analyzer.py after local analysis completes. Decides whether the
article warrants a cloud re-run, based on three OR-combined triggers:

  T1  parser-fail: local didn't produce a complete, well-closed 3/3 R/B/P
      (capability-independent — the model couldn't finish the structure)

  T2  content heuristics: vendor advertorial signals in the article itself
      (vendor-authored, CTA present, product in headline, self-cited
      research, sponsored markers, advertorial-prone source domain)

  T3  local flagged a pattern (rare on gemma4:e2b but kept for completeness)

Escalation never depends on local recognizing manipulation — trigger 2
patches the WizOS blind spot by using article-side signals that don't
require the local model to reason about vendor motivation.

Also owns:
  - Hard weekly cap on cloud calls (arc:cloud_calls:weekly:<isoweek>).
    When cap is hit, cloud_capacity_available() returns False and every
    character/analyzer that would call cloud falls back to local gracefully.
  - Council model resolver: cloud characters downgrade to local unless the
    article's escalation score >= COUNCIL_ESCALATION_SCORE and cap available.
  - Source stats: rolling stats per source, auto-promotes into
    advertorial_prone after >= N articles at >= 60% escalation rate AND
    >= 40% vendor-heuristic trigger rate. Measured, not prejudged.

Config: constants below are read from arc_config.yaml -> escalation: block
when present, otherwise these defaults apply. Kept as module-level constants
so tests can monkey-patch cheaply.
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import yaml
import redis

logger = logging.getLogger(__name__)


# ─── Defaults (overridden by arc_config.yaml -> escalation: block) ────────────

DEFAULT_HEURISTIC_ESCALATION_THRESHOLD = 4     # any two moderate or one strong signal
DEFAULT_NEW_SOURCE_COLD_START_N        = 10    # articles before source stats stabilize
DEFAULT_WEEKLY_CAP                     = 400   # cloud calls per ISO week (hard backstop)
DEFAULT_COUNCIL_ESCALATION_SCORE       = 2     # min score for cloud characters to fire

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'arc_config.yaml')

def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get('escalation', {}) or {}
    except Exception:
        return {}

_cfg = _load_config()

HEURISTIC_ESCALATION_THRESHOLD = int(_cfg.get('heuristic_threshold', DEFAULT_HEURISTIC_ESCALATION_THRESHOLD))
NEW_SOURCE_COLD_START_N        = int(_cfg.get('new_source_cold_start_n', DEFAULT_NEW_SOURCE_COLD_START_N))
WEEKLY_CAP                     = int(_cfg.get('weekly_cap', DEFAULT_WEEKLY_CAP))
COUNCIL_ESCALATION_SCORE       = int(_cfg.get('council_escalation_score', DEFAULT_COUNCIL_ESCALATION_SCORE))


# ─── Trigger 1: parser-fail signal ────────────────────────────────────────────

_PATTERNS_LINE_RE = re.compile(r'Patterns detected:\s*(.+)', re.IGNORECASE)
_TERMINATOR_CHARS = ('.', '?', '!', '"', "'", ')', ']', '}')

def _purple_looks_closed(purple: str) -> bool:
    """A section is 'closed' when it ends with a natural terminator or contains
    the 'Patterns detected:' line (v6.4 convention). Everything else looks
    like the model stopped mid-generation."""
    if not purple:
        return False
    stripped = purple.rstrip()
    if _PATTERNS_LINE_RE.search(stripped):
        return True
    return stripped.endswith(_TERMINATOR_CHARS)


# ─── Trigger 2: content heuristics ────────────────────────────────────────────

_CTA_PATTERNS = [
    re.compile(r'\brequest\s+a\s+demo\b', re.IGNORECASE),
    re.compile(r'\blearn\s+more\s+at\b', re.IGNORECASE),
    re.compile(r'\bcontact\s+sales\b', re.IGNORECASE),
    re.compile(r'\bsign\s+up\s+for\b', re.IGNORECASE),
    re.compile(r'\btry\s+[\w:\-]+\s+for\s+free\b', re.IGNORECASE),
    re.compile(r'\bschedule\s+a\s+demo\b', re.IGNORECASE),
    re.compile(r'\bget\s+started\s+with\b', re.IGNORECASE),
]

# "our research shows / Vendor research reveals" — self-citation pattern
_VENDOR_RESEARCH_RE = re.compile(
    r'\b(?:our|[A-Z]\w+)\s+research\s+(?:shows|found|reveals|reports|indicates|demonstrates|has\s+shown)\b',
    re.IGNORECASE,
)

_SPONSORED_MARKERS = (
    'sponsored by', 'presented by', 'advertorial',
    'paid post', 'promoted post', 'sponsored content',
)

# Product-name candidate: names with camelCase or embedded acronym or digits.
# Matches: SentinelOne, CrowdStrike, FortiGate, MacBook (CamelCase),
#          WizOS, MacOS (CamelCase + trailing acronym),
#          iPhone, iPad, iPhone17 (lowercase-first camelCase),
#          Zone42, Route53 (proper-case + digits).
# Deliberately does NOT match single proper-cased words (Nemotron, Boston) —
# too many false positives on place names and human names.
_PRODUCT_TOKEN_RE = re.compile(
    r'\b(?:[A-Z][a-z]+){2,}(?:\d+)?\b'      # SentinelOne, MacBook
    r'|\b[A-Z][a-z]+[A-Z]{2,}\b'            # WizOS, MacOS
    r'|\b[A-Z][a-z]+\d+\b'                  # Zone42
    r'|\b[a-z][A-Z][a-z]+\d*\b'             # iPhone, iPhone17, eBay
)

@dataclass
class HeuristicResult:
    score: int = 0
    reasons: list = field(default_factory=list)

def _vendor_heuristic_hits(article: dict, source_is_advertorial_prone: bool = False) -> HeuristicResult:
    r = HeuristicResult()
    title = article.get('title') or ''
    body = (article.get('original_text') or '')[:20000]
    body_lower = body.lower()

    # A. Product name repeated ≥3× in body (extracted from title)
    product_repeated = None
    for tok in _PRODUCT_TOKEN_RE.findall(title):
        if len(tok) < 4:
            continue
        count = body_lower.count(tok.lower())
        if count >= 3:
            product_repeated = (tok, count)
            break
    if product_repeated:
        r.score += 2
        r.reasons.append(f"product_repeated:{product_repeated[0]}({product_repeated[1]}x)")

    # B. Product-in-headline (proper-cased token with inner-cap or digits)
    if _PRODUCT_TOKEN_RE.search(title):
        r.score += 2
        r.reasons.append("product_in_headline")

    # C. CTA present
    cta_hits = [p.pattern for p in _CTA_PATTERNS if p.search(body)]
    if cta_hits:
        r.score += 3
        r.reasons.append(f"cta_present({len(cta_hits)})")

    # D. Vendor self-citation
    if _VENDOR_RESEARCH_RE.search(body):
        r.score += 3
        r.reasons.append("vendor_self_research")

    # E. Advertorial-prone source (post-cold-start, auto-promoted)
    if source_is_advertorial_prone:
        r.score += 2
        r.reasons.append("source_advertorial_prone")

    # F. Explicit sponsored marker (very strong — one hit escalates)
    body_head = body[:2000].lower()
    for marker in _SPONSORED_MARKERS:
        if marker in body_head:
            r.score += 5
            r.reasons.append(f"sponsored_marker:{marker}")
            break

    return r


def label_local_analyses(analyses: dict) -> str:
    """Label a local analysis result as 'local_full' or 'local_partial'.
    Full = 3/3 sections present AND purple looks closed. Anything else is
    partial — that's what the frontend surfaces as a transparency badge.
    Cloud runs are never labelled local_* — the caller sets 'cloud' directly.
    """
    section_count = sum(1 for k in ('blue', 'red', 'purple') if analyses.get(k))
    if section_count == 3 and _purple_looks_closed(analyses.get('purple', '')):
        return 'local_full'
    return 'local_partial'


# ─── Trigger 3: local flagged a pattern ───────────────────────────────────────

def _local_flagged_patterns(purple: str) -> bool:
    if not purple:
        return False
    m = _PATTERNS_LINE_RE.search(purple)
    if not m:
        return False
    val = m.group(1).strip().lower()
    if val.startswith('none') or val.startswith('no ') or val.startswith('n/a'):
        return False
    # Look for ARC- code presence anywhere in the citation
    return 'arc-' in val


# ─── Main decision ────────────────────────────────────────────────────────────

@dataclass
class EscalationDecision:
    escalate: bool
    score: int
    reason: str

def decide_escalate(analyses: dict, article: dict, source_stats: Optional[dict] = None) -> EscalationDecision:
    """
    Return an EscalationDecision. `analyses` is the local-produced R/B/P dict.
    `article` is the full article hash from Redis. `source_stats` is the
    optional stats hash for this article's source (or None if not tracked yet).
    """
    reasons = []
    total_score = 0

    # T1 — parser-fail signal
    purple = analyses.get('purple', '') or ''
    section_count = sum(1 for k in ('blue', 'red', 'purple') if analyses.get(k))
    if section_count < 3:
        total_score += 3
        reasons.append(f"incomplete_sections({section_count}/3)")
    elif not _purple_looks_closed(purple):
        total_score += 3
        reasons.append("purple_truncated")

    # T2 — content heuristics
    is_prone = bool(source_stats and source_stats.get('is_advertorial_prone'))
    h = _vendor_heuristic_hits(article, source_is_advertorial_prone=is_prone)
    if h.score >= HEURISTIC_ESCALATION_THRESHOLD:
        total_score += h.score
        reasons.extend(h.reasons)

    # T3 — local flagged a pattern
    if _local_flagged_patterns(purple):
        total_score += 2
        reasons.append("local_flagged_pattern")

    return EscalationDecision(
        escalate=total_score > 0,
        score=total_score,
        reason='|'.join(reasons) if reasons else '',
    )


# ─── Weekly cap counter (hard backstop) ───────────────────────────────────────

_WEEKLY_KEY_PREFIX = "arc:cloud_calls:weekly:"

def _weekly_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    iso_year, iso_week, _ = now.isocalendar()
    return f"{_WEEKLY_KEY_PREFIX}{iso_year}-W{iso_week:02d}"

def cloud_capacity_available(r: redis.Redis) -> bool:
    """True while this ISO week's cloud call count is below WEEKLY_CAP."""
    try:
        count = int(r.get(_weekly_key()) or 0)
        return count < WEEKLY_CAP
    except Exception:
        # If Redis is down we err on "available" so nothing pages — the actual
        # cloud call would fail loudly, which is more legible than silently
        # falling to local because we couldn't check.
        return True

def record_cloud_call(r: redis.Redis) -> int:
    """Increment the weekly counter. Returns the new count. Sets a TTL slightly
    past 7 days so the counter self-rolls over.

    Callers must verify the cloud host is reachable BEFORE calling this
    (ollama_utils.is_cloud_reachable) — record-before-HTTP is deliberate for
    the reachable case, but a dead host must never consume cap (2026-07-07).
    """
    try:
        key = _weekly_key()
        count = int(r.incr(key))
        r.expire(key, 8 * 86400)
        # INCR is atomic, so exactly one caller sees the crossing value —
        # the warning fires once per week even with concurrent recorders.
        warn_at = int(WEEKLY_CAP * 0.9)
        if count == warn_at:
            logger.warning(
                f"⚠️  Weekly cloud call counter at 90% of cap ({count}/{WEEKLY_CAP}) "
                f"— escalation degrades to local at {WEEKLY_CAP}"
            )
        return count
    except Exception:
        return -1

def weekly_cloud_call_count(r: redis.Redis) -> int:
    try:
        return int(r.get(_weekly_key()) or 0)
    except Exception:
        return 0


# ─── Character-model resolver (council gate) ──────────────────────────────────

def resolve_character_model(char: dict, article: dict, r: redis.Redis,
                            default_local: str = 'gemma4:e2b') -> str:
    """
    A character's declared `model:` field is the CEILING — it can only be
    downgraded to local, never upgraded to cloud.

    Rule: cloud characters (model ends in '-cloud') fire on cloud only when
      (a) the article was escalated by decide_escalate with
          score >= COUNCIL_ESCALATION_SCORE, AND
      (b) the weekly cloud cap has capacity.
    Otherwise, downgrade to the local model. Council still runs — the voice
    is just weaker on those articles. Still-annotate > not-annotate.
    """
    declared = char.get('model') or default_local
    if not declared.endswith('-cloud'):
        return declared  # local already

    aid = article.get('id', '')
    if not aid:
        return default_local
    try:
        escalation_score = int(r.hget(f"article:{aid}", 'escalation_score') or 0)
    except Exception:
        escalation_score = 0

    if escalation_score >= COUNCIL_ESCALATION_SCORE and cloud_capacity_available(r):
        return declared
    return default_local


# ─── Source stats (rolling, auto-promotion to advertorial_prone) ──────────────

def _source_slug(article: dict) -> str:
    """Normalize a source into a stable slug for the source_stats hash."""
    su = article.get('sourceUrl') or ''
    if su:
        try:
            netloc = urlparse(su).netloc.lower()
            netloc = re.sub(r'^www\.', '', netloc)
            if netloc:
                return netloc
        except Exception:
            pass
    name = (article.get('source_name') or 'unknown').strip().lower()
    return re.sub(r'\s+', '_', name) or 'unknown'

def _source_stats_key(article: dict) -> str:
    return f"arc:source_stats:{_source_slug(article)}"

def get_source_stats(r: redis.Redis, article: dict) -> dict:
    """Return the raw stats hash + a resolved is_advertorial_prone bool."""
    try:
        stats = r.hgetall(_source_stats_key(article)) or {}
    except Exception:
        stats = {}
    stats['is_advertorial_prone'] = stats.get('is_advertorial_prone') == '1'
    return stats

def update_source_stats(r: redis.Redis, article: dict, escalated: bool, reasons: str) -> None:
    """
    Increment rolling counters and possibly auto-promote / demote the source's
    advertorial_prone flag. Called from analyzer after each publish.
    """
    key = _source_stats_key(article)
    reasons_text = reasons or ''
    triggered_heuristic = any(
        s in reasons_text for s in
        ('product_', 'cta_present', 'vendor_self_research', 'sponsored_marker', 'source_advertorial_prone')
    )
    try:
        pipe = r.pipeline()
        pipe.hincrby(key, 'total_articles', 1)
        if escalated:
            pipe.hincrby(key, 'escalated_articles', 1)
        if triggered_heuristic:
            pipe.hincrby(key, 'vendor_heuristic_articles', 1)
        pipe.expire(key, 30 * 86400)
        pipe.execute()

        total = int(r.hget(key, 'total_articles') or 0)
        if total < NEW_SOURCE_COLD_START_N:
            return  # cold start — stats not yet stable

        esc_rate = int(r.hget(key, 'escalated_articles') or 0) / total
        vh_rate  = int(r.hget(key, 'vendor_heuristic_articles') or 0) / total

        # Auto-promote: high overall escalation AND majority from vendor heuristics
        # (so a source that only fails on parser truncation doesn't get flagged)
        if esc_rate >= 0.6 and vh_rate >= 0.4:
            r.hset(key, 'is_advertorial_prone', '1')
        else:
            r.hset(key, 'is_advertorial_prone', '0')
    except Exception:
        # Stats are best-effort. Never let stats bookkeeping break analysis.
        pass
