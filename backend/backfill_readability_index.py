#!/usr/bin/env python3
"""Backfill readability_index onto existing Arc feed articles.

readability_index is the semantic name for Arc's 0-100 readability synthesis,
written going forward by main.py pre_analyze with the same value as
chimera_score (which on Arc *is* that synthesis). Articles scored before that
change have chimera_score but no readability_index, so the unified
IntelligenceCard reading dial — which reads readability_index and never
chimera_score — would show no number on them.

This one-off, idempotent pass copies dossier.chimera_score ->
dossier.readability_index (and nlp_chimera_score -> nlp_readability_index at
top level) for every feed article that lacks it. Run near the frontend merge
so old and new items look uniform. Safe to re-run: articles already carrying
readability_index are skipped, and chimera_score is never modified.

    python3 backfill_readability_index.py --dry-run
    python3 backfill_readability_index.py
"""
import argparse
import json
import os

import redis
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))


def connect():
    url = os.environ.get('REDIS_URL')
    if not url:
        raise SystemExit('REDIS_URL not set — check backend/.env')
    r = redis.from_url(url, decode_responses=True)
    r.ping()
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true', help='report only; write nothing')
    args = ap.parse_args()

    r = connect()
    ids = r.zrange('feed', 0, -1)
    scanned = updated = already = no_chimera = 0

    for aid in ids:
        scanned += 1
        key = f'article:{aid}'
        raw = r.hget(key, 'dossier')
        try:
            dossier = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            dossier = {}

        if dossier.get('readability_index') is not None:
            already += 1
            continue
        chimera = dossier.get('chimera_score')
        if chimera is None or chimera == '':
            no_chimera += 1
            continue

        if not args.dry_run:
            dossier['readability_index'] = chimera
            pipe = r.pipeline()
            pipe.hset(key, 'dossier', json.dumps(dossier))
            # Mirror the top-level nlp_* field when its chimera counterpart exists.
            nlp_chimera = r.hget(key, 'nlp_chimera_score')
            if nlp_chimera not in (None, '') and r.hget(key, 'nlp_readability_index') in (None, ''):
                pipe.hset(key, 'nlp_readability_index', str(nlp_chimera))
            pipe.execute()
        updated += 1

    verb = 'would update' if args.dry_run else 'updated'
    print(f"feed articles scanned : {scanned}")
    print(f"{verb:<21} : {updated}")
    print(f"already had index     : {already}")
    print(f"no chimera_score      : {no_chimera}")
    if args.dry_run:
        print("\nDRY RUN — nothing written.")


if __name__ == '__main__':
    main()
