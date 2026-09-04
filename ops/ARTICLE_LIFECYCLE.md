# Article lifecycle — observed behaviour

Reference doc, not config — nothing here is read by any script. It exists
because the question "what happens to an article at stage X" kept getting
re-derived from scratch across a multi-day trace (dead-id investigation,
2026-09-04 — see the RUNBOOK entry of the same date for the fix that came
out of it). Written down once here instead.

This documents what the code **does**, not a designed state machine — Arc
has no explicit `status`/`RETIRED` field on an article (confirmed by
exhaustive grep, see below). Every row below is a *combination* of
independent facts (`feed` zset membership, `article:{id}` hash presence,
`content_type`, `visibility`, `PINNED_SET` membership), not a stored flag.
Applies to both stacks — the mechanics (`retention.py`, `kasmir7.py`,
`cleanup.py`, the four social posters) are identical across arc_stack and
huntaegis_stack; only namespaces (Redis DB, directive names, character
handles) differ.

Every line is tagged **MATCHES CURRENT BEHAVIOUR** (this is what happens
today) or **WOULD BE A CHANGE** (this is a gap or an inconsistency worth
knowing about, not something any fix here touches).

## No RETIRED state exists

Searched exhaustively: `grep -rniw retired` across every `.py` in both
backends turns up only *system*-retirement comments (a poster retired, a
model retired, an old audio pass retired) — never an article-level flag.
The only article-level state axes are `content_type` (`news` default /
`reference`), `visibility` (`private` / absent), and `PINNED_SET`
membership — none of which distinguish "off the feed, still served" from
"still active". That distinction is real (see REMOVED below) but it's an
emergent property of ISR/CDN caching, not anything Arc models.

## States

### ACTIVE — in `feed` zset, `article:{id}` hash present, `content_type=news`
| axis | behaviour | |
|---|---|---|
| feed visibility | public | MATCHES CURRENT BEHAVIOUR |
| page serving | live | MATCHES CURRENT BEHAVIOUR |
| work scheduling | eligible — analyzer/audio/scribe all select from `feed` | MATCHES CURRENT BEHAVIOUR |
| social | eligible — posters select from `feed` minus `*:posted` | MATCHES CURRENT BEHAVIOUR |
| newsradio | eligible — carried live by the wiki listing (`/api/wiki/<directive>`) | MATCHES CURRENT BEHAVIOUR |

### PRIVATE — `visibility == "private"`
| axis | behaviour | |
|---|---|---|
| feed visibility | hidden from `/api/get_feed` and `/api/wiki/<directive>` (owner-only) | MATCHES CURRENT BEHAVIOUR |
| page serving | live, **ungated** at `/article/{id}` | MATCHES CURRENT BEHAVIOUR — `get_single_article` (`main.py:646`) has no visibility check at all; a private article's own page is fetchable by anyone with the id/URL. Flagged here, not fixed — likely unintentional but out of scope for this pass. |
| work scheduling | eligible — no visibility check in analyzer/audio paths | MATCHES CURRENT BEHAVIOUR |
| social | excluded — all 4 posters check `visibility == 'private'` and skip | MATCHES CURRENT BEHAVIOUR |
| newsradio | excluded — wiki route filters `visibility == 'private'` | MATCHES CURRENT BEHAVIOUR |

### PINNED (`PINNED_SET` member) / REFERENCE (`content_type == "reference"`)
| axis | behaviour | |
|---|---|---|
| feed visibility | public | MATCHES CURRENT BEHAVIOUR |
| page serving | live | MATCHES CURRENT BEHAVIOUR |
| work scheduling | eligible | MATCHES CURRENT BEHAVIOUR |
| social | eligible | MATCHES CURRENT BEHAVIOUR |
| newsradio | eligible | MATCHES CURRENT BEHAVIOUR |
| trim exempt | excluded from every bulk age/orphan trim path (`retention.trim_by_hours`, kasmir7 bulk flows) | MATCHES CURRENT BEHAVIOUR |

### REMOVED — deleted via kasmir7 delete flow, `retention.trim_by_hours`, or `cleanup.py`'s orphan sweep
| axis | behaviour | |
|---|---|---|
| feed visibility | gone | MATCHES CURRENT BEHAVIOUR |
| page serving | **stale-cache 200 until the next failed ISR revalidation, then 404** | MATCHES CURRENT BEHAVIOUR — confirmed live: a hash deleted 13 days prior still served `/article/{id}` → 200 while `/api/article/{id}` → 404. This is deliberate (Ross): it's what keeps old Bluesky/Mastodon permalinks resolving. **Do not change.** |
| work scheduling | not reselected (`feed`-driven); any already-in-flight `analyzer:queue` entry logs "not found in Redis — skipping" once and drops — one-shot, not a retry loop | MATCHES CURRENT BEHAVIOUR |
| social | not reselected; `*:posted` / `characters:posted:*` membership persists | as of 2026-09-04: `*:posted` now age-prunes on a `posted_set_days` window (was: unbounded forever) — see RUNBOOK. `characters:posted:*` is unchanged, still cleared immediately on delete (out of scope this pass). |
| newsradio | not discoverable via wiki scrape once the wiki listing regenerates; an orphaned `uploads/audio/{id}.mp3` may survive if nothing else cleaned it | MATCHES CURRENT BEHAVIOUR |
| satellites purged | comments / translations / grade / `characters:*` / images / audio | as of 2026-09-04: cleared by `cleanup.py`'s orphan sweep too, not just `retention.py`'s trim and kasmir7's delete flows — see RUNBOOK "orphan sweep parity". |

## Consumer behaviour on a REMOVED id (feed-lookup failure), one line each

| consumer | candidate source | on lookup failure |
|---|---|---|
| analyzer queue (`analyzer:queue`) | pushed at ingest/on-demand, not re-derived from `feed` | pops once, `r.exists()` fails → logs, drops |
| audio pass (`audio_backfill.py`) | `zrevrangebyscore('feed', ...)`, live | never selected, no error |
| social posters (fb/bsky/mastodon/threads) | `set(all_article_ids())` from `feed`, minus `*:posted` | never in the candidate set, silently skipped |
| sitemap/RSS (`kasmir7.generate_sitemap/rss/news_sitemap`) | live `feed` scan | absent from the next generated file |
| newsradio's builder (`build_wiki_show.py`) | scrapes `/wiki/<directive>` HTML, matches local `uploads/audio/*.mp3` | can't appear once the wiki page regenerates; a surviving `.mp3` is a harmless orphan |
| wiki taxonomy page (`/api/wiki/<directive>`) | live `ZRANGE feed` + `HMGET article:{id}` | `hmget` returns all-None → directive match fails → dropped from the next render |

Every one of these degrades silently. No exceptions, no retry loops.
