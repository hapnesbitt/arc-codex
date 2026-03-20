#!/bin/bash
# watchdog.sh - Arc Codex Service Watchdog
# Checks all services every 60 seconds, restarts any that died.
# Managed by arc.sh — do not run directly in production.
#
# Updated: Mar 2026 — mailer added (was missing from original)
#           Mar 2026 — frontend now managed as Docker container

ITC_ROOT="/home/www/arc_stack"
PID_DIR="$ITC_ROOT/pids"
LOG_DIR="$ITC_ROOT/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
CHECK_INTERVAL=60

BACKEND_DIR="$ITC_ROOT/backend"
FRONTEND_DIR="$ITC_ROOT/frontend"
VENV="$BACKEND_DIR/venv/bin/activate"

COMPOSE_FILE="$ITC_ROOT/docker-compose.yml"
export PATH="/home/ross/.nvm/versions/node/v22.16.0/bin:$PATH"

# Must match arc.sh SERVICES order — watchdog does not manage itself
SERVICES=(
    "gunicorn|$BACKEND_DIR|./gunicorn_arc.sh|true|5005"
    "scribe|$BACKEND_DIR|python3 scribe.py|true|"
    "manual_publisher|$BACKEND_DIR|python3 manual_publisher.py|true|"
    "stream_consumer|$BACKEND_DIR|python3 stream_consumer.py|true|"
    "analyzer|$BACKEND_DIR|python3 analyzer.py|true|"
    "mailer|$BACKEND_DIR|python3 mailer.py|true|"
    "bluesky_poster|$BACKEND_DIR|python3 bluesky_poster.py|true|"
    "character_builder|$BACKEND_DIR|python3 character_builder.py|true|"
    "frontend|$ITC_ROOT|docker|false|3000"   # docker sentinel — managed via docker compose
)

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WATCHDOG] - $1" >> "$WATCHDOG_LOG"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WATCHDOG] - $1"
}

is_running() {
    local name="$1"
    if [ "$name" = "frontend" ]; then
        docker ps --filter "name=arc-frontend" --filter "status=running" -q 2>/dev/null | grep -q .
        return
    fi
    local pidfile="$PID_DIR/$name.pid"
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

    # Docker-managed services
    if [ "$cmd" = "docker" ]; then
        docker compose -f "$COMPOSE_FILE" up -d --no-deps "$name" >> "$LOG_DIR/$name.log" 2>&1
        sleep 3
        if is_running "$name"; then
            log "✅ $name recovered (docker arc-$name)"
        else
            log "❌ $name container failed to restart — manual intervention needed"
        fi
        return
    fi

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

    # Gunicorn needs longer to bind
    local wait=3
    [[ "$name" == "gunicorn" ]] && wait=5
    sleep $wait

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
        IFS='|' read -r _ _ local_cmd _ _ <<< "$svc"
        if ! is_running "$local_name"; then
            if [ "$local_cmd" = "docker" ]; then
                # Docker containers: restart if compose service exists but container is not running
                if docker compose -f "$COMPOSE_FILE" ps --services 2>/dev/null | grep -q "^$local_name$"; then
                    log "💀 $local_name container is down — restarting"
                    restart_service "$svc"
                fi
            elif [ -f "$PID_DIR/$local_name.pid" ]; then
                # Native services: only restart if PID file exists (died vs. intentionally stopped)
                log "💀 $local_name is down — restarting"
                restart_service "$svc"
            fi
        fi
    done
    sleep "$CHECK_INTERVAL"
done
