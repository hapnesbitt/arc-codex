"""
Arc Codex — User Preferences Blueprint
backend/user_prefs.py

Manages the user:{sub} Redis hash for authenticated users.
User identity arrives via X-User-Id header, set exclusively by the
Next.js server-side proxy (app/api/user/prefs/route.ts).

Security: only accepts requests from loopback (127.0.0.1).
The header cannot be spoofed by browser clients.

Register in main.py:
    from user_prefs import user_prefs_bp
    app.register_blueprint(user_prefs_bp)
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, abort
import redis as redis_lib

logger = logging.getLogger(__name__)

user_prefs_bp = Blueprint("user_prefs", __name__)

_redis = redis_lib.Redis.from_url(
    "redis://:simplenes@localhost:6379/0",
    decode_responses=True
)

# Fields that are always written on login (upsert from signIn callback)
IDENTITY_FIELDS = {"email", "name", "picture"}

# Fields the user can update themselves via PATCH
MUTABLE_FIELDS = {"preferred_lang"}


def _user_key(sub: str) -> str:
    return f"user:{sub}"


def _require_user_id() -> str:
    """
    Extract and validate X-User-Id header.
    Only accepts requests from loopback to prevent header injection from browsers.
    """
    if request.remote_addr not in ("127.0.0.1", "::1"):
        logger.warning(
            "user_prefs: rejected request from non-loopback addr %s",
            request.remote_addr
        )
        abort(403)

    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        abort(400, description="X-User-Id header required")

    return user_id


# ---------------------------------------------------------------------------
# GET /api/user/prefs — retrieve preferences
# ---------------------------------------------------------------------------
@user_prefs_bp.route("/api/user/prefs", methods=["GET"])
def get_prefs():
    sub = _require_user_id()
    key = _user_key(sub)

    data = _redis.hgetall(key)
    if not data:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"sub": sub, **data})


# ---------------------------------------------------------------------------
# POST /api/user/prefs — full upsert (called by signIn callback)
# ---------------------------------------------------------------------------
@user_prefs_bp.route("/api/user/prefs", methods=["POST"])
def upsert_prefs():
    sub = _require_user_id()
    key = _user_key(sub)
    body = request.get_json(silent=True) or {}

    now = datetime.now(timezone.utc).isoformat()
    existing = _redis.hgetall(key)

    update = {}

    # Always refresh identity fields from Google
    for field in IDENTITY_FIELDS:
        if field in body:
            update[field] = str(body[field])

    # Set created_at only on first login
    if not existing.get("created_at"):
        update["created_at"] = now

    # Always update last_seen
    update["last_seen"] = now

    # Preserve existing preferred_lang — don't overwrite on login
    if not existing.get("preferred_lang") and "preferred_lang" in body:
        update["preferred_lang"] = str(body["preferred_lang"])
    elif not existing.get("preferred_lang"):
        update["preferred_lang"] = ""

    if update:
        _redis.hset(key, mapping=update)

    logger.info("user_prefs: upserted %s (%s)", sub, body.get("email", "unknown"))
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# PATCH /api/user/prefs — partial update (called from settings panel)
# ---------------------------------------------------------------------------
@user_prefs_bp.route("/api/user/prefs", methods=["PATCH"])
def patch_prefs():
    sub = _require_user_id()
    key = _user_key(sub)
    body = request.get_json(silent=True) or {}

    if not _redis.exists(key):
        return jsonify({"error": "User not found"}), 404

    update = {}
    for field in MUTABLE_FIELDS:
        if field in body:
            update[field] = str(body[field])

    if not update:
        return jsonify({"error": "No mutable fields provided"}), 400

    _redis.hset(key, mapping=update)
    logger.info("user_prefs: patched %s → %s", sub, update)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# DELETE /api/user/prefs — remove all user data (GDPR-style self-service)
# ---------------------------------------------------------------------------
@user_prefs_bp.route("/api/user/prefs", methods=["DELETE"])
def delete_prefs():
    sub = _require_user_id()
    key = _user_key(sub)

    deleted = _redis.delete(key)
    logger.info("user_prefs: deleted %s (existed: %s)", sub, bool(deleted))
    return jsonify({"success": True, "deleted": bool(deleted)})
