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


class OllamaTransportError(Exception):
    """Never reached the model at all — connection refused, DNS failure,
    connect timeout, or the pre-flight health check itself failing.
    Nothing about the article/prompt or the model's behavior was
    observed; this is purely infrastructure (the host, the network path,
    or a firewall between here and it). Callers should not count this
    against a per-article retry budget — retrying won't teach us
    anything about the input, only about whether the host is back.

    2026-09-12: this distinction exists because a ~10h spectre firewall
    gap made every warden narration attempt fail with a ConnectTimeout,
    indistinguishable in the log from an ordinary content rejection.
    """


class OllamaNoResponseError(Exception):
    """The host was reached and responded, but produced nothing usable —
    a non-200 status, or HTTP 200 with an empty body (e.g. gemma4-family
    thinking-phase token exhaustion, done_reason=length). This is about
    the model/host or its configured options, not about this specific
    call's input — same reasoning as OllamaTransportError, one level
    further in: the host answered, but the answer itself carries no
    information about the prompt. Callers should not count this against
    a per-article retry budget either.
    """

logger = logging.getLogger(__name__)

OLLAMA_URL            = os.environ.get("OLLAMA_URL", "http://192.168.1.185:11434")
OLLAMA_CLOUD_MODEL    = os.environ.get("OLLAMA_CLOUD_MODEL", "gemma4:31b-cloud")
OLLAMA_LOCAL_FALLBACK  = os.environ.get("OLLAMA_LOCAL_FALLBACK", "gemma4:e2b")

# Dedicated host/model for scribe.run_broadcast_script only (2026-09-11).
# Script-writing is a narrow, bounded rewrite of existing Red/Blue/Purple
# findings — unlike analysis, it doesn't need gemma4:e2b's size. Both unset
# by default so every other call_ollama_local_only() caller (analyzer.py,
# prompt_to_article.py, scribe.py's sentinel/counter-analyst passes) is
# unaffected. Set on spectre to route narration script-writing to warden
# instead of the M1, which was otherwise absorbing 100% of this load on top
# of everything else (M1 measured at 89% swap used 2026-09-11).
BROADCAST_OLLAMA_HOST  = os.environ.get("BROADCAST_OLLAMA_HOST")   # e.g. http://192.168.1.190:11434
BROADCAST_OLLAMA_MODEL = os.environ.get("BROADCAST_OLLAMA_MODEL")  # e.g. qwen2.5:1.5b

TRANSLATION_LOCK_KEY      = "translation:active"
TRANSLATION_LOCK_MAX_WAIT = 60  # seconds to wait before proceeding anyway
LOCAL_HEALTHCHECK_TIMEOUT = 2.0
LOCAL_BREAKER_TTL         = 60

# Cloud circuit breaker — set on any TERMINAL cloud response (see the
# _CLOUD_BREAKER_STATUSES set below), cleared automatically after 24 h or by
# `redis-cli DEL ollama:cloud_unavailable` once the underlying cause is fixed.
CLOUD_UNAVAILABLE_KEY = "ollama:cloud_unavailable"
CLOUD_UNAVAILABLE_TTL = 86_400  # 24 hours

# HTTP statuses that should stop us from hammering the cloud endpoint. 429 is
# transient (retry after the window closes) — a 24h reprieve is conservative
# but bounded. 401/403 is PERMANENT until a human fixes credentials; without
# tripping the breaker, every subsequent call keeps paying the auth roundtrip
# and silently degrades to local. Hunt logged 3,717 "status 401" lines in
# analyzer.log alone before this was added (2026-08-28) — same failure class
# as the AuthenticationError-subclassing-ConnectionError bug in wait_for_redis
# fixed the day before: a permanent error being retried as a transient one.
# Clearing the breaker after fixing auth: `redis-cli DEL ollama:cloud_unavailable`.
_CLOUD_BREAKER_STATUSES = frozenset({401, 403, 429})

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


def _local_breaker_key(base_url: str) -> str:
    normalized = base_url.rstrip("/").replace("://", "__").replace("/", "_")
    return f"ollama:local_unavailable:{normalized}"


def _trip_local_breaker(base_url: str) -> None:
    if _redis is not None:
        try:
            _redis.setex(_local_breaker_key(base_url), LOCAL_BREAKER_TTL, "1")
        except Exception:
            pass


def is_local_available(base_url: str | None = None, timeout: float = LOCAL_HEALTHCHECK_TIMEOUT) -> bool:
    """Fast health check for the local Ollama host."""
    host = (base_url or ollama_client.FALLBACK or OLLAMA_URL).rstrip("/")
    if _redis is not None:
        try:
            if _redis.exists(_local_breaker_key(host)):
                logger.info("🖥️  Local Ollama circuit breaker is OPEN — skipping %s", host)
                return False
        except Exception:
            pass

    try:
        resp = requests.get(f"{host}/api/tags", timeout=timeout)
        if resp.status_code == 200:
            return True
        logger.warning("🖥️  Local Ollama health check failed for %s (status %s)", host, resp.status_code)
    except requests.RequestException as exc:
        logger.warning("🖥️  Local Ollama health check failed for %s (%s)", host, type(exc).__name__)
    _trip_local_breaker(host)
    return False


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
      - options.num_ctx=16384 → per-slot context that fits spectre at -np 2
        (2026-09-13: dropped from 32768 to 16384 to make room for a second
        parallel slot on the 14 GiB inference host — llama-server is spawned
        with -c num_ctx × num_parallel, so 32768×2 overflows RAM. Pair change:
        analysis_max_chars 100000 → 50000 in arc.cfg. p99 prompt at the new
        cap measures ~18.9k gemma tokens; ~1.4% of articles on the far tail
        will still truncate silently — accepted trade for the throughput win,
        see analyzer.py:100-106 for the prior 32k-cap decision this replaces.)

    Reference implementation for future spec-following calls fleet-wide.
    """
    payload["think"] = False
    opts = payload.setdefault("options", {})
    opts.setdefault("num_predict", -1)
    opts.setdefault("num_ctx", 16384)


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


def _trip_cloud_breaker(status: int | None = None) -> None:
    """Set the 24 h Redis key that bypasses cloud in call_ollama_with_fallback.

    ``status`` — the HTTP status that tripped the breaker, if any. Used only to
    color the log line: 401/403 is auth (permanent, human action required),
    429 is rate-limit (transient, will heal). Callers that trip the breaker
    without a specific status (e.g. an assertion path) pass None.
    """
    if _redis is not None:
        _redis.setex(CLOUD_UNAVAILABLE_KEY, CLOUD_UNAVAILABLE_TTL, "1")
        if status in (401, 403):
            # ERROR: silent degrade to local is exactly what happens next;
            # someone needs to see this in the logs and fix credentials.
            logger.error(
                "🚨 Cloud circuit breaker OPEN (HTTP %s auth failure) — "
                "check OLLAMA_API_KEY / OLLAMA_CLOUD_HOST auth. Skipping cloud "
                "for 24 h; after fixing auth clear with "
                "`redis-cli DEL %s`.", status, CLOUD_UNAVAILABLE_KEY,
            )
        elif status == 429:
            logger.warning(
                "☁️  Cloud circuit breaker OPEN (HTTP 429 rate-limited) — "
                "skipping cloud for 24 h"
            )
        else:
            logger.warning(
                "☁️  Cloud circuit breaker OPEN — skipping cloud for 24 h"
            )


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
    local_host = ollama_client.FALLBACK or OLLAMA_URL

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
                if not is_local_available(local_host):
                    logger.warning("🖥️  Local model skipped for %s — health check unavailable", local_host)
                    continue
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

            if resp.status_code in _CLOUD_BREAKER_STATUSES and label == "cloud":
                _trip_cloud_breaker(resp.status_code)

            logger.warning(f"{label.capitalize()} model failed (status {resp.status_code}), trying next")

        except Exception as e:
            if label == "local" and isinstance(e, requests.RequestException):
                _trip_local_breaker(local_host)
            logger.warning(f"{label.capitalize()} model error: {e}, trying next")

    tried = ", ".join(m for m, _ in candidates) or "(none)"
    raise Exception(f"All Ollama models failed (tried {tried})")


def call_ollama_local_only(prompt_text: str, timeout: int = 900, *,
                            host: str | None = None, model: str | None = None,
                            num_predict: int | None = None):
    """
    Call Ollama using the local model only (OLLAMA_LOCAL_FALLBACK) — never the cloud model.
    No local-to-local fallback: one local model, one attempt.
    Used by scribe.py to avoid cloud API costs during background ingestion.

    host/model: override the configured local host/model for THIS call only.
    Used by run_broadcast_script to route to BROADCAST_OLLAMA_HOST/MODEL
    (e.g. warden + qwen2.5:1.5b) instead of the M1 + OLLAMA_LOCAL_FALLBACK.
    When given: no ollama_client primary/fallback host failover (a single
    attempt against the given host — consistent with this function's
    "one local model, one attempt" contract) and no gemma4-family
    spec-following options applied (those are scoped to the gemma4 family;
    an override is presumed to be a different, non-thinking model).

    num_predict: hard output-token ceiling for THIS call only, applied
    after (and overriding) whatever _apply_spec_following_options set —
    that function defaults gemma4-family calls to num_predict=-1
    (unbounded) via setdefault(), so an explicit value here always wins
    regardless of host/model. Unlike a length instruction in the prompt,
    this actually stops generation — see run_broadcast_script's
    BROADCAST_NUM_PREDICT for why this exists (2026-09-11: a measured,
    wide, roughly-800-to-4000-char output distribution with no visible
    pull toward the prompt's stated 1,100-char target — the instruction
    alone wasn't constraining anything). Truncation at the token cap is a
    different failure mode than the length-based rejection this pairs
    with: the response stops mid-thought rather than finishing early:
    over the cap, the reject never fires because a shorter piece never
    reaches BROADCAST_MAX_CHARS.

    Returns:
        tuple: (response_text, duration_ms, model_used)

    Raises:
        OllamaTransportError: never reached the model — connection/timeout/
            DNS, or the pre-flight health check itself failing. Not about
            this call's input; see the exception's own docstring.
        OllamaNoResponseError: the host responded but produced nothing
            usable (bad status, or HTTP 200 with an empty body). Also not
            about this call's input.
        Exception: unexpected failures not covered above (defensive
            fallback — should be rare).
    """
    _wait_for_translation()
    local_host = host or ollama_client.FALLBACK or OLLAMA_URL
    local_model = model or OLLAMA_LOCAL_FALLBACK

    for attempt_model, label in [(local_model, "local")]:
        try:
            logger.info(f"🖥️  Trying {label} model: {attempt_model} @ {local_host}")
            payload = {"model": attempt_model, "prompt": prompt_text, "stream": False}
            if not is_local_available(local_host):
                raise OllamaTransportError(f"health check failed for {local_host}")
            if model is None:
                _apply_spec_following_options(payload)
            if num_predict is not None:
                payload.setdefault("options", {})["num_predict"] = num_predict

            call_start = time.perf_counter()
            try:
                if host is None:
                    resp = ollama_client.post("/api/generate", json=payload, read_timeout=timeout)
                else:
                    resp = requests.post(f"{local_host.rstrip('/')}/api/generate",
                                          json=payload, timeout=(3.0, timeout))
            except requests.RequestException as e:
                _trip_local_breaker(local_host)
                raise OllamaTransportError(f"{attempt_model} @ {local_host} unreachable: {e}") from e
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
                    return (response_text, duration_ms, attempt_model)
                if done_reason == "length":
                    logger.warning(f"🔥 {label.capitalize()} model EMPTY (done_reason=length) — thinking-phase token exhaustion; check think=false + num_predict for {attempt_model}")
                raise OllamaNoResponseError(
                    f"{attempt_model} @ {local_host} returned an empty response "
                    f"(done_reason={done_reason!r}) in {duration_ms:.0f}ms")

            raise OllamaNoResponseError(
                f"{attempt_model} @ {local_host} failed (status {resp.status_code})")

        except (OllamaTransportError, OllamaNoResponseError):
            raise
        except Exception as e:
            if isinstance(e, requests.RequestException):
                _trip_local_breaker(local_host)
            logger.warning(f"{label.capitalize()} model error: {e}, trying next")

    raise Exception(f"Local Ollama model failed (tried {local_model} @ {local_host})")
