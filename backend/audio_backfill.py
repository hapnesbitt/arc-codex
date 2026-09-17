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
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

# --- Path setup: run from anywhere under the repo ---------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dotenv import load_dotenv                                                # noqa: E402
load_dotenv(os.path.join(_HERE, '.env'))

import redis                                                                  # noqa: E402
from site_config import load_site_config                                      # noqa: E402
from operational_state import enqueue_analysis                                # noqa: E402
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
# TTL — up to AUDIO_TIMEOUT_SECONDS + 60, i.e. eleven minutes).
#
# REDESIGNED (this pass): a bare-PID liveness check (os.kill(pid, 0)) is not
# fixable — it can only ever answer "is some process on THIS host running
# with that PID," which false-positives on ordinary PID recycling (observed
# twice against run-cupsd) and is flatly meaningless once the holder may be
# on a different host (see push_to_destination / remote-synth mode above).
# So there is no liveness check any more, on this host or any other: this is
# now a plain heartbeat lease. A short TTL (AUDIO_MUTEX_LEASE_TTL) is the
# ONLY staleness signal — "stale" means "expired," full stop, nothing to
# prove. A live holder keeps its lease alive by actively renewing it (see
# _lease_heartbeat below) for as long as it's actually working; a dead one
# just stops renewing and the key falls off on its own within one TTL.
AUDIO_MUTEX_KEY = "arc:audio:active"
AUDIO_MUTEX_LEASE_TTL = 45          # seconds — short on purpose, see above
_LEASE_REFRESH_INTERVAL = AUDIO_MUTEX_LEASE_TTL / 3   # renew well before expiry

# Heartbeat for mailer.py's check_narration_liveness (2026-09-11). Set to
# now() on every successful narration — output-arriving, not process-alive;
# a real 2026-09-11 incident had the daemon, this mutex, and the Redis
# tunnel all healthy for 4h45m of broadcast-script rejections producing
# nothing, which `systemctl` would never have caught. Plain epoch seconds,
# no TTL — mailer reads its AGE, same shape as scribe:last_cycle.
AUDIO_LAST_NARRATION_KEY = "arc:audio:last_narration"

# Bounded, durable retry record (2026-09-11) — closes the gap
# failed_this_run left open: that set is process-local, so a real failure
# (rejected script, synthesis timeout, sync failure) got exactly one
# lifetime attempt per daemon process (no automatic retry without a
# restart), while a restart wiped it entirely and gave every past failure
# an UNBOUNDED fresh attempt, forever, including ones that will never
# succeed. This persists the attempt count in Redis instead: bounded
# (AUDIO_RETRY_MAX_ATTEMPTS) regardless of how many restarts happen in
# between, and durable (a restart no longer means "forget everything").
#
# TTL is sized off backfill_window_ceiling_hours, not the live
# backfill_window_hours — the record must outlive the article's candidacy
# window no matter how that's tuned, and self-expire shortly after the
# article could never be a candidate again (no manual cleanup).
AUDIO_RETRY_ATTEMPTS_KEY_PREFIX = "arc:audio:attempts:"
AUDIO_RETRY_MAX_ATTEMPTS = 3


def _retry_key(article_id: str) -> str:
    return f"{AUDIO_RETRY_ATTEMPTS_KEY_PREFIX}{article_id}"


def retry_attempts(r: redis.Redis, article_id: str) -> int:
    """Attempts recorded so far for this article, 0 if none."""
    raw = r.get(_retry_key(article_id))
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def record_narration_failure(r: redis.Redis, cfg_audio: dict, article_id: str, reason: str) -> int:
    """Increment the durable attempt counter for a failure, TTL it on
    first creation, and log distinctly — once — the moment it crosses
    AUDIO_RETRY_MAX_ATTEMPTS. Returns the new attempt count.

    Callers (narrate_one's one call site) are expected to call this ONLY
    for countable failures — see narrate_one's own docstring for the
    countable/not-countable split (2026-09-12). This function itself
    doesn't gate on that; it trusts the caller, same as it trusted the
    caller to only call it on real failures before this distinction
    existed.

    Distinct from the poison-pill log line on purpose: poison-pill is
    "known unwinnable on sight" (over the char budget, never attempted);
    this is "tried AUDIO_RETRY_MAX_ATTEMPTS real times and failed every
    time" — a permanently-failing article should be findable later by
    what actually happened to it, not folded into the same message as an
    article that was never attempted at all.
    """
    key = _retry_key(article_id)
    attempts = r.incr(key)
    if attempts == 1:
        ceiling_hours = float(cfg_audio.get("backfill_window_ceiling_hours", 6))
        r.expire(key, int(ceiling_hours * 3600) + 3600)  # +1h margin past the ceiling
    if attempts == AUDIO_RETRY_MAX_ATTEMPTS:
        logger.warning(
            f"🛑 {article_id} — retry budget exhausted after {attempts} attempts, "
            f"last failure: {reason}; permanently silent — will not be "
            f"retried again while it remains in the candidate window")
    return attempts

# Atomic compare-and-delete: only clear the key if it still holds the value
# we expect. Used to release our own lock — never delete a mutex some other
# holder has since taken (the old release_mutex() deleted unconditionally).
_CAS_DELETE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""

# Atomic compare-and-refresh: only extend the TTL if the key still holds the
# value we expect — a heartbeat that's late enough to run after our lease
# already expired and was picked up by someone else must not resurrect it
# out from under them.
_CAS_REFRESH_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
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

# Silent-loss visibility (2026-09-16). Prior 24h observations of ~65 articles
# aging out of the audio window unanalyzed with zero log lines and zero
# retry counters (see TODO.md §2026-09-13 "silent data loss") happened
# because there was no counter for the pass-over case in find_newest_silent.
# The metric here surfaces the same loss automatically regardless of what
# cycle_minutes happens to be that week: any time arrivals-of-unanalyzable
# exceed analyzer drain within the window, the counter ticks and one log
# line fires per aged-out article. That's the drift a hand-tuned knob makes
# invisible without a metric.
NOTED_UNANALYZED_SET = "arc:audio:noted_unanalyzed_ids"
AGED_OUT_UNANALYZED_COUNTER = "arc:stats:aged_out_unanalyzed"


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

    estimated_synthesis_cps is WALL-CLOCK chars/s, not the audio (speech)
    rate — those are different numbers. Pre-spectre (through 2026-09-03)
    the value was 15, derived from historical logs where Kokoro on
    resolute was slow enough for wall and speech rates to coincide, and
    the name masked the ambiguity. On spectre they diverge: 23
    successful narrations 2026-09-03 morning ranged 12.5-32.9 chars/s
    wall (median 23.7) while the audio rate was still ~15, so the old
    9,000-char threshold was refusing about half of every pass on
    articles synthesis could easily finish. The 18.34 default now
    (~11,000-char budget) is a conservative bump that clears the
    2026-09-03 near-misses without going to the median-derived ~14,200.
    See arc.cfg [audio] for the full rationale.

    The structural fix is per-chunk (not per-article) timeout — Kokoro
    already splits and synthesizes sequentially, so a 600s cap per chunk
    removes the length ceiling entirely. That's what to reach for next
    if long articles keep hitting this guard.

    KNOWN COST of the 11004 budget, observed 2026-09-03 first pass after
    the raise: an article at 9940 chars ran the full 600.4s and got
    killed on AUDIO_TIMEOUT_SECONDS (656c30ce3e35...). Its wall rate was
    ≤ 16.56 chars/s — below the low tail of the 8 successful completions
    in the same pass (min 16.72, median 22.36). So articles in the
    9000-11004-char band at wall rates below ~16.5 will burn the full
    600s before returning None from synthesize_article_audio; the next
    pass then re-picks them and burns it again on every restart. This
    is the exact failure the poison-pill guard was designed to prevent,
    reintroduced in a narrower band as the deliberate cost of catching
    articles that would otherwise stay silent. Accepted trade for now
    (one 600s burn per ~5-8 recovered articles); Step 2 (per-chunk
    timeout, see TODO.md Section 6 Phase 2) is what removes it properly.
    """
    cps = float(cfg_audio.get("estimated_synthesis_cps", 18.34))
    return int(cps * scribe.AUDIO_TIMEOUT_SECONDS)


_ANALYSIS_FIELDS = ('red_team_analysis', 'blue_team_analysis', 'purple_team_analysis')


def _is_analyzed(red: str | None, blue: str | None, purple: str | None) -> bool:
    return len(red or '') > 10 and len(blue or '') > 10 and len(purple or '') > 10


def _ensure_analysis_queued(r: redis.Redis, article_id: str) -> None:
    """Eager, non-blocking enqueue for a narration candidate that isn't
    analyzed yet (2026-09-06). Reuses the exact dedup key main.py's two
    producers already share (SET NX EX 21600) so this can never
    double-enqueue against a concurrent view or ingest-time dispatch.

    Deliberately does not wait: pushes and returns immediately. This
    candidate is skipped THIS pass (see find_newest_silent) and picked up
    again on a future pass once analysis has landed — analyzer.py is a
    single-consumer, minutes-scale worker, and blocking this daemon's loop
    on it would stall every other candidate behind this one.

    'left' (head of queue), matching the view-handler's priority — a
    narration-bound article is a live consumer waiting on this the same
    way a reader is, not backlog the way ingest-time dispatch's 'right'
    push is.
    """
    try:
        if r.set(f"analyzer:queued:{article_id}", '1', ex=21600, nx=True):
            enqueue_analysis(r, article_id, 'left')
            logger.info(f"📋 {article_id} — queued for analysis (narration is waiting on it)")
    except Exception as e:
        # Same non-fatal handling as main.py's ingest-time dispatch: a
        # queueing error here must not take down the narration daemon.
        logger.warning(f"⚠️  Analysis dispatch failed for {article_id}: {e}")


def _tally_aged_out_unanalyzed(r: redis.Redis, cutoff: float, hours: float) -> None:
    """Detect articles that were noted as unanalyzed while inside the audio
    window but have since aged out without ever being analyzed. Increment
    arc:stats:aged_out_unanalyzed and log once per article.

    The point of separating "note" from "count" is idempotency: an article
    is added to NOTED_UNANALYZED_SET on first observation, and only counted
    once at the transition where its feed_ts falls below the window cutoff.
    A busy poll cycle would otherwise increment the same article's tally
    on every pass, drowning the signal.

    Buckets at age-out time:
      - has audio → success; drop silently
      - deleted (feed ZSCORE None) → retention swept it; drop silently
      - still in window (feed_ts >= cutoff) → keep watching
      - aged out, analyzed but unnarrated → different failure mode (Kokoro
        timeouts, sync failures) — drop without counting; those have their
        own counters
      - aged out AND unanalyzed → increment + one WARN log line + drop
    """
    try:
        noted = r.smembers(NOTED_UNANALYZED_SET)
    except Exception as e:
        logger.debug(f"tally_aged_out: SMEMBERS failed: {e}")
        return
    if not noted:
        return
    noted_list = list(noted)
    pipe = r.pipeline()
    for aid in noted_list:
        pipe.zscore('feed', aid)
        pipe.hmget(f"article:{aid}", ['audio_url', *_ANALYSIS_FIELDS])
    results = pipe.execute()
    for i, aid in enumerate(noted_list):
        feed_score = results[i * 2]
        audio_url, red, blue, purple = results[i * 2 + 1]
        if audio_url:
            r.srem(NOTED_UNANALYZED_SET, aid)
            continue
        if feed_score is None:
            r.srem(NOTED_UNANALYZED_SET, aid)
            continue
        if feed_score >= cutoff:
            continue
        if _is_analyzed(red, blue, purple):
            r.srem(NOTED_UNANALYZED_SET, aid)
            continue
        r.incr(AGED_OUT_UNANALYZED_COUNTER)
        logger.warning(
            f"📉 {aid} aged out of {hours}h window UNANALYZED "
            f"— analyzer drain < arrival rate; counter arc:stats:aged_out_unanalyzed"
        )
        r.srem(NOTED_UNANALYZED_SET, aid)


def find_newest_silent(r: redis.Redis, hours: float, skip: set,
                        max_chars: int) -> tuple[str, str, str, str, str] | None:
    """Newest silent, analyzed article published within the last `hours`,
    or None. Returns (article_id, body, red, blue, purple) — body is still
    the candidacy gate (is there enough real source content here at all),
    but the caller narrates from red/blue/purple via
    scribe.run_broadcast_script(), never from body directly.

    Rebuilt fresh from Redis on every call — this function body IS the
    trailing window, not a cache of one. `skip` is the process-local
    failed-this-run set (see main loop); a restart clears it, but that no
    longer means "forget everything" — retry_attempts() below independently
    checks the durable Redis counter (record_narration_failure), so a
    candidate that has already exhausted AUDIO_RETRY_MAX_ATTEMPTS across any
    number of restarts stays skipped regardless of what's in the in-memory
    set this process happens to have. A candidate over `max_chars` (see
    max_chars_for_budget) is logged once and added to `skip` right here
    rather than being returned and later failing — its length won't change,
    so unlike a real synthesis failure this verdict is good for the rest of
    the run, no retry ever worth attempting.

    An unanalyzed candidate is NOT added to `skip` — it's eager-enqueued
    (if not already) and passed over for this pass only; a future pass
    picks it up once analysis lands, same as any other article that just
    hasn't reached the front of the window's attention yet.
    """
    cutoff = time.time() - hours * 3600
    _tally_aged_out_unanalyzed(r, cutoff, hours)
    ids = r.zrevrangebyscore('feed', '+inf', cutoff)
    if not ids:
        return None

    ids = [aid for aid in ids if aid not in skip]
    if not ids:
        return None

    pipe = r.pipeline()
    for aid in ids:
        pipe.hmget(f"article:{aid}",
                   ['audio_url', 'source_lang', 'original_text', *_ANALYSIS_FIELDS])
    rows = pipe.execute()

    for aid, (audio_url, lang, body, red, blue, purple) in zip(ids, rows):
        if audio_url:
            continue
        if (lang or 'English') != 'English':
            continue
        body = (body or '').strip()
        if len(body) < scribe.SOURCE_MIN_CHARS:
            continue
        # Source-length upper bound removed 2026-09-12. It was
        # estimated_synthesis_cps × AUDIO_TIMEOUT_SECONDS (18.34 × 600
        # = 11004 chars), sized to keep synthesis of RAW ARTICLE TEXT
        # under the Kokoro timeout — but nothing narrates source text
        # any more. narrate_one calls scribe.run_broadcast_script() and
        # feeds the resulting ~1700-char script to synthesize_article_
        # audio; the script's length is bounded by BROADCAST_NUM_PREDICT
        # (300 tokens) at generation time, and does not scale with the
        # source article. A 110,000-char article produces the same
        # ~1700-char script as a 13,000-char one, so a source-length
        # gate here filters candidates it has no business filtering.
        # max_chars is kept in the signature until the caller stops
        # computing it (see max_chars_for_budget), but it is no longer
        # consulted.
        if retry_attempts(r, aid) >= AUDIO_RETRY_MAX_ATTEMPTS:
            # Exhaustion itself was already logged once, distinctly, by
            # record_narration_failure() at the moment it happened — this
            # is silent on purpose so a long-lived process doesn't repeat
            # the same warning every 30s poll for as long as the article
            # remains in the window.
            skip.add(aid)
            continue
        if not _is_analyzed(red, blue, purple):
            _ensure_analysis_queued(r, aid)
            # Idempotent mark for the silent-loss detector; _tally_aged_out_
            # unanalyzed reads this set at the top of every pass and counts
            # the age-out transition. SADD is idempotent — safe to call on
            # every poll while an article remains unanalyzed in the window.
            try:
                r.sadd(NOTED_UNANALYZED_SET, aid)
            except Exception as e:
                logger.debug(f"note_unanalyzed: SADD failed for {aid}: {e}")
            continue
        return aid, body, red or '', blue or '', purple or ''
    return None


def _holder_id() -> str:
    """A fresh, effectively-unique identity for one lease acquisition.

    No longer a bare PID — the lease is validated purely by TTL expiry now
    (see the "Coordination primitives" note above), so this value is never
    interpreted, only ever compared for exact equality (CAS ownership
    checks) or printed in a log line. The PID prefix is kept as a debugging
    aid only; the random suffix is what actually makes each acquisition's
    token unique, including across hosts, so two different processes can
    never be mistaken for the same lease holder.
    """
    return f"{os.getpid()}:{uuid.uuid4().hex[:8]}"


def acquire_mutex(r: redis.Redis) -> tuple[bool, str | None]:
    """Try to take arc:audio:active.

    Returns (True, my_token) on success — the caller must hold onto that
    token and pass it to _lease_heartbeat/release_mutex, not recompute it —
    or (False, holder) on failure, where holder is the token seen holding
    it (for the caller's log line), or None if it changed hands between our
    failed SET and the follow-up GET.

    No liveness check, no stale-clear branch: a short AUDIO_MUTEX_LEASE_TTL
    is the only staleness signal now. If the holder is real and working,
    _lease_heartbeat keeps it renewed; if not, it simply expires and the
    next poll (at most one POLL_SECONDS + AUDIO_MUTEX_LEASE_TTL later)
    succeeds on its own — no proactive clearing needed.
    """
    me = _holder_id()
    if r.set(AUDIO_MUTEX_KEY, me, nx=True, ex=AUDIO_MUTEX_LEASE_TTL):
        return True, me
    return False, r.get(AUDIO_MUTEX_KEY)


@contextmanager
def _lease_heartbeat(r: redis.Redis, cas_refresh, token: str):
    """Keep `token`'s lease alive for as long as the `with` body runs.

    Renews AUDIO_MUTEX_KEY's TTL every _LEASE_REFRESH_INTERVAL seconds via a
    CAS-guarded PEXPIRE (only refreshes while the key still holds `token` —
    a late heartbeat can never resurrect a lease that already expired and
    was picked up by someone else).

    The renew loop runs on a daemon thread, so it cannot outlive the
    process: a SIGKILL or an unhandled SIGTERM ends the whole process,
    thread included, in the same instant — there is no separate cleanup
    step for the thread to skip in that case, because there's no process
    left to skip it in. What this context manager guarantees is narrower
    and is the part that's actually ours to guarantee: the thread never
    outlives the *lease hold* while the process keeps running. The `finally`
    below always fires — on a normal return from the body, and on an
    exception raised inside it (e.g. narrate_one blowing up mid-synthesis)
    — stopping and joining the thread before this function returns, so the
    caller's own release_mutex() never races a heartbeat that's still in
    flight.
    """
    stop = threading.Event()

    def _run() -> None:
        while not stop.wait(_LEASE_REFRESH_INTERVAL):
            try:
                cas_refresh(keys=[AUDIO_MUTEX_KEY],
                            args=[token, AUDIO_MUTEX_LEASE_TTL * 1000])
            except Exception as e:
                logger.warning(f"lease refresh failed for {token}: {e}")

    t = threading.Thread(target=_run, daemon=True, name="audio-mutex-heartbeat")
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=5)


def release_mutex(r: redis.Redis, cas_delete, token: str) -> None:
    """Drop the mutex — but only if it still holds `token`.

    Compare-and-delete against the token this hold actually acquired, not
    an unconditional DEL: if our lease already lapsed and someone else has
    since acquired it, an unconditional delete would drop their lock
    instead of ours. Best-effort beyond that — the lease TTL is the safety
    net if this fails outright.
    """
    try:
        cas_delete(keys=[AUDIO_MUTEX_KEY], args=[token])
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


def narrate_one(r: redis.Redis, article_id: str, red: str, blue: str, purple: str) -> tuple[bool, str | None, bool]:
    """Write a broadcast script from this article's analysis, then
    synthesize and store audio from THAT — never from the source text.

    Returns (ok, reason, countable):
      ok        — True on success.
      reason    — short human-readable failure reason, or None on success.
      countable — meaningless when ok is True; when ok is False, whether
                  this failure says something about THIS article and
                  should count against its retry budget (see
                  record_narration_failure). False means infrastructure —
                  the model host was unreachable or answered with nothing
                  usable, the synthesis tool crashed/timed out, or the
                  push to the serving host failed. Only content-level
                  outcomes are True: the model answered, the answer
                  arrived, and it was unusable for a reason specific to
                  this article (over BROADCAST_MAX_CHARS, or the written
                  script too short to narrate). 2026-09-12: added after a
                  ~10h spectre firewall gap made every attempt fail with a
                  ConnectTimeout that looked, in the log and in the retry
                  counter, identical to an ordinary content rejection —
                  burning through an article's attempts for a reason that
                  taught us nothing about the article.

    The caller (find_newest_silent) has already confirmed red/blue/purple
    are all present.
    """
    started = time.perf_counter()

    try:
        script = scribe.run_broadcast_script(article_id, red, blue, purple)
    except scribe.OllamaTransportError as e:
        reason = f"broadcast script host unreachable: {e}"
        logger.warning(f"{article_id} — 📡 UNREACHABLE — {reason} — "
                       f"infrastructure, not counted against retry budget")
        return False, reason, False
    except scribe.OllamaNoResponseError as e:
        reason = f"broadcast script host gave no usable response: {e}"
        logger.warning(f"{article_id} — 🔇 NO-RESPONSE — {reason} — "
                       f"infrastructure, not counted against retry budget")
        return False, reason, False

    if not script:
        reason = "no broadcast script"
        logger.warning(f"{article_id} — no broadcast script; narration skipped this pass")
        return False, reason, True

    try:
        audio_url = scribe.synthesize_article_audio(article_id, script)
    except scribe.AudioToolError as e:
        reason = f"synthesis tool failure: {e}"
        logger.warning(f"{article_id} — 🔧 TOOL-FAILURE — {reason} — "
                       f"infrastructure, not counted against retry budget")
        return False, reason, False
    wall = time.perf_counter() - started

    if not audio_url:
        reason = f"synthesis returned None after {wall:.1f}s"
        logger.warning(f"{article_id} — {reason}")
        return False, reason, True

    audio_path = os.path.join(
        os.path.dirname(_HERE), 'frontend', 'public',
        'uploads', 'audio', f"{article_id}.mp3")

    # Remote-synth mode: push to the serving host BEFORE committing
    # audio_url. audio_url promises the file is visible where Next.js
    # serves it; a hset that beats the sync is a broken promise. No-op on
    # the serving host itself (SYNC_DEST unset). See push_to_destination.
    # Every failure shape here is the network path or the destination
    # host — rsync has no concept of "this article's content," so this is
    # unconditionally infrastructure, never counted.
    if not push_to_destination(r, article_id, audio_path):
        reason = f"synthesized OK but sync to {SYNC_DEST} failed after {SYNC_ATTEMPTS} attempts"
        logger.warning(
            f"{article_id} — 🚚 SYNC-FAILURE — {reason}; article stays silent, "
            f"will re-enter candidacy next pass — infrastructure, not "
            f"counted against retry budget")
        return False, reason, False

    r.hset(f"article:{article_id}", 'audio_url', audio_url)
    r.set(AUDIO_LAST_NARRATION_KEY, int(time.time()))

    dur = probe_duration_seconds(audio_path)
    if dur is None:
        logger.info(f"{article_id} ✓ {len(script)} script chars → {audio_url} "
                    f"({wall:.1f}s wall, duration unknown)")
    else:
        cps = len(script) / dur if dur > 0 else 0
        flag = " ⚠ suspicious" if not (5 < cps < 40) else ""
        logger.info(f"{article_id} ✓ {len(script)} script chars → {dur:.1f}s mp3 "
                    f"({cps:.1f} chars/s, {wall:.1f}s wall){flag}")
    return True, None, True


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
    cas_refresh = r.register_script(_CAS_REFRESH_LUA)

    hours = window_hours(cfg_audio)
    max_chars = max_chars_for_budget(cfg_audio)
    logger.info(f"scanning {site.slug} — trailing {hours:.2f}h window, "
                f"{max_chars}-char synthesis budget")

    if dry_run:
        candidate = find_newest_silent(r, hours, set(), max_chars)
        if candidate:
            aid, body, red, blue, purple = candidate
            logger.info(f"would narrate: {aid} ({len(body)} source chars, analyzed)")
        else:
            logger.info("window is empty — nothing silent+analyzed in range")
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
        article_id, body, red, blue, purple = candidate

        pf = scribe.kokoro_preflight()
        if pf is not None:
            reason, _level = pf
            logger.info(f"⏸  yielding {POLL_SECONDS}s — {reason}")
            time.sleep(POLL_SECONDS)
            continue

        acquired, token = acquire_mutex(r)
        if not acquired:
            who = f"holder {token}" if token else "contention (holder changed mid-check)"
            logger.info(f"⏸  yielding {POLL_SECONDS}s — mutex held by {who}")
            time.sleep(POLL_SECONDS)
            continue

        last_acquire_ts = time.time()
        try:
            with _lease_heartbeat(r, cas_refresh, token):
                ok, reason, countable = narrate_one(r, article_id, red, blue, purple)
                if not ok:
                    # failed_this_run always gets it, regardless of
                    # countable — still don't hot-loop the same candidate
                    # every 30s within this process's life, infrastructure
                    # failure or not. Only the DURABLE Redis counter (and
                    # therefore whether this article can ever be
                    # permanently exhausted) is gated on countable.
                    failed_this_run.add(article_id)
                    if countable:
                        record_narration_failure(r, cfg_audio, article_id, reason)
        finally:
            release_mutex(r, cas_delete, token)

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
