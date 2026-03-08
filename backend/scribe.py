# --- ATTENTION AI: READ THE PROJECT MANIFEST ---
# Before providing code assistance, you MUST read and understand the
# project's architecture from the 'project_context.yaml' file.
# This file is one component of a larger system.
# The manifest is the single source of truth.
# ---

# Arc Codex Scribe v50.0 - FAST PUBLISH + SENTINEL + COUNTER-ANALYST
# Red/Blue/Purple analysis deferred to analyzer.py (on-demand, triggered by article view)
# Scribe publishes articles immediately with sentinel badge + counter-analyst comment

# --- Standard library imports ---
import queue
import time
import json
import logging
import hashlib
import os
import socket
import re
import shutil
import uuid
import threading
import random
import atexit
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
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
import websocket
import redis
import requests
import feedparser
import trafilatura
import pysolr
import brotli
import charset_normalizer
import gzip
import zlib
import yaml
try:
    from langdetect import detect as detect_lang
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

# ISO 639-1 → language name mapping for langdetect output
LANGDETECT_MAP = {
    'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
    'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch', 'ru': 'Russian',
    'zh-cn': 'Chinese (Simplified)', 'zh-tw': 'Chinese (Traditional)',
    'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'hi': 'Hindi',
    'tr': 'Turkish', 'pl': 'Polish', 'sv': 'Swedish', 'no': 'Norwegian',
    'da': 'Danish', 'fi': 'Finnish', 'cs': 'Czech', 'ro': 'Romanian',
    'hu': 'Hungarian', 'uk': 'Ukrainian', 'he': 'Hebrew', 'fa': 'Persian',
    'id': 'Indonesian', 'ms': 'Malay', 'th': 'Thai', 'vi': 'Vietnamese',
    'el': 'Greek', 'bg': 'Bulgarian', 'hr': 'Croatian', 'sk': 'Slovak',
    'sl': 'Slovenian', 'sr': 'Serbian', 'lt': 'Lithuanian', 'lv': 'Latvian',
    'et': 'Estonian', 'ca': 'Catalan', 'af': 'Afrikaans', 'sq': 'Albanian',
    'bn': 'Bengali', 'ur': 'Urdu', 'ta': 'Tamil', 'te': 'Telugu',
    'ml': 'Malayalam', 'sw': 'Swahili', 'tl': 'Filipino',
}

def detect_article_language(text: str) -> str:
    """Detect article language, returns language name string. Defaults to English."""
    if not LANGDETECT_AVAILABLE or not text or len(text) < 50:
        return 'English'
    try:
        code = detect_lang(text[:2000])  # sample first 2000 chars
        return LANGDETECT_MAP.get(code, 'English')
    except Exception:
        return 'English'


# Load environment variables
load_dotenv()

# Create a module logger
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
manual_upload_event = threading.Event()
REDIS_PRIORITY_QUEUE_KEY = "scribe:priority_uploads"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_BASE_URL = os.environ.get("SCRIBE_API_BASE_URL", "http://127.0.0.1:5005/api")
WS_URL = os.environ.get("SCRIBE_WS_URL", "ws://127.0.0.1:8765")
SOLR_URL = os.environ.get("SCRIBE_SOLR_URL", "http://localhost:8983/solr/feeds/")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "simplenes")
SCRIBE_SECRET_KEY = os.environ.get("SCRIBE_SECRET_KEY", "default_secret_for_dev")
# Category-based default images (using existing assets in /public)
DEFAULT_IMAGES = {
    'tech':      'https://arc-codex.com/tech-surveillance.jpg',
    'security':  'https://arc-codex.com/information-warfare.jpg',
    'economics': 'https://arc-codex.com/economic-control.jpg',
    'science':   'https://arc-codex.com/science-medical.jpg',
    'manual':    'https://arc-codex.com/manual-upload.jpg',
    'default':   'https://arc-codex.com/information-warfare.jpg',
}
DEFAULT_IMAGE_URL = DEFAULT_IMAGES['default']  # Backward compat for extract_image_url_enhanced


@lru_cache(maxsize=256)
def _classify(directive_name='', source_category=''):
    """Classify content into one of 5 canonical categories using keyword matching.
    
    Returns: 'threat_intelligence', 'tech_surveillance', 'economic_finance', 
             'science_health', or 'general'
    """
    combined = f"{directive_name} {source_category}".lower()
    
    # --- Explicit overrides for ambiguous terms ---
    if any(kw in combined for kw in ['biotech', 'biopharma', 'genomic']):
        return 'science_health'
    
    # --- THREAT INTELLIGENCE (check first - site's core mission) ---
    threat_keywords = [
        'threat', 'malware', 'vulnerab', 'exploit', 'phish', 'spam',
        'cyber', 'osint', 'disinformation', 'counterterror', 'homeland',
        'defense intel', 'defence intel', 'military', 'surveillance',
        'national security', 'breach', 'incident', 'ransomware',
        'adversary', 'zero-day', 'endpoint', 'hunting', 'apt',
        'geopolitical', 'conflict', 'sanction', 'enforcement',
        'law enforcement', 'watchdog', 'oversight', 'civil liberties',
        'hybrid threat', 'information warfare', 'intelligence',
        'security',  # broad catch-all — most "security" sources are infosec
    ]
    if any(kw in combined for kw in threat_keywords):
        return 'threat_intelligence'
    
    # --- TECH & SURVEILLANCE ---
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
    
    # --- ECONOMIC & FINANCE ---
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
    
    # --- SCIENCE & HEALTH ---
    science_keywords = [
        'science', 'medical', 'health', 'pharma', 'biotech',
        'genomic', 'biopharma', 'nuclear', 'climate',
        'renewable', 'solar', 'wind energy', 'battery',
        'demographic', 'existential risk',
    ]
    if any(kw in combined for kw in science_keywords):
        return 'science_health'
    
    return 'general'

# Map canonical categories to DEFAULT_IMAGES keys
_CATEGORY_TO_IMAGE_KEY = {
    'threat_intelligence': 'security',
    'tech_surveillance': 'tech',
    'economic_finance': 'economics',
    'science_health': 'science',
    'general': 'default',
}

def get_default_image(directive_name='', source_category=''):
    """Pick a contextual default image based on directive name and/or source category."""
    cat = _classify(directive_name, source_category)
    return DEFAULT_IMAGES[_CATEGORY_TO_IMAGE_KEY[cat]]

def get_canonical_category(directive_name='', source_category=''):
    """Return the canonical category ID for use in Redis filtering.
    
    Returns one of: 'threat_intelligence', 'tech_surveillance', 
    'economic_finance', 'science_health', 'general'
    """
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

# Ensemble pipeline
# Note: ensemble analysis moved to analyzer.py (on-demand)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

# Thread-local Playwright management
# sync_playwright uses greenlets internally and cannot be shared across threads.
# Each worker thread in the ThreadPoolExecutor gets its own isolated instance.
_thread_local = threading.local()
_all_browser_threads = []
_all_browser_lock = threading.Lock()
BROWSER_RECYCLE_INTERVAL = 20

def _close_thread_browser():
    """Close and clean up the current thread's browser instance."""
    browser = getattr(_thread_local, 'browser', None)
    pw = getattr(_thread_local, 'playwright', None)
    if browser:
        try:
            browser.close()
        except Exception:
            pass
        _thread_local.browser = None
    if pw:
        try:
            pw.stop()
        except Exception:
            pass
        _thread_local.playwright = None
    _thread_local.browser_use_count = 0

# --- INITIALIZATION ---
log_formatter = logging.Formatter('%(asctime)s - [SCRIBE v50.0] - %(levelname)s - %(message)s')
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
    except:
        pass
    
    # Clean RSS-style names
    cleaned = source_name
    cleaned = re.sub(r'\s*-\s*RSS.*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\|\s*RSS.*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\(RSS\).*', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    
    return cleaned if cleaned else source_name

def clean_article_metadata(title, html_content=None):
    """Clean and enhance article metadata for professional display"""
    # Clean title — strip any HTML tags (some RSS feeds emit raw HTML in title)
    try:
        cleaned_title = BeautifulSoup(unescape(title), 'html.parser').get_text()
    except Exception:
        cleaned_title = unescape(title)
    
    # Remove site name suffixes
    suffixes = [
        r'\s*[-|–—]\s*.{1,40}$',
        r'\s*\|\s*.{1,40}$',
    ]
    for pattern in suffixes:
        cleaned_title = re.sub(pattern, '', cleaned_title)
    
    # Remove excessive emoji
    emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F]', cleaned_title))
    if emoji_count > 3:
        cleaned_title = re.sub(r'[\U0001F600-\U0001F64F]', '', cleaned_title)
    
    # Fix ALL CAPS titles
    if sum(1 for c in cleaned_title if c.isupper()) / max(len(cleaned_title), 1) > 0.7:
        cleaned_title = cleaned_title.title()
    
    cleaned_title = ' '.join(cleaned_title.split())
    
    # Extract description and reading time if HTML provided
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
        except:
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
    
    # Strategy 1: Social media meta tags (highest priority)
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
    
    # Strategy 2: Article hero images
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
    
    # Strategy 3: High-res images in content
    all_imgs = soup.find_all('img', src=True)
    for img in all_imgs:
        src = img.get('src', '')
        width = img.get('width', 0)
        height = img.get('height', 0)
        
        try:
            if width and height and (int(width) < 300 or int(height) < 200):
                continue
        except:
            pass
        
        skip_patterns = ['logo', 'icon', 'avatar', 'placeholder', 'loading', 'pixel', 'ad', 'banner']
        if any(pattern in src.lower() for pattern in skip_patterns):
            continue
        
        candidates.append(('content', src, 50))
    
    if candidates:
        candidates.sort(key=lambda x: x[2], reverse=True)
        best_img = candidates[0][1]
        
        # Make URL absolute
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
    
    # Check for paywalls
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
    
    # Check for low-quality listicles
    listicle_pattern = r'\d+\s+(things|ways|reasons|facts|tips|tricks|secrets)\s+(?:you|that)'
    if re.search(listicle_pattern, text_lower) and len(article_text) < 800:
        return (False, "low_quality_listicle")
    
    # Check for auto-generated content
    auto_gen_markers = [
        'this article was automatically generated',
        'powered by ai',
        'generated by machine',
    ]
    if any(marker in text_lower for marker in auto_gen_markers):
        return (False, "auto_generated")
    
    return (True, "acceptable")

# --- BROWSER MANAGEMENT ---

def get_thread_browser():
    """Get or create a Playwright browser for the current thread.
    
    Each thread in the ThreadPoolExecutor gets its own playwright + browser
    instance. sync_playwright uses greenlets internally and cannot be shared
    across thread boundaries — this is the correct pattern for threaded use.
    """
    use_count = getattr(_thread_local, 'browser_use_count', 0)
    if getattr(_thread_local, 'browser', None) and use_count >= BROWSER_RECYCLE_INTERVAL:
        logger.info(f"♻️  Recycling browser after {use_count} uses ({threading.current_thread().name})")
        _close_thread_browser()
    if not getattr(_thread_local, 'browser', None):
        logger.info(f"🎭 Initializing Playwright for thread {threading.current_thread().name}")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--memory-pressure-off',
                '--max_old_space_size=256'
            ]
        )
        _thread_local.playwright = pw
        _thread_local.browser = browser
        _thread_local.browser_use_count = 0
        # Register for cleanup at process exit
        with _all_browser_lock:
            _all_browser_threads.append(_thread_local)

    _thread_local.browser_use_count = getattr(_thread_local, 'browser_use_count', 0) + 1
    return _thread_local.browser


def cleanup_all_browsers():
    """Clean up all thread-local Playwright resources at process exit."""
    with _all_browser_lock:
        for tl in _all_browser_threads:
            browser = getattr(tl, 'browser', None)
            pw = getattr(tl, 'playwright', None)
            try:
                if browser:
                    browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            try:
                if pw:
                    pw.stop()
            except Exception as e:
                logger.warning(f"Error stopping Playwright: {e}")
            tl.browser = None
            tl.playwright = None

atexit.register(cleanup_all_browsers)

# --- UTILITY FUNCTIONS ---

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

def detect_and_decode_content(response):
    """Handle compressed and encoded content intelligently"""
    content = response.content
    
    # Handle compression
    if len(content) > 0 and content[:3] == b'\x1f\x8b\x08':
        try:
            content = gzip.decompress(content)
        except:
            pass
    elif len(content) > 0 and content[:2] == b'\x78\x9c':
        try:
            content = zlib.decompress(content)
        except:
            pass
    
    # Use charset-normalizer for encoding detection
    try:
        result = charset_normalizer.detect(content)
        if result['encoding'] and result['confidence'] > 0.8:
            decoded = content.decode(result['encoding'])
            if any(tag in decoded.lower() for tag in ['<html', '<body', '<div', '<article']):
                return decoded
    except:
        pass
    
    # Fallback encodings
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
        
        # Site-specific selectors
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

# --- CONTENT FETCHING ---

def fetch_with_anti_bot_handling(url, headers):
    """Three-tier anti-bot strategy with stealth"""
    # Tier 1: Simple requests
    session = None
    try:
        session = requests.Session()
        session.headers.update(headers)
        
        if 'axios.com' in url:
            session.headers.update({
                'Referer': 'https://www.axios.com/',
                'Origin': 'https://www.axios.com'
            })
        
        response = session.get(url, timeout=10, allow_redirects=True)
        
        if response.status_code == 403:
            logger.info(f"🚫 403 detected for {url}, escalating to Playwright")
            raise Exception("Bot detection - escalating")
        
        response.raise_for_status()
        html_content = detect_and_decode_content(response)
        
        article_text = trafilatura.extract(html_content)
        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            article_text = extract_with_beautifulsoup(html_content, url)
        
        if article_text and len(article_text) > MIN_ARTICLE_LENGTH:
            logger.info(f"✅ Simple request succeeded for {url}")
            return {
                'text': article_text,
                'image_url': extract_image_url_enhanced(html_content, url),
                'html_content': html_content
            }
    except Exception as e:
        logger.warning(f"Simple request failed for {url}: {e}")
    finally:
        if session:
            try:
                session.close()
            except:
                pass
    
    # Tier 2: Playwright with stealth
    logger.info(f"🎭 Attempting Playwright stealth extraction for {url}")
    browser = get_thread_browser()
    context = None
    page = None
    
    try:
        context = browser.new_context(
            user_agent=headers.get('User-Agent', random.choice(USER_AGENTS)),
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers=headers
        )
        
        # Inject stealth scripts
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            window.chrome = { runtime: {} };
        """)
        
        page = context.new_page()
        page.goto(url, wait_until='load', timeout=15000)
        page.wait_for_timeout(2000)
        
        html_content = page.content()
        
        article_text = trafilatura.extract(html_content)
        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            article_text = extract_with_beautifulsoup(html_content, url)
        
        if article_text and len(article_text) > MIN_ARTICLE_LENGTH:
            has_captcha = 'captcha' in html_content.lower() or 'cloudflare' in html_content.lower()
            if has_captcha:
                logger.warning(f"⚠️  CAPTCHA detected but extracted {len(article_text)} chars from {url}")
            else:
                logger.info(f"✅ Playwright stealth succeeded for {url}")
            
            return {
                'text': article_text,
                'image_url': extract_image_url_enhanced(html_content, url),
                'html_content': html_content
            }
        
        logger.warning(f"❌ No usable content extracted from {url}")
        return None
        
    except Exception as e:
        logger.error(f"Playwright stealth failed for {url}: {e}")
        return None
    finally:
        if page:
            try:
                page.close()
            except:
                pass
        if context:
            try:
                context.close()
            except:
                pass

def fetch_article_data(url):
    """Main article fetching function with quality enhancements"""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    # Use anti-bot handling for problematic sites
    if is_problematic_news_site(url):
        logger.info(f"🛡️  Detected protected site: {url}")
        return fetch_with_anti_bot_handling(url, headers)
    
    # Standard path
    session = None
    try:
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(url, timeout=NETWORK_TIMEOUT_SECONDS, allow_redirects=True)
        response.raise_for_status()
        html_content = detect_and_decode_content(response)
        
        if not html_content or len(html_content) < 100:
            raise Exception("Content too short or empty")
        
        article_text = trafilatura.extract(html_content)
        if article_text and len(article_text) > MIN_ARTICLE_LENGTH:
            logger.info(f"✅ Standard extraction succeeded for {url}")
            return {
                'text': article_text,
                'image_url': extract_image_url_enhanced(html_content, url),
                'html_content': html_content
            }
    except Exception as e:
        logger.warning(f"Standard request failed for {url}: {e}")
    finally:
        if session:
            try:
                session.close()
            except:
                pass
    
    # Fallback to anti-bot handling
    return fetch_with_anti_bot_handling(url, headers)

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

# --- OLLAMA FUNCTIONS ---

# NOTE: build_unified_prompt_from_yaml() and ensemble analysis moved to analyzer.py
# Scribe now publishes fast, analyzer runs on-demand when articles are viewed.




def _repair_sentinel_json(raw: str) -> dict | None:
    """Attempt to parse or repair JSON from sentinel output.
    
    Small models (3B-7B) often produce JSON with:
    - Unescaped newlines/quotes inside string values
    - Missing commas between fields
    - Trailing commas before closing braces
    - Commentary before/after the JSON block
    
    Strategy: try strict parse first, then repair, then regex fallback.
    """
    # Step 0: Strip markdown fencing
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

    # Step 1: Extract just the JSON object (skip any preamble/postamble)
    brace_match = re.search(r'\{[\s\S]*\}', cleaned)
    if not brace_match:
        return None
    json_str = brace_match.group(0)

    # Step 2: Try strict parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Step 3: Repair common issues
    repaired = json_str
    # Fix unescaped newlines inside strings by collapsing to spaces
    repaired = re.sub(r'(?<=": ")(.*?)(?="[,\s}])', 
                      lambda m: m.group(0).replace('\n', ' ').replace('\r', ''), 
                      repaired, flags=re.DOTALL)
    # Fix trailing commas before } or ]
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    # Fix missing commas between "key": "value" pairs
    repaired = re.sub(r'"\s*\n\s*"', '",\n"', repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Step 3.5: Strip problematic nested arrays entirely, keep top-level fields
    try:
        stripped = re.sub(r'"indicators"\s*:\s*\[.*?\]', '"indicators": []', json_str, flags=re.DOTALL)
        stripped = re.sub(r'"human_signals"\s*:\s*\[.*?\]', '"human_signals": []', stripped, flags=re.DOTALL)
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Step 4: Regex fallback — extract the three required fields
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
    """Run the Sentinel forensic pass independently of the ensemble pipeline.
    
    Returns parsed JSON dict on success, None on failure.
    Sentinel detects AI-generated/synthetic content indicators.
    """
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

        # Validate expected keys
        required_keys = {'synthetic_confidence', 'assessment', 'summary'}
        if not required_keys.issubset(sentinel_data.keys()):
            logger.warning(f"⚠️  Sentinel response missing keys: {required_keys - sentinel_data.keys()}")
            return None

        # Clamp confidence to valid range
        conf = sentinel_data.get('synthetic_confidence', 0.0)
        sentinel_data['synthetic_confidence'] = max(0.0, min(1.0, float(conf)))

        # Validate assessment enum
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
    """Generate a devil's advocate comment and post it directly to Redis.
    
    Returns True if comment was posted, False otherwise.
    Non-fatal — article publishes even if this fails.
    """
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

        # Clean up response — strip any prefixes the model might add
        comment_text = raw_response.strip()
        # Remove common AI prefixes
        for prefix in ['Counter-argument:', 'Counter-Argument:', 'As an AI', 'Here is']:
            if comment_text.startswith(prefix):
                comment_text = comment_text[len(prefix):].strip()
                if comment_text.startswith(':'):
                    comment_text = comment_text[1:].strip()

        # Validate: should be 1-4 sentences, not a novel
        if len(comment_text) < 20:
            logger.warning(f"⚠️  Counter-analyst response too short ({len(comment_text)} chars)")
            return False
        if len(comment_text) > 2000:
            # Truncate to ~4 sentences
            sentences = comment_text.split('. ')
            comment_text = '. '.join(sentences[:4])
            if not comment_text.endswith('.') and not comment_text.endswith('?'):
                comment_text += '.'

        # Post as comment directly to Redis
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
    """Publish article and generate analysis"""
    article = target.get('article', {})
    directive = target.get('directive', {})
    article_id = article.get('article_hash')

    if not article or not article_id:
        return False

    if r.sismember('processed_hashes', article_id):
        logger.info(f"Article {article_id} already processed")
        return True

    logger.info(f"📰 Publishing: '{article.get('title', 'Untitled')}'")

    # If the article image is still the generic fallback, swap in a
    # category-appropriate default using both directive name and source category
    current_image = article.get('imageUrl', DEFAULT_IMAGE_URL)
    if current_image == DEFAULT_IMAGE_URL:
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
        'source_lang': detect_article_language(article.get('article_text', ''))
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
            'chimera_score': dossier_data.get('chimera_score', 0.0)
        }
        try:
            solr.add([solr_doc])
            solr.commit()
            logger.info(f"✅ Indexed in Solr: {article_id}")
        except Exception as e:
            logger.warning(f"Solr indexing failed: {e}")

    # --- SENTINEL FORENSIC PASS (fast, independent) ---
    text_for_analysis = article.get('article_text', '')
    try:
        sentinel_data = run_sentinel_analysis(text_for_analysis)
        if sentinel_data:
            publish_analysis(r, article_id, 'sentinel', json.dumps(sentinel_data))
            logger.info(f"🛡️  Sentinel published for {article_id}")
    except Exception as e:
        logger.warning(f"🛡️  Sentinel pass failed (non-fatal): {e}")

    # --- COUNTER-ANALYST COMMENT (seeds discussion) ---
    try:
        run_counter_analyst(text_for_analysis, article_id)
    except Exception as e:
        logger.warning(f"🤖 Counter-analyst failed (non-fatal): {e}")

    # Red/Blue/Purple analysis is NOT queued here.
    # It triggers on-demand when someone views the article (via app.py → analyzer.py)
 
    if directive.get('name'):
        recently_published.append(directive['name'])

    return True

def main():
    logger.info("🚀 Arc Codex Scribe v50.0 - FAST PUBLISH + SENTINEL + COUNTER-ANALYST")
    logger.info(f"📡 Models: {OLLAMA_CLOUD_MODEL} → {OLLAMA_LOCAL_FALLBACK}")
    logger.info(f"📋 Red/Blue/Purple analysis deferred to analyzer.py (on-demand)")
    api_client = APIClient(API_BASE_URL, SCRIBE_SECRET_KEY)
    
    initialize_directories()
    socket.setdefaulttimeout(NETWORK_TIMEOUT_SECONDS)
    recently_published = deque(maxlen=RECENTLY_PUBLISHED_MEMORY)
    
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            
            try:
                processed_hashes = r.smembers('processed_hashes')
                all_sources = load_json_file(SOURCES_FILE, [])
                all_directives = [d for topic in load_json_file(DIRECTIVES_FILE, []) 
                                for key, value in topic.items() if isinstance(value, list) for d in value]
                
                if not all_sources or not all_directives:
                    time.sleep(0)
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
                                    
                                    # Quality gate
                                    is_quality, reason = assess_content_quality(article_text, html_content)
                                    if not is_quality:
                                        logger.info(f"⛔ Skipping article: {reason}")
                                        continue
                                    
                                    full_hash = get_article_hash(entry.title, article_text)
                                    if full_hash in processed_hashes:
                                        continue
                                    
                                    # Clean metadata
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
                
                # Cleanup
                del candidates
                gc.collect()
                
                logger.info("💤 Cycle complete. Sleeping one thousand seconds ...")
                time.sleep(1000)
                
            except Exception as e:
                logger.error(f"MAIN LOOP ERROR: {e}", exc_info=True)
                # Clear this thread's browser so it reinitializes on next use
                _thread_local.browser = None
                _thread_local.playwright = None
                time.sleep(300)
                
    finally:
        cleanup_all_browsers()

if __name__ == "__main__":
    main()
