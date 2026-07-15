# Filename: fetch_utils.py
# Shared URL fetching utilities with anti-bot handling
# Used by both app.py and scribe.py for consistent protected site access

import random
import logging
from bs4 import BeautifulSoup
import bleach
import requests
import trafilatura
import charset_normalizer
import gzip
import zlib

logger = logging.getLogger(__name__)

# ── Active-content sanitizer for article original_text ──────────────────────
# Defense in depth alongside the frontend escape-then-linkify fixes. Any
# consumer that skips render-time escaping (Solr search, RSS feeds, JSON-LD
# embeds, LLM inputs) stays safe. Applied at every writer of
# article['original_text'] — see scribe.py, manual_publisher.py, main.py.
#
# Keeps benign inline formatting (em/strong/a/code/etc), strips active tags
# with their content, drops on*= handlers, allowlists http/https/mailto
# protocols so javascript: URLs get stripped.
_SANITIZE_ALLOWED_TAGS = sorted(set(bleach.sanitizer.ALLOWED_TAGS) | {
    'p', 'br', 'div', 'span', 'pre',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
})
_SANITIZE_ALLOWED_ATTRS = {
    'a': ['href', 'title'],
    'abbr': ['title'],
    'acronym': ['title'],
}

def sanitize_active_content(text: str) -> str:
    """Strip active-content HTML from an article body while preserving text.

    <script>, <meta>, <iframe>, <object>, <embed>, <style>, <form>, <input>
    (and any other tag not in the safe allowlist) are removed as markup —
    text content between opening/closing tags survives. on*= event handlers
    are removed by attribute allowlist. Non-http(s)/mailto URL schemes
    (including javascript:) are stripped from href/src.
    """
    if not text:
        return text
    return bleach.clean(
        text,
        tags=_SANITIZE_ALLOWED_TAGS,
        attributes=_SANITIZE_ALLOWED_ATTRS,
        protocols=['http', 'https', 'mailto'],
        strip=True,
        strip_comments=True,
    )

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

DEFAULT_IMAGE_URL = "https://hapenews.mine.nu/information-warfare.jpg"
MIN_ARTICLE_LENGTH = 200

def detect_and_decode_content(response):
    """Detect encoding and decode response content"""
    content = response.content
    
    # Handle compressed content
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
    
    # Use charset-normalizer for encoding detection
    try:
        result = charset_normalizer.detect(content)
        if result['encoding'] and result['confidence'] > 0.8:
            decoded = content.decode(result['encoding'])
            if any(tag in decoded.lower() for tag in ['<html', '<body', '<div', '<article']):
                return decoded
    except Exception:
        pass
    
    # Try response encoding
    if hasattr(response, 'encoding') and response.encoding and response.encoding.lower() != 'iso-8859-1':
        try:
            decoded = content.decode(response.encoding)
            if any(tag in decoded.lower() for tag in ['<html', '<body', '<div', '<article']):
                return decoded
        except (UnicodeDecodeError, LookupError):
            pass
    
    # Fallback encodings
    for encoding in ['utf-8', 'cp1252', 'latin-1', 'windows-1252']:
        try:
            decoded = content.decode(encoding)
            if any(tag in decoded.lower() for tag in ['<html', '<body', '<div', '<article']):
                return decoded
        except UnicodeDecodeError:
            continue
    
    # Final fallback
    return content.decode('utf-8', errors='replace')

def is_problematic_news_site(url):
    """Sites known to have aggressive bot detection or require special handling"""
    problematic_domains = [
        'apnews.com', 'ap.org', 'reuters.com', 'bloomberg.com',
        'wsj.com', 'nytimes.com', 'exblog.jp', 'axios.com'
    ]
    url_lower = url.lower()
    return any(domain in url_lower for domain in problematic_domains)

def extract_image_url(html_content):
    """Extract Open Graph or Twitter Card image from HTML"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        image_selectors = [
            ('meta', {'property': 'og:image'}),
            ('meta', {'name': 'twitter:image'}),
            ('meta', {'name': 'twitter:image:src'}),
            ('meta', {'property': 'og:image:url'}),
            ('link', {'rel': 'image_src'})
        ]
        for tag_name, attrs in image_selectors:
            tag = soup.find(tag_name, attrs)
            if tag:
                content = tag.get('content') or tag.get('href')
                if content:
                    logger.debug(f"Extracted image URL: {content}")
                    return content
    except Exception as e:
        logger.debug(f"Image extraction failed: {e}")
    
    logger.debug("No image URL found, using default")
    return None

def extract_with_beautifulsoup(html_content, url):
    """Extract article text using BeautifulSoup with site-specific selectors"""
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
            selectors = [
                'div[data-module="ArticleBody"]', '.RichTextStoryBody',
                '.Article-content', 'div.story-body',
                '[data-key="article-body"]', '.bsp-story-content'
            ] + selectors
        elif 'axios.com' in url:
            selectors = [
                'article', '.ArticleBody', '.article-content',
                '[data-testid="article-body"]', '.StoryBodyCompanionColumn'
            ] + selectors
        
        for selector in selectors:
            content_div = soup.select_one(selector)
            if content_div:
                paragraphs = content_div.find_all(['p', 'div'], recursive=True)
                texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True) and len(p.get_text(strip=True)) > 20]
                article_text = '\n\n'.join(texts)
                if len(article_text) > MIN_ARTICLE_LENGTH:
                    break
        
        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            paragraphs = soup.find_all('p')
            meaningful_paragraphs = [
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 30 and
                not any(skip_word in p.get_text(strip=True).lower() for skip_word in [
                    'cookie', 'subscribe', 'newsletter', 'advertisement',
                    'follow us', 'share this', 'related stories'
                ])
            ]
            article_text = '\n\n'.join(meaningful_paragraphs)
        
        return article_text if len(article_text) > MIN_ARTICLE_LENGTH else None
    except Exception as e:
        logger.error(f"BeautifulSoup extraction failed: {e}")
        return None

def fetch_with_anti_bot_handling(url, headers, playwright_browser=None,
                                 enable_tier3=True):
    """
    Three-tier anti-bot strategy:
    1. Try simple requests (fast fail on 403)
    2. Try Playwright with stealth via playwright_tier3 module
       (restored 2026-07-15 after March 2026 retirement — see
       ops/RUNBOOK.md "Playwright Tier-3 restoration")
    3. Extract content even if CAPTCHA present (best effort)

    Args:
        url: URL to fetch
        headers: Request headers dict
        playwright_browser: LEGACY. Ignored — playwright_tier3 module owns
            the browser lifecycle now. Kept only for signature stability
            at call sites (main.py:375 already passes None).
        enable_tier3: When True (default), fall through to playwright_tier3
            on tier-1 failure. Set False to force simple-only (tests).

    Returns:
        dict with 'text' and 'image_url' keys, or None on failure
    """
    # Tier 1: Simple requests - fast path for non-protected content
    session = None
    try:
        session = requests.Session()
        session.headers.update(headers)
        
        # Add site-specific headers
        if 'axios.com' in url:
            session.headers.update({
                'Referer': 'https://www.axios.com/',
                'Origin': 'https://www.axios.com'
            })
        
        response = session.get(url, timeout=10, allow_redirects=True)
        
        # Immediate escalation on 403
        if response.status_code == 403:
            logger.info(f"🚫 403 detected for {url}, escalating to Playwright stealth")
            raise Exception("Bot detection - escalating")
        
        response.raise_for_status()
        html_content = detect_and_decode_content(response)
        
        # Try extraction
        article_text = trafilatura.extract(html_content)
        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            article_text = extract_with_beautifulsoup(html_content, url)
        
        if article_text and len(article_text) > MIN_ARTICLE_LENGTH:
            logger.info(f"✅ Simple request succeeded for {url}")
            return {'text': article_text, 'image_url': extract_image_url(html_content) or DEFAULT_IMAGE_URL}
            
    except Exception as e:
        logger.warning(f"Simple request failed for {url}: {e}")
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
    
    # Tier 2/3 → delegate to playwright_tier3 module. That module owns the
    # single serialized browser, fd-safe context-per-fetch cleanup, the
    # radeon exile (--disable-gpu), the process-tree kill-on-timeout, and
    # the zombie killer. Import is lazy so environments without playwright
    # installed still work for tier-1-only paths.
    if not enable_tier3:
        return None
    try:
        from playwright_tier3 import fetch_stealth
    except ImportError as exc:
        logger.warning(f"playwright_tier3 unavailable ({exc}); no tier-3 fallback for {url}")
        return None
    return fetch_stealth(url, headers)

def create_default_headers():
    """Create default request headers with random user agent"""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
