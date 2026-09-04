#!/usr/bin/env python3
"""
Arc Codex Cleanup Script
backend/cleanup.py

Non-interactive maintenance script — safe to schedule via cron.
Runs orphan purges on Redis and Solr, logs results.

Cron (Sunday 1am, before cold backup):
  0 1 * * 0 /home/www/arc_stack/backend/venv/bin/python3 /home/www/arc_stack/backend/cleanup.py >> /home/www/arc_stack/logs/cleanup.log 2>&1

Also safe to run manually at any time — read-only scan first, then purge.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# purge_article_satellites / _character_state_keys are the same helpers
# retention.py's trim_by_hours and every kasmir7.py delete flow already run
# after removing an article's hash — comments, cached translations, the
# grade cache, per-persona character state, rehosted images, and narrated
# audio. purge_redis_orphans below was the one deletion path that skipped
# them (see ops/RUNBOOK.md — orphan-hash sweep parity, 2026-09-04): an
# orphan here is only "no feed entry", not "never fully published", so it
# can carry real satellite state, not just a stray hash from a failed
# publish. Import deferred to module scope (not inside main()) so a
# missing retention.py fails loudly at startup rather than mid-run.
from retention import purge_article_satellites, _character_state_keys

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [CLEANUP] - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger('cleanup')

# --- CONFIG ---
REDIS_PASSWORD = os.environ['REDIS_PASSWORD']
SOLR_URL       = os.environ.get('SCRIBE_SOLR_URL', 'http://localhost:8983/solr/feeds/')

# Rehosted hero images live here, named {article_id}.jpg plus {article_id}-{w}.webp
# variants (see scribe.rehost_article_image). Same derivation scribe uses.
_BACKEND_DIR      = os.path.dirname(os.path.abspath(__file__))
SCRAPED_IMAGE_DIR = os.path.join(os.path.dirname(_BACKEND_DIR),
                                 'frontend', 'public', 'uploads', 'scraped')

# Narrated audio dir, for _count_satellites' preview only — the actual
# removal is purge_article_satellites' job (retention.AUDIO_DIR). Kept as
# a separate read here rather than importing retention.AUDIO_DIR so this
# count never silently drifts if a future retention.py reshapes that path.
AUDIO_DIR = os.path.join(os.path.dirname(_BACKEND_DIR),
                         'frontend', 'public', 'uploads', 'audio')


def get_image_retention_days():
    """[retention].image_days from the site cfg, or None (with a loud log) if
    it is missing/unloadable — in which case the scraped-image purge is skipped
    while the Redis/Solr purges still run."""
    try:
        from site_config import load_site_config
        return int(load_site_config()["retention"]["image_days"])
    except Exception as e:
        logger.warning(f"⚠️  [retention].image_days unavailable ({e}) — "
                       f"skipping scraped-image purge")
        return None


def get_posted_set_retention_days():
    """[retention].posted_set_days from the site cfg, or None (with a loud
    log) if missing/unloadable — in which case the posted-set prune is
    skipped while every other purge still runs."""
    try:
        from site_config import load_site_config
        return int(load_site_config()["retention"]["posted_set_days"])
    except Exception as e:
        logger.warning(f"⚠️  [retention].posted_set_days unavailable ({e}) — "
                       f"skipping posted-set prune")
        return None


def get_redis():
    import redis
    r = redis.Redis(decode_responses=True, password=REDIS_PASSWORD)
    r.ping()
    return r


def get_solr():
    import pysolr
    solr = pysolr.Solr(SOLR_URL)
    solr.ping()
    return solr


def _count_satellites(r, article_id, char_state_keys) -> int:
    """Best-effort, read-only count of satellite state purge_article_satellites
    is about to remove for one article id — comments, cached translations,
    the grade cache, per-persona character state, rehosted images, and any
    narrated audio. Sized before the delete so the log line below can say
    what the sweep actually cleared, not just how many hashes it touched."""
    count = 0
    count += r.llen(f"comments:{article_id}")
    langs = r.smembers(f"translation:langs:{article_id}")
    if langs:
        count += len(langs) + 1  # each translation:{id}:{lang} + the langs set itself
    if r.exists(f"grade:{article_id}"):
        count += 1
    for k in char_state_keys:
        if k.startswith("characters:skip_attempts:"):
            if r.hexists(k, article_id):
                count += 1
        elif k.startswith("characters:skipped:"):
            if r.zscore(k, article_id) is not None:
                count += 1
        else:  # characters:pending: / characters:posted: — SETs
            if r.sismember(k, article_id):
                count += 1
    try:
        count += len([n for n in os.listdir(SCRAPED_IMAGE_DIR)
                      if n.split('-', 1)[0].split('.', 1)[0] == article_id]) \
            if os.path.isdir(SCRAPED_IMAGE_DIR) else 0
    except OSError:
        pass
    if os.path.exists(os.path.join(AUDIO_DIR, f"{article_id}.mp3")):
        count += 1
    return count


def purge_redis_orphans(r) -> tuple[int, int]:
    """
    Remove article:{id} hashes that have no entry in the feed sorted set,
    plus every satellite key/file still hanging off them (purge_article_
    satellites — the same call retention.py's age-based trim and every
    kasmir7.py delete flow already make; this was the one deletion path
    that skipped it). These orphans accumulate from failed publishes,
    deduped submissions, etc. — but also, it turns out, from articles that
    fell out of `feed` some other way while still fully published (see
    ops/RUNBOOK.md), so satellite state is not a rare case here.
    Returns (hashes purged, satellite items cleared).
    """
    feed_ids = set(r.zrange('feed', 0, -1))
    logger.info(f"Feed articles : {len(feed_ids)}")

    cursor = 0
    orphans = []
    scanned = 0

    while True:
        cursor, keys = r.scan(cursor, match='article:*', count=500)
        for key in keys:
            article_id = key.split(':', 1)[1]
            if article_id not in feed_ids:
                orphans.append(key)
        scanned += len(keys)
        if cursor == 0:
            break

    logger.info(f"article:* keys: {scanned}")
    logger.info(f"Redis orphans : {len(orphans)}")

    if not orphans:
        logger.info("✅ Redis clean — no orphans found")
        return 0, 0

    char_state_keys = _character_state_keys(r)
    satellites_cleared = 0
    for key in orphans:
        article_id = key.split(':', 1)[1]
        satellites_cleared += _count_satellites(r, article_id, char_state_keys)
        purge_article_satellites(r, article_id, char_state_keys)

    # Delete the hashes themselves in a batch, same as before.
    pipe = r.pipeline()
    for key in orphans:
        pipe.delete(key)
    pipe.execute()

    logger.info(f"✅ Purged {len(orphans)} orphaned Redis hash(es)")
    logger.info(f"✅ Cleared {satellites_cleared} orphaned satellite item(s) "
                f"(comments, translations, grade, character state, images, audio)")
    return len(orphans), satellites_cleared


def purge_solr_orphans(r, solr) -> int:
    """
    Remove Solr documents with no matching Redis article hash.
    Returns count of purged documents.
    """
    feed_ids = set(r.zrange('feed', 0, -1))

    rows     = 1000
    start    = 0
    orphans  = []
    scanned  = 0

    while True:
        results = solr.search('*:*', fl='id', rows=rows, start=start)
        if not results.docs:
            break
        for doc in results.docs:
            doc_id = doc.get('id', '')
            if doc_id not in feed_ids:
                orphans.append(doc_id)
        scanned += len(results.docs)
        if scanned >= results.hits:
            break
        start += rows

    logger.info(f"Solr documents: {scanned}")
    logger.info(f"Solr orphans  : {len(orphans)}")

    if not orphans:
        logger.info("✅ Solr clean — no orphans found")
        return 0

    # Delete orphans from Solr
    for doc_id in orphans:
        solr.delete(id=doc_id)
    solr.commit()

    logger.info(f"✅ Purged {len(orphans)} orphaned Solr document(s)")
    return len(orphans)


def purge_processed_hashes(r) -> int:
    """
    Remove entries from processed_hashes that are no longer in the feed.
    Keeps the dedup set lean — it grows unbounded otherwise.
    """
    feed_ids    = set(r.zrange('feed', 0, -1))
    all_hashes  = r.smembers('processed_hashes')
    stale       = [h for h in all_hashes if h not in feed_ids]

    logger.info(f"processed_hashes total : {len(all_hashes)}")
    logger.info(f"Stale processed hashes : {len(stale)}")

    if not stale:
        logger.info("✅ processed_hashes clean")
        return 0

    pipe = r.pipeline()
    for h in stale:
        pipe.srem('processed_hashes', h)
    pipe.execute()

    logger.info(f"✅ Removed {len(stale)} stale processed_hashes entries")
    return len(stale)


def purge_scraped_images(r, solr, max_age_days: int) -> int:
    """Delete rehosted scraped images older than max_age_days, but only when no
    live article references them.

    Reference-check FIRST: build the set of live article ids (feed zset, plus
    any Solr doc ids as belt-and-braces), then delete second. A file is removed
    only when BOTH hold: its article id is unreferenced AND its mtime is older
    than the threshold. An unreferenced-but-young file is kept (grace window); a
    referenced-but-old file is kept (still in use). Filenames embed the article
    id: {id}.jpg and {id}-{w}.webp, so the id is the stem up to the first '-'.
    """
    if not os.path.isdir(SCRAPED_IMAGE_DIR):
        logger.info(f"Scraped dir absent ({SCRAPED_IMAGE_DIR}) — skipping image purge")
        return 0

    referenced = set(r.zrange('feed', 0, -1))
    if solr is not None:
        start, rows = 0, 1000
        while True:
            results = solr.search('*:*', fl='id', rows=rows, start=start)
            if not results.docs:
                break
            referenced.update(d.get('id', '') for d in results.docs)
            start += rows
            if start >= results.hits:
                break
    logger.info(f"Referenced article ids : {len(referenced)}")

    cutoff = time.time() - max_age_days * 86400
    deleted = kept_referenced = kept_young = 0
    freed_bytes = 0

    for name in os.listdir(SCRAPED_IMAGE_DIR):
        path = os.path.join(SCRAPED_IMAGE_DIR, name)
        if not os.path.isfile(path):
            continue
        article_id = os.path.splitext(name)[0].split('-', 1)[0]
        if article_id in referenced:
            kept_referenced += 1
            continue
        try:
            if os.path.getmtime(path) >= cutoff:
                kept_young += 1
                continue
            size = os.path.getsize(path)
            os.remove(path)
        except OSError as e:
            logger.warning(f"  ⚠️  could not remove {name}: {e}")
            continue
        deleted += 1
        freed_bytes += size

    logger.info(f"Scraped images > {max_age_days}d & unreferenced deleted : {deleted} "
                f"({freed_bytes / 1_048_576:.1f} MB freed)")
    logger.info(f"  kept (referenced)    : {kept_referenced}")
    logger.info(f"  kept (within {max_age_days}d): {kept_young}")
    return deleted


def purge_stale_posted_entries(r, max_age_days: int) -> int:
    """Age-prune the facebook/bluesky/mastodon/threads :posted ZSETs.

    These are the posters' only anti-duplicate-repost guard (member=article
    id, score=post unix ts since the 2026-09-04 SET→ZSET migration — see
    ops/migrate_posted_sets_to_zset.py). Pruned by AGE from the post event,
    not tied to the article's own deletion: an id can be re-ingested (same
    md5(title+snippet) hash) any time up to and past when retention.py
    trims the original article out of `feed`, so clearing a :posted entry
    the instant its article disappears would reopen the repost window
    while a duplicate could still realistically surface. See
    [retention].posted_set_days in arc.cfg for the window and its
    derivation. Returns total entries removed across all four sets.
    """
    cutoff = time.time() - max_age_days * 86400
    total = 0
    for key in ("facebook:posted", "bluesky:posted", "mastodon:posted", "threads:posted"):
        try:
            removed = r.zremrangebyscore(key, "-inf", cutoff)
        except Exception as e:
            logger.warning(f"  ⚠️  could not prune {key}: {e}")
            continue
        if removed:
            logger.info(f"  {key}: pruned {removed} entr{'y' if removed == 1 else 'ies'} "
                        f"older than {max_age_days}d")
        total += removed

    logger.info(f"✅ Pruned {total} stale posted-set entr{'y' if total == 1 else 'ies'} "
                f"(> {max_age_days}d old)")
    return total


def main():
    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info(f"Arc Codex Cleanup — {start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 60)

    try:
        r = get_redis()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.critical(f"🔥 Redis connection failed: {e}")
        sys.exit(1)

    try:
        solr = get_solr()
        logger.info("✅ Solr connected")
    except Exception as e:
        logger.warning(f"⚠️  Solr connection failed — Solr purge will be skipped: {e}")
        solr = None

    feed_size = r.zcard('feed')
    logger.info(f"Feed size: {feed_size} articles")

    # --- Run purges ---
    redis_purged, satellites_cleared = purge_redis_orphans(r)
    solr_purged   = purge_solr_orphans(r, solr) if solr else 0
    hashes_purged = purge_processed_hashes(r)

    image_days = get_image_retention_days()
    images_purged = purge_scraped_images(r, solr, image_days) if image_days else 0

    posted_set_days = get_posted_set_retention_days()
    posted_pruned = purge_stale_posted_entries(r, posted_set_days) if posted_set_days else 0

    # --- Summary ---
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("-" * 60)
    logger.info(f"Redis orphans purged  : {redis_purged}")
    logger.info(f"Orphaned satellites   : {satellites_cleared}")
    logger.info(f"Solr orphans purged   : {solr_purged}")
    logger.info(f"Stale hashes removed  : {hashes_purged}")
    logger.info(f"Scraped images purged : {images_purged}")
    logger.info(f"Posted-set entries pruned : {posted_pruned}")
    logger.info(f"Completed in {elapsed:.1f}s")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
