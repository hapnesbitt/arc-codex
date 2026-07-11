"""Smoke suite — the money paths.

Every test uses the Flask test client. Redis / library.db / Ollama are
monkey-patched; no live services required. Failures here indicate real
regressions on the three surfaces most likely to draw scraper traffic,
cost cloud credits, or expose the write path.
"""
from unittest.mock import MagicMock

import main


# ============================================================================
# /api/get_feed — clamps + shape (Wave B: uncapped limit was the recon prompt)
# ============================================================================

def test_get_feed_503_when_redis_offline(client, monkeypatch):
    monkeypatch.setattr(main, "r", None)
    resp = client.get("/api/get_feed")
    assert resp.status_code == 503
    assert resp.get_json() == {"error": "Database connection is offline."}


def test_get_feed_returns_empty_list_when_feed_empty(client, monkeypatch):
    fake_r = MagicMock()
    fake_r.zrevrange.return_value = []
    monkeypatch.setattr(main, "r", fake_r)
    resp = client.get("/api/get_feed")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_get_feed_clamps_limit_to_50(client, monkeypatch):
    fake_r = MagicMock()
    fake_r.zrevrange.return_value = []
    monkeypatch.setattr(main, "r", fake_r)
    resp = client.get("/api/get_feed?limit=100000")
    assert resp.status_code == 200
    # limit clamped to 50 → ZREVRANGE 0..49 (inclusive)
    fake_r.zrevrange.assert_called_once_with("feed", 0, 49)


def test_get_feed_clamps_negative_offset_to_zero(client, monkeypatch):
    fake_r = MagicMock()
    fake_r.zrevrange.return_value = []
    monkeypatch.setattr(main, "r", fake_r)
    resp = client.get("/api/get_feed?offset=-999")
    assert resp.status_code == 200
    # default limit 33, offset clamped to 0 → ZREVRANGE 0..32
    fake_r.zrevrange.assert_called_once_with("feed", 0, 32)


# ============================================================================
# /api/library/<id>?lang=… — Wave B Sec-Fetch-* gate
# ============================================================================

_FAKE_META = {
    "gutenberg_id": "1",
    "title": "Test Book",
    "author": "Author",
    "language": "en",
    "subjects": "[]",
    "year_published": "1900",
    "download_count": "0",
    "encoding": "utf-8",
    "source_url": "",
    "fetched_at": "",
    "chimera_score": None,
    "reading_label": "",
    "chimera_skip_reason": "",
    "fk_grade": None,
    "coleman_liau": None,
    "smog": None,
    "dale_chall": None,
    "scored_at": "",
}


class _FakeConnCM:
    """Stand-in for library_db.db() context manager."""
    def __enter__(self): return object()
    def __exit__(self, *exc): return False


def _patch_library(monkeypatch, cached_translation=None):
    """Wire library_db + Redis so the endpoint reaches the gate branch.

    English work with body, no cached translation → forces the code down
    the branch that either commissions or gates. cached_translation=<dict>
    exercises the cache-hit path instead.
    """
    monkeypatch.setattr(main.library_db, "db", _FakeConnCM)
    monkeypatch.setattr(main.library_db, "get_work",
                        lambda conn, gid: dict(_FAKE_META))
    monkeypatch.setattr(main.library_db, "get_text",
                        lambda conn, gid: "Body text.")
    monkeypatch.setattr(main.library_db, "get_translation",
                        lambda conn, gid, lang: cached_translation)
    # Redis inflight lock — grant it so we'd reach commission if not gated
    fake_r = MagicMock()
    fake_r.set.return_value = True
    monkeypatch.setattr(main, "r", fake_r)
    return fake_r


def test_library_gate_scraper_no_sec_fetch_gets_bot_path(client, monkeypatch):
    _patch_library(monkeypatch)
    # Fake-Chrome UA (slips _is_bot_ua) with NO Sec-Fetch-* headers
    resp = client.get(
        "/api/library/1?lang=fr",
        headers={"User-Agent":
                 "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/140"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["translation_error"] == "Translation not generated for automated clients."
    assert body["is_translated"] is False


def test_library_gate_browser_shaped_passes_to_commission(client, monkeypatch):
    _patch_library(monkeypatch)
    # Intercept the commission call so we prove the gate LET THROUGH
    called = {"n": 0}
    def spy(snippet, lang_name, src, timeout=120):
        called["n"] += 1
        return "translated body"
    import translation
    monkeypatch.setattr(translation, "_call_translation_model", spy)
    monkeypatch.setattr(main.library_db, "set_translation",
                        lambda *a, **kw: None)

    resp = client.get(
        "/api/library/1?lang=fr",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/140",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        },
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert called["n"] == 1, "commission never fired — gate blocked incorrectly"
    assert body["is_translated"] is True


def test_library_cache_hit_served_to_scraper_ungated(client, monkeypatch):
    _patch_library(monkeypatch, cached_translation={
        "body": "cached translation",
        "is_preview": False,
        "preview_chars": None,
    })
    resp = client.get(
        "/api/library/1?lang=es",
        headers={"User-Agent":
                 "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/140"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["is_translated"] is True
    assert body["text"] == "cached translation"
    assert "translation_error" not in body


# ============================================================================
# /api/post_bluesky — Wave A commit 1b4c32b hardened this to require secret
# ============================================================================

def test_post_bluesky_403_without_secret(client):
    resp = client.post("/api/post_bluesky", json={"article_id": "x"})
    assert resp.status_code == 403
    assert resp.get_json() == {"error": "Unauthorized"}


def test_post_bluesky_403_with_wrong_secret(client):
    resp = client.post(
        "/api/post_bluesky",
        headers={"X-Scribe-Secret": "not-the-secret"},
        json={"article_id": "x"},
    )
    assert resp.status_code == 403
