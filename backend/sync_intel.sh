#!/bin/bash
# Arc Codex - Autonomous Intelligence Sync

APP_DIR="/home/www/arc_stack/backend"
LOG_FILE="/home/www/arc_stack/logs/sync_intel.log"

# Ensure we are in the right directory for imports to work
cd "$APP_DIR"

# Activate Venv
source venv/bin/activate

# --- Line-level timestamps ---
# Before 2026-08-27 the wrapper timestamped only its outer STARTING/COMPLETE
# boundaries; every print() inside kasmir7 (connect_redis, generate_*) and
# every "Redis is loading" error from a boot-adjacent cron fire landed in
# the log undated. arc.sh cmd_checkup's time gate then had no way to age
# those lines out — they slipped past its awk regex, and older ones like
# 5-month-old ModuleNotFoundError tracebacks got silently excluded once
# the checkup grew the gate. Prefix every line with the same YYYY-MM-DD
# HH:MM:SS format cmd_checkup's time gate already recognises.
_ts() { while IFS= read -r line; do printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$line"; done; }

{
    echo "--- STARTING HOURLY BROADCAST ---"
    # -u so kasmir7's print() calls aren't buffered when piped into _ts —
    # a buffered flush at the end would collapse all interior lines onto
    # a single per-second timestamp.
    python3 -u - <<'PY'
import os, sys, time
from dotenv import load_dotenv
# Explicit path, not the default frame-walking find_dotenv(): a heredoc-fed
# `python3 -u -` runs as __main__ with `<stdin>` as its file, and dotenv's
# find_dotenv asserts on frame.f_back being non-None — the wrapper cd's
# to backend/ before invoking python, so ".env" is the same file kasmir7
# picks up when it later re-loads on import.
load_dotenv(".env")
import redis
from redis.exceptions import BusyLoadingError, ConnectionError as RedisConnErr

# --- Redis readiness gate ---
# sync_intel runs from cron ("0 * * * *"), not systemd, so it has no
# After=redis-server.service ordering. When a boot lands within seconds
# of a top-of-hour, this fires while Redis is still loading its dataset
# from disk; every command returns BusyLoadingError "Redis is loading
# the dataset in memory". systemd's After= wouldn't be enough on its own
# either: redis-server.service reports "started" the moment the process
# forks, before the dataset load finishes — the load window is invisible
# to systemd ordering, so any consumer that connects to Redis at boot
# needs a readiness retry, not just After=. Do the retry here rather
# than in kasmir7.connect_redis so the fix stays scoped to the cron path
# (kasmir7's connect_redis is also imported by the interactive TUI where
# a fast-fail is preferable).
_r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD") or None,
    db=int(os.getenv("REDIS_DB", 0)),
    decode_responses=True,
    socket_connect_timeout=5,
)
_deadline = time.monotonic() + 60
while True:
    try:
        _r.ping()
        break
    except (BusyLoadingError, RedisConnErr) as e:
        if time.monotonic() >= _deadline:
            print(f"[!] Redis not ready after 60s ({e}); skipping cycle", flush=True)
            sys.exit(2)
        time.sleep(2)

import kasmir7
from termcolor import colored
r = kasmir7.connect_redis()
kasmir7.generate_sitemap(r)
kasmir7.generate_rss(r)
kasmir7.generate_news_sitemap(r)
PY
    echo "--- BROADCAST COMPLETE ---"
} 2>&1 | _ts >> "$LOG_FILE"
