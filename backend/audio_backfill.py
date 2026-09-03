#!/usr/bin/env python3
"""audio_backfill.py — sliding-window narration daemon for silent articles.

REDESIGNED 2026-08-27. Not a batch job any more — the old snapshot-and-work-
the-list version (git history has it) took a single candidate list at launch
and worked through it in order, which meant twelve hours in it was narrating
articles that were fresh at launch and long since stale, while anything
published since launch wasn't in its list at all. Ross's principle: "Any
cycles spent on anything that isn't breaking news is old news."

THE MODEL
---------
Every pass: silent articles published in the last BACKFILL_WINDOW_HOURS,
newest first (rebuilt fresh from Redis, not cached). Narrate the newest one.
Rebuild the list. Repeat. New publications enter the front of the queue
immediately — there is no snapshot to be behind.

TRAILING window, not fixed clock buckets: this isn't "the 05:00-06:00 bucket,
then the 06:00-07:00 bucket." An article published at 06:58 gets close to the
full window of attention rather than being cut off the moment the clock ticks
over. Same effect (always working the newest complete stretch, never looking
back), no cliff at the bucket boundary.

An article that ages out of the window before its turn is PERMANENTLY silent.
That is correct, deliberate behavior — this narrates breaking news, not a
historical archive, and reaching back further to "catch up" on old silence is
exactly the failure mode being designed against. The one-time 3,431-article
legacy backlog that the old batch version was working through is DECLINED,
not deferred — see ops/RUNBOOK.md 2026-08-27.

When the window is empty (everything recent already has audio), sleep briefly
and re-scan. Idle is correct behavior here, not an opportunity to reach
further back and find something to do.

NO CHECKPOINT, NO RESUME LOGIC, NO GIVE-UP BOOKKEEPING
-------------------------------------------------------
A process with no position to lose doesn't need to save one. Restart it —
planned, crashed, or a reboot — and it looks at what's silent in the current
window and continues; the worst case is losing one in-flight synthesis, never
a lost place in a list. This is also why there's no "gave up after N minutes
of waiting" accounting the old version had: when Kokoro capacity finally
frees up, the window is re-evaluated fresh, so there's no risk of finishing a
wait for a target that's gone stale — the age filter already dropped it if it
aged out, with no separate bookkeeping needed to notice.

RUNS CONTINUOUSLY
------------------
Managed by systemd (ops/systemd/audio-backfill.service) — Restart=always
with backoff, WantedBy=multi-user.target so it starts at boot without a
login (resolute has no FileVault-equivalent gate blocking that, unlike the
M1). The weekday 13:59-19:01 peak hour used to be a full blackout (idling
in place so systemd never saw the pause as a crash to restart). It's now a
THROTTLE instead — see peak_gate() below and arc.cfg [audio]
peak_throttle_minutes.

SOLE NARRATOR (merged 2026-08-27)
----------------------------------
scribe.py used to run its own independent audio pass once per ingest cycle
(_run_audio_pass et al., now removed — see the note above
synthesize_article_audio's definition in scribe.py). It never took
arc:audio:active — only a process-local threading.Lock — so it had zero
exclusion against this daemon. The two independently reimplemented "pick the
newest silent article" against the same feed and could (did, 2026-08-27
09:56-10:12: article dc73d5ad4b60…) land on the same article and run two
concurrent Kokoro subprocesses for it, each starving the other past
AUDIO_TIMEOUT_SECONDS. See ops/RUNBOOK.md 2026-08-27 for the incident.

scribe's old blackout-coverage argument for staying separate (it narrated
during the daemon's peak-hour idle) is now handled by the throttle above
instead of a second worker: one selector, one mutex holder, always.

Coordination with scribe.py is now one-directional: this daemon imports
scribe purely for synthesize_article_audio()/kokoro_preflight()/AUDIO_*
constants, and is the only caller of synthesize_article_audio() for site
arc. The arc:audio:active Redis mutex (SET NX EX, with stale-holder
detection — see acquire_mutex()) now only has to guard against two
instances of THIS daemon overlapping (e.g. mid systemd restart), not
cross-process contention with scribe.

Usage
-----
  python3 audio_backfill.py                 # run continuously (normal mode)
  python3 audio_backfill.py --once          # one narration attempt, then exit
  python3 audio_backfill.py --dry-run       # show the current window's top candidate, exit
  python3 audio_backfill.py --ignore-peak   # weekday emergency catch-up
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
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


# --- Logging: stdout, journald captures it under systemd ---------------------
# Runs as a systemd unit now (ops/systemd/audio-backfill.service), which
# redirects StandardOutput/StandardError to logs/audio_backfill.log — same
# convention as arc-watchdog.service. Plain stdout here either way; no file
# handler of its own, matching how this script has always deferred to
# whatever's supervising it rather than managing its own log file.
logger = logging.getLogger("audio_backfill")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                      "%H:%M:%S"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)


# --- Coordination primitives -------------------------------------------------
# Now the only cross-instance guard this daemon needs — scribe no longer
# competes for it (see module docstring, "SOLE NARRATOR"). Still worth
# getting right: a killed instance mid-synthesis is exactly how today's
# stale-mutex stall happened (2026-08-27 — a prior audio-backfill.service
# restart killed a process holding this mutex, and with no way to tell a
# dead holder from a live one, the new instance just waited out the full
# TTL). AUDIO_MUTEX_TTL is still the safety net for whatever the liveness
# check below can't resolve, but it should rarely be the thing that clears
# it now.
AUDIO_MUTEX_KEY = "arc:audio:active"
AUDIO_MUTEX_TTL = scribe.AUDIO_TIMEOUT_SECONDS + 60   # a stuck synth expires

# Atomic compare-and-delete: only clear the key if it still holds the value
# we expect. Used both to release our own lock (never delete a mutex some
# other holder has since taken — the old release_mutex() deleted
# unconditionally) and to clear a confirmed-dead holder's stale entry
# without racing another waiter doing the same thing at once.
_CAS_DELETE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""

# How often to poll when the mutex is held, the memory preflight is failing,
# or the window is empty. All three are "nothing to do right now, check back
# shortly" — there is no defer-budget/give-up timer any more (see module
# docstring): waiting has no "wrong target" risk once the candidate list is
# rebuilt fresh on every check.
POLL_SECONDS = 30

# --- Push-per-file sync (remote-synth mode) ----------------------------------
# When narration runs on a host that isn't the serving host (spectre, currently),
# every finished mp3 gets rsync'd to the serving host before audio_url is
# committed. `audio_url` on the article hash is a promise that the file is
# visible where Next.js serves it from — so the sync must complete before that
# promise is written. On the serving host itself (resolute today, single-host
# mode), leave ARC_AUDIO_SYNC_DEST unset and this code path is a no-op that
# returns True immediately. Section 6 of TODO.md carries the rationale
# (Option B1, push-per-file rsync — chosen over NFS to keep sync failures in
# their own failure domain and to surface them via a Redis counter).
#
# The destination is expected to sit behind a restricted ssh key using rrsync
# with -wo (write-only), chrooted to the audio directory: the client cannot
# read from, delete on, or rsync outside that one directory even if this key
# is exfiltrated. See TODO.md Section 6 "Push-per-file sync key" for the
# concrete authorized_keys line.
SYNC_DEST = os.environ.get("ARC_AUDIO_SYNC_DEST", "").strip()   # e.g. "arc-audio-sync@192.168.1.198:."
SYNC_SSH_KEY = os.environ.get("ARC_AUDIO_SYNC_SSH_KEY", "").strip()  # optional; passed via -i if set
SYNC_ATTEMPTS = 3                    # per-file attempts; 3 = ~14s worst-case (2s+4s backoff, plus timeouts)
SYNC_TIMEOUT_S = 30                  # rsync's own --timeout, per attempt
SYNC_OK_COUNTER = "arc:audio:sync_ok"
SYNC_FAIL_COUNTER = "arc:audio:sync_fail"


def push_to_destination(r: redis.Redis, article_id: str, local_path: str) -> bool:
    """Push one just-written mp3 to SYNC_DEST via rsync. True on success.

    Returns True immediately (no-op) when SYNC_DEST is unset — that's
    single-host mode on the serving host, and no push is meaningful. This is
    the shape that keeps the same audio_backfill.py running unchanged on
    resolute while the spectre-side unit runs it with the env vars set.

    Bounded retries (SYNC_ATTEMPTS), exponential backoff (2s, 4s, …) between
    attempts. Each attempt has its own rsync timeout. On final failure the
    caller does NOT commit audio_url; the article stays silent and enters
    the next find_newest_silent pass as a candidate again — wasteful (the
    synthesis is thrown away) but eventually convergent once the underlying
    sync issue is resolved.

    Every success increments SYNC_OK_COUNTER; every final failure increments
    SYNC_FAIL_COUNTER. That gives corpus_exporter a signal for a silently
    stopped syncer — the specific failure mode this counter exists for.
    """
    if not SYNC_DEST:
        return True

    ssh_bits = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "StrictHostKeyChecking=accept-new"]
    if SYNC_SSH_KEY:
        ssh_bits.extend(["-i", SYNC_SSH_KEY])
    ssh_e = " ".join(ssh_bits)

    for attempt in range(1, SYNC_ATTEMPTS + 1):
        try:
            proc = subprocess.run(
                ["rsync", "-a", "--partial", f"--timeout={SYNC_TIMEOUT_S}",
                 "-e", ssh_e, local_path, f"{SYNC_DEST}/"],
                capture_output=True, text=True,
                timeout=SYNC_TIMEOUT_S + 15)
            if proc.returncode == 0:
                r.incr(SYNC_OK_COUNTER)
                return True
            logger.warning(
                f"🔊 {article_id} rsync attempt {attempt}/{SYNC_ATTEMPTS} "
                f"rc={proc.returncode}: {(proc.stderr or '').strip()[:300]}")
        except subprocess.TimeoutExpired:
            logger.warning(
                f"🔊 {article_id} rsync attempt {attempt}/{SYNC_ATTEMPTS} "
                f"timed out after {SYNC_TIMEOUT_S + 15}s wall")
        except FileNotFoundError:
            # rsync binary not installed — no point retrying
            logger.error("🔊 rsync binary not on PATH; sync cannot proceed")
            break

        if attempt < SYNC_ATTEMPTS:
            time.sleep(2 ** attempt)

    r.incr(SYNC_FAIL_COUNTER)
    return False


def in_peak_window(cfg_audio: dict) -> bool:
    """True if now is inside the [start, end) peak-hour window.

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


def peak_gate(cfg_audio: dict, last_acquire_ts: float | None) -> tuple[bool, float]:
    """Whether a narration attempt may proceed right now, inside the peak
    window, and if not, how many seconds until it can.

    Replaces the old full idle-through (2026-08-27 — see module docstring):
    now that this daemon is the sole narrator, going fully silent for up to
    5 weekday hours isn't acceptable, but running at full sliding-window
    speed defeats the point of the window too. Throttle to roughly one
    acquire per peak_throttle_minutes instead — sized to match the cadence
    scribe's old per-cycle pass used to provide during this window (arc.cfg
    [audio]).

    The throttle interval is continuous across the window boundary, not
    reset by it: last_acquire_ts is whenever we last actually acquired,
    peak or not. A quiet stretch right before 14:00 means the first peak
    attempt fires immediately (last_acquire_ts is None or old); a busy one
    means it picks up the existing countdown rather than allowing an
    immediate second acquire right at the boundary. Only a cold start
    (last_acquire_ts is None — daemon just launched) always proceeds
    without waiting a full interval first.

    Callers outside the peak window shouldn't call this — in_peak_window()
    gates that.
    """
    throttle_s = float(cfg_audio.get("peak_throttle_minutes", 95)) * 60
    if last_acquire_ts is None:
        return True, 0.0
    remaining = throttle_s - (time.time() - last_acquire_ts)
    return remaining <= 0, max(remaining, 0.0)


def window_hours(cfg_audio: dict) -> float:
    """BACKFILL_WINDOW_HOURS, clamped floor..ceiling per arc.cfg [audio].

    A value can't be set so wide it turns this back into the batch backfill
    the redesign replaced, and can't be set so narrow it stops meaning
    anything.
    """
    hours = float(cfg_audio.get("backfill_window_hours", 2))
    floor = float(cfg_audio.get("backfill_window_floor_hours", 0.25))
    ceiling = float(cfg_audio.get("backfill_window_ceiling_hours", 6))
    return max(floor, min(ceiling, hours))


def max_chars_for_budget(cfg_audio: dict) -> int:
    """Longest body (chars) synthesis can plausibly finish within
    AUDIO_TIMEOUT_SECONDS, from arc.cfg [audio] estimated_synthesis_cps.

    Guards against a poison-pill article that can never finish in budget:
    dc73d5ad4b60 (2026-08-27) was 16,479 chars, needing ~1,100s of Kokoro
    time against a 600s AUDIO_TIMEOUT_SECONDS — it could never succeed, and
    with no length check it re-entered the candidate window on every daemon
    restart, burning a full 600s timeout each time before falling through
    to failed_this_run.

    The default (15 chars/s) is the OBSERVED rate, not a best case — 191
    historical narrations (audio_backfill_263*.log) ranged 11.0-16.9
    chars/s, median 15.1, mean 14.8. Using the median rather than the
    fastest-seen case means this doesn't reflexively skip articles that
    would actually have finished in time; a corpus check the same day found
    ~21% of articles over the resulting ~9,000-char threshold, and about
    14% of those already had audio from before this guard existed — so the
    estimate is deliberately not tightened further to catch every one of
    them. Meaningful enough of the corpus sits over the line that chunked
    synthesis (narrating in AUDIO_MAX_CHARS-sized pieces against a
    per-chunk budget, not one shot against the whole article) is worth
    considering later if that fraction matters more than skipping it does.
    """
    cps = float(cfg_audio.get("estimated_synthesis_cps", 15.0))
    return int(cps * scribe.AUDIO_TIMEOUT_SECONDS)


def find_newest_silent(r: redis.Redis, hours: float, skip: set,
                        max_chars: int) -> tuple[str, str] | None:
    """Newest silent article published within the last `hours`, or None.

    Rebuilt fresh from Redis on every call — this function body IS the
    trailing window, not a cache of one. `skip` is the process-local
    failed-this-run set (see main loop) so a synthesis failure doesn't get
    retried every single pass forever; a restart clears it. A candidate
    over `max_chars` (see max_chars_for_budget) is logged once and added to
    `skip` right here rather than being returned and later failing — its
    length won't change, so unlike a real synthesis failure this verdict is
    good for the rest of the run, no retry ever worth attempting.
    """
    cutoff = time.time() - hours * 3600
    ids = r.zrevrangebyscore('feed', '+inf', cutoff)
    if not ids:
        return None

    ids = [aid for aid in ids if aid not in skip]
    if not ids:
        return None

    pipe = r.pipeline()
    for aid in ids:
        pipe.hmget(f"article:{aid}",
                   ['audio_url', 'source_lang', 'original_text'])
    rows = pipe.execute()

    for aid, (audio_url, lang, body) in zip(ids, rows):
        if audio_url:
            continue
        if (lang or 'English') != 'English':
            continue
        body = (body or '').strip()
        if len(body) < scribe.AUDIO_MIN_CHARS:
            continue
        if len(body) > max_chars:
            logger.info(f"{aid} skipped — {len(body)} chars is over the "
                        f"{max_chars}-char budget for {scribe.AUDIO_TIMEOUT_SECONDS}s; "
                        f"never retried this run")
            skip.add(aid)
            continue
        return aid, body
    return None


def _holder_id() -> str:
    """This process's identity as stored in the mutex value: its PID.

    Single host, so a bare PID is enough to both log a meaningful holder
    and check liveness (_holder_is_alive below) — no hostname needed.
    """
    return str(os.getpid())


def _holder_is_alive(value: str) -> bool | None:
    """True/False if `value` names a live/dead PID, None if we can't tell.

    None covers anything unparseable (e.g. the pre-2026-08-27 literal
    "backfill", or a value from some future format change) — those are left
    alone rather than guessed at; AUDIO_MUTEX_TTL is what eventually clears
    them.
    """
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive, just not ours to signal
    except OSError:
        return None


def acquire_mutex(r: redis.Redis, cas_delete) -> tuple[bool, str | None]:
    """Try to take arc:audio:active.

    Returns (True, None) on success, or (False, holder) on failure — holder
    is the PID string seen holding it (for the caller's log line), or None
    if it changed hands between our failed SET and the follow-up GET.

    A holder we can prove is dead (_holder_is_alive → False) is cleared via
    an atomic compare-and-delete and retried immediately, rather than left
    to sit for the full AUDIO_MUTEX_TTL — that TTL-only wait is exactly
    what turned a killed instance into a ~7-minute stall for the next one
    on 2026-08-27. The CAS check (only delete if the value still matches
    what we just read) means a second waiter doing the same check at the
    same moment can't both "clear" it and double up the retry.
    """
    me = _holder_id()
    if r.set(AUDIO_MUTEX_KEY, me, nx=True, ex=AUDIO_MUTEX_TTL):
        return True, None

    current = r.get(AUDIO_MUTEX_KEY)
    if current is not None and _holder_is_alive(current) is False:
        if cas_delete(keys=[AUDIO_MUTEX_KEY], args=[current]):
            logger.warning(f"cleared stale mutex — holder pid {current} no longer exists")
            if r.set(AUDIO_MUTEX_KEY, me, nx=True, ex=AUDIO_MUTEX_TTL):
                return True, None
            current = r.get(AUDIO_MUTEX_KEY)
    return False, current


def release_mutex(r: redis.Redis, cas_delete) -> None:
    """Drop the mutex — but only if it's still ours.

    Compare-and-delete against our own holder id, not an unconditional
    DEL: if our TTL already lapsed and someone else has since acquired it,
    an unconditional delete would drop their lock instead of ours. Best-
    effort beyond that — the TTL is the safety net if this fails outright.
    """
    try:
        cas_delete(keys=[AUDIO_MUTEX_KEY], args=[_holder_id()])
    except Exception as e:
        logger.warning(f"could not release {AUDIO_MUTEX_KEY}: {e}")


def probe_duration_seconds(path: str) -> float | None:
    """ffprobe the finished mp3 for its container-reported duration.

    Nice-to-have for the log line — nothing critical rides on it, so a
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


def narrate_one(r: redis.Redis, article_id: str, body: str) -> bool:
    """Synthesize and store audio for one article. True on success."""
    started = time.perf_counter()
    audio_url = scribe.synthesize_article_audio(article_id, body)
    wall = time.perf_counter() - started

    if not audio_url:
        logger.warning(
            f"{article_id} — synthesis returned None after {wall:.1f}s")
        return False

    audio_path = os.path.join(
        os.path.dirname(_HERE), 'frontend', 'public',
        'uploads', 'audio', f"{article_id}.mp3")

    # Remote-synth mode: push to the serving host BEFORE committing
    # audio_url. audio_url promises the file is visible where Next.js
    # serves it; a hset that beats the sync is a broken promise. No-op on
    # the serving host itself (SYNC_DEST unset). See push_to_destination.
    if not push_to_destination(r, article_id, audio_path):
        logger.warning(
            f"{article_id} — synthesized OK but sync to {SYNC_DEST} failed "
            f"after {SYNC_ATTEMPTS} attempts; article stays silent, "
            f"will re-enter candidacy next pass")
        return False

    r.hset(f"article:{article_id}", 'audio_url', audio_url)

    dur = probe_duration_seconds(audio_path)
    if dur is None:
        logger.info(f"{article_id} ✓ {len(body)} chars → {audio_url} "
                    f"({wall:.1f}s wall, duration unknown)")
    else:
        cps = len(body) / dur if dur > 0 else 0
        flag = " ⚠ suspicious" if not (5 < cps < 40) else ""
        logger.info(f"{article_id} ✓ {len(body)} chars → {dur:.1f}s mp3 "
                    f"({cps:.1f} chars/s, {wall:.1f}s wall){flag}")
    return True


def run(once: bool, dry_run: bool, ignore_peak: bool) -> int:
    site = load_site_config()
    cfg_audio = site["audio"]

    r = redis.Redis(decode_responses=True,
                    password=os.environ['REDIS_PASSWORD'],
                    db=site.redis_db)
    # Boot-adjacent readiness gate — audio-backfill.service is
    # After=redis-server.service but starts at boot alongside redis-
    # server, so it can hit BusyLoadingError while the dataset loads.
    # register_script issues a Redis command (SCRIPT LOAD), so the gate
    # has to come before it. See redis_readiness.
    from redis_readiness import wait_for_redis
    wait_for_redis(r, log=logger)
    cas_delete = r.register_script(_CAS_DELETE_LUA)

    hours = window_hours(cfg_audio)
    max_chars = max_chars_for_budget(cfg_audio)
    logger.info(f"scanning {site.slug} — trailing {hours:.2f}h window, "
                f"{max_chars}-char synthesis budget")

    if dry_run:
        candidate = find_newest_silent(r, hours, set(), max_chars)
        if candidate:
            aid, body = candidate
            logger.info(f"would narrate: {aid} ({len(body)} chars)")
        else:
            logger.info("window is empty — nothing silent in range")
        return 0

    failed_this_run: set[str] = set()
    idle_logged = False
    peak_throttled_logged = False
    was_in_peak = False
    last_acquire_ts: float | None = None

    while True:
        in_peak = in_peak_window(cfg_audio) and not ignore_peak
        if in_peak and not was_in_peak:
            throttle_min = float(cfg_audio.get("peak_throttle_minutes", 95))
            logger.info(f"⏸  entering peak-hour window — throttling to "
                        f"~1 acquire / {throttle_min:.0f}m")
        elif was_in_peak and not in_peak:
            logger.info("▶  peak window ended — resuming full speed")
            peak_throttled_logged = False
        was_in_peak = in_peak

        if in_peak:
            proceed, remaining = peak_gate(cfg_audio, last_acquire_ts)
            if not proceed:
                if not peak_throttled_logged:
                    logger.info(f"⏸  peak-hour throttle — next attempt in {remaining / 60:.1f}m")
                    peak_throttled_logged = True
                time.sleep(min(POLL_SECONDS, max(remaining, 1.0)))
                continue
            peak_throttled_logged = False

        candidate = find_newest_silent(r, hours, failed_this_run, max_chars)
        if candidate is None:
            if not idle_logged:
                logger.info(f"idle — nothing silent in the last {hours:.2f}h; "
                            f"re-scanning every {POLL_SECONDS}s")
                idle_logged = True
            time.sleep(POLL_SECONDS)
            if once:
                return 0
            continue
        idle_logged = False
        article_id, body = candidate

        pf = scribe.kokoro_preflight()
        if pf is not None:
            reason, _level = pf
            logger.info(f"⏸  yielding {POLL_SECONDS}s — {reason}")
            time.sleep(POLL_SECONDS)
            continue

        acquired, holder = acquire_mutex(r, cas_delete)
        if not acquired:
            who = f"pid {holder}" if holder else "contention (holder changed mid-check)"
            logger.info(f"⏸  yielding {POLL_SECONDS}s — mutex held by {who}")
            time.sleep(POLL_SECONDS)
            continue

        last_acquire_ts = time.time()
        try:
            ok = narrate_one(r, article_id, body)
            if not ok:
                failed_this_run.add(article_id)
        finally:
            release_mutex(r, cas_delete)

        if once:
            return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--once", action="store_true",
                        help="One narration attempt (or idle check), then exit.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the current window's top candidate; don't call Kokoro.")
    parser.add_argument("--ignore-peak", action="store_true",
                        help="Do not honour the peak-hour blackout. "
                             "For emergencies only.")
    args = parser.parse_args()

    if args.ignore_peak:
        logger.warning("--ignore-peak set — peak-hour fence disabled for this run")

    return run(once=args.once, dry_run=args.dry_run, ignore_peak=args.ignore_peak)


if __name__ == "__main__":
    sys.exit(main())
