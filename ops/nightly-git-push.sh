#!/bin/bash
# Nightly git push safety net — pushes landed commits on both stacks.
#
# PUSH ONLY. This script must never run git add, git commit, git pull,
# or git rebase. Uncommitted work stays uncommitted; unpushed commits
# get pushed. A failed push (auth, diverged, network) is logged and the
# script moves on to the next stack — no retries, no prompts, no
# recovery attempts. Fixing a diverged branch is a human decision.
#
# Pushes `origin HEAD` — whatever branch is actually checked out — not a
# hardcoded `origin main`. Fixed 2026-08-27: both stacks had been sitting
# on fix/translate-failure-visibility since ~Aug 15 (26 unpushed commits
# on Arc, 10+ on Hunt), and this script logged "Everything up-to-date ...
# OK" every night of that regardless, because it was pushing a `main` that
# genuinely was up to date while the branch with all the real work sat
# unpushed. Same shape as the digest logging "sent" on failure — a script
# reporting the health of the wrong thing reads as more reassuring than
# reporting nothing.
#
# `origin HEAD`, not `--all`: this is a safety net for whatever's actually
# being worked on, not a blanket publish of every local branch — a stray
# experimental or throwaway branch shouldn't go to the remote just because
# it happens to exist locally when cron fires.
#
# Every log line names the branch pushed, on purpose — a hardcoded "main"
# in the log was exactly what made twelve nights of the wrong branch look
# identical to twelve nights of the right one. Also reports commits moved
# (comparing the remote ref before the push, fetched fresh via ls-remote —
# not a possibly-stale local tracking ref) so "up to date, 0 commits" reads
# differently from "pushed 26 commits" instead of both just saying "OK".
#
# Cron: 30 2 * * * (see ops/RUNBOOK.md). Log: arc_stack/logs/nightly_push.log

export GIT_TERMINAL_PROMPT=0   # fail instead of prompting for credentials

LOG=/home/www/arc_stack/logs/nightly_push.log
STACKS="/home/www/arc_stack /home/www/huntaegis_stack /home/www/claude_horst /home/www/claude_stack /home/www/claude_stack_vid"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

for repo in $STACKS; do
    branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null)
    if [ -z "$branch" ] || [ "$branch" = "HEAD" ]; then
        echo "[$(ts)] $repo: detached HEAD — no branch to push, skipping" >> "$LOG"
        continue
    fi

    # Live query against the remote, not `origin/$branch` locally — that
    # tracking ref only updates on fetch, and could itself be stale enough
    # to mask exactly the kind of gap this fix exists to catch.
    before=$(git -C "$repo" ls-remote origin "refs/heads/$branch" 2>/dev/null | cut -f1)
    local_head=$(git -C "$repo" rev-parse HEAD)

    echo "[$(ts)] $repo: push origin HEAD (branch=$branch)" >> "$LOG"
    if git -C "$repo" push origin HEAD >> "$LOG" 2>&1; then
        if [ -z "$before" ]; then
            n=$(git -C "$repo" rev-list --count HEAD)
            echo "[$(ts)] $repo: OK — pushed NEW branch $branch ($n commits)" >> "$LOG"
        elif [ "$before" = "$local_head" ]; then
            echo "[$(ts)] $repo: OK — $branch already up to date (0 commits moved)" >> "$LOG"
        else
            n=$(git -C "$repo" rev-list --count "$before..$local_head" 2>/dev/null)
            echo "[$(ts)] $repo: OK — pushed $branch, ${n:-?} commit(s) moved ($before -> $local_head)" >> "$LOG"
        fi
    else
        echo "[$(ts)] $repo: PUSH FAILED (exit $?) on branch $branch — continuing" >> "$LOG"
    fi
done
