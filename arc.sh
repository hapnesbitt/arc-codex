#!/bin/bash
# arc.sh - Arc Codex / A.R.C. Stack Manager
# Updated: Mar 2026
#   - Dual backup: fast SSD (code only, keep 5) + cold archive big drive (full, keep 30)
#   - Build: removed rm -rf .next, use --clean flag only when needed
#   - Gunicorn start_service sleep bumped to 5s
#   - Mailer added to watchdog service list (was missing)
#   - Frontend now managed as Docker container (arc-frontend)
#   - Fixed: Solr core arc_codex → feeds in backup-cold
#   - Fixed: Redis BGSAVE now uses password from env
#   - 2026-07-15: LinkedIn auto-poster retired (account closed)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
ITC_ROOT="/home/www/arc_stack"
FRONTEND_DIR="$ITC_ROOT/frontend"
BACKEND_DIR="$ITC_ROOT/backend"
VENV="$BACKEND_DIR/venv/bin/activate"
LOG_DIR="$ITC_ROOT/logs"
PID_DIR="$ITC_ROOT/pids"

# SSD — fast, lightweight, keep 5. Same drive as stack.
# Not a disaster-recovery backup — just a quick rollback point.
BACKUP_DIR="$ITC_ROOT/backups"
BACKUP_KEEP=5

# Big drive — full cold archive. Disaster recovery.
# Dedicated subdir: automated retention must never share a namespace with
# the manual must-never-delete artifacts (July RDB snapshots, library.db)
# that live loose in /mnt/arcdata.
# Retention math (2026-07-11): archive ≈ stack ~5GB (uploads are JPEG/WebP,
# barely compress) + Redis RDB + Solr 26MB + library.db 13.7GB→~7GB gz
# ≈ 12-14GB each. KEEP=4 → ~48-56GB of the mount's ~197GB free (~28%).
# Old value /mnt/data/www/... was root-owned+unwritable — cold backup had
# NEVER once produced an archive (register R4).
COLD_BACKUP_DIR="/mnt/arcdata/backups"
COLD_BACKUP_KEEP=4

# Log retention/rotation thresholds — single source of truth is the site cfg
# ([backup].log_days / log_max_mb). logrotate.conf mirrors log_days in its
# `rotate` count; keep the two in step when either changes.
LOG_MAX_DAYS="$(grep -oP '^log_days\s*=\s*\K[0-9]+' "$ITC_ROOT/arc.cfg" 2>/dev/null)"
LOG_MAX_DAYS="${LOG_MAX_DAYS:-9}"
LOG_MAX_SIZE_MB="$(grep -oP '^log_max_mb\s*=\s*\K[0-9]+' "$ITC_ROOT/arc.cfg" 2>/dev/null)"
LOG_MAX_SIZE_MB="${LOG_MAX_SIZE_MB:-50}"

# Docker
COMPOSE_FILE="$ITC_ROOT/docker-compose.yml"
GRAFANA_COMPOSE_FILE="$ITC_ROOT/docker-compose.grafana.yml"
# Redis password — used for the cold-backup RDB capture. Read the
# REDIS_PASSWORD= line directly: the old REDIS_URL regex extracted "//"
# from the scheme, so every authenticated redis-cli call in this script
# had been failing silently (register R4 forensics, 2026-07-11).
REDIS_PASSWORD="${REDIS_PASSWORD:-$(grep -oP '^REDIS_PASSWORD=\K.*' "$BACKEND_DIR/.env" 2>/dev/null)}"

SERVICES=(
    "gunicorn|$BACKEND_DIR|./gunicorn_arc.sh|true|5005"
    "scribe|$BACKEND_DIR|python3 scribe.py|true|"
    "manual_publisher|$BACKEND_DIR|python3 manual_publisher.py|true|"
    "stream_consumer|$BACKEND_DIR|python3 stream_consumer.py|true|"
    "analyzer|$BACKEND_DIR|python3 analyzer.py|true|"
    "mailer|$BACKEND_DIR|python3 mailer.py|true|"
    "bluesky_poster|$BACKEND_DIR|python3 bluesky_poster.py|true|"
    "mastodon_poster|$BACKEND_DIR|python3 mastodon_poster.py|true|"
    "facebook_poster|$BACKEND_DIR|python3 facebook_poster.py|true|"
    "character_builder|$BACKEND_DIR|python3 character_builder.py|true|"
    "quiz_generator|$BACKEND_DIR|python3 quiz_generator.py|true|"
    "frontend|$ITC_ROOT|docker|false|3000"   # docker sentinel — managed via docker compose
    "corpus_exporter|$BACKEND_DIR|python3 corpus_exporter.py|true|9101"
    "caddy_exporter|$BACKEND_DIR|python3 caddy_exporter.py|true|9102"
)

export PATH="/home/ross/.nvm/versions/node/v22.16.0/bin:$PATH"

# ==============================================================================
# HELPERS
# ==============================================================================
mkdir -p "$LOG_DIR" "$PID_DIR" "$BACKUP_DIR"
mkdir -p "$COLD_BACKUP_DIR" 2>/dev/null || true

is_running() {
    local name="$1"
    # Docker-managed frontend
    if [ "$name" = "frontend" ]; then
        docker ps --filter "name=arc-frontend" --filter "status=running" -q 2>/dev/null | grep -q .
        return
    fi
    local pidfile="$PID_DIR/$name.pid"
    [ -f "$pidfile" ] || return 1
    local pid svc dir cmd port proc_cwd proc_cmd proc_pgid
    pid=$(cat "$pidfile" 2>/dev/null)
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    svc=$(get_service_def "$name") || return 1
    IFS='|' read -r _ dir cmd _ port <<< "$svc"
    proc_cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null)
    [ "$proc_cwd" = "$dir" ] || return 1
    proc_cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    if [ "$name" = "gunicorn" ]; then
        proc_pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
        [ "$pid" = "$proc_pgid" ] &&
            [[ "$proc_cmd" == *gunicorn* ]] &&
            [[ "$proc_cmd" == *"--bind 127.0.0.1:$port"* ]]
    else
        [[ "$proc_cmd" == *"$cmd"* ]]
    fi
}

free_port() {
    local name="$1" dir="$2" cmd="$3" port="$4"
    [ -z "$port" ] && return 0
    local pid proc_cwd proc_cmd listeners
    local owned=() foreign=()
    listeners=$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)
    [ -z "$listeners" ] && return 0
    while IFS= read -r pid; do
        proc_cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null)
        proc_cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
        if [ "$proc_cwd" = "$dir" ] &&
           { { [ "$name" = "gunicorn" ] && [[ "$proc_cmd" == *gunicorn* ]] &&
               [[ "$proc_cmd" == *"--bind 127.0.0.1:$port"* ]]; } ||
             { [ "$name" != "gunicorn" ] && [[ "$proc_cmd" == *"$cmd"* ]]; }; }; then
            owned+=("$pid")
        else
            foreign+=("$pid")
        fi
    done <<< "$listeners"
    if [ "${#foreign[@]}" -gt 0 ]; then
        echo "    ❌ Refusing to free port $port: foreign listener pid(s): ${foreign[*]}"
        return 1
    fi
    echo "    🔧 Freeing port $port (stack-owned pids: ${owned[*]})"
    kill "${owned[@]}" 2>/dev/null || true
    sleep 1
    listeners=$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)
    if [ -n "$listeners" ]; then
        while IFS= read -r pid; do
            proc_cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null)
            proc_cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
            if [ "$proc_cwd" = "$dir" ] &&
               { { [ "$name" = "gunicorn" ] && [[ "$proc_cmd" == *gunicorn* ]] &&
                   [[ "$proc_cmd" == *"--bind 127.0.0.1:$port"* ]]; } ||
                 { [ "$name" != "gunicorn" ] && [[ "$proc_cmd" == *"$cmd"* ]]; }; }; then
                kill -9 "$pid" 2>/dev/null
            fi
        done <<< "$listeners"
        sleep 1
    fi
    listeners=$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)
    [ -z "$listeners" ] || { echo "    ❌ Port $port remains occupied; refusing startup"; return 1; }
}

# ==============================================================================
# UPLOADS BIND-MOUNT PREFLIGHT
# frontend/public/uploads is served from the host (docker-compose.yml), not
# baked into the image. Two things must hold before the frontend container
# starts, and neither can be left to chance:
#
#   1. The directory must exist. If it does not, Docker creates the bind
#      source itself as root:root — the backend (uid 1000) then silently
#      loses the ability to write heroes. This is the restore-from-scratch
#      and fresh-appliance failure mode.
#   2. Files must be world-readable. The container serves them as uid 1001
#      (nextjs, gid 65533/nogroup), which matches neither the owner nor the
#      group of a 664 ross:ross upload — it reads them via the "other" bits.
#      The image used to carry a chmod pass for this; uploads no longer pass
#      through the image, so the check lives here.
#
# Deliberately touches only offenders: a blanket chmod -R over 34k files cost
# 218s per build when it lived in the Dockerfile.
# ==============================================================================
ensure_uploads_dir() {
    local d="$FRONTEND_DIR/public/uploads"

    if [ ! -d "$d" ]; then
        echo "  📁 uploads/ missing (fresh host or restore) — creating $d"
        mkdir -p "$d" || { echo "  ❌ Cannot create $d — frontend would serve 404s for every hero"; return 1; }
    fi

    # Owned by the stack user, group-writable, world-readable+traversable.
    chmod 775 "$d" 2>/dev/null || true

    local bad_files bad_dirs
    bad_files=$(find "$d" -type f ! -perm -o+r 2>/dev/null | wc -l)
    bad_dirs=$(find "$d" -type d ! -perm -o+x 2>/dev/null | wc -l)
    if [ "$bad_files" -gt 0 ] || [ "$bad_dirs" -gt 0 ]; then
        echo "  🔧 Normalising $bad_files file(s) + $bad_dirs dir(s) unreadable by the container user..."
        find "$d" -type f ! -perm -o+r -exec chmod a+r  {} + 2>/dev/null
        find "$d" -type d ! -perm -o+x -exec chmod a+rx {} + 2>/dev/null
    fi
    return 0
}

# The fetcher and the internal Next route share one scoped bearer secret.
# Generate it once at frontend start and copy it only to the two ignored env
# files that need it. Never print the value. A mismatch is treated as a hard
# configuration error rather than silently rotating a live credential.
read_library_revalidation_secret() {
    local env_file="$1" line value
    [ -f "$env_file" ] || return 0
    line=$(grep -E '^LIBRARY_REVALIDATE_SECRET=' "$env_file" 2>/dev/null | tail -n 1)
    value="${line#*=}"
    value="${value%$'\r'}"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    printf '%s' "$value"
}

append_library_revalidation_secret() {
    local env_file="$1" secret="$2"
    [ -f "$env_file" ] || { echo "  ❌ Missing environment file: $env_file"; return 1; }
    (
        umask 077
        printf '\n# Local fetcher → Next Library cache revalidation\nLIBRARY_REVALIDATE_SECRET=%s\n' "$secret" >> "$env_file"
    ) || return 1
    chmod go-rwx "$env_file" 2>/dev/null || true
}

ensure_library_revalidation_secret() {
    local backend_env="$BACKEND_DIR/.env"
    local frontend_env="$FRONTEND_DIR/.env.local"
    local backend_secret frontend_secret secret

    backend_secret=$(read_library_revalidation_secret "$backend_env")
    frontend_secret=$(read_library_revalidation_secret "$frontend_env")
    if [ -n "$backend_secret" ] && [ -n "$frontend_secret" ] && [ "$backend_secret" != "$frontend_secret" ]; then
        echo "  ❌ LIBRARY_REVALIDATE_SECRET differs between backend/.env and frontend/.env.local"
        return 1
    fi

    secret="${backend_secret:-$frontend_secret}"
    if [ -z "$secret" ]; then
        command -v openssl >/dev/null 2>&1 || { echo "  ❌ openssl is required to create the Library revalidation secret"; return 1; }
        secret=$(openssl rand -hex 32) || return 1
        echo "  🔐 Created scoped Library revalidation credential"
    fi

    [ -n "$backend_secret" ] || append_library_revalidation_secret "$backend_env" "$secret" || return 1
    [ -n "$frontend_secret" ] || append_library_revalidation_secret "$frontend_env" "$secret" || return 1
    return 0
}

start_service() {
    local name dir cmd use_venv port
    IFS='|' read -r name dir cmd use_venv port <<< "$1"
    # Starting is an explicit enable action. The watchdog honors this marker
    # when an operator deliberately stops a service.
    rm -f "$PID_DIR/$name.disabled"
    if is_running "$name"; then
        echo "  ⏭️  $name already running"
        return
    fi
    echo "  🚀 Starting $name..."
    free_port "$name" "$dir" "$cmd" "$port" || return 1

    # Docker-managed services
    if [ "$cmd" = "docker" ]; then
        [ "$name" = "frontend" ] && {
            ensure_uploads_dir || return 1
            ensure_library_revalidation_secret || return 1
        }
        docker compose -f "$COMPOSE_FILE" up -d --no-deps "$name" >> "$LOG_DIR/$name.log" 2>&1
        sleep 6
        if docker ps --filter "name=arc-$name" --filter "status=running" -q | grep -q .; then
            echo "    ✅ $name up (docker container arc-$name)"
            return 0
        else
            echo "    ❌ $name container failed — check $LOG_DIR/$name.log"
            return 1
        fi
    fi

    if [ "$use_venv" = "true" ]; then
        setsid bash -c "cd '$dir' && source '$VENV' && exec $cmd" >> "$LOG_DIR/$name.log" 2>&1 &
    else
        setsid bash -c "cd '$dir' && exec $cmd" >> "$LOG_DIR/$name.log" 2>&1 &
    fi
    local pid=$!
    echo $pid > "$PID_DIR/$name.pid"
    # Gunicorn needs longer to bind than other services
    local wait=2
    [[ "$name" == "gunicorn" ]] && wait=5
    sleep $wait
    if is_running "$name"; then
        echo "    ✅ $name up (pid $pid) → $LOG_DIR/$name.log"
    else
        echo "    ❌ $name failed — check $LOG_DIR/$name.log"
        rm -f "$PID_DIR/$name.pid"
        return 1
    fi
    return 0
}

stop_service() {
    local name dir cmd use_venv port
    IFS='|' read -r name dir cmd use_venv port <<< "$1"
    local pidfile="$PID_DIR/$name.pid"
    touch "$PID_DIR/$name.disabled"

    # Docker-managed services
    if [ "$cmd" = "docker" ]; then
        echo "  🛑 Stopping $name (docker)..."
        if ! docker compose -f "$COMPOSE_FILE" stop "$name" >> "$LOG_DIR/$name.log" 2>&1; then
            echo "    ❌ $name failed to stop — check $LOG_DIR/$name.log"
            return 1
        fi
        if is_running "$name"; then
            echo "    ❌ $name still running after docker stop"
            return 1
        fi
        rm -f "$pidfile"
        echo "    ✅ $name stopped"
        return 0
    fi

    # Always sweep orphans first — before is_running check
    pkill -f "$dir.*python3 $cmd" 2>/dev/null || true
    if ! is_running "$name"; then
        free_port "$name" "$dir" "$cmd" "$port" || return 1
        echo "  ⏭️  $name not running"
        rm -f "$pidfile"
        return 0
    fi
    local pid=$(cat "$pidfile")
    echo "  🛑 Stopping $name (pid $pid)..."
    local pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
    if [ -n "$pgid" ] && [ "$pgid" != "0" ]; then
        kill -- "-$pgid" 2>/dev/null
    else
        kill "$pid" 2>/dev/null
    fi
    local i=0
    while kill -0 "$pid" 2>/dev/null && [ $i -lt 10 ]; do
        sleep 1
        ((i++))
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "    ⚠️  $name didn't stop cleanly, force killing..."
        [ -n "$pgid" ] && [ "$pgid" != "0" ] && kill -9 -- "-$pgid" 2>/dev/null
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi
    if kill -0 "$pid" 2>/dev/null; then
        echo "    ❌ $name is still alive after force kill (pid $pid)"
        return 1
    fi
    # Kill orphaned processes from this specific stack directory
    pgrep -f "cd '$dir'.*$cmd\|$dir.*$cmd" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    free_port "$name" "$dir" "$cmd" "$port" || return 1
    rm -f "$pidfile"
    echo "    ✅ $name stopped"
    return 0
}

# ==============================================================================
# LOG MANAGEMENT
# ==============================================================================
cmd_prune_logs() {
    local dry_run="${1:-}"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "🧹 Log maintenance ($timestamp)..."

    for logfile in "$LOG_DIR"/*.log "$BACKEND_DIR"/*.log; do
        [ -f "$logfile" ] || continue
        local size_mb=$(du -m "$logfile" 2>/dev/null | cut -f1)
        if [ "${size_mb:-0}" -ge "$LOG_MAX_SIZE_MB" ]; then
            local ts=$(date '+%Y%m%d_%H%M%S')
            local rotated="${logfile%.log}.$ts.log"
            if [ -z "$dry_run" ]; then
                mv "$logfile" "$rotated"
                gzip "$rotated" &
                touch "$logfile"
                echo "  🔄 Rotated $(basename $logfile) (${size_mb}MB) → $(basename $rotated).gz"
            else
                echo "  [DRY] Would rotate $(basename $logfile) (${size_mb}MB)"
            fi
        fi
    done

    local count=0
    while IFS= read -r old_log; do
        if [ -z "$dry_run" ]; then
            rm -f "$old_log"
            echo "  🗑️  Deleted $(basename $old_log)"
        else
            echo "  [DRY] Would delete $(basename $old_log)"
        fi
        ((count++))
    done < <(find "$LOG_DIR" "$BACKEND_DIR" \
        \( -name "*.log" -o -name "*.log.gz" \) \
        -mtime +$LOG_MAX_DAYS 2>/dev/null)

    [ $count -eq 0 ] \
        && echo "  ✅ No logs older than ${LOG_MAX_DAYS} days." \
        || echo "  ✅ Pruned $count old log file(s)."

    echo ""
    echo "  📊 Current log sizes:"
    du -sh "$LOG_DIR"/*.log "$BACKEND_DIR"/*.log 2>/dev/null \
        | sort -rh \
        | awk '{printf "     %s  %s\n", $1, $2}'
    echo ""
}

get_service_def() {
    local target="$1"
    for svc in "${SERVICES[@]}"; do
        local name
        IFS='|' read -r name _ _ _ _ <<< "$svc"
        [ "$name" = "$target" ] && echo "$svc" && return 0
    done
    return 1
}

# ==============================================================================
# START / STOP / RESTART
# ==============================================================================
cmd_start() {
    local target="${1:-}"
    if [ -n "$target" ]; then
        local svc
        svc=$(get_service_def "$target") || { echo "❌ Unknown service: $target"; exit 1; }
        echo "🚀 Starting $target..."
        start_service "$svc"
    else
        echo "🔧 Starting Arc Codex stack..."
        cmd_prune_logs
        local failed=()
        local svc name
        for svc in "${SERVICES[@]}"; do
            IFS='|' read -r name _ _ _ _ <<< "$svc"
            start_service "$svc" || failed+=("$name")
        done
        echo ""
        if [ "${#failed[@]}" -gt 0 ]; then
            echo "❌ Stack startup failed: ${failed[*]}"
            return 1
        fi
        echo "✅ Stack started. Run './arc.sh status' to verify."
    fi
}

cmd_stop() {
    local target="${1:-}"
    if [ -n "$target" ]; then
        local svc
        svc=$(get_service_def "$target") || { echo "❌ Unknown service: $target"; exit 1; }
        echo "🛑 Stopping $target..."
        stop_service "$svc"
    else
        echo "🛑 Stopping Arc Codex stack (reverse order)..."
        local failed=()
        local name
        for (( i=${#SERVICES[@]}-1; i>=0; i-- )); do
            name="${SERVICES[$i]%%|*}"
            stop_service "${SERVICES[$i]}" || failed+=("$name")
        done
        echo ""
        if [ "${#failed[@]}" -gt 0 ]; then
            echo "❌ Stack stop incomplete: ${failed[*]}"
            return 1
        fi
        echo "✅ Stack stopped."
    fi
}

cmd_restart() {
    local target="${1:-}"
    if [ -n "$target" ]; then
        local svc
        svc=$(get_service_def "$target") || { echo "❌ Unknown service: $target"; exit 1; }
        echo "🔄 Restarting $target..."
        # Hold off the watchdog while the stop→start gap is open, so its
        # 60s check can't race us and spawn an untracked duplicate.
        touch "$PID_DIR/watchdog.hold"
        trap 'rm -f "$PID_DIR/watchdog.hold"' EXIT
        if ! stop_service "$svc"; then
            rm -f "$PID_DIR/watchdog.hold"
            trap - EXIT
            return 1
        fi
        sleep 1
        local rc=0
        start_service "$svc" || rc=$?
        rm -f "$PID_DIR/watchdog.hold"
        trap - EXIT
        return "$rc"
    else
        cmd_stop || return 1
        sleep 2
        cmd_start
    fi
}

# ==============================================================================
# STATUS / LOGS / CHECKUP
# ==============================================================================
cmd_status() {
    echo "📊 Arc Codex Stack Status:"
    echo "─────────────────────────────────────"
    for svc in "${SERVICES[@]}"; do
        local name port
        IFS='|' read -r name _ _ _ port <<< "$svc"
        local pidfile="$PID_DIR/$name.pid"
        if is_running "$name"; then
            local detail
            if [ "$name" = "frontend" ]; then
                detail="docker arc-frontend, port $port"
            else
                local pid=$(cat "$pidfile")
                detail="pid $pid"
                [ -n "$port" ] && lsof -i:"$port" >/dev/null 2>&1 && detail="$detail, port $port"
            fi
            echo "  🟢 $name ($detail)"
        elif [ -f "$pidfile" ]; then
            echo "  🔴 $name (stale pidfile — crashed?)"
        else
            echo "  ⚫ $name (not started)"
        fi
    done
    echo "─────────────────────────────────────"
    local log_size=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
    local backup_count=$(ls "$BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)
    local backup_size=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    local cold_count=$(ls "$COLD_BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)
    local cold_size=$(du -sh "$COLD_BACKUP_DIR" 2>/dev/null | cut -f1)
    echo "  💾 logs/:          $log_size"
    echo "  📦 SSD backups:    $backup_size ($backup_count files, keep $BACKUP_KEEP)"
    echo "  🧊 Cold archive:   $cold_size ($cold_count files, keep $COLD_BACKUP_KEEP)"
}

cmd_logs() {
    echo "📋 Tailing all logs (Ctrl+C to stop)..."
    tail -f "$LOG_DIR"/*.log
}

cmd_build() {
    echo "🏗️  Building frontend (Docker)..."
    if ! is_running "gunicorn"; then
        echo "  ⚠️  Gunicorn not running — starting it for the build..."
        start_service "gunicorn|$BACKEND_DIR|./gunicorn_arc.sh|true|5005"
        sleep 5
    fi
    # Stop running container before rebuild
    docker compose -f "$COMPOSE_FILE" stop frontend 2>/dev/null
    local build_args=""
    if [[ "${2:-}" == "--clean" ]]; then
        echo "  🧹 No-cache rebuild requested..."
        build_args="--no-cache"
    fi
    # Stamp the SW cache key so browsers detect the new bundle and purge the
    # old cache on next navigation. `git describe --always --dirty` at least
    # distinguishes clean-vs-dirty; it will not distinguish two different
    # dirty states, so commit before deploying if that matters.
    export SW_CACHE_STAMP="$(git -C "$ITC_ROOT" describe --always --dirty 2>/dev/null || echo dev)"
    echo "  🔖 SW_CACHE_STAMP=$SW_CACHE_STAMP"
    docker compose -f "$COMPOSE_FILE" build $build_args frontend 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Build complete."
        echo "  🔄 Starting new frontend container..."
        ensure_uploads_dir || { echo "❌ Refusing to start frontend without a usable uploads/ mount."; exit 1; }
        ensure_library_revalidation_secret || { echo "❌ Refusing to start frontend without Library revalidation authentication."; exit 1; }
        docker compose -f "$COMPOSE_FILE" up -d --no-deps frontend 2>&1
        sleep 6
        if is_running "frontend"; then
            echo "  ✅ Frontend live (docker arc-frontend)"
        else
            echo "  ❌ Frontend container failed to start — check logs"
        fi
    else
        echo "❌ Build failed — check output above."
        exit 1
    fi
}

cmd_checkup() {
    echo "🩺 Arc Codex Health Checkup..."
    echo "─────────────────────────────────────"
    echo -n "📡 API Response:      "
    curl -o /dev/null -s -w '%{time_total}s\n' http://127.0.0.1:5005/api/get_feed?limit=1 || echo "FAILED"
    echo -n "🌐 Frontend Response: "
    curl -o /dev/null -s -w '%{time_total}s\n' http://127.0.0.1:3000 || echo "FAILED"
    echo "📁 Recent Log Errors (last 24h):"
    # See ops/RUNBOOK.md. Two prior bugs stacked in this block:
    #
    # 1) `tail -n 5` with no time gate took the last 5 grep MATCHES in glob
    #    order, so a mostly-quiet file (e.g. watchdog.log, tens of thousands
    #    of lines) could surface week-old resolved errors as if current.
    #    Confirmed doing exactly that 2026-08-27 morning: showed 6-day-old
    #    corpus_exporter/caddy_exporter failures that had recovered on their
    #    own via a host reboot hours earlier.
    #
    # 2) The time gate then exposed a second bug: `-riE
    #    "error|failed|exception"` also matched INFO-level lines whose BODY
    #    contained one of those words — normal retry paths ("🔄 Simple fetch
    #    failed, trying stealth headers"), INFO successes whose URL/title
    #    happened to contain the string ("✅ simple request succeeded for
    #    .../error-analyses-of-auto/..."), thumb rehost fallbacks. Sampled
    #    2026-08-27: 367 of the trailing-24h matches were INFO. Fix: match
    #    on the LOG LEVEL TOKEN, case-sensitive. Python's logging module
    #    always emits ERROR/WARNING/CRITICAL uppercase; word-boundaries
    #    prevent "AttributeError" in a stack trace or an article title
    #    containing "Error" from firing (a proper logger.exception() emits
    #    the ERROR line ABOVE the traceback, and that line still matches on
    #    its own level token). Every log in the stack passes through Python
    #    logging with LEVEL in an uppercased delimited slot, across all
    #    four formatter variants: " - LEVEL - ", " LEVEL ", "] LEVEL in ",
    #    "[LEVEL]".
    #
    # String comparison, not date -d per line: ISO-ish "YYYY-MM-DD HH:MM:SS"
    # timestamps sort lexicographically the same as chronologically, so one
    # `date` call for the cutoff is enough — spawning date per line would
    # make checkup noticeably slow for no benefit.
    #
    # Logs using a bare HH:MM:SS format with no date (audio_backfill.log)
    # can't be verified this way and are silently excluded — under-
    # reporting one log beats resurrecting the stale-line bug replaced in
    # (1). The main other historical source of undated lines was
    # sync_intel.log's Redis-loading messages from a boot-adjacent hourly
    # cron; those got timestamps in the same commit as this fix, so the
    # "silently excluded" set is now near-empty rather than open-ended.
    local _checkup_cutoff
    _checkup_cutoff=$(date -d '24 hours ago' '+%Y-%m-%d %H:%M:%S')
    local _checkup_errors
    _checkup_errors=$(grep -rE '\b(ERROR|WARNING|CRITICAL)\b' "$LOG_DIR"/*.log 2>/dev/null | awk -v cutoff="$_checkup_cutoff" '
        match($0, /[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}/) {
            ts = substr($0, RSTART, RLENGTH)
            gsub(/T/, " ", ts)
            if (ts >= cutoff) print
        }
    ' | tail -n 5)
    if [ -n "$_checkup_errors" ]; then
        echo "$_checkup_errors"
    else
        echo "   ✅ No critical errors found in the last 24h."
    fi
    echo "🧠 Resource Usage (stack processes):"
    ps -u $USER -o %cpu,%mem,cmd | grep -E "gunicorn|node|scribe|analyzer|mailer" | grep -v grep \
        | awk '{cpu+=$1; mem+=$2} END {printf "   CPU: %.1f%% | RAM: %.1f%%\n", cpu, mem}'
    echo "─────────────────────────────────────"
}

# ==============================================================================
# BACKUP — FAST (SSD, code only, stack stopped, keep 5)
# For: daily rollback point. Not disaster recovery.
# Cron: 0 3 * * * /home/www/arc_stack/arc.sh backup
# ==============================================================================
cmd_backup() {
    local DATE=$(date +%Y-%m-%d_%H%M)
    local FILE="$BACKUP_DIR/arc_backup_$DATE.tar.gz"
    echo "📦 Fast backup (SSD, code only)..."
    cmd_prune_logs
    cmd_stop || { echo "❌ Backup aborted: stack did not stop cleanly."; return 1; }
    echo "🗜️  Archiving code and config..."
    # Scraped hero images are large (grew the warm tar to ~2 GB) and fully
    # reproducible on re-scrape; exclude them unless the cfg opts in. Default
    # (flag absent) is to exclude.
    local SCRAPED_EXCLUDE="--exclude=./frontend/public/uploads/scraped"
    [ "$(grep -oP '^include_scraped_images\s*=\s*\K(true|false)' "$ITC_ROOT/arc.cfg" 2>/dev/null)" = "true" ] \
        && SCRAPED_EXCLUDE=""
    # umask scoped to the tar ONLY (subshell): this archive also embeds
    # backend/.env, so it must not be world-readable — but cmd_backup restarts
    # the stack below, and a function-level umask would follow cmd_start into
    # every service log and pidfile it creates. Keep the blast radius here.
    ( umask 027
      tar -zcf "$FILE" \
        $SCRAPED_EXCLUDE \
        --exclude="./frontend/node_modules" \
        --exclude="./frontend/.next" \
        --exclude="./backend/venv" \
        --exclude="./backups" \
        --exclude="./logs" \
        --exclude="./pids" \
        --exclude="*.log" \
        --exclude="*.log.gz" \
        --exclude="./upload/completed" \
        --exclude="./upload/failed" \
        -C "$ITC_ROOT" . )
    if [ -f "$FILE" ]; then
        echo "✅ Backup: $FILE ($(du -sh "$FILE" | cut -f1))"
        # Retain only the most recent N
        ls -t "$BACKUP_DIR"/arc_backup_*.tar.gz 2>/dev/null \
            | tail -n +$(( BACKUP_KEEP + 1 )) \
            | xargs rm -f 2>/dev/null
        echo "📦 SSD backups kept: $(ls "$BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)/$BACKUP_KEEP"
    else
        echo "❌ Backup FAILED."
    fi
    echo "🔄 Restarting stack..."
    cmd_start
}

# ==============================================================================
# BACKUP — COLD (small: code + config only, stack stays up, keep N)
# For: disaster recovery of what can't be re-derived. NOT a snapshot of
# ingested content. Ross's principle (2026-08-27): "Nothing I ingest actually
# matters, it's the ingestion code that needs backup, not the contents.
# Anything I already have is already obsolete — this is a system for
# analyzing current signals, not antique ones." Reshaped from a ~19 GB
# data-heavy archive to ~355 MB on that basis. See ops/RUNBOOK.md 2026-08-27
# for the full inventory and reasoning; summary:
#
#   DROPPED (was captured here, no longer is):
#     - Redis RDB       — the ingested corpus. Disposable per the principle;
#                         re-ingests via scribe's normal cycle.
#     - Solr snapshot    — rebuildable from Redis (kasmir7.py has a
#                         re-index-from-Redis path already).
#     - library.db       — re-fetchable from Gutenberg (library_fetcher.py),
#                         a stable low-risk source. A download, not a loss.
#   DROPPED (excluded from the tar below, was never staged separately):
#     - frontend/public/uploads/  — audio + scraped hero images + loose
#                         assets. Audio derives from original_text, which
#                         lives in the (also disposable) Redis RDB — keeping
#                         audio without the text it narrates is incoherent,
#                         and old narrations aren't worth ~37h resynthesis
#                         under the principle above anyway. Hero images are
#                         re-fetchable from image_source_url only while the
#                         source is still live — same disposability as Redis.
#     - frontend/.next   — build output, regenerate with `npm run build`.
#
#   KEPT:
#     - .git             — despite the nightly GitHub push (see
#                         ops/nightly-git-push.sh). A backup that depends on
#                         a third party being reachable isn't self-sufficient,
#                         and 251 MB is nothing at this archive's new size.
#     - host_config/Caddyfile — sole server of /uploads/*. A required member.
#     - host_config/systemd/  — installed unit drift record. Best-effort.
#
# Restore requires supplying separately (not in the archive, by R9 design):
#   backend/.env, frontend/.env.local, secret/ — reconfigurable, not
# recoverable. Plus rebuilding what was dropped above: library.db via
# library_fetcher.py, Solr via kasmir7's re-index, the corpus via normal
# re-ingestion. OLD CONTENT IS NOT RESTORED — that is by design, not a gap.
# Cron: 0 2 * * 0 /home/www/arc_stack/arc.sh backup-cold
# ==============================================================================
cmd_backup_cold() {
    # No secrets in the archive (R9 closed 2026-08-27) and no bulk ingested
    # data either now, but still kept non-world-readable — code, config, and
    # host_config aren't meant for every local account. 027 → files 640,
    # dirs 750. The GROUP comes from the setgid bit on $COLD_BACKUP_DIR
    # (2750 ross:bkread), not from here — without setgid these land
    # ross:ross and bkpull cannot read them.
    umask 027
    local DATE=$(date +%Y-%m-%d_%H%M)
    mkdir -p "$COLD_BACKUP_DIR"
    local FILE="$COLD_BACKUP_DIR/arc_cold_$DATE.tar.gz"
    local STAGING="$COLD_BACKUP_DIR/.staging_$DATE"
    mkdir -p "$STAGING/host_config/systemd"
    echo "🧊 Cold archive backup (code + config only — see header comment)..."

    # --- Host config: lives outside $ITC_ROOT, so the stack tar never saw it ---
    # The Caddyfile is the whole reason this block exists: since uploads left
    # the frontend image, Caddy's `handle /uploads/*` file_server is the ONLY
    # thing serving hero images. A restore-from-scratch without it comes back
    # with every hero 404ing and no config on disk explaining why.
    if cp /etc/caddy/Caddyfile "$STAGING/host_config/Caddyfile" 2>/dev/null; then
        echo "   ✅ Caddyfile captured ($(du -sh "$STAGING/host_config/Caddyfile" | cut -f1))"
    else
        echo "   ⚠️  Caddyfile capture FAILED — /uploads route will be unrestorable"
    fi
    # Installed systemd units. ops/systemd/ in the repo is the source of truth
    # and already rides in the stack tar, so these copies are the *drift
    # record*: what is actually installed on the host, drop-ins included.
    # Best-effort by design — a missing unit is recoverable from the repo copy,
    # so it warns rather than failing the archive (unlike the Caddyfile).
    for u in arc-stack arc-watchdog; do
        cp "/etc/systemd/system/$u.service" "$STAGING/host_config/systemd/" 2>/dev/null \
            || echo "   ⚠️  systemd unit not captured: $u.service"
        [ -d "/etc/systemd/system/$u.service.d" ] \
            && cp -r "/etc/systemd/system/$u.service.d" "$STAGING/host_config/systemd/"
    done

    echo "🗜️  Archiving stack (code + config — no data layer, see header)..."
    local PARTIAL="$FILE.partial"
    tar -zcf "$PARTIAL" \
        --exclude="./frontend/node_modules" \
        --exclude="./frontend/.next" \
        --exclude="./frontend/public/uploads" \
        --exclude="./backend/venv" \
        --exclude="./backend/.env*" \
        --exclude="./frontend/.env.local*" \
        --exclude="./secret" \
        --exclude="./backups" \
        --exclude="./logs" \
        --exclude="./pids" \
        --exclude="*.log" \
        --exclude="*.log.gz" \
        --exclude="./backend/upload/completed" \
        --exclude="./backend/upload/failed" \
        -C "$ITC_ROOT" . \
        -C "$STAGING" host_config
    local tar_rc=$?

    # --- Verification gate. Nothing gets a .sha256 sidecar without passing
    # every check here, so a torn archive can never impersonate a good one.
    # No RDB to redis-check-rdb any more — gate is tar exit, gzip -t, and
    # required-member presence. The sidecar is the eligibility token for the
    # off-host pull (ops/spectre-pull-backups.sh). Missing sidecar = not
    # pulled — this gate is load-bearing, not aspirational.
    local fail=""
    [ $tar_rc -eq 0 ] || fail="tar exit $tar_rc"
    if [ -z "$fail" ] && ! gzip -t "$PARTIAL" 2>/dev/null; then
        fail="gzip -t integrity check"
    fi
    if [ -z "$fail" ]; then
        local required="./backend/main.py ./arc.sh host_config/Caddyfile"
        local members
        members=$(tar -tzf "$PARTIAL" 2>/dev/null) || fail="tar -tzf listing"
        if [ -z "$fail" ]; then
            for m in $required; do
                echo "$members" | grep -qx "$m" || { fail="required member missing: $m"; break; }
            done
        fi
    fi
    rm -rf "$STAGING"

    if [ -n "$fail" ]; then
        rm -f "$PARTIAL"
        echo "❌ Cold backup FAILED verification: $fail — no archive, no sidecar."
        return 1
    fi

    sync "$PARTIAL"
    mv "$PARTIAL" "$FILE"
    # Sidecar LAST — its existence marks the archive complete and shippable.
    ( cd "$COLD_BACKUP_DIR" && sha256sum "$(basename "$FILE")" > "$(basename "$FILE").sha256" )
    echo "✅ Cold archive: $FILE ($(du -sh "$FILE" | cut -f1))"
    # Retain only the most recent N
    ls -t "$COLD_BACKUP_DIR"/arc_cold_*.tar.gz 2>/dev/null \
        | tail -n +$(( COLD_BACKUP_KEEP + 1 )) \
        | xargs rm -f 2>/dev/null
    # Drop sidecars orphaned by rotation
    for s in "$COLD_BACKUP_DIR"/arc_cold_*.tar.gz.sha256; do
        [ -f "${s%.sha256}" ] || rm -f "$s"
    done
    echo "🧊 Cold archives kept: $(ls "$COLD_BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)/$COLD_BACKUP_KEEP"
}

# ==============================================================================
# RESTORE — select and extract a backup, then restart the stack
# Lists SSD backups first, then cold archives. Pick by number.
# ==============================================================================
cmd_restore() {
    echo "🗄️  Arc Codex Restore"
    echo "────────────────────────────────────"

    # Collect all available backups
    local -a files=()
    local -a labels=()

    # SSD backups (newest first)
    while IFS= read -r f; do
        files+=("$f")
        labels+=("📦 SSD   $(basename "$f")  ($(du -sh "$f" | cut -f1))")
    done < <(ls -t "$BACKUP_DIR"/arc_backup_*.tar.gz 2>/dev/null)

    # Cold archives (newest first)
    while IFS= read -r f; do
        files+=("$f")
        labels+=("🧊 Cold  $(basename "$f")  ($(du -sh "$f" | cut -f1))")
    done < <(ls -t "$COLD_BACKUP_DIR"/arc_cold_*.tar.gz 2>/dev/null)

    if [ ${#files[@]} -eq 0 ]; then
        echo "❌ No backups found."
        return 1
    fi

    echo "Available backups:"
    echo ""
    for i in "${!files[@]}"; do
        printf "  [%d] %s\n" "$((i+1))" "${labels[$i]}"
    done
    echo ""
    printf "Select backup to restore [1-%d] (or q to quit): " "${#files[@]}"
    read -r choice

    [[ "$choice" == "q" || "$choice" == "Q" ]] && echo "Aborted." && return 0

    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#files[@]}" ]; then
        echo "❌ Invalid selection."
        return 1
    fi

    local selected="${files[$((choice-1))]}"
    echo ""
    echo "⚠️  You selected: $(basename "$selected")"
    echo "   This will STOP the stack and overwrite $ITC_ROOT"
    printf "   Type 'yes' to confirm: "
    read -r confirm

    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        return 0
    fi

    echo ""
    echo "🛑 Stopping stack..."
    cmd_stop || { echo "❌ Restore aborted: stack did not stop cleanly."; return 1; }

    echo "📂 Extracting $(basename "$selected") → $ITC_ROOT ..."
    tar -zxf "$selected" -C "$ITC_ROOT"

    if [ $? -eq 0 ]; then
        echo "✅ Restore complete."
    else
        echo "❌ Extraction failed — check the archive."
        return 1
    fi

    echo "🔄 Restarting stack..."
    cmd_start
}

# ==============================================================================
# COMMAND DISPATCH
# ==============================================================================
VALID_SERVICES="gunicorn|scribe|manual_publisher|stream_consumer|analyzer|mailer|bluesky_poster|mastodon_poster|facebook_poster|character_builder|quiz_generator|frontend|corpus_exporter|caddy_exporter"

case "${1:-}" in
    start)        cmd_start "${2:-}" ;;
    stop)         cmd_stop "${2:-}" ;;
    restart)      cmd_restart "${2:-}" ;;
    status)       cmd_status ;;
    logs)         cmd_logs ;;
    build)        cmd_build "${@}" ;;
    checkup)      cmd_checkup ;;
    backup)       cmd_backup ;;
    backup-cold)  cmd_backup_cold ;;
    restore)      cmd_restore ;;
    prune)        cmd_prune_logs "${2:-}" ;;
    grafana-start)
        echo "🚀 Starting Grafana stack (Prometheus + Grafana)..."
        docker compose -f "$GRAFANA_COMPOSE_FILE" up -d
        echo "✅ Grafana available at https://grafana.arc-codex.com"
        ;;
    grafana-stop)
        echo "🛑 Stopping Grafana stack..."
        docker compose -f "$GRAFANA_COMPOSE_FILE" stop
        echo "✅ Grafana stack stopped."
        ;;
    grafana-status)
        docker compose -f "$GRAFANA_COMPOSE_FILE" ps
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|build [--clean]|checkup|backup|backup-cold|restore|prune [dry]|grafana-start|grafana-stop|grafana-status}"
        echo ""
        echo "Service-level control (add service name as second arg):"
        echo "  $0 start|stop|restart [$VALID_SERVICES]"
        echo ""
        echo "Backup:"
        echo "  $0 backup          # Fast SSD backup, code only, stack stops briefly"
        echo "  $0 backup-cold     # Full cold archive to /mnt/data, stack stays up"
        echo "  $0 restore         # Interactive — list backups, pick one, extract + restart"
        echo "  $0 build --clean   # docker build --no-cache: discards ALL layers,"
        echo "                     # including the deps stage (full npm ci reinstall)."
        echo "                     # For dependency, lockfile, or base-image problems"
        echo "                     # only — a plain '$0 build' handles source changes."
        echo ""
        echo "Grafana:"
        echo "  $0 grafana-start   # Start Prometheus + Grafana"
        echo "  $0 grafana-stop    # Stop Prometheus + Grafana"
        echo "  $0 grafana-status  # Show Grafana stack status"
        echo ""
        echo "Cron setup:"
        echo "  0 3 * * *   /home/www/arc_stack/arc.sh backup"
        echo "  0 2 * * 0   /home/www/arc_stack/arc.sh backup-cold"
        exit 1
        ;;
esac
