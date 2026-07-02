#!/usr/bin/env python3
"""One-time backfill: self-host hero images for the existing corpus.

Walks the feed ZSET newest→oldest and rehosts every external hotlinked image
via scribe.rehost_article_image (fetch → 1200x675 normalize → save under
frontend/public/uploads/scraped/{id}.jpg), then updates the article hash:
    imageUrl         → /uploads/scraped/{id}.jpg
    image_source_url → original URL (doubles as the "done" marker)

Resumable by construction — articles with image_source_url set are skipped,
so the script can be killed and rerun at any point. Failures are recorded in
the arc:backfill:images:failed hash (id → reason) and skipped on rerun unless
--retry-failed is given. Nothing is deleted; a failed article keeps its
hotlink exactly as it was.

Run deliberately, during a quiet window:
    cd backend && source venv/bin/activate
    python3 backfill_images.py --dry-run          # count what would happen
    python3 backfill_images.py --limit 100        # trial batch
    python3 backfill_images.py                    # full run (~10k fetches)

Afterwards run reindex_solr.py once — Solr docs store imageUrl at index time
and go stale for backfilled articles until reindexed.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                    stream=sys.stdout)

# Importing scribe connects to Redis (module-level) and pulls in the shared
# rehost helper — one implementation for ingest and backfill.
from scribe import r, rehost_article_image

FAILED_KEY = 'arc:backfill:images:failed'


def main():
    ap = argparse.ArgumentParser(description='Self-host hero images for existing articles')
    ap.add_argument('--limit', type=int, default=0, help='stop after N rehost attempts (0 = no limit)')
    ap.add_argument('--sleep', type=float, default=0.5, help='seconds between fetches (politeness)')
    ap.add_argument('--dry-run', action='store_true', help='count and list, fetch nothing')
    ap.add_argument('--retry-failed', action='store_true', help='retry articles recorded in the failed hash')
    args = ap.parse_args()

    ids = r.zrevrange('feed', 0, -1)
    logging.info(f"feed contains {len(ids)} articles")

    stats = {'done_already': 0, 'local_or_default': 0, 'no_image': 0,
             'skipped_failed': 0, 'rehosted': 0, 'failed': 0}
    attempts = 0

    try:
        for article_id in ids:
            key = f'article:{article_id}'
            image_url = r.hget(key, 'imageUrl') or ''

            if r.hexists(key, 'image_source_url'):
                stats['done_already'] += 1
                continue
            if not image_url:
                stats['no_image'] += 1
                continue
            if not image_url.startswith(('http://', 'https://')) or 'arc-codex.com' in image_url:
                stats['local_or_default'] += 1
                continue
            if not args.retry_failed and r.hexists(FAILED_KEY, article_id):
                stats['skipped_failed'] += 1
                continue

            if args.dry_run:
                stats['rehosted'] += 1  # counts what WOULD be attempted
                attempts += 1
                if args.limit and attempts >= args.limit:
                    break
                continue

            attempts += 1
            local_path = rehost_article_image(article_id, image_url)
            if local_path:
                r.hset(key, mapping={'imageUrl': local_path, 'image_source_url': image_url})
                r.hdel(FAILED_KEY, article_id)
                stats['rehosted'] += 1
            else:
                # Reason detail is in the rehost log line just above this one
                r.hset(FAILED_KEY, article_id,
                       f"{datetime.now(timezone.utc).isoformat()} {image_url[:200]}")
                stats['failed'] += 1
                logging.warning(f"failed: {article_id} {image_url[:80]}")

            if attempts % 50 == 0:
                logging.info(f"progress: {attempts} attempted, "
                             f"{stats['rehosted']} ok, {stats['failed']} failed")
            if args.limit and attempts >= args.limit:
                logging.info(f"--limit {args.limit} reached")
                break
            time.sleep(args.sleep)
    except KeyboardInterrupt:
        logging.info("interrupted — safe to rerun, done articles are skipped")

    mode = 'DRY RUN (would rehost)' if args.dry_run else 'rehosted'
    logging.info(f"summary: {mode}={stats['rehosted']} failed={stats['failed']} "
                 f"already-done={stats['done_already']} local/default={stats['local_or_default']} "
                 f"no-image={stats['no_image']} skipped-prior-failures={stats['skipped_failed']}")
    if not args.dry_run and stats['rehosted']:
        logging.info("reminder: run reindex_solr.py to refresh imageUrl in Solr docs")


if __name__ == '__main__':
    main()
