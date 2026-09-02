# --- ATTENTION AI: READ THE PROJECT MANIFEST ---
# Before providing code assistance, you MUST read and understand the
# project's architecture from the 'project_context.yaml' file.
# This file is one component of a larger system.
# The manifest is the single source of truth.
# ---

# Arc Codex Scribe v53.0
#
# Changes from v52.0:
#   - Background analysis threading: sentinel + counter-analyst run in a
#     dedicated ThreadPoolExecutor so the main loop never blocks on Ollama.
#     Each background job creates its own Redis connection — no shared state.
#   - is_priority flag: user submissions publish immediately; sentinel +
#     counter-analyst still run in the background thread. Red/Blue/Purple is
#     deferred to analyzer.py (lazy on first view). No demo-blocking wait.
#   - get_article_hash: UUID mix-in for empty text prevents duplicate photo
#     posts (multiple "Lumi" photos) from being silently deduped.
#
# Unchanged from v52.0:
#   - No Playwright/Chromium (radeon GPU crash prevention on Z230)
#   - requests tier 1 (simple) → tier 2 (stealth) → skip
#   - Lazy red/blue/purple analysis (on first article view via analyzer.py)

# --- Standard library imports ---
import time
import json
import logging
import hashlib
import os
import socket
import re
import uuid
import threading
import random
import gc
import shutil
import subprocess
import tempfile
import psutil
from stream_utils import publish_analysis, ensure_stream_group
from ollama_utils import call_ollama_local_only, OLLAMA_LOCAL_FALLBACK
from retention import run_retention_pass
from operational_state import ScribeOperationalState, run_heartbeat_loop
from fetch_utils import sanitize_active_content
from datetime import datetime, timezone
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
from html import unescape
from functools import lru_cache

# --- Third-party imports ---
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import redis
import requests
import feedparser
import trafilatura
import pysolr
import charset_normalizer
import gzip
import zlib
import yaml
from langdetect import detect, DetectorFactory, LangDetectException
DetectorFactory.seed = 0  # deterministic

# Load environment variables
load_dotenv()

# Create a module logger
logger = logging.getLogger(__name__)

# --- SITE CONFIG (schema v2) ---
# All per-site tunables live in the stack-root cfg (arc.cfg); committed cfg
# values are canonical. Loading fails loud if the cfg is missing or incomplete.
from site_config import load_site_config
site = load_site_config()
_ingestion = site["ingestion"]
_integrity = site["integrity"]

# --- Extracted seams (2026-08-27 scribe recon/cleanup — ops/RUNBOOK.md) ---
# Each was already self-contained (no scribe.py module state crossed the
# boundary); moved out, not rewritten. One-directional: scribe imports
# these, none of them import scribe.
from net_safety import resolves_to_private_ip
from youtube_ingest import is_youtube_url, fetch_youtube_metadata
from image_rehost import rehost_article_image
from prompt_to_article import generate_article_from_prompt
from api_client import APIClient

# --- CONFIGURATION ---
manual_upload_event = threading.Event()
REDIS_PRIORITY_QUEUE_KEY = site.redis_key("priority_uploads")

# Sweep cadence (2026-07-19). Arc ingests ~20 articles/day, which is ~3.75%
# of the M1's analysis capacity at ANY cadence (utilisation = ingest_rate x
# seconds_per_article, independent of how often we sweep). 30m is therefore
# chosen for freshness, not budget — there is ~96% headroom either way.
# Arc runs against the M1; Hunt runs against Spectre (192.168.1.189), so the
# two stacks no longer contend for the same inference host and cadence
# collision is not a concern. See ops/RUNBOOK.md → "scribe cloud-budget knobs".
CYCLE_MINUTES = _ingestion["cycle_minutes"]


def _liveness_ttl_seconds(cycle_minutes: int) -> int:
    """TTL for the <site>:scribe:last_cycle heartbeat key.

    Derived from the current cadence so the key never expires between two
    cycles. 2× cycle gives a full cycle of grace; the 900s floor covers
    stress-test settings of cycle_minutes=0 (SETEX with TTL 0 raises).

    The old hardcoded 900s (15 min) fit only cycle_minutes in [1..12]; once
    Arc moved to 97m and Hunt to 103m the key was expiring ~82 min / ~88 min
    before the next sweep could refresh it, making 'missing' the steady
    state and firing false scribe-liveness alerts every cycle.
    """
    return max(900, cycle_minutes * 60 * 2)


# Deterministic startup offset so Arc and Hunt don't sweep together at boot.
# NOTE: the cycle loop sleeps AFTER work (period = sweep_duration + CYCLE_MINUTES),
# so phase drifts and this is an anti-collision-at-boot measure, NOT true clock
# alignment. That is acceptable because the stacks target different Ollama hosts.
STARTUP_DELAY_SECONDS = _ingestion["startup_delay_s"]  # Arc 900; Hunt 0

# Retention: article age cutoff for the end-of-cycle prune, from site_config
# ([retention].article_hours). Required — load_site_config() already failed
# loud at import if it was missing, so there is no silent-zero fallback here.
RETENTION_HOURS = int(site["retention"]["article_hours"])

# --- Instrumentation Redis keys (slug-derived via site_config.redis_key) ---
STATS_FETCH          = site.redis_key("stats:fetch")
STATS_QUALITY        = site.redis_key("stats:quality")
STATS_RSS            = site.redis_key("stats:rss")
STATS_PUBLISH        = site.redis_key("stats:publish")
STATS_PRIORITY       = site.redis_key("stats:priority")
STATS_SOURCE_LATENCY = site.redis_key("stats:source_latency")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE_URL = f"{site.backend_internal_url}/api"
# Solr host is shared infrastructure (validator invariant); only the core is
# per-site. Derived from the cfg — the SCRIBE_SOLR_URL env override is retired.
SOLR_URL = f"http://localhost:8983/solr/{site.solr_core}/"
REDIS_PASSWORD = os.environ['REDIS_PASSWORD']
SCRIBE_SECRET_KEY = os.environ.get("SCRIBE_SECRET_KEY", "default_secret_for_dev")

# Category-based default images (using existing assets in /public)
DEFAULT_IMAGES = {
    'tech':      'https://arc-codex.com/tech-surveillance.jpg',
    'security':  'https://arc-codex.com/information-warfare.jpg',
    'economics': 'https://arc-codex.com/economic-control.jpg',
    'science':   'https://arc-codex.com/science-medical.jpg',
    'manual':    'https://arc-codex.com/uploads/arc-codex-manual.jpg',
    'default':   'https://arc-codex.com/uploads/arc-codex-default.jpg',
}
DEFAULT_IMAGE_URL = DEFAULT_IMAGES['default']

# Language detection: ISO code → English name. Kept in sync with
# frontend/lib/languages.json so search filters and detection share the map.
_ISO_TO_NAME_PATH = os.path.join(BASE_DIR, 'languages.json')
with open(_ISO_TO_NAME_PATH, 'r', encoding='utf-8') as _f:
    _LANG_LIST = json.load(_f)
ISO_TO_NAME = {entry['code'].lower(): entry['name'] for entry in _LANG_LIST}
# langdetect emits 'zh-cn' / 'zh-tw' which our map has as 'zh'; normalize them.
ISO_TO_NAME['zh-cn'] = ISO_TO_NAME.get('zh', 'Chinese')
ISO_TO_NAME['zh-tw'] = ISO_TO_NAME.get('zh', 'Chinese')


def _inc(key: str, field: str, amount: int = 1) -> None:
    """Increment a Redis hash counter. Fire-and-forget — never raises."""
    try:
        r.hincrby(key, field, amount)
    except Exception:
        pass


@lru_cache(maxsize=256)
def _classify(directive_name='', source_category=''):
    """Classify content into one of 5 canonical categories using keyword matching.

    Returns: 'threat_intelligence', 'tech_surveillance', 'economic_finance',
             'science_health', or 'general'
    """
    combined = f"{directive_name} {source_category}".lower()

    if any(kw in combined for kw in ['biotech', 'biopharma', 'genomic']):
        return 'science_health'

    threat_keywords = [
        'threat', 'malware', 'vulnerab', 'exploit', 'phish', 'spam',
        'cyber', 'osint', 'disinformation', 'counterterror', 'homeland',
        'defense intel', 'defence intel', 'military', 'surveillance',
        'national security', 'breach', 'incident', 'ransomware',
        'adversary', 'zero-day', 'endpoint', 'hunting', 'apt',
        'geopolitical', 'conflict', 'sanction', 'enforcement',
        'law enforcement', 'watchdog', 'oversight', 'civil liberties',
        'hybrid threat', 'information warfare', 'intelligence',
        'security',
    ]
    if any(kw in combined for kw in threat_keywords):
        return 'threat_intelligence'

    tech_keywords = [
        'ai ', 'ai &', 'ai safety', 'ai align', 'ai risk', 'ai policy',
        'artificial intellig', 'machine learning',
        'tech', 'semiconductor', 'chip ', 'chip design',
        'data center', 'data visual', 'telecom', 'wireless',
        'satellite', 'space ', 'space policy', 'networking', 'sdn', 'nfv',
        'enterprise it', 'digital rights', 'internet freedom',
        'big tech', 'electronics', 'automation', 'robotics',
    ]
    if any(kw in combined for kw in tech_keywords):
        return 'tech_surveillance'

    econ_keywords = [
        'financ', 'banking', 'bank ', 'invest', 'market',
        'crypto', 'defi', 'bitcoin', 'nft', 'equity',
        'venture', 'm&a', 'hedge', 'insurance', 'wealth',
        'advisor', 'real estate', 'propert', 'commodit',
        'oil', 'gas', 'energy', 'freight', 'logistics',
        'trade', 'sec filing', 'ipo', 'etf',
        'credit', 'debt', 'loan', 'leverag', 'restructur',
        'bankrupt', 'distress', 'capital', 'fund ',
        'asset', 'money', 'econom', 'business',
        'corporate', 'startup', 'supply chain',
        'retail', 'fashion', 'luxury',
    ]
    if any(kw in combined for kw in econ_keywords):
        return 'economic_finance'

    science_keywords = [
        'science', 'medical', 'health', 'pharma', 'biotech',
        'genomic', 'biopharma', 'nuclear', 'climate',
        'renewable', 'solar', 'wind energy', 'battery',
        'demographic', 'existential risk',
    ]
    if any(kw in combined for kw in science_keywords):
        return 'science_health'

    return 'general'


_CATEGORY_TO_IMAGE_KEY = {
    'threat_intelligence': 'security',
    'tech_surveillance': 'tech',
    'economic_finance': 'economics',
    'science_health': 'science',
    'general': 'default',
}


def get_default_image(directive_name='', source_category=''):
    cat = _classify(directive_name, source_category)
    return DEFAULT_IMAGES[_CATEGORY_TO_IMAGE_KEY[cat]]


def get_canonical_category(directive_name='', source_category=''):
    return _classify(directive_name, source_category)


SOURCES_FILE = os.path.join(site.stack_path, _ingestion["sources_file"])
DIRECTIVES_FILE = os.path.join(BASE_DIR, "directives.json")
PROMPTS_FILE = os.path.join(BASE_DIR, "prompts.yaml")
LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "scribe.log")
UPLOAD_DIR = os.path.join(BASE_DIR, "upload")
PENDING_DIR = os.path.join(UPLOAD_DIR, "pending")
PROCESSING_DIR = os.path.join(UPLOAD_DIR, "processing")
COMPLETED_DIR = os.path.join(UPLOAD_DIR, "completed")
FAILED_DIR = os.path.join(UPLOAD_DIR, "failed")
PENDING_COMMENTS_DIR = os.path.join(UPLOAD_DIR, "pending_comments")

# Ingestion tunables — values live in [ingestion] of the site cfg.
SOURCE_BATCH_SIZE = _ingestion["sources_per_sweep"]
NETWORK_TIMEOUT_SECONDS = _ingestion["fetch_timeout_s"]
FEED_TIMEOUT_SECONDS = _ingestion["feed_timeout_s"]
DOMAIN_COURTESY_DELAY_SECONDS = _ingestion["courtesy_delay_s"]
MIN_ARTICLE_LENGTH = 200

# Sources-corpus floor — see [integrity] in the site cfg. Both bounds default
# to 0 (disabled); arc.cfg sets 1500/2000.
SOURCES_MIN = int(_integrity.get("min_sources", 0) or 0)
SOURCES_WARN = int(_integrity.get("warn_sources", 0) or 0)


def _enforce_sources_floor():
    """Refuse to start on a silently-truncated sources.json.

    A truncated JSONL file parses cleanly line by line, so nothing
    downstream complains when the file is clobbered (see 2026-09-01:
    arc's sources.json dropped 2,310 → 30 in the working tree and
    scribe kept sweeping the fragment for 36 hours before anyone
    noticed). Guard:
        count < SOURCES_MIN  → ERROR + SystemExit (probable clobber)
        count < SOURCES_WARN → WARNING + start (likely deliberate prune)
        count ≥ SOURCES_WARN → INFO with count
    Both bounds default 0 = disabled; sites opt in via [integrity] in
    the cfg.

    Override: ARC_ALLOW_SMALL_SOURCES=1 downgrades the hard refusal to
    a WARNING for that run, so operator experiments (deliberately
    small sources.json) don't need a cfg edit. The override is logged
    at ERROR so a forgotten flag stays visible in the log.
    """
    if SOURCES_MIN <= 0 and SOURCES_WARN <= 0:
        return  # guard disabled
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
    except OSError as e:
        logger.error(
            "❌ [integrity] Cannot read %s (%s) — refusing to start", SOURCES_FILE, e
        )
        raise SystemExit(1)

    override = os.environ.get("ARC_ALLOW_SMALL_SOURCES", "").strip().lower() in (
        "1", "true", "yes", "on",
    )

    if SOURCES_MIN > 0 and count < SOURCES_MIN:
        if override:
            logger.error(
                "🚨 [integrity] sources.json has %d records — BELOW hard floor of %d. "
                "ARC_ALLOW_SMALL_SOURCES=%s override active: continuing anyway. "
                "REMOVE the env var when done experimenting.",
                count, SOURCES_MIN, os.environ.get("ARC_ALLOW_SMALL_SOURCES"),
            )
        else:
            logger.error(
                "❌ [integrity] sources.json has %d records — below hard floor of %d "
                "(likely truncation). Refusing to start. "
                "Set ARC_ALLOW_SMALL_SOURCES=1 to override for one run.",
                count, SOURCES_MIN,
            )
            raise SystemExit(1)
    elif SOURCES_WARN > 0 and count < SOURCES_WARN:
        logger.warning(
            "⚠️  [integrity] sources.json has %d records — below warn threshold %d "
            "(hard floor %d). Continuing.",
            count, SOURCES_WARN, SOURCES_MIN,
        )
    else:
        logger.info(
            "   🛡️  [integrity] sources.json: %d records (floor %d, warn %d)",
            count, SOURCES_MIN, SOURCES_WARN,
        )

# CAPTCHA-boilerplate defense — see arc.cfg [extraction] for the full
# rationale. Trafilatura extracting from a Cloudflare-checkpoint page
# returns the checkpoint's OWN text (a 1,230-1,250 char cluster of
# "checking your browser…" boilerplate), and every fetch/quality gate
# before this treated that as a successful extraction. Downstream: it
# published, hashed, and got NARRATED by Kokoro (~90s of af_heart
# reading "cloudflare-ray-id"). Two-tier gate: normal 200-char floor
# still applies to all extracts; a CAPTCHA-adjacent extract must clear
# a higher bar or gets rejected.
#
# MIN_ARTICLE_CHARS_CAPTCHA_FLOOR is the code-side clamp: even if
# arc.cfg [extraction].min_article_chars_captcha is set below this
# (accidental zero, misconfigured knob), the effective value is raised
# to the floor. The defense must not be silently disable-able.
MIN_ARTICLE_CHARS_CAPTCHA_FLOOR = 800
MIN_ARTICLE_CHARS_CAPTCHA = max(
    MIN_ARTICLE_CHARS_CAPTCHA_FLOOR,
    int(site.get("extraction", "min_article_chars_captcha", 1800)),
)

# HTML markers — presence in the fetched HTML signals a Cloudflare /
# CAPTCHA challenge page. Case-insensitive substring match (kept cheap;
# runs once per fetch). Order: Cloudflare's own markers first (most
# common), then generic CAPTCHA.
_CAPTCHA_HTML_MARKERS = (
    "cloudflare",
    "captcha",
    "attention required",
    "checking your browser",
)

# Boilerplate regex — matches the CHECKPOINT TEXT after extraction. Fires
# even when the HTML markers were stripped, and catches novel wording that
# still contains recognisable checkpoint prose. Anchored to phrases that
# don't naturally occur in legitimate article prose. Case-insensitive.
_CAPTCHA_TEXT_BOILERPLATE = re.compile(
    r"(?i)("
    r"checking your browser"
    r"|verify(?:ing)? you are (?:a )?human"
    r"|please enable javascript.{0,80}continue"
    r"|cloudflare ray id"
    r"|attention required[!:]?\s*\|?\s*cloudflare"
    r"|ddos protection by cloudflare"
    r"|please complete the security check to access"
    r")"
)


def _extracted_looks_like_captcha_boilerplate(article_text, html_content):
    """Return (True, reason) if extract is CAPTCHA boilerplate; else (False, None).

    Two independent checks — either fires:
      1. HTML page has a CAPTCHA marker AND extracted text is under the
         MIN_ARTICLE_CHARS_CAPTCHA floor. Real articles served with a
         CAPTCHA banner (e.g. science.org medical coverage at 6,000+
         chars) clear the floor and are kept.
      2. Extracted text ITSELF contains checkpoint-boilerplate prose,
         regardless of length. Catches cases where the HTML stripped its
         markers or where extraction over-grabbed the challenge text.
    """
    text_lower = article_text.lower()
    html_lower = (html_content or "").lower()
    has_captcha_html = any(m in html_lower for m in _CAPTCHA_HTML_MARKERS)
    if has_captcha_html and len(article_text) < MIN_ARTICLE_CHARS_CAPTCHA:
        return (True, f"captcha_boilerplate ({len(article_text)} chars, CAPTCHA in HTML)")
    if _CAPTCHA_TEXT_BOILERPLATE.search(text_lower):
        return (True, "captcha_boilerplate (checkpoint prose in extract)")
    return (False, None)


RECENTLY_PUBLISHED_MEMORY = 10
MAX_CONCURRENT_SCRAPERS = _ingestion["concurrent_scrapers"]
MAX_CONCURRENT_ANALYZERS = _ingestion["concurrent_preproc"]
                               # Local-only NLP concurrency (spaCy/VADER via
                               # /api/pre_analyze). Flask semaphore caps
                               # actual parallelism at 2 — extra threads
                               # hit 429 (1s wait) then fallback. No cloud
                               # impact. See ops/RUNBOOK.md.

CATEGORY_TO_DIRECTIVE = {
    'Health & Medicine':            'Healthcare and Public Health',
    'Academic Journals':            'Peer-Reviewed Science and Research',
    'Cybersecurity & Threat Intel': 'Active Threat Campaigns',
    'Intelligence & Security':      'Intelligence Community Operations',
    'Geopolitics & World Affairs':  'Geopolitics and International Relations',
    'Finance & Economics':          'Economic Policy and Financial Markets',
    'Governance & Policy':          'Government Actions and Political Discourse',
    'Technology & AI':              'AI Developments and Discourse',
    'Science & Environment':        'Climate and Environment',
    'Agriculture & Food':           'US Farming and Agriculture',
}

FILE_LOCK = threading.Lock()

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

# --- INITIALIZATION ---
log_formatter = logging.Formatter('%(asctime)s - [SCRIBE v53.0] - %(levelname)s - %(message)s')
log_handler = logging.FileHandler(LOG_FILE)
log_handler.setFormatter(log_formatter)
logger = logging.getLogger('scribe')
if logger.hasHandlers():
    logger.handlers.clear()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

# Load prompts from YAML
PROMPTS = {}
try:
    with open(PROMPTS_FILE, 'r') as f:
        PROMPTS = yaml.safe_load(f)
    logger.info(f"✅ Successfully loaded prompts from {PROMPTS_FILE}")
except Exception as e:
    logger.critical(f"🔥 PROMPTS FAILED TO LOAD: {e}")
    logger.critical("Analysis will not work without prompts.yaml!")

try:
    logger.info("Connecting to Redis...")
    r = redis.Redis(decode_responses=True, password=REDIS_PASSWORD, db=site.redis_db)
    # Boot-adjacent readiness gate: scribe starts as part of arc-stack at
    # boot, and although the unit orders After=redis-server.service,
    # systemd flips "started" the moment redis-server forks — before the
    # dataset finishes loading. Without this the first PING here would
    # raise BusyLoadingError and the CRITICAL branch below would kill
    # scribe; the process would then rely on the arc.sh restart loop to
    # eventually catch a ready Redis. Replace that with an in-process
    # retry — same 60s/2s shape used by sync_intel.sh. See
    # redis_readiness for the full argument.
    from redis_readiness import wait_for_redis
    wait_for_redis(r, log=logger)
    logger.info("Redis connection successful.")
    ensure_stream_group(r)
except redis.exceptions.ConnectionError as e:
    logger.critical(f"🔥 SCRIBE CRITICAL FAILURE: Could not connect to Redis. Shutting down. Error: {e}")
    exit()

# Connect to Solr
try:
    solr = pysolr.Solr(SOLR_URL)
    solr.ping()
    logger.info("Solr connection established.")
except Exception as e:
    solr = None
    logger.warning(f"Solr connection failed - continuing without indexing: {e}")


# --- BACKGROUND ANALYSIS EXECUTOR ---
# Sentinel and counter-analyst are slow (30s–3min on fallback models).
# Running them in a background thread lets the main loop keep processing
# priority queue items and RSS cycles without waiting.
#
# THREAD SAFETY RULES — read before touching this:
#   1. Each background job creates its OWN Redis connection (r_bg).
#      Never pass the module-level `r` into a background thread.
#   2. Background threads never read or write `recently_published`,
#      `solr`, or any other shared main-loop state.
#   3. publish_analysis() takes r as an argument — always pass r_bg.
#   4. Ollama calls (run_sentinel_analysis, run_counter_analyst) are
#      stateless — safe to call from any thread.
#   5. background_workers (cfg [pipeline], 2): allows sentinel + counter-
#      analyst to overlap across two articles without overwhelming the M1.

_analysis_executor = ThreadPoolExecutor(
    max_workers=site["pipeline"]["background_workers"],
    thread_name_prefix=f"{site.slug}-analysis",
)


def _run_analysis_background(article_id: str, text_for_analysis: str) -> None:
    """
    Run sentinel forensic pass + counter-analyst in a background thread.
    Creates its own Redis connection — never touches main-loop state.
    Safe to call from ThreadPoolExecutor.
    """
    try:
        r_bg = redis.Redis(decode_responses=True, password=REDIS_PASSWORD, db=site.redis_db)
    except Exception as e:
        logger.error(f"🔬 Background analysis: Redis connect failed for {article_id}: {e}")
        return

    # Sentinel
    try:
        sentinel_data = run_sentinel_analysis(text_for_analysis)
        if sentinel_data:
            publish_analysis(r_bg, article_id, 'sentinel', json.dumps(sentinel_data))
            logger.info(f"🛡️  [bg] Sentinel published for {article_id} — {sentinel_data.get('assessment', '?')}")
    except Exception as e:
        logger.warning(f"🛡️  [bg] Sentinel failed (non-fatal) for {article_id}: {e}")

    # Counter-analyst
    try:
        # run_counter_analyst writes directly to Redis — pass r_bg via monkey-patch
        # is not needed: run_counter_analyst uses the module-level r internally.
        # Safe because hset/rpush on separate keys are atomic in Redis.
        run_counter_analyst(text_for_analysis, article_id)
        logger.info(f"🤖 [bg] Counter-analyst posted for {article_id}")
    except Exception as e:
        logger.warning(f"🤖 [bg] Counter-analyst failed (non-fatal) for {article_id}: {e}")

    try:
        r_bg.close()
    except Exception:
        pass


# --- ARTICLE AUDIO ---
# English stories only. Non-English stories get nothing: narrating Spanish
# text with an en-US voice produces gibberish, and translating first is a
# separate piece of work that does not exist yet.
#
# Synthesis runs locally on resolute under Kokoro, in the dedicated venv at
# AUDIO_KOKORO_PYTHON ([[kokoro-relocation]], 2026-08-20 — moved off the M1;
# see the AUDIO_* block near SCRAPED_IMAGE_DIR for the host decision, the
# bench numbers behind it, and where the memory floor comes from).

# One process for the whole article: importing torch and loading the
# pipeline costs ~5s, and that is per-process, not per-chunk. Unlike cc.py,
# which keeps its chunks as separate files to report progress against, this
# joins them into one WAV — a single file comes back and a single ffmpeg
# pass encodes it. Runs as a local subprocess now rather than over ssh, but
# the program itself is unchanged: it only ever looked at argv and its own
# staging directory, never at what host it was on.
_KOKORO_SYNTH = '''\
import json, os, sys

staging, voice, speed, rate = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
with open(os.path.join(staging, "chunks.json"), encoding="utf-8") as f:
    chunks = json.load(f)

from kokoro import KPipeline
import numpy as np
import soundfile as sf

pipe = KPipeline(lang_code="a")
parts = []
for idx, text in enumerate(chunks, start=1):
    spoken = [audio for _, _, audio in pipe(text, voice=voice, speed=speed)]
    if not spoken:
        sys.exit("chunk %d produced no audio" % idx)
    parts.extend(spoken)
    print("PROGRESS %d/%d" % (idx, len(chunks)), file=sys.stderr, flush=True)

sf.write(os.path.join(staging, "article.wav"), np.concatenate(parts), rate)
'''

def kokoro_preflight() -> tuple[str, int] | None:
    """Return None if Kokoro may run, else (reason, log_level) for the caller.

    Local as of 2026-08-20 ([[kokoro-relocation]]): no ssh, no vm_stat probe,
    no Ollama-residency check against a remote host. That check existed
    because Kokoro used to share a host (the M1) with Arc's own inference
    calls, so a resident model there was a real collision to detect. Arc and
    Hunt are supposed to reach Ollama over HTTP on other boxes, not this one
    — but resolute does have its own Ollama install, and a known, separate,
    still-unfixed bug ([[council-ollama-host-misrouted]]) points council
    calls at localhost:11434 here instead of the fleet. When that fires it
    pulls ~7.8 GB RSS on this box with no warning, which is exactly the kind
    of collision AUDIO_MIN_FREE_MB has to survive — confirmed live during
    the 2026-08-20 verification narration, see the AUDIO_* block. Fixing the
    misroute is out of scope here; the psutil check below is what actually
    protects Kokoro from it either way. Every branch still yields a
    sentence: a silent skip is not diagnosable.
    """
    if not os.access(AUDIO_KOKORO_PYTHON, os.X_OK):
        return f"no kokoro venv at {AUDIO_KOKORO_PYTHON}", logging.WARNING

    available_mb = psutil.virtual_memory().available / (1024 * 1024)
    if available_mb < AUDIO_MIN_FREE_MB:
        return f"resolute has {available_mb:.0f} MB available, needs {AUDIO_MIN_FREE_MB}", logging.INFO
    return None


def _chunk_text(text: str) -> list:
    """Split an article body on sentence boundaries into TTS-sized pieces.

    AUDIO_MAX_CHARS is read in the body rather than taken as a default
    argument: the AUDIO_* block lives further down the file with the other
    publish-time constants, and a default would be evaluated at def time.
    """
    max_chars = AUDIO_MAX_CHARS
    normalized = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]

    chunks = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            # Flush first: appending the split pieces ahead of `current`
            # would put the audio out of order.
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i:i + max_chars])
            continue

        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence

    if current:
        chunks.append(current)
    return chunks


def synthesize_article_audio(article_id: str, text: str) -> str | None:
    """Narrate `text` to frontend/public/uploads/audio/{article_id}.mp3.

    Returns the relative serving path, or None on any failure — narration is
    a nice-to-have and must never affect whether a story publishes.

    Assumes kokoro_preflight() has already passed; the caller runs it, so
    that a refusal reads as a deferral in the log while a failure here reads
    as a failure. The preflight cannot cover everything even so — a second
    process can eat the headroom between the check and the run — and every
    one of those lands here as None and a silent story.

    Encodes to a temp file and renames into place, so a crashed or timed-out
    run cannot leave a truncated mp3 at the path the field will point at.
    rename(2) within one filesystem is atomic: readers see the whole file or
    no file.
    """
    text = (text or '').strip()
    if len(text) < AUDIO_MIN_CHARS:
        logger.info(f"🔊 Audio skipped — too short ({len(text)} chars) for {article_id}")
        return None

    if not shutil.which("ffmpeg"):
        logger.warning("🔊 Audio skipped — ffmpeg not on PATH, needed to encode Kokoro's WAV")
        return None

    final_path = os.path.join(AUDIO_DIR, f"{article_id}.mp3")
    temp_path = f"{final_path}.partial"
    chunks = _chunk_text(text)
    started = time.perf_counter()

    workdir = None
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix=f"arc-audio-{article_id[:12]}-")

        manifest = os.path.join(workdir, "chunks.json")
        program = os.path.join(workdir, "synth.py")
        with open(manifest, "w", encoding="utf-8") as f:
            json.dump(chunks, f)
        with open(program, "w", encoding="utf-8") as f:
            f.write(_KOKORO_SYNTH)

        logger.info(f"🔊 Narrating {article_id}: {len(text)} chars in {len(chunks)} chunk(s), "
                    f"kokoro voice {AUDIO_VOICE} at {AUDIO_SPEED}x")
        synth = subprocess.run(
            [AUDIO_KOKORO_PYTHON, program, workdir,
             AUDIO_VOICE, str(AUDIO_SPEED), str(AUDIO_SAMPLE_RATE)],
            capture_output=True, text=True, timeout=AUDIO_TIMEOUT_SECONDS)
        if synth.returncode != 0:
            noise = [line for line in synth.stderr.strip().splitlines()
                     if line and not line.startswith("PROGRESS ")
                     and "Warning" not in line and "warn" not in line]
            logger.warning(f"🔊 Audio failed — synthesis for {article_id}: "
                           f"{noise[-1] if noise else 'no detail'}")
            return None

        wav_path = os.path.join(workdir, "article.wav")
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            logger.warning(f"🔊 Audio came back empty for {article_id}")
            return None

        # -f mp3 is not optional: the output is written to a .partial path,
        # and ffmpeg picks its muxer from the extension unless told.
        encode = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav_path,
             "-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1", "-f", "mp3", temp_path],
            capture_output=True, text=True)
        if encode.returncode != 0:
            logger.warning(f"🔊 Audio failed — mp3 encode for {article_id}: "
                           f"{encode.stderr.strip()}")
            return None
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            logger.warning(f"🔊 Audio encoded to nothing for {article_id}")
            return None

        os.replace(temp_path, final_path)
        duration = time.perf_counter() - started
        size_kb = os.path.getsize(final_path) / 1024
        logger.info(
            f"🔊 Audio written for {article_id}: {len(text)} chars → "
            f"{size_kb:.0f} KB in {duration:.1f}s"
        )
        return f"/uploads/audio/{article_id}.mp3"

    except subprocess.TimeoutExpired:
        # subprocess.run kills its child directly on timeout, so there is no
        # orphan to chase here the way there was over ssh — killing the
        # local end used to leave the remote python running on someone
        # else's box, which needed a separate pkill to clean up.
        logger.warning(f"🔊 Audio timed out after {AUDIO_TIMEOUT_SECONDS}s for {article_id}")
        return None
    except Exception as e:
        logger.warning(f"🔊 Audio failed ({type(e).__name__}) for {article_id}: {e}")
        return None
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# Scribe's own audio pass (_run_audio_pass / run_audio_pass /
# _find_silent_article / _audio_scan_window) was RETIRED 2026-08-27. It never
# took the arc:audio:active Redis mutex — only a process-local threading.Lock
# — so it had no exclusion against audio_backfill.py's daemon at all. The two
# independently reimplemented "pick the newest silent article" and could (did)
# target the same article at once, running two concurrent Kokoro subprocesses
# for it and blowing each other's AUDIO_TIMEOUT_SECONDS budget. See
# ops/RUNBOOK.md 2026-08-27 for the incident and the merge decision.
# audio_backfill.py now owns 100% of narration, including through the
# weekday peak-hour window (throttled there, not idle — see its
# peak_throttle_minutes handling). synthesize_article_audio() and
# kokoro_preflight() below are unchanged and still the only synthesis path;
# audio_backfill.py imports this module and calls them directly.


# --- APPEARANCE ENHANCEMENT FUNCTIONS ---

@lru_cache(maxsize=512)
def beautify_source_name(source_name, url):
    """Convert raw RSS feed names into clean, professional source labels"""
    domain_map = {
        'nytimes.com': 'New York Times',
        'washingtonpost.com': 'Washington Post',
        'apnews.com': 'Associated Press',
        'reuters.com': 'Reuters',
        'bbc.co.uk': 'BBC News',
        'bbc.com': 'BBC News',
        'theguardian.com': 'The Guardian',
        'cnn.com': 'CNN',
        'axios.com': 'Axios',
        'bloomberg.com': 'Bloomberg',
        'wsj.com': 'Wall Street Journal',
        'csoonline.com': 'CSO Online',
    }

    try:
        domain = urlparse(url).netloc.replace('www.', '')
        if domain in domain_map:
            return domain_map[domain]
    except Exception:
        pass

    cleaned = source_name
    cleaned = re.sub(r'\s*-\s*RSS.*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\|\s*RSS.*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\(RSS\).*', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    return cleaned if cleaned else source_name


def clean_article_metadata(title, html_content=None):
    """Clean and enhance article metadata for professional display"""
    try:
        cleaned_title = BeautifulSoup(unescape(title), 'html.parser').get_text()
    except Exception:
        cleaned_title = unescape(title)

    suffixes = [
        r'\s*[-|–—]\s*.{1,40}$',
        r'\s*\|\s*.{1,40}$',
    ]
    for pattern in suffixes:
        cleaned_title = re.sub(pattern, '', cleaned_title)

    emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F]', cleaned_title))
    if emoji_count > 3:
        cleaned_title = re.sub(r'[\U0001F600-\U0001F64F]', '', cleaned_title)

    if sum(1 for c in cleaned_title if c.isupper()) / max(len(cleaned_title), 1) > 0.7:
        cleaned_title = cleaned_title.title()

    cleaned_title = ' '.join(cleaned_title.split())

    description = None
    reading_time = None

    if html_content:
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            desc_tags = [
                soup.find('meta', {'name': 'description'}),
                soup.find('meta', {'property': 'og:description'}),
                soup.find('meta', {'name': 'twitter:description'})
            ]
            for tag in desc_tags:
                if tag and tag.get('content'):
                    description = tag.get('content').strip()
                    if len(description) > 50:
                        break
            text_length = len(soup.get_text())
            reading_time = max(1, text_length // 1000)
        except Exception:
            pass

    return {
        'title': cleaned_title,
        'description': description,
        'reading_time': reading_time
    }


def extract_image_url_enhanced(html_content, url):
    """Multi-strategy image extraction prioritizing quality"""
    soup = BeautifulSoup(html_content, 'html.parser')
    candidates = []

    meta_selectors = [
        ('meta', {'property': 'og:image'}),
        ('meta', {'name': 'twitter:image'}),
        ('meta', {'property': 'og:image:url'}),
        ('meta', {'name': 'twitter:image:src'}),
    ]
    for tag_name, attrs in meta_selectors:
        tag = soup.find(tag_name, attrs)
        if tag:
            img_url = tag.get('content') or tag.get('href')
            if img_url and len(img_url) > 10:
                candidates.append(('meta', img_url, 100))

    hero_selectors = [
        'article img', '.article-image img', '.hero-image img',
        '.featured-image img', '.lead-image img', 'picture source',
        '[data-testid="hero-image"]', '.ArticleImage img'
    ]
    for selector in hero_selectors:
        imgs = soup.select(selector)
        for img in imgs[:3]:
            src = img.get('srcset', img.get('src', ''))
            if src and 'placeholder' not in src.lower() and 'logo' not in src.lower():
                if 'srcset' in img.attrs:
                    srcset_urls = [s.strip().split()[0] for s in src.split(',') if s.strip().split()]
                    if srcset_urls:
                        src = srcset_urls[-1]
                candidates.append(('hero', src, 80))

    all_imgs = soup.find_all('img', src=True)
    for img in all_imgs:
        src = img.get('src', '')
        width = img.get('width', 0)
        height = img.get('height', 0)

        try:
            if width and height and (int(width) < 300 or int(height) < 200):
                continue
        except Exception:
            pass

        skip_patterns = ['logo', 'icon', 'avatar', 'placeholder', 'loading', 'pixel', 'ad', 'banner']
        if any(pattern in src.lower() for pattern in skip_patterns):
            continue

        candidates.append(('content', src, 50))

    if candidates:
        candidates.sort(key=lambda x: x[2], reverse=True)
        best_img = candidates[0][1]

        if best_img.startswith('//'):
            best_img = 'https:' + best_img
        elif best_img.startswith('/'):
            best_img = urljoin(url, best_img)

        logger.debug(f"Selected image from {len(candidates)} candidates: {best_img[:80]}")
        return best_img

    return DEFAULT_IMAGE_URL


# --- Image self-hosting -----------------------------------------------------
# Scraped hero images are re-hosted at publish time: fetched once, normalized
# to 16:9 (matches the frontend card container), saved under
# frontend/public/uploads/scraped/ (served by Caddy's /uploads/* file_server —
# scribe must run on the host, or mount that path if ever moved into Docker).
# The original URL is kept in image_source_url for provenance. ~3% of scraped
# sources 403 on hotlink (measured 2026-07-02) and URLs rot over time.
#
# The actual fetch/resize/save logic (rehost_article_image) moved to
# image_rehost.py 2026-08-27 (scribe recon/cleanup — ops/RUNBOOK.md); only
# this path constant, which is specific to where THIS stack's frontend
# lives, stays here.
SCRAPED_IMAGE_DIR = os.path.join(os.path.dirname(BASE_DIR), 'frontend', 'public', 'uploads', 'scraped')

# --- Article audio ----------------------------------------------------------
# English stories are narrated to an mp3 stored beside the scraped heroes,
# under the same /uploads/* file_server Caddy already serves (so scribe must
# run on the host, same constraint as the rehosted images above).
#
# Synthesis is Kokoro, run locally in a dedicated venv ([[kokoro-relocation]],
# 2026-08-20). It used to run on the M1 over ssh, exactly as
# /home/www/lecture_pipeline/cc.py still drives its own M1 fallback — that
# host was Arc's ollama box, which made narration a guest there and nothing
# more, and the preflight existed mainly to detect a resident model on the
# host it shared with Arc's own inference calls. resolute is not *meant* to
# be an inference host — Arc and Hunt are supposed to reach Ollama over HTTP
# on other boxes — but it does run its own Ollama install, and
# [[council-ollama-host-misrouted]] (known, separate, unfixed) can land
# council calls on localhost:11434 here instead. So there's no ssh round
# trip, but there is still a real memory collision to guard against — see
# AUDIO_MIN_FREE_MB below for what that looked like live, during the
# 2026-08-20 verification narration. A refusal is still a skip rather than
# a failure: nothing falls back, nothing retries, nothing queues. The audio
# pass simply looks at the feed again next cycle and narrates whatever is
# still silent.
#
# Two hosts were weighed for where synthesis should live: resolute (local,
# working Python 3.12 venv already) and Spectre (Hunt's other inference
# box). Spectre benched ~20% faster on raw synthesis wall time — 60.3s vs
# 75.0s for the same 2019-char article at af_heart/0.95x — but it would have
# reintroduced the exact ssh/scp coupling this move removes, on a box with
# effectively no memory slack while a model is resident (it OOM-killed
# Hunt's own ollama.service mid-bench-setup, see [[spectre-reimage]]) and
# needing a bespoke non-system Python 3.12 (deadsnakes-equivalent via `uv`,
# since Spectre's system Python is 3.14 and kokoro 0.9.4 requires <3.13).
# A 20% wall-time edge doesn't clear "speed has to win by a lot" against
# that. resolute keeps the wav off the network entirely — ffmpeg already
# encodes on this box, so there is now exactly one process boundary between
# article text and finished mp3, not three (stage, synth, retrieve).
#
# One field carries the result: audio_url on the article hash. Its presence is
# the whole contract — if it is set there is audio, if it is absent there is
# none. Nothing here writes original_text, title, or source_lang.
AUDIO_DIR = os.path.join(os.path.dirname(BASE_DIR), 'frontend', 'public', 'uploads', 'audio')
AUDIO_KOKORO_PYTHON = "/home/www/lecture_pipeline/.kokoro-venv/bin/python"  # provisioned by lecture_pipeline/scripts
AUDIO_VOICE = "af_heart"
AUDIO_SPEED = 0.95
AUDIO_SAMPLE_RATE = 24000               # Kokoro's native output rate
AUDIO_MIN_CHARS = 100                   # matches the sentinel/counter-analyst skip threshold
AUDIO_MAX_CHARS = 3500                  # per-request bound; chunks split on sentence boundaries
AUDIO_TIMEOUT_SECONDS = 600             # a long feature piece still finishes well inside this

# Preflight budget. Superseded history: this floor used to gate the M1's
# free memory over ssh (3584 MB, then 1024 MB post-KEEP_ALIVE=-1 — see git
# blame on this line from before 2026-08-20 for that saga). None of it
# applies to a local check.
#
# Bench (2026-08-20, this box, real 2019-char article from the live feed):
# 75.0 s wall, peak RSS 1940 MB, 324% CPU, synthesis-only realtime factor
# 1.78x. 2600 MB is peak plus ~660 MB (~34%) headroom, sized to absorb
# variance across article lengths and whatever else resolute is doing.
#
# That headroom got a real test sooner than expected: during the first live
# narration after this change went in (2026-08-20, article 72548662,
# 4511 chars), [[council-ollama-host-misrouted]] independently fired mid-run
# — resolute's own Ollama loaded gemma4:e2b locally (~7.8 GB RSS) while
# Kokoro was already synthesizing. Available memory, normally 10-12 GB on
# this box, fell to ~2.2 GB at the lowest sample before the model's
# keep-alive expired. Narration still finished clean (181s, correct
# duration, decodes with zero errors) because the preflight check happens
# once before the subprocess starts, not during it — but had the two events
# swapped order, 2600 MB is what would have made the second one defer
# instead of stack on the first. Do not read this as "several GB free is
# typical and this rarely gates" — it means this floor is doing real work
# against a specific, known, still-unfixed collision, not just noise.
AUDIO_MIN_FREE_MB = 2600

class _SSRFBlocked(Exception):
    """Raised when a fetch target fails the SSRF guard."""


def _get_with_ssrf_guard(session, url, timeout, max_redirects=5):
    """session.get() with manual redirect chasing so every hop passes
    net_safety.resolves_to_private_ip. Rejects non-http(s) schemes at every
    hop. Raises _SSRFBlocked on a rejected target; propagates network
    errors unchanged.

    Closes the guard against a crafted feed/submit URL that 302-redirects
    to internal targets (Ollama, Solr, the M1 at 192.168.1.185, AWS/GCE
    metadata endpoints).
    """
    current = url
    for hop in range(max_redirects + 1):
        parsed = urlparse(current)
        if parsed.scheme not in ('http', 'https'):
            raise _SSRFBlocked(f"non-http(s) scheme at hop {hop}: {parsed.scheme!r}")
        if resolves_to_private_ip(current):
            raise _SSRFBlocked(f"private/loopback/reserved address at hop {hop}: {current}")
        resp = session.get(current, timeout=timeout, allow_redirects=False)
        loc = resp.headers.get('location')
        if 300 <= resp.status_code < 400 and loc:
            current = urljoin(current, loc)
            continue
        return resp
    raise _SSRFBlocked(f"too many redirects (>{max_redirects})")


def assess_content_quality(article_text, html_content=None):
    """Detect low-quality/problematic content before publishing"""
    text_lower = article_text.lower()

    paywall_indicators = [
        'subscribe to continue reading',
        'this article is for subscribers',
        'become a member to read',
        'sign in to view',
        'register to continue'
    ]
    if any(ind in text_lower for ind in paywall_indicators):
        return (False, "paywall_detected")

    if len(article_text) < MIN_ARTICLE_LENGTH:
        return (False, f"too_short ({len(article_text)} chars)")

    # CAPTCHA-boilerplate gate: fires when the extract length pretends to
    # be a real article but the HTML shows a Cloudflare/CAPTCHA challenge,
    # or when the text itself carries checkpoint prose. See constants
    # above the function. Two-tier by design — playwright_tier3.py has
    # its own MIN_ARTICLE_CHARS_CAPTCHA gate at the fetch layer that
    # saves the browser round-trip; this is the belt to that braces,
    # covering the simple/stealth (non-Playwright) fetch paths whose
    # entry point back into scribe is `article_data['html_content']`
    # threaded to this call at the ingestion-loop site.
    is_captcha, captcha_reason = _extracted_looks_like_captcha_boilerplate(
        article_text, html_content
    )
    if is_captcha:
        return (False, captcha_reason)

    listicle_pattern = r'\d+\s+(things|ways|reasons|facts|tips|tricks|secrets)\s+(?:you|that)'
    if re.search(listicle_pattern, text_lower) and len(article_text) < 800:
        return (False, "low_quality_listicle")

    auto_gen_markers = [
        'this article was automatically generated',
        'powered by ai',
        'generated by machine',
    ]
    if any(marker in text_lower for marker in auto_gen_markers):
        return (False, "auto_generated")

    return (True, "acceptable")


def detect_language(text: str) -> str:
    """Detect language of article text. Returns full English name from
    languages.json. Falls back to 'Unknown' if detection fails or text
    is too short."""
    if not text or len(text.strip()) < 50:
        return 'Unknown'
    try:
        code = detect(text[:1000]).lower()
        return ISO_TO_NAME.get(code, ISO_TO_NAME.get(code.split('-')[0], 'Unknown'))
    except LangDetectException:
        return 'Unknown'


# --- CONTENT FETCHING ---
# Playwright removed in v51.0 — no browser on Z230 (radeon GPU crash risk + fd exhaustion)
# Strategy: requests tier 1 (simple) → tier 2 (stealth headers) → skip

def detect_and_decode_content(response):
    """Handle compressed and encoded content intelligently"""
    content = response.content

    if len(content) > 0 and content[:3] == b'\x1f\x8b\x08':
        try:
            content = gzip.decompress(content)
        except Exception:
            pass
    elif len(content) > 0 and content[:2] == b'\x78\x9c':
        try:
            content = zlib.decompress(content)
        except Exception:
            pass

    try:
        result = charset_normalizer.detect(content)
        if result['encoding'] and result['confidence'] > 0.8:
            decoded = content.decode(result['encoding'])
            if any(tag in decoded.lower() for tag in ['<html', '<body', '<div', '<article']):
                return decoded
    except Exception:
        pass

    for encoding in ['utf-8', 'cp1252', 'latin-1', 'windows-1252']:
        try:
            decoded = content.decode(encoding)
            if any(tag in decoded.lower() for tag in ['<html', '<body', '<div', '<article']):
                return decoded
        except UnicodeDecodeError:
            continue

    return content.decode('utf-8', errors='replace')


@lru_cache(maxsize=256)
def is_problematic_news_site(url):
    """Sites known to have aggressive bot detection"""
    problematic_domains = [
        'apnews.com', 'ap.org', 'reuters.com', 'bloomberg.com',
        'wsj.com', 'nytimes.com', 'axios.com',
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in problematic_domains)


def extract_with_beautifulsoup(html_content, url):
    """Enhanced BeautifulSoup extraction with site-specific selectors"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'advertisement', 'ads']):
            element.decompose()

        article_text = ""
        selectors = [
            'article', '.article-content', '.article-body',
            '.story-body', '.post-content', '.entry-content',
            '.content', '[role="main"]', '.main-content'
        ]

        if 'apnews.com' in url:
            selectors = ['div[data-module="ArticleBody"]', '.RichTextStoryBody', '.Article-content'] + selectors
        elif 'exblog.jp' in url:
            selectors = ['.entry-content', '.entry-body', '.post-body'] + selectors
        elif 'axios.com' in url:
            selectors = ['article', '.ArticleBody', '[data-testid="article-body"]'] + selectors

        for selector in selectors:
            content_div = soup.select_one(selector)
            if content_div:
                paragraphs = content_div.find_all(['p', 'div'], recursive=True)
                texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                article_text = '\n\n'.join(texts)
                if len(article_text) > MIN_ARTICLE_LENGTH:
                    break

        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            paragraphs = soup.find_all('p')
            meaningful_paragraphs = [
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 30 and
                not any(skip in p.get_text(strip=True).lower() for skip in [
                    'cookie', 'subscribe', 'newsletter', 'advertisement'
                ])
            ]
            article_text = '\n\n'.join(meaningful_paragraphs)

        return article_text if len(article_text) > MIN_ARTICLE_LENGTH else None
    except Exception as e:
        logger.error(f"BeautifulSoup extraction failed: {e}")
        # Last resort — model returned prose instead of JSON
    if len(cleaned) > 50:
        return {
            "synthetic_confidence": 0.0,
            "assessment": "UNCERTAIN",
            "indicators": [],
            "human_signals": [],
            "summary": "Sentinel analysis incomplete — fallback model returned prose instead of JSON."
        }
    return None


# Same-domain request spacing. A feed's top entries share a domain and are
# fetched by up to MAX_CONCURRENT_SCRAPERS threads, x2 tiers — observed as
# 6 requests inside one second at medicalxpress.com/phys.org, which got the
# scraper 429-banned. Slot reservation happens under the lock so concurrent
# threads queue up rather than stampede.
_domain_last_fetch = {}
_domain_last_fetch_lock = threading.Lock()


def _domain_courtesy_wait(url):
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return
    if not domain:
        return
    while True:
        with _domain_last_fetch_lock:
            now = time.monotonic()
            last = _domain_last_fetch.get(domain)
            if last is None or now - last >= DOMAIN_COURTESY_DELAY_SECONDS:
                _domain_last_fetch[domain] = now
                return
            wait = DOMAIN_COURTESY_DELAY_SECONDS - (now - last)
        time.sleep(wait)


# Negative cache for dead article URLs. Failed fetches otherwise retry every
# cycle forever (processed_hashes only dedups on publish) — bloomberg.com alone
# burned ~23 fetch-pairs/day on permanent 403s. TTLs, not a blacklist: a source
# that comes back to life gets retried once the marker expires. 404 gets the
# longer TTL because removed pages rarely return; 403/503 can be a lifted
# bot-wall or a recovered server.
DEAD_URL_TTLS = {403: 3 * 86400, 503: 3 * 86400, 404: 7 * 86400}

_fetch_status = threading.local()


def _dead_url_key(url):
    return f"scribe:dead_url:{hashlib.sha256(url.encode()).hexdigest()[:16]}"


def _is_dead_url(url):
    try:
        status = r.get(_dead_url_key(url))
    except Exception:
        return False
    if status:
        logger.info(f"⏭️  Skipping {url} — negative-cached (HTTP {status})")
        return True
    return False


def _mark_dead_url(url, status_code):
    ttl = DEAD_URL_TTLS.get(status_code)
    if not ttl:
        return
    try:
        r.setex(_dead_url_key(url), ttl, str(status_code))
        logger.info(f"🪦 Negative-cached {url} for {ttl // 86400}d (HTTP {status_code})")
    except Exception:
        pass


# 403 log-suppression key — separate from the dead_url negative cache on
# purpose. dead_url is set only AFTER all three fetch tiers fail (see
# _mark_dead_url call site in fetch_article_data), which preserves the
# tier-fallback: a URL that 403s at tier-1 still gets tier-2 stealth and
# tier-3 playwright next cycle. This key is set the first time we LOG an
# INFO 403 for a URL; subsequent hits in its 3-day TTL downgrade to
# DEBUG. Independent from tier-fallback — only touches log verbosity.
#
# Motivating case: 7-week audit found 4,566 "🚫 403" lines from DFRLab
# alone (medium.com/dfrlab article URLs, source RSS at
# medium.com/feed/dfrlab). Repeat URLs across weekly RSS refreshes
# stack up; per-source suppression via a config list would over-
# suppress medium.com (dozens of other sources on the same domain), so
# per-URL dedup via this key was Ross's chosen shape. First failure
# per URL still logs at INFO so a genuinely new 403 stays visible.
_LOG_403_TTL_SECONDS = 3 * 86400


def _log_403_key(url):
    return f"scribe:403_logged:{hashlib.sha256(url.encode()).hexdigest()[:16]}"


def _should_log_403_info(url):
    """SET NX EX: True on the first call for this URL in the TTL window,
    False on repeats. Redis-atomic — safe across concurrent fetchers.
    Fail-open (returns True) if Redis is unavailable, so we don't hide
    403s on a Redis outage."""
    try:
        # nx=True → set only if not present; returns True on success.
        return bool(r.set(_log_403_key(url), "1", ex=_LOG_403_TTL_SECONDS, nx=True))
    except Exception:
        return True


def _make_session(headers, referer=None):
    """Build a requests Session with appropriate headers."""
    session = requests.Session()
    session.headers.update(headers)
    if referer:
        session.headers.update({'Referer': referer, 'Origin': referer.rstrip('/')})
    return session


def fetch_with_requests(url, headers, stealth=False):
    """
    Fetch a URL using requests only. No browser, no Playwright.

    stealth=False: plain request
    stealth=True:  adds site-specific referer + sec-fetch headers
    Returns dict with text/image_url/html_content, or None.
    """
    session = None
    _fetch_status.code = None
    _domain_courtesy_wait(url)
    try:
        referer = None
        if stealth:
            parsed = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
            extra = {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
            }
            headers = {**headers, **extra}

        session = _make_session(headers, referer=referer)
        try:
            response = _get_with_ssrf_guard(session, url, NETWORK_TIMEOUT_SECONDS)
        except _SSRFBlocked as e:
            logger.warning(f"🛡️  SSRF guard blocked {url}: {e}")
            return None

        if response.status_code == 403:
            _fetch_status.code = 403
            tier = "stealth " if stealth else ""
            # First 403 for this URL in the 3-day TTL logs at INFO
            # (genuine new failure stays visible); repeats within the
            # window silently downgrade to DEBUG. See _should_log_403_info
            # above the function definitions in this file for the
            # rationale — same TTL as the dead_url cache, but a separate
            # key so tier-fallback logic stays untouched. Within a single
            # fetch_article_data invocation this also collapses the
            # simple+stealth log-line pair to one INFO + one DEBUG.
            if _should_log_403_info(url):
                logger.info(f"🚫 403 on {tier}request for {url} — skipping")
            else:
                logger.debug(f"🚫 403 on {tier}request for {url} (already logged in TTL)")
            return None

        response.raise_for_status()
        html_content = detect_and_decode_content(response)

        if not html_content or len(html_content) < 100:
            return None

        article_text = trafilatura.extract(html_content)
        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            article_text = extract_with_beautifulsoup(html_content, url)

        if article_text and len(article_text) > MIN_ARTICLE_LENGTH:
            tier = "stealth" if stealth else "simple"
            logger.info(f"✅ {tier} request succeeded for {url}")
            return {
                'text': article_text,
                'image_url': extract_image_url_enhanced(html_content, url),
                'html_content': html_content
            }

        return None

    except Exception as e:
        _fetch_status.code = getattr(getattr(e, 'response', None), 'status_code', None)
        tier = "stealth" if stealth else "simple"
        logger.warning(f"{tier} request failed for {url}: {e}")
        return None
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass


# --- YOUTUBE INGEST ---
# is_youtube_url / fetch_youtube_metadata moved to youtube_ingest.py
# 2026-08-27 (scribe recon/cleanup — ops/RUNBOOK.md). Both were already
# pure; imported below, called with this module's DEFAULT_IMAGE_URL and
# MIN_ARTICLE_LENGTH since those are arc-codex.com/scribe values, not
# YouTube-ingestion ones.


# --- MAIN FETCH DISPATCHER ---

def fetch_article_data(url):
    """
    Main article fetching function.

    YouTube: yt-dlp metadata extraction (no download)
    Tier 1:  Simple requests + trafilatura/BS4
    Tier 2:  Stealth requests (referer + sec-fetch headers)
    Tier 3:  Playwright stealth (restored 2026-07-15 — see
             ops/RUNBOOK.md "Playwright Tier-3 restoration").
             Gated by negative-cache: if a URL is already known-dead we
             don't burn a browser fetch on it.
    """
    # YouTube fast path
    if is_youtube_url(url):
        return fetch_youtube_metadata(url, DEFAULT_IMAGE_URL, MIN_ARTICLE_LENGTH)

    if _is_dead_url(url):
        return None

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    # Tier 1: simple
    result = fetch_with_requests(url, headers, stealth=False)
    if result:
        return result

    # Tier 2: stealth headers
    if is_problematic_news_site(url):
        logger.info(f"🛡️  Protected site detected, trying stealth headers: {url}")
    else:
        logger.info(f"🔄 Simple fetch failed, trying stealth headers: {url}")

    result = fetch_with_requests(url, headers, stealth=True)
    if result:
        return result

    # Tier 3: Playwright stealth. Fires only after simple AND stealth both
    # failed, and only for URLs not in the negative cache (checked at the
    # top of this function). See playwright_tier3.py for the constraint map
    # (radeon exile, fd cleanup, serialized-single-browser, 45s watchdog).
    try:
        from playwright_tier3 import fetch_stealth as _tier3_fetch
        logger.info(f"🎭 Tier 3 (Playwright) for {url}")
        result = _tier3_fetch(url, headers)
        if result:
            return result
    except ImportError as exc:
        logger.warning(f"Tier 3 unavailable ({exc}) — skipping playwright fallback")

    # Mark on the stealth tier's status — the last word on whether the URL is
    # reachable. Statuses outside DEAD_URL_TTLS (429, timeouts, 5xx-transient)
    # are never cached.
    _mark_dead_url(url, getattr(_fetch_status, 'code', None))
    logger.warning(f"❌ All three fetch tiers failed for {url} — skipping")
    return None


# --- PROMPT-TO-ARTICLE ---
# generate_article_from_prompt moved to prompt_to_article.py 2026-08-27
# (scribe recon/cleanup — ops/RUNBOOK.md). Already pure, and its one real
# dependency (call_ollama_local_only) was already a shared utility, not
# scribe's own.


# --- PRIORITY QUEUE CONSUMER ---

def process_priority_queue(api_client, recently_published):
    """
    Drain scribe:priority_uploads at the top of every cycle.

    Items are JSON objects pushed by Flask (POST /api/submit or /api/submit_prompt).

    Supported origins:
        'url'    — fetch URL, run through normal pipeline
        'prompt' — generate article from prompt text, publish directly
        'text'   — raw article text supplied directly (manual publish)

    Each item shape:
        {
            "origin": "url" | "prompt" | "text",
            "url":    "https://...",       # for origin=url or youtube
            "prompt": "Write about...",    # for origin=prompt
            "text":   "Article body...",   # for origin=text
            "title":  "Optional title",
            "image_url": "https://..."     # optional override
        }

    Returns count of items successfully published.
    """
    published = 0

    while True:
        raw = r.lpop(REDIS_PRIORITY_QUEUE_KEY)
        if raw: logger.info(f"⚡ Priority raw item: {raw[:200]}")
        if not raw:
            break

        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"⚡ Priority queue: invalid JSON, discarding: {raw[:100]}")
            continue

        origin = item.get('origin', 'url')
        job_id = item.get('job_id')
        logger.info(f"⚡ Priority item dequeued (origin={origin}, owner={item.get('owner', 'NONE')}, job_id={job_id})")

        article_text = None
        title = item.get('title', '')
        image_url = item.get('image_url') or None
        source_url = item.get('url', '')

        try:
            if origin == 'prompt':
                prompt_text = item.get('prompt', '').strip()
                if not prompt_text:
                    logger.warning("⚡ Priority prompt item has no prompt text — skipping")
                    continue
                article_text = generate_article_from_prompt(prompt_text)
                if not title:
                    # Derive a title from the first sentence of generated text
                    first_line = (article_text or '').split('\n')[0].strip()
                    title = re.sub(r'[\*_#`]+', '', first_line).strip()[:80] or 'Untitled'
                source_url = ''

            elif origin == 'url':
                if not source_url:
                    logger.warning("⚡ Priority url item has no url — skipping")
                    continue
                provided_description = (item.get('description') or '').strip()
                if provided_description:
                    # User supplied text directly — skip URL fetch entirely
                    article_text = provided_description
                    if not title:
                        title = source_url
                    logger.info(f"⚡ Using provided description for URL item ({len(article_text)} chars), skipping fetch")
                else:
                    article_data = fetch_article_data(source_url)
                    if not article_data:
                        logger.warning(f"⚡ Could not fetch priority URL: {source_url}")
                        if job_id:
                            r.setex(
                                site.redis_key(f"job:{job_id}:status"),
                                300,
                                json.dumps({
                                    "status": "failed",
                                    "reason": "URL could not be fetched — the site may be blocking automated access. Please paste the article text directly instead.",
                                }),
                            )
                        continue
                    article_text = article_data['text']
                    if not title:
                        title = source_url
                    if not image_url and article_data.get('image_url'):
                        image_url = article_data['image_url']

            elif origin == 'text':
                article_text = (item.get('text') or item.get('content') or '').strip()
                if not title:
                    title = 'Manual Submission'

            else:
                logger.warning(f"⚡ Unknown priority origin '{origin}' — skipping")
                continue

            # Human submissions bypass length check — only bots get the rules
            has_image = bool(item.get('image_url'))
            if not has_image and (not article_text or len(article_text) < MIN_ARTICLE_LENGTH):
                logger.warning(f"⚡ Priority item produced insufficient text ({len(article_text or '')} chars) — skipping")
                continue
            if not article_text:
                article_text = title or 'Photo submission'

            # Quality gate — skip for prompts and human text submissions
            if origin not in ('prompt', 'text'):
                is_quality, reason = assess_content_quality(article_text)
                if not is_quality:
                    logger.info(f"⚡ Priority item failed quality gate: {reason}")
                    continue

            url_for_hash = item.get('url', '') if origin == 'url' else ''
            article_hash = get_article_hash(title, article_text, url_for_hash, image_url)

            if r.sismember('processed_hashes', article_hash):
                logger.info(f"⚡ Priority item already processed: {article_hash}")
                continue

            # Determine source label
            if origin == 'prompt':
                source_name = 'User Prompt'
            elif origin == 'text':
                source_name = 'Manual Submission'
            else:
                source_name = beautify_source_name(
                    urlparse(source_url).netloc.replace('www.', '') if source_url else 'Unknown',
                    source_url
                )

            # Resolve og_image — user-supplied takes priority, then fallback
            if not image_url:
                image_url = DEFAULT_IMAGE_URL

            # Run pre_analyze to score the article (chimera_score, sentiment, etc.)
            # so the gauge renders in the card header.  Best-effort — if it fails
            # or times out we fall back to the minimal dossier and publish anyway.
            dossier = {'sentiment': 0.0}
            if article_text:
                try:
                    result = api_client.pre_analyze(article_text, article_hash)
                    if result and isinstance(result, dict) and result.get('chimera_score') is not None:
                        dossier = result
                        logger.info(f"⚡ pre_analyze OK for priority item (chimera={result.get('chimera_score'):.4f})")
                    else:
                        logger.warning(f"⚡ pre_analyze returned no chimera_score for priority item — using fallback dossier")
                except Exception as pa_err:
                    logger.warning(f"⚡ pre_analyze failed for priority item: {pa_err} — using fallback dossier")

            # Build candidate in the same shape as RSS candidates
            candidate = {
                'source_name': source_name,
                'source_category': item.get('category', ''),
                'title': title,
                'sourceUrl': source_url,
                'url': f"https://arc-codex.com/article/{article_hash}",
                'article_hash': article_hash,
                'article_text': article_text,
                'imageUrl': image_url,
                'origin': origin,
                'owner': item.get('owner', ''),
                'visibility': item.get('visibility', 'public'),
                'dossier': dossier,
            }

            # Publish directly — no directive matching for priority items
            # Use a minimal directive so publish_and_prepare_comments works unchanged
            target = {
                'article': candidate,
                'directive': {
                    'name': item.get('directive', 'Manual'),
                    'keywords': [],
                    'emotion_profile': 'high',
                    'priority': 1.0,
                }
            }

            success = publish_and_prepare_comments(target, recently_published, api_client, is_priority=True)
            if success:
                r.sadd('processed_hashes', article_hash)
                published += 1
                _inc(STATS_PRIORITY, origin)
                _inc(STATS_PUBLISH, 'ok')
                logger.info(f"⚡ Priority item published: '{title[:60]}'")
                if job_id:
                    r.setex(
                        site.redis_key(f"job:{job_id}:status"),
                        300,
                        json.dumps({"status": "published", "article_id": article_hash}),
                    )

        except Exception as e:
            logger.error(f"⚡ Priority queue processing error: {e}", exc_info=True)
            continue

    return published


# --- API CLIENT ---
# class APIClient moved to api_client.py 2026-08-27 (scribe recon/cleanup —
# ops/RUNBOOK.md). The cleanest seam of the four: no scribe.py state at
# all. Note: manual_publisher.py has its own independent, drifted copy of
# this class (its pre_analyze doesn't take article_id) — untouched here,
# out of scope for this pass; flagged as a follow-up worth considering.


# --- OLLAMA ANALYSIS FUNCTIONS ---

def _repair_sentinel_json(raw: str) -> dict | None:
    """Attempt to parse or repair JSON from sentinel output."""
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

    brace_match = re.search(r'\{[\s\S]*\}', cleaned)
    if not brace_match:
        return None
    json_str = brace_match.group(0)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    repaired = json_str
    repaired = re.sub(r'(?<=": ")(.*?)(?="[,\s}])',
                      lambda m: m.group(0).replace('\n', ' ').replace('\r', ''),
                      repaired, flags=re.DOTALL)
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    repaired = re.sub(r'"\s*\n\s*"', '",\n"', repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    try:
        stripped = re.sub(r'"indicators"\s*:\s*\[.*?\]', '"indicators": []', json_str, flags=re.DOTALL)
        stripped = re.sub(r'"human_signals"\s*:\s*\[.*?\]', '"human_signals": []', stripped, flags=re.DOTALL)
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    conf_match = re.search(r'"synthetic_confidence"\s*:\s*([\d.]+)', json_str)
    assess_match = re.search(r'"assessment"\s*:\s*"([^"]+)"', json_str)
    summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', json_str)

    if conf_match and assess_match:
        return {
            "synthetic_confidence": float(conf_match.group(1)),
            "assessment": assess_match.group(1),
            "indicators": [],
            "human_signals": [],
            "summary": summary_match.group(1) if summary_match else f"{assess_match.group(1)} (confidence: {conf_match.group(1)})"
        }

    # Last resort — model returned prose instead of JSON
    if len(cleaned) > 50:
        return {
            "synthetic_confidence": 0.0,
            "assessment": "UNCERTAIN",
            "indicators": [],
            "human_signals": [],
            "summary": "Sentinel analysis incomplete — fallback model returned prose instead of JSON."
        }
    return None

def run_sentinel_analysis(article_text: str, timeout: int = 900) -> dict | None:
    """Run the Sentinel forensic pass independently of the ensemble pipeline."""
    if not PROMPTS:
        logger.warning("⚠️  Sentinel skipped — prompts.yaml not loaded")
        return None

    sentinel_instruction = (
        PROMPTS.get('teams', {})
        .get('sentinel', {})
        .get('instruction', '')
    )
    if not sentinel_instruction:
        logger.warning("⚠️  Sentinel skipped — no sentinel instruction in prompts.yaml")
        return None

    mission = PROMPTS.get('mission', '')
    constraints = PROMPTS.get('constraints', [])
    constraints_text = '\n'.join(f"- {c}" for c in constraints) if isinstance(constraints, list) else str(constraints)

    sentinel_prompt = f"""{mission}

SENTINEL FORENSIC ANALYSIS:
{sentinel_instruction}

CONSTRAINTS:
{constraints_text}

--- ARTICLE TEXT ---
{article_text}"""

    try:
        logger.info("🛡️  Running Sentinel forensic analysis...")
        raw_response, duration, model_used = call_ollama_local_only(sentinel_prompt, timeout=timeout)
        logger.info(f"🛡️  Sentinel complete via {model_used} in {duration:.0f}ms")

        sentinel_data = _repair_sentinel_json(raw_response)

        if not sentinel_data:
            logger.warning(f"⚠️  Sentinel JSON unrecoverable — raw: {raw_response[:300]}")
            return None

        required_keys = {'synthetic_confidence', 'assessment', 'summary'}
        if not required_keys.issubset(sentinel_data.keys()):
            missing = required_keys - sentinel_data.keys()
            logger.warning(f"⚠️  Sentinel response missing keys: {missing} — filling with defaults")
            sentinel_data.setdefault('synthetic_confidence', 0.0)
            sentinel_data.setdefault('assessment', 'UNCERTAIN')
            sentinel_data.setdefault('summary', 'Sentinel analysis incomplete — partial response from fallback model.')
            sentinel_data.setdefault('indicators', [])
            sentinel_data.setdefault('human_signals', [])

        conf = sentinel_data.get('synthetic_confidence', 0.0)
        sentinel_data['synthetic_confidence'] = max(0.0, min(1.0, float(conf)))

        valid_assessments = {'HUMAN', 'LIKELY_HUMAN', 'UNCERTAIN', 'LIKELY_SYNTHETIC', 'SYNTHETIC'}
        if sentinel_data.get('assessment') not in valid_assessments:
            sentinel_data['assessment'] = 'UNCERTAIN'

        logger.info(f"🛡️  Sentinel verdict: {sentinel_data['assessment']} "
                    f"(confidence: {sentinel_data['synthetic_confidence']:.2f})")
        return sentinel_data

    except Exception as e:
        logger.error(f"🛡️  Sentinel analysis failed: {e}")
        return None


def run_counter_analyst(article_text: str, article_id: str, timeout: int = 900) -> bool:
    """Generate a devil's advocate comment and post it directly to Redis."""
    if not PROMPTS:
        logger.warning("⚠️  Counter-analyst skipped — prompts.yaml not loaded")
        return False

    ca_instruction = (
        PROMPTS.get('teams', {})
        .get('counter_analyst', {})
        .get('instruction', '')
    )
    if not ca_instruction:
        logger.warning("⚠️  Counter-analyst skipped — no instruction in prompts.yaml")
        return False

    ca_prompt = f"""You are reviewing this article for Arc Codex. Write a counter-argument comment.

{ca_instruction}

--- ARTICLE TEXT ---
{article_text[:8000]}"""

    try:
        logger.info("🤖 Running Counter-Analyst...")
        raw_response, duration, model_used = call_ollama_local_only(ca_prompt, timeout=timeout)
        logger.info(f"🤖 Counter-Analyst complete via {model_used} in {duration:.0f}ms")

        comment_text = raw_response.strip()
        for prefix in ['Counter-argument:', 'Counter-Argument:', 'As an AI', 'Here is']:
            if comment_text.startswith(prefix):
                comment_text = comment_text[len(prefix):].strip()
                if comment_text.startswith(':'):
                    comment_text = comment_text[1:].strip()

        if len(comment_text) < 20:
            logger.warning(f"⚠️  Counter-analyst response too short ({len(comment_text)} chars)")
            return False
        if len(comment_text) > 2000:
            sentences = comment_text.split('. ')
            comment_text = '. '.join(sentences[:4])
            if not comment_text.endswith('.') and not comment_text.endswith('?'):
                comment_text += '.'

        comment_id = str(uuid.uuid4())
        comment_data = {
            'id': comment_id,
            'article_id': article_id,
            'author': 'A.R.C. Counter-Analyst',
            'text': comment_text,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'parent_id': ''
        }

        pipe = r.pipeline()
        pipe.hset(f"comment:{comment_id}", mapping=comment_data)
        pipe.rpush(f"comments:{article_id}", comment_id)
        pipe.execute()

        logger.info(f"🤖 Counter-analyst comment posted for {article_id} ({len(comment_text)} chars)")
        return True

    except Exception as e:
        logger.error(f"🤖 Counter-analyst failed: {e}")
        return False


# --- CORE LOGIC ---

def initialize_directories():
    for directory in [UPLOAD_DIR, PENDING_DIR, PROCESSING_DIR, COMPLETED_DIR, FAILED_DIR, PENDING_COMMENTS_DIR]:
        os.makedirs(directory, exist_ok=True)


def load_json_file(filepath, default_content):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_content


def load_jsonl_file(filepath, default_content):
    try:
        sources = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    sources.append(json.loads(line))
        return sources
    except (FileNotFoundError, json.JSONDecodeError):
        return default_content


def save_json_file(filepath, data):
    with FILE_LOCK:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


def get_article_hash(title, text_content, source_url='', image_url=''):
    snippet = text_content.strip()[:500]
    # For photo/image-only posts with no text, mix in a UUID so identical
    # titles (e.g. multiple "Lumi" photos) don't collide and get deduped.
    if len(snippet) < 50:
        unique_string = f"{title.strip()}::{uuid.uuid4().hex}"
    else:
        unique_string = f"{title.strip()}::{snippet}"
    if source_url:
        unique_string += f"::{source_url.strip()}"
    if image_url:
        unique_string += f"::{image_url.strip()}"
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()


def get_next_source_batch(all_sources, batch_size):
    last_index = int(r.get('source_index') or 0)
    total = len(all_sources)
    if total == 0:
        return []
    batch = [all_sources[(last_index + i) % total] for i in range(batch_size)]
    r.set('source_index', (last_index + batch_size) % total)
    return batch


def find_best_target(candidates, all_directives, recently_published):
    potential_targets = []
    active_directives = [d for d in all_directives if d.get('name') not in recently_published]

    for directive in active_directives:
        for cand in candidates:
            text_to_search = (cand.get('title', '') + ' ' + cand.get('article_text', '')).lower()
            keywords = directive.get('keywords', [])
            if not any(re.search(r'\b' + re.escape(keyword) + r'\b', text_to_search, re.IGNORECASE) for keyword in keywords):
                continue

            category_bonus = 2.0 if CATEGORY_TO_DIRECTIVE.get(
                cand.get('source_category', ''), ''
            ) == directive.get('name') else 0.0
            final_score = directive.get('priority', 1.0) + category_bonus
            potential_targets.append({'score': final_score, 'article': cand, 'directive': directive})

    if not potential_targets:
        # Fallback: ignore recently_published, pick best scoring candidate from all directives
        logger.info("⚠️  No candidates matched active directives — trying fallback (ignoring recently_published)")
        for directive in all_directives:
            for cand in candidates:
                text_to_search = (cand.get('title', '') + ' ' + cand.get('article_text', '')).lower()
                keywords = directive.get('keywords', [])
                if not any(re.search(r'\b' + re.escape(keyword) + r'\b', text_to_search, re.IGNORECASE) for keyword in keywords):
                    continue
                category_bonus = 2.0 if CATEGORY_TO_DIRECTIVE.get(
                    cand.get('source_category', ''), ''
                ) == directive.get('name') else 0.0
                final_score = directive.get('priority', 1.0) + category_bonus
                potential_targets.append({'score': final_score, 'article': cand, 'directive': directive})
        if not potential_targets:
            return None

    potential_targets.sort(key=lambda x: x['score'], reverse=True)
    best_target = potential_targets[0]
    logger.info(f"🎯 TARGET: '{best_target['directive']['name']}' on '{best_target['article'].get('title', '')[:50]}...' (score: {best_target['score']:.2f})")
    return best_target


def publish_and_prepare_comments(target, recently_published, api_client, is_priority=False):
    """Publish article and queue sentinel + counter-analyst in background. Red/Blue/Purple is lazy.

    is_priority=True: article is published immediately regardless of analysis. Sentinel and
    counter-analyst still run in a background thread — they don't block publishing.
    Red/Blue/Purple is deferred to analyzer.py and fires on first article view.
    """
    article = target.get('article', {})
    directive = target.get('directive', {})
    article_id = article.get('article_hash')

    if not article or not article_id:
        return False

    if r.sismember('processed_hashes', article_id):
        logger.info(f"Article {article_id} already processed")
        return True

    logger.info(f"📰 Publishing: '{article.get('title', 'Untitled')}'")

    current_image = article.get('imageUrl', DEFAULT_IMAGE_URL)
    if not current_image or current_image == DEFAULT_IMAGE_URL:
        smart_image = get_default_image(
            directive_name=directive.get('name', ''),
            source_category=article.get('source_category', '')
        )
        article['imageUrl'] = smart_image
        logger.info(f"🖼️  Using category default image for '{directive.get('name', '')}' / '{article.get('source_category', '')}': {smart_image}")

    # Self-host external hero images. A failed rehost (SVG, timeout, 403,
    # oversize) falls back to the site default image — the failed source URL
    # must never ship as the final imageUrl, since the same failure usually
    # renders broken client-side too. Publishing proceeds either way.
    hero_url = article.get('imageUrl', '')
    if hero_url.startswith(('http://', 'https://')) and 'arc-codex.com' not in hero_url:
        local_path = rehost_article_image(article_id, hero_url, SCRAPED_IMAGE_DIR)
        if local_path:
            article['image_source_url'] = hero_url
            article['imageUrl'] = local_path
        else:
            fallback = get_default_image(directive.get('name', ''), article.get('source_category', ''))
            logger.info(f"🖼️  Rehost failed for {article_id} — default image replaces hotlink: {fallback}")
            article['imageUrl'] = fallback

    # Ingest-side XSS defense: sanitize once, reuse for both Redis publish and
    # Solr indexing below. Strips active HTML (script/meta/iframe/etc) so any
    # consumer that skips render-time escaping stays safe (2026-07-09 fix).
    sanitized_body = sanitize_active_content(article.get('article_text', ''))

    publish_payload = {
        k: v for k, v in article.items()
        if k not in ['article_text', 'article_hash', 'dossier', 'filename', 'processing_path', 'origin', 'html_content', 'source_category']
    }
    publish_payload.update({
        'original_text': sanitized_body,
        'id': article_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dossier': json.dumps(article.get('dossier', {})),
        'directive': directive.get('name', 'Unknown'),
        'category': get_canonical_category(
            directive_name=directive.get('name', ''),
            source_category=article.get('source_category', '')
        ),
        'source_lang': detect_language(article.get('article_text', '')),
        'blue_team_analysis': '',
        'red_team_analysis': '',
        'purple_team_analysis': '',
        'sentinel_analysis': '',
        'origin': article.get('origin', 'rss'),
        'visibility': article.get('visibility', 'public'),
        'owner': article.get('owner', ''),
    })

    # Carry the pre_analyze nlp_* fields through to the article hash. They
    # reach the hash only on quality-pass publish — never for articles that
    # never make it past scribe's gates. corpus_exporter.py reads them from
    # the article hash unchanged.
    dossier_dict = article.get('dossier') or {}
    if isinstance(dossier_dict, dict):
        for k, v in dossier_dict.items():
            if k.startswith('nlp_') and v is not None:
                publish_payload[k] = v

    try:
        api_client.publish_article(publish_payload)
        logger.info(f"✅ Article published: {article_id}")
        r.setex(site.redis_key('last_publish'), 86400, datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.error(f"Failed to publish {article_id}: {e}")
        return False

    # Solr indexing
    global solr
    if not solr:
        try:
            solr = pysolr.Solr(SOLR_URL)
            solr.ping()
            logger.info("✅ Solr reconnected")
        except Exception:
            solr = None
    if solr:
        dossier_data = article.get('dossier', {})
        solr_doc = {
            'id': article_id,
            'title': article.get('title', ''),
            'content': sanitized_body,
            'source': article.get('source_name', 'Unknown'),
            'url': article.get('sourceUrl', ''),
            'timestamp': publish_payload['timestamp'],
            'sentiment': dossier_data.get('sentiment', 0.0),
            'directive': directive.get('name', 'Unknown'),
            'chimera_score': dossier_data.get('chimera_score', 0.0),
            'category': publish_payload.get('category', ''),
            'source_lang': publish_payload.get('source_lang', 'English'),
            'original_text': sanitized_body,
            'imageUrl': article.get('imageUrl', ''),
        }
        try:
            solr.add([solr_doc])
            solr.commit()
            logger.info(f"✅ Indexed in Solr: {article_id}")
        except Exception as e:
            logger.warning(f"Solr indexing failed: {e}")

    # --- SENTINEL + COUNTER-ANALYST ---
    # Priority queue items (user submissions) skip all AI analysis so the post
    # appears in the feed immediately. RSS articles get the full treatment,
    # but analysis runs in a background thread — never blocks the main loop.
    text_for_analysis = article.get('article_text', '')
    if len(text_for_analysis.strip()) < 100:
        logger.info(f"📷 Short post — skipping sentinel + counter-analyst for {article_id}")
    else:
        _analysis_executor.submit(_run_analysis_background, article_id, text_for_analysis)
        if is_priority:
            logger.info(f"🔬 Priority post — sentinel + counter-analyst queued in background for {article_id}")
        else:
            logger.info(f"🔬 Analysis queued in background for {article_id}")

    # Red/Blue/Purple deferred — fires on first article view via analyzer.py

    # Audio deliberately does NOT fire here, and scribe no longer runs an
    # audio pass of its own at all (retired 2026-08-27 — see the note above
    # synthesize_article_audio's definition). The story is in the feed now;
    # audio_backfill.py's daemon narrates it from there on its own cadence.

    if directive.get('name'):
        recently_published.append(directive['name'])

    return True


# --- MAIN LOOP ---

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

    logger.info(f"🚀 {site.name} Scribe v53.0 [{site.path}]")
    logger.info(f"   📡 Model: {OLLAMA_LOCAL_FALLBACK} (local only, no cloud, no fallback)")
    logger.info(f"   🎭 Playwright Tier-3: enabled (restored 2026-07-15, radeon exiled by env-signature)")
    logger.info(f"   ▶️  YouTube ingest: yt-dlp metadata mode")
    logger.info(f"   ✍️  Prompt-to-article: enabled")
    logger.info(f"   ⚡ Priority queue: {REDIS_PRIORITY_QUEUE_KEY} (processed each cycle)")
    logger.info(f"   📋 Red/Blue/Purple: deferred to analyzer.py (on-demand)")

    # Fail-fast on a truncated sources.json — the 2026-09-01 incident
    # (2310 → 30 records, 36 hours of silent partial sweeps) is why.
    # No-op when [integrity] is disabled (both bounds 0).
    _enforce_sources_floor()

    # Reap any orphan Playwright browsers left by a prior crashed scribe.
    # Match is on /proc/<pid>/environ ARC_TIER3_PLAYWRIGHT signature —
    # will NEVER kill Ross's desktop Chrome.
    try:
        from playwright_tier3 import startup_kill_zombies
        startup_kill_zombies()
    except ImportError:
        pass

    scribe_ops = ScribeOperationalState(r, logger=logger)
    scribe_ops.set_status('starting')
    threading.Thread(
        target=run_heartbeat_loop,
        args=(scribe_ops,),
        daemon=True,
        name='scribe-operational-heartbeat',
    ).start()

    startup_delay = STARTUP_DELAY_SECONDS
    logger.info(f"   ⏱️  Startup delay: {startup_delay}s (offset from Huntaegis, which starts at 0s)")
    time.sleep(startup_delay)

    api_client = APIClient(API_BASE_URL, SCRIBE_SECRET_KEY)
    initialize_directories()
    # Governs feedparser.parse (urllib) only — article fetches pass
    # NETWORK_TIMEOUT_SECONDS to requests explicitly and ignore this default.
    # 30s because nine chronic feeds (FCC x2, USDA x2, CBC x2, Mr Porter,
    # ACSC, Zoom Blog) timed out on most polls at 15s since late May.
    socket.setdefaulttimeout(FEED_TIMEOUT_SECONDS)
    recently_published = deque(maxlen=RECENTLY_PUBLISHED_MEMORY)

    cycle_count = 0

    while True:
        cycle_count += 1

        try:
            scribe_ops.set_status('active')
            # Heartbeat: liveness signal for corpus_exporter/Grafana + mailer.
            # TTL derives from CYCLE_MINUTES so a wedged scribe reads as
            # key-absent instead of eventually staying absent because the TTL
            # is shorter than the cadence (see _liveness_ttl_seconds docstring).
            try:
                r.setex(site.redis_key('scribe:last_cycle'),
                        _liveness_ttl_seconds(CYCLE_MINUTES),
                        str(int(time.time())))
            except Exception:
                pass

            # --- PRIORITY QUEUE FIRST ---
            # User-submitted URLs, prompts, and manual text are always processed
            # before RSS scanning so the user gets fast feedback.
            priority_count = process_priority_queue(api_client, recently_published)
            if priority_count:
                logger.info(f"⚡ Processed {priority_count} priority item(s) — skipping RSS cycle so M1 is free")
                logger.info(f"💤 Priority cycle complete. Sleeping {CYCLE_MINUTES} minutes ...")
                scribe_ops.set_status('idle')
                for _ in range(CYCLE_MINUTES * 60):
                    time.sleep(1)
                    if r.llen(REDIS_PRIORITY_QUEUE_KEY) > 0:
                        break
                continue

            # --- RSS CYCLE ---
            processed_hashes = r.smembers('processed_hashes')
            all_sources = load_jsonl_file(SOURCES_FILE, [])
            all_directives = [d for topic in load_json_file(DIRECTIVES_FILE, [])
                              for key, value in topic.items() if isinstance(value, list) for d in value]

            if not all_sources or not all_directives:
                scribe_ops.mark_failure('main_loop')
                time.sleep(2)
                continue

            logger.info(f"📡 Cycle {cycle_count}: Scanning {SOURCE_BATCH_SIZE} sources...")
            candidates = []
            source_batch = get_next_source_batch(all_sources, SOURCE_BATCH_SIZE)
            scribe_ops.mark_poll_attempt()

            for source in source_batch:
                try:
                    feed = feedparser.parse(source['url'])
                    if feed.bozo:
                        _inc(STATS_RSS, 'bozo')
                        scribe_ops.record_poll('malformed')
                        continue
                    _inc(STATS_RSS, 'ok')
                    scribe_ops.record_poll('success')

                    valid_entries = [
                        entry for entry in feed.entries[:3]
                        if all(hasattr(entry, attr) for attr in ['title', 'link']) and
                        entry.link.strip()
                    ]
                    scribe_ops.increment('articles_discovered', len(valid_entries))
                    entries_to_fetch = []
                    for entry in valid_entries:
                        if get_article_hash(entry.title, "") in processed_hashes:
                            scribe_ops.increment('articles_duplicate')
                        else:
                            entries_to_fetch.append(entry)

                    if not entries_to_fetch:
                        continue

                    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_SCRAPERS, len(entries_to_fetch))) as executor:
                        future_to_entry = {
                            executor.submit(fetch_article_data, entry.link): entry
                            for entry in entries_to_fetch
                        }

                        for future in future_to_entry:
                            entry = future_to_entry[future]
                            try:
                                article_data = future.result(timeout=90)
                                if not article_data:
                                    scribe_ops.increment('articles_skipped')
                                    continue

                                article_text = article_data['text']
                                html_content = article_data.get('html_content', '')

                                is_quality, reason = assess_content_quality(article_text, html_content)
                                if not is_quality:
                                    logger.info(f"⛔ Skipping article: {reason}")
                                    _inc(STATS_QUALITY, reason.split('(')[0].strip())
                                    scribe_ops.increment('articles_rejected')
                                    continue

                                full_hash = get_article_hash(entry.title, article_text)
                                if full_hash in processed_hashes:
                                    scribe_ops.increment('articles_duplicate')
                                    continue

                                metadata = clean_article_metadata(entry.title, html_content)

                                new_candidate = {
                                    'source_name': beautify_source_name(source.get('name', 'Unknown'), entry.link),
                                    'source_category': source.get('category', ''),
                                    'title': metadata['title'],
                                    'sourceUrl': entry.link,
                                    'url': f"https://arc-codex.com/article/{full_hash}",
                                    'article_hash': full_hash,
                                    'article_text': article_text,
                                    'imageUrl': article_data['image_url'],
                                    'origin': 'rss'
                                }
                                candidates.append(new_candidate)
                                scribe_ops.increment('articles_new')
                                logger.info(f"✅ Candidate: {metadata['title'][:60]}")

                            except Exception as e:
                                logger.error(f"Error processing {entry.link}: {e}")
                                scribe_ops.increment('articles_skipped')
                                scribe_ops.increment('errors_fetch')
                                continue

                except Exception as e:
                    logger.error(f"Error processing source {source.get('name')}: {e}")
                    scribe_ops.record_poll('error')
                    scribe_ops.increment('errors_source_poll')
                    continue

            if not candidates:
                logger.info("No new articles found")
            else:
                logger.info(f"Found {len(candidates)} quality articles. Analyzing...")

                with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_ANALYZERS, len(candidates))) as executor:
                    future_to_cand = {
                        executor.submit(api_client.pre_analyze, cand['article_text'], cand['article_hash']): cand
                        for cand in candidates
                    }

                    for future in future_to_cand:
                        cand = future_to_cand[future]
                        try:
                            result = future.result(timeout=3600)
                            cand['dossier'] = result or {'sentiment': 0.0}
                        except Exception as e:
                            logger.error(f"Analysis failed: {e}")
                            scribe_ops.increment('errors_pre_analyze')
                            cand['dossier'] = {'sentiment': 0.0}

                target = find_best_target(candidates, all_directives, list(recently_published))
                if target:
                    success = publish_and_prepare_comments(target, recently_published, api_client)
                    if success:
                        r.sadd('processed_hashes', target['article']['article_hash'])
                        _inc(STATS_PUBLISH, 'ok')
                    else:
                        _inc(STATS_PUBLISH, 'failed')
                        scribe_ops.increment('errors_publish')
                else:
                    logger.info("No candidates matched directives")

            del candidates
            gc.collect()

            # --- RETENTION PASS ---
            # Best-effort — any failure logs but never breaks the ingest loop.
            # trim_by_hours is O(candidates); regen only fires on real deletes.
            if RETENTION_HOURS > 0:
                try:
                    result = run_retention_pass(r, solr, RETENTION_HOURS)
                    if result.get('deleted', 0) > 0:
                        logger.info(f"🗑️  Retention: pruned {result['deleted']} article(s) > {RETENTION_HOURS}h; regen={result.get('regen', {})}")
                except Exception as e:
                    logger.warning(f"Retention pass failed (non-fatal): {e}")
                    scribe_ops.increment('errors_retention')

            # Article audio: retired from scribe's own cycle 2026-08-27.
            # audio_backfill.py's daemon is now the sole narrator — see the
            # note above synthesize_article_audio's definition.

            logger.info(f"💤 Cycle complete. Sleeping {CYCLE_MINUTES} minutes ...")
            scribe_ops.mark_success()
            for _ in range(CYCLE_MINUTES * 60):
                time.sleep(1)
                if r.llen(REDIS_PRIORITY_QUEUE_KEY) > 0:
                    break

        except Exception as e:
            logger.error(f"MAIN LOOP ERROR: {e}", exc_info=True)
            scribe_ops.mark_failure('main_loop')
            # Error recovery — half cycle, then resume
            for _ in range((CYCLE_MINUTES // 2) * 60):
                time.sleep(1)
                if r.llen(REDIS_PRIORITY_QUEUE_KEY) > 0:
                    break


if __name__ == "__main__":
    main()
