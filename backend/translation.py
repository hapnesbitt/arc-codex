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
import time
from flask import Blueprint, jsonify, request
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
import redis as redis_lib
from dotenv import load_dotenv

load_dotenv()
from ollama_utils import call_ollama_with_fallback, OLLAMA_LOCAL_FALLBACK
import os

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
_redis = redis_lib.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
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
# Translation caller — LOCAL ONLY by tiering rule (2026-07-12 shed-and-yield):
# analyzers may escalate to cloud; translations never do. Before this,
# translations rode the default cloud-first chain WITHOUT record_cloud_call —
# uncounted spend against the weekly cap. Translations get the graceful
# English-degrade path in main.py instead. Ollama's per-model queue still
# serializes translation with analysis on e2b; no separate lock required.
# ---------------------------------------------------------------------------

def _call_translation_model(text: str, language: str, source_lang: str = "English", timeout: int = 300) -> str:
    """Translate ``text`` from ``source_lang`` to ``language``. Returns the
    translation as a plain string."""
    prompt = (
        f"Translate the following {source_lang} text to {language}. "
        f"Output ONLY the complete {language} translation. "
        f"Do not summarize. Do not respond in {source_lang}. Do not add any commentary.\n\n{text}"
    )
    return call_ollama_with_fallback(
        prompt,
        timeout=timeout,
        models=[(OLLAMA_LOCAL_FALLBACK, "local")],
    )[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_key(article_id: str, lang: str) -> str:
    safe_lang = lang.lower().replace(" ", "_")
    return f"translation:{article_id}:{safe_lang}"


def _is_rtl(lang: str) -> bool:
    return lang.lower().strip() in RTL_LANGUAGES


_TRUTHY = {"1", "true", "yes", "on"}


def _cached_only_requested() -> bool:
    """True when the caller asked for cache-or-nothing (?cached_only=1).

    This is the server-authoritative guarantee that a request cannot start
    inference. Callers that render a translation without a human asking for
    one — language pills, any preference-driven mount fetch — must set it, so
    "this control never triggers a model call" is enforced here rather than
    trusted to the client.
    """
    return request.args.get("cached_only", "").strip().lower() in _TRUTHY


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


def _translate(
    fields: dict, language: str, source_lang: str = "English"
) -> tuple[dict, list[str]] | None:
    """
    Translate each field individually.
    Fields are translated one at a time (model works best on plain text, not JSON).

    Returns ``(translated_fields, failed_field_names)``, or None if *every*
    field failed — the caller turns that into a 503.

    Each field is isolated. Previously a raise from _call_translation_model
    (typically the 300s read timeout) propagated straight out of the request
    handler, discarding the fields that had already translated successfully
    and returning a bare Flask 500 after minutes of work. Four good fields
    were thrown away because the fifth timed out.
    """
    payload = {k: v for k, v in fields.items() if v and str(v).strip()}
    if not payload:
        return {}, []

    translated: dict = {}
    failed: list[str] = []

    for key, value in payload.items():
        try:
            result = _call_translation_model(value, language, source_lang)
        except Exception as exc:
            logger.warning(
                "Field '%s' translation raised for lang=%s (%s) — keeping original",
                key, language, exc,
            )
            translated[key] = value
            failed.append(key)
            continue

        if result:
            translated[key] = result
        else:
            logger.warning("Field '%s' translation failed for lang=%s — keeping original", key, language)
            translated[key] = value  # keep original on per-field failure
            failed.append(key)

    if len(failed) == len(payload):
        return None

    return translated, failed


# ---------------------------------------------------------------------------
# Safety net
# ---------------------------------------------------------------------------
# Any unhandled exception in a translate route becomes a JSON 500 rather than
# Flask's default HTML 500 page. The frontend calls these endpoints as JSON
# and — after a multi-minute inference wait — needs a parseable error to
# render an actual failure state, not an unparseable HTML body.

@translation_bp.errorhandler(Exception)
def _translation_exception_handler(exc: Exception):
    # Let HTTPException instances (405, 429, future abort(), etc.) render
    # themselves via their own handling -- RateLimitExceeded has a dedicated
    # handler below; without this passthrough it would be caught here and
    # returned as a 500, masquerading as "the model itself broke."
    if isinstance(exc, HTTPException):
        return exc
    logger.exception("Unhandled exception in translate route: %s", exc)
    return jsonify({"error": "Translation service error"}), 500


@translation_bp.errorhandler(RateLimitExceeded)
def _translation_rate_limited(exc: RateLimitExceeded):
    # First-class 429: a JSON body the frontend can render (error =
    # "rate_limited" is the machine discriminator against "translation
    # failed"/500 and "no such article"/404) plus the standard Retry-After
    # header for non-frontend clients that expect the RFC-shaped signal.
    #
    # Retry-After is the window duration for the breached limit
    # (exc.limit.limit is a RateLimitItem; .get_expiry() is the window in
    # seconds). Flask-Limiter's after_request __inject_headers will overlay
    # its own precise reset_at via header.set(max(existing, computed)); the
    # window-duration we set here is the same order of magnitude and, at a
    # just-breached fresh window, exactly equal -- so the body's
    # retry_after and the response's Retry-After header agree.
    try:
        retry_after = int(exc.limit.limit.get_expiry())
    except Exception:
        retry_after = 60
    response = jsonify({
        "error": "rate_limited",
        "detail": "Translation rate limit exceeded. Try again later.",
        "retry_after": retry_after,
    })
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


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

    # Cache miss. If the caller asked for cache-or-nothing, stop here — before
    # _get_article, whose slug fallback scans the whole feed ZSET, and well
    # before _translate would call the model. 204 rather than 404 so callers
    # can tell "no cached translation" from "no such article".
    if _cached_only_requested():
        return "", 204

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
    result = _translate(fields_to_translate, lang, source_lang)
    if result is None:
        return jsonify({"error": "Translation failed — model unavailable"}), 503
    translated, failed = result

    response = {
        "article_id": article_id,
        "language": lang,
        "rtl": _is_rtl(lang),
        "cached": False,
        # Surfaced so the client can show a real error state instead of
        # presenting a half-translated article as a clean success.
        "partial": bool(failed),
        "failed_fields": failed,
        **translated,
    }

    # A partial result is deliberately NOT cached. Caching it would freeze the
    # failure for the full TTL and, worse, add the language to
    # translation:langs — advertising a complete translation that isn't one.
    # Leaving it uncached means the next reader retries and can get a whole
    # article. The cost is that a partial result is recomputed; that is the
    # right trade when the alternative is a permanent bad cache entry.
    if failed:
        logger.warning(
            "Partial translation for %s lang=%s — %d/%d fields failed (%s); not caching",
            article_id, lang, len(failed), len(fields_to_translate), ", ".join(failed),
        )
        return jsonify(response)

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


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------
# Two per-IP buckets attached from main.py after register_blueprint. Applied
# via a factory (rather than @limiter.limit decorators) because on Hunt the
# limiter lives in main.py which imports translation_bp from this module --
# a direct `from main import limiter` would circular-import. Symmetric shape
# on Arc where limiter lives in auth.py.
#
# Fresh translations: 10/hour per IP. A fresh translate costs ~150s of model
# time (5 fields x ~30s); 10/hour caps single-IP model consumption at ~25
# min/hour. B.4's semaphore caps concurrent inference; this caps per-IP
# amplification over time. The shareable ?lang= URL with 158 supported
# languages is the amplification vector this closes.
#
# cached_only=1: 120/hour. Cache-only requests provably cannot reach the
# model -- that is the guarantee the parameter exists to provide -- so a
# much higher ceiling applies. Lets a preference-driven caller (Unit D's
# language pills) page through cached translations without throttling a
# real reader switching languages across a handful of articles.
#
# BOTH exempt_when callables MUST call the shared _cached_only_requested
# predicate that the route also uses. If a caller reimplemented the
# truthy-set logic and disagreed on any value, a request the route treats
# as fresh could land in the 120/hour bucket -- 120 real inferences per
# hour per IP through a gate designed to allow zero. tests/test_translation
# pins the shared predicate against exactly that class of drift.

_RATE_LIMITED_MARKER = "_translation_rate_limits_applied"
_TRANSLATE_ENDPOINT = "translation.translate_article"


def apply_rate_limits(app, limiter):
    """Attach translate rate limits to translate_article.

    The wrapped result MUST replace the view function in app.view_functions:
    Flask-Limiter's decorated limits are only loaded via the wrapper path,
    not the middleware `before_request` path. Verified against
    flask-limiter 4.1.1 -- see flask_limiter._manager.LimitManager.resolve_limits,
    the `if not in_middleware:` gate on `decorated_limits.extend(...)`. A
    future flask-limiter upgrade that changes that dispatch shape must be
    caught here by a human, not by an M1 running hot: if the internal moves,
    decorated limits might load via before_request and this
    wrapper-replacement dance becomes unnecessary -- or, worse, doubles the
    limit count.

    Fails loudly if translate_article is not registered. A limiter that
    silently no-ops because register_blueprint(translation_bp) has not run
    yet (or the endpoint name has drifted) is the failure mode you discover
    from a bill, not a log.

    Idempotent: marks the wrapped view and returns early on re-entry. Flask
    app factories get called twice more often than anyone expects, and
    double-wrapping silently halves both limits.
    """
    if _TRANSLATE_ENDPOINT not in app.view_functions:
        raise RuntimeError(
            f"apply_rate_limits: {_TRANSLATE_ENDPOINT!r} is not registered on "
            f"the app. Either register_blueprint(translation_bp) has not run "
            f"yet, or the blueprint/view name has drifted from "
            f"{_TRANSLATE_ENDPOINT!r}. Refusing to boot with an unlimited "
            f"translate route -- a silent no-op here would go unnoticed "
            f"until the next cost spike."
        )

    view_func = app.view_functions[_TRANSLATE_ENDPOINT]
    if getattr(view_func, _RATE_LIMITED_MARKER, False):
        return

    wrapped = translate_article
    wrapped = limiter.limit(
        "120/hour",
        key_func=get_remote_address,
        exempt_when=lambda: not _cached_only_requested(),
    )(wrapped)
    wrapped = limiter.limit(
        "10/hour",
        key_func=get_remote_address,
        exempt_when=_cached_only_requested,
    )(wrapped)
    setattr(wrapped, _RATE_LIMITED_MARKER, True)
    app.view_functions[_TRANSLATE_ENDPOINT] = wrapped
