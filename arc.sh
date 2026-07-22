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

LOG_MAX_DAYS=9
LOG_MAX_SIZE_MB=50

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
    "watchdog|$ITC_ROOT|./watchdog.sh|false|"
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
        echo "  ⏭️  $name already running"
        return
    fi
    echo "  🚀 Starting $name..."
    free_port "$port"

    # Docker-managed services
    if [ "$cmd" = "docker" ]; then
        docker compose -f "$COMPOSE_FILE" up -d --no-deps "$name" >> "$LOG_DIR/$name.log" 2>&1
        sleep 6
        if docker ps --filter "name=arc-$name" --filter "status=running" -q | grep -q .; then
            echo "    ✅ $name up (docker container arc-$name)"
        else
            echo "    ❌ $name container failed — check $LOG_DIR/$name.log"
        fi
        return
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
    fi
}

stop_service() {
    local name dir cmd use_venv port
    IFS='|' read -r name dir cmd use_venv port <<< "$1"
    local pidfile="$PID_DIR/$name.pid"

    # Docker-managed services
    if [ "$cmd" = "docker" ]; then
        echo "  🛑 Stopping $name (docker)..."
        docker compose -f "$COMPOSE_FILE" stop "$name" >> "$LOG_DIR/$name.log" 2>&1
        echo "    ✅ $name stopped"
        return
    fi

    # Always sweep orphans first — before is_running check
    pkill -f "$dir.*python3 $cmd" 2>/dev/null || true
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
    # Kill orphaned processes from this specific stack directory
    pgrep -f "cd '$dir'.*$cmd\|$dir.*$cmd" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    free_port "$port"
    rm -f "$pidfile"
    echo "    ✅ $name stopped"
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
        # Hold off the watchdog while the stop→start gap is open, so its
        # 60s check can't race us and spawn an untracked duplicate.
        touch "$PID_DIR/watchdog.hold"
        stop_service "$svc"
        sleep 1
        start_service "$svc"
        rm -f "$PID_DIR/watchdog.hold"
    else
        cmd_stop
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
    docker compose -f "$COMPOSE_FILE" build $build_args frontend 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Build complete."
        echo "  🔄 Starting new frontend container..."
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
    grep -riE "error|failed|exception" "$LOG_DIR"/*.log 2>/dev/null | tail -n 5 \
        || echo "   ✅ No critical errors found."
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
    cmd_stop
    echo "🗜️  Archiving code and config..."
    # Scraped hero images are large (grew the warm tar to ~2 GB) and fully
    # reproducible on re-scrape; exclude them unless the cfg opts in. Default
    # (flag absent) is to exclude.
    local SCRAPED_EXCLUDE="--exclude=./frontend/public/uploads/scraped"
    [ "$(grep -oP '^include_scraped_images\s*=\s*\K(true|false)' "$ITC_ROOT/arc.cfg" 2>/dev/null)" = "true" ] \
        && SCRAPED_EXCLUDE=""
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
        -C "$ITC_ROOT" .
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
# BACKUP — COLD (big drive, full snapshot, stack stays up, keep 30)
# For: disaster recovery. Stack code + config PLUS the data layer:
#   data_layer/redis-arc.rdb    — consistent RDB via redis-cli --rdb
#                                 (streams a point-in-time snapshot over the
#                                 socket; /var/lib/redis is root-only, and
#                                 --rdb can never capture a mid-write file)
#   data_layer/solr-snapshot/   — Solr replication-handler backup (consistent
#                                 committed-segment snapshot; raw index-dir
#                                 copy can race merges). Staged under
#                                 SOLR_HOME because solr.allowPaths restricts
#                                 backup locations; moved into the archive.
#   data_layer/library.db       — SQLite online .backup (safe with readers)
# Stack does NOT stop. backend/.env rides in the stack tar (known R9 issue —
# encrypted secret store is a separate fix; do not half-solve it here).
# Cron: 0 2 * * 0 /home/www/arc_stack/arc.sh backup-cold
# ==============================================================================
cmd_backup_cold() {
    local DATE=$(date +%Y-%m-%d_%H%M)
    mkdir -p "$COLD_BACKUP_DIR"
    local FILE="$COLD_BACKUP_DIR/arc_cold_$DATE.tar.gz"
    local STAGING="$COLD_BACKUP_DIR/.staging_$DATE"
    local SOLR_BK_HOME="/home/ross/solr-9.9.0/server/solr/backups"
    mkdir -p "$STAGING/data_layer" "$SOLR_BK_HOME"
    echo "🧊 Cold archive backup (data layer + stack)..."

    # --- Redis: consistent point-in-time RDB over the socket ---
    if redis-cli --no-auth-warning -a "$REDIS_PASSWORD" --rdb "$STAGING/data_layer/redis-arc.rdb" &>/dev/null \
        && [ -s "$STAGING/data_layer/redis-arc.rdb" ]; then
        echo "   ✅ Redis RDB captured ($(du -sh "$STAGING/data_layer/redis-arc.rdb" | cut -f1))"
    else
        echo "   ⚠️  Redis RDB capture FAILED — archive will lack Redis data"
    fi

    # --- Solr: commit, then replication-handler snapshot ---
    curl -s "http://localhost:8983/solr/feeds/update?commit=true" >/dev/null 2>&1
    rm -rf "$SOLR_BK_HOME/snapshot.cold_$DATE"
    local solr_bk=$(curl -s "http://localhost:8983/solr/feeds/replication?command=backup&location=$SOLR_BK_HOME&name=cold_$DATE&wt=json")
    if echo "$solr_bk" | grep -q '"OK"'; then
        # Backup is async — poll until the snapshot dir size is stable
        local prev=0 size=0
        for i in $(seq 1 30); do
            sleep 2
            size=$(du -sb "$SOLR_BK_HOME/snapshot.cold_$DATE" 2>/dev/null | cut -f1)
            [ -n "$size" ] && [ "$size" -gt 0 ] && [ "$size" = "$prev" ] && break
            prev="$size"
        done
        if [ -d "$SOLR_BK_HOME/snapshot.cold_$DATE" ]; then
            mv "$SOLR_BK_HOME/snapshot.cold_$DATE" "$STAGING/data_layer/solr-snapshot"
            echo "   ✅ Solr snapshot captured ($(du -sh "$STAGING/data_layer/solr-snapshot" | cut -f1))"
        else
            echo "   ⚠️  Solr snapshot never appeared — archive will lack Solr data"
        fi
    else
        echo "   ⚠️  Solr backup command failed — archive will lack Solr data"
    fi

    # --- SQLite library: online backup (consistent with concurrent readers) ---
    if [ -f /mnt/arcdata/library.db ]; then
        if sqlite3 /mnt/arcdata/library.db ".backup '$STAGING/data_layer/library.db'" 2>/dev/null; then
            echo "   ✅ library.db captured ($(du -sh "$STAGING/data_layer/library.db" | cut -f1))"
        else
            echo "   ⚠️  library.db backup FAILED — archive will lack the library"
        fi
    fi

    echo "🗜️  Archiving stack + data layer (this may take a while)..."
    local PARTIAL="$FILE.partial"
    tar -zcf "$PARTIAL" \
        --exclude="./frontend/node_modules" \
        --exclude="./backend/venv" \
        --exclude="./backups" \
        --exclude="./logs" \
        --exclude="./pids" \
        --exclude="*.log" \
        --exclude="*.log.gz" \
        --exclude="./upload/completed" \
        --exclude="./upload/failed" \
        -C "$ITC_ROOT" . \
        -C "$STAGING" data_layer
    local tar_rc=$?

    # --- Verification gate. The .sha256 sidecar is the eligibility token the
    # off-host pull job keys on (Codex task-7): nothing without a sidecar ever
    # ships, and nothing gets a sidecar without passing every check here.
    local fail=""
    [ $tar_rc -eq 0 ] || fail="tar exit $tar_rc"
    if [ -z "$fail" ] && ! redis-check-rdb "$STAGING/data_layer/redis-arc.rdb" >/dev/null 2>&1; then
        fail="redis-check-rdb rejected staged RDB"
    fi
    if [ -z "$fail" ] && ! gzip -t "$PARTIAL" 2>/dev/null; then
        fail="gzip -t integrity check"
    fi
    if [ -z "$fail" ]; then
        local required="./backend/main.py ./arc.sh data_layer/redis-arc.rdb data_layer/solr-snapshot/"
        [ -f /mnt/arcdata/library.db ] && required="$required data_layer/library.db"
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
    cmd_stop

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
VALID_SERVICES="gunicorn|scribe|manual_publisher|stream_consumer|analyzer|mailer|bluesky_poster|mastodon_poster|facebook_poster|character_builder|quiz_generator|frontend|watchdog|corpus_exporter|caddy_exporter"

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
        echo "  $0 build --clean   # Force clear webpack cache before build"
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
