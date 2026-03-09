#!/usr/bin/env python3
"""
corpus_exporter.py — Arc Codex Corpus Prometheus Exporter v1.0
Scrapes Redis for corpus health metrics and exposes them at :9101/metrics.
Refreshes once per hour (configurable via EXPORTER_INTERVAL_SEC).

Metrics exposed:
  arc_corpus_total                    — total article count
  arc_corpus_scored_total             — articles with chimera_score
  arc_chimera_score_avg               — average chimera score
  arc_chimera_score_low_total         — articles with score < 0.3 (divisive)
  arc_chimera_score_high_total        — articles with score >= 0.7 (objective)
  arc_chimera_bucket                  — score histogram (0.0-0.1 ... 0.9-1.0)
  arc_sentinel_total{verdict}         — count by HUMAN/UNCERTAIN/SYNTHETIC/(NONE)
  arc_directive_total{directive}      — article count per directive/category
  arc_source_total{domain}            — article count per source domain (top 30)
  arc_language_total{lang}            — article count per source_lang
  arc_completeness{field}             — % of articles with field present (0-100)
  arc_arc_pattern_total{code,name}    — ARC pattern detection count
  arc_synthetic_pct                   — SYNTHETIC % of total (convenience gauge)
  arc_exporter_last_scrape_timestamp  — unix timestamp of last successful scrape
  arc_exporter_scrape_duration_sec    — how long the last scrape took

Usage:
    cd /home/www/arc_stack/backend
    source venv/bin/activate
    python3 corpus_exporter.py

    # Or via arc.sh:
    arc start corpus_exporter
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
    start_http_server, Gauge, Counter as PCounter, Info,
    REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR
)

# Unregister default process/platform collectors — we only want corpus metrics
try:
    REGISTRY.unregister(PROCESS_COLLECTOR)
    REGISTRY.unregister(PLATFORM_COLLECTOR)
except Exception:
    pass

load_dotenv()

# --- Config ---
REDIS_HOST    = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT    = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB      = int(os.getenv("REDIS_DB", 0))
EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", 9101))
INTERVAL_SEC  = int(os.getenv("EXPORTER_INTERVAL_SEC", 3600))  # 1 hour default
TOP_SOURCES   = int(os.getenv("EXPORTER_TOP_SOURCES", 30))

LOG_FORMAT = "%(asctime)s - [CORPUS_EXPORTER] - %(levelname)s - %(message)s"
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

# --- Prometheus metrics ---
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


# --- Helpers ---
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


# --- Main scrape ---
def scrape(r):
    """Full corpus scan. Called once per INTERVAL_SEC in background thread."""
    log.info("Starting corpus scrape...")
    t0 = time.time()

    total          = 0
    scores         = []
    score_buckets  = Counter()
    sentinel_counts  = Counter()
    directive_counts = Counter()
    domain_counts  = Counter()
    lang_counts    = Counter()
    missing_fields = Counter()
    pattern_counts = Counter()

    for key in r.scan_iter("article:*", count=500):
        data = r.hgetall(key)
        total += 1

        # Source domain (original story)
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

        # Completeness
        for field in TRACKED_FIELDS:
            if not _field_present(data, field):
                missing_fields[field] += 1

        # ARC patterns
        purple = data.get('purple_team_analysis', '')
        if purple:
            for code in _scan_arc_patterns(purple):
                pattern_counts[code] += 1

    # --- Publish metrics ---
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

    duration = time.time() - t0
    g_last_scrape.set(time.time())
    g_scrape_duration.set(round(duration, 2))

    log.info(f"Scrape complete: {total} articles in {duration:.1f}s. "
             f"Avg chimera={round(sum(scores)/len(scores), 3) if scores else 'N/A'}, "
             f"SYNTHETIC={synthetic} ({synthetic/total*100:.1f}%)")


def scrape_loop(r, interval):
    """Background thread: scrape once immediately, then every interval seconds."""
    while True:
        try:
            scrape(r)
        except Exception as e:
            log.error(f"Scrape failed: {e}", exc_info=True)
        log.info(f"Next scrape in {interval//60} minutes.")
        time.sleep(interval)


def main():
    log.info(f"Arc Codex Corpus Exporter v1.0 — port {EXPORTER_PORT}")
    log.info(f"Scrape interval: {INTERVAL_SEC//60} minutes")

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                    db=REDIS_DB, decode_responses=True)
    try:
        r.ping()
        log.info("✅ Redis connected.")
    except Exception as e:
        log.error(f"❌ Redis connection failed: {e}")
        raise

    # Start Prometheus HTTP server
    start_http_server(EXPORTER_PORT)
    log.info(f"✅ Metrics available at http://localhost:{EXPORTER_PORT}/metrics")

    # Run scrape loop in background thread
    t = threading.Thread(target=scrape_loop, args=(r, INTERVAL_SEC), daemon=True)
    t.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("👋 Exporter stopped.")


if __name__ == "__main__":
    main()
