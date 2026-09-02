#!/usr/bin/env python3
"""Conservative original-publication metadata extraction.

Only explicit first/original-publication statements near the beginning of a
Gutenberg description or stripped ebook text are accepted. Gutenberg release
dates, bare copyright notices, edition dates, and ordinary prose years are
intentionally ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

TEXT_SCAN_CHARS = 20_000
DESCRIPTION_SCAN_CHARS = 4_000

_YEAR = r"(?P<year>1\d{3}|20\d{2})"
_SUBJECT = r"(?:(?:this|the)\s+(?:book|work|novel|story|collection|volume)\s+(?:was\s+)?)?"
_PHRASE = r"(?P<phrase>first published|originally published)"
_DIRECT_PATTERN = re.compile(
    rf"^[\s\[(]*{_SUBJECT}{_PHRASE}\s*(?:in\s+)?[:;,\-]?\s*{_YEAR}\b",
    re.IGNORECASE,
)
_PUBLISHER_PATTERN = re.compile(
    rf"^[\s\[(]*{_SUBJECT}{_PHRASE}\s+by\s+[^\n]{{1,100}}?"
    rf"(?:,|\s+in)\s*{_YEAR}\b",
    re.IGNORECASE,
)
_AMBIGUOUS_CONTEXT = re.compile(
    r"\b(?:edition|translation|translated|printing|version|"
    r"e-?text|preparation of this)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OriginalPublicationEvidence:
    year: int
    source: str
    confidence: float
    evidence: str


def _extract_explicit_statement(
    material: str | None,
    *,
    source: str,
    confidence: float,
    max_chars: int,
) -> OriginalPublicationEvidence | None:
    if not material:
        return None
    current_year = datetime.now(timezone.utc).year
    lines = str(material)[:max_chars].splitlines()
    for line_number, raw_line in enumerate(lines, 1):
        line = " ".join(raw_line.split())
        if not line or len(line) > 240:
            continue
        match = _DIRECT_PATTERN.search(line) or _PUBLISHER_PATTERN.search(line)
        if not match:
            continue
        nearby = " ".join(
            " ".join(context_line.split())
            for context_line in lines[max(0, line_number - 11):line_number]
        )
        if _AMBIGUOUS_CONTEXT.search(nearby):
            continue
        year = int(match.group("year"))
        if not 1000 <= year <= current_year:
            continue
        phrase = match.group("phrase").lower()
        location = "description" if source == "gutenberg_description" else f"text line {line_number}"
        return OriginalPublicationEvidence(
            year=year,
            source=source,
            confidence=confidence,
            evidence=f'explicit "{phrase}" statement; year={year}; location={location}',
        )
    return None


def extract_original_publication(
    *,
    description: str | None = None,
    text: str | None = None,
) -> OriginalPublicationEvidence | None:
    """Return strong evidence or None; descriptions take precedence over text."""
    from_description = _extract_explicit_statement(
        description,
        source="gutenberg_description",
        confidence=0.98,
        max_chars=DESCRIPTION_SCAN_CHARS,
    )
    if from_description:
        return from_description
    return _extract_explicit_statement(
        text,
        source="gutenberg_text",
        confidence=0.95,
        max_chars=TEXT_SCAN_CHARS,
    )
