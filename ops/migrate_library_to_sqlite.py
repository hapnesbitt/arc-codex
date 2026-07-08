#!/usr/bin/env python3
"""
One-shot migration: library:* Redis namespace → /mnt/arcdata/library.db.

Part of the 2026-07-08 Redis OOM remediation. Reads every work hash, text
blob, translation cache, and shelf from Redis DB 0 and writes them to the
SQLite schema in backend/library_db.py. Purely additive — deletes nothing
from Redis; the purge is a separate manual step after verification.

Idempotent: re-running upserts the same rows.

Usage:
    cd /home/www/arc_stack/backend && source venv/bin/activate
    python3 ../ops/migrate_library_to_sqlite.py
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import redis
from dotenv import load_dotenv

import library_db

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env"))

WORK_HASH_RE = re.compile(r"^library:work:(\d+)$")
TRANSLATION_RE = re.compile(r"^library:work:(\d+):translation:([a-z-]+)$")

SCORE_FIELDS = (
    "chimera_score", "reading_label", "fk_grade", "coleman_liau",
    "smog", "dale_chall", "chimera_skip_reason", "scored_at",
)


def main() -> int:
    r = redis.Redis(decode_responses=True, password=os.environ["REDIS_PASSWORD"])
    r.ping()

    conn = library_db.connect()
    library_db.init_schema(conn)

    # --- Works + texts ---
    works = texts = 0
    for key in r.scan_iter(match="library:work:*", count=500):
        m = WORK_HASH_RE.match(key)
        if not m:
            continue
        gid = int(m.group(1))
        meta = r.hgetall(key)
        if not meta:
            continue
        text = r.get(f"{key}:text") or ""
        import json as _json
        try:
            subjects = _json.loads(meta.get("subjects", "[]"))
        except (ValueError, TypeError):
            subjects = []
        library_db.upsert_work(conn, gid, {
            "title":          meta.get("title", ""),
            "author":         meta.get("author", "Unknown"),
            "language":       meta.get("language", ""),
            "subjects":       subjects,
            "year_published": meta.get("year_published", ""),
            "download_count": meta.get("download_count", 0),
            "encoding":       meta.get("encoding", ""),
            "source_url":     meta.get("source_url", ""),
            "fetched_at":     meta.get("fetched_at", ""),
            "text_md5":       meta.get("text_md5", ""),
        }, text)
        score_fields = {f: meta[f] for f in SCORE_FIELDS if f in meta}
        if score_fields:
            library_db.update_work_fields(conn, gid, score_fields)
        works += 1
        if text:
            texts += 1
        if works % 200 == 0:
            conn.commit()
            print(f"  … {works} works migrated", flush=True)
    conn.commit()
    print(f"Works: {works} rows ({texts} with text)")

    # --- Translations ---
    tx = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for key in r.scan_iter(match="library:work:*:translation:*", count=500):
        m = TRANSLATION_RE.match(key)
        if not m:
            continue  # :meta keys handled alongside their body key
        gid, lang = int(m.group(1)), m.group(2)
        body = r.get(key)
        if body is None:
            continue
        tmeta = r.hgetall(f"{key}:meta") or {}
        try:
            preview_chars = int(tmeta.get("preview_chars") or 0) or None
        except (ValueError, TypeError):
            preview_chars = None
        library_db.set_translation(
            conn, gid, lang, body,
            is_preview=tmeta.get("is_preview") == "1",
            preview_chars=preview_chars,
            created_at=now_iso,
        )
        tx += 1
    conn.commit()
    print(f"Translations: {tx} rows")

    # --- Shelves ---
    shelves = 0
    for slug in sorted(r.smembers("library:shelves") or []):
        meta = r.hgetall(f"library:shelf:{slug}:meta") or {}
        member_ids = [int(g) for g in r.smembers(f"library:shelf:{slug}") or []]
        if not meta and not member_ids:
            continue
        library_db.replace_shelf(conn, slug, meta, member_ids)
        shelves += 1
    conn.commit()
    print(f"Shelves: {shelves}")

    # --- Summary counts for verification ---
    for table in ("works", "work_texts", "translations", "shelves", "shelf_members"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
