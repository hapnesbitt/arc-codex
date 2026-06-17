#!/usr/bin/env python3
# Filename: ollama_client.py
# Transport-layer primary/fallback wrapper for ALL Ollama HTTP calls.
#
# Why this exists
# ---------------
# Arc Codex inference is cutting over from the local M1 (192.168.1.185) to a
# remote Ollama host (Jim's RTX 5090, reachable over Tailscale). If the remote
# box is down, rebooting, or refusing connections we must fail back to the M1
# automatically, with no coordination on Jim's end. This module is that
# commitment.
#
# Scope: TRANSPORT ONLY. It does not touch model selection, per-character model
# overrides, the cloud/local model-fallback loop, the translation lock, or the
# cloud 429 circuit-breaker. Those all live in ollama_utils.py / character_builder.py
# and keep working exactly as-is. This wrapper only decides *which host* a single
# HTTP request goes to.
#
# Design notes
# ------------
# * Host failover sits UNDERNEATH the existing model-fallback loop: callers invoke
#   post() once per model attempt, so each model attempt independently gets
#   primary -> fallback. The circuit breaker stops every attempt re-paying the
#   3s connect timeout during an outage.
# * Cloud models (name ends in "-cloud", e.g. devstral-2:123b-cloud) need cloud
#   credentials/routing, which only the M1 has. They are pinned to the cloud host
#   (defaults to the fallback / M1) with NO host failover — Jim's box can't serve
#   them, so there's nowhere to fail over to. If the cloud host is unreachable the
#   request raises, and the caller's model loop drops to a local model as it does today.
# * Failover triggers ONLY on connect failure / connection refused / connect
#   timeout / HTTP 5xx. A read timeout means the box is alive but slow
#   (inference is slow by design) — we do NOT fail over on it.
#
# Config (resolution order: JSON config file > environment > built-in default)
#   OLLAMA_PRIMARY      primary base URL      (default: http://JIM_TAILSCALE_IP:11434 placeholder)
#   OLLAMA_FALLBACK     fallback base URL     (default: http://192.168.1.185:11434  the M1)
#   OLLAMA_CLOUD_HOST   host for -cloud models (default: the resolved fallback / M1)
#   OLLAMA_CONFIG_FILE  optional JSON override path (default: <thisdir>/ollama_endpoints.json)
#     JSON shape: {"primary": "...", "fallback": "...", "cloud": "..."}  (all keys optional)
#
# Cutover day = change OLLAMA_PRIMARY (one line in .env or ollama_endpoints.json) to
# Jim's Tailscale IP and restart services. No code edit.

import os
import json as _json
import time
import logging
import threading
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Built-in defaults ────────────────────────────────────────────────────────
DEFAULT_PRIMARY  = "http://JIM_TAILSCALE_IP:11434"   # placeholder — set via env/config
DEFAULT_FALLBACK = "http://192.168.1.185:11434"      # the M1

CONNECT_TIMEOUT      = 3.0     # seconds — fast fail to primary, then fail over
DEFAULT_READ_TIMEOUT = 300.0   # seconds — inference is slow; never fail over on this
BREAKER_WINDOW       = 60.0    # seconds primary is presumed down after a failover


def _resolve_endpoints():
    """Resolve (primary, fallback, cloud_host) from defaults < env < JSON file."""
    primary  = os.environ.get("OLLAMA_PRIMARY",  DEFAULT_PRIMARY)
    fallback = os.environ.get("OLLAMA_FALLBACK", DEFAULT_FALLBACK)
    cloud    = os.environ.get("OLLAMA_CLOUD_HOST")  # may be None -> default to fallback below

    cfg_path = os.environ.get(
        "OLLAMA_CONFIG_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ollama_endpoints.json"),
    )
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as fh:
                data = _json.load(fh)
            primary  = data.get("primary",  primary)
            fallback = data.get("fallback", fallback)
            if data.get("cloud"):
                cloud = data["cloud"]
        except Exception as exc:
            logger.warning("ollama_client: could not read %s (%s) — using env/defaults", cfg_path, exc)

    if not cloud:
        cloud = fallback  # cloud models live on the M1 (the fallback) by default
    return primary, fallback, cloud


PRIMARY, FALLBACK, CLOUD_HOST = _resolve_endpoints()

# ── Circuit-breaker-lite state (module-level, no Redis) ──────────────────────
_breaker_lock = threading.Lock()
_primary_down_until = 0.0  # time.monotonic() value; primary skipped until then


def configure(primary=None, fallback=None, cloud=None):
    """Override endpoints at runtime (used by tests). Resets the breaker."""
    global PRIMARY, FALLBACK, CLOUD_HOST
    if primary is not None:
        PRIMARY = primary
    if fallback is not None:
        FALLBACK = fallback
    if cloud is not None:
        CLOUD_HOST = cloud
    reset_breaker()


def reset_breaker():
    global _primary_down_until
    with _breaker_lock:
        _primary_down_until = 0.0


def _primary_is_down() -> bool:
    with _breaker_lock:
        return time.monotonic() < _primary_down_until


def _trip_breaker():
    global _primary_down_until
    with _breaker_lock:
        _primary_down_until = time.monotonic() + BREAKER_WINDOW


def _is_cloud_model(model: str) -> bool:
    return bool(model) and model.strip().lower().endswith("-cloud")


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _same_host(a: str, b: str) -> bool:
    return a.rstrip("/").lower() == b.rstrip("/").lower()


def _log_failover(failed_endpoint: str, fallback_endpoint: str, error_class: str, model: str):
    """One structured, greppable line per failover event. Token: ollama_failover."""
    logger.warning(
        "ollama_failover ts=%s failed_endpoint=%s error=%s model=%s fallback_endpoint=%s",
        datetime.now(timezone.utc).isoformat(),
        failed_endpoint,
        error_class,
        model or "?",
        fallback_endpoint,
    )


def post(path: str, json=None, *, read_timeout: float = DEFAULT_READ_TIMEOUT,
         connect_timeout: float = CONNECT_TIMEOUT, **kwargs) -> requests.Response:
    """
    POST to Ollama with primary -> fallback host failover.

    Drop-in for `requests.post(f"{BASE}/api/generate", json=payload, timeout=T)`:
      before: requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=900)
      after:  ollama_client.post("/api/generate", json=payload, read_timeout=900)

    Returns the same requests.Response the call site already consumes.

    Failover (connect failure / refused / connect timeout / HTTP 5xx) is handled
    transparently. A read timeout is re-raised (box is alive but slow). Cloud
    models are pinned to the cloud host with no failover.
    """
    model = ""
    if isinstance(json, dict):
        model = json.get("model", "") or ""
    timeout = (connect_timeout, read_timeout)

    # Cloud models have a single home (cloud creds/routing) — no host failover.
    if _is_cloud_model(model):
        return requests.post(_join(CLOUD_HOST, path), json=json, timeout=timeout, **kwargs)

    primary, fallback = PRIMARY, FALLBACK

    # Inert / single-host mode: failover is meaningless if both point at one box.
    if _same_host(primary, fallback):
        return requests.post(_join(primary, path), json=json, timeout=timeout, **kwargs)

    # Breaker open: skip the dead primary and the 3s timeout, go straight to fallback.
    if _primary_is_down():
        return requests.post(_join(fallback, path), json=json, timeout=timeout, **kwargs)

    # Normal path: try primary, fail over on connect failure / 5xx only.
    try:
        resp = requests.post(_join(primary, path), json=json, timeout=timeout, **kwargs)
        if resp.status_code >= 500:
            _trip_breaker()
            _log_failover(primary, fallback, f"HTTP{resp.status_code}", model)
            return requests.post(_join(fallback, path), json=json, timeout=timeout, **kwargs)
        return resp
    except requests.exceptions.ReadTimeout:
        # Box is working but slow mid-generation — do NOT fail over.
        raise
    except requests.exceptions.ConnectionError as exc:
        # Connection refused / DNS / connect timeout (ConnectTimeout subclasses this).
        _trip_breaker()
        _log_failover(primary, fallback, type(exc).__name__, model)
        return requests.post(_join(fallback, path), json=json, timeout=timeout, **kwargs)
