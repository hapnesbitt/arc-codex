#!/usr/bin/env python3
"""Backfill Red/Blue/Purple analysis for articles that never got a reader.

WHY THIS EXISTS
---------------
Ported from huntaegis_stack/backend/backfill_analysis.py (2026-09-07) — same
schema, same failure mode, same fix. Arc had no equivalent; this was
confirmed absent before porting, not assumed.

main.py has two writers to `analyzer:queue` (ingest-time dispatch in
publish_article, and the on-demand trigger in get_single_article behind the
bot-UA gate) — but neither one retries a job the analyzer loses. analyzer.py
holds the `analyzer:queued:{id}` dedup lock for the whole run and deletes it
only on a successful publish; a crash or an unhandled exception mid-job just
lets the TTL expire, and the article sits un-analyzed until a human happens
to open it (bot-gated) or something re-enqueues it. Arc's analyzer.py has the
identical BRPOP + hold-lock + delete-on-success pattern Hunt's does (same
crash-mid-job exposure), which is why this was ported rather than assumed
unnecessary.

This script re-drives those orphans through the *existing* queue. It does not
touch the bot gate, the reader path, or the analyzer. It is a producer that
speaks the same protocol main.py's two dispatch sites speak, via the shared
enqueue_analysis() helper (operational_state.py) so this producer's pushes
get the same queue-timeline record corpus_exporter's age gauge reads.

SAFETY PROPERTIES
-----------------
* RPUSH (tail), not LPUSH. analyzer.py does BRPOP, so reader-triggered LPUSH
  jobs are popped before anything this script adds. Live readers always win.
* Same dedup lock as main.py:531 — SET analyzer:queued:{id} '1' EX 21600 NX.
  If the lock is held the article is already queued (or the analyzer is
  mid-run on it — analyzer.py refreshes this same key to a shorter TTL at
  pickup) and we skip it.
* Throttled: never enqueues while LLEN analyzer:queue >= --max-depth. The
  backfill yields to organic depth rather than adding to it.
* Idempotent / resumable. Safe to Ctrl-C and re-run: the <10-char check skips
  completed work and the dedup lock skips in-flight work. analyzer.py is a
  second line of defence — it re-checks and no-ops on already-analyzed
  articles, so even a duplicate enqueue costs nothing.

USAGE
-----
    python3 backfill_analysis.py --dry-run          # report, enqueue nothing
    python3 backfill_analysis.py                    # run with defaults
    python3 backfill_analysis.py --max-depth 8      # allow a deeper queue
    python3 backfill_analysis.py --limit 20         # small trial run
"""
import argparse
import os
import signal
import sys
import time

import redis
from dotenv import load_dotenv

from operational_state import enqueue_analysis

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

QUEUE_KEY = 'analyzer:queue'
FEED_KEY = 'feed'
LOCK_TTL = 21_600          # 6h — identical to main.py:531
ANALYSIS_FIELDS = ('red_team_analysis', 'blue_team_analysis', 'purple_team_analysis')
MIN_ANALYSIS_LEN = 10      # same threshold main.py and analyzer.py use

# Default queue ceiling. Arc defines LIBRARY_TRANSLATION_YIELD_DEPTH = 3
# (main.py:2267) as its own "analyzer is behind" threshold for yielding
# library-translation work — reused here rather than duplicated, so the two
# "is the analyzer behind" checks in this codebase can't drift apart.
DEFAULT_MAX_DEPTH = 3
DEFAULT_BATCH = 2
DEFAULT_POLL = 20          # seconds between depth checks when throttled

_stop = False


def _handle_sigint(signum, frame):
    global _stop
    _stop = True
    print('\n⏸  Stop requested — finishing current batch, then exiting cleanly.')
    print('   Re-run the same command to resume; completed work will be skipped.')


def connect():
    url = os.environ.get('REDIS_URL')
    if not url:
        sys.exit('🔥 REDIS_URL not set — check backend/.env')
    r = redis.from_url(url, decode_responses=True)
    r.ping()
    return r


def find_orphans(r):
    """Articles in the feed with any of R/B/P missing or stub-length.

    Returns (orphans, already_queued, analyzed, total). `orphans` excludes
    articles whose dedup lock is held — those already have a job pending.
    """
    ids = r.zrevrange(FEED_KEY, 0, -1)
    orphans, already_queued, analyzed = [], [], 0

    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        p = r.pipeline()
        for aid in chunk:
            p.hmget(f'article:{aid}', *ANALYSIS_FIELDS)
        rows = p.execute()

        thin = [aid for aid, vals in zip(chunk, rows)
                if not all(len(v or '') > MIN_ANALYSIS_LEN for v in vals)]
        analyzed += len(chunk) - len(thin)

        if thin:
            p = r.pipeline()
            for aid in thin:
                p.exists(f'analyzer:queued:{aid}')
            for aid, locked in zip(thin, p.execute()):
                (already_queued if locked else orphans).append(aid)

    return orphans, already_queued, analyzed, len(ids)


def enqueue(r, article_id):
    """Mirror main.py's ingest-time dispatch exactly: same lock, same RPUSH
    (tail — readers keep priority), via enqueue_analysis()."""
    lock = f'analyzer:queued:{article_id}'
    if not r.set(lock, '1', ex=LOCK_TTL, nx=True):
        return False                       # someone queued it between scan and now
    try:
        enqueue_analysis(r, article_id, 'right')
        return True
    except Exception as e:
        r.delete(lock)                     # never leave an orphan lock behind
        print(f'  ⚠️  RPUSH failed for {article_id} ({e}) — lock released')
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true',
                    help='report what would be enqueued; change nothing')
    ap.add_argument('--limit', type=int, default=0,
                    help='enqueue at most N articles (0 = all)')
    ap.add_argument('--batch', type=int, default=DEFAULT_BATCH,
                    help=f'articles per batch (default {DEFAULT_BATCH})')
    ap.add_argument('--max-depth', type=int, default=DEFAULT_MAX_DEPTH,
                    help=f'pause while LLEN {QUEUE_KEY} >= this (default {DEFAULT_MAX_DEPTH})')
    ap.add_argument('--poll', type=int, default=DEFAULT_POLL,
                    help=f'seconds between depth checks (default {DEFAULT_POLL})')
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _handle_sigint)
    r = connect()

    print('🔎 Scanning feed for un-analyzed articles...')
    orphans, already_queued, analyzed, total = find_orphans(r)
    pct = 100 * analyzed / total if total else 0

    print(f'\n  feed articles      : {total}')
    print(f'  fully analyzed     : {analyzed} ({pct:.1f}%)')
    print(f'  already queued     : {len(already_queued)} (dedup lock held — skipping)')
    print(f'  ORPHANS to enqueue : {len(orphans)}')
    print(f'  current queue depth: {r.llen(QUEUE_KEY)} (ceiling {args.max_depth})')

    if args.limit:
        orphans = orphans[:args.limit]
        print(f'  --limit applied    : {len(orphans)}')

    if args.dry_run:
        print('\n🧪 DRY RUN — nothing enqueued.')
        if orphans:
            print('   First 10 that would be enqueued:')
            for aid in orphans[:10]:
                print(f'     {aid}')
        return

    if not orphans:
        print('\n✅ Nothing to do — no orphaned articles.')
        return

    print(f'\n🚀 Enqueuing {len(orphans)} article(s), '
          f'{args.batch} at a time, holding depth < {args.max_depth}\n')

    done = skipped = 0
    started = time.time()

    for i in range(0, len(orphans), args.batch):
        if _stop:
            break
        batch = orphans[i:i + args.batch]

        # Throttle: wait for the queue to drain below the ceiling before adding.
        waited = 0
        while not _stop:
            depth = r.llen(QUEUE_KEY)
            if depth < args.max_depth:
                break
            if waited % 300 == 0:
                print(f'  ⏳ queue depth {depth} >= {args.max_depth} — waiting for drain '
                      f'({done} enqueued so far)')
            time.sleep(args.poll)
            waited += args.poll
        if _stop:
            break

        for aid in batch:
            if enqueue(r, aid):
                done += 1
            else:
                skipped += 1

        elapsed = time.time() - started
        print(f'  📋 {done}/{len(orphans)} enqueued  '
              f'(depth={r.llen(QUEUE_KEY)}, skipped={skipped}, {elapsed/60:.1f}m elapsed)')

    print(f'\n{"⏸  Stopped early" if _stop else "✅ Complete"}: '
          f'{done} enqueued, {skipped} skipped, {time.time() - started:.0f}s')
    print(f'   queue depth now: {r.llen(QUEUE_KEY)}')
    if _stop or done < len(orphans):
        print('   Re-run the same command to resume.')


if __name__ == '__main__':
    main()
