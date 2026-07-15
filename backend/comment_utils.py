#!/usr/bin/env python3
"""Shared reader for the auto-seeded Counter-Analyst comment.

Single source of truth for every social poster (facebook/bluesky/mastodon/
linkedin) and any future consumer. Each poster used to carry its own copy of
this reader; three of them (facebook/bluesky/mastodon) shared a byte-identical
bug — json.loads() on a bare-UUID list entry, then reading a 'body' field that
does not exist — so the Counter-Analyst comment never reached those channels
(it silently fell back to a purple-team excerpt after a full 60s wait). This
module is that reader done once, matching analyzer.py's correct hgetall pattern.

Storage shape:
  comments:<article_id>   LIST of comment UUIDs
  comment:<uuid>          HASH {author, text, article_id, parent_id, timestamp}
"""
import time

COUNTER_ANALYST_AUTHOR = "A.R.C. Counter-Analyst"
_LEAD = "the article"


def _s(v):
    """Coerce str-or-bytes → str (posters differ on decode_responses)."""
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


def get_counter_analyst_comment(r, article_id, wait_seconds=20):
    """Return the Counter-Analyst comment text for an article, or None.

    The comment is normally already present at poll time (scribe seeds it at
    publish); the wait is a safety net for an article whose counter-analyst
    generation is still in flight. 20s, not 60 — if it is not there within a
    few polls it was a generation failure and will never appear. Redis errors
    fail closed (return None → caller uses its purple-excerpt fallback).
    """
    deadline = time.time() + max(0, wait_seconds)
    while True:
        try:
            for cid in r.lrange(f"comments:{article_id}", 0, -1):
                data = r.hgetall(f"comment:{_s(cid)}")
                if not data:
                    continue
                d = {_s(k): _s(v) for k, v in data.items()}
                if d.get("author") == COUNTER_ANALYST_AUTHOR:
                    text = (d.get("text", "") or "").strip()
                    if text.lower().startswith(_LEAD):
                        text = "This article" + text[len(_LEAD):]
                    return text or None
        except Exception:
            pass
        if time.time() >= deadline:
            return None
        time.sleep(5)
