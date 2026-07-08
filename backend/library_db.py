#!/usr/bin/env python3
"""
Arc Codex — library_db.py

SQLite storage for the Gutenberg library corpus. Replaces the former
library:* Redis namespace (2026-07-08 Redis OOM remediation — the ~12.7 GB
of book text was ~90% of Redis memory and drove the 2026-07-07 OOM kills).

The corpus is cold-archive data: written by a weekly cron
(library_fetcher.py, score_library.py), read by the /api/library/* reader
endpoints and the sitemap generator. It lives on the archive SSD.

Layout:
  works         — one row per Gutenberg work: metadata + readability scores
                  (columns mirror the old library:work:<id> hash fields;
                  score fields stay TEXT — '' means unscored/non-English,
                  matching the previous Redis string semantics)
  work_texts    — body text, separate table so metadata scans never touch
                  the multi-hundred-KB blobs
  shelves       — curated shelf metadata (old library:shelf:<slug>:meta)
  shelf_members — shelf membership (old library:shelf:<slug> sets)
  translations  — cached reader translations (old
                  library:work:<id>:translation:<lang>[:meta])

Concurrency: WAL mode; writers are the weekly crons and the occasional
translation-cache insert from Flask. Each caller opens a short-lived
connection via connect() / db().
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("LIBRARY_DB_PATH", "/mnt/arcdata/library.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    gutenberg_id        INTEGER PRIMARY KEY,
    title               TEXT NOT NULL DEFAULT '',
    author              TEXT NOT NULL DEFAULT 'Unknown',
    language            TEXT NOT NULL DEFAULT '',
    subjects            TEXT NOT NULL DEFAULT '[]',
    year_published      TEXT NOT NULL DEFAULT '',
    download_count      INTEGER NOT NULL DEFAULT 0,
    encoding            TEXT NOT NULL DEFAULT '',
    source_url          TEXT NOT NULL DEFAULT '',
    fetched_at          TEXT NOT NULL DEFAULT '',
    text_md5            TEXT NOT NULL DEFAULT '',
    chimera_score       TEXT NOT NULL DEFAULT '',
    reading_label       TEXT NOT NULL DEFAULT '',
    fk_grade            TEXT NOT NULL DEFAULT '',
    coleman_liau        TEXT NOT NULL DEFAULT '',
    smog                TEXT NOT NULL DEFAULT '',
    dale_chall          TEXT NOT NULL DEFAULT '',
    chimera_skip_reason TEXT NOT NULL DEFAULT '',
    scored_at           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_works_downloads ON works (download_count DESC);

CREATE TABLE IF NOT EXISTS work_texts (
    gutenberg_id INTEGER PRIMARY KEY REFERENCES works (gutenberg_id) ON DELETE CASCADE,
    text         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS shelves (
    slug                   TEXT PRIMARY KEY,
    name                   TEXT NOT NULL DEFAULT '',
    description            TEXT NOT NULL DEFAULT '',
    gutenberg_bookshelf_id TEXT NOT NULL DEFAULT '',
    fetched_at             TEXT NOT NULL DEFAULT '',
    book_count             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS shelf_members (
    slug         TEXT NOT NULL REFERENCES shelves (slug) ON DELETE CASCADE,
    gutenberg_id INTEGER NOT NULL,
    PRIMARY KEY (slug, gutenberg_id)
);
CREATE INDEX IF NOT EXISTS idx_shelf_members_work ON shelf_members (gutenberg_id);

CREATE TABLE IF NOT EXISTS translations (
    gutenberg_id  INTEGER NOT NULL REFERENCES works (gutenberg_id) ON DELETE CASCADE,
    lang          TEXT NOT NULL,
    body          TEXT NOT NULL DEFAULT '',
    is_preview    INTEGER NOT NULL DEFAULT 0,
    preview_chars INTEGER,
    created_at    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (gutenberg_id, lang)
);
"""

WORK_META_COLUMNS = [
    "gutenberg_id", "title", "author", "language", "subjects",
    "year_published", "download_count", "encoding", "source_url",
    "fetched_at", "text_md5", "chimera_score", "reading_label",
    "fk_grade", "coleman_liau", "smog", "dale_chall",
    "chimera_skip_reason", "scored_at",
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


@contextmanager
def db():
    """Short-lived connection with schema guaranteed. Commits on clean exit."""
    conn = connect()
    try:
        init_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Works
# ---------------------------------------------------------------------------

def get_work(conn: sqlite3.Connection, gid: int | str) -> dict | None:
    row = conn.execute(
        f"SELECT {', '.join(WORK_META_COLUMNS)} FROM works WHERE gutenberg_id = ?",
        (int(gid),),
    ).fetchone()
    return dict(row) if row else None


def get_text(conn: sqlite3.Connection, gid: int | str) -> str:
    row = conn.execute(
        "SELECT text FROM work_texts WHERE gutenberg_id = ?", (int(gid),)
    ).fetchone()
    return row["text"] if row else ""


def upsert_work(conn: sqlite3.Connection, gid: int | str, meta: dict, text: str) -> None:
    """Insert or refresh a fetched work. `meta` uses library_fetcher's dict
    shape. Preserves existing score columns on refresh (scores are managed
    by score_library.py, not the fetcher)."""
    conn.execute(
        """
        INSERT INTO works (gutenberg_id, title, author, language, subjects,
                           year_published, download_count, encoding,
                           source_url, fetched_at, text_md5)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (gutenberg_id) DO UPDATE SET
            title = excluded.title,
            author = excluded.author,
            language = excluded.language,
            subjects = excluded.subjects,
            year_published = excluded.year_published,
            download_count = excluded.download_count,
            encoding = excluded.encoding,
            source_url = excluded.source_url,
            fetched_at = excluded.fetched_at,
            text_md5 = excluded.text_md5
        """,
        (
            int(gid),
            meta.get("title", ""),
            meta.get("author", "Unknown"),
            meta.get("language", ""),
            json.dumps(meta.get("subjects", [])),
            meta.get("year_published", ""),
            int(meta.get("download_count", 0) or 0),
            meta.get("encoding", ""),
            meta.get("source_url", ""),
            meta.get("fetched_at", ""),
            meta.get("text_md5", ""),
        ),
    )
    conn.execute(
        """
        INSERT INTO work_texts (gutenberg_id, text) VALUES (?, ?)
        ON CONFLICT (gutenberg_id) DO UPDATE SET text = excluded.text
        """,
        (int(gid), text),
    )


def update_work_fields(conn: sqlite3.Connection, gid: int | str, fields: dict) -> None:
    """Update a subset of works columns (used by score_library.py)."""
    cols = [c for c in fields if c in WORK_META_COLUMNS and c != "gutenberg_id"]
    if not cols:
        return
    assignments = ", ".join(f"{c} = ?" for c in cols)
    conn.execute(
        f"UPDATE works SET {assignments} WHERE gutenberg_id = ?",
        [fields[c] for c in cols] + [int(gid)],
    )


def all_work_ids_by_downloads(conn: sqlite3.Connection) -> list[int]:
    return [
        row["gutenberg_id"]
        for row in conn.execute(
            "SELECT gutenberg_id FROM works ORDER BY download_count DESC, gutenberg_id"
        )
    ]


def iter_work_meta(conn: sqlite3.Connection, columns: list[str]):
    """Yield metadata rows for all works, most-downloaded first."""
    safe = [c for c in columns if c in WORK_META_COLUMNS]
    return conn.execute(
        f"SELECT {', '.join(safe)} FROM works ORDER BY download_count DESC, gutenberg_id"
    )


def delete_translations(conn: sqlite3.Connection, gid: int | str) -> int:
    cur = conn.execute("DELETE FROM translations WHERE gutenberg_id = ?", (int(gid),))
    return cur.rowcount


def prune_unreferenced_works(conn: sqlite3.Connection, max_works: int) -> int:
    """Hard bound on corpus size: keep every work referenced by a current
    shelf; above `max_works` total, drop the oldest-fetched unreferenced
    works until the bound holds. Texts and translations cascade."""
    total = conn.execute("SELECT COUNT(*) AS n FROM works").fetchone()["n"]
    if total <= max_works:
        return 0
    cur = conn.execute(
        """
        DELETE FROM works WHERE gutenberg_id IN (
            SELECT w.gutenberg_id FROM works w
            WHERE NOT EXISTS (
                SELECT 1 FROM shelf_members m WHERE m.gutenberg_id = w.gutenberg_id
            )
            ORDER BY w.fetched_at ASC
            LIMIT ?
        )
        """,
        (total - max_works,),
    )
    return cur.rowcount


# ---------------------------------------------------------------------------
# Shelves
# ---------------------------------------------------------------------------

def list_shelves(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT slug, name, description, gutenberg_bookshelf_id, "
            "fetched_at, book_count FROM shelves ORDER BY slug"
        )
    ]


def get_shelf(conn: sqlite3.Connection, slug: str) -> dict | None:
    row = conn.execute(
        "SELECT slug, name, description, gutenberg_bookshelf_id, "
        "fetched_at, book_count FROM shelves WHERE slug = ?",
        (slug,),
    ).fetchone()
    return dict(row) if row else None


def get_shelf_member_ids(conn: sqlite3.Connection, slug: str) -> list[int]:
    return [
        row["gutenberg_id"]
        for row in conn.execute(
            "SELECT gutenberg_id FROM shelf_members WHERE slug = ?", (slug,)
        )
    ]


def replace_shelf(conn: sqlite3.Connection, slug: str, meta: dict, member_ids: list[int]) -> None:
    """Rebuild a shelf's metadata + membership fresh (removed books drop out)."""
    conn.execute(
        """
        INSERT INTO shelves (slug, name, description, gutenberg_bookshelf_id,
                             fetched_at, book_count)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (slug) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            gutenberg_bookshelf_id = excluded.gutenberg_bookshelf_id,
            fetched_at = excluded.fetched_at,
            book_count = excluded.book_count
        """,
        (
            slug,
            meta.get("name", slug),
            meta.get("description", ""),
            str(meta.get("gutenberg_bookshelf_id", "")),
            meta.get("fetched_at", ""),
            int(meta.get("book_count", len(member_ids)) or 0),
        ),
    )
    conn.execute("DELETE FROM shelf_members WHERE slug = ?", (slug,))
    conn.executemany(
        "INSERT OR IGNORE INTO shelf_members (slug, gutenberg_id) VALUES (?, ?)",
        [(slug, int(g)) for g in member_ids],
    )


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

def get_translation(conn: sqlite3.Connection, gid: int | str, lang: str) -> dict | None:
    row = conn.execute(
        "SELECT body, is_preview, preview_chars FROM translations "
        "WHERE gutenberg_id = ? AND lang = ?",
        (int(gid), lang),
    ).fetchone()
    return dict(row) if row else None


def set_translation(
    conn: sqlite3.Connection,
    gid: int | str,
    lang: str,
    body: str,
    is_preview: bool,
    preview_chars: int | None,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO translations (gutenberg_id, lang, body, is_preview,
                                  preview_chars, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (gutenberg_id, lang) DO UPDATE SET
            body = excluded.body,
            is_preview = excluded.is_preview,
            preview_chars = excluded.preview_chars,
            created_at = excluded.created_at
        """,
        (int(gid), lang, body, 1 if is_preview else 0, preview_chars, created_at),
    )
