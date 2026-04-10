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
import requests
import redis as redis_lib
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_URL            = os.environ.get("OLLAMA_URL", "http://192.168.1.185:11434")
OLLAMA_CLOUD_MODEL    = os.environ.get("OLLAMA_CLOUD_MODEL", "nemotron-3-nano:30b-cloud")
OLLAMA_LOCAL_FALLBACK  = os.environ.get("OLLAMA_LOCAL_FALLBACK", "mistral:7b")
OLLAMA_LOCAL_FALLBACK2 = os.environ.get("OLLAMA_LOCAL_FALLBACK2", "llama3.2:latest")

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


def is_cloud_available() -> bool:
    """Returns True if the cloud circuit breaker is not tripped (key absent)."""
    if _redis is None:
        return True
    return not bool(_redis.exists(CLOUD_UNAVAILABLE_KEY))


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


def call_ollama_with_fallback(prompt_text: str, timeout: int = 900):
    """
    Call Ollama API with cloud model first, fallback to local if cloud fails.
    Waits for any active translation to finish before calling the M1.
    Strips <think>...</think> reasoning blocks from thinking models.

    Returns:
        tuple: (response_text, duration_ms, model_used)

    Raises:
        Exception: if both cloud and local models fail.
    """
    _wait_for_translation()

    candidates = [(OLLAMA_CLOUD_MODEL, "cloud"), (OLLAMA_LOCAL_FALLBACK, "local"), (OLLAMA_LOCAL_FALLBACK2, "local2")]
    if not is_cloud_available():
        logger.info("☁️  Cloud circuit breaker is OPEN — skipping cloud model")
        candidates = [(m, l) for m, l in candidates if l != "cloud"]

    for model, label in candidates:
        try:
            logger.info(f"{'🌩️' if label == 'cloud' else '🖥️ '} Trying {label} model: {model}")
            payload = {"model": model, "prompt": prompt_text, "stream": False}

            call_start = time.perf_counter()
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
            duration_ms = (time.perf_counter() - call_start) * 1000

            if resp.status_code == 200:
                response_text = resp.json().get("response", "").strip()
                # Strip reasoning blocks from thinking models (e.g. nemotron)
                response_text = re.sub(r'^.*?</think>\s*', '', response_text, flags=re.DOTALL).strip()
                if response_text:
                    logger.info(f"✅ {label.capitalize()} model response in {duration_ms:.0f}ms ({len(response_text)} chars)")
                    return (response_text, duration_ms, model)

            if resp.status_code == 429 and label == "cloud":
                _trip_cloud_breaker()

            logger.warning(f"{label.capitalize()} model failed (status {resp.status_code}), trying next")

        except Exception as e:
            logger.warning(f"{label.capitalize()} model error: {e}, trying next")

    raise Exception(f"All Ollama models failed (tried {OLLAMA_CLOUD_MODEL}, {OLLAMA_LOCAL_FALLBACK}, {OLLAMA_LOCAL_FALLBACK2})")


def call_ollama_local_only(prompt_text: str, timeout: int = 900):
    """
    Call Ollama using local models only — never the cloud model.
    Tries OLLAMA_LOCAL_FALLBACK (mistral:7b) first, then OLLAMA_LOCAL_FALLBACK2 (llama3.2:latest).
    Used by scribe.py to avoid cloud API costs during background ingestion.

    Returns:
        tuple: (response_text, duration_ms, model_used)

    Raises:
        Exception: if both local models fail.
    """
    _wait_for_translation()

    for model, label in [(OLLAMA_LOCAL_FALLBACK, "local"), (OLLAMA_LOCAL_FALLBACK2, "local2")]:
        try:
            logger.info(f"🖥️  Trying {label} model: {model}")
            payload = {"model": model, "prompt": prompt_text, "stream": False}

            call_start = time.perf_counter()
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
            duration_ms = (time.perf_counter() - call_start) * 1000

            if resp.status_code == 200:
                response_text = resp.json().get("response", "").strip()
                response_text = re.sub(r'^.*?</think>\s*', '', response_text, flags=re.DOTALL).strip()
                if response_text:
                    logger.info(f"✅ {label.capitalize()} model response in {duration_ms:.0f}ms ({len(response_text)} chars)")
                    return (response_text, duration_ms, model)

            logger.warning(f"{label.capitalize()} model failed (status {resp.status_code}), trying next")

        except Exception as e:
            logger.warning(f"{label.capitalize()} model error: {e}, trying next")

    raise Exception(f"All local Ollama models failed (tried {OLLAMA_LOCAL_FALLBACK}, {OLLAMA_LOCAL_FALLBACK2})")
