#!/bin/bash
# watchdog.sh - Arc Codex Service Watchdog
# Checks all ITC services every 60 seconds, restarts any that died.
# Designed to run as a service itself, managed by itc.sh.
#
# Usage: ./watchdog.sh (or managed by itc.sh)

ITC_ROOT="/home/www/arc_stack"
PID_DIR="$ITC_ROOT/pids"
LOG_DIR="$ITC_ROOT/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
CHECK_INTERVAL=60

BACKEND_DIR="$ITC_ROOT/backend"
FRONTEND_DIR="$ITC_ROOT/frontend"
VENV="$BACKEND_DIR/venv/bin/activate"

export PATH="/home/ross/.nvm/versions/node/v22.16.0/bin:$PATH"

SERVICES=(
    "gunicorn|$BACKEND_DIR|./gunicorn_arc.sh|true|5005"
    "scribe|$BACKEND_DIR|python3 scribe.py|true|"
    "manual_publisher|$BACKEND_DIR|python3 manual_publisher.py|true|"
    "stream_consumer|$BACKEND_DIR|python3 stream_consumer.py|true|"
    "analyzer|$BACKEND_DIR|python3 analyzer.py|true|"
    "frontend|$FRONTEND_DIR|npm run start|false|3000"
)

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WATCHDOG] - $1" >> "$WATCHDOG_LOG"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WATCHDOG] - $1"
}

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
        log "🔧 Freeing port $port (pids: $pids)"
        echo "$pids" | xargs kill 2>/dev/null
        sleep 1
        pids=$(lsof -t -i:"$port" 2>/dev/null)
        [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null
    fi
}

restart_service() {
    local name dir cmd use_venv port
    IFS='|' read -r name dir cmd use_venv port <<< "$1"

    log "🔄 Restarting $name..."
    free_port "$port"

    if [ "$use_venv" = "true" ]; then
        setsid bash -c "cd '$dir' && source '$VENV' && exec $cmd" \
            >> "$LOG_DIR/$name.log" 2>&1 &
    else
        setsid bash -c "cd '$dir' && exec $cmd" \
            >> "$LOG_DIR/$name.log" 2>&1 &
    fi

    local pid=$!
    echo $pid > "$PID_DIR/$name.pid"
    sleep 3

    if is_running "$name"; then
        log "✅ $name recovered (pid $pid)"
    else
        log "❌ $name failed to restart — manual intervention needed"
        rm -f "$PID_DIR/$name.pid"
    fi
}

# --- MAIN LOOP ---
log "🐕 Arc Codex Watchdog started (checking every ${CHECK_INTERVAL}s)"

while true; do
    for svc in "${SERVICES[@]}"; do
        local_name="${svc%%|*}"
        if ! is_running "$local_name"; then
            # Only restart if PID file exists (service died vs. intentionally stopped)
            if [ -f "$PID_DIR/$local_name.pid" ]; then
                log "💀 $local_name is down — restarting"
                restart_service "$svc"
            fi
        fi
    done
    sleep "$CHECK_INTERVAL"
done
