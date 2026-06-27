# backend/quiz_api.py
#
# Flask blueprint serving the Pop Quiz read endpoints.
#   GET /api/quiz              -> current week's quiz (falls back to most recent
#                                 populated week if `arc:quiz:current` is stale).
#   GET /api/quiz/<week_slug>  -> specific archived week, e.g. /api/quiz/2026-W24
#
# All payloads are precomputed by quiz_generator.py and stored as JSON strings
# in Redis under the arc:quiz:* namespace.

import json
import os
import re

import redis
from flask import Blueprint, current_app, jsonify

quiz_bp = Blueprint("quiz_bp", __name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    _r = redis.from_url(REDIS_URL, decode_responses=True)
    _r.ping()
except Exception:
    _r = None

WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")


def _payload(week_slug: str) -> dict | None:
    if _r is None:
        return None
    raw = _r.get(f"arc:quiz:{week_slug}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


@quiz_bp.route("/api/quiz", methods=["GET"])
def get_current_quiz():
    if _r is None:
        return jsonify({"error": "Database offline"}), 503

    current = _r.get("arc:quiz:current")
    if current:
        payload = _payload(current)
        if payload:
            return jsonify(payload)

    # Fallback: walk arc:quiz:* keys via SCAN, newest week first.
    weeks = []
    cursor = 0
    while True:
        cursor, batch = _r.scan(cursor=cursor, match="arc:quiz:*", count=200)
        for k in batch:
            tail = k.split(":", 2)[-1]
            if WEEK_RE.match(tail):
                weeks.append(tail)
        if cursor == 0:
            break

    if not weeks:
        return jsonify({"error": "No quiz available yet"}), 404

    weeks.sort(reverse=True)
    for slug in weeks:
        payload = _payload(slug)
        if payload:
            return jsonify(payload)

    return jsonify({"error": "No quiz available yet"}), 404


@quiz_bp.route("/api/quiz/<week_slug>", methods=["GET"])
def get_archived_quiz(week_slug: str):
    if _r is None:
        return jsonify({"error": "Database offline"}), 503
    if not WEEK_RE.match(week_slug):
        return jsonify({"error": "Bad week slug — expected YYYY-Www"}), 400
    payload = _payload(week_slug)
    if not payload:
        return jsonify({"error": "Quiz not found"}), 404
    return jsonify(payload)


@quiz_bp.route("/api/quiz/weeks", methods=["GET"])
def list_quiz_weeks():
    """Return all available week slugs, newest first. Used for /quiz archive index."""
    if _r is None:
        return jsonify([]), 503
    weeks = []
    cursor = 0
    while True:
        cursor, batch = _r.scan(cursor=cursor, match="arc:quiz:*", count=200)
        for k in batch:
            tail = k.split(":", 2)[-1]
            if WEEK_RE.match(tail):
                weeks.append(tail)
        if cursor == 0:
            break
    weeks.sort(reverse=True)
    return jsonify(weeks)
