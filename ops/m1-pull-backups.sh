#!/bin/bash
# ==============================================================================
# m1-pull-backups.sh — off-host cold-archive pull, Resolute → M1
#
# THIS SCRIPT RUNS ON THE BACKUP DESTINATION HOST, NOT ON RESOLUTE. The host is
# parameterized (BKPULL_HOST, below): Spectre is primary once reimaged, the M1
# (192.168.1.185) secondary. It lives in this repo so it is version-controlled
# and rides in the cold archive; deploy it to whichever host will pull, e.g.
#     scp ops/m1-pull-backups.sh rossnesbitt@<dest-host>:~/ops/
#
# PULL, NOT PUSH. The M1 fetches from a restricted read-only account on
# Resolute (bkpull, command-forced through `rrsync -ro`). Resolute holds no
# credential to the M1, so a compromised Resolute cannot reach out and erase
# its own off-host backups. Mirrors the Prediger pattern in reverse.
# Do NOT reuse id_ed25519_pt — that key is scoped to Prediger ops.
#
# ELIGIBILITY: only archives with a matching .sha256 sidecar are fetched.
# Anything with a .partial, no sidecar, or a failed local verification is
# skipped. See arc_stack/ops/RUNBOOK.md 2026-07-23 for why some sidecars are
# gate-issued and three are backfilled.
#
# NO ENCRYPTION (decision 2026-07-23). Cold archives embed backend/.env, so
# this widens that exposure from one host to two. Accepted ONLY because the
# M1 is Ross-controlled, FileVault'd, and on the LAN. REVISIT IMMEDIATELY if
# the destination ever stops being Ross-controlled — cloud, offsite, or
# anyone else's hardware. The real fix is R9 (encrypted secret store).
#
# THE M1 IS A LAPTOP AND SLEEPS. Built for that, not around it: `caffeinate -s`
# holds it awake, launchd runs a missed schedule at next wake, and the dead-man
# alert is the PRIMARY freshness signal — "no news" here is otherwise
# indistinguishable from "lid shut for a week".
#
# Exit codes: 0 ok · 1 rsync/ssh failed · 2 STALE · 3 capacity floor
#             4 arrival verification failed · 5 preflight failed
# Grep the log for "R-OFFSITE ALERT".
#
# ------------------------------------------------------------------------------
# v2 (2026-07-23), after the first live run failed with a MISLEADING error.
# It reported "nothing eligible on source — every archive lacks a sidecar?" when
# the sidecars were fine and permissions were fine. Two defects, both mine:
#
#   1. `listing=$(rsync ... 2>/dev/null | awk ...) || alert` — the `||` tests the
#      PIPELINE's status, which is awk's, and awk succeeds even when rsync dies.
#      So the failure branch could never fire. Compounded by `2>/dev/null`
#      throwing away the one message that would have explained anything.
#   2. Enumeration parsed `--list-only`'s COLUMN layout. That is GNU-rsync
#      specific; macOS ships either rsync 2.6.9 or openrsync, both of which
#      differ. Portability landmine.
#
# v2 fixes the class, not just the instance:
#   * Nothing is silenced. rsync stderr is captured and echoed on failure, and
#     status comes from PIPESTATUS/direct exit, never from a downstream pipe.
#   * Eligibility no longer parses ANY listing output. Sidecars are 98 bytes, so
#     we fetch the sidecars first and derive the eligible set from which ones
#     arrive. Format-independent by construction.
#   * Ordering comes from the date-stamped FILENAME, not stat/mtime — no
#     GNU/BSD `stat` divergence.
#   * Budget selection happens BEFORE transfer, so we no longer pull ~27 GB of
#     arc archives just to delete 6.5 GB of them seconds later.
#   * Preflight fails LOUDLY on an unusable rsync instead of degrading to
#     silence.
#
# ------------------------------------------------------------------------------
# v3 (2026-08-05), after three archives sat with NO valid offsite copy for two
# weeks while the job dutifully alerted every single day. Not a transfer fault:
# the M1 copies were byte-exact TRUNCATED PREFIXES of intact originals, so three
# interrupted fetches (a laptop that sleeps — by design) became permanent.
#
# The trap was three mechanisms agreeing:
#   1. Bare `--partial` parks incomplete data at the FINAL filename.
#   2. `fetch_one` tested `[ -f ]`, so that stub read as "have" forever, and the
#      capacity gate used the same test, so it budgeted 0 bytes to repair it.
#   3. A verification failure left the file exactly where it was, to be
#      re-verified and re-failed on every subsequent run.
# Each is defensible alone. Together they made a recoverable interruption
# permanent, and made the alert unable to distinguish "retrying" from "stuck".
#
# v3 breaks all three:
#   * --partial-dir=.rsync-partial — incomplete data never takes the final name.
#   * have_complete() compares local size to source size, and BOTH the fetch step
#     and the capacity gate call it. One helper, so they cannot drift apart.
#   * A checksum mismatch now quarantines the file so the next run re-fetches it.
#     Deliberately NOT for sha-passes-but-structurally-broken: that indicts the
#     original, and re-fetching it forever would be this same bug mirrored.
#
# Standing lesson: a self-healing job must be able to say "I cannot fix this".
# Every failure here alerted correctly and none of them could clear itself.
# ==============================================================================
set -u

# Source host: default to Resolute's STATIC IP, not `resolute.lan`. That mDNS/hosts
# name resolves only on the M1, so the .lan default silently failed the moment this
# was deployed anywhere else (Spectre) — the preflight SSH check below dies with
# "could not resolve". The IP resolves LAN-wide. Override BKPULL_HOST to retarget
# (e.g. a rebuilt Resolute); the account is fixed by the rrsync forced-command setup.
BKPULL_USER="${BKPULL_USER:-bkpull}"
BKPULL_HOST="${BKPULL_HOST:-192.168.1.198}"
SRC_HOST="${BKPULL_USER}@${BKPULL_HOST}"
KEY="$HOME/.ssh/id_ed25519_resolute_pull"
DEST="$HOME/offsite/resolute"
LOG_TAG="R-OFFSITE"

# --- Retention: BYTE BUDGET, not a count. -------------------------------------
# Arc archives grew +10.1% in 12 days (6.49→7.15 GB, ≈1.65 GB/month). A fixed
# "keep 3" would silently overflow this disk within ~6 months. A byte budget
# degrades gracefully: as archives grow, the retained COUNT drops. That degrade
# is INTENDED — logged and exported as a metric, never silent. Always >=1 per
# stack.
ARC_BUDGET_BYTES=$((22 * 1000 * 1000 * 1000))
HUNT_BUDGET_BYTES=$((8 * 1000 * 1000 * 1000))
FLOOR_BYTES=$((10 * 1000 * 1000 * 1000))
MAX_AGE_HOURS=192                                  # 8d: weekly cron + laptop slack

TEXTFILE_DIR="$HOME/.node_exporter/textfile"
PROM="$TEXTFILE_DIR/offsite_backup.prom"
ERR=$(mktemp "${TMPDIR:-/tmp}/offsite_err.XXXXXX")

log()   { echo "[$(date '+%F %T')] $*"; }
alert() { echo "[$(date '+%F %T')] $LOG_TAG ALERT: $*"; }

# Show whatever rsync actually said. The v1 bug was throwing this away.
show_err() { [ -s "$ERR" ] && sed 's/^/      rsync: /' "$ERR"; : > "$ERR"; }

finish() {
    local code=$1 age=$2 arc_n=$3 hunt_n=$4 free=$5 verified=$6 degraded=$7
    rm -f "$ERR"
    if [ -d "$TEXTFILE_DIR" ]; then
        local tmp="$PROM.tmp"
        {
            echo '# HELP offsite_backup_last_pull_timestamp Unix time this job last ran (any outcome).'
            echo '# TYPE offsite_backup_last_pull_timestamp gauge'
            echo "offsite_backup_last_pull_timestamp $(date +%s)"
            echo '# HELP offsite_backup_newest_archive_age_seconds Age of newest archive held here; -1 unknown.'
            echo '# TYPE offsite_backup_newest_archive_age_seconds gauge'
            echo "offsite_backup_newest_archive_age_seconds $age"
            echo '# HELP offsite_backup_archives_held Archives currently retained, by stack.'
            echo '# TYPE offsite_backup_archives_held gauge'
            echo "offsite_backup_archives_held{stack=\"arc\"} $arc_n"
            echo "offsite_backup_archives_held{stack=\"huntaegis\"} $hunt_n"
            echo '# HELP offsite_backup_retention_degraded 1 if the byte budget holds fewer than nominal 3 arc / 4 hunt copies.'
            echo '# TYPE offsite_backup_retention_degraded gauge'
            echo "offsite_backup_retention_degraded $degraded"
            echo '# HELP offsite_backup_dest_free_bytes Free space on the destination volume.'
            echo '# TYPE offsite_backup_dest_free_bytes gauge'
            echo "offsite_backup_dest_free_bytes $free"
            echo '# HELP offsite_backup_verified_total Archives that passed full arrival verification this run.'
            echo '# TYPE offsite_backup_verified_total gauge'
            echo "offsite_backup_verified_total $verified"
            echo '# HELP offsite_backup_pull_exit_code 0 ok, 1 rsync, 2 stale, 3 capacity, 4 verify, 5 preflight.'
            echo '# TYPE offsite_backup_pull_exit_code gauge'
            echo "offsite_backup_pull_exit_code $code"
        } > "$tmp" && chmod 644 "$tmp" && mv "$tmp" "$PROM"
    fi
    exit "$code"
}

free_bytes() { df -k "$DEST" | awk 'NR==2 {print $4 * 1024}'; }

SSH="ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=15"

mkdir -p "$DEST/backups/huntaegis" "$DEST/backups/statics" "$TEXTFILE_DIR"

# ==============================================================================
# 0. PREFLIGHT — fail loudly, never silently.
# ==============================================================================
log "pull starting → $DEST"

rsync_ver=$(rsync --version 2>/dev/null | head -1)
if [ -z "$rsync_ver" ]; then
    alert "no usable rsync on PATH"; finish 5 -1 0 0 "$(free_bytes)" 0 0
fi
log "  local rsync: $rsync_ver"
case "$rsync_ver" in
    *openrsync*)
        alert "this is openrsync (macOS default), not GNU rsync."
        alert "  It does not support the option set this script relies on."
        alert "  Fix: brew install rsync   (then ensure /opt/homebrew/bin precedes /usr/bin in PATH)"
        finish 5 -1 0 0 "$(free_bytes)" 0 0 ;;
esac
ver_num=$(printf '%s\n' "$rsync_ver" | sed -n 's/.*version \([0-9][0-9.]*\).*/\1/p')
ver_major=${ver_num%%.*}
if [ -z "$ver_major" ] || [ "$ver_major" -lt 3 ] 2>/dev/null; then
    alert "rsync $ver_num is too old (need >= 3.1). macOS ships 2.6.9; brew install rsync."
    finish 5 -1 0 0 "$(free_bytes)" 0 0
fi

if ! $SSH -o ConnectTimeout=10 "$SRC_HOST" true 2>"$ERR"; then
    # The forced command means `true` is never actually run — rrsync rejects a
    # non-rsync command. That rejection still proves auth works, so treat only
    # a genuine connection/auth failure as fatal.
    if grep -qiE 'permission denied|connection refused|could not resolve|timed out|no route' "$ERR"; then
        alert "cannot reach $SRC_HOST"; show_err
        finish 1 -1 0 0 "$(free_bytes)" 0 0
    fi
    log "  ssh reachable (forced command rejected a non-rsync request, as expected)"
fi
: > "$ERR"

# ==============================================================================
# 1. ELIGIBILITY — derived from which SIDECARS arrive. No listing parsing.
#    Sidecars are 98 bytes each, so this costs nothing and is immune to
#    rsync-flavour output differences. An archive with no sidecar simply has
#    no entry here and is never considered.
# ==============================================================================
log "fetching sidecars (eligibility tokens)..."
if ! rsync -a --include='*/' --include='*.sha256' --exclude='*' \
        -e "$SSH" "$SRC_HOST:/" "$DEST/backups/" 2>"$ERR"; then
    alert "sidecar fetch FAILED — this is the real error, not 'no sidecars':"
    show_err
    finish 1 -1 0 0 "$(free_bytes)" 0 0
fi

# Newest-first ordering comes from the DATE-STAMPED FILENAME (arc_cold_YYYY-MM-DD_HHMM),
# not from stat/mtime — avoids GNU vs BSD `stat` divergence entirely.
arc_elig=$(cd "$DEST/backups" && ls -1 arc_cold_*.tar.gz.sha256 2>/dev/null | sed 's/\.sha256$//' | sort -r)
hunt_elig=$(cd "$DEST/backups/huntaegis" && ls -1 huntaegis_cold_*.tar.gz.sha256 2>/dev/null | sed 's/\.sha256$//' | sort -r)

n_arc_elig=$(printf '%s' "$arc_elig" | grep -c . || true)
n_hunt_elig=$(printf '%s' "$hunt_elig" | grep -c . || true)
log "  eligible: $n_arc_elig arc, $n_hunt_elig huntaegis"

if [ "$n_arc_elig" -eq 0 ] && [ "$n_hunt_elig" -eq 0 ]; then
    alert "no sidecars present on source — nothing is eligible to ship."
    alert "  Check on Resolute:  ls -l /mnt/arcdata/backups/*.sha256"
    alert "  and that bkpull can read them:  sudo -u bkpull ls -l /mnt/arcdata/backups/"
    finish 2 -1 0 0 "$(free_bytes)" 0 0
fi

# ==============================================================================
# 2. SELECT within budget BEFORE transferring. v1 pulled everything eligible and
#    then deleted the overflow — ~6.5 GB of wasted LAN transfer per run.
# ==============================================================================
remote_size() {   # $1 = path relative to the rrsync root. ALWAYS prints an integer.
    local out sz
    out=$(rsync -n --stats -e "$SSH" "$SRC_HOST:/$1" "$DEST/backups/" 2>"$ERR") || { show_err; echo 0; return; }
    sz=$(printf '%s\n' "$out" | sed -n 's/^Total file size: \([0-9,]*\) bytes.*/\1/p' | tr -d ',' | head -1)
    # Never emit empty: callers do arithmetic on this, and `$(( n +  ))` is a
    # hard syntax error, not a zero.
    case "$sz" in ''|*[!0-9]*) echo 0 ;; *) echo "$sz" ;; esac
}

# Is the local copy actually the whole archive? A bare `[ -f ]` says only that a
# NAME exists, and with plain --partial an interrupted transfer left its stub at
# exactly that name — so "have" was satisfied forever by a 4%-complete file that
# was never re-fetched and failed verification on every run for two weeks
# (2026-07-21/23 archives; see RUNBOOK). Size equality against the source is what
# makes the answer honest; the sha256 in section 5 is what makes it correct.
#
# Unknown remote size (0) deliberately returns "not complete": re-fetching a good
# file is a cheap no-op for rsync, whereas skipping a bad one is what caused this.
have_complete() {   # $1 = rel path from rrsync root, $2 = local dir → 0 if whole
    local rel="$1" dst="$2" base local_sz remote_sz
    base=$(basename "$rel")
    [ -f "$dst/$base" ] || return 1
    local_sz=$(stat -f%z "$dst/$base" 2>/dev/null || stat -c%s "$dst/$base" 2>/dev/null)
    case "$local_sz" in ''|*[!0-9]*) return 1 ;; esac
    remote_sz=$(remote_size "$rel")
    [ "$remote_sz" -gt 0 ] 2>/dev/null || return 1
    [ "$local_sz" = "$remote_sz" ]
}

select_within_budget() {   # $1=list  $2=budget  $3=subdir-prefix  → prints chosen
    local used=0 n=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        local sz; sz=$(remote_size "$3$f")
        [ -n "$sz" ] && [ "$sz" -gt 0 ] 2>/dev/null || sz=0
        if [ $n -eq 0 ] || { [ "$sz" -gt 0 ] && [ $(( used + sz )) -le "$2" ]; }; then
            used=$(( used + sz )); n=$(( n + 1 )); echo "$f"
        else
            break     # contiguous newest-N; everything older stops here
        fi
    done <<EOF
$1
EOF
}

arc_sel=$(select_within_budget "$arc_elig" "$ARC_BUDGET_BYTES" "")
hunt_sel=$(select_within_budget "$hunt_elig" "$HUNT_BUDGET_BYTES" "huntaegis/")
n_arc=$(printf '%s' "$arc_sel" | grep -c . || true)
n_hunt=$(printf '%s' "$hunt_sel" | grep -c . || true)
log "  selected within budget: $n_arc arc, $n_hunt huntaegis"

# ==============================================================================
# 3. CAPACITY GATE — floor read at runtime, never assumed.
# ==============================================================================
# Same completeness test as fetch_one — one helper, so the gate can never budget
# 0 bytes for an archive the transfer step is about to re-fetch in full.
need=0
for f in $arc_sel;  do have_complete "$f" "$DEST/backups" || need=$(( need + $(remote_size "$f") )); done
for f in $hunt_sel; do have_complete "huntaegis/$f" "$DEST/backups/huntaegis" || need=$(( need + $(remote_size "huntaegis/$f") )); done
free=$(free_bytes)
log "  need $need B, free $free B, floor $FLOOR_BYTES B"
if [ "$need" -gt 0 ] && [ $(( free - need )) -lt "$FLOOR_BYTES" ]; then
    alert "capacity floor would be breached — refusing transfer (no partial sets)"
    alert "  prune $DEST/backups or lower ARC_BUDGET_BYTES"
    finish 3 -1 0 0 "$free" 0 1
fi

# ==============================================================================
# 4. TRANSFER, one archive at a time, newest first.
#    Per-archive (rather than one giant rsync) means a mid-run failure still
#    leaves the NEWEST archives fully fetched and verified, instead of dying at
#    90% of a 27 GB blob with nothing usable.
#    caffeinate -s holds the laptop awake for the duration.
# ==============================================================================
CAFF=""; command -v caffeinate >/dev/null && CAFF="caffeinate -s"

# --partial-dir, never bare --partial. Interrupted data parks in .rsync-partial/
# under the destination and resumes from there next run; what it must never do is
# occupy the final filename, because every "do I have this?" test in this script
# keys on that name. The laptop sleeping mid-transfer is expected, not exceptional
# — that is the whole reason --partial is here — so the resume path has to be the
# safe one. rsync auto-excludes a relative partial-dir from the transfer itself.
fetch_one() {   # $1 = rel path from rrsync root, $2 = local dir
    local rel="$1" dst="$2" base; base=$(basename "$rel")
    if have_complete "$rel" "$dst"; then log "  have: $base"; return 0; fi
    [ -f "$dst/$base" ] && log "  incomplete, re-fetching: $base"
    log "  fetching: $base"
    if ! $CAFF rsync -a --partial --partial-dir=.rsync-partial \
            -e "$SSH" "$SRC_HOST:/$rel" "$dst/" 2>"$ERR"; then
        alert "transfer FAILED: $base"; show_err; return 1
    fi
    return 0
}

xfer_fail=0
for f in $arc_sel;  do fetch_one "$f" "$DEST/backups" || xfer_fail=1; done
for f in $hunt_sel; do fetch_one "huntaegis/$f" "$DEST/backups/huntaegis" || xfer_fail=1; done

# Statics: fetch only what is missing. The 8.11 GB corpus RDB is already here
# from Ross's manual scp — rsync skips it on size+mtime, so this costs nothing.
log "syncing statics (never pruned; existing copies are verified, not re-fetched)..."
if ! $CAFF rsync -a -e "$SSH" \
        --include='statics/' --include='statics/*' --include='SIDECAR-PROVENANCE.md' \
        --exclude='*' "$SRC_HOST:/" "$DEST/backups/" 2>"$ERR"; then
    alert "statics sync FAILED"; show_err; xfer_fail=1
fi

chmod -R go-rwx "$DEST" 2>/dev/null   # archives embed backend/.env

# ==============================================================================
# 5. ARRIVAL VERIFICATION — recompute here, compare to sidecar, then structure.
# ==============================================================================
verified=0; failed=0
TMP=$(mktemp -d "${TMPDIR:-/tmp}/offsite.XXXXXX")
trap 'rm -rf "$TMP"; rm -f "$ERR"' EXIT

sha_check() {   # portable: shasum on macOS, sha256sum on Linux
    local dir="$1" name="$2"
    if command -v shasum >/dev/null; then
        ( cd "$dir" && shasum -a 256 -c "$name.sha256" >/dev/null 2>&1 )
    else
        ( cd "$dir" && sha256sum -c "$name.sha256" >/dev/null 2>&1 )
    fi
}

# A failed archive that stays put is re-verified and re-failed forever while the
# fetch step keeps saying "have" — the exact deadlock this script sat in from
# 2026-07-23 to 2026-08-05. Move it aside so the next run re-fetches it.
#
# ONLY on checksum mismatch. A mismatch means the local bytes are wrong and a
# re-fetch is the fix. If the sha MATCHES and the file still fails gzip/tar/RDB,
# the ORIGINAL on Resolute is bad — re-fetching cannot help, and doing it anyway
# would burn 7 GB of LAN every run forever. That case stays put and stays loud.
#
# One quarantined copy per name (fixed suffix, overwritten): forensics survive,
# disk use stays bounded on a volume that has a capacity floor to respect.
QUARANTINE="$DEST/quarantine"
quarantine_bad() {   # $1 = full path to the bad archive
    local p="$1" b; b=$(basename "$p")
    mkdir -p "$QUARANTINE" 2>/dev/null
    if mv -f "$p" "$QUARANTINE/$b.bad" 2>/dev/null; then
        alert "  moved aside → quarantine/$b.bad (next run re-fetches)"
    else
        rm -f "$p" && alert "  unlinked (quarantine unavailable); next run re-fetches"
    fi
}

verify_one() {
    local path="$1" name dir; name=$(basename "$path"); dir=$(dirname "$path")
    sha_check "$dir" "$name" || {
        alert "checksum MISMATCH on arrival: $name"; quarantine_bad "$path"; return 1; }
    gzip -t "$path" 2>/dev/null   || { alert "gzip -t failed: $name"; return 1; }
    tar -tzf "$path" >/dev/null 2>&1 || { alert "tar -tzf failed: $name"; return 1; }
    local rdb
    rdb=$(tar -tzf "$path" 2>/dev/null | grep -m1 -E '^data_layer/redis-(arc|hnt)\.rdb$')
    [ -n "$rdb" ] || { alert "no embedded RDB in $name"; return 1; }
    tar -xzf "$path" -O "$rdb" > "$TMP/rdb" 2>/dev/null
    if command -v redis-check-rdb >/dev/null; then
        redis-check-rdb "$TMP/rdb" >/dev/null 2>&1 \
            || { alert "redis-check-rdb rejected embedded RDB: $name"; rm -f "$TMP/rdb"; return 1; }
    else
        log "  (redis-check-rdb absent — RDB structural check skipped; brew install redis)"
    fi
    rm -f "$TMP/rdb"
    log "  verified: $name"
    return 0
}

for p in "$DEST/backups"/arc_cold_*.tar.gz "$DEST/backups/huntaegis"/*.tar.gz; do
    [ -f "$p" ] || continue
    if verify_one "$p"; then verified=$((verified+1)); else failed=$((failed+1)); fi
done
for p in "$DEST/backups/statics"/*.rdb; do
    [ -f "$p" ] || continue
    if command -v redis-check-rdb >/dev/null; then
        redis-check-rdb "$p" >/dev/null 2>&1 \
            && log "  static ok: $(basename "$p")" \
            || { alert "static RDB failed check: $(basename "$p")"; failed=$((failed+1)); }
    fi
done

# ==============================================================================
# 6. PRUNE anything outside the selected set. Statics are NEVER pruned.
# ==============================================================================
degraded=0
prune_unselected() {   # $1=dir  $2=glob  $3=selected list
    local d="$1" g="$2" sel="$3"
    for p in "$d"/$g; do
        [ -f "$p" ] || continue
        local b; b=$(basename "$p")
        printf '%s\n' "$sel" | grep -qx "$b" && continue
        log "  retention: dropping $b (outside byte budget)"
        rm -f "$p" "$p.sha256"
    done
}
prune_unselected "$DEST/backups" 'arc_cold_*.tar.gz' "$arc_sel"
prune_unselected "$DEST/backups/huntaegis" 'huntaegis_cold_*.tar.gz' "$hunt_sel"

if [ "$n_arc" -lt 3 ] || [ "$n_hunt" -lt 4 ]; then
    degraded=1
    log "NOTE: retention degraded — holding $n_arc arc (nominal 3), $n_hunt hunt (nominal 4)."
    log "      This is the byte budget working as designed as archives grow."
fi

# ==============================================================================
# 7. FRESHNESS. A pull that happily syncs an aging set is false comfort.
# ==============================================================================
newest=$(ls -t "$DEST/backups"/arc_cold_*.tar.gz "$DEST/backups/huntaegis"/*.tar.gz 2>/dev/null | head -1)
if [ -z "$newest" ]; then
    alert "no archives present after sync"
    finish 2 -1 "$n_arc" "$n_hunt" "$(free_bytes)" "$verified" "$degraded"
fi
mt=$(stat -f%m "$newest" 2>/dev/null || stat -c%Y "$newest")
age=$(( $(date +%s) - mt ))

[ "$xfer_fail" -eq 0 ] || { alert "one or more transfers failed"
    finish 1 "$age" "$n_arc" "$n_hunt" "$(free_bytes)" "$verified" "$degraded"; }
[ "$failed" -eq 0 ] || { alert "$failed archive(s) failed arrival verification"
    finish 4 "$age" "$n_arc" "$n_hunt" "$(free_bytes)" "$verified" "$degraded"; }
if [ $(( age / 3600 )) -ge "$MAX_AGE_HOURS" ]; then
    alert "newest archive is $(( age / 3600 ))h old (>= ${MAX_AGE_HOURS}h) — backup-cold on Resolute may be dead"
    finish 2 "$age" "$n_arc" "$n_hunt" "$(free_bytes)" "$verified" "$degraded"
fi

log "ok: $n_arc arc + $n_hunt hunt archives, $verified verified, newest $(( age / 3600 ))h old, $(free_bytes) B free"
finish 0 "$age" "$n_arc" "$n_hunt" "$(free_bytes)" "$verified" "$degraded"
