#!/usr/bin/env python3
"""Incrementally extract original-publication metadata from stored book text.

This command performs no Gutenberg network requests. Unknown results remain
NULL and receive a checked timestamp so the next bounded run can advance.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import library_db
from publication_metadata import extract_original_publication


@dataclass
class BackfillStats:
    examined: int = 0
    populated: int = 0
    unknown: int = 0
    last_gutenberg_id: int | None = None


def run_backfill(
    conn,
    *,
    limit: int,
    after_id: int = 0,
    min_id: int | None = None,
    max_id: int | None = None,
    shelf: str | None = None,
    retry_checked: bool = False,
) -> BackfillStats:
    """Process a bounded candidate batch and commit progress per work."""
    candidates = library_db.publication_backfill_candidates(
        conn,
        limit=limit,
        after_id=after_id,
        min_id=min_id,
        max_id=max_id,
        shelf=shelf,
        retry_checked=retry_checked,
    )
    stats = BackfillStats()
    for row in candidates:
        gid = int(row["gutenberg_id"])
        # Load one blob at a time; even the maximum 5,000-ID batch must not
        # materialize thousands of complete ebooks in memory.
        evidence = extract_original_publication(text=library_db.get_text(conn, gid))
        if evidence is None:
            stats.unknown += 1
        else:
            changed = library_db.set_original_publication_metadata(
                conn,
                gid,
                year=evidence.year,
                source=evidence.source,
                confidence=evidence.confidence,
                evidence=evidence.evidence,
            )
            stats.populated += int(changed)
        library_db.mark_original_publication_checked(conn, gid)
        conn.commit()
        stats.examined += 1
        stats.last_gutenberg_id = gid
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Conservatively backfill original publication years from stored text"
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after-id", type=int, default=0)
    parser.add_argument("--min-id", type=int)
    parser.add_argument("--max-id", type=int)
    parser.add_argument("--shelf")
    parser.add_argument(
        "--retry-checked",
        action="store_true",
        help="rescan checked records that still have a NULL publication year",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 5000:
        parser.error("--limit must be between 1 and 5000")
    if args.min_id is not None and args.max_id is not None and args.min_id > args.max_id:
        parser.error("--min-id cannot exceed --max-id")
    return args


def main() -> int:
    args = parse_args()
    with library_db.db() as conn:
        stats = run_backfill(
            conn,
            limit=args.limit,
            after_id=args.after_id,
            min_id=args.min_id,
            max_id=args.max_id,
            shelf=args.shelf,
            retry_checked=args.retry_checked,
        )
    print(
        "PUBLICATION YEAR BACKFILL "
        f"examined={stats.examined} populated={stats.populated} "
        f"unknown={stats.unknown} last_gutenberg_id={stats.last_gutenberg_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
