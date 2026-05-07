"""
Arc Codex — Translation Blueprint
GET /api/translate/<article_id>?lang=<language>

Translates title, original_text, and all A.R.C. analysis fields on demand.
Ephemeral: translations are cached in Redis (24h TTL) but never overwrite
the canonical article hash, preserving original A.R.C. analysis integrity.

Register in main.py:
    from translation import translation_bp
    app.register_blueprint(translation_bp)

Translation routes through call_ollama_with_fallback (cloud → gemma4:e2b on
the M1). The previous specialty translation model was retired on 2026-05-06:
it could not co-reside in the M1's 8GB RAM with the analysis model, so
interleaved requests caused swap thrash and 120s timeouts.
"""

import json
import logging
from flask import Blueprint, jsonify, request
import redis as redis_lib
from dotenv import load_dotenv

load_dotenv()
from ollama_utils import call_ollama_with_fallback

logger = logging.getLogger(__name__)
translation_bp = Blueprint("translation", __name__)

# ---------------------------------------------------------------------------
# ISO 639-1 language codes — name → ISO. Imported by main.py to derive
# LIBRARY_SUPPORTED_LANGS for the public-domain reader.
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
    "portuguese": "pt", "brazilian portuguese": "pt-BR",
    "punjabi": "pa", "romanian": "ro", "russian": "ru",
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
# All 5 fields translated — title, original_text, red/blue/purple team analysis.
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
TRANSLATABLE_FIELDS = TRANSLATABLE_FIELDS_PRO  # translate all 5 fields

# ---------------------------------------------------------------------------
# Translation caller — routes through call_ollama_with_fallback
# (cloud → gemma4:e2b on M1). Translation and analysis share the same model
# now, so Ollama's per-model request queue serializes them; no separate
# coordination lock is required.
# ---------------------------------------------------------------------------

def _call_translation_model(text: str, language: str, source_lang: str = "English", timeout: int = 300) -> str:
    """Translate ``text`` from ``source_lang`` to ``language``. Returns the
    translation as a plain string."""
    prompt = (
        f"Translate the following {source_lang} text to {language}. "
        f"Output ONLY the complete {language} translation. "
        f"Do not summarize. Do not respond in {source_lang}. Do not add any commentary.\n\n{text}"
    )
    return call_ollama_with_fallback(prompt, timeout=timeout)[0]


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


def _translate(fields: dict, language: str, source_lang: str = "English") -> dict | None:
    """
    Translate each field individually.
    Fields are translated one at a time (model works best on plain text, not JSON).
    Returns a dict of translated fields, or None on total failure.
    """
    payload = {k: v for k, v in fields.items() if v and str(v).strip()}
    if not payload:
        return {}

    translated = {}
    for key, value in payload.items():
        result = _call_translation_model(value, language, source_lang)
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

    # Determine source language from article metadata (defaults to English)
    source_lang = article.get("source_lang") or "English"

    # Translate
    translated = _translate(fields_to_translate, lang, source_lang)
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
