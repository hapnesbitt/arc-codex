#!/usr/bin/env python3
"""
reindex_solr.py - Re-index Arc Codex articles from Redis into Solr
Finds all article:* keys in Redis, checks which are missing from Solr, indexes them.
Usage:
    python3 reindex_solr.py           # dry run — shows what would be indexed
    python3 reindex_solr.py --commit  # actually index missing articles
"""

import sys
import json
import redis
import pysolr
from dotenv import load_dotenv
import os

load_dotenv('/home/www/itc_stack/backend/.env')

REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')
SOLR_URL = os.getenv('SCRIBE_SOLR_URL', 'http://localhost:8983/solr/feeds/')
DRY_RUN = '--commit' not in sys.argv

r = redis.Redis(decode_responses=True, password=REDIS_PASSWORD)
solr = pysolr.Solr(SOLR_URL)

print(f"{'[DRY RUN] ' if DRY_RUN else ''}Arc Codex Solr Re-indexer")
print(f"Solr: {SOLR_URL}")
print("─" * 50)

# Get all article IDs from Redis
all_keys = r.keys('article:*')
total = len(all_keys)
print(f"Found {total} articles in Redis")

# Check which are already in Solr in batches
def check_solr_batch(ids):
    id_list = ' OR '.join(f'"{i}"' for i in ids)
    results = solr.search(f'id:({id_list})', rows=len(ids), fl='id')
    return {doc['id'] for doc in results}

batch_size = 100
indexed_ids = set()
for i in range(0, total, batch_size):
    batch_keys = all_keys[i:i+batch_size]
    batch_ids = [k.replace('article:', '') for k in batch_keys]
    indexed_ids |= check_solr_batch(batch_ids)
    print(f"  Checked {min(i+batch_size, total)}/{total}...", end='\r')

print(f"\nAlready in Solr: {len(indexed_ids)}")
missing_keys = [k for k in all_keys if k.replace('article:', '') not in indexed_ids]
print(f"Missing from Solr: {len(missing_keys)}")

if not missing_keys:
    print("✅ Nothing to re-index.")
    sys.exit(0)

if DRY_RUN:
    print("\nSample missing articles:")
    for key in missing_keys[:10]:
        title = r.hget(key, 'title') or '(no title)'
        ts = r.hget(key, 'timestamp') or ''
        print(f"  {key.replace('article:', '')[:12]}... | {ts[:10]} | {title[:60]}")
    print(f"\nRun with --commit to index all {len(missing_keys)} missing articles.")
    sys.exit(0)

# Index missing articles
print("\nIndexing missing articles...")
success = 0
failed = 0
batch = []

for key in missing_keys:
    article_id = key.replace('article:', '')
    data = r.hgetall(key)
    if not data:
        continue

    dossier = {}
    try:
        dossier = json.loads(data.get('dossier', '{}'))
    except Exception:
        pass

    # Normalize timestamp — Solr needs ISO 8601
    from datetime import datetime, timezone
    raw_ts = data.get('timestamp', '')
    timestamp = ''
    if raw_ts:
        try:
            timestamp = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        except (ValueError, OSError):
            timestamp = raw_ts  # already a string

    solr_doc = {
        'id': article_id,
        'title': data.get('title', ''),
        'content': data.get('article_text', '') or data.get('content', ''),
        'source': data.get('source_name', 'Unknown'),
        'url': data.get('sourceUrl', '') or data.get('url', ''),
        'timestamp': timestamp,
        'sentiment': dossier.get('sentiment', 0.0),
        'directive': data.get('category', 'Unknown'),
        'chimera_score': dossier.get('chimera_score', 0.0),
    }

    # Skip if no meaningful content
    if not solr_doc['title'] and not solr_doc['content']:
        continue

    batch.append(solr_doc)

    if len(batch) >= 50:
        try:
            solr.add(batch)
            success += len(batch)
            print(f"  ✅ Indexed {success} so far...")
            batch = []
        except Exception as e:
            print(f"  ⚠️  Batch failed, trying individually: {e}")
            for doc in batch:
                try:
                    solr.add([doc])
                    success += 1
                except Exception as e2:
                    print(f"  ❌ Skipped {doc['id'][:12]}: {e2}")
                    failed += 1
            batch = []

# Final batch
if batch:
    try:
        solr.add(batch)
        success += len(batch)
    except Exception as e:
        print(f"  ⚠️  Final batch failed, trying individually: {e}")
        for doc in batch:
            try:
                solr.add([doc])
                success += 1
            except Exception as e2:
                print(f"  ❌ Skipped {doc['id'][:12]}: {e2}")
                failed += 1

solr.commit()
print(f"\n✅ Done. Indexed: {success} | Failed: {failed}")
