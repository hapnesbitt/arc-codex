#!/usr/bin/env python3
"""
One-shot migration: facebook/bluesky/mastodon/threads :posted SET → ZSET.

Part of the 2026-09-04 posted-set age-bounding fix (see ops/RUNBOOK.md).
Each :posted set was an unbounded SET of article ids with no way to prune
it by age — cleanup.py can now zremrangebyscore it (see
purge_stale_posted_entries / [retention].posted_set_days in arc.cfg), but
that needs a score per member, which a SET doesn't have.

Converts each key in place: reads every existing member, re-creates the key
as a ZSET with every member scored at the migration's own run time (`now`),
then deletes the old SET data as part of the same rename. Scoring existing
members at `now` rather than backdating them to their actual post time is
deliberate — the actual post time isn't recoverable from a SET member alone,
and starting the retention clock at migration time (rather than at some
guessed-backdate) guarantees no already-posted id is even close to eligible
for pruning immediately after this runs; each one gets the full
posted_set_days window from today.

Idempotent: re-running on an already-ZSET key is a no-op (TYPE check skips
it). Safe to run more than once.

Usage:
    cd /home/www/arc_stack/backend && source venv/bin/activate
    python3 ../ops/migrate_posted_sets_to_zset.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import redis
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env"))

POSTED_SETS = ["facebook:posted", "bluesky:posted", "mastodon:posted", "threads:posted"]


def migrate_one(r, key: str, now: float) -> str:
    key_type = r.type(key)

    if key_type == "none":
        return f"{key}: absent — nothing to migrate"

    if key_type == "zset":
        return f"{key}: already a ZSET ({r.zcard(key)} members) — skipped"

    if key_type != "set":
        return f"{key}: unexpected type {key_type!r} — skipped, needs a look"

    members = r.smembers(key)
    if not members:
        r.delete(key)
        return f"{key}: SET was empty — deleted, will be re-created as a ZSET on next write"

    pipe = r.pipeline()
    pipe.delete(key)
    for member in members:
        pipe.zadd(key, {member: now})
    pipe.execute()

    return f"{key}: migrated {len(members)} member(s), scored at {now:.0f} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC)"


def main():
    r = redis.Redis(decode_responses=True, password=os.environ["REDIS_PASSWORD"])
    r.ping()

    now = time.time()
    print(f"Migrating {len(POSTED_SETS)} posted-set(s), scoring existing members at now "
          f"({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now))} UTC) "
          f"so none is anywhere near the posted_set_days prune window yet.\n")

    for key in POSTED_SETS:
        print(migrate_one(r, key, now))


if __name__ == "__main__":
    main()
