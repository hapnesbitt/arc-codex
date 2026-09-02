"""Focused tests for nullable, provenance-bearing publication metadata."""
import sqlite3

import library_db
import library_fetcher
import main as arc_main
from publication_metadata import extract_original_publication
from publication_year_backfill import run_backfill


def _meta(**overrides):
    meta = {
        "title": "Synthetic Work",
        "author": "Test Author",
        "language": "en",
        "subjects": ["Tests"],
        "year_published": "2024",
        "download_count": 1,
        "encoding": "utf-8",
        "source_url": "test://work",
        "fetched_at": "2026-08-11T00:00:00+00:00",
        "text_md5": "test",
    }
    meta.update(overrides)
    return meta


def test_schema_migration_adds_nullable_columns_to_existing_database(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE works (
            gutenberg_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            download_count INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO works (gutenberg_id, title) VALUES (7, 'Preserved');
        """
    )

    library_db.init_schema(conn)
    library_db.init_schema(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(works)")}
    assert {
        "original_publication_year",
        "original_publication_source",
        "original_publication_confidence",
        "original_publication_evidence",
        "original_publication_checked_at",
    } <= columns
    row = conn.execute(
        "SELECT title, original_publication_year FROM works WHERE gutenberg_id = 7"
    ).fetchone()
    assert dict(row) == {"title": "Preserved", "original_publication_year": None}
    conn.close()


def test_null_original_publication_year_is_valid(monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    with library_db.db() as conn:
        library_db.upsert_work(conn, 1, _meta(), "No publication statement.")
        row = library_db.get_work(conn, 1)
    assert row["year_published"] == "2024"
    assert row["original_publication_year"] is None


def test_gutenberg_release_year_does_not_become_original_year(monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    with library_db.db() as conn:
        status = library_fetcher.write_work(
            conn,
            2,
            {
                "title": "Released Electronically",
                "author": "Author",
                "language": "en",
                "subjects": [],
                "year_published": "2025",
                "download_count": 0,
                "gutenberg_description": "Project Gutenberg release date: 2025.",
            },
            "Release Date: January 1, 2025\nThis is ordinary text.",
            "utf-8",
            "test://work",
        )
        row = library_db.get_work(conn, 2)
    assert status == "inserted"
    assert row["year_published"] == "2025"
    assert row["original_publication_year"] is None


def test_extracts_explicit_first_published_year():
    result = extract_original_publication(
        text="Title Page\n\nFirst published 1930\n\nChapter One"
    )
    assert result is not None
    assert (result.year, result.source, result.confidence) == (
        1930,
        "gutenberg_text",
        0.95,
    )
    assert "first published" in result.evidence


def test_extracts_explicit_originally_published_year_from_description():
    result = extract_original_publication(
        description="This work was originally published in 1927",
        text="First published 1930",
    )
    assert result is not None
    assert (result.year, result.source, result.confidence) == (
        1927,
        "gutenberg_description",
        0.98,
    )


def test_random_year_in_ordinary_prose_is_rejected():
    assert extract_original_publication(
        text="Chapter One\nIn 1930 the train arrived shortly before midnight."
    ) is None


def test_copyright_edition_and_unqualified_publisher_years_are_rejected():
    assert extract_original_publication(
        text=(
            "Copyright 2004 by Example Author\n"
            "Second edition 2005\n"
            "Published by Example Press 2006\n"
            "Printing 2007"
        )
    ) is None


def test_first_published_year_for_an_edition_or_etext_is_rejected():
    assert extract_original_publication(
        text=(
            "From the Loeb Library Edition\n"
            "Originally published by Example Press\n"
            "First published in 1912"
        )
    ) is None
    assert extract_original_publication(
        text=(
            "The 1913 printing of the Second Edition\n"
            "(first published in 1902) was used in preparation of this etext."
        )
    ) is None


def test_manual_value_is_not_overwritten_by_automatic_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    with library_db.db() as conn:
        library_db.upsert_work(conn, 3, _meta(), "First published 1950")
        library_db.set_manual_original_publication_year(
            conn, 3, 1949, "verified first-edition catalog"
        )
        library_db.upsert_work(
            conn,
            3,
            _meta(
                original_publication_year=1950,
                original_publication_source="gutenberg_text",
                original_publication_confidence=0.95,
                original_publication_evidence="automatic statement",
            ),
            "First published 1950",
        )
        row = library_db.get_work(conn, 3)
    assert row["original_publication_year"] == 1949
    assert row["original_publication_source"] == "manual"
    assert row["original_publication_confidence"] == 1.0


def test_repeated_ingestion_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    meta = {
        "title": "Repeatable",
        "author": "Author",
        "language": "en",
        "subjects": [],
        "year_published": "2024",
        "download_count": 0,
        "gutenberg_description": "",
    }
    with library_db.db() as conn:
        library_fetcher.write_work(
            conn, 4, meta, "First published 1930", "utf-8", "test://work"
        )
        first = library_db.get_work(conn, 4)
        library_fetcher.write_work(
            conn, 4, meta, "First published 1930", "utf-8", "test://work"
        )
        second = library_db.get_work(conn, 4)
        count = library_db.count_works(conn)
    assert count == 1
    assert first["original_publication_year"] == second["original_publication_year"] == 1930
    assert first["original_publication_source"] == second["original_publication_source"]


def test_api_serializes_publication_metadata_and_nulls(client, monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    monkeypatch.setattr(arc_main.library_db, "DB_PATH", str(tmp_path / "library.db"))
    with library_db.db() as conn:
        library_db.upsert_work(conn, 10, _meta(title="Known"), "Body")
        library_db.set_original_publication_metadata(
            conn,
            10,
            year=1930,
            source="bibliographic",
            confidence=0.99,
            evidence="verified bibliographic record",
        )
        library_db.upsert_work(conn, 11, _meta(title="Unknown"), "Body")
        library_db.replace_shelf(
            conn,
            "test",
            {"name": "Test", "gutenberg_bookshelf_id": 77},
            [10, 11],
        )

    known = client.get("/api/library/10").get_json()
    unknown = client.get("/api/library/11").get_json()
    search = client.get("/api/library/search?q=known").get_json()
    shelf = client.get("/api/library/shelf/test").get_json()

    assert known["year_published"] == "2024"
    assert known["original_publication_year"] == 1930
    assert known["original_publication_source"] == "bibliographic"
    assert known["original_publication_confidence"] == 0.99
    assert known["original_publication_evidence"] == "verified bibliographic record"
    assert unknown["original_publication_year"] is None
    assert unknown["original_publication_source"] is None
    assert unknown["original_publication_confidence"] is None
    assert unknown["original_publication_evidence"] is None
    search_by_id = {row["gutenberg_id"]: row for row in search}
    shelf_by_id = {row["gutenberg_id"]: row for row in shelf["books"]}
    assert search_by_id["10"]["original_publication_year"] == 1930
    assert search_by_id["11"]["original_publication_year"] is None
    assert shelf_by_id["10"]["original_publication_source"] == "bibliographic"
    assert shelf_by_id["11"]["original_publication_source"] is None


def test_backfill_limit_resume_and_idempotence(monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    with library_db.db() as conn:
        library_db.upsert_work(conn, 20, _meta(), "First published 1901")
        library_db.upsert_work(conn, 21, _meta(), "A year such as 1902 in prose.")
        library_db.upsert_work(conn, 22, _meta(), "Originally published in 1903")

        first = run_backfill(conn, limit=2)
        second = run_backfill(conn, limit=2)
        third = run_backfill(conn, limit=2)
        rows = {
            row["gutenberg_id"]: dict(row)
            for row in conn.execute(
                "SELECT gutenberg_id, original_publication_year, "
                "original_publication_checked_at FROM works ORDER BY gutenberg_id"
            )
        }

    assert (first.examined, first.populated, first.unknown, first.last_gutenberg_id) == (
        2, 1, 1, 21
    )
    assert (second.examined, second.populated, second.last_gutenberg_id) == (1, 1, 22)
    assert third.examined == 0
    assert rows[20]["original_publication_year"] == 1901
    assert rows[21]["original_publication_year"] is None
    assert rows[21]["original_publication_checked_at"] is not None
    assert rows[22]["original_publication_year"] == 1903


def test_backfill_does_not_change_shelves_or_scoring(monkeypatch, tmp_path):
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "library.db"))
    with library_db.db() as conn:
        library_db.upsert_work(conn, 30, _meta(), "First published 1910")
        library_db.update_work_fields(
            conn,
            30,
            {"chimera_score": "77", "reading_label": "Accessible"},
        )
        library_db.replace_shelf(conn, "test", {"name": "Test"}, [30])
        run_backfill(conn, limit=1)
        row = library_db.get_work(conn, 30)
        members = library_db.get_shelf_member_ids(conn, "test")

    assert row["original_publication_year"] == 1910
    assert row["chimera_score"] == "77"
    assert row["reading_label"] == "Accessible"
    assert members == [30]
