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
import hashlib
import math
import time
import threading
import logging
from collections import Counter
from datetime import datetime, timezone

import redis
import urllib.parse
from dotenv import load_dotenv
from prometheus_client import (
    start_http_server, Counter as PromCounter, Gauge, Histogram,
    REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR
)
from prometheus_client.core import HistogramMetricFamily

from operational_state import (
    ANALYZER_ACTIVE_KEY,
    ANALYZER_COUNTERS_KEY,
    ANALYZER_DURATION_BUCKETS,
    ANALYZER_DURATION_KEY,
    ANALYZER_FAILURE_STAGES,
    ANALYZER_HEARTBEAT_KEY,
    ANALYZER_JOB_OUTCOMES,
    ANALYZER_QUEUE_KEY,
    ANALYZER_QUEUE_TIMELINE_KEY,
    ANALYZER_QUEUE_TRACKING_KEY,
    ANALYZER_STATE_KEY,
    ANALYZER_TRACKING_LIMIT,
    ANALYZER_TRACKING_VERSION,
    EXPORTER_ERROR_STAGES,
    EXPORTER_SCAN_RESULTS,
    SCRIBE_COUNTERS_KEY,
    SCRIBE_ERROR_STAGES,
    SCRIBE_HEARTBEAT_KEY,
    SCRIBE_POLL_RESULTS,
    SCRIBE_STATE_KEY,
    WORKER_STATES,
    ExporterHealthState,
    require_allowed,
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
STALE_AFTER_SEC = max(INTERVAL_SEC * 2 + 300, 900)
SCRIBE_HEARTBEAT_MAX_AGE_SEC = 180
SCRIBE_ACTIVE_STALL_SEC = max(INTERVAL_SEC, 3600)
ANALYZER_HEARTBEAT_MAX_AGE_SEC = 180
ANALYZER_ACTIVE_STALL_SEC = 1500
STACK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
# Wave C R6: newest article timestamp from the feed ZSET (feed is scored
# by unix timestamp). Feeds the ArcFeedStale alert; a scribe outage or a
# widespread source failure surfaces here as the value stops advancing.
g_last_publish    = Gauge('arc_last_publish_timestamp',         'Unix timestamp of the newest article in the feed ZSET')
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
# Cloud valve (2026-07-12): exhaustion should be a Grafana fact at 60%, not
# log archaeology at 100% — the July cap exhaustion was invisible for 5 days.
g_cloud_calls_week = Gauge('arc_cloud_calls_week',     'Cloud escalation calls this ISO week (arc:cloud_calls:weekly:*)')
g_cloud_week_cap   = Gauge('arc_cloud_calls_week_cap', 'Weekly cloud call cap — escalation degrades to local at 100%')
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

# P0-A exporter self-observation. These separate HTTP scrapeability
# (Prometheus up) from completed-scan status, staleness, and readiness.
g_intel_ready = Gauge(
    'arc_intelligence_exporter_ready',
    '1 only after a complete successful scan and a recent successful fast-state read',
)
g_intel_stale = Gauge(
    'arc_intelligence_exporter_stale',
    '1 when no successful scan exists or the last successful scan is too old',
)
g_intel_scan_in_progress = Gauge(
    'arc_intelligence_exporter_scan_in_progress',
    '1 while a full corpus scan is running',
)
g_intel_last_scan_success = Gauge(
    'arc_intelligence_exporter_last_scan_success',
    'Most recently completed scan result (1 success, 0 failure or not yet run)',
)
g_intel_last_scan = Gauge(
    'arc_intelligence_exporter_last_scan_timestamp_seconds',
    'Unix timestamp of the last fully successful scan; 0 before first success',
)
g_intel_last_attempt = Gauge(
    'arc_intelligence_exporter_last_scan_attempt_timestamp_seconds',
    'Unix timestamp of the most recent scan start or completion; 0 before first attempt',
)
g_intel_last_fast_state = Gauge(
    'arc_intelligence_exporter_last_fast_state_timestamp_seconds',
    'Unix timestamp of the last successful fast-state read; 0 when unavailable',
)
c_intel_scans = PromCounter(
    'arc_intelligence_exporter_scans_total',
    'Full corpus scan attempts by result',
    ['result'],
)
h_intel_scan_duration = Histogram(
    'arc_intelligence_exporter_scan_duration_seconds',
    'Duration of full corpus scan attempts, including failures',
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)
c_intel_scan_errors = PromCounter(
    'arc_intelligence_exporter_scan_errors_total',
    'Exporter errors by bounded stage',
    ['stage'],
)

for _result in sorted(EXPORTER_SCAN_RESULTS):
    c_intel_scans.labels(result=_result)
for _stage in sorted(EXPORTER_ERROR_STAGES):
    c_intel_scan_errors.labels(stage=_stage)

exporter_health = ExporterHealthState(stale_after_seconds=STALE_AFTER_SEC)

# P0-B Scribe state. PID existence is diagnostic only; readiness additionally
# requires a fresh heartbeat and a valid non-failed, non-stalled state record.
g_scribe_process_exists_p0 = Gauge(
    'arc_scribe_process_exists',
    '1 when the registered Arc Scribe PID has matching cwd and command identity',
)
g_scribe_ready_p0 = Gauge(
    'arc_scribe_ready',
    '1 when Scribe has matching process identity, fresh heartbeat, and valid healthy state',
)
g_scribe_stale_p0 = Gauge(
    'arc_scribe_stale',
    '1 when Scribe operational state is missing, malformed, expired, or active too long',
)
g_scribe_state_valid_p0 = Gauge(
    'arc_scribe_state_valid',
    '1 when the bounded Scribe state record is present and valid',
)
g_scribe_state_p0 = Gauge(
    'arc_scribe_state',
    'One-hot current Scribe state from a fixed vocabulary',
    ['state'],
)
g_scribe_heartbeat_p0 = Gauge(
    'arc_scribe_heartbeat_timestamp_seconds',
    'Unix timestamp of the latest P0 Scribe heartbeat; NaN when missing or malformed',
)
g_scribe_heartbeat_age_p0 = Gauge(
    'arc_scribe_operational_heartbeat_age_seconds',
    'Age of the latest P0 Scribe heartbeat; NaN when missing or malformed',
)
g_scribe_last_poll_p0 = Gauge(
    'arc_scribe_last_poll_timestamp_seconds',
    'Unix timestamp of the most recent RSS polling-cycle attempt; NaN when unavailable',
)
g_scribe_last_success_p0 = Gauge(
    'arc_scribe_last_success_timestamp_seconds',
    'Unix timestamp of the most recent completed healthy cycle, including quiet cycles',
)
g_scribe_last_failure_p0 = Gauge(
    'arc_scribe_last_failure_timestamp_seconds',
    'Unix timestamp of the most recent recorded failed cycle or stage; NaN when unavailable',
)
c_scribe_source_polls_p0 = PromCounter(
    'arc_scribe_source_polls_total',
    'RSS source poll events since P0-B deployment by bounded result',
    ['result'],
)
c_scribe_articles_discovered_p0 = PromCounter(
    'arc_scribe_articles_discovered_total',
    'Valid RSS entries discovered since P0-B deployment',
)
c_scribe_articles_new_p0 = PromCounter(
    'arc_scribe_articles_new_total',
    'New quality article candidates observed since P0-B deployment',
)
c_scribe_articles_duplicate_p0 = PromCounter(
    'arc_scribe_articles_duplicate_total',
    'Entries rejected by existing deduplication decisions since P0-B deployment',
)
c_scribe_articles_rejected_p0 = PromCounter(
    'arc_scribe_articles_rejected_total',
    'Fetched articles rejected by the existing quality gate since P0-B deployment',
)
c_scribe_articles_skipped_p0 = PromCounter(
    'arc_scribe_articles_skipped_total',
    'Entries skipped after an existing fetch/extraction failure since P0-B deployment',
)
c_scribe_errors_p0 = PromCounter(
    'arc_scribe_errors_total',
    'Scribe operational errors since P0-B deployment by bounded stage',
    ['stage'],
)

for _state in sorted(WORKER_STATES):
    g_scribe_state_p0.labels(state=_state).set(float('nan'))
for _result in sorted(SCRIBE_POLL_RESULTS):
    c_scribe_source_polls_p0.labels(result=_result)
for _stage in sorted(SCRIBE_ERROR_STAGES):
    c_scribe_errors_p0.labels(stage=_stage)

_scribe_counter_seen = {}
_scribe_counter_lock = threading.Lock()

# P0-C uses one fixed stack and queue vocabulary. Exact IDs/digests never
# become labels or samples.
_ANALYZER_STACK = 'arc'
_ANALYZER_QUEUE = 'analysis'
g_analyzer_process_exists = Gauge('arc_analyzer_process_exists', 'Matching registered analyzer process exists', ['stack'])
g_analyzer_ready = Gauge('arc_analyzer_ready', 'Analyzer readiness, distinct from PID existence', ['stack'])
g_analyzer_stale = Gauge('arc_analyzer_stale', 'Analyzer heartbeat/state is missing, malformed, expired, or stalled', ['stack'])
g_analyzer_state_valid = Gauge('arc_analyzer_state_valid', 'Bounded analyzer state record is valid', ['stack'])
g_analyzer_state = Gauge('arc_analyzer_state', 'One-hot bounded analyzer state', ['stack', 'state'])
g_analyzer_heartbeat = Gauge('arc_analyzer_heartbeat_timestamp_seconds', 'Latest analyzer operational heartbeat', ['stack'])
g_analyzer_heartbeat_age = Gauge('arc_analyzer_heartbeat_age_seconds', 'Age of analyzer operational heartbeat', ['stack'])
g_analyzer_last_started = Gauge('arc_analyzer_last_started_timestamp_seconds', 'Latest analysis job start', ['stack'])
g_analyzer_last_success = Gauge('arc_analyzer_last_success_timestamp_seconds', 'Latest completed or safely skipped analysis job', ['stack'])
g_analyzer_last_failure = Gauge('arc_analyzer_last_failure_timestamp_seconds', 'Latest failed analysis job', ['stack'])
c_analyzer_jobs = PromCounter('arc_analyzer_jobs_total', 'Persistent analyzer jobs since P0-C deployment', ['stack', 'outcome'])
c_analyzer_failures = PromCounter('arc_analyzer_failures_total', 'Persistent analyzer failures by bounded stage', ['stack', 'stage'])
g_analyzer_queue_depth = Gauge('arc_analyzer_queue_depth', 'Current analyzer queue occurrence count', ['stack', 'queue'])
g_analyzer_queue_age_known = Gauge('arc_analyzer_queue_age_known', '1 only when every queue occurrence has a valid aligned timestamp', ['stack', 'queue'])
g_analyzer_oldest_age = Gauge('arc_analyzer_oldest_item_age_seconds', 'Oldest enqueue age; NaN when empty or tracking is uncertain', ['stack', 'queue'])
g_analyzer_active_locks = Gauge('arc_analyzer_active_locks', 'Current non-stale operational processing locks', ['stack'])
g_analyzer_stale_locks = Gauge('arc_analyzer_stale_locks', 'Operational processing locks older than the stall threshold', ['stack'])

for _outcome in sorted(ANALYZER_JOB_OUTCOMES):
    c_analyzer_jobs.labels(stack=_ANALYZER_STACK, outcome=_outcome)
for _stage in sorted(ANALYZER_FAILURE_STAGES):
    c_analyzer_failures.labels(stack=_ANALYZER_STACK, stage=_stage)
for _state in sorted(WORKER_STATES):
    g_analyzer_state.labels(stack=_ANALYZER_STACK, state=_state).set(float('nan'))

_analyzer_counter_seen = {}
_analyzer_counter_lock = threading.Lock()


class AnalyzerDurationCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = None

    def update(self, buckets, total_sum):
        with self._lock:
            self._snapshot = (tuple(buckets), float(total_sum))

    def collect(self):
        metric = HistogramMetricFamily(
            'arc_analyzer_job_duration_seconds',
            'Persistent analyzer job duration observations since P0-C deployment',
            labels=['stack'],
        )
        with self._lock:
            snapshot = self._snapshot
        if snapshot is not None:
            metric.add_metric([_ANALYZER_STACK], snapshot[0], snapshot[1])
        yield metric


analyzer_duration_collector = AnalyzerDurationCollector()
REGISTRY.register(analyzer_duration_collector)


class ScanStageError(RuntimeError):
    """One or more bounded scan-stage failures."""

    def __init__(self, failures):
        self.failures = tuple(
            (require_allowed(stage, EXPORTER_ERROR_STAGES, 'scan error stage'), cause)
            for stage, cause in failures
        )
        super().__init__('; '.join(f"{stage} failed: {cause}" for stage, cause in self.failures))


def _publish_exporter_health(now=None):
    snapshot = exporter_health.snapshot(now=now)
    g_intel_ready.set(1 if snapshot.ready else 0)
    g_intel_stale.set(1 if snapshot.stale else 0)
    g_intel_scan_in_progress.set(1 if snapshot.scan_in_progress else 0)
    g_intel_last_scan_success.set(1 if snapshot.last_scan_success else 0)
    g_intel_last_scan.set(snapshot.last_scan_timestamp)
    g_intel_last_attempt.set(snapshot.last_scan_attempt_timestamp)
    g_intel_last_fast_state.set(snapshot.last_fast_state_timestamp)
    return snapshot


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


def _registered_scribe_process_exists():
    """Validate the registered Scribe PID without treating PID existence as health."""
    try:
        with open(os.path.join(STACK_ROOT, 'pids', 'scribe.pid'), encoding='ascii') as handle:
            pid = int(handle.read().strip())
        proc_root = f'/proc/{pid}'
        expected_cwd = os.path.realpath(os.path.join(STACK_ROOT, 'backend'))
        if os.path.realpath(os.readlink(os.path.join(proc_root, 'cwd'))) != expected_cwd:
            return False
        with open(os.path.join(proc_root, 'cmdline'), 'rb') as handle:
            command = handle.read().replace(b'\0', b' ').decode('utf-8', 'replace')
        return 'scribe.py' in command and 'python' in command
    except (OSError, ValueError):
        return False


def _finite_timestamp(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 and math.isfinite(parsed) else None


def _set_optional_gauge(gauge, value):
    gauge.set(value if value is not None else float('nan'))


def _sync_scribe_counter(metric, identity, value):
    """Mirror a persistent Redis counter into a process-lifetime Prom counter."""
    parsed = int(value or 0)
    if parsed < 0:
        raise ValueError(f'negative Scribe counter: {identity}')
    with _scribe_counter_lock:
        previous = _scribe_counter_seen.get(identity)
        delta = parsed if previous is None or parsed < previous else parsed - previous
        if delta:
            metric.inc(delta)
        _scribe_counter_seen[identity] = parsed


def _clear_scribe_operational_metrics(process_exists=None):
    if process_exists is None:
        process_exists = _registered_scribe_process_exists()
    g_scribe_process_exists_p0.set(1 if process_exists else 0)
    g_scribe_ready_p0.set(0)
    g_scribe_stale_p0.set(1)
    g_scribe_state_valid_p0.set(0)
    for state in WORKER_STATES:
        g_scribe_state_p0.labels(state=state).set(float('nan'))
    for gauge in (
        g_scribe_heartbeat_p0,
        g_scribe_heartbeat_age_p0,
        g_scribe_last_poll_p0,
        g_scribe_last_success_p0,
        g_scribe_last_failure_p0,
    ):
        gauge.set(float('nan'))


def scrape_scribe_operational(r, now=None):
    """Read bounded Scribe state; malformed or missing state fails visibly."""
    now = float(time.time() if now is None else now)
    process_exists = _registered_scribe_process_exists()
    heartbeat_raw, state, counters = r.get(SCRIBE_HEARTBEAT_KEY), r.hgetall(SCRIBE_STATE_KEY), r.hgetall(SCRIBE_COUNTERS_KEY)
    heartbeat = _finite_timestamp(heartbeat_raw)
    status = state.get('status')
    status_since = _finite_timestamp(state.get('status_since'))
    state_valid = status in WORKER_STATES and status_since is not None

    g_scribe_process_exists_p0.set(1 if process_exists else 0)
    g_scribe_state_valid_p0.set(1 if state_valid else 0)
    for candidate in WORKER_STATES:
        g_scribe_state_p0.labels(state=candidate).set(
            1 if state_valid and candidate == status else (0 if state_valid else float('nan'))
        )

    _set_optional_gauge(g_scribe_heartbeat_p0, heartbeat)
    _set_optional_gauge(g_scribe_heartbeat_age_p0, max(0, now - heartbeat) if heartbeat else None)
    _set_optional_gauge(g_scribe_last_poll_p0, _finite_timestamp(state.get('last_poll')))
    _set_optional_gauge(g_scribe_last_success_p0, _finite_timestamp(state.get('last_success')))
    _set_optional_gauge(g_scribe_last_failure_p0, _finite_timestamp(state.get('last_failure')))

    fresh = heartbeat is not None and 0 <= now - heartbeat <= SCRIBE_HEARTBEAT_MAX_AGE_SEC
    active_stalled = bool(state_valid and status == 'active' and now - status_since > SCRIBE_ACTIVE_STALL_SEC)
    stale = not fresh or not state_valid or active_stalled
    healthy_state = status in {'idle', 'active'}
    g_scribe_stale_p0.set(1 if stale else 0)
    g_scribe_ready_p0.set(1 if process_exists and not stale and healthy_state else 0)

    mappings = {
        'articles_discovered': c_scribe_articles_discovered_p0,
        'articles_new': c_scribe_articles_new_p0,
        'articles_duplicate': c_scribe_articles_duplicate_p0,
        'articles_rejected': c_scribe_articles_rejected_p0,
        'articles_skipped': c_scribe_articles_skipped_p0,
    }
    for result in SCRIBE_POLL_RESULTS:
        field = f'poll_{result}'
        _sync_scribe_counter(c_scribe_source_polls_p0.labels(result=result), ('poll', result), counters.get(field))
    for field, metric in mappings.items():
        _sync_scribe_counter(metric, ('article', field), counters.get(field))
    for stage in SCRIBE_ERROR_STAGES:
        field = f'errors_{stage}'
        _sync_scribe_counter(c_scribe_errors_p0.labels(stage=stage), ('error', stage), counters.get(field))


def _matching_analyzer_process_count():
    count = 0
    expected_cwd = os.path.realpath(os.path.join(STACK_ROOT, 'backend'))
    try:
        entries = os.listdir('/proc')
    except OSError:
        return 0
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            root = os.path.join('/proc', entry)
            if os.path.realpath(os.readlink(os.path.join(root, 'cwd'))) != expected_cwd:
                continue
            with open(os.path.join(root, 'cmdline'), 'rb') as handle:
                command = handle.read().replace(b'\0', b' ').decode('utf-8', 'replace')
            if 'analyzer.py' in command and 'python' in command:
                count += 1
        except OSError:
            continue
    return count


def _sync_analyzer_counter(metric, identity, value):
    parsed = int(value or 0)
    if parsed < 0:
        raise ValueError('negative analyzer counter')
    with _analyzer_counter_lock:
        previous = _analyzer_counter_seen.get(identity)
        delta = parsed if previous is None or parsed < previous else parsed - previous
        if delta:
            metric.inc(delta)
        _analyzer_counter_seen[identity] = parsed


def _clear_analyzer_metrics(process_count=None):
    process_count = _matching_analyzer_process_count() if process_count is None else process_count
    g_analyzer_process_exists.labels(stack=_ANALYZER_STACK).set(1 if process_count == 1 else 0)
    g_analyzer_ready.labels(stack=_ANALYZER_STACK).set(0)
    g_analyzer_stale.labels(stack=_ANALYZER_STACK).set(1)
    g_analyzer_state_valid.labels(stack=_ANALYZER_STACK).set(0)
    for state in WORKER_STATES:
        g_analyzer_state.labels(stack=_ANALYZER_STACK, state=state).set(float('nan'))
    for gauge in (g_analyzer_heartbeat, g_analyzer_heartbeat_age,
                  g_analyzer_last_started, g_analyzer_last_success, g_analyzer_last_failure):
        gauge.labels(stack=_ANALYZER_STACK).set(float('nan'))
    g_analyzer_queue_depth.labels(stack=_ANALYZER_STACK, queue=_ANALYZER_QUEUE).set(float('nan'))
    g_analyzer_queue_age_known.labels(stack=_ANALYZER_STACK, queue=_ANALYZER_QUEUE).set(0)
    g_analyzer_oldest_age.labels(stack=_ANALYZER_STACK, queue=_ANALYZER_QUEUE).set(float('nan'))
    g_analyzer_active_locks.labels(stack=_ANALYZER_STACK).set(float('nan'))
    g_analyzer_stale_locks.labels(stack=_ANALYZER_STACK).set(float('nan'))


def scrape_analyzer_operational(r, now=None):
    now = float(time.time() if now is None else now)
    process_count = _matching_analyzer_process_count()
    heartbeat = _finite_timestamp(r.get(ANALYZER_HEARTBEAT_KEY))
    state = r.hgetall(ANALYZER_STATE_KEY)
    counters = r.hgetall(ANALYZER_COUNTERS_KEY)
    duration = r.hgetall(ANALYZER_DURATION_KEY)
    status = state.get('status')
    status_since = _finite_timestamp(state.get('status_since'))
    state_valid = status in WORKER_STATES and status_since is not None
    fresh = heartbeat is not None and 0 <= now - heartbeat <= ANALYZER_HEARTBEAT_MAX_AGE_SEC
    stalled = bool(state_valid and status == 'active' and now - status_since > ANALYZER_ACTIVE_STALL_SEC)
    stale = not fresh or not state_valid or stalled or process_count != 1

    g_analyzer_process_exists.labels(stack=_ANALYZER_STACK).set(1 if process_count == 1 else 0)
    g_analyzer_ready.labels(stack=_ANALYZER_STACK).set(
        1 if not stale and status in {'idle', 'active'} else 0)
    g_analyzer_stale.labels(stack=_ANALYZER_STACK).set(1 if stale else 0)
    g_analyzer_state_valid.labels(stack=_ANALYZER_STACK).set(1 if state_valid else 0)
    for candidate in WORKER_STATES:
        g_analyzer_state.labels(stack=_ANALYZER_STACK, state=candidate).set(
            1 if state_valid and candidate == status else (0 if state_valid else float('nan')))
    _set_optional_gauge(g_analyzer_heartbeat.labels(stack=_ANALYZER_STACK), heartbeat)
    _set_optional_gauge(g_analyzer_heartbeat_age.labels(stack=_ANALYZER_STACK),
                        max(0, now - heartbeat) if heartbeat else None)
    _set_optional_gauge(g_analyzer_last_started.labels(stack=_ANALYZER_STACK), _finite_timestamp(state.get('last_started')))
    _set_optional_gauge(g_analyzer_last_success.labels(stack=_ANALYZER_STACK), _finite_timestamp(state.get('last_success')))
    _set_optional_gauge(g_analyzer_last_failure.labels(stack=_ANALYZER_STACK), _finite_timestamp(state.get('last_failure')))

    for outcome in ANALYZER_JOB_OUTCOMES:
        _sync_analyzer_counter(c_analyzer_jobs.labels(stack=_ANALYZER_STACK, outcome=outcome),
                               ('job', outcome), counters.get(f'jobs_{outcome}'))
    for stage in ANALYZER_FAILURE_STAGES:
        _sync_analyzer_counter(c_analyzer_failures.labels(stack=_ANALYZER_STACK, stage=stage),
                               ('failure', stage), counters.get(f'failures_{stage}'))

    if duration:
        buckets = []
        previous = -1
        for bound in ANALYZER_DURATION_BUCKETS:
            value = int(duration.get(f'bucket_{bound}', 0))
            if value < previous:
                raise ValueError('non-cumulative analyzer histogram')
            buckets.append((str(float(bound)), value))
            previous = value
        infinite = int(duration.get('bucket_inf', 0))
        count = int(duration.get('count', 0))
        total_sum = float(duration.get('sum', 0))
        if infinite != count or infinite < previous or total_sum < 0 or not math.isfinite(total_sum):
            raise ValueError('invalid analyzer histogram state')
        buckets.append(('+Inf', infinite))
        analyzer_duration_collector.update(buckets, total_sum)

    depth = int(r.llen(ANALYZER_QUEUE_KEY))
    g_analyzer_queue_depth.labels(stack=_ANALYZER_STACK, queue=_ANALYZER_QUEUE).set(depth)
    known = False
    oldest = None
    if (process_count == 1 and depth <= ANALYZER_TRACKING_LIMIT
            and r.get(ANALYZER_QUEUE_TRACKING_KEY) == ANALYZER_TRACKING_VERSION):
        timeline_length = int(r.llen(ANALYZER_QUEUE_TIMELINE_KEY))
        if timeline_length == depth:
            if depth == 0:
                known = True
            else:
                queue_entries = r.lrange(ANALYZER_QUEUE_KEY, 0, ANALYZER_TRACKING_LIMIT - 1)
                timeline = r.lrange(ANALYZER_QUEUE_TIMELINE_KEY, 0, ANALYZER_TRACKING_LIMIT - 1)
                timestamps = []
                if len(queue_entries) == len(timeline) == depth:
                    known = True
                    for article_id, record in zip(queue_entries, timeline):
                        digest, separator, raw_timestamp = record.partition('|')
                        timestamp = _finite_timestamp(raw_timestamp) if separator else None
                        expected = hashlib.sha256(article_id.encode('utf-8')).hexdigest()
                        if digest != expected or len(digest) != 64 or timestamp is None or timestamp > now:
                            known = False
                            break
                        timestamps.append(timestamp)
                    if known:
                        oldest = max(0, now - min(timestamps))
    g_analyzer_queue_age_known.labels(stack=_ANALYZER_STACK, queue=_ANALYZER_QUEUE).set(1 if known else 0)
    g_analyzer_oldest_age.labels(stack=_ANALYZER_STACK, queue=_ANALYZER_QUEUE).set(
        oldest if known and oldest is not None else float('nan'))

    active = r.zrange(ANALYZER_ACTIVE_KEY, 0, -1, withscores=True)
    recent = sum(1 for _member, started in active if now - float(started) <= ANALYZER_ACTIVE_STALL_SEC)
    g_analyzer_active_locks.labels(stack=_ANALYZER_STACK).set(recent)
    g_analyzer_stale_locks.labels(stack=_ANALYZER_STACK).set(len(active) - recent)

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

    # --- Cloud valve: weekly escalation-call counter vs cap ---
    try:
        from escalation import weekly_cloud_call_count, WEEKLY_CAP
        g_cloud_calls_week.set(weekly_cloud_call_count(r))
        g_cloud_week_cap.set(WEEKLY_CAP)
    except Exception as e:
        log.debug("cloud-valve gauge skipped: %s", e)


# =============================================================================
# Main corpus scrape — reads article:* hashes
# =============================================================================

def scrape(r):
    """Full corpus scan. Called once per INTERVAL_SEC in background thread."""
    log.info("Starting corpus scrape v2.0...")
    t0 = time.time()
    stage_failures = []

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
        stage_failures.append(('pipeline_stats', e))

    # ==========================================================================
    # Timing + newest-publish gauge
    # ==========================================================================
    duration = time.time() - t0
    g_last_scrape.set(time.time())
    g_scrape_duration.set(round(duration, 2))

    # Wave C R6: newest article timestamp (feed ZSET is scored by unix ts).
    # ZRANGE feed -1 -1 WITHSCORES → [(id, score)]. Set to 0 on empty feed
    # so the alert can distinguish "never published" from a stale gauge.
    try:
        newest = r.zrevrange('feed', 0, 0, withscores=True)
        g_last_publish.set(float(newest[0][1]) if newest else 0.0)
    except Exception as e:
        log.warning(f"last_publish_timestamp gauge update failed: {e}")
        stage_failures.append(('publish_timestamp', e))

    log.info(
        f"Scrape complete: {total} articles ({nlp_count} with NLP) in {duration:.1f}s. "
        f"Avg chimera={round(sum(scores)/len(scores), 3) if scores else 'N/A'}, "
        f"SYNTHETIC={synthetic} ({synthetic/total*100:.1f}% of total), "
        f"Avg sentiment={_avg(nlp_sentiment):.3f}, "
        f"Avg subjectivity={_avg(nlp_subjectivity):.3f}, "
        f"Avg FK grade={_avg(nlp_fk_grade):.1f}"
    )

    if stage_failures:
        raise ScanStageError(stage_failures)


def run_scan_once(r):
    """Run and account for one full scan; return True only on full success."""
    exporter_health.begin_scan()
    _publish_exporter_health()
    started = time.monotonic()
    try:
        scrape(r)
    except ScanStageError as e:
        for stage, _cause in e.failures:
            c_intel_scan_errors.labels(stage=stage).inc()
        c_intel_scans.labels(result='failure').inc()
        exporter_health.finish_scan(False)
        log.error("Incomplete exporter scan: %s", e)
        return False
    except Exception as e:
        c_intel_scan_errors.labels(stage='redis_scan').inc()
        c_intel_scans.labels(result='failure').inc()
        exporter_health.finish_scan(False)
        log.error(f"Scrape failed: {e}", exc_info=True)
        return False
    else:
        c_intel_scans.labels(result='success').inc()
        exporter_health.finish_scan(True)
        return True
    finally:
        h_intel_scan_duration.observe(time.monotonic() - started)
        _publish_exporter_health()


def scrape_loop(r, interval):
    while True:
        run_scan_once(r)
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

    try:
        scrape_scribe_operational(r_arc, now=now)
    except Exception as exc:
        _clear_scribe_operational_metrics()
        c_intel_scan_errors.labels(stage='operational_state').inc()
        log.warning('Scribe operational-state read failed: %s', type(exc).__name__)

    try:
        scrape_analyzer_operational(r_arc, now=now)
    except Exception as exc:
        _clear_analyzer_metrics()
        c_intel_scan_errors.labels(stage='operational_state').inc()
        log.warning('Analyzer operational-state read failed: %s', type(exc).__name__)


def fast_loop(r_arc, r_hnt, interval=60):
    while True:
        try:
            scrape_fast(r_arc, r_hnt)
            exporter_health.mark_fast_state_success()
        except Exception as e:
            exporter_health.mark_fast_state_failure()
            c_intel_scan_errors.labels(stage='fast_state').inc()
            log.warning(f"Fast scrape failed (non-fatal): {e}")
        _publish_exporter_health()
        time.sleep(interval)


def main():
    log.info(f"Arc Codex Corpus Exporter v2.0 — port {EXPORTER_PORT}")
    log.info(f"Scrape interval: {INTERVAL_SEC//60} minutes")

    # Publish fail-closed startup state before opening the HTTP listener.
    _publish_exporter_health()

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
