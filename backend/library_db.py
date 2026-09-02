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
from datetime import datetime, timezone

DB_PATH = os.environ.get("LIBRARY_DB_PATH", "/mnt/arcdata/library.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    gutenberg_id        INTEGER PRIMARY KEY,
    title               TEXT NOT NULL DEFAULT '',
    author              TEXT NOT NULL DEFAULT 'Unknown',
    language            TEXT NOT NULL DEFAULT '',
    subjects            TEXT NOT NULL DEFAULT '[]',
    -- Legacy name: this is Gutenberg's dcterms:issued YEAR, not the
    -- underlying work's original publication year.
    year_published      TEXT NOT NULL DEFAULT '',
    original_publication_year       INTEGER,
    original_publication_source     TEXT,
    original_publication_confidence REAL,
    original_publication_evidence   TEXT,
    original_publication_checked_at TEXT,
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
    "year_published", "original_publication_year",
    "original_publication_source", "original_publication_confidence",
    "original_publication_evidence", "original_publication_checked_at",
    "download_count", "encoding", "source_url",
    "fetched_at", "text_md5", "chimera_score", "reading_label",
    "fk_grade", "coleman_liau", "smog", "dale_chall",
    "chimera_skip_reason", "scored_at",
]

_WORKS_ADDITIVE_COLUMNS = {
    "original_publication_year": "INTEGER",
    "original_publication_source": "TEXT",
    "original_publication_confidence": "REAL",
    "original_publication_evidence": "TEXT",
    "original_publication_checked_at": "TEXT",
}

_PUBLICATION_SOURCE_PRIORITY = {
    "manual": 400,
    "bibliographic": 300,
    "gutenberg_description": 200,
    "gutenberg_text": 100,
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    existing = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(works)")
    }
    for column, column_type in _WORKS_ADDITIVE_COLUMNS.items():
        if column in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE works ADD COLUMN {column} {column_type}")
        except sqlite3.OperationalError as error:
            # Multiple application processes may initialize the same upgraded
            # database concurrently. Ignore only a confirmed duplicate-column
            # race; every other migration failure remains fatal.
            refreshed = {
                row["name"] if isinstance(row, sqlite3.Row) else row[1]
                for row in conn.execute("PRAGMA table_info(works)")
            }
            if column not in refreshed:
                raise error
        existing.add(column)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_works_original_publication_year "
        "ON works (original_publication_year DESC)"
    )
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


def count_works(conn: sqlite3.Connection) -> int:
    """Return the canonical public Library work count."""
    return int(conn.execute("SELECT COUNT(*) FROM works").fetchone()[0])


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
    if meta.get("original_publication_year") is not None:
        set_original_publication_metadata(
            conn,
            gid,
            year=meta["original_publication_year"],
            source=meta.get("original_publication_source", ""),
            confidence=meta.get("original_publication_confidence"),
            evidence=meta.get("original_publication_evidence"),
        )
    checked_at = meta.get("original_publication_checked_at")
    if checked_at:
        mark_original_publication_checked(conn, gid, str(checked_at))


def _normalize_evidence(evidence: str | None) -> str | None:
    if not evidence:
        return None
    normalized = " ".join(str(evidence).split())
    return normalized[:240] or None


def _validate_original_publication_value(
    year: int | str,
    source: str,
    confidence: float | str | None,
) -> tuple[int, str, float]:
    try:
        normalized_year = int(year)
    except (TypeError, ValueError) as error:
        raise ValueError("original publication year must be an integer") from error
    current_year = datetime.now(timezone.utc).year
    if normalized_year < 1 or normalized_year > current_year:
        raise ValueError(
            f"original publication year must be between 1 and {current_year}"
        )
    normalized_source = str(source or "").strip().lower()
    if not normalized_source:
        raise ValueError("original publication source is required")
    try:
        normalized_confidence = float(confidence)
    except (TypeError, ValueError) as error:
        raise ValueError("original publication confidence is required") from error
    if not 0.0 <= normalized_confidence <= 1.0:
        raise ValueError("original publication confidence must be between 0 and 1")
    return normalized_year, normalized_source, normalized_confidence


def set_original_publication_metadata(
    conn: sqlite3.Connection,
    gid: int | str,
    *,
    year: int | str,
    source: str,
    confidence: float | str | None,
    evidence: str | None = None,
    replace_manual: bool = False,
) -> bool:
    """Set publication metadata only when its provenance outranks existing data.

    Returns True when the row changed. Automatic callers must leave
    ``replace_manual`` false. A deliberate manual correction may set it true.
    """
    year_i, source_s, confidence_f = _validate_original_publication_value(
        year, source, confidence
    )
    row = conn.execute(
        "SELECT original_publication_year, original_publication_source, "
        "original_publication_confidence, original_publication_evidence "
        "FROM works WHERE gutenberg_id = ?",
        (int(gid),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Gutenberg work {int(gid)}")

    existing_year = row["original_publication_year"]
    existing_source = (row["original_publication_source"] or "").lower()
    existing_confidence = row["original_publication_confidence"]
    incoming_priority = _PUBLICATION_SOURCE_PRIORITY.get(source_s, 0)
    existing_priority = _PUBLICATION_SOURCE_PRIORITY.get(existing_source, 0)

    should_update = existing_year is None
    if existing_year is not None:
        if existing_source == "manual":
            should_update = source_s == "manual" and replace_manual
        elif source_s == "manual":
            should_update = True
        elif incoming_priority > existing_priority:
            should_update = True
        elif incoming_priority == existing_priority:
            existing_confidence_f = float(existing_confidence or 0.0)
            should_update = confidence_f > existing_confidence_f
            if (
                not should_update
                and year_i == int(existing_year)
                and source_s == existing_source
                and confidence_f == existing_confidence_f
                and not row["original_publication_evidence"]
                and evidence
            ):
                should_update = True

    if not should_update:
        return False

    conn.execute(
        "UPDATE works SET original_publication_year = ?, "
        "original_publication_source = ?, original_publication_confidence = ?, "
        "original_publication_evidence = ? WHERE gutenberg_id = ?",
        (
            year_i,
            source_s,
            confidence_f,
            _normalize_evidence(evidence),
            int(gid),
        ),
    )
    return True


def set_manual_original_publication_year(
    conn: sqlite3.Connection,
    gid: int | str,
    year: int | str,
    evidence: str | None = None,
) -> bool:
    """Set or deliberately correct a manually verified publication year."""
    return set_original_publication_metadata(
        conn,
        gid,
        year=year,
        source="manual",
        confidence=1.0,
        evidence=evidence,
        replace_manual=True,
    )


def mark_original_publication_checked(
    conn: sqlite3.Connection,
    gid: int | str,
    checked_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE works SET original_publication_checked_at = ? "
        "WHERE gutenberg_id = ?",
        (checked_at or datetime.now(timezone.utc).isoformat(), int(gid)),
    )


def publication_backfill_candidates(
    conn: sqlite3.Connection,
    *,
    limit: int,
    after_id: int = 0,
    min_id: int | None = None,
    max_id: int | None = None,
    shelf: str | None = None,
    retry_checked: bool = False,
) -> list[sqlite3.Row]:
    """Return IDs for a bounded, resumable stored-text backfill."""
    clauses = ["w.original_publication_year IS NULL", "w.gutenberg_id > ?"]
    params: list[object] = [int(after_id)]
    if not retry_checked:
        clauses.append("w.original_publication_checked_at IS NULL")
    if min_id is not None:
        clauses.append("w.gutenberg_id >= ?")
        params.append(int(min_id))
    if max_id is not None:
        clauses.append("w.gutenberg_id <= ?")
        params.append(int(max_id))
    if shelf:
        clauses.append(
            "EXISTS (SELECT 1 FROM shelf_members sm "
            "WHERE sm.gutenberg_id = w.gutenberg_id AND sm.slug = ?)"
        )
        params.append(str(shelf))
    clauses.append(
        "EXISTS (SELECT 1 FROM work_texts wt WHERE wt.gutenberg_id = w.gutenberg_id)"
    )
    params.append(max(0, int(limit)))
    return list(
        conn.execute(
            "SELECT w.gutenberg_id FROM works w "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY w.gutenberg_id LIMIT ?",
            params,
        )
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
