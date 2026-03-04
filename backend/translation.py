"""
Arc Codex — Translation Blueprint
GET /api/translate/<article_id>?lang=<language>

Translates title, original_text, and all A.R.C. analysis fields on demand.
Ephemeral: translations are cached in Redis (24h TTL) but never overwrite
the canonical article hash, preserving original A.R.C. analysis integrity.

Register in main.py:
    from translation import translation_bp
    app.register_blueprint(translation_bp)

TranslateGemma-4B notes (Feb 28, 2026):
  - Requires /api/chat endpoint, NOT /api/generate
  - Requires ISO 639-1 language codes (te, es, fr) not English names
  - Requires specific system preamble: "You are a professional English (en) to X (code) translator..."
  - Low temperature (0.1-0.3) required — higher values cause script hallucination in Dravidian languages
  - Falls back to call_ollama_with_fallback (devstral/gemma3 on M1) on any error
"""

import json
import logging
import os
import requests as _requests
from flask import Blueprint, jsonify, request
import redis as redis_lib
from dotenv import load_dotenv

load_dotenv()
from ollama_utils import call_ollama_with_fallback

logger = logging.getLogger(__name__)
translation_bp = Blueprint("translation", __name__)

# ---------------------------------------------------------------------------
# Config — read from backend/.env
# ---------------------------------------------------------------------------
TRANSLATION_HOST  = os.environ.get("TRANSLATION_HOST", "http://192.168.1.185:11434")
TRANSLATION_MODEL = os.environ.get("TRANSLATION_MODEL", "MedAIBase/TranslateGemma:4b")

# Redis lock — signals to ollama_utils that M1 is busy with translation
TRANSLATION_LOCK_KEY = "translation:active"
TRANSLATION_LOCK_TTL = 300  # 5 min safety expiry in case of crash

# ---------------------------------------------------------------------------
# ISO 639-1 codes for TranslateGemma's 55 supported languages
# TranslateGemma requires codes, not English names
# ---------------------------------------------------------------------------
LANGUAGE_CODES = {
    "afrikaans": "af", "amharic": "am", "arabic": "ar", "bengali": "bn",
    "bulgarian": "bg", "burmese": "my", "catalan": "ca", "chinese (simplified)": "zh",
    "chinese (traditional)": "zh-TW", "croatian": "hr", "czech": "cs",
    "danish": "da", "dutch": "nl", "estonian": "et", "finnish": "fi",
    "french": "fr", "german": "de", "greek": "el", "gujarati": "gu",
    "haitian creole": "ht", "hebrew": "he", "hindi": "hi", "hungarian": "hu",
    "indonesian": "id", "italian": "it", "japanese": "ja", "kannada": "kn",
    "khmer": "km", "korean": "ko", "latvian": "lv", "lithuanian": "lt",
    "malay": "ms", "malayalam": "ml", "marathi": "mr", "nepali": "ne",
    "norwegian": "no", "persian": "fa", "farsi": "fa", "polish": "pl",
    "portuguese": "pt", "punjabi": "pa", "romanian": "ro", "russian": "ru",
    "serbian": "sr", "sinhala": "si", "slovak": "sk", "slovenian": "sl",
    "somali": "so", "spanish": "es", "swahili": "sw", "swedish": "sv",
    "tagalog": "tl", "tamil": "ta", "telugu": "te", "thai": "th",
    "turkish": "tr", "ukrainian": "uk", "urdu": "ur", "vietnamese": "vi",
    "zulu": "zu",
}

# Languages whose scripts run right-to-left
RTL_LANGUAGES = {
    "arabic", "hebrew", "urdu", "persian", "farsi", "pashto",
    "sindhi", "uyghur", "kurdish (sorani)", "yiddish",
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
_redis = redis_lib.Redis.from_url("redis://:simplenes@localhost:6379/0", decode_responses=True)
TRANSLATION_TTL         = 86_400    # 24 hours (default)
TRANSLATION_TTL_ENGLISH = 604_800   # 7 days — English translations are high-value
TRANSLATION_LANGS_TTL   = 604_800   # 7 days — langs set TTL matches longest translation

# Fields to translate
# Local model (TranslateGemma:4b): title + original_text only — A.R.C. analyses
# are too long for the 4b model within reasonable time limits.
# Pro model (devstral): all 5 fields.
TRANSLATABLE_FIELDS_LOCAL = [
    "title",
    "original_text",
]
TRANSLATABLE_FIELDS_PRO = [
    "title",
    "original_text",
    "red_team_analysis",
    "blue_team_analysis",
    "purple_team_analysis",
]
TRANSLATABLE_FIELDS = TRANSLATABLE_FIELDS_LOCAL  # default

# ---------------------------------------------------------------------------
# TranslateGemma-specific caller
# Uses /api/chat with system preamble + ISO codes + low temperature
# Falls back to call_ollama_with_fallback on any error
# ---------------------------------------------------------------------------

def _call_translation_model(text: str, language: str, timeout: int = 300) -> str:
    """
    Call TranslateGemma-4B via Ollama /api/chat.
    Uses the model's required system preamble and ISO 639-1 language codes.
    Falls back to call_ollama_with_fallback (devstral/gemma3 on M1) on error.
    """
    # Acquire translation lock — signals analysis pipeline to back off
    _redis.setex(TRANSLATION_LOCK_KEY, TRANSLATION_LOCK_TTL, "1")
    try:
      return _call_translation_model_inner(text, language, timeout)
    finally:
        _redis.delete(TRANSLATION_LOCK_KEY)


def _call_translation_model_inner(text: str, language: str, timeout: int = 300) -> str:
    """Inner implementation — called with lock held."""
    lang_lower = language.lower().strip()
    target_code = LANGUAGE_CODES.get(lang_lower, lang_lower[:2])

    system_prompt = (
        f"You are a professional English (en) to {language} ({target_code}) translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original English text "
        f"while adhering to {language} grammar, vocabulary, and cultural sensitivities. "
        f"Produce only the {language} translation, without any additional explanations or commentary."
    )

    try:
        resp = _requests.post(
            f"{TRANSLATION_HOST}/api/chat",
            json={
                "model": TRANSLATION_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        translated = result.get("message", {}).get("content", "").strip()
        if translated:
            logger.info("TranslateGemma succeeded (model=%s, lang=%s/%s)", TRANSLATION_MODEL, language, target_code)
            return translated
        logger.warning("TranslateGemma returned empty response for lang=%s", language)
    except Exception as e:
        logger.warning("TranslateGemma failed (%s), falling back to main pipeline: %s", TRANSLATION_MODEL, e)

    # Fallback — devstral or gemma3 on M1
    fallback_prompt = (
        f"Translate the following text to {language}. "
        f"Return ONLY the translated text, no commentary.\n\n{text}"
    )
    return call_ollama_with_fallback(fallback_prompt)[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_key(article_id: str, lang: str) -> str:
    safe_lang = lang.lower().replace(" ", "_")
    return f"translation:{article_id}:{safe_lang}"


def _is_rtl(lang: str) -> bool:
    return lang.lower().strip() in RTL_LANGUAGES


def _get_article(article_id: str) -> dict | None:
    """
    Fetch article hash from Redis.
    Tries direct key first, then slug/id scan — handles article page URLs
    where the route segment is a slug rather than the raw Redis key.
    """
    data = _redis.hgetall(f"article:{article_id}")
    if data:
        return data

    article_ids = _redis.zrevrange('feed', 0, -1)
    for aid in article_ids:
        candidate = _redis.hgetall(f"article:{aid}")
        if (
            candidate.get('slug') == article_id
            or candidate.get('id') == article_id
            or aid == article_id
        ):
            return candidate

    return None


def _translate(fields: dict, language: str) -> dict | None:
    """
    Translate each field individually using TranslateGemma.
    Fields are translated one at a time (model works best on plain text, not JSON).
    Returns a dict of translated fields, or None on total failure.
    """
    payload = {k: v for k, v in fields.items() if v and str(v).strip()}
    if not payload:
        return {}

    translated = {}
    for key, value in payload.items():
        result = _call_translation_model(value, language)
        if result:
            translated[key] = result
        else:
            logger.warning("Field '%s' translation failed for lang=%s — keeping original", key, language)
            translated[key] = value  # keep original on per-field failure

    return translated if translated else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@translation_bp.route("/api/translate/<article_id>", methods=["GET"])
def translate_article(article_id: str):
    lang = request.args.get("lang", "").strip()
    if not lang:
        return jsonify({"error": "Missing 'lang' query parameter"}), 400

    # Check cache first
    cache_key = _cache_key(article_id, lang)
    cached = _redis.get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            data["cached"] = True
            return jsonify(data)
        except json.JSONDecodeError:
            _redis.delete(cache_key)

    # Fetch article
    article = _get_article(article_id)
    if article is None:
        return jsonify({"error": "Article not found"}), 404

    fields_to_translate = {
        field: article.get(field, "")
        for field in TRANSLATABLE_FIELDS
    }

    # Translate
    translated = _translate(fields_to_translate, lang)
    if translated is None:
        return jsonify({"error": "Translation failed — model unavailable"}), 503

    response = {
        "article_id": article_id,
        "language": lang,
        "rtl": _is_rtl(lang),
        "cached": False,
        **translated,
    }

    # Cache result — English gets 7-day TTL (foreign->EN is high-value and slow to regenerate)
    ttl = TRANSLATION_TTL_ENGLISH if lang.lower() == "english" else TRANSLATION_TTL
    try:
        pipe = _redis.pipeline()
        pipe.setex(cache_key, ttl, json.dumps(response, ensure_ascii=False))
        # Track which languages are cached for this article (for EN pill in UI)
        langs_key = f"translation:langs:{article_id}"
        pipe.sadd(langs_key, lang)
        pipe.expire(langs_key, TRANSLATION_LANGS_TTL)
        pipe.execute()
    except Exception as e:
        logger.warning("Failed to cache translation: %s", e)

    return jsonify(response)


@translation_bp.route("/api/translate/<article_id>/cache", methods=["DELETE"])
def invalidate_translation_cache(article_id: str):
    """Admin: bust all cached translations for an article."""
    pattern = f"translation:{article_id}:*"
    keys = list(_redis.scan_iter(pattern))
    if keys:
        _redis.delete(*keys)
    return jsonify({"deleted": len(keys), "article_id": article_id})
