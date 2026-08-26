#!/usr/bin/env python3
"""audio_backfill.py — one-shot narration pass over silent articles.

Why this exists
---------------
Scribe's audio pass looks at the newest AUDIO_SCAN_WINDOW articles only:
a story published while narration was busy that then falls out of that
window never gets audio, ever. The window is now publish-rate-derived and
clamped (see scribe.py AUDIO_SCAN_* / arc.cfg [audio]), which stops NEW
silence from accumulating — but the backlog that piled up under the old
fixed-50 window is still there. This script walks the whole feed once and
narrates whatever is still silent, one article at a time.

Not a service. A CLI you run when you want to clear the backlog.

Coordination with the live audio pass
-------------------------------------
Both paths run on the same box and both drive Kokoro through subprocess,
so they must not run in parallel. Two levers:

  1. AUDIO_MIN_FREE_MB preflight. Live-imported from scribe.py so we honour
     the same 2600 MB floor scribe uses. If a scribe pass has started a
     Kokoro run, available memory drops below that and this loop defers.
     Symmetric — this loop's Kokoro run will cause scribe's preflight to
     defer the next time it fires.

  2. arc:audio:active Redis mutex (SET NX EX). Self-serialization first —
     two `audio_backfill.py` invocations in the same window can't both
     synthesize — and it's the primitive scribe's audio pass will grow
     into if we ever want the two paths to strictly interlock. Today it's
     backfill-side only; the memory preflight handles the scribe direction.

Do NOT bypass the preflight. This is the "yield to live work" rule — a
backfill run is catch-up, live scribe narration is fresher and matters
more; the memory floor is what makes catch-up defer instead of compete.

Peak-window fence
-----------------
arc.cfg [audio].peak_start_hour / peak_end_hour define a half-open
[start, end) blackout in local time; peak_weekdays_only leaves Sat/Sun
unfenced. Checked between articles, never mid-synthesis — a run that
straddles the boundary finishes the article it's on before pausing.

Usage
-----
  python3 audio_backfill.py --limit 3          # smoke test
  python3 audio_backfill.py                    # everything silent
  python3 audio_backfill.py --dry-run          # list candidates only
  python3 audio_backfill.py --ignore-peak      # weekday emergency catch-up

Reports one line per candidate; on success also emits duration + kbps so
Ross can eyeball "did that actually decode plausibly" without a separate
ffprobe run.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime

# --- Path setup: run from anywhere under the repo ---------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dotenv import load_dotenv                                                # noqa: E402
load_dotenv(os.path.join(_HERE, '.env'))

import redis                                                                  # noqa: E402
from site_config import load_site_config                                      # noqa: E402
# Import scribe LAST — it constructs an audio ThreadPoolExecutor at import
# time. That's cheap (max_workers=1, no threads spawned until submit) but it
# means we're taking on scribe's full module footprint here. Acceptable: the
# alternative is duplicating synthesize_article_audio() and drifting from it.
import scribe                                                                 # noqa: E402


# --- Logging: single stream to stdout, no file handler ----------------------
# Backfill is CLI-invoked; the operator watches stdout live. We deliberately
# leave the root logger to scribe's own handlers (which write to scribe.log)
# so that synthesize_article_audio's INFO/WARNING lines land in the same log
# they always did — Ross greps scribe.log for "🔊", not a second file.
logger = logging.getLogger("audio_backfill")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                      "%H:%M:%S"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# --- Coordination primitives -----------------------------------------------
AUDIO_MUTEX_KEY = "arc:audio:active"
AUDIO_MUTEX_TTL = scribe.AUDIO_TIMEOUT_SECONDS + 60   # a stuck synth expires

# How long to wait, and how often to poll, when either the mutex is held or
# the memory preflight is failing. Both cases are "someone else is doing
# audio; check back shortly". 30 s matches roughly half of one narration.
DEFER_POLL_SECONDS = 30
DEFER_BUDGET_SECONDS = 30 * 60   # give up on one article after 30 min of yielding


@dataclass
class Result:
    ok: int = 0
    skipped_short: int = 0
    skipped_lang: int = 0
    failed_synth: int = 0
    deferred_too_long: int = 0


def in_peak_window(cfg_audio: dict) -> bool:
    """True if now is inside the [start, end) peak-hour blackout.

    Weekday-only if peak_weekdays_only; weekends are always outside.
    """
    if cfg_audio.get("peak_weekdays_only", True):
        # Monday=0 … Sunday=6; weekends unfenced.
        if datetime.now().weekday() >= 5:
            return False
    hour = datetime.now().hour
    start = int(cfg_audio.get("peak_start_hour", 14))
    end = int(cfg_audio.get("peak_end_hour", 19))
    return start <= hour < end


def wait_out_peak(cfg_audio: dict) -> None:
    """Block until we exit the peak window (checked every minute)."""
    logged = False
    while in_peak_window(cfg_audio):
        if not logged:
            logger.info("⏸  in peak-hour blackout — waiting it out")
            logged = True
        time.sleep(60)
    if logged:
        logger.info("▶  peak window ended — resuming")


def find_silent(r: redis.Redis) -> list[tuple[str, str]]:
    """All articles missing audio, newest first: (id, body).

    Applies the same filters scribe.py's audio pass does — English,
    body ≥ AUDIO_MIN_CHARS — so the "candidate" count matches what would
    ever have been synthesized. Scans the whole feed ZSET, not just the
    top-N: that's the whole point of a backfill.
    """
    ids = r.zrevrange('feed', 0, -1)
    if not ids:
        return []

    # HMGET one at a time via pipeline in a single round-trip.
    pipe = r.pipeline()
    for aid in ids:
        pipe.hmget(f"article:{aid}",
                   ['audio_url', 'source_lang', 'original_text'])
    rows = pipe.execute()

    out: list[tuple[str, str]] = []
    for aid, (audio_url, lang, body) in zip(ids, rows):
        if audio_url:
            continue
        if (lang or 'English') != 'English':
            continue
        body = (body or '').strip()
        if len(body) < scribe.AUDIO_MIN_CHARS:
            continue
        out.append((aid, body))
    return out


def acquire_mutex(r: redis.Redis) -> bool:
    """Try to take arc:audio:active; return True on success."""
    return bool(r.set(AUDIO_MUTEX_KEY, "backfill", nx=True, ex=AUDIO_MUTEX_TTL))


def release_mutex(r: redis.Redis) -> None:
    """Drop the mutex. Best-effort — the TTL is our safety net if release fails."""
    try:
        r.delete(AUDIO_MUTEX_KEY)
    except Exception as e:
        logger.warning(f"could not release {AUDIO_MUTEX_KEY}: {e}")


def yield_until_ready(r: redis.Redis) -> str | None:
    """Wait for both the mutex and the memory preflight to clear.

    Returns None when both are green (caller may proceed and holds the
    mutex), or a "gave up" reason string if the defer budget is exhausted.
    On success the mutex IS acquired here — caller must release_mutex().
    """
    started = time.time()
    while True:
        # Preflight first: cheaper than a Redis round-trip and the failure
        # we most want to log (memory tight) is more actionable than "the
        # mutex is held".
        pf = scribe.kokoro_preflight()
        if pf is None and acquire_mutex(r):
            return None

        elapsed = time.time() - started
        if elapsed > DEFER_BUDGET_SECONDS:
            reason = pf[0] if pf else "mutex still held"
            return f"defer budget exhausted after {int(elapsed)}s ({reason})"

        # If we got the mutex but preflight failed, release it before sleeping
        # so scribe's live pass can grab it if it comes along.
        if pf is not None:
            # We hadn't acquired; nothing to release.
            reason = pf[0]
        else:
            release_mutex(r)
            reason = "mutex held by another audio worker"
        logger.info(f"⏸  yielding {DEFER_POLL_SECONDS}s — {reason}")
        time.sleep(DEFER_POLL_SECONDS)


def probe_duration_seconds(path: str) -> float | None:
    """ffprobe the finished mp3 for its container-reported duration.

    Nice-to-have — the backfill smoke test asks for "plausible durations",
    which is exactly what this returns. Nothing critical rides on it, so a
    missing ffprobe or a parse failure just returns None.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return None
        return float(out.stdout.strip())
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        return None


def run(limit: int, dry_run: bool, ignore_peak: bool) -> Result:
    site = load_site_config()
    cfg_audio = site["audio"]

    r = redis.Redis(decode_responses=True,
                    password=os.environ['REDIS_PASSWORD'],
                    db=site.redis_db)

    logger.info(f"scanning {site.slug} feed for silent articles…")
    candidates = find_silent(r)
    logger.info(f"found {len(candidates)} silent candidates "
                f"(English, body ≥ {scribe.AUDIO_MIN_CHARS} chars)")

    if limit:
        candidates = candidates[:limit]
        logger.info(f"limited to first {limit} for this run")

    if not candidates:
        return Result()

    if dry_run:
        for aid, body in candidates:
            logger.info(f"  would narrate {aid} ({len(body)} chars)")
        return Result()

    result = Result()
    for i, (aid, body) in enumerate(candidates, 1):
        # Peak window check happens between articles, not mid-synthesis.
        if not ignore_peak:
            wait_out_peak(cfg_audio)

        held = False
        gave_up = yield_until_ready(r)
        if gave_up:
            logger.warning(f"[{i}/{len(candidates)}] {aid} — {gave_up}")
            result.deferred_too_long += 1
            continue
        held = True

        try:
            started = time.perf_counter()
            audio_url = scribe.synthesize_article_audio(aid, body)
            wall = time.perf_counter() - started

            if not audio_url:
                # synthesize_article_audio already logged the reason
                result.failed_synth += 1
                logger.warning(
                    f"[{i}/{len(candidates)}] {aid} — synthesis returned None "
                    f"after {wall:.1f}s")
                continue

            # Persist the field the same way scribe does — one write, one
            # field, hset. Nothing else on the hash changes.
            r.hset(f"article:{aid}", 'audio_url', audio_url)

            # Plausibility check: decode duration, compare to text length.
            # Kokoro at 0.95x speed lands around 15 chars/second on English
            # prose, so a 2000-char article is roughly 130s. Anything wildly
            # off (a 5s mp3 for a 2000-char article) is worth flagging.
            audio_path = os.path.join(
                os.path.dirname(_HERE), 'frontend', 'public',
                'uploads', 'audio', f"{aid}.mp3")
            dur = probe_duration_seconds(audio_path)
            if dur is None:
                logger.info(
                    f"[{i}/{len(candidates)}] {aid} ✓ {len(body)} chars → "
                    f"{audio_url} ({wall:.1f}s wall, duration unknown)")
            else:
                cps = len(body) / dur if dur > 0 else 0
                flag = " ⚠ suspicious" if not (5 < cps < 40) else ""
                logger.info(
                    f"[{i}/{len(candidates)}] {aid} ✓ {len(body)} chars → "
                    f"{dur:.1f}s mp3 ({cps:.1f} chars/s, {wall:.1f}s wall){flag}")
            result.ok += 1
        finally:
            if held:
                release_mutex(r)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap at N articles (0 = no cap; default 0).")
    parser.add_argument("--dry-run", action="store_true",
                        help="List candidates; don't call Kokoro.")
    parser.add_argument("--ignore-peak", action="store_true",
                        help="Do not honour the peak-hour blackout. "
                             "For emergencies only.")
    args = parser.parse_args()

    if args.ignore_peak:
        logger.warning("--ignore-peak set — peak-hour fence disabled for this run")

    started = time.time()
    result = run(limit=args.limit, dry_run=args.dry_run,
                 ignore_peak=args.ignore_peak)
    elapsed = time.time() - started

    logger.info("─" * 60)
    logger.info(f"done in {elapsed/60:.1f} min: "
                f"ok={result.ok}, failed_synth={result.failed_synth}, "
                f"deferred_too_long={result.deferred_too_long}")
    return 0 if result.failed_synth == 0 and result.deferred_too_long == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
