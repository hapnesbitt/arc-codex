#!/usr/bin/env python3
"""
Arc Codex — library_fetcher.py

One-shot (or cron) ingestion of the Project Gutenberg "Top 100, last 30 days"
list. For each book:
  1. Parse the top-100 list page for ebook IDs.
  2. Fetch RDF metadata (title, author, language, subjects, downloads, year).
  3. Fetch the plain-text body (UTF-8 first, Latin-1 fallback, then encoding
     detection via charset-normalizer).
  4. Strip the Project Gutenberg boilerplate header/footer.
  5. Write to Redis under the library: namespace.

Idempotent: a work fetched within the last 7 days is skipped.

Usage:
    cd /home/www/arc_stack/backend && source venv/bin/activate
    python3 library_fetcher.py

All deps already in requirements.txt: requests, beautifulsoup4, lxml,
charset-normalizer, redis, python-dotenv.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import redis
import requests
import yaml
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
TOP_LIST_URL  = "https://www.gutenberg.org/browse/scores/top#authors-last30"
SHELF_URL_TMPL = "https://www.gutenberg.org/ebooks/bookshelf/{id}?start_index={start}"
RDF_URL_TMPL  = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.rdf"
TXT_URL_TMPLS = [
    "https://www.gutenberg.org/files/{id}/{id}-0.txt",   # UTF-8 modern
    "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt",
    "https://www.gutenberg.org/files/{id}/{id}.txt",     # Latin-1 older
    "https://www.gutenberg.org/files/{id}/{id}-8.txt",   # Latin-1 alt
]
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
REQUEST_TIMEOUT = 30
SECTION_HEADING = "Top 100 EBooks last 30 days"
RECHECK_AFTER_SECONDS = 7 * 24 * 60 * 60  # 7 days
SHELVES_CONFIG_PATH = Path(__file__).resolve().parent.parent / "shelves.yaml"

REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "simplenes")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [library_fetcher] %(levelname)s %(message)s",
)
log = logging.getLogger("library_fetcher")


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

def _parse_shelf_page(html: str) -> list[int]:
    """Extract /ebooks/<id> ids from a single bookshelf page, preserving order."""
    soup = BeautifulSoup(html, "lxml")
    ids: list[int] = []
    seen: set[int] = set()
    for a in soup.find_all("a", href=True):
        m = re.match(r"^/ebooks/(\d+)$", a["href"])
        if not m:
            continue
        gid = int(m.group(1))
        if gid in seen:
            continue
        seen.add(gid)
        ids.append(gid)
    return ids


def fetch_shelf_ids(bookshelf_id: int, limit: int = 50) -> list[int]:
    """Fetch the first N book IDs from a Gutenberg bookshelf.

    Gutenberg paginates 25 results per page via ?start_index=1, 26, 51, 76.
    Returns IDs in the order Gutenberg lists them on the shelf page.
    Returns an empty list (with a warning logged) on parse / fetch failure
    rather than raising — one bad shelf shouldn't stop the rest.
    """
    ids: list[int] = []
    seen: set[int] = set()
    for start in range(1, limit + 1, 25):
        url = SHELF_URL_TMPL.format(id=bookshelf_id, start=start)
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Bookshelf %d page start_index=%d fetch failed: %s", bookshelf_id, start, e)
            break

        try:
            page_ids = _parse_shelf_page(resp.text)
        except Exception as e:
            log.warning("Bookshelf %d page start_index=%d parse failed: %s", bookshelf_id, start, e)
            break

        if not page_ids:
            break

        for gid in page_ids:
            if gid in seen:
                continue
            seen.add(gid)
            ids.append(gid)
            if len(ids) >= limit:
                break

        if len(ids) >= limit:
            break
        time.sleep(0.5)

    return ids[:limit]


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

    # Issued / publication date (Gutenberg release date — best we can do without parsing each work)
    issued_el = soup.find("dcterms:issued")
    year_published = ""
    if issued_el:
        text = issued_el.get_text(strip=True)
        m = re.match(r"^(\d{4})", text)
        if m:
            year_published = m.group(1)

    return {
        "title":          title,
        "author":         author,
        "language":       language,
        "subjects":       subjects,
        "download_count": download_count,
        "year_published": year_published,
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
    for tmpl in TXT_URL_TMPLS:
        url = tmpl.format(id=gid)
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.debug("[%d] %s — request error: %s", gid, url, e)
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
# Redis writes
# ---------------------------------------------------------------------------

def get_redis() -> redis.Redis:
    return redis.Redis(decode_responses=True, password=REDIS_PASSWORD)


def is_fresh(r: redis.Redis, gid: int) -> bool:
    """Return True if this work was fetched within RECHECK_AFTER_SECONDS."""
    fetched_at = r.hget(f"library:work:{gid}", "fetched_at")
    if not fetched_at:
        return False
    try:
        ts = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age < RECHECK_AFTER_SECONDS


def _invalidate_derived_caches(r: redis.Redis, gid: int) -> None:
    """Drop pagination boundaries and on-demand translations when the source
    text changes. Uses SCAN MATCH (never KEYS) for pattern deletes."""
    patterns = [
        f"library:work:{gid}:pagination:*",
        f"library:work:{gid}:de:*",
        f"library:work:{gid}:fr:*",
        f"library:work:{gid}:es:*",
        f"library:work:{gid}:pt-br:*",
    ]
    deleted = 0
    for pat in patterns:
        for k in r.scan_iter(match=pat, count=200):
            r.delete(k)
            deleted += 1
    if deleted:
        log.info("library #%d — invalidated %d derived cache key(s) after text change", gid, deleted)


def write_work(r: redis.Redis, gid: int, meta: dict, text: str, encoding: str, source_url: str) -> None:
    key = f"library:work:{gid}"
    new_text_md5 = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
    old_text = r.get(f"{key}:text")
    old_text_md5 = (
        hashlib.md5(old_text.encode("utf-8", errors="replace")).hexdigest()
        if old_text else None
    )

    r.hset(key, mapping={
        "gutenberg_id":   str(gid),
        "title":          meta["title"],
        "author":         meta["author"],
        "language":       meta["language"],
        "subjects":       json.dumps(meta["subjects"]),
        "year_published": meta["year_published"],
        "download_count": str(meta["download_count"]),
        "encoding":       encoding,
        "source_url":     source_url,
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "text_md5":       new_text_md5,
    })
    r.set(f"{key}:text", text)
    # ZSET sorted by download_count — ZREVRANGE for desc display.
    r.zadd("library:works", {str(gid): float(meta["download_count"])})

    if old_text_md5 is not None and old_text_md5 != new_text_md5:
        _invalidate_derived_caches(r, gid)


# ---------------------------------------------------------------------------
# Per-work ingest (shared by top-100 and shelves)
# ---------------------------------------------------------------------------

def ensure_work_exists(r: redis.Redis, gid: int, label: str = "") -> str:
    """Fetch + write a single Gutenberg work if it isn't already fresh.

    Returns one of: 'fresh', 'fetched', 'failed'. Idempotent — running twice
    on the same id within RECHECK_AFTER_SECONDS performs no network I/O on the
    second call. Failures are logged and swallowed so callers can keep going.
    """
    if is_fresh(r, gid):
        log.info("%s%d — fresh, skipping", label, gid)
        return "fresh"

    meta = fetch_rdf_metadata(gid)
    if meta is None:
        return "failed"

    text, encoding, source_url = fetch_book_text(gid)
    if text is None:
        log.warning("%s%d — no plain-text URL succeeded; skipping", label, gid)
        return "failed"

    cleaned = strip_gutenberg_boilerplate(text)
    write_work(r, gid, meta, cleaned, encoding or "unknown", source_url or "")
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
    return "fetched"


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


def fetch_all_shelves(r: redis.Redis, shelves_config: dict) -> None:
    """Fetch every configured shelf and populate library:shelf:<slug>."""
    limit = int(shelves_config.get("books_per_shelf", 50))
    shelves = shelves_config.get("shelves", {})
    slugs: list[str] = []

    for slug, cfg in shelves.items():
        if not isinstance(cfg, dict):
            log.warning("Shelf '%s' config is not a mapping; skipping", slug)
            continue
        bookshelf_id = cfg.get("gutenberg_bookshelf_id")
        if not isinstance(bookshelf_id, int):
            log.warning("Shelf '%s' missing integer gutenberg_bookshelf_id; skipping", slug)
            continue

        log.info("Shelf '%s' (Gutenberg #%d) — fetching id list", slug, bookshelf_id)
        ids = fetch_shelf_ids(bookshelf_id, limit)
        if not ids:
            log.warning("Shelf '%s' returned no ids — leaving existing membership untouched", slug)
            continue

        for i, gid in enumerate(ids, 1):
            ensure_work_exists(r, gid, label=f"[{slug} {i}/{len(ids)}] ")

        # Rebuild membership fresh so removed books drop out.
        shelf_key = f"library:shelf:{slug}"
        r.delete(shelf_key)
        r.sadd(shelf_key, *[str(g) for g in ids])
        r.hset(f"{shelf_key}:meta", mapping={
            "slug":                    slug,
            "name":                    cfg.get("name", slug),
            "description":             cfg.get("description", ""),
            "gutenberg_bookshelf_id":  str(bookshelf_id),
            "fetched_at":              datetime.now(timezone.utc).isoformat(),
            "book_count":              str(len(ids)),
        })
        slugs.append(slug)
        log.info("Shelf '%s': %d works", slug, len(ids))

    # Maintain a registry of known shelf slugs so the API can enumerate them.
    if slugs:
        r.delete("library:shelves")
        r.sadd("library:shelves", *slugs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    r = get_redis()
    try:
        r.ping()
    except redis.RedisError as e:
        log.error("Redis ping failed: %s", e)
        return 1

    try:
        ids = fetch_top_100_ids()
    except Exception as e:
        log.error("Top-100 list fetch failed: %s", e)
        return 1

    fetched = skipped = failed = 0
    for i, gid in enumerate(ids, 1):
        status = ensure_work_exists(r, gid, label=f"[top100 {i}/{len(ids)}] ")
        if status == "fresh":
            skipped += 1
        elif status == "fetched":
            fetched += 1
        else:
            failed += 1

    log.info("Top-100 done. fetched=%d skipped=%d failed=%d", fetched, skipped, failed)

    shelves_config = load_shelves_config()
    if shelves_config is not None:
        try:
            fetch_all_shelves(r, shelves_config)
        except Exception as e:
            log.error("Shelf fetch failed: %s", e, exc_info=True)
            return 2

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
