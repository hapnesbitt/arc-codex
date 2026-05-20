# Filename: /home/www/arc_stack/backend/main.py
# Arc Codex API Engine v50
# Refactored: removed /api/stm, call_ollama(), /api/me (pre-Auth.js remnants),
#             duplicate Bluesky constants, fixed get_stats() ghost-hash bug,
#             fixed upload_image() EXIF orientation (iPhone portrait rotation)

import io
import pypdf
import docx
from rss_feed import rss_blueprint, init_rss
from odf.opendocument import load as odf_load
from odf import text as odf_text
from pypdf import PdfReader
import os
import datetime
import time
from flask import Flask, request, jsonify, Response, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import redis
import re
import logging
import json
import spacy
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import nltk
import textstat
from textblob import TextBlob
import uuid
import threading
import requests
import html2text
import trafilatura
import yaml
import pysolr
from dotenv import load_dotenv

# NEW: Import anti-bot utilities
from fetch_utils import (
    fetch_with_anti_bot_handling,
    is_problematic_news_site,
    create_default_headers,
    DEFAULT_IMAGE_URL as FETCH_UTILS_DEFAULT_IMAGE
)
from catalog_loader import load_catalog

load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(32))
# Shared session cookie — must match LightBox (vid.arc-codex.com) config
# app.config['SESSION_COOKIE_DOMAIN'] = '.arc-codex.com'  # removed 2026-05-16 — Safari ITP rejects parent-domain cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.logger.setLevel(logging.INFO)

# --- CONFIGURATION & INITIALIZATION ---
SCRIBE_SECRET_KEY = os.getenv("SCRIBE_SECRET_KEY")
REDIS_URL = os.getenv("REDIS_URL")
MAX_CONTENT_CHARS = 60000  # Unified truncation limit for stored article text
DEFAULT_IMAGE_URL = "https://arc-codex.com/information-warfare.jpg"
PROMPTS = {}

try:
    with open('prompts.yaml', 'r') as f:
        PROMPTS = yaml.safe_load(f)
    app.logger.info("✅ Successfully loaded prompts from prompts.yaml.")
except Exception as e:
    app.logger.critical(f"🔥 PROMPTS FAILED TO LOAD: {e}")

r = None
if REDIS_URL:
    try:
        start_redis = time.perf_counter()
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        app.register_blueprint(rss_blueprint)
        init_rss(r)
        from translation import translation_bp
        app.register_blueprint(translation_bp)
        from grade import grade_bp
        app.register_blueprint(grade_bp)
        from user_prefs import user_prefs_bp
        app.register_blueprint(user_prefs_bp)
        from auth import auth_bp, init_auth
        app.register_blueprint(auth_bp)
        init_auth(app,
            redis_password=os.getenv("REDIS_PASSWORD"),
            domain=os.getenv("DOMAIN", "arc-codex.com"),
            from_addr=os.getenv("MAIL_FROM", "ross@arc-codex.com"))
        redis_duration = (time.perf_counter() - start_redis) * 1000
        app.logger.info(f"✅ Successfully connected to Redis in {redis_duration:.2f}ms")
    except Exception as e:
        app.logger.critical(f"🔥 REDIS FAILED TO CONNECT: {e}")
else:
    app.logger.critical("🔥 REDIS_URL not set in .env file.")

NLP_PROCESSOR, SENTIMENT_ANALYZER, AI_BACKEND = None, None, None
try:
    NLP_PROCESSOR = spacy.load("en_core_web_sm")
    try:
        nltk.data.find('sentiment/vader_lexicon.zip')
    except:
        nltk.download('vader_lexicon', quiet=True)
    SENTIMENT_ANALYZER = SentimentIntensityAnalyzer()
    AI_BACKEND = "ollama"
    app.logger.info(f"✅ Arc Codex API Engine: NLP initialized. AI Backend: {AI_BACKEND}")
except Exception as e:
    app.logger.error(f"🔥 Model Initialization FAILED: {e}")

# --- SOLR CONNECTION ---
SOLR_URL = os.getenv("SOLR_URL", "http://localhost:8983/solr/feeds/")

# --- BLUESKY CONFIG ---
BLUESKY_HANDLE       = os.getenv("BLUESKY_HANDLE", "hapenez.bsky.social")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD", "")
BLUESKY_API_BASE     = "https://bsky.social/xrpc"

solr = None
try:
    solr = pysolr.Solr(SOLR_URL)
    solr.ping()
    app.logger.info("✅ Solr connection established.")
except Exception as e:
    solr = None
    app.logger.warning(f"⚠️  Solr connection failed — search disabled: {e}")

# --- HELPER: safe truncation for logging ---
def safe_truncate(text, max_len=200):
    """Safely truncate text for logging, handling unicode properly."""
    if not text:
        return ""
    text_str = str(text)
    if len(text_str) <= max_len:
        return text_str
    return text_str[:max_len] + "..."

# --- HELPER: classify reading level for transparency ---
def classify_reading_level(grade):
    """
    Convert Flesch-Kincaid grade level to human-readable category.
    Provides transparency without penalizing technical writing.
    """
    if grade < 6:
        return "elementary"
    elif grade < 9:
        return "middle_school"
    elif grade < 13:
        return "high_school"
    elif grade < 16:
        return "college"
    elif grade < 18:
        return "graduate"
    else:
        return "technical"

# --- HELPER: robust URL fetching with anti-bot handling ---
def fetch_and_process_url(url):
    """
    Fetches content from a URL with anti-bot handling for protected sites,
    then extracts the main article text using trafilatura for HTML or pypdf for PDFs.
    Returns a tuple: (success, content_or_error_message)
    """
    headers = create_default_headers()
    
    try:
        fetch_start = time.perf_counter()
        app.logger.info(f"⬇️  Fetching URL: {url}")
        
        # Check if this is a problematic site that needs anti-bot handling
        if is_problematic_news_site(url):
            app.logger.info(f"🛡️  Detected protected site, using anti-bot extraction: {url}")
            # Note: app.py doesn't have Playwright initialized, so pass None
            # This will attempt simple request then fail gracefully
            result = fetch_with_anti_bot_handling(url, headers, playwright_browser=None)
            
            if result:
                fetch_duration = (time.perf_counter() - fetch_start) * 1000
                app.logger.info(f"✅ Anti-bot fetch complete in {fetch_duration:.0f}ms - {len(result['text'])} chars")
                return (True, result['text'])
            else:
                # If anti-bot fails without Playwright, return helpful error
                return (False, "This site requires advanced access. The URL submission system currently supports simpler sites. Try pasting the article text directly instead.")
        
        # Standard path for non-protected sites
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        fetch_duration = (time.perf_counter() - fetch_start) * 1000

        # Check if the content is a PDF
        content_type = response.headers.get('Content-Type', '').lower()
        is_pdf = 'application/pdf' in content_type or url.lower().endswith('.pdf')

        extract_start = time.perf_counter()
        
        if is_pdf:
            # Handle PDF content
            app.logger.info(f"📄 Detected PDF content, extracting text...")
            try:
                pdf_file = io.BytesIO(response.content)
                pdf_reader = PdfReader(pdf_file)
                
                page_texts = []
                for page_num in range(len(pdf_reader.pages)):
                    page_texts.append(pdf_reader.pages[page_num].extract_text() or '')
                    # Stop early if raw accumulation already exceeds limit (saves memory)
                    if sum(len(t) for t in page_texts) > MAX_CONTENT_CHARS * 2:
                        app.logger.warning(f"⚠️  PDF extraction stopped at page {page_num+1} - size limit reached")
                        break

                extracted_text = _normalize_pdf_text('\n\n'.join(page_texts))

                if not extracted_text:
                    app.logger.warning(f"⚠️  PDF text extraction returned empty content")
                    return (False, "The PDF appears to be empty or contains only images. Text extraction failed.")

                # Truncate if needed
                if len(extracted_text) > MAX_CONTENT_CHARS:
                    app.logger.warning(f"⚠️  PDF text truncated from {len(extracted_text)} to {MAX_CONTENT_CHARS} chars")
                    extracted_text = extracted_text[:MAX_CONTENT_CHARS]

                extract_duration = (time.perf_counter() - extract_start) * 1000
                total_duration = fetch_duration + extract_duration

                app.logger.info(f"✅ PDF extraction complete in {extract_duration:.0f}ms (fetch: {fetch_duration:.0f}ms, total: {total_duration:.0f}ms) - {len(extracted_text)} chars")
                return (True, extracted_text)
                
            except Exception as pdf_error:
                app.logger.error(f"🔥 PDF extraction failed: {pdf_error}")
                return (False, f"Failed to extract text from PDF: {str(pdf_error)}")
        
        else:
            # Handle HTML content
            extracted_text = trafilatura.extract(response.content, include_comments=False, deduplicate=True)

            if not extracted_text:
                app.logger.warning(f"⚠️  trafilatura failed for {url}. Falling back to html2text.")
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                extracted_text = h.handle(response.text)
            
            extract_duration = (time.perf_counter() - extract_start) * 1000
            total_duration = fetch_duration + extract_duration
            
            app.logger.info(f"✅ URL fetch complete in {fetch_duration:.0f}ms (extract: {extract_duration:.0f}ms, total: {total_duration:.0f}ms) - {len(extracted_text)} chars")
            return (True, extracted_text)

    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error fetching URL: {e.response.status_code} {e.response.reason}"
        app.logger.error(f"🔥 {error_msg} for url: {url}")
        
        # Better error message for 403
        if e.response.status_code == 403:
            return (False, f"The website returned an error (403). They may be blocking automated access. Try copying the article text directly instead.")
        
        return (False, f"The website returned an error ({e.response.status_code}). They may be blocking automated access.")
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {e}"
        app.logger.error(f"🔥 {error_msg} for url: {url}")
        return (False, "Could not connect to the website. It might be offline or blocking our connection.")


# --- API ENDPOINTS ---
@app.route('/api/publish_article', methods=['POST'])
def publish_article():
    if not r: 
        app.logger.error("🔥 Redis unavailable for publish_article")
        return jsonify({"error": "Database connection is offline."}), 503
    
    if request.headers.get('X-Scribe-Secret') != SCRIBE_SECRET_KEY:
        app.logger.warning(f"⚠️  Unauthorized publish attempt. Provided key: {request.headers.get('X-Scribe-Secret')}")
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    required_fields = ['id', 'title', 'timestamp', 'original_text']
    if not all(field in data for field in required_fields):
        app.logger.warning(f"⚠️  Missing required fields in publish_article")
        return jsonify({"error": "Missing required fields."}), 400
    
    article_id = data['id']
    if r.sismember('processed_hashes', article_id):
        app.logger.info(f"📌 Duplicate article skipped: {article_id}")
        return jsonify({"success": True, "message": "Duplicate, skipped."}), 200
    
    try:
        redis_start = time.perf_counter()
        article_data = {k: v for k, v in data.items() if v is not None}
        if 'dossier' in article_data and isinstance(article_data['dossier'], dict):
            article_data['dossier'] = json.dumps(article_data['dossier'])
        pipe = r.pipeline()
        pipe.hset(f"article:{article_id}", mapping=article_data)
        pipe.zadd('feed', {article_id: int(time.time())})
        pipe.sadd('processed_hashes', article_id)
        pipe.execute()
        redis_duration = (time.perf_counter() - redis_start) * 1000
        
        app.logger.info(f"✅ Published article '{data['title']}' to Redis (ID: {article_id}) in {redis_duration:.2f}ms")
        return jsonify({"success": True, "message": "Article published."}), 201
    except Exception as e:
        app.logger.error(f"🔥 Failed to publish article to Redis: {e}", exc_info=True)
        return jsonify({"error": "Failed to save article."}), 500

@app.route('/api/get_feed', methods=['GET'])
def get_feed():
    if not r: 
        app.logger.error("🔥 Redis unavailable for get_feed")
        return jsonify({"error": "Database connection is offline."}), 503
    
    limit = request.args.get('limit', 33, type=int)
    offset = request.args.get('offset', 0, type=int)
    category_filter  = request.args.get('category', '', type=str).strip()
    directive_filter = request.args.get('directive', '', type=str).strip()
    
    try:
        redis_start = time.perf_counter()
        
        if not category_filter and not directive_filter:
            # --- UNFILTERED: original fast path (unchanged) ---
            article_ids = r.zrevrange('feed', offset, offset + limit - 1)
            if not article_ids: 
                app.logger.info(f"📭 Feed query returned 0 articles (offset: {offset}, limit: {limit})")
                return jsonify([])
            
            pipe = r.pipeline()
            for article_id in article_ids: 
                pipe.hgetall(f"article:{article_id}")
            for article_id in article_ids:
                pipe.smembers(f"translation:langs:{article_id}")
            pipe_results = pipe.execute()
            feed_data = pipe_results[:len(article_ids)]
            langs_data = pipe_results[len(article_ids):]
        else:
            # --- FILTERED: scan in batches, collect matches ---
            # offset = how many matching articles to skip
            # limit = how many matching articles to return
            BATCH_SIZE = 100
            matched_ids = []
            skipped = 0
            cursor = 0
            total_feed = r.zcard('feed')
            
            while len(matched_ids) < limit and cursor < total_feed:
                batch_ids = r.zrevrange('feed', cursor, cursor + BATCH_SIZE - 1)
                if not batch_ids:
                    break
                
                # Pipeline-fetch just the category field for this batch
                pipe = r.pipeline()
                for aid in batch_ids:
                    pipe.hget(f"article:{aid}", 'directive' if directive_filter else 'category')
                categories = pipe.execute()
                
                for aid, cat_or_dir in zip(batch_ids, categories):
                    if directive_filter:
                        match = (cat_or_dir or '') == directive_filter
                    else:
                        match = (cat_or_dir or 'general') == category_filter
                    if match:
                        if skipped < offset:
                            skipped += 1
                        else:
                            matched_ids.append(aid)
                            if len(matched_ids) >= limit:
                                break
                
                cursor += BATCH_SIZE
            
            if not matched_ids:
                app.logger.info(f"📭 Feed query returned 0 articles (category: {category_filter}, offset: {offset})")
                return jsonify([])
            
            # Fetch full data for matched articles only
            pipe = r.pipeline()
            for article_id in matched_ids:
                pipe.hgetall(f"article:{article_id}")
            for article_id in matched_ids:
                pipe.smembers(f"translation:langs:{article_id}")
            pipe_results = pipe.execute()
            feed_data = pipe_results[:len(matched_ids)]
            langs_data = pipe_results[len(matched_ids):]
        
        redis_duration = (time.perf_counter() - redis_start) * 1000
        
        requesting_user = request.headers.get('X-User-Id') or session.get('username', '')
        formatted_feed = []
        for item, langs in zip(feed_data, langs_data):
            if item:
                # Filter private articles — only show to owner
                if item.get('visibility') == 'private' and item.get('owner', '') != requesting_user:
                    continue
                try:
                    item['dossier'] = json.loads(item.get('dossier', '{}'))
                except (json.JSONDecodeError, ValueError):
                    item['dossier'] = {}
                item['cached_langs'] = list(langs) if langs else []
                formatted_feed.append(item)

        filter_info = f", category: {category_filter}" if category_filter else ""
        app.logger.info(f"✅ Retrieved {len(formatted_feed)} articles from feed in {redis_duration:.2f}ms{filter_info}")
        return jsonify(formatted_feed)
    except Exception as e:
        app.logger.error(f"🔥 Error retrieving feed: {e}", exc_info=True)
        return jsonify({"error": f"Could not retrieve feed: {e}"}), 500

@app.route('/api/article/<article_id>', methods=['GET'])
def get_single_article(article_id):
    if not r:
        app.logger.error("🔥 Redis unavailable for get_single_article")
        return jsonify({"error": "Database connection is offline."}), 503
    try:
        redis_start = time.perf_counter()
        article_data = r.hgetall(f"article:{article_id}")
        if not article_data:
            article_ids = r.zrevrange('feed', 0, -1)
            for aid in article_ids:
                temp_data = r.hgetall(f"article:{aid}")
                if (temp_data.get('slug') == article_id or temp_data.get('id') == article_id or aid == article_id):
                    article_data = temp_data
                    break
        redis_duration = (time.perf_counter() - redis_start) * 1000
        
        if not article_data:
            app.logger.warning(f"⚠️  Article not found: {article_id}")
            return jsonify({'error': 'Article not found'}), 404
        
        try:
            article_data['dossier'] = json.loads(article_data.get('dossier', '{}'))
        except (json.JSONDecodeError, ValueError):
            article_data['dossier'] = {}
        
        # --- ON-DEMAND ANALYSIS TRIGGER ---
        # Queue for analyzer.py if any of the three analyses are missing or incomplete.
        # Check all three — a partial run (e.g. only blue_team written due to a truncated
        # Ollama response) must re-queue so red and purple are filled.
        blue_analysis = article_data.get('blue_team_analysis', '')
        red_analysis = article_data.get('red_team_analysis', '')
        purple_analysis = article_data.get('purple_team_analysis', '')
        if not (len(blue_analysis) > 10 and len(red_analysis) > 10 and len(purple_analysis) > 10):
            actual_id = article_data.get('id', article_id)
            try:
                # Only queue if not already queued recently (simple dedup)
                queue_key = f"analyzer:queued:{actual_id}"
                if not r.exists(queue_key):
                    r.lpush('analyzer:queue', actual_id)
                    r.setex(queue_key, 300, '1')  # 5-minute dedup window
                    app.logger.info(f"📋 Queued {actual_id} for on-demand analysis")
            except Exception as e:
                app.logger.warning(f"⚠️  Failed to queue analysis trigger: {e}")
        
        actual_id = article_data.get('id', article_id)
        article_data['cached_langs'] = list(r.smembers(f"translation:langs:{actual_id}"))

        app.logger.info(f"✅ Retrieved article {article_id} in {redis_duration:.2f}ms")
        return jsonify(article_data)
    except Exception as e:
        app.logger.error(f"🔥 Error fetching article {article_id}: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/search', methods=['GET'])
def search_articles():
    """Full-text search via Solr. Returns matching articles with highlighted snippets."""
    global solr
    if not solr:
        try:
            solr = pysolr.Solr(SOLR_URL)
            solr.ping()
            app.logger.info("✅ Solr reconnected (lazy)")
        except Exception as e:
            app.logger.error(f"🔥 Solr unavailable for search: {e}")
            return jsonify({"error": "Search is currently unavailable."}), 503

    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    offset = int(request.args.get('offset', 0))
    lang_filter      = request.args.get('lang', '').strip()
    directive_filter = request.args.get('directive', '').strip()

    if not query and not lang_filter and not directive_filter:
        return jsonify({"error": "Search query or filter is required."}), 400

    try:
        search_start = time.perf_counter()

        # Sort options:
        #   recent     = newest first
        #   oldest     = oldest first
        #   score_desc = hardest (highest Chimera difficulty) first
        #   score_asc  = easiest (lowest Chimera difficulty) first
        sort_param = request.args.get('sort', 'recent')
        sort_order = {
            'recent':     'timestamp desc, score desc',
            'oldest':     'timestamp asc, score desc',
            'score_desc': 'chimera_score desc, timestamp desc',
            'score_asc':  'chimera_score asc, timestamp desc',
        }.get(sort_param, 'timestamp desc, score desc')

        # Build Solr filter queries for language and directive
        fq = []
        if lang_filter:
            fq.append(f'source_lang:"{lang_filter}"')
        if directive_filter:
            fq.append(f'directive:"{directive_filter}"')

        # Search title and content with smart query construction:
        # Multi-word queries: phrase match (exact) boosted highest, then AND (all words), then OR fallback
        # Empty query = browse mode (all docs matching filters)
        if query:
            words = query.split()
            if len(words) > 1:
                phrase = f'"{query}"'
                and_terms = ' AND '.join(words)
                solr_query = (
                    f'title:{phrase}^10 OR content:{phrase}^5 '
                    f'OR title:({and_terms})^3 OR content:({and_terms})'
                )
            else:
                solr_query = f'title:({query})^3 OR content:({query})'
        else:
            solr_query = '*:*'

        search_kwargs = {
            'rows': limit,
            'start': offset,
            'sort': sort_order,
            'fl': 'id,title,source,url,timestamp,directive,chimera_score,source_lang,score',
        }
        if fq:
            search_kwargs['fq'] = fq
        if query:
            search_kwargs.update({
                'hl': 'true',
                'hl.fl': 'content,title',
                'hl.snippets': '1',
                'hl.fragsize': '250',
                'hl.simple.pre': '<mark class="bg-amber-400/30 text-slate-100 px-0.5 rounded">',
                'hl.simple.post': '</mark>',
            })

        results = solr.search(solr_query, **search_kwargs)

        # Build response with highlights
        articles = []
        highlighting = results.highlighting if hasattr(results, 'highlighting') else {}

        for doc in results:
            doc_id = doc.get('id', '')
            highlights = highlighting.get(doc_id, {})
            snippet = ''
            if 'content' in highlights:
                snippet = highlights['content'][0]
            elif 'title' in highlights:
                snippet = highlights['title'][0]

            articles.append({
                'id': doc_id,
                'title': doc.get('title', [''])[0] if isinstance(doc.get('title'), list) else doc.get('title', ''),
                'source': doc.get('source', [''])[0] if isinstance(doc.get('source'), list) else doc.get('source', ''),
                'url': doc.get('url', [''])[0] if isinstance(doc.get('url'), list) else doc.get('url', ''),
                'timestamp': doc.get('timestamp', [''])[0] if isinstance(doc.get('timestamp'), list) else doc.get('timestamp', ''),
                'directive': doc.get('directive', [''])[0] if isinstance(doc.get('directive'), list) else doc.get('directive', ''),
                'chimera_score': doc.get('chimera_score', 0),
                'source_lang': doc.get('source_lang', [''])[0] if isinstance(doc.get('source_lang'), list) else doc.get('source_lang', ''),
                'snippet': snippet,
                'score': doc.get('score', 0),
            })

        search_duration = (time.perf_counter() - search_start) * 1000
        filter_info = ''.join([f' lang={lang_filter}' if lang_filter else '', f' directive={directive_filter}' if directive_filter else ''])
        app.logger.info(f"🔍 Search '{query}'{filter_info} returned {len(articles)} results in {search_duration:.0f}ms")

        return jsonify({
            'query': query,
            'total': results.hits,
            'offset': offset,
            'limit': limit,
            'results': articles
        })

    except Exception as e:
        app.logger.error(f"🔥 Search error: {e}", exc_info=True)
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Live archive stats — article count, oldest, newest."""
    try:
        count = r.zcard('feed')
        oldest = None
        newest = None
        if count > 0:
            oldest_ids = r.zrange('feed', 0, 0)
            newest_ids = r.zrange('feed', -1, -1)
            if oldest_ids:
                oldest = r.hget(f"article:{oldest_ids[0]}", 'timestamp')
            if newest_ids:
                newest = r.hget(f"article:{newest_ids[0]}", 'timestamp')
        return jsonify({'article_count': count, 'oldest': oldest, 'newest': newest})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """
    Return arc_config.yaml values + live Redis runtime state.
    No secrets — credentials never leave backend/.env.
    """
    config_path = os.path.join(os.path.dirname(__file__), '..', 'arc_config.yaml')
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        app.logger.error(f"Failed to load arc_config.yaml: {e}")
        return jsonify({"error": "Config file not found"}), 503

    runtime = {
        "bluesky_autopost":  False,
        "linkedin_autopost": False,
        "article_count":     0,
        "last_publish":      None,
    }
    if r:
        try:
            runtime["bluesky_autopost"]  = r.get("bluesky:autopost") == "1"
            runtime["linkedin_autopost"] = r.get("linkedin:autopost") == "1"
            runtime["article_count"]     = r.zcard("feed")
            runtime["last_publish"]      = r.get("arc:last_publish")
        except Exception:
            pass

    cfg["runtime"]   = runtime
    cfg["loaded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return jsonify(cfg), 200

@app.route('/api/article/<article_id>/comments', methods=['GET'])
def get_article_comments(article_id):
    if not r:
        app.logger.error("🔥 Redis unavailable for get_article_comments")
        return jsonify({"error": "Database connection is offline."}), 503
    try:
        redis_start = time.perf_counter()
        comment_ids = r.lrange(f"comments:{article_id}", 0, -1)
        if not comment_ids:
            app.logger.info(f"📭 No comments for article: {article_id}")
            return jsonify([])
        
        pipe = r.pipeline()
        for comment_id in comment_ids:
            pipe.hgetall(f"comment:{comment_id}")
        comments_data = pipe.execute()
        
        # Fetch reaction counts for all comments in one pipeline
        reaction_pipe = r.pipeline()
        for comment_id in comment_ids:
            reaction_pipe.hgetall(f"reactions:{comment_id}")
        reactions_data = reaction_pipe.execute()
        
        # Merge reactions into comment data
        formatted_comments = []
        for i, comment in enumerate(comments_data):
            if comment:
                reactions = reactions_data[i] if i < len(reactions_data) and reactions_data[i] else {}
                comment['reactions'] = {k: int(v) for k, v in reactions.items() if int(v) > 0}
                formatted_comments.append(comment)
        
        formatted_comments.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        redis_duration = (time.perf_counter() - redis_start) * 1000
        
        app.logger.info(f"✅ Retrieved {len(formatted_comments)} comments for article {article_id} in {redis_duration:.2f}ms")
        return jsonify(formatted_comments)
    except Exception as e:
        app.logger.error(f"🔥 Error fetching comments for article {article_id}: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/submit_comment', methods=['POST'])
def submit_comment():
    if not r or not SENTIMENT_ANALYZER: 
        app.logger.error("🔥 System unavailable for submit_comment")
        return jsonify({"error": "System is offline."}), 503
    
    data = request.get_json()
    article_id = data.get('article_id')
    comment_text = data.get('comment_text')
    author = data.get('author', 'User')
    parent_id = data.get('parent_id', '')
    
    if not article_id or not comment_text: 
        app.logger.warning("⚠️  Missing required fields in submit_comment")
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Moderation check - only reject clearly hostile/abusive comments
    # VADER scores: -1.0 (most negative) to +1.0 (most positive)
    # -0.7 threshold allows substantive disagreement, theological debate, etc.
    # Only catches overtly hostile language, slurs, threats
    sentiment_score = SENTIMENT_ANALYZER.polarity_scores(comment_text)['compound']
    if sentiment_score < -0.7:
        app.logger.warning(f"⚠️  Comment rejected by moderation (sentiment: {sentiment_score:.2f}, author: {author})")
        return jsonify({'error': 'Comment rejected by moderation.'}), 400
    elif sentiment_score < -0.3:
        app.logger.info(f"📝 Borderline comment allowed (sentiment: {sentiment_score:.2f}, author: {author})")
    
    comment_id = str(uuid.uuid4())
    new_comment = {
        'id': comment_id, 
        'article_id': article_id, 
        'author': author, 
        'text': comment_text, 
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'parent_id': parent_id
    }
    
    try:
        redis_start = time.perf_counter()
        pipe = r.pipeline()
        pipe.hset(f"comment:{comment_id}", mapping=new_comment)
        pipe.rpush(f"comments:{article_id}", comment_id)
        pipe.execute()
        redis_duration = (time.perf_counter() - redis_start) * 1000
        
        app.logger.info(f"✅ Comment submitted by '{author}' on article {article_id} (ID: {comment_id}) in {redis_duration:.2f}ms")
        
        # --- AI REPLY TRIGGER ---
        # If this is a reply to an A.R.C. Counter-Analyst comment, queue an AI follow-up
        if parent_id:
            try:
                parent_comment = r.hgetall(f"comment:{parent_id}")
                parent_author = parent_comment.get('author', '')
                if parent_author == 'A.R.C. Counter-Analyst':
                    # Don't reply to AI replying to AI (prevent loops)
                    if author != 'A.R.C. Counter-Analyst':
                        reply_payload = json.dumps({
                            'article_id': article_id,
                            'user_comment_id': comment_id,
                            'user_comment_text': comment_text,
                            'ai_comment_text': parent_comment.get('text', ''),
                            'user_author': author
                        })
                        r.lpush('counteranalyst:reply_queue', reply_payload)
                        app.logger.info(f"🤖 Queued AI reply to user comment on {article_id}")
            except Exception as e:
                app.logger.warning(f"⚠️  AI reply trigger failed (non-fatal): {e}")
        
        return jsonify({"success": True, "comment": new_comment}), 201
    except Exception as e:
        app.logger.error(f"🔥 Error saving comment: {e}", exc_info=True)
        return jsonify({"error": f"Server error saving comment: {e}"}), 500


VALID_REACTIONS = {'like', 'dislike', 'heart', 'happy', 'care'}

@app.route('/api/comment/<comment_id>/react', methods=['POST'])
def react_to_comment(comment_id):
    """Toggle a reaction on a comment. Increments or decrements the count."""
    if not r:
        app.logger.error("🔥 Redis unavailable for react_to_comment")
        return jsonify({"error": "Database connection is offline."}), 503
    
    data = request.get_json()
    reaction = data.get('reaction', '')
    action = data.get('action', 'add')  # 'add' or 'remove'
    
    if reaction not in VALID_REACTIONS:
        return jsonify({'error': f'Invalid reaction. Must be one of: {", ".join(sorted(VALID_REACTIONS))}'}), 400
    
    if action not in ('add', 'remove'):
        return jsonify({'error': 'Action must be "add" or "remove"'}), 400
    
    try:
        redis_start = time.perf_counter()
        key = f"reactions:{comment_id}"
        
        if action == 'add':
            new_count = r.hincrby(key, reaction, 1)
        else:
            new_count = r.hincrby(key, reaction, -1)
            if new_count < 0:
                r.hset(key, reaction, 0)
                new_count = 0
        
        # Return all current counts
        all_reactions = r.hgetall(key)
        counts = {k: int(v) for k, v in all_reactions.items() if int(v) > 0}
        redis_duration = (time.perf_counter() - redis_start) * 1000
        
        app.logger.info(f"{'➕' if action == 'add' else '➖'} Reaction '{reaction}' {action}ed on comment {comment_id[:12]}... in {redis_duration:.0f}ms")
        return jsonify({'reactions': counts})
    except Exception as e:
        app.logger.error(f"🔥 Error processing reaction: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

_pre_analyze_sem = threading.Semaphore(2)


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


@app.route('/api/pre_analyze', methods=['POST'])
def pre_analyze():
    """
    Pre-analysis endpoint — NLP scoring pass.

    Chimera Difficulty Score: average of FK, Coleman-Liau, SMOG, Dale-Chall
    grade metrics scaled 0-100 with a named reading label.

    Also computes VADER sentiment, TextBlob subjectivity, entity counts,
    readability suite, and word/sentence structure. All returned in the
    JSON response — including pre-formatted ``nlp_*`` keys that scribe
    carries through into publish_payload, so the data lands in the
    article hash only when the article actually publishes (no orphans).
    """
    if not all([NLP_PROCESSOR, SENTIMENT_ANALYZER]):
        app.logger.error("🔥 NLP Engine unavailable for pre_analyze")
        return jsonify({"error": "NLP Engine is offline."}), 503

    if not _pre_analyze_sem.acquire(timeout=1):
        app.logger.warning("⚠️  pre_analyze: concurrency limit reached, returning 429")
        return jsonify({"error": "Server busy, please retry shortly."}), 429

    try:
        data = request.get_json()
        input_text  = data.get('inputText', '')

        if not input_text:
            return jsonify({"chimera_score": 0.0, "sentiment": 0.0, "entities_found": []})

        input_text_snippet = input_text[:MAX_CONTENT_CHARS]

        analyze_start = time.perf_counter()

        # --- VADER sentiment (full breakdown) ---
        vader_scores  = SENTIMENT_ANALYZER.polarity_scores(input_text_snippet)
        sentiment     = vader_scores.get('compound', 0.0)
        vader_pos     = round(vader_scores.get('pos', 0.0), 4)
        vader_neg     = round(vader_scores.get('neg', 0.0), 4)
        vader_neu     = round(vader_scores.get('neu', 0.0), 4)

        # --- TextBlob objectivity ---
        blob           = TextBlob(input_text_snippet)
        subjectivity   = blob.sentiment.subjectivity
        objectivity_score = (1 - subjectivity) * 100

        # --- Readability suite ---
        readability_grade   = textstat.flesch_kincaid_grade(input_text_snippet)
        reading_level       = classify_reading_level(readability_grade)
        coleman_liau        = round(textstat.coleman_liau_index(input_text_snippet), 2)
        smog_index          = round(textstat.smog_index(input_text_snippet), 2)
        dale_chall          = round(textstat.dale_chall_readability_score(input_text_snippet), 2)
        syllable_count      = textstat.syllable_count(input_text_snippet)
        word_count          = textstat.lexicon_count(input_text_snippet, removepunct=True)
        sentence_count      = textstat.sentence_count(input_text_snippet)
        avg_sentence_len    = round(word_count / max(sentence_count, 1), 1)

        # --- spaCy NLP ---
        doc = NLP_PROCESSOR(input_text_snippet)

        # Entity counts by type
        entity_labels = ["PERSON", "ORG", "GPE", "LOC", "DATE", "MONEY", "EVENT"]
        entity_counts = {label: 0 for label in entity_labels}
        entities_found = []
        for ent in doc.ents:
            if ent.label_ in entity_counts:
                entity_counts[ent.label_] += 1
                entities_found.append(ent.label_)


        # Chimera Difficulty Score: average of four grade-level readability metrics
        chimera_score  = compute_chimera(readability_grade, coleman_liau, smog_index, dale_chall)
        reading_label  = chimera_reading_label(chimera_score)

        analyze_duration = (time.perf_counter() - analyze_start) * 1000

        app.logger.info(
            f"✅ Pre-analysis v3.0 in {analyze_duration:.0f}ms "
            f"(chimera={chimera_score}, label={reading_label}, obj={objectivity_score:.0f}, "
            f"grade={readability_grade:.1f}, words={word_count}, "
            f"entities={sum(entity_counts.values())})"
        )

        result = {
            # --- Core scores ---
            "chimera_score":        chimera_score,
            "reading_label":        reading_label,
            "sentiment":            sentiment,
            "subjectivity":         round(subjectivity, 4),
            "objectivity_score":    round(objectivity_score, 2),
            "readability_grade":    round(readability_grade, 1),
            "reading_level":        reading_level,
            "entities_found":       list(set(entities_found)),

            # --- VADER breakdown ---
            "vader_pos":            vader_pos,
            "vader_neg":            vader_neg,
            "vader_neu":            vader_neu,

            # --- Entity counts by type ---
            "entity_person_count":  entity_counts["PERSON"],
            "entity_org_count":     entity_counts["ORG"],
            "entity_gpe_count":     entity_counts["GPE"],
            "entity_loc_count":     entity_counts["LOC"],
            "entity_date_count":    entity_counts["DATE"],
            "entity_money_count":   entity_counts["MONEY"],
            "entity_event_count":   entity_counts["EVENT"],

            # --- Text structure ---
            "word_count":           word_count,
            "sentence_count":       sentence_count,
            "avg_sentence_len":     avg_sentence_len,
            "syllable_count":       syllable_count,

            # --- Readability suite ---
            "coleman_liau":         coleman_liau,
            "smog_index":           smog_index,
            "dale_chall":           dale_chall,

            # --- nlp_* fields, ready to be merged verbatim into the article
            #     hash at publish time. Same keys corpus_exporter.py reads.
            #     Stored as strings so the Redis hash mapping is type-stable.
            "nlp_chimera_score":    str(chimera_score),
            "nlp_reading_label":    reading_label,
            "nlp_sentiment":        str(sentiment),
            "nlp_vader_pos":        str(vader_pos),
            "nlp_vader_neg":        str(vader_neg),
            "nlp_vader_neu":        str(vader_neu),
            "nlp_subjectivity":     str(round(subjectivity, 4)),
            "nlp_objectivity":      str(round(objectivity_score, 2)),
            "nlp_word_count":       str(word_count),
            "nlp_sentence_count":   str(sentence_count),
            "nlp_avg_sentence_len": str(avg_sentence_len),
            "nlp_syllable_count":   str(syllable_count),
            "nlp_fk_grade":         str(round(readability_grade, 1)),
            "nlp_reading_level":    reading_level,
            "nlp_coleman_liau":     str(coleman_liau),
            "nlp_smog":             str(smog_index),
            "nlp_dale_chall":       str(dale_chall),
            "nlp_entity_person":    str(entity_counts["PERSON"]),
            "nlp_entity_org":       str(entity_counts["ORG"]),
            "nlp_entity_gpe":       str(entity_counts["GPE"]),
            "nlp_entity_loc":       str(entity_counts["LOC"]),
            "nlp_entity_date":      str(entity_counts["DATE"]),
            "nlp_entity_money":     str(entity_counts["MONEY"]),
            "nlp_entity_event":     str(entity_counts["EVENT"]),
        }

        # NLP fields are returned in the JSON above; scribe carries them into
        # publish_payload so they land in the article hash only on quality-pass
        # publish. Pre-publish Redis writes here would orphan ~1.5k hashes/day
        # for articles that never make it past scribe's gates.
        return jsonify(result)

    except Exception as e:
        app.logger.error(f"🔥 Pre-analysis failed: {e}", exc_info=True)
        return jsonify({"chimera_score": 0.0, "sentiment": 0.0, "entities_found": []})
    finally:
        _pre_analyze_sem.release()

# --- PDF text normalizer ---
def _normalize_pdf_text(raw_text: str) -> str:
    """
    Clean up text extracted from a PDF so it reads as natural paragraphs.

    PyPDF often produces word-per-line output because each PDF glyph run is a
    separate text object.  The three fixes applied in order:

    1. Rejoin soft hyphens at line breaks  (e.g. "compu-\\nter" → "computer")
    2. Collapse single newlines into spaces (intra-paragraph line wraps)
    3. Normalise runs of blank lines to a single paragraph break
    4. Collapse any remaining runs of spaces
    """
    text = raw_text
    # 1. Soft hyphen at end of line: remove the hyphen and join the word
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    # 2. Single newline (not preceded or followed by another newline) → space
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # 3. Three or more consecutive newlines → two (one blank line between paragraphs)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 4. Multiple spaces → single space
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# --- STM ENDPOINT with enhanced logging ---
def extract_file_text(file_storage):
    """Extract text from uploaded files: txt, md, pdf, docx, odt"""
    filename = file_storage.filename.lower()
    file_storage.seek(0)
    raw = file_storage.read()
    
    try:
        if filename.endswith(('.txt', '.md')):
            try:
                return True, raw.decode('utf-8')
            except UnicodeDecodeError:
                return True, raw.decode('latin-1')

        elif filename.endswith('.pdf'):
            reader = PdfReader(io.BytesIO(raw))
            raw_text = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
            text = _normalize_pdf_text(raw_text)
            return True, text[:50000]

        elif filename.endswith('.docx'):
            doc = docx.Document(io.BytesIO(raw))
            text = '\n'.join(p.text for p in doc.paragraphs)
            return True, text

        elif filename.endswith('.odt'):
            odt_doc = odf_load(io.BytesIO(raw))
            all_text = []
            for elem in odt_doc.getElementsByType(odf_text.P):
                t = ''
                for node in elem.childNodes:
                    if hasattr(node, 'data'):
                        t += node.data
                    elif hasattr(node, 'childNodes'):
                        for child in node.childNodes:
                            if hasattr(child, 'data'):
                                t += child.data
                all_text.append(t)
            return True, '\n'.join(all_text)

        else:
            return False, f"Unsupported file type: {filename}"

    except Exception as e:
        return False, f"Failed to extract text: {e}"

@app.route('/api/submit_content', methods=['POST'])
def submit_content():
    """
    Content submission endpoint - handles text, URLs, and file uploads
    """
    try:
        data = request.form
        title = data.get('title')
        content_type = data.get('content_type')
        content = data.get('content')
        category = data.get('category', 'general')
        file = request.files.get('file')

        if not title:
            app.logger.warning("⚠️  submit_content: title missing")
            return jsonify({'error': 'Title is required.'}), 400

        app.logger.info(f"📥 Content submission: '{title}' (type: {content_type}, category: {category})")

        processed_content = ''
        source_url_for_metadata = ''

        if content_type == 'text':
            processed_content = content
            app.logger.info(f"   Processing as direct text ({len(content)} chars)")

        elif content_type == 'url':
            source_url_for_metadata = content
            success, result = fetch_and_process_url(content)
            if not success:
                app.logger.error(f"🔥 URL fetch failed for: {content}")
                return jsonify({'error': result}), 400
            processed_content = result

        elif content_type == 'file':
            if file and file.filename != '':
                app.logger.info(f"   Processing uploaded file: {file.filename} ({file.mimetype})")
                success, result = extract_file_text(file)
                if not success:
                    app.logger.error(f"🔥 File extraction failed: {result}")
                    return jsonify({'error': result}), 400
                processed_content = result
                app.logger.info(f"   File extracted successfully ({len(processed_content)} chars)")
            else:
                app.logger.warning("⚠️  File content_type selected but no file provided")
                return jsonify({'error': 'File was selected but not provided.'}), 400
        else:
            app.logger.warning(f"⚠️  Invalid content_type: {content_type}")
            return jsonify({'error': 'Invalid content_type.'}), 400

        safe_title = secure_filename(title) or f"submission_{uuid.uuid4().hex[:8]}"
        filename = f"{safe_title}.txt"
        pending_dir = os.path.join(os.path.dirname(__file__), 'upload', 'pending')
        os.makedirs(pending_dir, exist_ok=True)

        file_metadata = {'original_url': source_url_for_metadata, 'content_type': content_type, 'category': category}
        file_content = f"---\n{json.dumps(file_metadata)}\n---\n{title}\n{processed_content}"
        
        file_path = os.path.join(pending_dir, filename)
        app.logger.info(f"💾 Writing submission to: {file_path}")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        app.logger.info(f"✅ Content submission saved: '{title}' ({len(file_content)} chars)")
        return jsonify({'success': True, 'message': f"Content '{title}' submitted."}), 201

    except Exception as e:
        app.logger.error(f"🔥 Unhandled error in submit_content: {e}", exc_info=True)
        return jsonify({'error': 'A critical server error occurred.'}), 500


# --- PRIORITY QUEUE ENDPOINTS ---
REDIS_PRIORITY_QUEUE_KEY = "arc:priority_uploads"


@app.route('/api/submit', methods=['POST'])
def submit():
    """
    Submit a URL or raw text directly into the scribe priority queue.
    Replaces the old filesystem-based submit_content path for url/text types.

    JSON body:
        {
            "content_type": "url" | "text",
            "content":      "...",
            "title":        "...",
            "image_url":    "https://..."   # optional — overrides OG image extraction
        }

    Returns 202 immediately — scribe processes asynchronously.
    """

    if not r:
        app.logger.error("🔥 Redis unavailable for submit")
        return jsonify({"error": "Database connection is offline."}), 503

    data = request.get_json(force=True, silent=True) or {}
    content_type = data.get('content_type', '').strip()
    content      = (data.get('content') or '').strip()
    title        = (data.get('title') or '').strip()
    source_url   = (data.get('source_url') or '').strip()

    if content_type not in ('url', 'text'):
        return jsonify({'error': 'content_type must be "url" or "text"'}), 400
    if not content:
        return jsonify({'error': 'content is required'}), 400

    if content_type == 'url':
        try:
            from urllib.parse import urlparse as _urlparse
            parsed = _urlparse(content)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                return jsonify({'error': 'Invalid URL'}), 400
        except Exception:
            return jsonify({'error': 'Invalid URL'}), 400

    job_id = str(uuid.uuid4())

    payload = {
        'origin': content_type,
        'url':    content if content_type == 'url'  else source_url,
        'text':   content if content_type == 'text' else '',
        'title':  title,
        'image_url': (data.get('image_url') or '').strip() or None,
        'visibility': (data.get('visibility') or 'public'),
        'owner': request.headers.get('X-User-Id') or session.get('username', ''),
        'job_id': job_id,
    }

    try:
        r.lpush(REDIS_PRIORITY_QUEUE_KEY, json.dumps(payload))
        queue_len = r.llen(REDIS_PRIORITY_QUEUE_KEY)
        app.logger.info(f"⚡ Queued {content_type} submission: '{title or content[:60]}' (queue depth: {queue_len}, job_id: {job_id})")
        return jsonify({
            'success': True,
            'message': 'Submitted. Your content will be published shortly.',
            'queue_position': queue_len,
            'job_id': job_id,
        }), 202
    except Exception as e:
        app.logger.error(f"🔥 Failed to queue submission: {e}", exc_info=True)
        return jsonify({'error': 'Failed to queue submission.'}), 500


@app.route('/api/submit_pdf', methods=['POST'])   # kept for backwards-compat
@app.route('/api/submit_doc', methods=['POST'])
def submit_doc():
    """
    Upload a document (PDF, DOCX, ODT), extract its text via extract_file_text(),
    and push it into the priority queue as a text submission.

    Multipart body:
        file        — .pdf, .docx, or .odt file
        title       — article title (optional; falls back to filename stem)
        visibility  — "public" | "private" (default: public)

    Returns 202 on success, 400 if the file type is unsupported, extraction
    fails, or the extracted text is under 200 characters.
    """
    if not r:
        app.logger.error("🔥 Redis unavailable for submit_doc")
        return jsonify({"error": "Database connection is offline."}), 503

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({'error': 'No file provided.'}), 400

    fname = file.filename.lower()
    if not fname.endswith(('.pdf', '.docx', '.odt')):
        return jsonify({'error': 'Unsupported file type. Please upload a PDF, DOCX, or ODT file.'}), 400

    title      = (request.form.get('title') or '').strip()
    visibility = (request.form.get('visibility') or 'public').strip()

    success, extracted = extract_file_text(file)
    if not success:
        app.logger.error(f"🔥 Document extraction failed for '{file.filename}': {extracted}")
        return jsonify({'error': f'Failed to extract text: {extracted}'}), 400

    extracted = extracted.strip()

    if len(extracted) < 200:
        app.logger.warning(f"⚠️  '{file.filename}' yielded only {len(extracted)} chars — too short")
        return jsonify({
            'error': (
                f'Text extraction produced too little content ({len(extracted)} characters). '
                'The file may be image-only, password-protected, or nearly empty. '
                'Please paste the text directly instead.'
            )
        }), 400

    if len(extracted) > MAX_CONTENT_CHARS:
        app.logger.warning(f"⚠️  '{file.filename}' text truncated from {len(extracted)} to {MAX_CONTENT_CHARS} chars")
        extracted = extracted[:MAX_CONTENT_CHARS]

    stem = secure_filename(file.filename).rsplit('.', 1)[0]
    job_id = str(uuid.uuid4())
    payload = {
        'origin': 'text',
        'url':    '',
        'text':   extracted,
        'title':  title or stem,
        'image_url': None,
        'visibility': visibility,
        'owner': request.headers.get('X-User-Id') or session.get('username', ''),
        'job_id': job_id,
    }

    try:
        r.lpush(REDIS_PRIORITY_QUEUE_KEY, json.dumps(payload))
        queue_len = r.llen(REDIS_PRIORITY_QUEUE_KEY)
        ext = fname.rsplit('.', 1)[-1].upper()
        app.logger.info(
            f"⚡ Queued {ext} submission: '{payload['title']}' "
            f"({len(extracted)} chars, queue depth: {queue_len}, job_id: {job_id})"
        )
        return jsonify({
            'success': True,
            'message': 'Document text extracted and queued. Your article will be published shortly.',
            'queue_position': queue_len,
            'job_id': job_id,
        }), 202
    except Exception as e:
        app.logger.error(f"🔥 Failed to queue document submission: {e}", exc_info=True)
        return jsonify({'error': 'Failed to queue submission.'}), 500


@app.route('/api/job/<job_id>', methods=['GET'])
def job_status(job_id):
    """
    Poll the processing status of a queued submission.

    Returns:
        {"status": "pending"}                          — not yet processed
        {"status": "published", "article_id": "..."}  — success
        {"status": "failed",    "reason": "..."}       — URL could not be fetched etc.
    """
    if not r:
        return jsonify({"error": "Database unavailable"}), 503

    raw = r.get(f"arc:job:{job_id}:status")
    if not raw:
        return jsonify({"status": "pending"}), 200

    try:
        return jsonify(json.loads(raw)), 200
    except Exception:
        return jsonify({"status": "pending"}), 200


@app.route('/api/cloud_status', methods=['GET'])
def cloud_status():
    """Return whether the cloud Ollama model is currently available (circuit breaker state)."""
    try:
        from ollama_utils import is_cloud_available
        available = is_cloud_available()
    except Exception:
        available = True  # assume available if we can't check
    return jsonify({"available": available})


@app.route('/api/submit_prompt', methods=['POST'])
def submit_prompt():
    """
    Submit a writing prompt. Scribe calls Ollama to generate a full article,
    then publishes it through the normal pipeline.

    JSON body:
        { "prompt": "Write a long article about...", "title": "Optional title" }

    Returns 202 immediately — generation and publish happen asynchronously in scribe.
    """
    if not r:
        app.logger.error("🔥 Redis unavailable for submit_prompt")
        return jsonify({"error": "Database connection is offline."}), 503

    data   = request.get_json(force=True, silent=True) or {}
    prompt = (data.get('prompt') or '').strip()
    title  = (data.get('title') or '').strip()
    image_url = (data.get('image_url') or '').strip() or None

    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400
    if len(prompt) < 10:
        return jsonify({'error': 'Prompt is too short — please be more descriptive'}), 400
    if len(prompt) > 2000:
        return jsonify({'error': 'Prompt is too long (max 2000 characters)'}), 400

    payload = {
        'origin': 'prompt',
        'prompt': prompt,
        'title':  title,
        'image_url': image_url,
        'visibility': (data.get('visibility') or 'public'),
        'owner': request.headers.get('X-User-Id') or session.get('username', ''),
    }

    try:
        r.lpush(REDIS_PRIORITY_QUEUE_KEY, json.dumps(payload))
        queue_len = r.llen(REDIS_PRIORITY_QUEUE_KEY)
        app.logger.info(f"✍️  Queued prompt: '{prompt[:80]}...' (queue depth: {queue_len})")
        return jsonify({
            'success': True,
            'message': 'Prompt received. Your article will be generated and published shortly.',
            'queue_position': queue_len,
        }), 202
    except Exception as e:
        app.logger.error(f"🔥 Failed to queue prompt: {e}", exc_info=True)
        return jsonify({'error': 'Failed to queue prompt.'}), 500


@app.route('/api/upload_image', methods=['POST'])
def upload_image():
    """
    Upload a cover image for an article.
    Saves to frontend/public/uploads/ — served statically by Next.js/Caddy.

    Returns: { "url": "/uploads/<filename>" }
    """
    import hashlib

    file = request.files.get('image')
    if not file or file.filename == '':
        return jsonify({'error': 'No image provided'}), 400

    # Validate content type
    allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif'}
    if file.mimetype not in allowed_types:
        return jsonify({'error': 'Unsupported image type. Use JPG, PNG, WebP, or GIF.'}), 400

    raw = file.read()
    if len(raw) > 10 * 1024 * 1024:
        return jsonify({'error': 'Image must be under 10MB'}), 400
    # Resize to social-card safe dimensions (max 1200x630, keeps aspect ratio)
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    from PIL import Image, ImageOps
    import io
    try:
        TARGET_W, TARGET_H = 1200, 630
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')
        src_w, src_h = img.size
        scale = max(TARGET_W / src_w, TARGET_H / src_h)
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - TARGET_W) // 2
        top = (new_h - TARGET_H) // 2
        img = img.crop((left, top, left + TARGET_W, top + TARGET_H))
        out = io.BytesIO()
        img.save(out, format='JPEG', quality=85, optimize=True)
        raw = out.getvalue()
        ext = 'jpg'
    except Exception as e:
        app.logger.warning(f"⚠️  Image resize failed, using original: {e}")
        ext_map = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'}
        ext = ext_map.get(file.mimetype, 'jpg')

    # Stable filename from content hash — deduplicates identical uploads
    content_hash = hashlib.sha256(raw).hexdigest()[:16]
    filename = f"{content_hash}.{ext}"

    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'public', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)

    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f_out:
            f_out.write(raw)
        app.logger.info(f"🖼️  Image saved: {filename} ({len(raw) // 1024}KB)")
    else:
        app.logger.info(f"🖼️  Image deduplicated: {filename}")

    return jsonify({'url': f'/uploads/{filename}', 'filename': filename}), 201


# --- BLUESKY POST ENDPOINT ---

def bluesky_get_token():
    """Authenticate and return (did, accessJwt) or raise."""
    resp = requests.post(
        f"{BLUESKY_API_BASE}/com.atproto.server.createSession",
        json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["did"], data["accessJwt"]

def bluesky_upload_thumb(token, og_image_url):
    """Download og_image and upload to Bluesky blob store. Returns blob ref or None."""
    if not og_image_url:
        return None
    try:
        img_resp = requests.get(og_image_url, timeout=10, stream=True)
        img_resp.raise_for_status()
        content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            return None
        img_bytes = img_resp.content
        # Convert PNG to JPEG — Bluesky corrupts large PNG thumbnails
        if content_type == "image/png":
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            img_bytes = buf.getvalue()
            content_type = "image/jpeg"
        if len(img_bytes) > 1_000_000:
            img_bytes = img_bytes[:1_000_000]  # Bluesky 1MB blob limit
        upload_resp = requests.post(
            f"{BLUESKY_API_BASE}/com.atproto.repo.uploadBlob",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
            },
            data=img_bytes,
            timeout=15,
        )
        upload_resp.raise_for_status()
        return upload_resp.json().get("blob")
    except Exception as e:
        app.logger.warning(f"Bluesky thumb upload failed: {e}")
        return None

def bluesky_resolve_url_card(token, url, title, description="", og_image_url=None):
    """Build external embed card, with optional image thumbnail."""
    try:
        external = {
            "$type": "app.bsky.embed.external#external",
            "uri": url,
            "title": title[:300],
            "description": description[:600],
        }
        thumb = bluesky_upload_thumb(token, og_image_url)
        if thumb:
            external["thumb"] = thumb
        return {
            "$type": "app.bsky.embed.external",
            "external": external,
        }
    except Exception:
        return None

@app.route('/api/post_bluesky', methods=['POST'])
def post_bluesky():
    """
    Manually post an article to Bluesky.

    JSON body:
        {
            "article_id": "abc123",
            "text":       "Optional override text (max 300 chars)"
        }

    Returns 200 with post URI on success.
    """
    if not BLUESKY_APP_PASSWORD:
        return jsonify({"error": "Bluesky not configured."}), 503

    data = request.get_json(force=True, silent=True) or {}
    article_id = data.get("article_id", "").strip()
    if not article_id:
        return jsonify({"error": "article_id required"}), 400

    # Fetch article from Redis
    article = r.hgetall(f"article:{article_id}")
    if not article:
        return jsonify({"error": "Article not found"}), 404

    title       = article.get("title", "Untitled")
    source_url  = article.get("sourceUrl") or article.get("url", "")
    article_url = f"{os.getenv('NEXT_PUBLIC_BACKEND_URL', 'https://arc-codex.com')}/article/{article_id}"
    blue_team   = article.get("blue_team_analysis", "")
    og_image    = article.get("imageUrl", "")

    # Build post text — title + short blurb + article URL
    blurb = (data.get("text") or blue_team)[:200].strip()
    if blurb:
        post_text = f"{title}\n\n{blurb}\n\n{article_url}"
    else:
        post_text = f"{title}\n\n{article_url}"

    # Bluesky hard limit: 300 graphemes
    if len(post_text) > 300:
        # Trim blurb to fit
        overhead = len(title) + len(article_url) + 4  # \n\n x2
        max_blurb = 300 - overhead - 3  # 3 for ellipsis
        blurb = blurb[:max(0, max_blurb)] + ("..." if max_blurb > 0 else "")
        post_text = f"{title}\n\n{blurb}\n\n{article_url}" if blurb else f"{title}\n\n{article_url}"

    try:
        did, token = bluesky_get_token()

        # Detect facets (links/mentions) in the post text
        facet_resp = requests.post(
            f"{BLUESKY_API_BASE}/app.bsky.richtext.detectFacets",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": post_text},
            timeout=10,
        )
        facets = facet_resp.json().get("facets", []) if facet_resp.ok else []

        # Build embed card (with image thumbnail if available)
        embed = bluesky_resolve_url_card(token, article_url, title, blurb, og_image_url=og_image)

        record = {
            "$type": "app.bsky.feed.post",
            "text": post_text,
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "langs": ["en"],
        }
        if facets:
            record["facets"] = facets
        if embed:
            record["embed"] = embed

        post_resp = requests.post(
            f"{BLUESKY_API_BASE}/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
            timeout=10,
        )
        post_resp.raise_for_status()
        result = post_resp.json()
        uri = result.get("uri", "")
        app.logger.info(f"🦋 Bluesky post published: {uri}")
        r.sadd("bluesky:posted", article_id)
        return jsonify({"success": True, "uri": uri}), 200

    except requests.HTTPError as e:
        app.logger.error(f"🔥 Bluesky API error: {e.response.text}")
        return jsonify({"error": f"Bluesky API error: {e.response.status_code}"}), 502
    except Exception as e:
        app.logger.error(f"🔥 Bluesky post failed: {e}")
        return jsonify({"error": str(e)}), 500
@app.route('/api/wiki/<path:directive_name>', methods=['GET'])
def wiki_directive(directive_name):
    """
    Return up to 50 public articles (newest first) for a given directive
    that have a purple_team_analysis. Uses ZRANGE on the feed ZSET.
    """
    if not r:
        return jsonify({"error": "Database offline"}), 503

    BATCH_SIZE = 100
    results = []
    cursor = 0
    total = r.zcard('feed')

    while len(results) < 50 and cursor < total:
        ids = r.zrevrange('feed', cursor, cursor + BATCH_SIZE - 1)
        if not ids:
            break

        pipe = r.pipeline()
        for aid in ids:
            pipe.hmget(
                f"article:{aid}",
                'directive', 'title', 'source_name', 'timestamp',
                'sourceUrl', 'purple_team_analysis', 'dossier', 'id', 'visibility'
            )
        rows = pipe.execute()

        for row in rows:
            d, title, source_name, timestamp, sourceUrl, purple, dossier_raw, art_id, visibility = row
            if d != directive_name:
                continue
            if not purple:
                continue
            if visibility == 'private':
                continue

            chimera_score = 0
            if dossier_raw:
                try:
                    dossier = json.loads(dossier_raw)
                    chimera_score = dossier.get('chimera_score', 0)
                except Exception:
                    pass

            results.append({
                'id': art_id,
                'title': title or '',
                'source_name': source_name or '',
                'timestamp': timestamp or '',
                'sourceUrl': sourceUrl or '',
                'purple_team_analysis': purple,
                'chimera_score': chimera_score,
            })

            if len(results) >= 50:
                break

        cursor += BATCH_SIZE

    app.logger.info(f"📖 Wiki query for '{directive_name}' returned {len(results)} articles")
    return jsonify(results)


@app.route('/api/sources', methods=['GET'])
def get_sources():
    """Return all RSS sources as a JSON array. Public, cached 1 hour."""
    sources_file = os.path.join(os.path.dirname(__file__), 'sources.json')
    try:
        sources = []
        with open(sources_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    sources.append(json.loads(line))
        resp = jsonify(sources)
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp
    except Exception as e:
        app.logger.error(f"🔥 /api/sources error: {e}", exc_info=True)
        return jsonify([]), 500


@app.route('/api/sitemap', methods=['GET'])
def get_sitemap_ids():
    """Return all public article IDs from the feed ZSET, newest first."""
    if not r:
        return jsonify([]), 503
    try:
        all_ids = r.zrevrange('feed', 0, -1)
        if not all_ids:
            return jsonify([])

        BATCH_SIZE = 200
        public_ids = []
        for i in range(0, len(all_ids), BATCH_SIZE):
            batch = all_ids[i:i + BATCH_SIZE]
            pipe = r.pipeline()
            for aid in batch:
                pipe.hget(f"article:{aid}", 'visibility')
            visibilities = pipe.execute()
            for aid, vis in zip(batch, visibilities):
                if vis != 'private':
                    public_ids.append(aid)

        app.logger.info(f"🗺️  Sitemap returned {len(public_ids)} public article IDs")
        return jsonify(public_ids)
    except Exception as e:
        app.logger.error(f"🔥 Sitemap error: {e}", exc_info=True)
        return jsonify([]), 500


def _load_library_lang_codes():
    """Load the canonical language list shared with the frontend.
    Returns a dict of lowercased ISO code -> human-readable name.
    Includes legacy aliases for previously cached translations."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'lib', 'languages.json')
    code_to_name = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            entries = json.load(f)
        for entry in entries:
            code = (entry.get('code') or '').strip()
            name = (entry.get('name') or '').strip()
            if code and name:
                code_to_name[code.lower()] = name
    except Exception as ex:
        app.logger.warning(f"Failed to load languages.json for library reader: {ex}")
    # Legacy aliases — keep cached translations from earlier reader versions reachable.
    code_to_name.setdefault('pt-br', 'Brazilian Portuguese')
    return code_to_name


LIBRARY_LANG_CODE_TO_NAME = _load_library_lang_codes()
# Build supported set from translation.py's LANGUAGE_CODES (name → ISO);
# we need the inverse — the set of ISO codes the translator accepts.
try:
    from translation import LANGUAGE_CODES as _TG_LANG_CODES
    LIBRARY_SUPPORTED_LANGS = {code.lower() for code in _TG_LANG_CODES.values()} | {'en'}
except Exception:
    # Fallback to a known-safe minimal set
    LIBRARY_SUPPORTED_LANGS = {'en', 'de', 'fr', 'es', 'it', 'pt', 'nl', 'ru', 'ja', 'zh'}
# Translate only the first ~8K chars: longer inputs exceed the translator's context window.
LIBRARY_TRANSLATION_PREVIEW_CHARS = 8000
LIBRARY_TRANSLATION_BOUNDARY_LOOKBACK = 1000


def _slice_for_translation(body: str) -> int:
    """Return the cut index for the translation preview window — prefers the
    last paragraph break within LOOKBACK chars of the cap, else hard cuts."""
    cap = LIBRARY_TRANSLATION_PREVIEW_CHARS
    if len(body) <= cap:
        return len(body)
    window_start = max(0, cap - LIBRARY_TRANSLATION_BOUNDARY_LOOKBACK)
    boundary = body.rfind('\n\n', window_start, cap)
    return boundary if boundary != -1 else cap


@app.route('/api/library/<gutenberg_id>', methods=['GET'])
def get_library_work(gutenberg_id):
    """Return a single work, including its full text body.
    Optional ?lang=<code> translates and caches the entire book."""
    if not r:
        return jsonify({"error": "Database offline"}), 503
    if not re.match(r'^\d+$', gutenberg_id):
        return jsonify({"error": "Invalid id"}), 400

    lang = (request.args.get('lang', 'en') or 'en').strip().lower()
    if lang not in LIBRARY_SUPPORTED_LANGS:
        return jsonify({"error": "Unsupported language"}), 400

    try:
        meta = r.hgetall(f"library:work:{gutenberg_id}")
        if not meta:
            return jsonify({"error": "Not found"}), 404
        body = r.get(f"library:work:{gutenberg_id}:text") or ""
        try:
            subjects = json.loads(meta.get('subjects', '[]'))
        except (ValueError, TypeError):
            subjects = []
        try:
            chimera_int = int(meta['chimera_score']) if meta.get('chimera_score') not in (None, '') else None
        except (ValueError, TypeError):
            chimera_int = None
        try:
            fk_grade_f = float(meta['fk_grade']) if meta.get('fk_grade') not in (None, '') else None
        except (ValueError, TypeError):
            fk_grade_f = None
        try:
            coleman_liau_f = float(meta['coleman_liau']) if meta.get('coleman_liau') not in (None, '') else None
        except (ValueError, TypeError):
            coleman_liau_f = None
        try:
            smog_f = float(meta['smog']) if meta.get('smog') not in (None, '') else None
        except (ValueError, TypeError):
            smog_f = None
        try:
            dale_chall_f = float(meta['dale_chall']) if meta.get('dale_chall') not in (None, '') else None
        except (ValueError, TypeError):
            dale_chall_f = None

        text_out = body
        is_translated = False
        is_preview = False
        preview_chars = None
        translation_error = None
        work_lang = (meta.get('language', '') or '').strip().lower()
        language_name = LIBRARY_LANG_CODE_TO_NAME.get(lang) if lang != 'en' else None

        if lang != 'en' and body:
            if work_lang and work_lang != 'en':
                translation_error = "Translation only available for English-language works."
            else:
                tx_key = f"library:work:{gutenberg_id}:translation:{lang}"
                tx_meta_key = f"library:work:{gutenberg_id}:translation:{lang}:meta"
                cached = r.get(tx_key)
                if cached is not None:
                    text_out = cached
                    is_translated = True
                    cached_meta = r.hgetall(tx_meta_key) or {}
                    if cached_meta.get('is_preview') == '1':
                        is_preview = True
                        try:
                            preview_chars = int(cached_meta.get('preview_chars') or 0) or None
                        except (ValueError, TypeError):
                            preview_chars = None
                else:
                    try:
                        from translation import _call_translation_model
                        cut = _slice_for_translation(body)
                        snippet = body[:cut]
                        lang_name = LIBRARY_LANG_CODE_TO_NAME.get(lang, lang)
                        translated = _call_translation_model(snippet, lang_name, "English", timeout=120)
                        if translated and translated.strip():
                            text_out = translated
                            is_translated = True
                            is_preview = True
                            preview_chars = cut
                            try:
                                r.set(tx_key, text_out)
                                r.hset(tx_meta_key, mapping={
                                    'is_preview': '1',
                                    'preview_chars': str(cut),
                                })
                            except Exception as ex:
                                app.logger.warning(f"Failed to cache library translation {tx_key}: {ex}")
                        else:
                            translation_error = "Translation model returned empty result"
                    except Exception as ex:
                        app.logger.warning(
                            f"Library translation failed for {gutenberg_id}/{lang}: {ex}"
                        )
                        translation_error = str(ex)

        payload = {
            'gutenberg_id':         meta.get('gutenberg_id', gutenberg_id),
            'title':                meta.get('title', ''),
            'author':               meta.get('author', 'Unknown'),
            'language':             meta.get('language', ''),
            'subjects':             subjects,
            'year_published':       meta.get('year_published', ''),
            'download_count':       int(meta['download_count']) if meta.get('download_count') else 0,
            'encoding':             meta.get('encoding', ''),
            'source_url':           meta.get('source_url', ''),
            'fetched_at':           meta.get('fetched_at', ''),
            'chimera_score':        chimera_int,
            'reading_label':        meta.get('reading_label', ''),
            'chimera_skip_reason':  meta.get('chimera_skip_reason', ''),
            'fk_grade':             fk_grade_f,
            'coleman_liau':         coleman_liau_f,
            'smog':                 smog_f,
            'dale_chall':           dale_chall_f,
            'scored_at':            meta.get('scored_at', ''),
            'text':                 text_out,
            'is_translated':        is_translated,
            'is_preview':           is_preview,
            'total_chars':          len(body),
        }
        if is_preview and preview_chars is not None:
            payload['preview_chars'] = preview_chars
        if language_name:
            payload['language_name'] = language_name
        if translation_error:
            payload['translation_error'] = translation_error

        resp = jsonify(payload)
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp
    except Exception as e:
        app.logger.error(f"🔥 /api/library/{gutenberg_id} error: {e}", exc_info=True)
        return jsonify({"error": "Internal error"}), 500


@app.route('/api/library/search', methods=['GET'])
def library_search():
    """Substring search across title + author. Public, no auth.
    Returns up to 50 matches sorted by download_count desc."""
    if not r:
        return jsonify([]), 503
    q = (request.args.get('q', '') or '').strip().lower()
    if len(q) < 2:
        return jsonify([])
    try:
        gids = r.zrevrange('library:works', 0, -1)
        if not gids:
            return jsonify([])

        pipe = r.pipeline()
        for gid in gids:
            pipe.hmget(
                f"library:work:{gid}",
                'gutenberg_id', 'title', 'author', 'language',
                'download_count', 'year_published',
            )
        rows = pipe.execute()

        results = []
        for gid, row in zip(gids, rows):
            gutenberg_id, title, author, language, download_count, year_published = row
            if not title:
                continue
            haystack = f"{title or ''} {author or ''}".lower()
            if q not in haystack:
                continue
            results.append({
                'gutenberg_id':   gutenberg_id or gid,
                'title':          title or '',
                'author':         author or 'Unknown',
                'language':       language or '',
                'download_count': int(download_count) if download_count else 0,
                'year_published': year_published or '',
            })
            if len(results) >= 50:
                break

        resp = jsonify(results)
        resp.headers['Cache-Control'] = 'public, max-age=300'
        return resp
    except Exception as e:
        app.logger.error(f"🔥 /api/library/search error: {e}", exc_info=True)
        return jsonify([]), 500


@app.route('/api/library/shelves', methods=['GET'])
def get_library_shelves():
    """Return the list of curated shelves with metadata. Public, no auth."""
    if not r:
        return jsonify([]), 503
    try:
        slugs = sorted(r.smembers('library:shelves') or [])
        if not slugs:
            return jsonify([])

        pipe = r.pipeline()
        for slug in slugs:
            pipe.hgetall(f"library:shelf:{slug}:meta")
        metas = pipe.execute()

        results = []
        for slug, meta in zip(slugs, metas):
            if not meta:
                continue
            try:
                book_count = int(meta.get('book_count', '0'))
            except (ValueError, TypeError):
                book_count = 0
            results.append({
                'slug':                   meta.get('slug', slug),
                'name':                   meta.get('name', slug),
                'description':            meta.get('description', ''),
                'gutenberg_bookshelf_id': meta.get('gutenberg_bookshelf_id', ''),
                'book_count':             book_count,
            })

        resp = jsonify(results)
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp
    except Exception as e:
        app.logger.error(f"🔥 /api/library/shelves error: {e}", exc_info=True)
        return jsonify([]), 500


@app.route('/api/library/shelf/<slug>', methods=['GET'])
def get_library_shelf(slug):
    """Return a single shelf's metadata + member works (no body text)."""
    if not r:
        return jsonify({"error": "Database offline"}), 503
    if not re.match(r'^[a-z0-9_-]+$', slug):
        return jsonify({"error": "Invalid slug"}), 400
    try:
        meta = r.hgetall(f"library:shelf:{slug}:meta")
        if not meta:
            return jsonify({"error": "Not found"}), 404

        member_ids = list(r.smembers(f"library:shelf:{slug}") or [])

        books = []
        if member_ids:
            pipe = r.pipeline()
            for gid in member_ids:
                pipe.hmget(
                    f"library:work:{gid}",
                    'gutenberg_id', 'title', 'author', 'language',
                    'download_count', 'year_published', 'subjects',
                    'chimera_score', 'reading_label', 'chimera_skip_reason',
                )
            rows = pipe.execute()

            for gid, row in zip(member_ids, rows):
                (gutenberg_id, title, author, language, download_count,
                 year_published, subjects_raw,
                 chimera_score, reading_label, chimera_skip_reason) = row
                # Skip ids that aren't in our catalog (fetch failure, pruned).
                if not title:
                    continue
                try:
                    subjects = json.loads(subjects_raw) if subjects_raw else []
                except (ValueError, TypeError):
                    subjects = []
                try:
                    chimera_int = int(chimera_score) if chimera_score not in (None, '') else None
                except (ValueError, TypeError):
                    chimera_int = None
                books.append({
                    'gutenberg_id':        gutenberg_id or gid,
                    'title':               title or '',
                    'author':              author or 'Unknown',
                    'language':            language or '',
                    'download_count':      int(download_count) if download_count else 0,
                    'year_published':      year_published or '',
                    'subjects':            subjects,
                    'chimera_score':       chimera_int,
                    'reading_label':       reading_label or '',
                    'chimera_skip_reason': chimera_skip_reason or '',
                })

        # Stable proxy for Gutenberg's own ranking: most-downloaded first.
        books.sort(key=lambda b: (-b['download_count'], b['title'].lower()))

        try:
            book_count = int(meta.get('book_count', str(len(books))))
        except (ValueError, TypeError):
            book_count = len(books)

        resp = jsonify({
            'slug':                   meta.get('slug', slug),
            'name':                   meta.get('name', slug),
            'description':            meta.get('description', ''),
            'gutenberg_bookshelf_id': meta.get('gutenberg_bookshelf_id', ''),
            'fetched_at':             meta.get('fetched_at', ''),
            'book_count':             book_count,
            'books':                  books,
        })
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp
    except Exception as e:
        app.logger.error(f"🔥 /api/library/shelf/{slug} error: {e}", exc_info=True)
        return jsonify({"error": "Internal error"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Curated catalogs (table-of-contents surfaces backed by Python source files)
# ─────────────────────────────────────────────────────────────────────────────
PLANTS_ANNUALS_FILE = '/home/ross/dual.py'
PLANTS_PERENNIALS_FILE = '/home/ross/perennials.py'
SYNDROMES_FILE = '/home/ross/syndromes.py'
_ARC_URL_PREFIX = 'https://arc-codex.com'


def _strip_arc_prefix(entries):
    """Return entries with arc-codex.com host stripped — frontend renders relative."""
    out = []
    for e in entries:
        url = e.get('url', '')
        if url.startswith(_ARC_URL_PREFIX):
            url = url[len(_ARC_URL_PREFIX):] or '/'
        out.append({'common': e['common'], 'latin': e['latin'], 'url': url})
    return out


@app.route('/api/syndromes', methods=['GET'])
def get_syndromes_catalog():
    """Return curated syndromes index. Cached 5 minutes.
    Maps catalog_loader's generic second column to 'classification'."""
    try:
        rows = _strip_arc_prefix(load_catalog(SYNDROMES_FILE, 'ALL_SYNDROMES'))
        syndromes = [
            {'common': r['common'], 'classification': r['latin'], 'url': r['url']}
            for r in rows
        ]
        resp = jsonify({'syndromes': syndromes})
        resp.headers['Cache-Control'] = 'public, max-age=300'
        return resp
    except FileNotFoundError as e:
        app.logger.error(f"🧬 /api/syndromes source missing: {e}")
        return jsonify({'error': 'Catalog source missing'}), 500
    except Exception as e:
        app.logger.error(f"🧬 /api/syndromes error: {e}", exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@app.route('/api/plants', methods=['GET'])
def get_plants_catalog():
    """Return curated plant catalog grouped by lifecycle. Cached 5 minutes."""
    try:
        annuals = _strip_arc_prefix(load_catalog(PLANTS_ANNUALS_FILE, 'ALL_PLANTS'))
        perennials = _strip_arc_prefix(load_catalog(PLANTS_PERENNIALS_FILE, 'ALL_PERENNIALS'))
        resp = jsonify({'annuals': annuals, 'perennials': perennials})
        resp.headers['Cache-Control'] = 'public, max-age=300'
        return resp
    except FileNotFoundError as e:
        app.logger.error(f"🌱 /api/plants source missing: {e}")
        return jsonify({'error': 'Catalog source missing'}), 500
    except Exception as e:
        app.logger.error(f"🌱 /api/plants error: {e}", exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=False)
