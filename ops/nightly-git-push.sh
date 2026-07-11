#!/bin/bash
# Nightly git push safety net — pushes landed commits on both stacks.
#
# PUSH ONLY. This script must never run git add, git commit, git pull,
# or git rebase. Uncommitted work stays uncommitted; unpushed commits
# get pushed. A failed push (auth, diverged, network) is logged and the
# script moves on to the next stack — no retries, no prompts, no
# recovery attempts. Fixing a diverged branch is a human decision.
#
# Cron: 30 2 * * * (see ops/RUNBOOK.md). Log: arc_stack/logs/nightly_push.log

export GIT_TERMINAL_PROMPT=0   # fail instead of prompting for credentials

LOG=/home/www/arc_stack/logs/nightly_push.log
STACKS="/home/www/arc_stack /home/www/huntaegis_stack"

for repo in $STACKS; do
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $repo: push origin main" >> "$LOG"
    if git -C "$repo" push origin main >> "$LOG" 2>&1; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $repo: OK" >> "$LOG"
    else
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $repo: PUSH FAILED (exit $?) — continuing" >> "$LOG"
    fi
done
