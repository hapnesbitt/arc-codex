#!/usr/bin/env python3
"""
arc_eval.py — regression detection for Arc's A.R.C. analyses.

Freezes the Red/Blue/Purple output for a fixed set of articles, then tells you
what moved after a prompts.yaml edit or a model swap. Read-only against Redis
unless you explicitly ask for --requeue.

    ./arc_eval.py freeze                 # snapshot current output as the baseline
    ./arc_eval.py compare                # diff current output against the baseline
    ./arc_eval.py compare --verbose      # ...with previews of what changed

Exit codes: 0 clean, 1 regressions found, 2 could not run.

The point is not to judge whether an analysis is GOOD — nothing here can do
that. It is to catch an analysis that silently got shorter, lost a section,
stopped citing ARC patterns, or diverged wholesale after a change you thought
was cosmetic.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import redis
except ImportError:
    sys.exit("2: pip install redis (use the backend venv)")

# --- configuration -----------------------------------------------------------

STACK_ROOT = Path(os.environ.get("ARC_STACK_ROOT", "/home/www/arc_stack"))
BASELINE = Path(os.environ.get("ARC_EVAL_BASELINE", STACK_ROOT / "eval" / "baseline.json"))
REDIS_DB = int(os.environ.get("ARC_EVAL_DB", "0"))
SAMPLE_SIZE = int(os.environ.get("ARC_EVAL_N", "15"))

# Sections we expect. Discovered from the hash at runtime; this is the fallback
# ordering and the set we report on.
SECTION_HINTS = ("red", "blue", "purple")

# Thresholds for calling something a regression.
LENGTH_DROP = 0.35      # section lost >35% of its characters
SIMILARITY_FLOOR = 0.45  # token overlap below this = wholesale rewrite

ARC_PATTERN = re.compile(r"\bARC-\d{4}\b")
WORD = re.compile(r"[a-z0-9']+")


# --- redis -------------------------------------------------------------------

def load_redis_password():
    """Read REDIS_PASSWORD out of backend/.env without sourcing it as shell.

    Sourcing .env from bash breaks on unquoted spaces in values; python-dotenv
    and this parser do not care.
    """
    env = STACK_ROOT / "backend" / ".env"
    if not env.exists():
        return os.environ.get("REDIS_PASSWORD")
    for line in env.read_text(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("REDIS_PASSWORD="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get("REDIS_PASSWORD")


def connect():
    pw = load_redis_password()
    if not pw:
        sys.exit("2: no REDIS_PASSWORD found in backend/.env or environment")
    r = redis.Redis(decode_responses=True, password=pw, db=REDIS_DB)
    r.ping()
    return r


# --- extraction --------------------------------------------------------------

def find_section_fields(hash_keys):
    """Locate the analysis fields without hardcoding their names.

    Arc stores these as *_team_analysis, but the naming has moved before and
    a hardcoded field name that silently matches nothing is exactly the class
    of bug this tool exists to catch.
    """
    found = {}
    for key in hash_keys:
        low = key.lower()
        if "analysis" not in low:
            continue
        for hint in SECTION_HINTS:
            if hint in low:
                found.setdefault(hint, key)
    return found


def tokens(text):
    return set(WORD.findall(text.lower()))


def profile(text):
    """Reduce a section to the things worth comparing."""
    text = (text or "").strip()
    return {
        "present": bool(text),
        "chars": len(text),
        "lines": text.count("\n") + 1 if text else 0,
        "arc_patterns": sorted(set(ARC_PATTERN.findall(text))),
        "tokens": sorted(tokens(text)),
        "preview": text[:200],
    }


def snapshot(r, article_ids):
    out = {}
    for aid in article_ids:
        h = r.hgetall(f"article:{aid}")
        if not h:
            out[aid] = {"missing": True}
            continue
        fields = find_section_fields(h.keys())
        rec = {
            "missing": False,
            "title": (h.get("title") or "")[:120],
            "source_lang": h.get("source_lang") or "English",
            "fields_seen": fields,
            "sections": {},
        }
        for hint in SECTION_HINTS:
            field = fields.get(hint)
            rec["sections"][hint] = profile(h.get(field, "") if field else "")
        out[aid] = rec
    return out


def pick_sample(r, n):
    """Newest n articles that currently have all three sections.

    Deliberately biased toward complete articles: a baseline built on
    half-analyzed stories reports noise forever.
    """
    ids = r.zrevrange("feed", 0, max(n * 6, 100) - 1)
    chosen = []
    for aid in ids:
        h = r.hgetall(f"article:{aid}")
        if not h:
            continue
        fields = find_section_fields(h.keys())
        if len(fields) < 3:
            continue
        if not all((h.get(f) or "").strip() for f in fields.values()):
            continue
        chosen.append(aid)
        if len(chosen) >= n:
            break
    return chosen


# --- comparison --------------------------------------------------------------

def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def compare_section(old, new):
    """Return (list_of_regressions, list_of_notes)."""
    regressions, notes = [], []

    if old["present"] and not new["present"]:
        regressions.append("section disappeared")
        return regressions, notes
    if not old["present"] and new["present"]:
        notes.append("section appeared (was empty in baseline)")
        return regressions, notes
    if not old["present"] and not new["present"]:
        return regressions, notes

    if old["chars"]:
        delta = (new["chars"] - old["chars"]) / old["chars"]
        if delta <= -LENGTH_DROP:
            regressions.append(f"length -{abs(delta):.0%} ({old['chars']}\u2192{new['chars']} chars)")
        elif abs(delta) >= 0.15:
            notes.append(f"length {delta:+.0%} ({old['chars']}\u2192{new['chars']} chars)")

    sim = jaccard(old["tokens"], new["tokens"])
    if sim < SIMILARITY_FLOOR:
        regressions.append(f"content diverged (token overlap {sim:.0%})")
    elif sim < 0.75:
        notes.append(f"reworded (token overlap {sim:.0%})")

    lost = set(old["arc_patterns"]) - set(new["arc_patterns"])
    gained = set(new["arc_patterns"]) - set(old["arc_patterns"])
    if old["arc_patterns"] and not new["arc_patterns"]:
        regressions.append("stopped citing ARC patterns entirely")
    elif lost:
        notes.append(f"dropped patterns: {', '.join(sorted(lost))}")
    if gained:
        notes.append(f"new patterns: {', '.join(sorted(gained))}")

    return regressions, notes


# --- commands ----------------------------------------------------------------

def cmd_freeze(args):
    r = connect()
    ids = args.ids or pick_sample(r, args.n)
    if not ids:
        sys.exit("2: no fully-analyzed articles found in the feed to baseline")
    data = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db": REDIS_DB,
        "article_ids": ids,
        "snapshot": snapshot(r, ids),
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(data, indent=1))
    print(f"baseline: {len(ids)} articles \u2192 {BASELINE}")
    for aid in ids:
        rec = data["snapshot"][aid]
        sizes = " ".join(f"{k}={rec['sections'][k]['chars']}" for k in SECTION_HINTS)
        print(f"  {aid[:12]}  {sizes}  {rec['title'][:48]}")
    print("\nRe-run `compare` after any prompts.yaml edit or model change.")
    return 0


def cmd_compare(args):
    if not BASELINE.exists():
        sys.exit(f"2: no baseline at {BASELINE} \u2014 run `freeze` first")
    base = json.loads(BASELINE.read_text())
    r = connect()

    if args.requeue:
        print("!! requeueing for re-analysis \u2014 this WRITES to analyzer:queue")
        for aid in base["article_ids"]:
            r.rpush("analyzer:queue", aid)
        print(f"   pushed {len(base['article_ids'])} ids. Wait for the analyzer, "
              f"then run compare again without --requeue.")
        return 0

    now = snapshot(r, base["article_ids"])
    total_reg = 0

    print(f"baseline {base['created']}  \u2192  now\n")
    for aid in base["article_ids"]:
        old, new = base["snapshot"][aid], now[aid]
        if new.get("missing"):
            print(f"  {aid[:12]}  GONE \u2014 no longer in Redis (trimmed from feed?)")
            continue
        if old.get("missing"):
            continue

        lines = []
        for hint in SECTION_HINTS:
            regs, notes = compare_section(old["sections"][hint], new["sections"][hint])
            total_reg += len(regs)
            for msg in regs:
                lines.append(f"      REGRESSION  {hint:<7} {msg}")
            for msg in notes:
                lines.append(f"      note        {hint:<7} {msg}")

        if lines or args.verbose:
            print(f"  {aid[:12]}  {old['title'][:56]}")
            print("\n".join(lines) if lines else "      unchanged")
            if args.verbose:
                for hint in SECTION_HINTS:
                    p = new["sections"][hint]["preview"].replace("\n", " ")
                    print(f"      {hint:<7} now: {p[:110]}")
            print()

    if total_reg:
        print(f"\n{total_reg} regression(s). Read them before you ship the prompt change.")
        return 1
    print("\nNo regressions. Rewording and length drift under threshold are notes, not failures.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("freeze", help="snapshot current output as the baseline")
    f.add_argument("-n", type=int, default=SAMPLE_SIZE, help=f"sample size (default {SAMPLE_SIZE})")
    f.add_argument("--ids", nargs="*", help="specific article ids instead of the newest complete ones")
    f.set_defaults(func=cmd_freeze)

    c = sub.add_parser("compare", help="diff current output against the baseline")
    c.add_argument("--verbose", action="store_true", help="show previews even when unchanged")
    c.add_argument("--requeue", action="store_true",
                   help="WRITES: push the baseline ids onto analyzer:queue to force re-analysis")
    c.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    try:
        sys.exit(args.func(args))
    except redis.exceptions.RedisError as e:
        sys.exit(f"2: redis: {e}")


if __name__ == "__main__":
    main()
