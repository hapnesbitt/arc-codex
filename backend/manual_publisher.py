#!/usr/bin/env python3
# Filename: manual_publisher.py
# Version 5.1 - LAZY ANALYSIS + OG:IMAGE EXTRACTION
# Watches /upload/pending/ and publishes articles using the same flow as scribe.py
# Publishes fast, runs Sentinel + Counter-Analyst only. Red/Blue/Purple deferred to analyzer.py on-demand.
# Fetches og:image from original_url when no explicit image_url is provided.
# Completely isolated from scribe.py - if this breaks, scribe.py keeps working

import os
import sys
import time
import json
import hashlib
import shutil
import uuid
import requests
import logging
import re
from bs4 import BeautifulSoup
from stream_utils import publish_analysis, get_redis_connection, ensure_stream_group
from ollama_utils import call_ollama_with_fallback, OLLAMA_CLOUD_MODEL, OLLAMA_LOCAL_FALLBACK
from fetch_utils import sanitize_active_content
from api_client import APIClient
import yaml
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_DIR = os.path.join(BASE_DIR, "upload", "pending")
COMPLETED_DIR = os.path.join(BASE_DIR, "upload", "completed")
FAILED_DIR = os.path.join(BASE_DIR, "upload", "failed")
LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "manual_publisher.log")
PROMPTS_FILE = os.path.join(BASE_DIR, "prompts.yaml")

API_BASE_URL = os.environ.get("SCRIBE_API_BASE_URL", "http://127.0.0.1:5005/api")
SCRIBE_SECRET_KEY = os.environ.get("SCRIBE_SECRET_KEY", "default_secret_for_dev")
# Redis connection for stream publishing
stream_redis = get_redis_connection()
ensure_stream_group(stream_redis)
# Category-based default images (matches frontend category selector)
CATEGORY_IMAGES = {
    'threat_intelligence': 'https://arc-codex.com/information-warfare.jpg',
    'tech_surveillance':   'https://arc-codex.com/tech-surveillance.jpg',
    'economic_finance':    'https://arc-codex.com/economic-control.jpg',
    'science_health':      'https://arc-codex.com/science-medical.jpg',
    'general':             'https://arc-codex.com/manual-upload.jpg',
}
DEFAULT_IMAGE_URL = CATEGORY_IMAGES['general']

CHECK_INTERVAL = 5  # Check for new files every 5 seconds

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MANUAL_PUBLISHER] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
    ]
)
logger = logging.getLogger('manual_publisher')

# --- ENSURE DIRECTORIES EXIST ---
for directory in [PENDING_DIR, COMPLETED_DIR, FAILED_DIR]:
    os.makedirs(directory, exist_ok=True)

# --- LOAD PROMPTS FROM YAML ---
PROMPTS = {}
try:
    with open(PROMPTS_FILE, 'r') as f:
        PROMPTS = yaml.safe_load(f)
    logger.info(f"✅ Successfully loaded prompts from {PROMPTS_FILE}")
except Exception as e:
    logger.critical(f"🔥 PROMPTS FAILED TO LOAD: {e}")
    logger.critical("Analysis will not work without prompts.yaml!")

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
    """Run the Sentinel forensic pass independently of the main analysis.
    
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
        logger.info("  🛡️  Running Sentinel forensic analysis...")
        raw_response, duration, model_used = call_ollama_with_fallback(sentinel_prompt, timeout=timeout)
        logger.info(f"  🛡️  Sentinel complete via {model_used} in {duration:.0f}ms")

        sentinel_data = _repair_sentinel_json(raw_response)

        if not sentinel_data:
            logger.warning(f"  ⚠️  Sentinel JSON unrecoverable — raw: {raw_response[:300]}")
            return None

        # Validate expected keys
        required_keys = {'synthetic_confidence', 'assessment', 'summary'}
        if not required_keys.issubset(sentinel_data.keys()):
            logger.warning(f"  ⚠️  Sentinel response missing keys: {required_keys - sentinel_data.keys()}")
            return None

        # Clamp confidence to valid range
        conf = sentinel_data.get('synthetic_confidence', 0.0)
        sentinel_data['synthetic_confidence'] = max(0.0, min(1.0, float(conf)))

        # Validate assessment enum
        valid_assessments = {'HUMAN', 'LIKELY_HUMAN', 'UNCERTAIN', 'LIKELY_SYNTHETIC', 'SYNTHETIC'}
        if sentinel_data.get('assessment') not in valid_assessments:
            sentinel_data['assessment'] = 'UNCERTAIN'

        logger.info(f"  🛡️  Sentinel verdict: {sentinel_data['assessment']} "
                     f"(confidence: {sentinel_data['synthetic_confidence']:.2f})")
        return sentinel_data

    except Exception as e:
        logger.error(f"  🛡️  Sentinel analysis failed: {e}")
        return None


def run_counter_analyst(article_text: str, article_id: str, redis_conn, timeout: int = 900) -> bool:
    """Generate a devil's advocate comment and post it directly to Redis.
    
    Returns True if comment was posted, False otherwise.
    Non-fatal — article publishes even if this fails.
    """
    if not PROMPTS:
        logger.warning("  ⚠️  Counter-analyst skipped — prompts.yaml not loaded")
        return False

    ca_instruction = (
        PROMPTS.get('teams', {})
        .get('counter_analyst', {})
        .get('instruction', '')
    )
    if not ca_instruction:
        logger.warning("  ⚠️  Counter-analyst skipped — no instruction in prompts.yaml")
        return False

    ca_prompt = f"""You are reviewing this article for Arc Codex. Write a counter-argument comment.

{ca_instruction}

--- ARTICLE TEXT ---
{article_text[:8000]}"""

    try:
        logger.info("  🤖 Running Counter-Analyst...")
        raw_response, duration, model_used = call_ollama_with_fallback(ca_prompt, timeout=timeout)
        logger.info(f"  🤖 Counter-Analyst complete via {model_used} in {duration:.0f}ms")

        # Clean up response — strip any prefixes the model might add
        comment_text = raw_response.strip()
        for prefix in ['Counter-argument:', 'Counter-Argument:', 'As an AI', 'Here is']:
            if comment_text.startswith(prefix):
                comment_text = comment_text[len(prefix):].strip()
                if comment_text.startswith(':'):
                    comment_text = comment_text[1:].strip()

        if len(comment_text) < 20:
            logger.warning(f"  ⚠️  Counter-analyst response too short ({len(comment_text)} chars)")
            return False
        if len(comment_text) > 2000:
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

        pipe = redis_conn.pipeline()
        pipe.hset(f"comment:{comment_id}", mapping=comment_data)
        pipe.rpush(f"comments:{article_id}", comment_id)
        pipe.execute()

        logger.info(f"  🤖 Counter-analyst comment posted for {article_id} ({len(comment_text)} chars)")
        return True

    except Exception as e:
        logger.error(f"  🤖 Counter-analyst failed: {e}")
        return False


# --- API CLIENT ---
# class APIClient moved to api_client.py 2026-08-27, consolidating this
# file's independent (drifted) copy onto the one scribe.py now uses too —
# see api_client.py's own docstring for why the logger is passed in
# explicitly here rather than left at its default.

# --- UTILITY FUNCTIONS ---
def get_article_hash(title, text_content):
    """Generate MD5 hash from title and text snippet"""
    snippet = text_content.strip()[:500]
    unique_string = f"{title.strip()}::{snippet}"
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()

def fetch_og_image(url: str, timeout: int = 15) -> str | None:
    """Fetch og:image from a URL. Returns image URL or None."""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ArcCodex/1.0)'
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Try og:image, twitter:image, og:image:url in order
        for prop in ['og:image', 'twitter:image', 'og:image:url', 'twitter:image:src']:
            tag = soup.find('meta', attrs={'property': prop}) or soup.find('meta', attrs={'name': prop})
            if tag:
                img = tag.get('content') or tag.get('href')
                if img and len(img) > 10:
                    # Make absolute
                    if img.startswith('//'):
                        img = 'https:' + img
                    elif img.startswith('/'):
                        from urllib.parse import urljoin
                        img = urljoin(url, img)
                    logger.info(f"  🖼️  Found og:image: {img[:80]}")
                    return img
        
        logger.info(f"  🖼️  No og:image found at {url[:60]}")
        return None
    except Exception as e:
        logger.warning(f"  🖼️  Failed to fetch og:image from {url[:60]}: {e}")
        return None

def image_url_renders(image_url: str, max_bytes: int = 10 * 1024 * 1024) -> bool:
    """True if the URL fetches as an image Pillow can decode. The manual
    path bypasses scribe's rehost pipeline, so this is its equivalent guard:
    an image that won't decode (SVG, timeout, 403, oversize, junk) must not
    ship as the final imageUrl — callers fall back to the category default.
    Local paths (already-hosted uploads) pass without a fetch. Pillow-only —
    SVG has no decoder here and correctly fails closed."""
    if not image_url.startswith(('http://', 'https://')):
        return True
    try:
        resp = requests.get(image_url, timeout=10, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ArcCodex/1.0)'
        })
        if resp.status_code != 200:
            return False
        if not resp.headers.get('content-type', '').startswith('image/'):
            return False
        raw = b''
        for chunk in resp.iter_content(chunk_size=65536):
            raw += chunk
            if len(raw) > max_bytes:
                return False
        import io
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
        return True
    except Exception as e:
        logger.info(f"  🖼️  Image validation failed ({type(e).__name__}): {image_url[:80]}")
        return False

def parse_upload_file(filepath):
    """
    Parse an upload file with format:
    ---
    {"original_url": "...", "image_url": "..."}
    ---
    Title Here
    Article content here...
    """
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
            # Try UTF-8 first, fallback to latin-1
            try:
                full_content = content.decode('utf-8', errors='replace').strip()
            except Exception:
                full_content = content.decode('latin-1', errors='replace').strip()
        
        # Split by --- separator
        parts = full_content.split('---', 2)
        
        # Extract metadata if present
        metadata = {}
        if len(parts) > 1:
            try:
                metadata = json.loads(parts[1].strip())
            except (json.JSONDecodeError, IndexError):
                logger.warning(f"Could not parse metadata from {filepath}, continuing without it")
        
        # Get the main content (title + article text)
        main_content = parts[-1].strip()
        
        # First line is title, rest is article text
        lines = main_content.split('\n', 1)
        title = lines[0].strip()
        article_text = lines[1].strip() if len(lines) > 1 else ""
        
        if not title or not article_text:
            raise ValueError("Missing title or article text")
        
        return title, article_text, metadata
        
    except Exception as e:
        logger.error(f"Error parsing file {filepath}: {e}")
        raise

def process_manual_upload(filepath, api_client):
    """Process a single manual upload file WITH FULL ANALYSIS"""
    filename = os.path.basename(filepath)
    logger.info(f"📥 Processing manual upload: {filename}")
    
    try:
        # Parse the file
        title, article_text, metadata = parse_upload_file(filepath)
        logger.info(f"  Title: {title[:60]}...")
        logger.info(f"  Content length: {len(article_text)} chars")
        
        # Generate article hash
        article_hash = get_article_hash(title, article_text)
        logger.info(f"  Article hash: {article_hash}")
        
        # Analyze the content
        logger.info(f"  🔍 Analyzing content...")
        dossier = api_client.pre_analyze(article_text, article_hash)
        if not dossier:
            dossier = {'sentiment': 0.0, 'civility': 0.5, 'chimera_score': 0.0}
            logger.warning(f"  Analysis failed, using default scores")
        else:
            logger.info(f"  Chimera Score: {dossier.get('chimera_score', 0.0)}")
        
        # Prepare article for publishing - prefer article's own image
        category = metadata.get('category', 'general')
        source_url = metadata.get('original_url', '')
        
        # Image priority: explicit metadata > og:image from URL > category default.
        # External candidates must actually render (see image_url_renders) —
        # a failed source URL never ships as the final imageUrl.
        image_url = metadata.get('image_url', '')
        if not image_url and source_url:
            image_url = fetch_og_image(source_url) or ''
        if image_url and not image_url_renders(image_url):
            logger.info(f"  🖼️  Image failed validation — using category default instead: {image_url[:80]}")
            image_url = ''
        if not image_url:
            image_url = CATEGORY_IMAGES.get(category, DEFAULT_IMAGE_URL)
        
        logger.info(f"  Category: {category} → image: {image_url[:80]}")
        
        article_data = {
            "id": article_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "Manual Upload",
            "title": title,
            "url": f"https://arc-codex.com/article/{article_hash}",
            "sourceUrl": source_url,
            "imageUrl": image_url,
            "dossier": json.dumps(dossier),
            "original_text": sanitize_active_content(article_text),
            "directive": metadata.get('category', 'Manual Publish'),
            "category": category,
            "blue_team_analysis": "",
            "red_team_analysis": "",
            "purple_team_analysis": "",
            "sentinel_analysis": ""
        }
        
        # Publish to Redis via backend API
        logger.info(f"  📤 Publishing to feed...")
        result = api_client.publish_article(article_data)
        
        if not (result and result.get('success')):
            raise Exception(f"Publish failed: {result}")
        
        logger.info(f"✅ Successfully published: {title}")
        
        # --- BLUE/RED/PURPLE: LAZY ANALYSIS ---
        # Skipped here — analyzer.py runs on-demand when article is first viewed.
        # This matches scribe.py v50.0 fast-publish pattern.
        logger.info(f"  📋 Red/Blue/Purple analysis deferred to on-demand analyzer")

        # --- SENTINEL FORENSIC PASS ---
        try:
            sentinel_data = run_sentinel_analysis(article_text)
            if sentinel_data:
                publish_analysis(stream_redis, article_hash, 'sentinel', json.dumps(sentinel_data))
                logger.info(f"  🛡️  Sentinel published for {article_hash}")
        except Exception as e:
            logger.warning(f"  🛡️  Sentinel pass failed (non-fatal): {e}")

        # --- COUNTER-ANALYST COMMENT (seeds discussion) ---
        try:
            run_counter_analyst(article_text, article_hash, stream_redis)
        except Exception as e:
            logger.warning(f"  🤖 Counter-analyst failed (non-fatal): {e}")
        
        # Move to completed
        completed_path = os.path.join(COMPLETED_DIR, filename)
        shutil.move(filepath, completed_path)
        logger.info(f"  Moved {filename} to completed/")
        return True
            
    except Exception as e:
        logger.error(f"❌ Failed to process {filename}: {e}")
        # Move to failed
        failed_path = os.path.join(FAILED_DIR, filename)
        try:
            shutil.move(filepath, failed_path)
            logger.info(f"  Moved {filename} to failed/")
        except Exception as move_error:
            logger.error(f"  Could not move {filename} to failed: {move_error}")
        return False

def main_loop():
    """Main loop - check for new files and process them"""
    logger.info("🚀 Arc Codex Manual Publisher v5.1 (LAZY ANALYSIS + OG:IMAGE EXTRACTION)")
    logger.info(f"   Watching: {PENDING_DIR}")
    logger.info(f"   Check interval: {CHECK_INTERVAL} seconds")
    logger.info(f"   Backend API: {API_BASE_URL}")
    logger.info(f"   Cloud model: {OLLAMA_CLOUD_MODEL}")
    logger.info(f"   Local fallback: {OLLAMA_LOCAL_FALLBACK}")
    logger.info("")
    
    api_client = APIClient(API_BASE_URL, SCRIBE_SECRET_KEY, logger=logger)
    
    while True:
        try:
            # Look for .txt files in pending directory
            pending_files = [
                os.path.join(PENDING_DIR, f)
                for f in os.listdir(PENDING_DIR)
                if f.endswith('.txt')
            ]
            
            if pending_files:
                logger.info(f"Found {len(pending_files)} file(s) to process")
                for filepath in pending_files:
                    process_manual_upload(filepath, api_client)
            
            # Wait before checking again
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("\n👋 Shutdown signal received. Exiting...")
            break
        except Exception as e:
            logger.error(f"🔥 Unexpected error in main loop: {e}")
            time.sleep(CHECK_INTERVAL * 2)  # Wait longer after errors

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("\n👋 Manual Publisher stopped")
