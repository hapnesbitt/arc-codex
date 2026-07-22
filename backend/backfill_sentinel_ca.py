#!/usr/bin/env python3
"""Backfill Sentinel + Counter-Analyst for articles that missed them at ingest.

WHY THIS EXISTS
---------------
Unlike Red/Blue/Purple (lazy, on first view — see backfill_analysis.py), the
Sentinel forensic pass and the Counter-Analyst seed comment are generated
*synchronously at ingest* by scribe.py / manual_publisher.py. When scribe is
restarted mid-cycle (e.g. the 09:26 restart) the articles in flight are
persisted to the feed but never get their sentinel/CA pass — and nothing ever
re-drives them, so characters parked on those articles spin until the 7-day
give-up. Known backlog from that window: Arc ~184 sentinel + 1 CA, Hunt 5.

This is NOT a substitute for backfill_analysis.py (that re-drives R/B/P through
analyzer:queue). It runs the two synchronous passes directly, via the exact
code paths manual_publisher uses:
  - Sentinel: run_sentinel_analysis() → publish_analysis(..., 'sentinel', ...)
    (the stream_consumer service persists it to article:{id}.sentinel_analysis)
  - Counter-Analyst: run_counter_analyst() posts the comment straight to Redis.

CANDIDATE SOURCE (choose exactly one — there is deliberately NO unbounded
default; a whole-feed scan would re-analyse hundreds of intentionally-thin
historical articles, not the restart orphans):
  * explicit article IDs as positional args, or --ids-file  → straight from
    the scribe logs around the incident. This is the faithful path.
  * --since EPOCH   → feed articles published at/after EPOCH (the restart time).
  * --newest N      → the N newest feed articles.
Whatever the source, the idempotency filters below decide what actually runs.

SAFETY PROPERTIES
-----------------
* Idempotent by field. An article gets a sentinel pass only if its
  sentinel_analysis field is <=20 chars, and a CA pass only if no comment by
  'A.R.C. Counter-Analyst' exists. Re-running skips completed work.
* Respects analyzer hold flags. An article whose analyzer:queued:{id} hold is
  set is being worked (or has an R/B/P job pending) — skipped this pass so we
  never pile a generation onto an article the analyzer owns. Re-run picks it up.
* Serial with a 30-60s gap between processed articles — gentle on the shared
  Ollama host. No concurrency.
* Resumable. Safe to Ctrl-C and re-run; the idempotency checks skip done work.

DEPENDENCY: the stream_consumer service must be running for sentinel results to
land on the hash (publish_analysis only enqueues to analysis:pending). CA
comments are written directly and need no consumer.

USAGE
-----
    # Hunt smoke test first (5 restart orphans), dry then live:
    python3 backfill_sentinel_ca.py --since $(date -d '2026-07-21 09:26' +%s) --dry-run
    python3 backfill_sentinel_ca.py --since $(date -d '2026-07-21 09:26' +%s) --limit 5
    # Explicit IDs pulled from the scribe log:
    python3 backfill_sentinel_ca.py 0690553513c0... 78e8d570033...
    python3 backfill_sentinel_ca.py --ids-file /tmp/restart_orphans.txt
"""
import argparse
import json
import os
import random
import signal
import sys
import time

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Importing manual_publisher connects Redis, ensures the stream group, and
# loads PROMPTS at import time — all idempotent. Its watch loop is __main__
# guarded, so nothing daemonizes here.
from manual_publisher import run_sentinel_analysis, run_counter_analyst, stream_redis as r
from stream_utils import publish_analysis

FEED_KEY = 'feed'
CA_AUTHOR = 'A.R.C. Counter-Analyst'
SENTINEL_FIELD = 'sentinel_analysis'
SENTINEL_MIN_LEN = 20         # idempotency: >20 chars means sentinel is present
MIN_BODY_LEN = 50             # below this there is nothing worth analysing
HOLD_KEY = 'analyzer:queued:{}'
DEFAULT_GAP = (30, 60)        # seconds between processed articles

_stop = False


def _handle_sigint(signum, frame):
    global _stop
    _stop = True
    print('\n⏸  Stop requested — finishing current article, then exiting cleanly.')
    print('   Re-run the same command to resume; completed work will be skipped.')


def has_ca(article_id):
    """True if a Counter-Analyst comment already exists (idempotency guard).

    Mirrors character_builder.has_comment_by, including the legacy-JSON entry
    fallback, without importing character_builder's heavier module setup.
    """
    for entry in r.lrange(f"comments:{article_id}", 0, -1):
        author = r.hget(f"comment:{entry}", "author")
        if author is None:
            try:
                author = json.loads(entry).get("author")
            except Exception:
                continue
        if author == CA_AUTHOR:
            return True
    return False


def gather_ids(args):
    """Resolve the candidate ID list (newest-first) from the chosen source."""
    if args.ids:
        return args.ids
    if args.ids_file:
        with open(args.ids_file) as f:
            return [ln.split('#', 1)[0].strip() for ln in f
                    if ln.split('#', 1)[0].strip()]
    if args.since is not None:
        return r.zrevrangebyscore(FEED_KEY, '+inf', args.since)
    if args.newest:
        return r.zrevrange(FEED_KEY, 0, args.newest - 1)
    return None


def filter_candidates(ids):
    """Keep only IDs that still need sentinel and/or CA.

    Returns (candidates, n_sentinel, n_ca) where candidates is an ordered list
    of (aid, need_sentinel, need_ca).
    """
    candidates, n_sentinel, n_ca = [], 0, 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        p = r.pipeline()
        for aid in chunk:
            p.hget(f'article:{aid}', SENTINEL_FIELD)
        sentinels = p.execute()
        for aid, sent in zip(chunk, sentinels):
            need_sentinel = len(sent or '') <= SENTINEL_MIN_LEN
            need_ca = not has_ca(aid)
            if need_sentinel or need_ca:
                candidates.append((aid, need_sentinel, need_ca))
                n_sentinel += need_sentinel
                n_ca += need_ca
    return candidates, n_sentinel, n_ca


def process(aid, need_sentinel, need_ca):
    """Run the needed passes for one article. Returns a list of what was done."""
    article = r.hgetall(f"article:{aid}")
    if not article:
        print(f'  ⏭  {aid[:12]} skipped — no such article hash')
        return []
    text = (article.get('original_text') or '').strip()
    if len(text) < MIN_BODY_LEN:
        print(f'  ⏭  {aid[:12]} skipped — body too short ({len(text)} chars)')
        return []

    done = []
    if need_sentinel:
        data = run_sentinel_analysis(text)
        if data:
            publish_analysis(r, aid, 'sentinel', json.dumps(data))
            done.append('sentinel')
        else:
            print(f'  ⚠️  {aid[:12]} sentinel produced no result (left for retry)')
    if need_ca:
        if run_counter_analyst(text, aid, r):
            done.append('CA')
        else:
            print(f'  ⚠️  {aid[:12]} counter-analyst produced no result (left for retry)')
    return done


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ids', nargs='*', help='explicit candidate article IDs')
    ap.add_argument('--ids-file', help='file of candidate IDs, one per line (# comments ok)')
    ap.add_argument('--since', type=int,
                    help='candidates = feed articles with score (publish epoch) >= this')
    ap.add_argument('--newest', type=int, default=0,
                    help='candidates = the N newest feed articles')
    ap.add_argument('--dry-run', action='store_true', help='report candidates; generate nothing')
    ap.add_argument('--limit', type=int, default=0, help='process at most N candidates (0 = all)')
    ap.add_argument('--gap-min', type=int, default=DEFAULT_GAP[0],
                    help=f'min seconds between processed articles (default {DEFAULT_GAP[0]})')
    ap.add_argument('--gap-max', type=int, default=DEFAULT_GAP[1],
                    help=f'max seconds between processed articles (default {DEFAULT_GAP[1]})')
    args = ap.parse_args()

    ids = gather_ids(args)
    if ids is None:
        ap.error('no candidate source — give explicit IDs, --ids-file, --since, or --newest '
                 '(there is no unbounded whole-feed default by design)')

    signal.signal(signal.SIGINT, _handle_sigint)

    print(f'🔎 {len(ids)} candidate ID(s) from source; checking what still needs work...')
    candidates, n_sentinel, n_ca = filter_candidates(ids)
    print(f'\n  need work           : {len(candidates)}')
    print(f'    need sentinel     : {n_sentinel}')
    print(f'    need CA           : {n_ca}')

    if args.limit:
        candidates = candidates[:args.limit]
        print(f'  --limit applied     : {len(candidates)}')

    if args.dry_run:
        print('\n🧪 DRY RUN — nothing generated.')
        for aid, ns, nc in candidates[:15]:
            flags = ','.join(f for f, on in (('sentinel', ns), ('CA', nc)) if on)
            print(f'     {aid[:16]}  [{flags}]')
        if len(candidates) > 15:
            print(f'     ... and {len(candidates) - 15} more')
        return

    if not candidates:
        print('\n✅ Nothing to do — every candidate already has sentinel + CA.')
        return

    print(f'\n🚀 Processing {len(candidates)} article(s), serial, '
          f'{args.gap_min}-{args.gap_max}s gap, respecting analyzer holds\n')

    done = held = 0
    started = time.time()
    for idx, (aid, need_sentinel, need_ca) in enumerate(candidates):
        if _stop:
            break
        if r.exists(HOLD_KEY.format(aid)):
            held += 1
            print(f'  🔒 {aid[:12]} held by analyzer — skipping this pass')
            continue

        # Re-check CA at processing time: the scan may be minutes old.
        if need_ca and has_ca(aid):
            need_ca = False
        if not need_sentinel and not need_ca:
            continue

        result = process(aid, need_sentinel, need_ca)
        if result:
            done += 1
            print(f'  ✅ {aid[:12]}  {"+".join(result)}  '
                  f'({done} done, {held} held, {(time.time()-started)/60:.1f}m)')

        if not _stop and idx < len(candidates) - 1:
            time.sleep(random.uniform(args.gap_min, args.gap_max))

    print(f'\n{"⏸  Stopped early" if _stop else "✅ Complete"}: '
          f'{done} processed, {held} held (skipped), {time.time()-started:.0f}s')
    if _stop or held:
        print('   Re-run the same command to resume; done work is skipped.')


if __name__ == '__main__':
    main()
