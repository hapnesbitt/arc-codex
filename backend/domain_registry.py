#!/usr/bin/env python3
"""
domain_registry.py — shared domain predicate for Arc Codex character gating.

WHAT: resolves a domain_id (from domains.yaml) into a yes/no answer for a given
article — "is this article about domain X?" — so a character can declare
`triggers.domains: [finance]` and only wake on matching articles.

WHY VENDORED, NOT IMPORTED: the _passes_selector predicate and its regex cache
below are copied VERBATIM from School of Chat (claude_stack/backend/main.py).
SoC and arc_stack are separate services/repos/processes. A live cross-service
import would create a runtime dependency between two independently-deployed
daemons — fragile, and overkill for a ~15-line pure, stateless function. A
vendored copy is cleaner. The single source of truth that DOES matter — the
domain definitions and their measured precision — lives once, in domains.yaml.
If the predicate ever changes in SoC, mirror it here (it has been stable since
the registry refactor; selector types: none | category | classifier).

domains.yaml is reloaded when its mtime changes, so live edits take effect
without restarting the character daemon (matching how characters.yaml reloads).
"""

import os
import re
import yaml

# ── Vendored from claude_stack/backend/main.py (_compiled / _passes_selector) ──
_PATTERN_CACHE: dict[str, "re.Pattern"] = {}


def _compiled(pattern: str) -> "re.Pattern":
    """Compile-and-cache a classifier regex (case-insensitive)."""
    p = _PATTERN_CACHE.get(pattern)
    if p is None:
        p = re.compile(pattern, re.I)
        _PATTERN_CACHE[pattern] = p
    return p


def _passes_selector(a: dict, selector: dict) -> bool:
    """True if article `a` matches a selector record. Reads only title,
    category, and the lead of original_text — no fetching, no windowing."""
    stype = (selector.get("type") or "none").lower()
    if stype == "none":
        return True
    if stype == "category":
        want = (selector.get("category") or "").strip().lower()
        return (a.get("category") or "").strip().lower() == want
    if stype == "classifier":
        pat = _compiled(selector.get("pattern") or r"(?!)")
        if selector.get("title_anchor", True) and pat.search(a.get("title") or ""):
            return True
        scan = selector.get("body_scan_chars", 1500)
        lead = (a.get("original_text") or "")[:scan]
        hits = {m.group(0).lower() for m in pat.finditer(lead)}
        return len(hits) >= selector.get("body_min_distinct", 3)
    return False


# ── Domain registry (domains.yaml) ────────────────────────────────────────────
_DOMAINS_PATH = os.path.join(os.path.dirname(__file__), "..", "domains.yaml")
_CACHE: dict = {"mtime": None, "domains": {}}


def load_domains() -> dict:
    """Return {domain_id: entry} from domains.yaml, reloading on file change."""
    try:
        mtime = os.path.getmtime(_DOMAINS_PATH)
    except OSError:
        return _CACHE["domains"]
    if mtime != _CACHE["mtime"]:
        with open(_DOMAINS_PATH) as f:
            data = yaml.safe_load(f) or {}
        _CACHE["domains"] = data.get("domains", {}) or {}
        _CACHE["mtime"] = mtime
    return _CACHE["domains"]


def domain_matches(domain_id: str, article: dict) -> bool:
    """True if `article` is on-domain for `domain_id`. Unknown domain → False
    (fail closed: an undefined domain gates nothing in, rather than everything)."""
    entry = load_domains().get(domain_id)
    if not entry:
        return False
    selector = entry.get("selector") or {"type": "none"}
    return _passes_selector(article, selector)


def matching_domains(article: dict) -> list[str]:
    """Every registry domain_id whose predicate matches `article`. Used by the
    cross-domain trigger: an article at the intersection of 2+ domains is one no
    single specialist owns cleanly. Reuses the same predicates — just runs them
    all and collects the hits."""
    return [
        domain_id
        for domain_id, entry in load_domains().items()
        if _passes_selector(article, entry.get("selector") or {"type": "none"})
    ]
