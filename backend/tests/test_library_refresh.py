"""Focused tests for Gutenberg ingest → Library publication."""
import logging
import os
import signal
from pathlib import Path
from unittest.mock import Mock

import pytest

import library_db
import library_fetcher
import main as arc_main


def _meta(title: str = "Test Work") -> dict:
    return {
        "title": title,
        "author": "Test Author",
        "language": "en",
        "subjects": ["Tests"],
        "download_count": 1,
        "year_published": "2026",
    }


def _configure_isolated_run(monkeypatch, tmp_path, ids=(101,)) -> Path:
    db_path = tmp_path / "library.db"
    monkeypatch.setattr(library_db, "DB_PATH", str(db_path))
    monkeypatch.setattr(
        library_fetcher,
        "REFRESH_LOCK_PATH",
        tmp_path / "library_fetcher.lock",
    )
    monkeypatch.setattr(library_fetcher, "fetch_top_100_ids", lambda: list(ids))
    monkeypatch.setattr(
        library_fetcher,
        "load_shelves_config",
        lambda: {"books_per_shelf": 1, "shelves": {}},
    )
    monkeypatch.setattr(library_fetcher, "fetch_rdf_metadata", lambda _gid: _meta())
    monkeypatch.setattr(
        library_fetcher,
        "fetch_book_text",
        lambda _gid: ("*** START OF THE PROJECT GUTENBERG EBOOK X ***\nBody", "utf-8", "test://work"),
    )
    monkeypatch.setattr(library_fetcher.time, "sleep", lambda _seconds: None)
    return db_path


def _shelf_html(
    ids,
    *,
    total,
    start,
    per_page=2,
    next_start=None,
    duplicate_next=False,
    malformed_booklink=False,
) -> str:
    booklinks = []
    for gid in ids:
        if malformed_booklink:
            booklinks.append('<li class="booklink"><span>missing link</span></li>')
        else:
            booklinks.append(
                f'<li class="booklink"><a class="link" href="/ebooks/{gid}">Book</a></li>'
            )
    next_link = ""
    if next_start is not None:
        next_link = (
            '<a accesskey="+" title="Go to the next page of results." '
            f'href="/ebooks/bookshelf/77?start_index={next_start}">Next</a>'
        )
        if duplicate_next:
            next_link += next_link
    return (
        "<html><head>"
        f'<meta name="totalResults" content="{total}">'
        f'<meta name="startIndex" content="{start}">'
        f'<meta name="itemsPerPage" content="{per_page}">'
        "</head><body><ul class=\"results\">"
        + "".join(booklinks)
        + next_link
        + "</ul></body></html>"
    )


def _response(html: str) -> Mock:
    response = Mock()
    response.text = html
    response.raise_for_status.return_value = None
    return response


def _run_with_installed_signal_handlers(callback):
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    library_fetcher.install_signal_handlers()
    try:
        return callback()
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)


def test_library_stats_uses_canonical_works_table(client, monkeypatch, tmp_path):
    db_path = tmp_path / "stats.db"
    monkeypatch.setattr(library_db, "DB_PATH", str(db_path))
    with library_db.db() as conn:
        library_db.upsert_work(conn, 1, _meta("One"), "one")
        library_db.upsert_work(conn, 2, _meta("Two"), "two")
        library_db.replace_shelf(conn, "only-one", {"name": "One"}, [1])

    response = client.get("/api/library/stats")

    assert response.status_code == 200
    assert response.get_json() == {"shelves": 1, "works": 2}


def test_success_logs_final_summary_and_publishes(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    _configure_isolated_run(monkeypatch, tmp_path)
    publisher = Mock()
    prune = Mock(return_value=0)
    monkeypatch.setattr(library_db, "prune_unreferenced_works", prune)

    exit_status = library_fetcher.main(publisher=publisher)

    assert exit_status == 0
    publisher.assert_called_once_with()
    prune.assert_called_once()
    assert "LIBRARY REFRESH SUMMARY status=SUCCESS exit_status=0" in caplog.text
    assert "inserted=1" in caplog.text
    assert "publication=SUCCESS" in caplog.text


def test_work_failure_is_nonzero_and_does_not_publish(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    _configure_isolated_run(monkeypatch, tmp_path)
    monkeypatch.setattr(library_fetcher, "fetch_rdf_metadata", lambda _gid: None)
    publisher = Mock()
    prune = Mock(return_value=0)
    monkeypatch.setattr(library_db, "prune_unreferenced_works", prune)

    exit_status = library_fetcher.main(publisher=publisher)

    assert exit_status == 2
    publisher.assert_not_called()
    prune.assert_not_called()
    assert "LIBRARY REFRESH SUMMARY status=FAILURE exit_status=2" in caplog.text
    assert "failed=1" in caplog.text
    assert "publication=NOT_ATTEMPTED" in caplog.text


def test_known_missing_text_is_skipped_without_blocking_publication(monkeypatch, tmp_path):
    _configure_isolated_run(monkeypatch, tmp_path)
    monkeypatch.setattr(
        library_fetcher,
        "fetch_book_text",
        lambda _gid: (None, None, None),
    )
    publisher = Mock()

    exit_status = library_fetcher.main(publisher=publisher)

    assert exit_status == 0
    publisher.assert_called_once_with()


def test_publication_failure_is_nonzero(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    _configure_isolated_run(monkeypatch, tmp_path)
    publisher = Mock(side_effect=RuntimeError("Next unavailable"))

    exit_status = library_fetcher.main(publisher=publisher)

    assert exit_status == 3
    publisher.assert_called_once_with()
    assert "publication=FAILURE" in caplog.text
    assert "LIBRARY REFRESH SUMMARY status=FAILURE exit_status=3" in caplog.text


def test_graceful_interrupt_is_nonzero_and_summarized(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    monkeypatch.setattr(library_db, "DB_PATH", str(tmp_path / "interrupted.db"))
    monkeypatch.setattr(
        library_fetcher,
        "REFRESH_LOCK_PATH",
        tmp_path / "library_fetcher.lock",
    )

    def interrupted(_stats):
        raise library_fetcher.JobInterrupted("received SIGTERM")

    monkeypatch.setattr(library_fetcher, "run_ingestion", interrupted)
    publisher = Mock()

    exit_status = library_fetcher.main(publisher=publisher)

    assert exit_status == 128
    publisher.assert_not_called()
    assert "Library refresh interrupted: received SIGTERM" in caplog.text
    assert "LIBRARY REFRESH SUMMARY status=FAILURE exit_status=128" in caplog.text


def test_sigterm_during_rdf_processing_stops_without_prune_or_publish(
    monkeypatch, tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    _configure_isolated_run(monkeypatch, tmp_path)
    publisher = Mock()
    prune = Mock(return_value=0)
    monkeypatch.setattr(library_db, "prune_unreferenced_works", prune)

    def interrupt_during_rdf(_gid):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM handler did not interrupt RDF processing")

    monkeypatch.setattr(library_fetcher, "fetch_rdf_metadata", interrupt_during_rdf)

    exit_status = _run_with_installed_signal_handlers(
        lambda: library_fetcher.main(publisher=publisher)
    )

    assert exit_status == 128
    publisher.assert_not_called()
    prune.assert_not_called()
    assert "Library refresh interrupted: received SIGTERM" in caplog.text
    assert "final_works=UNKNOWN" in caplog.text


def test_sigint_during_shelf_parsing_stops_without_prune_or_publish(
    monkeypatch, tmp_path, caplog
):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    _configure_isolated_run(monkeypatch, tmp_path)
    monkeypatch.setattr(
        library_fetcher,
        "load_shelves_config",
        lambda: {
            "books_per_shelf": 2,
            "shelves": {"test": {"gutenberg_bookshelf_id": 77}},
        },
    )
    monkeypatch.setattr(
        library_fetcher.requests,
        "get",
        Mock(return_value=_response(_shelf_html([201, 202], total=2, start=1))),
    )
    publisher = Mock()
    prune = Mock(return_value=0)
    monkeypatch.setattr(library_db, "prune_unreferenced_works", prune)

    def interrupt_during_parse(*_args):
        os.kill(os.getpid(), signal.SIGINT)
        raise AssertionError("SIGINT handler did not interrupt shelf parsing")

    monkeypatch.setattr(library_fetcher, "_parse_shelf_page", interrupt_during_parse)

    exit_status = _run_with_installed_signal_handlers(
        lambda: library_fetcher.main(publisher=publisher)
    )

    assert exit_status == 128
    publisher.assert_not_called()
    prune.assert_not_called()
    assert "Library refresh interrupted: received SIGINT" in caplog.text
    assert "final_works=UNKNOWN" in caplog.text


def test_sigterm_during_publication_is_not_retried(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    _configure_isolated_run(monkeypatch, tmp_path)
    monkeypatch.setenv("LIBRARY_REVALIDATE_SECRET", "test-scoped-secret")
    post = Mock()

    def interrupt_publication(*_args, **_kwargs):
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("SIGTERM handler did not interrupt publication")

    post.side_effect = interrupt_publication
    monkeypatch.setattr(library_fetcher.requests, "post", post)

    exit_status = _run_with_installed_signal_handlers(library_fetcher.main)

    assert exit_status == 128
    assert post.call_count == 1
    assert "publication=NOT_ATTEMPTED" in caplog.text


def test_rerun_is_idempotent_and_does_not_duplicate(monkeypatch, tmp_path):
    _configure_isolated_run(monkeypatch, tmp_path)

    assert library_fetcher.main(publisher=Mock()) == 0
    assert library_fetcher.main(publisher=Mock()) == 0

    with library_db.db() as conn:
        assert library_db.count_works(conn) == 1
        assert conn.execute(
            "SELECT COUNT(DISTINCT gutenberg_id) FROM works"
        ).fetchone()[0] == 1


def test_normal_multi_page_shelf_completion(monkeypatch):
    pages = [
        _response(
            _shelf_html(
                [1, 2], total=3, start=1, next_start=3, duplicate_next=True
            )
        ),
        _response(_shelf_html([3], total=3, start=3)),
    ]
    get = Mock(side_effect=pages)
    monkeypatch.setattr(library_fetcher.requests, "get", get)
    monkeypatch.setattr(library_fetcher.time, "sleep", lambda _seconds: None)

    assert library_fetcher.fetch_shelf_ids(77, limit=10) == [1, 2, 3]
    assert get.call_count == 2


def test_malformed_http_200_on_first_shelf_page_is_rejected(monkeypatch):
    monkeypatch.setattr(
        library_fetcher.requests,
        "get",
        Mock(return_value=_response("<html><title>Checking your browser</title></html>")),
    )

    with pytest.raises(library_fetcher.ShelfFetchError, match="parse failed"):
        library_fetcher.fetch_shelf_ids(77, limit=10)


def test_malformed_http_200_on_later_shelf_page_is_rejected(monkeypatch):
    pages = [
        _response(_shelf_html([1, 2], total=3, start=1, next_start=3)),
        _response(
            _shelf_html(
                [3], total=3, start=3, malformed_booklink=True
            )
        ),
    ]
    monkeypatch.setattr(library_fetcher.requests, "get", Mock(side_effect=pages))
    monkeypatch.setattr(library_fetcher.time, "sleep", lambda _seconds: None)

    with pytest.raises(library_fetcher.ShelfFetchError, match="parse failed"):
        library_fetcher.fetch_shelf_ids(77, limit=10)


def test_partial_shelf_followed_by_challenge_page_is_rejected(monkeypatch):
    pages = [
        _response(_shelf_html([1, 2], total=3, start=1, next_start=3)),
        _response("<html><title>Challenge</title><body>Try again</body></html>"),
    ]
    monkeypatch.setattr(library_fetcher.requests, "get", Mock(side_effect=pages))
    monkeypatch.setattr(library_fetcher.time, "sleep", lambda _seconds: None)

    with pytest.raises(library_fetcher.ShelfFetchError, match="start_index=3"):
        library_fetcher.fetch_shelf_ids(77, limit=10)


def test_incomplete_shelf_preserves_existing_membership(monkeypatch, tmp_path):
    db_path = tmp_path / "library.db"
    monkeypatch.setattr(library_db, "DB_PATH", str(db_path))
    pages = [
        _response(_shelf_html([1, 2], total=3, start=1, next_start=3)),
        _response("<html><title>Challenge</title></html>"),
    ]
    monkeypatch.setattr(library_fetcher.requests, "get", Mock(side_effect=pages))
    monkeypatch.setattr(library_fetcher.time, "sleep", lambda _seconds: None)

    with library_db.db() as conn:
        library_db.replace_shelf(conn, "test", {"name": "Existing"}, [900, 901])
        stats = library_fetcher.RunStats()
        library_fetcher.fetch_all_shelves(
            conn,
            {
                "books_per_shelf": 10,
                "shelves": {"test": {"gutenberg_bookshelf_id": 77}},
            },
            stats,
        )
        assert set(library_db.get_shelf_member_ids(conn, "test")) == {900, 901}

    assert stats.shelves_failed == 1


def test_shelf_failure_skips_prune_and_publication(monkeypatch, tmp_path):
    _configure_isolated_run(monkeypatch, tmp_path)
    monkeypatch.setattr(library_fetcher, "load_shelves_config", lambda: None)
    prune = Mock(return_value=0)
    publisher = Mock()
    monkeypatch.setattr(library_db, "prune_unreferenced_works", prune)

    assert library_fetcher.main(publisher=publisher) == 2
    prune.assert_not_called()
    publisher.assert_not_called()


def test_second_fetcher_cannot_acquire_refresh_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(
        library_fetcher,
        "REFRESH_LOCK_PATH",
        tmp_path / "library_fetcher.lock",
    )
    first = library_fetcher.try_acquire_refresh_lock()
    assert first is not None
    try:
        assert library_fetcher.try_acquire_refresh_lock() is None
    finally:
        first.close()

    third = library_fetcher.try_acquire_refresh_lock()
    assert third is not None
    third.close()


def test_locked_main_exits_cleanly_without_ingestion(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="library_fetcher")
    monkeypatch.setattr(
        library_fetcher,
        "REFRESH_LOCK_PATH",
        tmp_path / "library_fetcher.lock",
    )
    first = library_fetcher.try_acquire_refresh_lock()
    assert first is not None
    ingestion = Mock()
    monkeypatch.setattr(library_fetcher, "run_ingestion", ingestion)
    try:
        assert library_fetcher.main(publisher=Mock()) == 0
    finally:
        first.close()

    ingestion.assert_not_called()
    assert "Another Library refresh is already active" in caplog.text


def test_publisher_calls_authenticated_local_endpoint(monkeypatch):
    response = Mock()
    response.json.return_value = {"revalidated": True, "path": "/library"}
    response.raise_for_status.return_value = None
    post = Mock(return_value=response)
    monkeypatch.setattr(library_fetcher.requests, "post", post)
    monkeypatch.setenv("LIBRARY_REVALIDATE_SECRET", "test-scoped-secret")
    monkeypatch.setenv(
        "LIBRARY_REVALIDATE_URL",
        "http://127.0.0.1:3000/api/internal/revalidate-library",
    )

    library_fetcher.publish_library()

    post.assert_called_once_with(
        "http://127.0.0.1:3000/api/internal/revalidate-library",
        headers={"Authorization": "Bearer test-scoped-secret"},
        timeout=library_fetcher.PUBLICATION_TIMEOUT,
    )


def test_frontend_revalidation_contract_is_wired():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend/app/library/page.tsx").read_text(encoding="utf-8")
    cache = (root / "frontend/lib/library-cache.ts").read_text(encoding="utf-8")
    route = (
        root / "frontend/app/api/internal/revalidate-library/route.ts"
    ).read_text(encoding="utf-8")

    assert "tags: [LIBRARY_LANDING_CACHE_TAG]" in page
    assert "revalidateTag(LIBRARY_LANDING_CACHE_TAG, { expire: 0 })" in cache
    assert "revalidatePath('/library', 'page')" in cache
    assert "LIBRARY_REVALIDATE_SECRET" in route
    assert "revalidateLibraryLanding()" in route
