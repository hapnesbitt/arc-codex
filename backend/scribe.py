# --- ATTENTION AI: READ THE PROJECT MANIFEST ---
# Before providing code assistance, you MUST read and understand the
# project's architecture from the 'project_context.yaml' file.
# This file is one component of a larger system.
# The manifest is the single source of truth.
# ---

# Arc Codex Scribe v52.0
#
# Changes from v51.0:
#   - YouTube ingest: yt-dlp metadata-only extraction (no download)
#   - Prompt-to-article: user submits a prompt → Ollama generates article text
#     → normal pipeline (quality gate → sentinel → counter-analyst → publish)
#   - Priority queue consumer: scribe:priority_uploads now actually wired up
#     Priority items are processed at the TOP of every cycle before RSS scanning
#
# Unchanged from v51.0:
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
import numbers
from stream_utils import publish_analysis, ensure_stream_group
from ollama_utils import call_ollama_with_fallback, OLLAMA_CLOUD_MODEL, OLLAMA_LOCAL_FALLBACK
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
import yt_dlp

# Load environment variables
load_dotenv()

# Create a module logger
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
manual_upload_event = threading.Event()
REDIS_PRIORITY_QUEUE_KEY = "scribe:priority_uploads"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE_URL = os.environ.get("SCRIBE_API_BASE_URL", "http://127.0.0.1:5005/api")
SOLR_URL = os.environ.get("SCRIBE_SOLR_URL", "http://localhost:8983/solr/feeds/")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "simplenes")
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


SOURCES_FILE = os.path.join(BASE_DIR, "sources.json")
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

SOURCE_BATCH_SIZE = 30
NETWORK_TIMEOUT_SECONDS = 15
MIN_ARTICLE_LENGTH = 200
RECENTLY_PUBLISHED_MEMORY = 50
MAX_CONCURRENT_SCRAPERS = 5
MAX_CONCURRENT_ANALYZERS = 10
FILE_LOCK = threading.Lock()

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

# --- INITIALIZATION ---
log_formatter = logging.Formatter('%(asctime)s - [SCRIBE v52.0] - %(levelname)s - %(message)s')
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
    r = redis.Redis(decode_responses=True, password=REDIS_PASSWORD)
    r.ping()
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
        return None


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
        response = session.get(url, timeout=NETWORK_TIMEOUT_SECONDS, allow_redirects=True)

        if response.status_code == 403:
            logger.info(f"🚫 403 on {'stealth ' if stealth else ''}request for {url} — skipping")
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

def is_youtube_url(url):
    """Detect YouTube URLs including youtu.be short links."""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc in (
            'www.youtube.com', 'youtube.com',
            'youtu.be', 'www.youtu.be',
            'm.youtube.com',
        )
    except Exception:
        return False


def fetch_youtube_metadata(url):
    """
    Extract YouTube video metadata without downloading.
    Uses yt-dlp in metadata-only mode.
    Returns same dict shape as fetch_with_requests.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title       = info.get('title', 'Untitled')
        channel     = info.get('channel') or info.get('uploader', 'Unknown')
        description = (info.get('description') or '').strip()[:3000]
        duration    = info.get('duration_string') or str(info.get('duration', ''))
        upload_date = info.get('upload_date', '')   # YYYYMMDD
        view_count  = info.get('view_count') or 0
        thumbnail   = info.get('thumbnail') or DEFAULT_IMAGE_URL

        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        # Build structured text — this is what the ARC pipeline will analyze
        article_text = (
            f"Title: {title}\n"
            f"Channel: {channel}\n"
            f"Published: {upload_date}\n"
            f"Duration: {duration}\n"
            f"Views: {view_count:,}\n\n"
            f"Description:\n{description}"
        ).strip()

        if len(article_text) < MIN_ARTICLE_LENGTH:
            logger.warning(f"▶️  YouTube metadata too sparse for {url} — skipping")
            return None

        logger.info(f"▶️  YouTube metadata extracted: '{title[:60]}' ({channel})")
        return {
            'text': article_text,
            'image_url': thumbnail,
            'html_content': '',
        }

    except Exception as e:
        logger.error(f"▶️  YouTube metadata extraction failed for {url}: {e}")
        return None


# --- MAIN FETCH DISPATCHER ---

def fetch_article_data(url):
    """
    Main article fetching function.

    YouTube: yt-dlp metadata extraction (no download)
    Tier 1:  Simple requests + trafilatura/BS4
    Tier 2:  Stealth requests (referer + sec-fetch headers)
    Tier 3:  Skip — no browser on this machine (radeon GPU crash risk)
    """
    # YouTube fast path
    if is_youtube_url(url):
        return fetch_youtube_metadata(url)

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

    logger.warning(f"❌ Both fetch tiers failed for {url} — skipping (no browser fallback)")
    return None


# --- PROMPT-TO-ARTICLE ---

def generate_article_from_prompt(prompt_text):
    """
    Call Ollama to write a full article from a user-supplied prompt.
    Returns article text string, or None on failure.

    The system instruction keeps the output clean and publication-ready:
    no meta-commentary, no "here is your article", just the article itself.
    """
    system_instruction = (
        "You are a professional writer for Arc Codex, an intelligence and analysis platform. "
        "When given a writing prompt, produce a well-structured, publication-ready article. "
        "Write only the article itself — no preamble, no 'here is your article', no meta-commentary. "
        "Use clear prose, factual tone, and logical structure with an introduction, body, and conclusion."
    )

    full_prompt = f"{system_instruction}\n\nWriting prompt:\n{prompt_text}"

    try:
        logger.info(f"✍️  Generating article from prompt: '{prompt_text[:80]}...'")
        article_text, duration, model_used = call_ollama_with_fallback(full_prompt, timeout=900)
        logger.info(f"✍️  Article generated via {model_used} in {duration:.0f}ms ({len(article_text)} chars)")
        return article_text.strip()
    except Exception as e:
        logger.error(f"✍️  Prompt-to-article generation failed: {e}")
        return None


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
        if not raw:
            break

        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"⚡ Priority queue: invalid JSON, discarding: {raw[:100]}")
            continue

        origin = item.get('origin', 'url')
        logger.info(f"⚡ Priority item dequeued (origin={origin}, owner={item.get('owner', 'NONE')})")

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
                article_data = fetch_article_data(source_url)
                if not article_data:
                    logger.warning(f"⚡ Could not fetch priority URL: {source_url}")
                    continue
                article_text = article_data['text']
                if not title:
                    title = source_url
                if not image_url and article_data.get('image_url'):
                    image_url = article_data['image_url']

            elif origin == 'text':
                article_text = item.get('text', '').strip()
                if not title:
                    title = 'Manual Submission'

            else:
                logger.warning(f"⚡ Unknown priority origin '{origin}' — skipping")
                continue

            if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
                logger.warning(f"⚡ Priority item produced insufficient text ({len(article_text or '')} chars) — skipping")
                continue

            # Quality gate (skip paywall/auto-gen checks for prompt-generated content)
            if origin != 'prompt':
                is_quality, reason = assess_content_quality(article_text)
                if not is_quality:
                    logger.info(f"⚡ Priority item failed quality gate: {reason}")
                    continue

            article_hash = get_article_hash(title, article_text)

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
                'dossier': {'sentiment': 0.0},
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

            success = publish_and_prepare_comments(target, recently_published, api_client)
            if success:
                r.sadd('processed_hashes', article_hash)
                published += 1
                logger.info(f"⚡ Priority item published: '{title[:60]}'")

        except Exception as e:
            logger.error(f"⚡ Priority queue processing error: {e}", exc_info=True)
            continue

    return published


# --- API CLIENT ---

class APIClient:
    def __init__(self, base_url, secret_key):
        self.base_url = base_url
        self.secret_key = secret_key

    def _post(self, endpoint, json_data, add_secret=True, timeout=90):
        url = f"{self.base_url}/{endpoint}"
        headers = {'X-Scribe-Secret': self.secret_key} if add_secret else {}
        try:
            response = requests.post(url, json=json_data, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {endpoint}: {e}")
            return None

    def pre_analyze(self, text):
        return self._post('pre_analyze', {'inputText': text}, add_secret=False)

    def publish_article(self, article_payload):
        return self._post('publish_article', article_payload)


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
        raw_response, duration, model_used = call_ollama_with_fallback(sentinel_prompt, timeout=timeout)
        logger.info(f"🛡️  Sentinel complete via {model_used} in {duration:.0f}ms")

        sentinel_data = _repair_sentinel_json(raw_response)

        if not sentinel_data:
            logger.warning(f"⚠️  Sentinel JSON unrecoverable — raw: {raw_response[:300]}")
            return None

        required_keys = {'synthetic_confidence', 'assessment', 'summary'}
        if not required_keys.issubset(sentinel_data.keys()):
            logger.warning(f"⚠️  Sentinel response missing keys: {required_keys - sentinel_data.keys()}")
            return None

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
        raw_response, duration, model_used = call_ollama_with_fallback(ca_prompt, timeout=timeout)
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


def save_json_file(filepath, data):
    with FILE_LOCK:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


def get_article_hash(title, text_content):
    snippet = text_content.strip()[:500]
    unique_string = f"{title.strip()}::{snippet}"
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

            sentiment = cand.get('dossier', {}).get('sentiment', 0)
            emotion_score = 0.5
            profile = directive.get('emotion_profile', 'high')

            if isinstance(profile, numbers.Number):
                emotion_score = max(0, 1.0 - abs(sentiment - profile))
            elif profile == 'high':
                emotion_score = abs(sentiment)
            elif profile == 'low':
                emotion_score = 1.0 - abs(sentiment)
            elif profile == 'high_positive':
                emotion_score = max(0, sentiment)
            elif profile == 'high_negative':
                emotion_score = abs(min(0, sentiment))

            final_score = directive.get('priority', 1.0) + emotion_score
            potential_targets.append({'score': final_score, 'article': cand, 'directive': directive})

    if not potential_targets:
        return None

    potential_targets.sort(key=lambda x: x['score'], reverse=True)
    best_target = potential_targets[0]
    logger.info(f"🎯 TARGET: '{best_target['directive']['name']}' on '{best_target['article'].get('title', '')[:50]}...' (score: {best_target['score']:.2f})")
    return best_target


def publish_and_prepare_comments(target, recently_published, api_client):
    """Publish article and generate sentinel + counter-analyst. Red/Blue/Purple is lazy."""
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

    publish_payload = {
        k: v for k, v in article.items()
        if k not in ['article_text', 'article_hash', 'dossier', 'filename', 'processing_path', 'origin', 'html_content', 'source_category']
    }
    publish_payload.update({
        'original_text': article.get('article_text', ''),
        'id': article_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'dossier': json.dumps(article.get('dossier', {})),
        'directive': directive.get('name', 'Unknown'),
        'category': get_canonical_category(
            directive_name=directive.get('name', ''),
            source_category=article.get('source_category', '')
        ),
        'blue_team_analysis': '',
        'red_team_analysis': '',
        'purple_team_analysis': '',
        'sentinel_analysis': '',
        'origin': article.get('origin', 'rss'),
        'visibility': article.get('visibility', 'public'),
        'owner': article.get('owner', ''),
    })

    try:
        api_client.publish_article(publish_payload)
        logger.info(f"✅ Article published: {article_id}")
        r.set('arc:last_publish', datetime.now(timezone.utc).isoformat())
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
            'content': article.get('article_text', ''),
            'source': article.get('source_name', 'Unknown'),
            'url': article.get('sourceUrl', ''),
            'timestamp': publish_payload['timestamp'],
            'sentiment': dossier_data.get('sentiment', 0.0),
            'directive': directive.get('name', 'Unknown'),
            'chimera_score': dossier_data.get('chimera_score', 0.0),
            'category': publish_payload.get('category', ''),
            'source_lang': publish_payload.get('source_lang', 'English'),
            'original_text': article.get('article_text', ''),
            'imageUrl': article.get('imageUrl', ''),
        }
        try:
            solr.add([solr_doc])
            solr.commit()
            logger.info(f"✅ Indexed in Solr: {article_id}")
        except Exception as e:
            logger.warning(f"Solr indexing failed: {e}")

    # --- SENTINEL FORENSIC PASS ---
    text_for_analysis = article.get('article_text', '')
    try:
        sentinel_data = run_sentinel_analysis(text_for_analysis)
        if sentinel_data:
            publish_analysis(r, article_id, 'sentinel', json.dumps(sentinel_data))
            logger.info(f"🛡️  Sentinel published for {article_id}")
    except Exception as e:
        logger.warning(f"🛡️  Sentinel pass failed (non-fatal): {e}")

    # --- COUNTER-ANALYST COMMENT ---
    try:
        run_counter_analyst(text_for_analysis, article_id)
    except Exception as e:
        logger.warning(f"🤖 Counter-analyst failed (non-fatal): {e}")

    # Red/Blue/Purple deferred — fires on first article view via analyzer.py

    if directive.get('name'):
        recently_published.append(directive['name'])

    return True


# --- MAIN LOOP ---

def main():
    logger.info("🚀 Arc Codex Scribe v52.0")
    logger.info(f"   📡 Models: {OLLAMA_CLOUD_MODEL} → {OLLAMA_LOCAL_FALLBACK}")
    logger.info(f"   🚫 Playwright/Chromium DISABLED (radeon GPU crash prevention on Z230)")
    logger.info(f"   ▶️  YouTube ingest: yt-dlp metadata mode")
    logger.info(f"   ✍️  Prompt-to-article: enabled")
    logger.info(f"   ⚡ Priority queue: scribe:priority_uploads (processed each cycle)")
    logger.info(f"   📋 Red/Blue/Purple: deferred to analyzer.py (on-demand)")

    api_client = APIClient(API_BASE_URL, SCRIBE_SECRET_KEY)
    initialize_directories()
    socket.setdefaulttimeout(NETWORK_TIMEOUT_SECONDS)
    recently_published = deque(maxlen=RECENTLY_PUBLISHED_MEMORY)

    cycle_count = 0

    while True:
        cycle_count += 1

        try:
            # --- PRIORITY QUEUE FIRST ---
            # User-submitted URLs, prompts, and manual text are always processed
            # before RSS scanning so the user gets fast feedback.
            priority_count = process_priority_queue(api_client, recently_published)
            if priority_count:
                logger.info(f"⚡ Processed {priority_count} priority item(s)")

            # --- RSS CYCLE ---
            processed_hashes = r.smembers('processed_hashes')
            all_sources = load_json_file(SOURCES_FILE, [])
            all_directives = [d for topic in load_json_file(DIRECTIVES_FILE, [])
                              for key, value in topic.items() if isinstance(value, list) for d in value]

            if not all_sources or not all_directives:
                time.sleep(2)
                continue

            logger.info(f"📡 Cycle {cycle_count}: Scanning {SOURCE_BATCH_SIZE} sources...")
            candidates = []
            source_batch = get_next_source_batch(all_sources, SOURCE_BATCH_SIZE)

            for source in source_batch:
                try:
                    feed = feedparser.parse(source['url'])
                    if feed.bozo:
                        continue

                    entries_to_fetch = [
                        entry for entry in feed.entries[:3]
                        if all(hasattr(entry, attr) for attr in ['title', 'link']) and
                        entry.link.strip() and
                        get_article_hash(entry.title, "") not in processed_hashes
                    ]

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
                                    continue

                                article_text = article_data['text']
                                html_content = article_data.get('html_content', '')

                                is_quality, reason = assess_content_quality(article_text, html_content)
                                if not is_quality:
                                    logger.info(f"⛔ Skipping article: {reason}")
                                    continue

                                full_hash = get_article_hash(entry.title, article_text)
                                if full_hash in processed_hashes:
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
                                logger.info(f"✅ Candidate: {metadata['title'][:60]}")

                            except Exception as e:
                                logger.error(f"Error processing {entry.link}: {e}")
                                continue

                except Exception as e:
                    logger.error(f"Error processing source {source.get('name')}: {e}")
                    continue

            if not candidates:
                logger.info("No new articles found")
            else:
                logger.info(f"Found {len(candidates)} quality articles. Analyzing...")

                with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_ANALYZERS, len(candidates))) as executor:
                    future_to_cand = {
                        executor.submit(api_client.pre_analyze, cand['article_text']): cand
                        for cand in candidates
                    }

                    for future in future_to_cand:
                        cand = future_to_cand[future]
                        try:
                            result = future.result(timeout=3600)
                            cand['dossier'] = result or {'sentiment': 0.0}
                        except Exception as e:
                            logger.error(f"Analysis failed: {e}")
                            cand['dossier'] = {'sentiment': 0.0}

                target = find_best_target(candidates, all_directives, list(recently_published))
                if target:
                    success = publish_and_prepare_comments(target, recently_published, api_client)
                    if success:
                        r.sadd('processed_hashes', target['article']['article_hash'])
                else:
                    logger.info("No candidates matched directives")

            del candidates
            gc.collect()

            logger.info("💤 Cycle complete. Sleeping ten minutes ...")
            for _ in range(60):
                time.sleep(10)
                if r.llen(REDIS_PRIORITY_QUEUE_KEY) > 0:
                    break

        except Exception as e:
            logger.error(f"MAIN LOOP ERROR: {e}", exc_info=True)
            for _ in range(30):
                time.sleep(10)
                if r.llen(REDIS_PRIORITY_QUEUE_KEY) > 0:
                    break


if __name__ == "__main__":
    main()
