"""Age-based retention pruning.

Shared by kasmir7 (interactive trim menu) and scribe (end-of-cycle hook).
The trim itself is small; the reason this lives in its own module is so
scribe.py doesn't have to import all of kasmir7's interactive machinery.

Semantics:
  - "hours" means article age against `time.time()` (Unix seconds).
  - feed zset scores are Unix timestamp per CLAUDE.md — we range-by-score.
  - Redis writes go through a pipeline per article (DEL + ZREM + SREM
    together) so a mid-loop crash leaves each article fully-deleted or
    fully-intact rather than half-deleted.
  - Solr is best-effort: batch-deleted after Redis, logs on failure but
    does not raise. purge_solr_orphans in kasmir7 exists to reconcile.
  - Sitemap/RSS/news-sitemap regeneration runs only when something was
    actually deleted, and only via the existing kasmir7 generators (no
    duplicated XML logic).

This module is identical across stacks; everything site-specific (the
pinned-set key) derives from the site slug so each stack stays in its own
Redis DB family.
"""

import logging
import time

from site_config import load_site_config

logger = logging.getLogger(__name__)

# Articles in this SET are exempt from age-based trimming (curated surfaces
# link to them permanently). Members are article IDs/hashes. The key is
# slug-namespaced (arc:pinned_articles / huntaegis:pinned_articles) so each
# stack's pinned set lives in its own DB family, never a sibling's.
PINNED_SET = f"{load_site_config().slug}:pinned_articles"


def trim_by_hours(r, solr, hours: int, dry_run: bool = False) -> dict:
    """Delete articles older than `hours` from Redis + Solr.

    Only content_type == news (the default) is ever trimmed: reference
    articles and members of PINNED_SET are exempt regardless of age.
    Returns {'found': N_candidates, 'deleted': M_deleted,
             'excluded': {'reference': X, 'pinned': Y}}.
    dry_run=True reports found candidates without touching anything.
    """
    excluded = {"reference": 0, "pinned": 0}
    if hours is None or hours <= 0:
        return {"found": 0, "deleted": 0, "excluded": excluded}

    cutoff = time.time() - (hours * 3600)
    ids_to_delete = r.zrangebyscore("feed", "-inf", cutoff)
    if ids_to_delete:
        pinned = r.smembers(PINNED_SET)
        pipe = r.pipeline()
        for aid in ids_to_delete:
            pipe.hget(f"article:{aid}", "content_type")
        ctypes = pipe.execute()
        keep = []
        for aid, ct in zip(ids_to_delete, ctypes):
            if (ct or "news") == "reference":
                excluded["reference"] += 1
            elif aid in pinned:
                excluded["pinned"] += 1
            else:
                keep.append(aid)
        ids_to_delete = keep
    if not ids_to_delete:
        return {"found": 0, "deleted": 0, "excluded": excluded}
    if dry_run:
        return {"found": len(ids_to_delete), "deleted": 0, "excluded": excluded}

    deleted = 0
    for aid in ids_to_delete:
        pipe = r.pipeline()
        pipe.delete(f"article:{aid}")
        pipe.zrem("feed", aid)
        pipe.srem("processed_hashes", aid)
        pipe.execute()
        deleted += 1

    if solr is not None:
        try:
            from kasmir7 import solr_delete_batch
            solr_delete_batch(solr, list(ids_to_delete))
        except Exception as e:
            logger.warning("Solr batch delete failed (Redis already trimmed; run purge_solr_orphans to reconcile): %s", e)

    return {"found": len(ids_to_delete), "deleted": deleted, "excluded": excluded}


def regenerate_public_files(r) -> dict:
    """Regenerate sitemap.xml, rss.xml, news-sitemap.xml via kasmir7 generators.

    Called after any prune pass that actually removed articles — otherwise
    dead URLs accumulate between manual regenerations.
    """
    from kasmir7 import generate_sitemap, generate_rss, generate_news_sitemap
    result = {}
    for name, fn in [
        ("sitemap", generate_sitemap),
        ("rss", generate_rss),
        ("news_sitemap", generate_news_sitemap),
    ]:
        try:
            fn(r)
            result[name] = True
        except Exception as e:
            logger.error("regen %s failed: %s", name, e)
            result[name] = False
    return result


def run_retention_pass(r, solr, hours: int, dry_run: bool = False) -> dict:
    """One retention pass: trim + regenerate public files if anything deleted."""
    result = trim_by_hours(r, solr, hours, dry_run=dry_run)
    if result["deleted"] > 0:
        result["regen"] = regenerate_public_files(r)
    return result
