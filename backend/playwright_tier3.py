#!/usr/bin/env python3
"""Tier-3 Playwright fetcher: last-resort stealth for bot-walled sites.

Restored 2026-07-15 after the March 2026 retirement (commit 0abc395).
See ops/RUNBOOK.md → "Playwright Tier-3 restoration" for the full story,
including the radeon-exile timeline and this module's constraint map.

Hard constraints (mapped to March/July incidents):
  RADEON EXILE — --disable-gpu + GPU sandbox off. This GPU killed ROCm-
    accelerated Playwright in March 2026 (UBSAN kernel lockup) and
    crashed Ollama via Vulkan auto-detect the morning of 2026-07-15.
    Assume it will find any new door; block them.

  FD EXHAUSTION — every fetch creates its own BrowserContext + Page,
    each closed in try/finally. Browser restarts every RESTART_EVERY
    fetches so incremental leaks can't accumulate across a long scribe
    run. RSS instrumented on every fetch (steady state + peak logged).

  PLAY-NICELY — one browser, all fetches serialized behind _lock;
    per-fetch wall-clock timeout via a supervisor thread that
    process-tree-kills the browser subprocess on expiry; startup hook
    kills orphaned browsers whose env holds our SIGNATURE_ENV marker
    (we set it via playwright's launch(env=…) — it flows into the
    chromium subprocess's /proc/<pid>/environ and NEVER appears in
    Ross's desktop Chrome, which is the whole point of using env vs
    a --flag: --user-data-dir is rejected by Playwright, and generic
    chromium flags could collide with a real desktop browser).
"""
from __future__ import annotations

import logging
import os
import queue
import random
import signal
import tempfile
import threading
import time
from typing import Optional

import psutil  # for RSS + process-tree kill

from fetch_utils import (
    DEFAULT_IMAGE_URL,
    MIN_ARTICLE_LENGTH,
    USER_AGENTS,
    detect_and_decode_content,  # unused but kept for parity
    extract_image_url,
    extract_with_beautifulsoup,
)
import trafilatura

logger = logging.getLogger(__name__)

# --- Config ------------------------------------------------------------------

# Signature env var passed into the chromium subprocess via playwright's
# launch(env=…). Zombie killer matches on /proc/<pid>/environ for this
# key. Unique to us — Ross's desktop Chrome will never have it in env.
SIGNATURE_ENV = "ARC_TIER3_PLAYWRIGHT"
SIGNATURE_VAL = "1"

# Per-fetch wall-clock. Playwright's own goto timeout is 15s; this is the
# outer supervisor that kills the browser subprocess tree if the whole
# fetch (nav + wait + extract) hangs beyond this.
FETCH_TIMEOUT_SECONDS = 45

# Restart the browser every N fetches to bound fd/handle accumulation.
# Chosen 50 to match the pre-retirement BROWSER_RECYCLE_INTERVAL doctrine.
RESTART_EVERY = 50

# Launch args — see docstring; --disable-gpu is the load-bearing arg.
# --no-sandbox because chromium sandbox needs suid-root helpers we don't
# have. --disable-dev-shm-usage avoids /dev/shm oom on smaller boxes.
_LAUNCH_ARGS = [
    "--disable-gpu",              # RADEON EXILE (March ROCm + July Vulkan)
    "--use-gl=disabled",          # belt-and-braces: no GL context at all
    "--disable-software-rasterizer",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-features=VizDisplayCompositor",
]

# Env passed to the chromium subprocess — carries SIGNATURE_ENV for the
# zombie killer AND inherits DISPLAY-less environment so no X server
# access is attempted (belt-and-braces on top of --disable-gpu).
_LAUNCH_ENV = {
    SIGNATURE_ENV: SIGNATURE_VAL,
    # Force no display; some GPU probes trip on DISPLAY existing.
    "DISPLAY": "",
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LANG": os.environ.get("LANG", "C.UTF-8"),
}

_STEALTH_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {} };
"""

# --- State -------------------------------------------------------------------

# Playwright's sync API is greenlet-bound to the thread that started it —
# any call from a different thread raises "cannot switch to a different
# thread". Scribe calls fetch_article_data() from a ThreadPoolExecutor
# (candidate-analysis pool), so caller thread varies. To satisfy the
# thread-affinity constraint AND still serialize fetches, we own a
# dedicated worker thread. Public fetch_stealth() enqueues a job on
# _work_q and blocks on its per-job reply queue. Worker owns _pw/_browser.

_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()   # only used to start the worker once
_work_q: "queue.Queue" = queue.Queue()  # items: (url, headers, reply_q)
_SHUTDOWN = object()              # sentinel to stop the worker

_pw = None                       # playwright driver handle (worker-owned)
_browser = None                  # single Browser instance (worker-owned)
_browser_pid: Optional[int] = None
_fetch_count = 0
_peak_rss_mb = 0.0                # highest RSS observed across the run


# --- Zombie signature scan ---------------------------------------------------

def _proc_has_signature(pid: int) -> bool:
    """True iff /proc/<pid>/environ contains our SIGNATURE_ENV marker."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            environ = f.read()
    except (FileNotFoundError, PermissionError):
        return False
    marker = f"{SIGNATURE_ENV}={SIGNATURE_VAL}".encode()
    # environ is NUL-separated KEY=VALUE pairs.
    return marker in environ


def startup_kill_zombies() -> int:
    """On scribe boot, kill any leftover chromium/headless_shell from a
    prior run that carries our env-var signature.

    MATCHES ON /proc/<pid>/environ, NOT PROCESS NAME. Ross's desktop
    Chrome and any other unrelated chromium are safe — they don't have
    ARC_TIER3_PLAYWRIGHT=1 in their environment.
    """
    killed = 0
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if not _proc_has_signature(p.info["pid"]):
                continue
            p.terminate()
            try:
                p.wait(timeout=3)
            except psutil.TimeoutExpired:
                p.kill()
            killed += 1
            logger.warning(
                "🧟 Killed orphan Playwright browser pid=%s name=%s",
                p.info["pid"], p.info.get("name"),
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        logger.info("🧟 startup_kill_zombies: reaped %d orphan(s)", killed)
    return killed


# --- Browser lifecycle -------------------------------------------------------

def _launch_browser():
    """Start a fresh Playwright + chromium. Caller must hold _lock."""
    global _pw, _browser, _browser_pid, _fetch_count
    from playwright.sync_api import sync_playwright
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(
        headless=True,
        args=_LAUNCH_ARGS,
        env=_LAUNCH_ENV,
    )
    # Grab the chromium PID (a descendant of our process, marked with our
    # SIGNATURE_ENV) for RSS + kill-on-timeout + zombie kill.
    _browser_pid = _find_browser_pid()
    _fetch_count = 0
    logger.info("🎭 Playwright browser launched (pid=%s, signature=%s)",
                _browser_pid, SIGNATURE_ENV)


def _shutdown_browser():
    """Close browser + stop driver. Caller must hold _lock. Idempotent."""
    global _pw, _browser, _browser_pid
    if _browser is not None:
        try:
            _browser.close()
        except Exception as exc:
            logger.warning("browser.close() raised: %s", exc)
    if _pw is not None:
        try:
            _pw.stop()
        except Exception as exc:
            logger.warning("playwright.stop() raised: %s", exc)
    # Belt-and-braces: kill anything still bound to our profile dir.
    if _browser_pid is not None:
        try:
            _kill_process_tree(_browser_pid)
        except Exception:
            pass
    _pw = None
    _browser = None
    _browser_pid = None


def _find_browser_pid() -> Optional[int]:
    """Walk our process tree looking for a child whose environ carries
    our SIGNATURE_ENV marker. Robust across Playwright driver versions."""
    me = psutil.Process(os.getpid())
    for child in me.children(recursive=True):
        try:
            if _proc_has_signature(child.pid):
                return child.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _kill_process_tree(pid: int) -> None:
    """SIGTERM then SIGKILL the process and all descendants."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    procs = parent.children(recursive=True) + [parent]
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _, alive = psutil.wait_procs(procs, timeout=3)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def _browser_rss_mb() -> float:
    """Sum RSS of the browser + all its descendants, in MB."""
    if _browser_pid is None:
        return 0.0
    try:
        parent = psutil.Process(_browser_pid)
    except psutil.NoSuchProcess:
        return 0.0
    total = 0
    try:
        total += parent.memory_info().rss
        for c in parent.children(recursive=True):
            try:
                total += c.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0.0
    return total / (1024 * 1024)


# --- Fetch supervisor: hard timeout with process-tree kill -------------------
#
# Playwright's sync API is greenlet-bound to the thread that started it —
# calling browser.new_context() from a different thread raises "cannot
# switch to a different thread". So the fetch runs on the CALLER's thread
# (fetches are already serialized here behind _lock), and a small watchdog
# thread is armed only to kill the browser subprocess if the whole fetch
# hangs past FETCH_TIMEOUT_SECONDS. SIGKILL from another thread is fine;
# it makes the caller's playwright RPC calls raise on the next await.

def _fetch_with_supervisor(headers: dict, url: str) -> Optional[dict]:
    """Do the Playwright fetch on the caller's thread with a watchdog
    that kills the browser subprocess on timeout. try/finally guarantees
    context+page cleanup (fd-exhaustion fix)."""
    done = threading.Event()
    timed_out = {"flag": False}

    def _watchdog():
        if not done.wait(FETCH_TIMEOUT_SECONDS):
            timed_out["flag"] = True
            logger.error(
                "🔪 Playwright fetch exceeded %ds for %s — killing browser process tree",
                FETCH_TIMEOUT_SECONDS, url,
            )
            if _browser_pid is not None:
                _kill_process_tree(_browser_pid)

    wd = threading.Thread(target=_watchdog, name="pw-watchdog", daemon=True)
    wd.start()

    context = None
    page = None
    data = None
    try:
        context = _browser.new_context(
            user_agent=headers.get("User-Agent", random.choice(USER_AGENTS)),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers=headers,
        )
        context.add_init_script(_STEALTH_INIT_SCRIPT)
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=15000)
        page.wait_for_timeout(2000)
        html = page.content()

        article_text = trafilatura.extract(html)
        if not article_text or len(article_text) < MIN_ARTICLE_LENGTH:
            article_text = extract_with_beautifulsoup(html, url)

        if article_text and len(article_text) > MIN_ARTICLE_LENGTH:
            has_captcha = ("captcha" in html.lower()
                           or "cloudflare" in html.lower())
            if has_captcha:
                logger.warning("⚠️  CAPTCHA present but extracted %d chars from %s",
                               len(article_text), url)
            else:
                logger.info("✅ Playwright stealth succeeded for %s", url)
            data = {
                "text": article_text,
                "image_url": extract_image_url(html) or DEFAULT_IMAGE_URL,
            }
        else:
            logger.warning("❌ Playwright stealth: no usable content from %s", url)
    except Exception as exc:
        if timed_out["flag"]:
            logger.warning("Playwright stealth killed by watchdog for %s", url)
        else:
            logger.warning("Playwright stealth failed for %s: %s", url, exc)
    finally:
        # Guaranteed cleanup — every fetch closes its context+page even if
        # the page itself crashed. This is the fd-exhaustion fix.
        if page is not None:
            try: page.close()
            except Exception: pass
        if context is not None:
            try: context.close()
            except Exception: pass
        done.set()  # disarm watchdog
    return data


# --- Public API --------------------------------------------------------------

def _worker_loop():
    """The one and only thread that touches Playwright. Serves jobs off
    _work_q, owns _pw/_browser lifecycle, handles restart-every-N.
    """
    global _fetch_count, _peak_rss_mb, _browser, _browser_pid
    logger.info("🎭 Playwright worker thread started (tid=%s)",
                threading.get_ident())
    while True:
        job = _work_q.get()
        if job is _SHUTDOWN:
            _shutdown_browser()
            logger.info("🎭 Playwright worker thread exiting")
            return
        url, headers, reply_q = job
        try:
            # Restart every N fetches OR if a prior kill left it gone.
            needs_restart = (
                _browser is None
                or _fetch_count >= RESTART_EVERY
                or (_browser_pid is not None and not psutil.pid_exists(_browser_pid))
            )
            if needs_restart and _browser is not None:
                logger.info("🎭 Restarting Playwright browser (fetch_count=%d)",
                            _fetch_count)
                _shutdown_browser()
            if _browser is None:
                _launch_browser()

            _fetch_count += 1
            data = _fetch_with_supervisor(headers, url)

            rss_mb = _browser_rss_mb()
            if rss_mb > _peak_rss_mb:
                _peak_rss_mb = rss_mb
            logger.info(
                "🎭 tier3 fetch #%d rss=%.1fMB peak=%.1fMB url=%s",
                _fetch_count, rss_mb, _peak_rss_mb, url,
            )
            reply_q.put(("ok", data))
        except Exception as exc:
            logger.exception("Worker exception on %s: %s", url, exc)
            reply_q.put(("err", None))


def _ensure_worker():
    """Start the worker thread on first use. Idempotent."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop, name="pw-worker", daemon=True,
        )
        _worker_thread.start()


def fetch_stealth(url: str, headers: dict) -> Optional[dict]:
    """Tier-3 fetch. Callable from any thread; the actual Playwright work
    runs on the dedicated worker thread (Playwright's sync API is
    greenlet-bound to its starting thread).

    Returns {'text': ..., 'image_url': ...} on success, None on failure.
    Failures are non-fatal: caller falls through to its own dead-URL cache.
    """
    _ensure_worker()
    reply_q: "queue.Queue" = queue.Queue(maxsize=1)
    _work_q.put((url, headers, reply_q))
    # Bound the wait: FETCH_TIMEOUT_SECONDS + margin for context/lock/cleanup.
    try:
        status, data = reply_q.get(timeout=FETCH_TIMEOUT_SECONDS + 15)
    except queue.Empty:
        logger.error("🔪 Worker did not respond in %ds for %s",
                     FETCH_TIMEOUT_SECONDS + 15, url)
        return None
    return data if status == "ok" else None


def shutdown() -> None:
    """Explicit shutdown for scribe exit paths. Safe to call multiple times."""
    if _worker_thread is not None and _worker_thread.is_alive():
        _work_q.put(_SHUTDOWN)
        _worker_thread.join(timeout=10)
