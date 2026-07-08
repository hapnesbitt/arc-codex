#!/usr/bin/env python3
# Filename: ollama_utils.py
# Shared Ollama cloud/local fallback utility for Arc Codex analysis pipeline.
# Used by: scribe.py, analyzer.py, manual_publisher.py
#
# Translation lock: if translation.py is actively using the M1, analysis calls
# back off for up to 60s rather than competing for GPU memory.

import os
import re
import time
import logging
import redis as redis_lib
import requests
from dotenv import load_dotenv

import ollama_client  # transport-layer primary/fallback host failover (owns requests)

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_URL            = os.environ.get("OLLAMA_URL", "http://192.168.1.185:11434")
OLLAMA_CLOUD_MODEL    = os.environ.get("OLLAMA_CLOUD_MODEL", "gemma4:31b-cloud")
OLLAMA_LOCAL_FALLBACK  = os.environ.get("OLLAMA_LOCAL_FALLBACK", "gemma4:e2b")

TRANSLATION_LOCK_KEY      = "translation:active"
TRANSLATION_LOCK_MAX_WAIT = 60  # seconds to wait before proceeding anyway

# Cloud circuit breaker — set on HTTP 429, cleared automatically after 24 h
CLOUD_UNAVAILABLE_KEY = "ollama:cloud_unavailable"
CLOUD_UNAVAILABLE_TTL = 86_400  # 24 hours

# Lightweight Redis connection for lock checks only
try:
    _redis = redis_lib.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=2,
    )
    _redis.ping()
except Exception:
    _redis = None


def _apply_spec_following_options(payload: dict) -> None:
    """
    Merge in the spec-following options for local (gemma4-family) calls.

    gemma4:e2b is a thinking model — with default options it exhausts its
    output-token budget inside the (hidden) thinking phase and returns HTTP 200
    with an empty response body and done_reason=length. That silently looked
    like "local model failed" and caused the "All Ollama models failed" pages
    plus a 12-day character_builder freeze while base analyses never completed.

    Fix (validated 2026-07-06 against previously-failing article
    8ed0bf56b5ed263873771e0d8f883855 and others):
      - think=false          → skip the thinking phase, emit directly
      - options.num_predict=-1 → remove output-length ceiling
      - options.num_ctx=32768 → generous context for ~4-5K-token analyzer prompts

    Reference implementation for future spec-following calls fleet-wide.
    """
    payload["think"] = False
    opts = payload.setdefault("options", {})
    opts.setdefault("num_predict", -1)
    opts.setdefault("num_ctx", 32768)


def is_cloud_available() -> bool:
    """Returns True if the cloud circuit breaker is not tripped (key absent)."""
    if _redis is None:
        return True
    return not bool(_redis.exists(CLOUD_UNAVAILABLE_KEY))


def is_cloud_reachable(timeout: float = 5.0) -> bool:
    """True if the host that serves -cloud models answers /api/tags.

    Distinct from is_cloud_available(): the circuit breaker only trips on
    HTTP 429 — an *unreachable* host never trips it. During the 2026-07-07
    M1 outage, 2,755 doomed escalations were recorded against a dead host
    because reachability was never checked before record_cloud_call().
    Callers must check this BEFORE incrementing the weekly cap counter.
    """
    try:
        resp = requests.get(
            f"{ollama_client.CLOUD_HOST.rstrip('/')}/api/tags", timeout=timeout
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _trip_cloud_breaker() -> None:
    """Set 24 h Redis key to bypass cloud after a 429 rate-limit response."""
    if _redis is not None:
        _redis.setex(CLOUD_UNAVAILABLE_KEY, CLOUD_UNAVAILABLE_TTL, "1")
        logger.warning("☁️  Cloud circuit breaker OPEN (429 received) — skipping cloud for 24 h")


def _wait_for_translation(max_wait: int = TRANSLATION_LOCK_MAX_WAIT) -> None:
    """
    Block until the translation lock is released, or max_wait seconds elapse.
    Proceeds regardless after timeout so analysis is never blocked indefinitely.
    """
    if _redis is None:
        return
    waited = 0
    while waited < max_wait:
        if not _redis.exists(TRANSLATION_LOCK_KEY):
            return
        if waited == 0:
            logger.info("⏳ Translation in progress — backing off analysis for up to %ds", max_wait)
        time.sleep(2)
        waited += 2
    logger.info("⏳ Translation lock wait expired (%ds) — proceeding anyway", max_wait)


def call_ollama_with_fallback(
    prompt_text: str,
    timeout: int = 900,
    *,
    format_schema: dict | str | None = None,
    temperature: float | None = None,
    models: list[tuple[str, str]] | None = None,
    num_ctx: int | None = None,
):
    """
    Call Ollama API with cloud model first, fallback to local if cloud fails.
    Waits for any active translation to finish before calling the M1.
    Strips <think>...</think> reasoning blocks from thinking models.

    Optional opt-in kwargs (None = today's behavior, no payload change):
        format_schema  — dict (JSON Schema) for schema-constrained decoding,
                         or the string "json" for valid-JSON only.
        temperature    — 0.0 for deterministic output. None = model default.
        models         — [(model_name, label), …] override of the default
                         cloud→local cascade. Labels are free-form for logs;
                         the literal label "cloud" still trips the 429 breaker.
        num_ctx        — override the local-path context window. Judgment tasks
                         (R/B/P, sentinel, grading) get 32768 via the spec-
                         following defaults; voice/reaction tasks should pass
                         8192 to free GPU memory. Only affects local-path calls.

    Returns:
        tuple: (response_text, duration_ms, model_used)

    Raises:
        Exception: if every candidate model fails.
    """
    _wait_for_translation()

    if models is None:
        candidates = [
            (OLLAMA_CLOUD_MODEL, "cloud"),
            (OLLAMA_LOCAL_FALLBACK, "local"),
        ]
    else:
        candidates = list(models)

    if not is_cloud_available():
        before = len(candidates)
        candidates = [(m, l) for m, l in candidates if l != "cloud"]
        if before != len(candidates):
            logger.info("☁️  Cloud circuit breaker is OPEN — skipping cloud model(s)")

    for model, label in candidates:
        try:
            logger.info(f"{'🌩️' if label == 'cloud' else '🖥️ '} Trying {label} model: {model}")
            payload: dict = {"model": model, "prompt": prompt_text, "stream": False}
            if format_schema is not None:
                payload["format"] = format_schema
            if temperature is not None:
                payload["options"] = {"temperature": temperature}
            if label == "local":
                if num_ctx is not None:
                    # Seed before spec-following defaults — its .setdefault will honor us.
                    payload.setdefault("options", {})["num_ctx"] = num_ctx
                _apply_spec_following_options(payload)

            call_start = time.perf_counter()
            resp = ollama_client.post("/api/generate", json=payload, read_timeout=timeout)
            duration_ms = (time.perf_counter() - call_start) * 1000

            if resp.status_code == 200:
                body = resp.json()
                response_text = body.get("response", "").strip()
                # Strip reasoning blocks from thinking models (e.g. nemotron)
                response_text = re.sub(r'^.*?</think>\s*', '', response_text, flags=re.DOTALL).strip()
                done_reason = body.get("done_reason", "")
                if response_text:
                    if done_reason == "length":
                        logger.warning(f"⚠️  {label.capitalize()} model TRUNCATED (done_reason=length) in {duration_ms:.0f}ms ({len(response_text)} chars) — output cap hit")
                    else:
                        logger.info(f"✅ {label.capitalize()} model response in {duration_ms:.0f}ms ({len(response_text)} chars)")
                    return (response_text, duration_ms, model)
                if done_reason == "length":
                    logger.warning(f"🔥 {label.capitalize()} model EMPTY (done_reason=length) — thinking-phase token exhaustion; check think=false + num_predict for {model}")

            if resp.status_code == 429 and label == "cloud":
                _trip_cloud_breaker()

            logger.warning(f"{label.capitalize()} model failed (status {resp.status_code}), trying next")

        except Exception as e:
            logger.warning(f"{label.capitalize()} model error: {e}, trying next")

    tried = ", ".join(m for m, _ in candidates) or "(none)"
    raise Exception(f"All Ollama models failed (tried {tried})")


def call_ollama_local_only(prompt_text: str, timeout: int = 900):
    """
    Call Ollama using the local model only (OLLAMA_LOCAL_FALLBACK) — never the cloud model.
    No local-to-local fallback: one local model, one attempt.
    Used by scribe.py to avoid cloud API costs during background ingestion.

    Returns:
        tuple: (response_text, duration_ms, model_used)

    Raises:
        Exception: if the local model fails.
    """
    _wait_for_translation()

    for model, label in [(OLLAMA_LOCAL_FALLBACK, "local")]:
        try:
            logger.info(f"🖥️  Trying {label} model: {model}")
            payload = {"model": model, "prompt": prompt_text, "stream": False}
            _apply_spec_following_options(payload)

            call_start = time.perf_counter()
            resp = ollama_client.post("/api/generate", json=payload, read_timeout=timeout)
            duration_ms = (time.perf_counter() - call_start) * 1000

            if resp.status_code == 200:
                body = resp.json()
                response_text = body.get("response", "").strip()
                response_text = re.sub(r'^.*?</think>\s*', '', response_text, flags=re.DOTALL).strip()
                done_reason = body.get("done_reason", "")
                if response_text:
                    if done_reason == "length":
                        logger.warning(f"⚠️  {label.capitalize()} model TRUNCATED (done_reason=length) in {duration_ms:.0f}ms ({len(response_text)} chars) — output cap hit")
                    else:
                        logger.info(f"✅ {label.capitalize()} model response in {duration_ms:.0f}ms ({len(response_text)} chars)")
                    return (response_text, duration_ms, model)
                if done_reason == "length":
                    logger.warning(f"🔥 {label.capitalize()} model EMPTY (done_reason=length) — thinking-phase token exhaustion; check think=false + num_predict for {model}")

            logger.warning(f"{label.capitalize()} model failed (status {resp.status_code}), trying next")

        except Exception as e:
            logger.warning(f"{label.capitalize()} model error: {e}, trying next")

    raise Exception(f"Local Ollama model failed (tried {OLLAMA_LOCAL_FALLBACK})")
