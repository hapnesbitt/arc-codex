#!/bin/bash
# arc.sh - Arc Codex / A.R.C. Stack Manager
# Updated: Feb 26, 2026 - Log consolidation, rotation, backup cleanup

# ==============================================================================
# CONFIGURATION
# ==============================================================================
ITC_ROOT="/home/www/arc_stack"
FRONTEND_DIR="$ITC_ROOT/frontend"
BACKEND_DIR="$ITC_ROOT/backend"
VENV="$BACKEND_DIR/venv/bin/activate"
LOG_DIR="$ITC_ROOT/logs"
PID_DIR="$ITC_ROOT/pids"
BACKUP_DIR="$ITC_ROOT/backups"
LOG_MAX_DAYS=9        # Prune logs older than this
LOG_MAX_SIZE_MB=50    # Rotate individual log if larger than this (MB)

SERVICES=(
    "gunicorn|$BACKEND_DIR|./gunicorn_arc.sh|true|5005"
    "scribe|$BACKEND_DIR|python3 scribe.py|true|"
    "manual_publisher|$BACKEND_DIR|python3 manual_publisher.py|true|"
    "stream_consumer|$BACKEND_DIR|python3 stream_consumer.py|true|"
    "analyzer|$BACKEND_DIR|python3 analyzer.py|true|"
    "mailer|$BACKEND_DIR|python3 mailer.py|true|"
    "frontend|$FRONTEND_DIR|npm run start|false|3000"
    "watchdog|$ITC_ROOT|./watchdog.sh|false|"
)

export PATH="/home/ross/.nvm/versions/node/v22.16.0/bin:$PATH"

# ==============================================================================
# HELPERS
# ==============================================================================
mkdir -p "$LOG_DIR" "$PID_DIR" "$BACKUP_DIR"

is_running() {
    local pidfile="$PID_DIR/$1.pid"
    [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

free_port() {
    local port="$1"
    [ -z "$port" ] && return
    local pids
    pids=$(lsof -t -i:"$port" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "    🔧 Freeing port $port (killing pids: $pids)"
        echo "$pids" | xargs kill 2>/dev/null
        sleep 1
        pids=$(lsof -t -i:"$port" 2>/dev/null)
        [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null
    fi
}

start_service() {
    local name dir cmd use_venv port
    IFS='|' read -r name dir cmd use_venv port <<< "$1"
    if is_running "$name"; then
        echo "  ⏭️  $name already running (pid $(cat "$PID_DIR/$name.pid"))"
        return
    fi
    echo "  🚀 Starting $name..."
    free_port "$port"
    if [ "$use_venv" = "true" ]; then
        setsid bash -c "cd '$dir' && source '$VENV' && exec $cmd" >> "$LOG_DIR/$name.log" 2>&1 &
    else
        setsid bash -c "cd '$dir' && exec $cmd" >> "$LOG_DIR/$name.log" 2>&1 &
    fi
    local pid=$!
    echo $pid > "$PID_DIR/$name.pid"
    sleep 2
    if is_running "$name"; then
        echo "    ✅ $name up (pid $pid) → $LOG_DIR/$name.log"
    else
        echo "    ❌ $name failed — check $LOG_DIR/$name.log"
        rm -f "$PID_DIR/$name.pid"
    fi
}

stop_service() {
    local name dir cmd use_venv port
    IFS='|' read -r name dir cmd use_venv port <<< "$1"
    local pidfile="$PID_DIR/$name.pid"
    if ! is_running "$name"; then
        free_port "$port"
        echo "  ⏭️  $name not running"
        rm -f "$pidfile"
        return
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
    fi
    free_port "$port"
    rm -f "$pidfile"
    echo "    ✅ $name stopped"
}

# ==============================================================================
# LOG MANAGEMENT
# Note: Python services write their own structured logs to backend/*.log via
# Python's logging module. arc.sh also captures stdout/stderr to logs/*.log.
# Both locations are managed here. To consolidate to logs/ only, update the
# LOG_FILE constant in each Python service to point to $LOG_DIR.
# ==============================================================================
cmd_prune_logs() {
    local dry_run="${1:-}"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "🧹 Log maintenance ($timestamp)..."

    # 1. Rotate oversized logs (rename with timestamp, gzip, recreate empty)
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

    # 2. Delete logs (including rotated/gzipped) older than LOG_MAX_DAYS
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

    if [ $count -eq 0 ]; then
        echo "  ✅ No logs older than ${LOG_MAX_DAYS} days."
    else
        echo "  ✅ Pruned $count old log file(s)."
    fi

    # 3. Report current log sizes
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
        if [ "$name" = "$target" ]; then
            echo "$svc"
            return 0
        fi
    done
    return 1
}

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
        for svc in "${SERVICES[@]}"; do start_service "$svc"; done
        echo ""
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
        for (( i=${#SERVICES[@]}-1; i>=0; i-- )); do stop_service "${SERVICES[$i]}"; done
        echo ""
        echo "✅ Stack stopped."
    fi
}

cmd_restart() {
    local target="${1:-}"
    if [ -n "$target" ]; then
        local svc
        svc=$(get_service_def "$target") || { echo "❌ Unknown service: $target"; exit 1; }
        echo "🔄 Restarting $target..."
        stop_service "$svc"
        sleep 1
        start_service "$svc"
    else
        cmd_stop
        sleep 2
        cmd_start
    fi
}

cmd_status() {
    echo "📊 Arc Codex Stack Status:"
    echo "─────────────────────────────────────"
    for svc in "${SERVICES[@]}"; do
        local name port
        IFS='|' read -r name _ _ _ port <<< "$svc"
        local pidfile="$PID_DIR/$name.pid"
        if is_running "$name"; then
            local pid=$(cat "$pidfile")
            local detail="pid $pid"
            [ -n "$port" ] && lsof -i:"$port" >/dev/null 2>&1 && detail="$detail, port $port"
            echo "  🟢 $name ($detail)"
        elif [ -f "$pidfile" ]; then
            echo "  🔴 $name (stale pidfile — crashed?)"
        else
            echo "  ⚫ $name (not started)"
        fi
    done
    echo "─────────────────────────────────────"
    local log_size=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
    local backend_log_size=$(du -sh "$BACKEND_DIR"/*.log 2>/dev/null | awk '{sum+=$1} END{print sum+0"M"}')
    local backup_count=$(ls "$BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)
    local backup_size=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    echo "  💾 logs/: $log_size  |  backend/*.log: $backend_log_size"
    echo "  📦 backups/: $backup_size ($backup_count files)"
}

cmd_logs() {
    echo "📋 Tailing all logs (Ctrl+C to stop)..."
    tail -f "$LOG_DIR"/*.log
}

cmd_build() {
    echo "🏗️  Building frontend..."
    if ! is_running "gunicorn"; then
        echo "  ⚠️  Gunicorn not running — starting it for the build..."
        start_service "gunicorn|$BACKEND_DIR|./gunicorn_arc.sh|true|5005"
        sleep 3
    fi
    cd "$FRONTEND_DIR" || exit 1
    rm -rf .next
    npm run build 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Build complete."
        echo "  🔄 Restarting frontend with new build..."
        cmd_restart "frontend"
    else
        echo "❌ Build failed — check output above."
        exit 1
    fi
}

cmd_backup() {
    local DATE=$(date +%Y-%m-%d_%H%M)
    local FILE="$BACKUP_DIR/arc_backup_$DATE.tar.gz"
    echo "📦 Initializing Stone-Axe Backup..."
    cmd_prune_logs
    cmd_stop
    echo "🗜️  Archiving code and config (excluding logs, venv, uploads, build artifacts)..."
    tar -zcf "$FILE" \
        --exclude="frontend/node_modules" \
        --exclude="backend/venv" \
        --exclude="frontend/.next" \
        --exclude="backups" \
        --exclude="logs" \
        --exclude="*.log" \
        --exclude="*.log.gz" \
        --exclude="upload/completed" \
        --exclude="upload/failed" \
        -C "$ITC_ROOT" .
    if [ -f "$FILE" ]; then
        echo "✅ Backup created: $FILE"
        echo "🛡️  Size: $(du -sh "$FILE" | cut -f1)"
        ls -t "$BACKUP_DIR"/arc_backup_*.tar.gz | tail -n +6 | xargs rm -f 2>/dev/null
    else
        echo "❌ Backup FAILED."
    fi
    echo "🔄 Restarting stack..."
    cmd_start
}

cmd_checkup() {
    echo "🩺 Arc Codex Health Checkup..."
    echo "─────────────────────────────────────"
    echo -n "📡 API Response: "
    curl -o /dev/null -s -w '%{time_total}s\n' http://127.0.0.1:5005/api/get_feed?limit=1 || echo "FAILED"
    echo -n "🌐 Frontend Response: "
    curl -o /dev/null -s -w '%{time_total}s\n' http://127.0.0.1:3000 || echo "FAILED"
    echo "📁 Recent Log Errors (Last 24h):"
    grep -riE "error|failed|exception" "$LOG_DIR"/*.log 2>/dev/null | tail -n 5 || echo "   ✅ No critical errors found."
    echo "🧠 Resource Usage (Stack):"
    ps -u $USER -o %cpu,%mem,cmd | grep -E "gunicorn|node|scribe|analyzer" | grep -v grep | awk '{cpu+=$1; mem+=$2} END {printf "   CPU: %.1f%% | RAM: %.1f%%\n", cpu, mem}'
    echo "─────────────────────────────────────"
}

VALID_SERVICES="gunicorn|scribe|manual_publisher|stream_consumer|analyzer|mailer|frontend|watchdog"

case "${1:-}" in
    start)   cmd_start "${2:-}" ;;
    stop)    cmd_stop "${2:-}" ;;
    restart) cmd_restart "${2:-}" ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    build)   cmd_build ;;
    checkup) cmd_checkup ;;
    backup)  cmd_backup ;;
    prune)   cmd_prune_logs "${2:-}" ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|build|checkup|backup|prune [dry]}"
        echo ""
        echo "Service-level control (add service name as second arg):"
        echo "  $0 start|stop|restart [$VALID_SERVICES]"
        echo ""
        echo "Examples:"
        echo "  $0 restart scribe"
        echo "  $0 restart frontend"
        echo "  $0 stop analyzer"
        echo "  $0 start gunicorn"
        exit 1
        ;;
esac
