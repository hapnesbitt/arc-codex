#!/usr/bin/env python3
"""
corpus_exporter.py — Arc Codex Corpus Prometheus Exporter v2.0
Scrapes Redis for corpus health metrics and exposes them at :9101/metrics.
Refreshes once per hour (configurable via EXPORTER_INTERVAL_SEC).

v2.0 additions:
  NLP metrics (from pre_analyze v3.0 nlp_* fields):
    arc_nlp_sentiment_avg           — avg VADER compound across corpus
    arc_nlp_vader_pos_avg           — avg VADER positive
    arc_nlp_vader_neg_avg           — avg VADER negative
    arc_nlp_vader_neu_avg           — avg VADER neutral
    arc_nlp_subjectivity_avg        — avg TextBlob subjectivity
    arc_nlp_word_count_avg          — avg word count per article
    arc_nlp_sentence_count_avg      — avg sentence count
    arc_nlp_avg_sentence_len_avg    — avg sentence length (words)
    arc_nlp_fk_grade_avg            — avg Flesch-Kincaid grade
    arc_nlp_coleman_liau_avg        — avg Coleman-Liau index
    arc_nlp_smog_avg                — avg SMOG index
    arc_nlp_dale_chall_avg          — avg Dale-Chall score
    arc_nlp_reading_level_total     — article count by reading level
    arc_nlp_entity_total            — entity count by type (PERSON/ORG/GPE/LOC/DATE/MONEY/EVENT)
    arc_nlp_coverage_pct            — % of articles with nlp_ fields present

  Pipeline health (from arc:stats:* Redis counters written by scribe):
    arc_fetch_total{domain,tier}    — fetch outcomes by domain + tier
    arc_fetch_latency_avg_ms{domain}— avg fetch latency per domain
    arc_quality_reject_total{reason}— quality gate rejections by reason
    arc_rss_total{outcome}          — RSS feed parse outcomes (ok/bozo/candidates)
    arc_publish_total{outcome}      — publish outcomes (ok/failed/duplicate)
    arc_priority_total{origin}      — priority queue items by origin

  Existing metrics (unchanged from v1.0):
    arc_corpus_total
    arc_corpus_scored_total
    arc_chimera_score_avg
    arc_chimera_score_low_total
    arc_chimera_score_high_total
    arc_chimera_bucket
    arc_sentinel_total{verdict}
    arc_directive_total{directive}
    arc_source_total{domain}
    arc_language_total{lang}
    arc_completeness{field}
    arc_arc_pattern_total{code,name}
    arc_synthetic_pct
    arc_exporter_last_scrape_timestamp
    arc_exporter_scrape_duration_sec

Usage:
    cd /home/www/arc_stack/backend
    source venv/bin/activate
    python3 corpus_exporter.py
"""

import os
import json
import time
import threading
import logging
from collections import Counter
from datetime import datetime, timezone

import redis
import urllib.parse
from dotenv import load_dotenv
from prometheus_client import (
    start_http_server, Gauge,
    REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR
)

try:
    REGISTRY.unregister(PROCESS_COLLECTOR)
    REGISTRY.unregister(PLATFORM_COLLECTOR)
except Exception:
    pass

load_dotenv()

# --- Config ---
REDIS_HOST     = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT     = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB       = int(os.getenv("REDIS_DB", 0))
EXPORTER_PORT  = int(os.getenv("EXPORTER_PORT", 9101))
INTERVAL_SEC   = int(os.getenv("EXPORTER_INTERVAL_SEC", 3600))
TOP_SOURCES    = int(os.getenv("EXPORTER_TOP_SOURCES", 30))

LOG_FORMAT = "%(asctime)s - [CORPUS_EXPORTER v2.0] - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

# All 48 A.R.C. patterns
ARC_PATTERNS = {
    "ARC-0001": "Sirens_Trap",
    "ARC-0002": "Deniability_Decoy",
    "ARC-0003": "Wolfs_Gambit",
    "ARC-0004": "Configuration_Drift",
    "ARC-0005": "Appeal_to_Ridicule",
    "ARC-0006": "Appeal_to_Spite",
    "ARC-0007": "Appeal_to_Force",
    "ARC-0008": "Ad_Hominem",
    "ARC-0009": "Straw_Man",
    "ARC-0010": "False_Dilemma",
    "ARC-0011": "Slippery_Slope",
    "ARC-0012": "Appeal_to_Nature",
    "ARC-0013": "Appeal_to_Tradition",
    "ARC-0014": "Appeal_to_Novelty",
    "ARC-0015": "Bandwagon",
    "ARC-0016": "Appeal_to_Authority",
    "ARC-0017": "Hasty_Generalization",
    "ARC-0018": "Anecdotal_Evidence",
    "ARC-0019": "Texas_Sharpshooter",
    "ARC-0020": "Post_Hoc",
    "ARC-0021": "Correlation_Causation",
    "ARC-0022": "False_Analogy",
    "ARC-0023": "Equivocation",
    "ARC-0024": "Ambiguity",
    "ARC-0025": "Composition_Fallacy",
    "ARC-0026": "Division_Fallacy",
    "ARC-0027": "Begging_the_Question",
    "ARC-0028": "Circular_Reasoning",
    "ARC-0029": "Red_Herring",
    "ARC-0030": "Irrelevant_Conclusion",
    "ARC-0031": "Moving_the_Goalposts",
    "ARC-0032": "No_True_Scotsman",
    "ARC-0033": "Tu_Quoque",
    "ARC-0034": "Two_Wrongs",
    "ARC-0035": "Appeal_to_Pity",
    "ARC-0036": "Appeal_to_Flattery",
    "ARC-0037": "Loaded_Question",
    "ARC-0038": "Burden_of_Proof_Shift",
    "ARC-0039": "Argument_from_Ignorance",
    "ARC-0040": "Black_or_White",
    "ARC-0041": "Middle_Ground_Fallacy",
    "ARC-0042": "Nirvana_Fallacy",
    "ARC-0043": "Motte_and_Bailey",
    "ARC-0044": "Gish_Gallop",
    "ARC-0045": "Sealioning",
    "ARC-0046": "Kafka_Trap",
    "ARC-0047": "Sanewashing",
    "ARC-0048": "Kalisti_Principle",
}

TRACKED_FIELDS = [
    'title', 'sourceUrl', 'red_team_analysis', 'blue_team_analysis',
    'purple_team_analysis', 'sentinel_verdict', 'source_lang', 'chimera_score',
]

NLP_FIELDS = [
    'nlp_chimera_score', 'nlp_sentiment', 'nlp_vader_pos', 'nlp_vader_neg',
    'nlp_vader_neu', 'nlp_subjectivity', 'nlp_objectivity', 'nlp_word_count',
    'nlp_sentence_count', 'nlp_avg_sentence_len', 'nlp_syllable_count',
    'nlp_noun_chunk_count', 'nlp_fk_grade', 'nlp_coleman_liau', 'nlp_smog',
    'nlp_dale_chall', 'nlp_entity_person', 'nlp_entity_org', 'nlp_entity_gpe',
    'nlp_entity_loc', 'nlp_entity_date', 'nlp_entity_money', 'nlp_entity_event',
    'nlp_reading_level', 'nlp_top_lemmas',
]

READING_LEVELS = ['elementary', 'middle_school', 'high_school', 'college', 'graduate', 'technical']
NLP_ENTITY_TYPES = ['person', 'org', 'gpe', 'loc', 'date', 'money', 'event']

# Stats keys written by scribe.py
STATS_FETCH          = "arc:stats:fetch"
STATS_QUALITY        = "arc:stats:quality"
STATS_RSS            = "arc:stats:rss"
STATS_PUBLISH        = "arc:stats:publish"
STATS_PRIORITY       = "arc:stats:priority"
STATS_SOURCE_LATENCY = "arc:stats:source_latency"

# =============================================================================
# Prometheus metrics — v1.0 (unchanged)
# =============================================================================
g_total           = Gauge('arc_corpus_total',            'Total articles in corpus')
g_scored          = Gauge('arc_corpus_scored_total',     'Articles with chimera_score')
g_chimera_avg     = Gauge('arc_chimera_score_avg',       'Average chimera score across corpus')
g_chimera_low     = Gauge('arc_chimera_score_low_total', 'Articles with chimera_score < 0.3 (divisive)')
g_chimera_high    = Gauge('arc_chimera_score_high_total','Articles with chimera_score >= 0.7 (objective)')
g_synthetic_pct   = Gauge('arc_synthetic_pct',           'Percentage of articles flagged SYNTHETIC by Sentinel')
g_last_scrape     = Gauge('arc_exporter_last_scrape_timestamp', 'Unix timestamp of last successful scrape')
g_scrape_duration = Gauge('arc_exporter_scrape_duration_sec',   'Duration of last corpus scrape in seconds')
g_chimera_bucket  = Gauge('arc_chimera_bucket',   'Chimera score histogram bucket count', ['bucket'])
g_sentinel        = Gauge('arc_sentinel_total',   'Article count by Sentinel verdict',    ['verdict'])
g_directive       = Gauge('arc_directive_total',  'Article count by directive/category',  ['directive'])
g_source          = Gauge('arc_source_total',     'Article count by source domain',       ['domain'])
g_language        = Gauge('arc_language_total',   'Article count by source language',     ['lang'])
g_completeness    = Gauge('arc_completeness',     'Percentage of articles with field present (0-100)', ['field'])
g_arc_pattern     = Gauge('arc_arc_pattern_total','ARC pattern detection count',          ['code', 'name'])

# =============================================================================
# Prometheus metrics — v2.0 NLP
# =============================================================================
g_nlp_sentiment_avg      = Gauge('arc_nlp_sentiment_avg',        'Avg VADER compound sentiment across corpus')
g_nlp_vader_pos_avg      = Gauge('arc_nlp_vader_pos_avg',        'Avg VADER positive score')
g_nlp_vader_neg_avg      = Gauge('arc_nlp_vader_neg_avg',        'Avg VADER negative score')
g_nlp_vader_neu_avg      = Gauge('arc_nlp_vader_neu_avg',        'Avg VADER neutral score')
g_nlp_subjectivity_avg   = Gauge('arc_nlp_subjectivity_avg',     'Avg TextBlob subjectivity (0=objective, 1=subjective)')
g_nlp_word_count_avg     = Gauge('arc_nlp_word_count_avg',       'Avg word count per article')
g_nlp_sentence_count_avg = Gauge('arc_nlp_sentence_count_avg',   'Avg sentence count per article')
g_nlp_sentence_len_avg   = Gauge('arc_nlp_avg_sentence_len_avg', 'Avg sentence length in words')
g_nlp_fk_grade_avg       = Gauge('arc_nlp_fk_grade_avg',         'Avg Flesch-Kincaid grade level')
g_nlp_coleman_liau_avg   = Gauge('arc_nlp_coleman_liau_avg',     'Avg Coleman-Liau readability index')
g_nlp_smog_avg           = Gauge('arc_nlp_smog_avg',             'Avg SMOG readability index')
g_nlp_dale_chall_avg     = Gauge('arc_nlp_dale_chall_avg',       'Avg Dale-Chall readability score')
g_nlp_coverage_pct       = Gauge('arc_nlp_coverage_pct',         '% of articles with NLP fields present')
g_nlp_reading_level      = Gauge('arc_nlp_reading_level_total',  'Article count by reading level', ['level'])
g_nlp_entity             = Gauge('arc_nlp_entity_total',         'Total entity count by NER type across corpus', ['entity_type'])

# =============================================================================
# Prometheus metrics — v2.0 pipeline health
# =============================================================================
g_fetch          = Gauge('arc_fetch_total',           'Fetch outcome count by domain and tier', ['domain', 'tier'])
g_fetch_latency  = Gauge('arc_fetch_latency_avg_ms',  'Avg fetch latency in ms by domain',      ['domain'])
g_quality_reject = Gauge('arc_quality_reject_total',  'Quality gate rejection count by reason',  ['reason'])
g_rss            = Gauge('arc_rss_total',             'RSS feed parse outcome count',            ['outcome'])
g_publish        = Gauge('arc_publish_total',         'Publish pipeline outcome count',          ['outcome'])
g_priority       = Gauge('arc_priority_total',        'Priority queue items processed by origin',['origin'])

# =============================================================================
# Prometheus metrics — v2.1 heartbeats + resource guards (fast loop, 60s)
# =============================================================================
g_scribe_heartbeat     = Gauge('arc_scribe_heartbeat_timestamp',
                               'Unix ts of the scribe heartbeat key (0 = absent/expired)', ['stack'])
g_scribe_heartbeat_age = Gauge('arc_scribe_heartbeat_age_seconds',
                               'Seconds since the scribe heartbeat (-1 = absent/expired)', ['stack'])
g_cloud_calls_weekly   = Gauge('arc_cloud_calls_weekly',
                               "This ISO week's cloud escalation call count (arc:cloud_calls:weekly:*)")
g_redis_used_memory    = Gauge('arc_redis_used_memory_bytes', 'Redis used_memory (shared instance)')
g_redis_maxmemory      = Gauge('arc_redis_maxmemory_bytes',   'Redis maxmemory (0 = uncapped)')
g_redis_memory_ratio   = Gauge('arc_redis_memory_ratio',      'used_memory / maxmemory (0 if uncapped)')


# =============================================================================
# Helpers
# =============================================================================

def _extract_registered_domain(url):
    try:
        host = urllib.parse.urlparse(url).netloc.lower().split(':')[0]
        parts = host.lstrip('www.').split('.')
        return '.'.join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ''

def _get_chimera_score(data):
    score = data.get('chimera_score')
    if score is not None:
        try:
            return float(score)
        except (ValueError, TypeError):
            pass
    try:
        dossier = json.loads(data.get('dossier', '{}'))
        s = dossier.get('chimera_score')
        if s is not None:
            return float(s)
    except Exception:
        pass
    return None

def _get_sentinel_verdict(data):
    verdict = data.get('sentinel_verdict', '')
    if not verdict:
        try:
            sa = json.loads(data.get('sentinel_analysis', '{}'))
            assessment = sa.get('assessment', '')
            if 'HUMAN' in assessment.upper():
                verdict = 'HUMAN'
            elif 'SYNTHETIC' in assessment.upper():
                verdict = 'SYNTHETIC'
            elif assessment:
                verdict = 'UNCERTAIN'
        except Exception:
            pass
    return verdict.upper() or '(NONE)'

def _scan_arc_patterns(text):
    found = []
    text_upper = text.upper()
    for code, name in ARC_PATTERNS.items():
        canonical = name.replace('_', ' ')
        if code in text_upper or canonical.upper() in text_upper:
            found.append(code)
    return found

def _field_present(data, field):
    if field == 'chimera_score':
        return _get_chimera_score(data) is not None
    if field == 'sentinel_verdict':
        return bool(data.get('sentinel_verdict') or data.get('sentinel_analysis'))
    val = data.get(field, '')
    return bool(val and val != '{}')

def _safe_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def _avg(values):
    return round(sum(values) / len(values), 4) if values else 0.0


# =============================================================================
# Pipeline health scrape — reads arc:stats:* counters
# =============================================================================

def scrape_pipeline_health(r):
    """Read scribe-written counters from Redis and publish to Prometheus."""

    # --- Fetch outcomes ---
    fetch_data = r.hgetall(STATS_FETCH) or {}
    # Keys are like "reuters.com:tier1_ok", "reuters.com:calls"
    FETCH_TIERS = ['tier1_ok', 'tier2_ok', 'youtube_ok', 'failed']
    domain_calls = {}
    for raw_key, val in fetch_data.items():
        if ':' not in raw_key:
            continue
        # last segment is the tier or 'calls'
        parts = raw_key.rsplit(':', 1)
        domain, tier = parts[0], parts[1]
        count = int(val or 0)
        if tier in FETCH_TIERS:
            g_fetch.labels(domain=domain, tier=tier).set(count)
        elif tier == 'calls':
            domain_calls[domain] = count

    # --- Fetch latency avg ---
    latency_data = r.hgetall(STATS_SOURCE_LATENCY) or {}
    for domain, cumulative_ms in latency_data.items():
        calls = domain_calls.get(domain, 1)
        avg_ms = round(float(cumulative_ms or 0) / max(calls, 1), 1)
        g_fetch_latency.labels(domain=domain).set(avg_ms)

    # --- Quality gate rejections ---
    quality_data = r.hgetall(STATS_QUALITY) or {}
    for reason, count in quality_data.items():
        g_quality_reject.labels(reason=reason).set(int(count or 0))

    # --- RSS outcomes ---
    rss_data = r.hgetall(STATS_RSS) or {}
    for outcome in ['ok', 'bozo', 'candidates']:
        g_rss.labels(outcome=outcome).set(int(rss_data.get(outcome, 0)))

    # --- Publish outcomes ---
    publish_data = r.hgetall(STATS_PUBLISH) or {}
    for outcome in ['ok', 'failed', 'duplicate']:
        g_publish.labels(outcome=outcome).set(int(publish_data.get(outcome, 0)))

    # --- Priority queue origins ---
    priority_data = r.hgetall(STATS_PRIORITY) or {}
    for origin, count in priority_data.items():
        g_priority.labels(origin=origin).set(int(count or 0))


# =============================================================================
# Main corpus scrape — reads article:* hashes
# =============================================================================

def scrape(r):
    """Full corpus scan. Called once per INTERVAL_SEC in background thread."""
    log.info("Starting corpus scrape v2.0...")
    t0 = time.time()

    total            = 0
    scores           = []
    score_buckets    = Counter()
    sentinel_counts  = Counter()
    directive_counts = Counter()
    domain_counts    = Counter()
    lang_counts      = Counter()
    missing_fields   = Counter()
    pattern_counts   = Counter()

    # NLP accumulators
    nlp_count        = 0
    nlp_sentiment    = []
    nlp_vader_pos    = []
    nlp_vader_neg    = []
    nlp_vader_neu    = []
    nlp_subjectivity = []
    nlp_word_count   = []
    nlp_sentence_count = []
    nlp_sentence_len = []
    nlp_fk_grade     = []
    nlp_coleman      = []
    nlp_smog         = []
    nlp_dale_chall   = []
    nlp_reading_levels = Counter()
    nlp_entities     = {t: 0 for t in NLP_ENTITY_TYPES}

    for key in r.scan_iter("article:*", count=500):
        data = r.hgetall(key)
        total += 1

        # Source domain
        source_url = data.get('sourceUrl') or data.get('url') or ''
        domain = _extract_registered_domain(source_url) or '(unknown)'
        domain_counts[domain] += 1

        # Language
        lang_counts[data.get('source_lang') or '(unknown)'] += 1

        # Directive
        cat = data.get('category') or data.get('directive') or '(unknown)'
        directive_counts[cat] += 1

        # Sentinel
        sentinel_counts[_get_sentinel_verdict(data)] += 1

        # Chimera score
        s = _get_chimera_score(data)
        if s is not None:
            scores.append(s)
            score_buckets[min(int(s * 10), 9)] += 1

        # Field completeness
        for field in TRACKED_FIELDS:
            if not _field_present(data, field):
                missing_fields[field] += 1

        # ARC patterns
        purple = data.get('purple_team_analysis', '')
        if purple:
            for code in _scan_arc_patterns(purple):
                pattern_counts[code] += 1

        # --- NLP fields (v2.0) ---
        has_nlp = bool(data.get('nlp_chimera_score'))
        if has_nlp:
            nlp_count += 1

            def _f(field):
                return _safe_float(data.get(field))

            v = _f('nlp_sentiment');        nlp_sentiment.append(v)    if v is not None else None
            v = _f('nlp_vader_pos');        nlp_vader_pos.append(v)    if v is not None else None
            v = _f('nlp_vader_neg');        nlp_vader_neg.append(v)    if v is not None else None
            v = _f('nlp_vader_neu');        nlp_vader_neu.append(v)    if v is not None else None
            v = _f('nlp_subjectivity');     nlp_subjectivity.append(v) if v is not None else None
            v = _f('nlp_word_count');       nlp_word_count.append(v)   if v is not None else None
            v = _f('nlp_sentence_count');   nlp_sentence_count.append(v) if v is not None else None
            v = _f('nlp_avg_sentence_len'); nlp_sentence_len.append(v) if v is not None else None
            v = _f('nlp_fk_grade');         nlp_fk_grade.append(v)     if v is not None else None
            v = _f('nlp_coleman_liau');     nlp_coleman.append(v)      if v is not None else None
            v = _f('nlp_smog');             nlp_smog.append(v)         if v is not None else None
            v = _f('nlp_dale_chall');       nlp_dale_chall.append(v)   if v is not None else None

            level = data.get('nlp_reading_level', '')
            if level:
                nlp_reading_levels[level] += 1

            for entity_type in NLP_ENTITY_TYPES:
                v = _safe_float(data.get(f'nlp_entity_{entity_type}'), 0)
                nlp_entities[entity_type] += int(v)

    # ==========================================================================
    # Publish corpus metrics (v1.0 unchanged)
    # ==========================================================================
    g_total.set(total)
    scored = len(scores)
    g_scored.set(scored)

    if scores:
        avg = sum(scores) / scored
        g_chimera_avg.set(round(avg, 4))
        g_chimera_low.set(sum(1 for s in scores if s < 0.3))
        g_chimera_high.set(sum(1 for s in scores if s >= 0.7))
    else:
        g_chimera_avg.set(0)
        g_chimera_low.set(0)
        g_chimera_high.set(0)

    for i in range(10):
        label = f"{i/10:.1f}-{(i+1)/10:.1f}"
        g_chimera_bucket.labels(bucket=label).set(score_buckets.get(i, 0))

    for verdict in ['HUMAN', 'UNCERTAIN', 'SYNTHETIC', '(NONE)']:
        g_sentinel.labels(verdict=verdict).set(sentinel_counts.get(verdict, 0))

    synthetic = sentinel_counts.get('SYNTHETIC', 0)
    g_synthetic_pct.set(round(synthetic / total * 100, 2) if total else 0)

    for directive, count in directive_counts.items():
        g_directive.labels(directive=directive).set(count)

    for domain, count in domain_counts.most_common(TOP_SOURCES):
        g_source.labels(domain=domain).set(count)

    for lang, count in lang_counts.items():
        g_language.labels(lang=lang).set(count)

    for field in TRACKED_FIELDS:
        missing = missing_fields.get(field, 0)
        pct = round((total - missing) / total * 100, 1) if total else 0
        g_completeness.labels(field=field).set(pct)

    for code, name in ARC_PATTERNS.items():
        g_arc_pattern.labels(code=code, name=name).set(pattern_counts.get(code, 0))

    # ==========================================================================
    # Publish NLP metrics (v2.0)
    # ==========================================================================
    g_nlp_coverage_pct.set(round(nlp_count / total * 100, 1) if total else 0)

    g_nlp_sentiment_avg.set(_avg(nlp_sentiment))
    g_nlp_vader_pos_avg.set(_avg(nlp_vader_pos))
    g_nlp_vader_neg_avg.set(_avg(nlp_vader_neg))
    g_nlp_vader_neu_avg.set(_avg(nlp_vader_neu))
    g_nlp_subjectivity_avg.set(_avg(nlp_subjectivity))
    g_nlp_word_count_avg.set(_avg(nlp_word_count))
    g_nlp_sentence_count_avg.set(_avg(nlp_sentence_count))
    g_nlp_sentence_len_avg.set(_avg(nlp_sentence_len))
    g_nlp_fk_grade_avg.set(_avg(nlp_fk_grade))
    g_nlp_coleman_liau_avg.set(_avg(nlp_coleman))
    g_nlp_smog_avg.set(_avg(nlp_smog))
    g_nlp_dale_chall_avg.set(_avg(nlp_dale_chall))

    for level in READING_LEVELS:
        g_nlp_reading_level.labels(level=level).set(nlp_reading_levels.get(level, 0))

    for entity_type in NLP_ENTITY_TYPES:
        g_nlp_entity.labels(entity_type=entity_type).set(nlp_entities[entity_type])

    # ==========================================================================
    # Pipeline health metrics (v2.0)
    # ==========================================================================
    try:
        scrape_pipeline_health(r)
    except Exception as e:
        log.warning(f"Pipeline health scrape failed (non-fatal): {e}")

    # ==========================================================================
    # Timing
    # ==========================================================================
    duration = time.time() - t0
    g_last_scrape.set(time.time())
    g_scrape_duration.set(round(duration, 2))

    log.info(
        f"Scrape complete: {total} articles ({nlp_count} with NLP) in {duration:.1f}s. "
        f"Avg chimera={round(sum(scores)/len(scores), 3) if scores else 'N/A'}, "
        f"SYNTHETIC={synthetic} ({synthetic/total*100:.1f}% of total), "
        f"Avg sentiment={_avg(nlp_sentiment):.3f}, "
        f"Avg subjectivity={_avg(nlp_subjectivity):.3f}, "
        f"Avg FK grade={_avg(nlp_fk_grade):.1f}"
    )


def scrape_loop(r, interval):
    while True:
        try:
            scrape(r)
        except Exception as e:
            log.error(f"Scrape failed: {e}", exc_info=True)
        log.info(f"Next scrape in {interval//60} minutes.")
        time.sleep(interval)


# =============================================================================
# Fast loop (60s) — heartbeats, weekly cloud counter, Redis memory
# =============================================================================

def scrape_fast(r_arc, r_hnt):
    now = time.time()
    for stack, client, key in (
        ("arc", r_arc, "arc:scribe:last_cycle"),
        ("huntaegis", r_hnt, "huntaegis:scribe:last_cycle"),
    ):
        ts = 0
        try:
            ts = int(client.get(key) or 0)
        except (ValueError, TypeError, redis.RedisError):
            pass
        g_scribe_heartbeat.labels(stack=stack).set(ts)
        g_scribe_heartbeat_age.labels(stack=stack).set(round(now - ts, 1) if ts else -1)

    # Weekly cloud escalation counter — same key shape as escalation._weekly_key
    iso_year, iso_week, _ = datetime.now().isocalendar()
    weekly_key = f"arc:cloud_calls:weekly:{iso_year}-W{iso_week:02d}"
    g_cloud_calls_weekly.set(int(r_arc.get(weekly_key) or 0))

    # Redis memory pressure (instance-wide, shared across stacks)
    info = r_arc.info('memory')
    used, maxm = info.get('used_memory', 0), info.get('maxmemory', 0)
    g_redis_used_memory.set(used)
    g_redis_maxmemory.set(maxm)
    g_redis_memory_ratio.set(round(used / maxm, 4) if maxm else 0)


def fast_loop(r_arc, r_hnt, interval=60):
    while True:
        try:
            scrape_fast(r_arc, r_hnt)
        except Exception as e:
            log.warning(f"Fast scrape failed (non-fatal): {e}")
        time.sleep(interval)


def main():
    log.info(f"Arc Codex Corpus Exporter v2.0 — port {EXPORTER_PORT}")
    log.info(f"Scrape interval: {INTERVAL_SEC//60} minutes")

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                    db=REDIS_DB, decode_responses=True)
    try:
        r.ping()
        log.info("✅ Redis connected.")
    except Exception as e:
        log.error(f"❌ Redis connection failed: {e}")
        raise

    start_http_server(EXPORTER_PORT)
    log.info(f"✅ Metrics available at http://localhost:{EXPORTER_PORT}/metrics")

    t = threading.Thread(target=scrape_loop, args=(r, INTERVAL_SEC), daemon=True)
    t.start()

    # Huntaegis heartbeat lives in its own DB (1) — read-only client.
    r_hnt = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                        db=1, decode_responses=True)
    t_fast = threading.Thread(target=fast_loop, args=(r, r_hnt), daemon=True)
    t_fast.start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("👋 Exporter stopped.")


if __name__ == "__main__":
    main()
