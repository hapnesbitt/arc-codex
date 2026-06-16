"""
Arc Codex — Editorial Grade Blueprint
GET /api/grade/<article_id>

Grades the article as a helpful TA/editor would — constructive feedback,
letter grade, specific suggestions for clarity/evidence/structure/tone.
Cached in Redis (7 days). Never overwrites canonical article data.

Register in main.py:
    from grade import grade_bp
    app.register_blueprint(grade_bp)
"""

import json
import logging
import os
from flask import Blueprint, jsonify
import redis as redis_lib
from dotenv import load_dotenv

load_dotenv()
from ollama_utils import call_ollama_with_fallback

logger = logging.getLogger(__name__)
grade_bp = Blueprint("grade", __name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_redis = redis_lib.Redis.from_url(
    os.environ['REDIS_URL'],
    decode_responses=True
)

GRADE_TTL = 604_800  # 7 days — grades don't change

# Fields to include in the grading context
GRADE_FIELDS = [
    "title",
    "original_text",
    "red_team_analysis",
    "blue_team_analysis",
    "purple_team_analysis",
]

# ---------------------------------------------------------------------------
# TA Prompt
# ---------------------------------------------------------------------------
GRADE_SYSTEM_PROMPT = """You are a supportive editorial assistant — like a thoughtful TA or trusted editor.
Your job is to read an article and give honest, constructive feedback that helps the writer improve.

Assume good faith. The writer wants to do better.

Your response must follow this exact format:

GRADE: [A+/A/A-/B+/B/B-/C+/C/C-/D/F]

SUMMARY: [2-3 sentence overall assessment — what works, what needs work]

CLARITY: [One paragraph on how clearly the ideas are expressed. Note any confusing passages.]

EVIDENCE: [One paragraph on the quality of sources, citations, and factual grounding.]

STRUCTURE: [One paragraph on organization, flow, and paragraph structure.]

TONE: [One paragraph on whether the tone is appropriate for the subject and audience.]

SUGGESTIONS:
- [Specific, actionable suggestion 1]
- [Specific, actionable suggestion 2]
- [Specific, actionable suggestion 3]

Be direct but kind. This is feedback, not a verdict."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache_key(article_id: str) -> str:
    return f"grade:{article_id}"


def _get_article(article_id: str) -> dict | None:
    data = _redis.hgetall(f"article:{article_id}")
    if data:
        return data
    # Slug fallback
    for aid in _redis.zrevrange('feed', 0, -1):
        candidate = _redis.hgetall(f"article:{aid}")
        if (
            candidate.get('slug') == article_id
            or candidate.get('id') == article_id
            or aid == article_id
        ):
            return candidate
    return None


def _build_context(article: dict) -> str:
    """Build the article context for the grading prompt."""
    parts = []

    title = article.get("title", "").strip()
    if title:
        parts.append(f"TITLE: {title}")

    text = article.get("original_text", "").strip()
    if text:
        parts.append(f"\nARTICLE TEXT:\n{text[:3000]}")

    for field, label in [
        ("red_team_analysis",    "FACTS ANALYSIS"),
        ("blue_team_analysis",   "EXECUTIVE SUMMARY"),
        ("purple_team_analysis", "FULL ANALYSIS"),
    ]:
        val = article.get(field, "").strip()
        if val:
            parts.append(f"\n{label}:\n{val[:800]}")

    return "\n".join(parts)


def _parse_grade(text: str) -> str:
    """Extract just the letter grade from the response."""
    for line in text.split("\n"):
        if line.strip().upper().startswith("GRADE:"):
            grade = line.split(":", 1)[1].strip()
            # Normalize — take first token (handles "B+ (Good)" etc.)
            return grade.split()[0].upper() if grade else "?"
    return "?"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@grade_bp.route("/api/grade/<article_id>", methods=["GET"])
def grade_article(article_id: str):
    # Check cache
    cached = _redis.get(_cache_key(article_id))
    if cached:
        try:
            data = json.loads(cached)
            data["cached"] = True
            return jsonify(data)
        except json.JSONDecodeError:
            _redis.delete(_cache_key(article_id))

    # Fetch article
    article = _get_article(article_id)
    if article is None:
        return jsonify({"error": "Article not found"}), 404

    context = _build_context(article)
    if not context.strip():
        return jsonify({"error": "Article has no content to grade"}), 400

    # Call Ollama — try cloud first, fall back to local
    # Embed system prompt directly — call_ollama_with_fallback takes prompt_text only
    prompt = f"{GRADE_SYSTEM_PROMPT}\n\n---\n\n{context}\n\n---\n\nPlease grade this article now."
    try:
        graded_text, duration_ms = call_ollama_with_fallback(prompt, timeout=300)
    except Exception as e:
        logger.error("Grade generation failed for %s: %s", article_id, e)
        return jsonify({"error": "Grading failed — model unavailable"}), 503

    if not graded_text or len(graded_text) < 50:
        return jsonify({"error": "Model returned empty grade"}), 503

    letter_grade = _parse_grade(graded_text)

    response = {
        "article_id": article_id,
        "grade":      letter_grade,
        "feedback":   graded_text,
        "cached":     False,
    }

    # Cache for 7 days
    try:
        _redis.setex(_cache_key(article_id), GRADE_TTL, json.dumps(response, ensure_ascii=False))
        logger.info("✅ Graded article %s → %s (%.0fms)", article_id, letter_grade, duration_ms)
    except Exception as e:
        logger.warning("Failed to cache grade for %s: %s", article_id, e)

    return jsonify(response)


@grade_bp.route("/api/grade/<article_id>/cache", methods=["DELETE"])
def invalidate_grade_cache(article_id: str):
    """Admin: bust cached grade for an article."""
    deleted = _redis.delete(_cache_key(article_id))
    return jsonify({"deleted": deleted, "article_id": article_id})
