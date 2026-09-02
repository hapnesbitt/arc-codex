#!/usr/bin/env python3
"""
Arc Codex — library_fetcher.py

One-shot (or cron) ingestion of the Project Gutenberg "Top 100, last 30 days"
list plus the curated shelves in shelves.yaml. For each book:
  1. Parse the top-100 list page for ebook IDs.
  2. Fetch RDF metadata (title, author, language, subjects, downloads, year).
  3. Fetch the plain-text body (UTF-8 first, Latin-1 fallback, then encoding
     detection via charset-normalizer).
  4. Strip the Project Gutenberg boilerplate header/footer.
  5. Write to SQLite at /mnt/arcdata/library.db (see library_db.py).
     Moved out of Redis 2026-07-08 — the text corpus had grown to ~12.7 GB
     of Redis memory and drove the 2026-07-07 OOM incident.

Scope: the corpus is the CURRENT top-100 + current shelf membership
(~1,800 works). Because both lists churn weekly, works accumulate beyond
that scope over time; LIBRARY_MAX_WORKS is the hard bound — after each run,
oldest-fetched works no longer referenced by any shelf are pruned until the
bound holds. (The pre-2026-07-08 behavior had no bound and hoarded ~29K
works in Redis.)

Idempotent: a work fetched within the last 7 days is skipped.

Usage:
    cd /home/www/arc_stack/backend && source venv/bin/activate
    python3 library_fetcher.py

All deps already in requirements.txt: requests, beautifulsoup4, lxml,
charset-normalizer, python-dotenv. Storage is stdlib sqlite3 via library_db.
"""
from __future__ import annotations

import hashlib
import fcntl
import logging
import os
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TextIO
from urllib.parse import parse_qs, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
from dotenv import load_dotenv

import library_db
from publication_metadata import extract_original_publication

load_dotenv()

# --- CONFIG ---
TOP_LIST_URL  = "https://www.gutenberg.org/browse/scores/top#authors-last30"
SHELF_SORT_ORDER = "release_date"
SHELF_SORT_LABEL = "Release Date"
SHELF_URL_TMPL = (
    "https://www.gutenberg.org/ebooks/bookshelf/{id}"
    "?sort_order={sort_order}&start_index={start}"
)
RDF_URL_TMPL  = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.rdf"
TXT_URL_TMPLS = [
    "https://www.gutenberg.org/files/{id}/{id}-0.txt",   # UTF-8 modern
    "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt",
    "https://www.gutenberg.org/files/{id}/{id}.txt",     # Latin-1 older
    "https://www.gutenberg.org/files/{id}/{id}-8.txt",   # Latin-1 alt
]
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
REQUEST_TIMEOUT = 30
PUBLICATION_TIMEOUT = 10
PUBLICATION_ATTEMPTS = 3
SECTION_HEADING = "Top 100 EBooks last 30 days"
RECHECK_AFTER_SECONDS = 7 * 24 * 60 * 60  # 7 days
SHELVES_CONFIG_PATH = Path(__file__).resolve().parent.parent / "shelves.yaml"
REFRESH_LOCK_PATH = Path(
    os.environ.get(
        "LIBRARY_REFRESH_LOCK_PATH",
        str(Path(__file__).resolve().parent.parent / "pids" / "library_fetcher.lock"),
    )
)
# Hard bound on corpus size: current top-100 + 34 shelves × 50 ≈ 1,800
# referenced works; the rest is churn history. Above this, oldest-fetched
# unreferenced works are pruned after each run.
LIBRARY_MAX_WORKS = int(os.environ.get("LIBRARY_MAX_WORKS", "5000"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [library_fetcher] %(levelname)s %(message)s",
)
log = logging.getLogger("library_fetcher")


class ShelfFetchError(RuntimeError):
    """A shelf listing could not be fetched completely and safely."""


class ShelfPaginationOverlap(ShelfFetchError):
    """A stable-order shelf scan overlapped and could not prove completeness."""


class WorkFetchError(RuntimeError):
    """A work could not be checked completely because transport failed."""


class JobInterrupted(RuntimeError):
    """The process received a graceful termination signal."""


@dataclass
class RunStats:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_monotonic: float = field(default_factory=time.monotonic)
    examined: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    shelves_completed: int = 0
    shelves_failed: int = 0
    last_completed_shelf: str = ""
    pruned: int = 0
    final_count: Optional[int] = None
    publication: str = "NOT_ATTEMPTED"
    errors: list[str] = field(default_factory=list)

    def record_work(self, status: str) -> None:
        self.examined += 1
        if status == "inserted":
            self.inserted += 1
        elif status == "updated":
            self.updated += 1
        elif status in {"fresh", "unavailable"}:
            self.skipped += 1
        else:
            self.failed += 1


# ---------------------------------------------------------------------------
# Top-100 list scraping
# ---------------------------------------------------------------------------

def fetch_top_100_ids() -> list[int]:
    """Return the gutenberg IDs in the 'last 30 days' section, in rank order."""
    log.info("Fetching top-100 list: %s", TOP_LIST_URL)
    resp = requests.get(TOP_LIST_URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    target_h2 = None
    for h2 in soup.find_all("h2"):
        if SECTION_HEADING.lower() in h2.get_text(strip=True).lower():
            target_h2 = h2
            break
    if target_h2 is None:
        raise RuntimeError(f"Could not find heading '{SECTION_HEADING}' on top-100 page")

    ol = target_h2.find_next("ol")
    if ol is None:
        raise RuntimeError("Could not find <ol> sibling after target heading")

    ids: list[int] = []
    for a in ol.find_all("a", href=True):
        m = re.match(r"^/ebooks/(\d+)$", a["href"])
        if m:
            ids.append(int(m.group(1)))
    if not ids:
        raise RuntimeError("No ebook IDs parsed from top-100 list")

    log.info("Parsed %d ebook IDs", len(ids))
    return ids[:100]


# ---------------------------------------------------------------------------
# Curated shelf scraping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShelfPage:
    ids: tuple[int, ...]
    total_results: int
    start_index: int
    items_per_page: int
    next_start: Optional[int]


def _required_meta_int(soup: BeautifulSoup, name: str) -> int:
    element = soup.find("meta", attrs={"name": name})
    value = element.get("content") if element else None
    if not isinstance(value, str) or not value.isdigit():
        raise ValueError(f"missing or invalid {name} metadata")
    return int(value)


def _parse_shelf_page(
    html: str,
    bookshelf_id: int,
    expected_start: int,
    expected_sort_order: str,
) -> ShelfPage:
    """Validate one Gutenberg shelf result page and its pagination metadata."""
    soup = BeautifulSoup(html, "lxml")
    total_results = _required_meta_int(soup, "totalResults")
    start_index = _required_meta_int(soup, "startIndex")
    items_per_page = _required_meta_int(soup, "itemsPerPage")
    if start_index != expected_start:
        raise ValueError(
            f"startIndex={start_index} does not match requested {expected_start}"
        )
    if items_per_page <= 0:
        raise ValueError("itemsPerPage must be positive")

    selected_sort = soup.select_one("button.sort-dropdown-toggle span")
    selected_sort_label = selected_sort.get_text(strip=True) if selected_sort else None
    if expected_sort_order == SHELF_SORT_ORDER and selected_sort_label != SHELF_SORT_LABEL:
        raise ValueError(
            f"expected {SHELF_SORT_LABEL!r} sorting, found {selected_sort_label!r}"
        )

    results = soup.select_one("ul.results")
    if results is None:
        raise ValueError("missing ul.results container")

    ids: list[int] = []
    seen: set[int] = set()
    booklinks = results.select("li.booklink")
    for booklink in booklinks:
        a = booklink.select_one("a.link[href]")
        if a is None:
            raise ValueError("booklink is missing its ebook link")
        m = re.match(r"^/ebooks/(\d+)$", a["href"])
        if not m:
            raise ValueError(f"unexpected booklink href: {a['href']!r}")
        gid = int(m.group(1))
        if gid in seen:
            raise ValueError(f"duplicate ebook id {gid} on one result page")
        seen.add(gid)
        ids.append(gid)

    next_links = results.select('a[accesskey="+"][href]')
    next_targets: set[tuple[str, int, str]] = set()
    for next_link in next_links:
        parsed = urlparse(next_link["href"])
        expected_path = f"/ebooks/bookshelf/{bookshelf_id}"
        query = parse_qs(parsed.query)
        values = query.get("start_index", [])
        sort_values = query.get("sort_order", [])
        if (
            parsed.path != expected_path
            or len(values) != 1
            or not values[0].isdigit()
            or sort_values != [expected_sort_order]
        ):
            raise ValueError("Next link does not target the requested bookshelf")
        next_targets.add((parsed.path, int(values[0]), sort_values[0]))
    if len(next_targets) > 1:
        raise ValueError("conflicting Next links found")
    next_start = next(iter(next_targets))[1] if next_targets else None

    if next_start is not None:
        expected_next = start_index + items_per_page
        if next_start != expected_next:
            raise ValueError(
                f"expected Next start_index={expected_next}, found {next_start!r}"
            )
        if total_results < next_start:
            raise ValueError(
                f"totalResults={total_results} precedes Next start_index={next_start}"
            )
        expected_count = items_per_page
    else:
        expected_count = max(total_results - start_index + 1, 0)

    if len(ids) != expected_count:
        raise ValueError(
            f"expected {expected_count} booklink(s) from pagination metadata, "
            f"parsed {len(ids)}"
        )

    return ShelfPage(
        ids=tuple(ids),
        total_results=total_results,
        start_index=start_index,
        items_per_page=items_per_page,
        next_start=next_start,
    )


def _fetch_shelf_ids_once(bookshelf_id: int, limit: int) -> list[int]:
    """Perform one structurally validated, stable-order shelf enumeration."""
    ids: list[int] = []
    seen: dict[int, tuple[int, int]] = {}
    overlaps = 0
    start = 1
    while len(ids) < limit:
        url = SHELF_URL_TMPL.format(
            id=bookshelf_id,
            sort_order=SHELF_SORT_ORDER,
            start=start,
        )
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ShelfFetchError(
                f"Bookshelf {bookshelf_id} page start_index={start} fetch failed: {e}"
            ) from e

        try:
            page = _parse_shelf_page(
                resp.text,
                bookshelf_id,
                start,
                SHELF_SORT_ORDER,
            )
        except JobInterrupted:
            raise
        except Exception as e:
            raise ShelfFetchError(
                f"Bookshelf {bookshelf_id} page start_index={start} parse failed: {e}"
            ) from e

        for position, gid in enumerate(page.ids, start=page.start_index):
            previous = seen.get(gid)
            if previous is not None:
                overlaps += 1
                log.warning(
                    "Bookshelf %d overlap under sort_order=%s: ebook id %d "
                    "at start_index=%d position=%d was already seen at "
                    "start_index=%d position=%d; deduplicating pending "
                    "completeness validation",
                    bookshelf_id,
                    SHELF_SORT_ORDER,
                    gid,
                    page.start_index,
                    position,
                    previous[0],
                    previous[1],
                )
                continue
            seen[gid] = (page.start_index, position)
            ids.append(gid)
            if len(ids) >= limit:
                break

        if len(ids) >= limit:
            if overlaps and page.next_start is not None:
                raise ShelfPaginationOverlap(
                    f"Bookshelf {bookshelf_id} encountered {overlaps} overlap(s) "
                    "before the configured result limit; completeness cannot "
                    "be established"
                )
            break
        if page.next_start is None:
            expected_unique = min(limit, page.total_results)
            if overlaps or len(ids) != expected_unique:
                raise ShelfPaginationOverlap(
                    f"Bookshelf {bookshelf_id} stable-order enumeration was "
                    f"incomplete after {overlaps} overlap(s): expected "
                    f"{expected_unique} unique ebook ids, collected {len(ids)}"
                )
            break
        start = page.next_start
        time.sleep(0.5)

    return ids[:limit]


def fetch_shelf_ids(bookshelf_id: int, limit: int = 50) -> list[int]:
    """Fetch the first N book IDs from a Gutenberg bookshelf.

    Gutenberg paginates 25 results per page via ?start_index=1, 26, 51, 76.
    Explicit release-date ordering avoids the default popularity order, whose
    live download counts can move works across page boundaries during
    enumeration. Unlike Gutenberg's title/author orderings, release-date order
    also produced non-overlapping live enumerations up to Arc's configured
    shelf limit during validation.
    A rare overlap under stable ordering is deduplicated, checked against the
    terminal result count, and retried once from page one if incomplete.
    Raises ShelfFetchError if a required page or retry fails so callers never
    replace a valid shelf with a partial response.
    """
    for attempt in range(2):
        try:
            return _fetch_shelf_ids_once(bookshelf_id, limit)
        except JobInterrupted:
            raise
        except ShelfPaginationOverlap:
            if attempt == 1:
                raise
            log.warning(
                "Bookshelf %d stable-order enumeration was incomplete; "
                "retrying once from start_index=1",
                bookshelf_id,
            )
            time.sleep(0.5)

    raise AssertionError("unreachable shelf retry state")


# ---------------------------------------------------------------------------
# RDF metadata
# ---------------------------------------------------------------------------

def fetch_rdf_metadata(gid: int) -> Optional[dict]:
    url = RDF_URL_TMPL.format(id=gid)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("[%d] RDF fetch failed: %s", gid, e)
        return None

    soup = BeautifulSoup(resp.content, "lxml-xml")

    title_el = soup.find("dcterms:title")
    title = title_el.get_text(strip=True) if title_el else ""

    # Author lives at dcterms:creator → pgterms:agent → pgterms:name.
    # Multiple creators are concatenated with " & ".
    authors: list[str] = []
    for creator in soup.find_all("dcterms:creator"):
        agent = creator.find("pgterms:agent")
        if not agent:
            continue
        name = agent.find("pgterms:name")
        if name:
            authors.append(name.get_text(strip=True))
    author = " & ".join(authors) if authors else "Unknown"

    # Language: dcterms:language → rdf:value → e.g. "en"
    lang_el = soup.find("dcterms:language")
    language = ""
    if lang_el:
        v = lang_el.find("rdf:value")
        language = v.get_text(strip=True) if v else lang_el.get_text(strip=True)

    # Subjects: each dcterms:subject → rdf:Description → rdf:value
    subjects: list[str] = []
    for subj in soup.find_all("dcterms:subject"):
        v = subj.find("rdf:value")
        if v:
            subjects.append(v.get_text(strip=True))

    # Downloads
    dl_el = soup.find("pgterms:downloads")
    download_count = 0
    if dl_el:
        try:
            download_count = int(dl_el.get_text(strip=True))
        except ValueError:
            pass

    # Gutenberg's electronic-edition release date. The legacy database/API
    # field year_published stores only this year; it is NOT the work's original
    # publication year.
    issued_el = soup.find("dcterms:issued")
    year_published = ""
    if issued_el:
        text = issued_el.get_text(strip=True)
        m = re.match(r"^(\d{4})", text)
        if m:
            year_published = m.group(1)

    description_el = soup.find("dcterms:description")
    description = description_el.get_text(" ", strip=True) if description_el else ""

    return {
        "title":          title,
        "author":         author,
        "language":       language,
        "subjects":       subjects,
        "download_count": download_count,
        "year_published": year_published,
        "gutenberg_description": description,
    }


# ---------------------------------------------------------------------------
# Plain-text body fetch + decode + boilerplate strip
# ---------------------------------------------------------------------------

# Project Gutenberg start markers (modern + legacy variants)
START_MARKERS = [
    re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^*]*\*\*\*", re.IGNORECASE),
    re.compile(r"\*END\*THE SMALL PRINT!.*?\*END\*", re.IGNORECASE | re.DOTALL),
]
END_MARKERS = [
    re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^*]*\*\*\*", re.IGNORECASE),
    re.compile(r"End of (?:the )?Project Gutenberg(?:'s)?[^.\n]*\.?$", re.IGNORECASE | re.MULTILINE),
]


def fetch_book_text(gid: int) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Return (text, encoding_used, source_url) on success, (None, None, None) otherwise.
    Tries each candidate URL with utf-8 → latin-1 → charset-normalizer detection.
    """
    request_errors: list[str] = []
    for tmpl in TXT_URL_TMPLS:
        url = tmpl.format(id=gid)
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.debug("[%d] %s — request error: %s", gid, url, e)
            request_errors.append(f"{url}: {e}")
            continue
        if resp.status_code != 200:
            log.debug("[%d] %s — HTTP %d", gid, url, resp.status_code)
            continue

        raw = resp.content
        text = None
        enc_used = None
        for enc in ("utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                enc_used = enc
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            best = from_bytes(raw).best()
            if best is not None:
                text = str(best)
                enc_used = best.encoding or "detected"

        if text is not None:
            return text, enc_used, url

    if request_errors:
        raise WorkFetchError(
            f"{len(request_errors)} text request(s) failed; no candidate URL succeeded"
        )
    return None, None, None


def strip_gutenberg_boilerplate(text: str) -> str:
    """
    Remove the standard Project Gutenberg header (everything up to and
    including the START marker) and footer (the END marker onward).
    Leaves the work itself intact. If markers aren't found, returns the
    text unchanged — better to show too much than to truncate the body.
    """
    body = text

    for pat in START_MARKERS:
        m = pat.search(body)
        if m:
            body = body[m.end():]
            break

    for pat in END_MARKERS:
        m = pat.search(body)
        if m:
            body = body[:m.start()]
            break

    return body.strip()


# ---------------------------------------------------------------------------
# SQLite writes
# ---------------------------------------------------------------------------

def is_fresh(conn, gid: int) -> bool:
    """Return True if this work was fetched within RECHECK_AFTER_SECONDS."""
    row = conn.execute(
        "SELECT fetched_at FROM works WHERE gutenberg_id = ?", (gid,)
    ).fetchone()
    if not row or not row["fetched_at"]:
        return False
    try:
        ts = datetime.fromisoformat(row["fetched_at"])
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age < RECHECK_AFTER_SECONDS


def write_work(conn, gid: int, meta: dict, text: str, encoding: str, source_url: str) -> str:
    new_text_md5 = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
    old = conn.execute(
        "SELECT text_md5 FROM works WHERE gutenberg_id = ?", (gid,)
    ).fetchone()
    old_text_md5 = old["text_md5"] if old else None

    checked_at = datetime.now(timezone.utc).isoformat()
    publication = extract_original_publication(
        description=meta.get("gutenberg_description"),
        text=text,
    )
    work_meta = {
        "title":          meta["title"],
        "author":         meta["author"],
        "language":       meta["language"],
        "subjects":       meta["subjects"],
        "year_published": meta["year_published"],
        "download_count": meta["download_count"],
        "encoding":       encoding,
        "source_url":     source_url,
        "fetched_at":     checked_at,
        "text_md5":       new_text_md5,
        "original_publication_checked_at": checked_at,
    }
    if publication is not None:
        work_meta.update({
            "original_publication_year": publication.year,
            "original_publication_source": publication.source,
            "original_publication_confidence": publication.confidence,
            "original_publication_evidence": publication.evidence,
        })
    library_db.upsert_work(conn, gid, work_meta, text)

    if old_text_md5 and old_text_md5 != new_text_md5:
        # Source text changed — cached translations are stale.
        deleted = library_db.delete_translations(conn, gid)
        if deleted:
            log.info("library #%d — invalidated %d cached translation(s) after text change", gid, deleted)
    conn.commit()
    return "updated" if old else "inserted"


# ---------------------------------------------------------------------------
# Per-work ingest (shared by top-100 and shelves)
# ---------------------------------------------------------------------------

def ensure_work_exists(conn, gid: int, label: str = "") -> str:
    """Fetch + write a single Gutenberg work if it isn't already fresh.

    Returns one of: 'fresh', 'unavailable', 'inserted', 'updated', 'failed'. Idempotent — running twice
    on the same id within RECHECK_AFTER_SECONDS performs no network I/O on the
    second call. Failures are logged and swallowed so callers can keep going.
    """
    if is_fresh(conn, gid):
        log.info("%s%d — fresh, skipping", label, gid)
        return "fresh"

    try:
        meta = fetch_rdf_metadata(gid)
    except JobInterrupted:
        raise
    except Exception as e:
        log.error("%s%d — RDF metadata check failed: %s", label, gid, e)
        return "failed"
    if meta is None:
        return "failed"

    try:
        text, encoding, source_url = fetch_book_text(gid)
    except WorkFetchError as e:
        log.error("%s%d — text fetch failed: %s", label, gid, e)
        return "failed"
    if text is None:
        log.warning("%s%d — no published plain-text rendition; skipping", label, gid)
        return "unavailable"

    cleaned = strip_gutenberg_boilerplate(text)
    status = write_work(conn, gid, meta, cleaned, encoding or "unknown", source_url or "")
    log.info(
        "%s%d — %s · %s · %s · %d chars · enc=%s",
        label, gid,
        (meta["title"] or "")[:48],
        (meta["author"] or "")[:32],
        meta["language"] or "?",
        len(cleaned),
        encoding,
    )
    time.sleep(0.5)  # gentle on Gutenberg
    return status


# ---------------------------------------------------------------------------
# Shelves
# ---------------------------------------------------------------------------

def load_shelves_config() -> Optional[dict]:
    """Load shelves.yaml. Returns None if the file is missing or malformed."""
    if not SHELVES_CONFIG_PATH.exists():
        log.info("No shelves.yaml at %s — skipping shelf fetch", SHELVES_CONFIG_PATH)
        return None
    try:
        with SHELVES_CONFIG_PATH.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        log.error("Failed to load shelves.yaml: %s", e)
        return None
    if not isinstance(cfg, dict) or not isinstance(cfg.get("shelves"), dict):
        log.error("shelves.yaml has no 'shelves' mapping; skipping")
        return None
    return cfg


def fetch_all_shelves(conn, shelves_config: dict, stats: RunStats) -> None:
    """Fetch every configured shelf, preserving valid work from other shelves."""
    limit = int(shelves_config.get("books_per_shelf", 50))
    shelves = shelves_config.get("shelves", {})

    for slug, cfg in shelves.items():
        if not isinstance(cfg, dict):
            message = f"Shelf '{slug}' config is not a mapping"
            log.error("%s; leaving existing membership untouched", message)
            stats.shelves_failed += 1
            stats.errors.append(message)
            continue
        bookshelf_id = cfg.get("gutenberg_bookshelf_id")
        if not isinstance(bookshelf_id, int):
            message = f"Shelf '{slug}' missing integer gutenberg_bookshelf_id"
            log.error("%s; leaving existing membership untouched", message)
            stats.shelves_failed += 1
            stats.errors.append(message)
            continue

        log.info("Shelf '%s' (Gutenberg #%d) — fetching id list", slug, bookshelf_id)
        try:
            ids = fetch_shelf_ids(bookshelf_id, limit)
        except JobInterrupted:
            raise
        except Exception as e:
            message = f"Shelf '{slug}' listing failed: {e}"
            log.error("%s; leaving existing membership untouched", message)
            stats.shelves_failed += 1
            stats.errors.append(message)
            continue
        if not ids:
            message = f"Shelf '{slug}' returned no ids"
            log.error("%s; leaving existing membership untouched", message)
            stats.shelves_failed += 1
            stats.errors.append(message)
            continue

        failures_before = stats.failed
        for i, gid in enumerate(ids, 1):
            status = ensure_work_exists(conn, gid, label=f"[{slug} {i}/{len(ids)}] ")
            stats.record_work(status)

        # Rebuild membership fresh so removed books drop out.
        library_db.replace_shelf(conn, slug, {
            "name":                    cfg.get("name", slug),
            "description":             cfg.get("description", ""),
            "gutenberg_bookshelf_id":  str(bookshelf_id),
            "fetched_at":              datetime.now(timezone.utc).isoformat(),
            "book_count":              len(ids),
        }, ids)
        conn.commit()
        if stats.failed == failures_before:
            stats.shelves_completed += 1
            stats.last_completed_shelf = slug
            log.info("Shelf '%s': %d works — complete", slug, len(ids))
        else:
            failed_here = stats.failed - failures_before
            message = f"Shelf '{slug}' completed with {failed_here} work failure(s)"
            stats.shelves_failed += 1
            stats.errors.append(message)
            log.error("%s", message)


# ---------------------------------------------------------------------------
# Publication + main
# ---------------------------------------------------------------------------

def publish_library() -> None:
    """Ask the local Next server to invalidate only Library landing caches."""
    url = os.environ.get(
        "LIBRARY_REVALIDATE_URL",
        "http://127.0.0.1:3000/api/internal/revalidate-library",
    )
    secret = os.environ.get("LIBRARY_REVALIDATE_SECRET", "")
    if not secret:
        raise RuntimeError("LIBRARY_REVALIDATE_SECRET is not configured")

    last_error: Optional[Exception] = None
    for attempt in range(1, PUBLICATION_ATTEMPTS + 1):
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {secret}"},
                timeout=PUBLICATION_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("revalidated") is not True:
                raise RuntimeError("revalidation endpoint did not confirm success")
            log.info("Library landing cache revalidated (attempt %d)", attempt)
            return
        except JobInterrupted:
            raise
        except (requests.RequestException, ValueError, RuntimeError) as e:
            last_error = e
            if attempt < PUBLICATION_ATTEMPTS:
                log.warning(
                    "Library revalidation attempt %d/%d failed; retrying: %s",
                    attempt,
                    PUBLICATION_ATTEMPTS,
                    e,
                )
                time.sleep(2)

    raise RuntimeError(
        f"Library revalidation failed after {PUBLICATION_ATTEMPTS} attempts: {last_error}"
    )


def try_acquire_refresh_lock() -> Optional[TextIO]:
    """Acquire the process-wide Library refresh lock without waiting."""
    REFRESH_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(REFRESH_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    lock_file = os.fdopen(descriptor, "r+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    return lock_file


def run_ingestion(stats: RunStats) -> bool:
    """Run and commit the Gutenberg refresh. Return True only if fully clean."""
    conn = library_db.connect()
    try:
        library_db.init_schema(conn)
        ids = fetch_top_100_ids()

        top_failures_before = stats.failed
        for i, gid in enumerate(ids, 1):
            status = ensure_work_exists(conn, gid, label=f"[top100 {i}/{len(ids)}] ")
            stats.record_work(status)

        top_failed = stats.failed - top_failures_before
        log.info(
            "Top-100 done. examined=%d inserted=%d updated=%d skipped=%d failed=%d",
            len(ids),
            stats.inserted,
            stats.updated,
            stats.skipped,
            top_failed,
        )

        # Surface the Top-100 list as a shelf so the /library landing page
        # picks it up alongside the curated thematic shelves. Membership is
        # rebuilt fresh each run so works that fall off the list drop out.
        library_db.replace_shelf(conn, "top100", {
            "name":         "Top 100 (Last 30 Days)",
            "description":  "Most-downloaded works on Project Gutenberg over the past month.",
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "book_count":   len(ids),
        }, ids)
        conn.commit()
        if top_failed:
            message = f"Shelf 'top100' completed with {top_failed} work failure(s)"
            stats.shelves_failed += 1
            stats.errors.append(message)
            log.error("%s", message)
        else:
            stats.shelves_completed += 1
            stats.last_completed_shelf = "top100"
            log.info("Shelf 'top100': %d works — complete", len(ids))

        shelves_config = load_shelves_config()
        if shelves_config is None:
            stats.errors.append("shelves.yaml was unavailable or invalid")
        else:
            fetch_all_shelves(conn, shelves_config, stats)

        ingestion_clean = (
            stats.failed == 0 and stats.shelves_failed == 0 and not stats.errors
        )
        if ingestion_clean:
            # Pruning is publication-affecting housekeeping. Never perform it
            # after a known partial or failed refresh.
            stats.pruned = library_db.prune_unreferenced_works(
                conn, LIBRARY_MAX_WORKS
            )
            conn.commit()
            if stats.pruned:
                log.info(
                    "Pruned %d unreferenced work(s) — corpus bound %d",
                    stats.pruned,
                    LIBRARY_MAX_WORKS,
                )
        else:
            log.warning("Skipping prune because ingestion recorded failures")
        stats.final_count = library_db.count_works(conn)
        return ingestion_clean
    finally:
        conn.close()


def _best_effort_final_count(stats: RunStats) -> None:
    if stats.final_count is not None:
        return
    try:
        with library_db.db() as conn:
            stats.final_count = library_db.count_works(conn)
    except JobInterrupted:
        raise
    except Exception as e:
        log.error("Could not read final work count for summary: %s", e)


def log_final_summary(stats: RunStats, exit_status: int) -> None:
    finished_at = datetime.now(timezone.utc)
    runtime = time.monotonic() - stats.started_monotonic
    status = "SUCCESS" if exit_status == 0 else "FAILURE"
    log.info(
        "LIBRARY REFRESH SUMMARY status=%s exit_status=%d "
        "start=%s finish=%s runtime_seconds=%.3f examined=%d inserted=%d "
        "updated=%d unchanged_skipped=%d failed=%d pruned=%d "
        "shelves_completed=%d shelves_failed=%d last_completed_shelf=%s "
        "final_works=%s publication=%s errors=%d",
        status,
        exit_status,
        stats.started_at.isoformat(),
        finished_at.isoformat(),
        runtime,
        stats.examined,
        stats.inserted,
        stats.updated,
        stats.skipped,
        stats.failed,
        stats.pruned,
        stats.shelves_completed,
        stats.shelves_failed,
        stats.last_completed_shelf or "NONE",
        stats.final_count if stats.final_count is not None else "UNKNOWN",
        stats.publication,
        len(stats.errors),
    )


def main(publisher: Optional[Callable[[], None]] = None) -> int:
    try:
        lock_file = try_acquire_refresh_lock()
    except JobInterrupted:
        raise
    except Exception as e:
        log.error("Could not acquire Library refresh lock: %s", e)
        return 1
    if lock_file is None:
        log.warning(
            "Another Library refresh is already active; skipping this invocation"
        )
        return 0

    stats = RunStats()
    exit_status = 1
    publisher = publisher or publish_library
    log.info("Library refresh started at %s", stats.started_at.isoformat())

    try:
        if not run_ingestion(stats):
            exit_status = 2
        else:
            publisher()
            stats.publication = "SUCCESS"
            exit_status = 0
    except JobInterrupted as e:
        stats.errors.append(str(e))
        log.error("Library refresh interrupted: %s", e)
        exit_status = 128
    except Exception as e:
        stats.errors.append(str(e))
        if stats.publication == "NOT_ATTEMPTED" and stats.final_count is not None:
            stats.publication = "FAILURE"
            exit_status = 3
        log.error("Library refresh failed: %s", e, exc_info=True)
    finally:
        if exit_status != 128:
            _best_effort_final_count(stats)
        log_final_summary(stats, exit_status)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

    return exit_status


def install_signal_handlers() -> None:
    def handle_signal(signum, _frame) -> None:
        name = signal.Signals(signum).name
        raise JobInterrupted(f"received {name}")

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


if __name__ == "__main__":
    install_signal_handlers()
    sys.exit(main())
