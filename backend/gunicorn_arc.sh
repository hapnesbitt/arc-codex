#!/bin/bash
source /home/www/arc_stack/backend/venv/bin/activate

# BEST PRACTICES CONFIG:
# --timeout 600: Industry standard for heavy data (safe & reliable).
# --worker-class gthread: Lets 1 worker handle multiple requests simultaneously.

# [gunicorn] read from arc.cfg — same grep -oP pattern arc.sh already uses for
# log_days/log_max_mb/include_scraped_images, so there is exactly one place
# left to read these three from and it is the cfg, not this script. Before
# this (2026-08-21 gunicorn sizing audit), workers/threads/timeout were
# hardcoded here and arc.cfg's [gunicorn] section was parsed by
# site_config.py and never read back by anything — editing the cfg did
# nothing. Fallback defaults below match what was hardcoded previously, so a
# missing/unparseable cfg fails safe into the old behavior rather than
# refusing to start.
CFG="/home/www/arc_stack/arc.cfg"
WORKERS="$(grep -oP '^workers\s*=\s*\K[0-9]+' "$CFG" 2>/dev/null)"
THREADS="$(grep -oP '^threads\s*=\s*\K[0-9]+' "$CFG" 2>/dev/null)"
TIMEOUT="$(grep -oP '^timeout\s*=\s*\K[0-9]+' "$CFG" 2>/dev/null)"
WORKERS="${WORKERS:-20}"
THREADS="${THREADS:-8}"
TIMEOUT="${TIMEOUT:-600}"

exec gunicorn \
    --bind 127.0.0.1:5005 \
    --workers "$WORKERS" \
    --threads "$THREADS" \
    --worker-class gthread \
    --timeout "$TIMEOUT" \
    --preload \
    --access-logfile /home/www/arc_stack/logs/gunicorn_access.log \
    --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s' \
    --error-logfile /home/www/arc_stack/logs/gunicorn_error.log \
    main:app
