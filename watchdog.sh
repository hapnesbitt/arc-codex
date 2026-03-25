#!/bin/bash
# watchdog.sh v2.0 - Arc Codex Service Watchdog
# Checks all services every 60 seconds, restarts any that died.
# Kills orphan duplicate processes before restarting.
# Supports multiple stacks via STACK_NAME env var.
#
# Usage:
#   ./watchdog.sh                          # arc-codex stack (default)
#   STACK_NAME=huntaegis ./watchdog.sh     # huntaegis stack
#
# Managed by arc.sh — do not run directly in production.

# =============================================================================
# STACK CONFIGURATION
# =============================================================================

STACK_NAME="${STACK_NAME:-arc-codex}"

if [ "$STACK_NAME" = "huntaegis" ]; then
    ITC_ROOT="/home/www/huntaegis_stack"
    COMPOSE_PROJECT="huntaegis"
    DOCKER_FRONTEND_NAME="huntaegis-frontend"
    SERVICES=(
        "gunicorn|$ITC_ROOT/backend|./gunicorn_arc.sh|true|5006"
        "scribe|$ITC_ROOT/backend|python3 scribe.py|true|"
        "manual_publisher|$ITC_ROOT/backend|python3 manual_publisher.py|true|"
        "stream_consumer|$ITC_ROOT/backend|python3 stream_consumer.py|true|"
        "analyzer|$ITC_ROOT/backend|python3 analyzer.py|true|"
        "mailer|$ITC_ROOT/backend|python3 mailer.py|true|"
        "frontend|$ITC_ROOT|docker|false|3002"
    )
else
    # arc-codex (default)
    ITC_ROOT="/home/www/arc_stack"
    COMPOSE_PROJECT="arc-codex"
    DOCKER_FRONTEND_NAME="arc-frontend"
    SERVICES=(
        "gunicorn|$ITC_ROOT/backend|./gunicorn_arc.sh|true|5005"
        "scribe|$ITC_ROOT/backend|python3 scribe.py|true|"
        "manual_publisher|$ITC_ROOT/backend|python3 manual_publisher.py|true|"
        "stream_consumer|$ITC_ROOT/backend|python3 stream_consumer.py|true|"
        "analyzer|$ITC_ROOT/backend|python3 analyzer.py|true|"
        "mailer|$ITC_ROOT/backend|python3 mailer.py|true|"
        "bluesky_poster|$ITC_ROOT/backend|python3 bluesky_poster.py|true|"
        "mastodon_poster|$ITC_ROOT/backend|python3 mastodon_poster.py|true|"
        "character_builder|$ITC_ROOT/backend|python3 character_builder.py|true|"
        "corpus_exporter|$ITC_ROOT/backend|python3 corpus_exporter.py|true|9101"
        "caddy_exporter|$ITC_ROOT/backend|python3 caddy_exporter.py|true|9102"
        "frontend|$ITC_ROOT|docker|false|3000"
    )
fi

PID_DIR="$ITC_ROOT/pids"
LOG_DIR="$ITC_ROOT/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
BACKEND_DIR="$ITC_ROOT/backend"
VENV="$BACKEND_DIR/venv/bin/activate"
COMPOSE_FILE="$ITC_ROOT/docker-compose.yml"
CHECK_INTERVAL=60

export PATH="/home/ross/.nvm/versions/node/v22.16.0/bin:$PATH"

# =============================================================================
# HELPERS
# =============================================================================

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WATCHDOG:$STACK_NAME] - $1" >> "$WATCHDOG_LOG"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [WATCHDOG:$STACK_NAME] - $1"
}

is_running() {
    local name="$1"
    if [ "$name" = "frontend" ]; then
        docker ps --filter "name=$DOCKER_FRONTEND_NAME" --filter "status=running" -q 2>/dev/null | grep -q .
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

kill_orphans() {
    # Kill any duplicate processes for this service that aren't the registered PID
    local name="$1"
    local cmd_fragment="$2"
    local pidfile="$PID_DIR/$name.pid"
    local registered_pid=""
    [ -f "$pidfile" ] && registered_pid=$(cat "$pidfile")

    # Find all PIDs matching the command fragment
    local all_pids
    all_pids=$(pgrep -f "$cmd_fragment" 2>/dev/null)
    if [ -z "$all_pids" ]; then
        return
    fi

    local orphan_count=0
    while IFS= read -r pid; do
        # Skip the registered PID and the watchdog itself
        if [ "$pid" = "$registered_pid" ] || [ "$pid" = "$$" ]; then
            continue
        fi
        # Only kill processes running from THIS stack's backend dir
        local proc_cwd
        proc_cwd=$(readlink /proc/$pid/cwd 2>/dev/null)
        [ "$proc_cwd" != "$BACKEND_DIR" ] && continue
        log "🧹 Killing orphan $name process (pid $pid)"
        kill "$pid" 2>/dev/null
        sleep 1
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
        orphan_count=$((orphan_count + 1))
    done <<< "$all_pids"

    [ $orphan_count -gt 0 ] && log "🧹 Killed $orphan_count orphan(s) for $name"
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
            log "✅ $name recovered (docker $DOCKER_FRONTEND_NAME)"
        else
            log "❌ $name container failed to restart — manual intervention needed"
        fi
        return
    fi

    # Kill any orphan processes before restarting
    kill_orphans "$name" "$cmd"

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

# Periodic orphan sweep — runs every 5 minutes independently of crash detection
orphan_sweep() {
    local last_sweep=0
    local sweep_interval=300  # 5 minutes

    while true; do
        sleep "$sweep_interval"
        log "🔍 Orphan sweep..."
        for svc in "${SERVICES[@]}"; do
            local name cmd
            name="${svc%%|*}"
            IFS='|' read -r _ _ cmd _ _ <<< "$svc"
            [ "$cmd" = "docker" ] && continue
            kill_orphans "$name" "$cmd"
        done
    done
}

# =============================================================================
# MAIN LOOP
# =============================================================================

log "🐕 Watchdog v2.0 started — stack: $STACK_NAME (checking every ${CHECK_INTERVAL}s)"

# Start orphan sweep in background
orphan_sweep &
SWEEP_PID=$!

trap "kill $SWEEP_PID 2>/dev/null; log '👋 Watchdog stopped'" EXIT

while true; do
    for svc in "${SERVICES[@]}"; do
        local_name="${svc%%|*}"
        IFS='|' read -r _ _ local_cmd _ _ <<< "$svc"
        if ! is_running "$local_name"; then
            if [ "$local_cmd" = "docker" ]; then
                if docker compose -f "$COMPOSE_FILE" ps --services 2>/dev/null | grep -q "^$local_name$"; then
                    log "💀 $local_name container is down — restarting"
                    restart_service "$svc"
                fi
            elif [ -f "$PID_DIR/$local_name.pid" ]; then
                log "💀 $local_name is down — restarting"
                restart_service "$svc"
            fi
        fi
    done
    sleep "$CHECK_INTERVAL"
done
