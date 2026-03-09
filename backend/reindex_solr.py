#!/usr/bin/env python3
"""
reindex_solr.py
Reindex all articles from Redis into Solr, adding category and source_lang.
Safe to re-run — uses Solr's upsert (add overwrites by id).
Run: /home/www/arc_stack/backend/venv/bin/python backend/reindex_solr.py
"""
import os
import sys
import json
import redis
import pysolr
from dotenv import load_dotenv

load_dotenv('/home/www/arc_stack/backend/.env')

REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'simplenes')
SOLR_URL = os.getenv('SCRIBE_SOLR_URL', 'http://localhost:8983/solr/feeds/')

r = redis.Redis(host='localhost', port=6379, password=REDIS_PASSWORD, decode_responses=True)
solr = pysolr.Solr(SOLR_URL, timeout=30)

# Category mapping (mirrors scribe.py _classify)
CATEGORY_MAP = {
    'zeus': 'zeus', 'leadership': 'zeus', 'governance': 'zeus', 'society': 'zeus',
    'poseidon': 'poseidon', 'climate': 'poseidon', 'ocean': 'poseidon', 'environment': 'poseidon',
    'hades': 'hades', 'privacy': 'hades', 'deep tech': 'hades', 'cyber': 'hades',
    'apollo': 'apollo', 'science': 'apollo', 'medicine': 'apollo', 'health': 'apollo',
    'artemis': 'artemis', 'ecology': 'artemis', 'conservation': 'artemis', 'nature': 'artemis',
    'athena': 'athena', 'strategy': 'athena', 'wisdom': 'athena',
    'ares': 'ares', 'conflict': 'ares', 'justice': 'ares', 'military': 'ares',
    'hephaestus': 'hephaestus', 'tech': 'hephaestus', 'innovation': 'hephaestus', 'engineering': 'hephaestus',
    'hermes': 'hermes', 'media': 'hermes', 'communication': 'hermes', 'networks': 'hermes',
    'aphrodite': 'aphrodite', 'culture': 'aphrodite', 'connection': 'aphrodite', 'social': 'aphrodite',
    'dionysus': 'dionysus', 'emotion': 'dionysus', 'movements': 'dionysus', 'chaos': 'dionysus',
    'demeter': 'demeter', 'food': 'demeter', 'community': 'demeter', 'sustainability': 'demeter',
}

def classify(directive='', category=''):
    combined = f"{directive} {category}".lower()
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in combined:
            return cat
    return 'hermes'  # default

def main():
    keys = r.keys('article:*')
    total = len(keys)
    print(f"📚 Reindexing {total} articles into Solr...")

    batch = []
    updated = 0
    errors = 0
    BATCH_SIZE = 100

    for i, key in enumerate(keys, 1):
        try:
            data = r.hgetall(key)
            if not data or not data.get('id'):
                continue

            # Parse dossier
            dossier = {}
            try:
                dossier = json.loads(data.get('dossier', '{}'))
            except Exception:
                pass

            article_id = data.get('id', key.replace('article:', ''))
            category = data.get('category', '') or classify(
                data.get('directive', ''), ''
            )
            source_lang = data.get('source_lang', 'English')

            doc = {
                'id': article_id,
                'title': data.get('title', ''),
                'content': data.get('original_text', ''),
                'source': data.get('source_name', data.get('source', 'Unknown')),
                'url': data.get('sourceUrl', ''),
                'timestamp': data.get('timestamp', ''),
                'sentiment': float(dossier.get('sentiment', 0.0)),
                'directive': data.get('directive', ''),
                'chimera_score': float(dossier.get('chimera_score', 0.0)),
                'category': category,
                'source_lang': source_lang,
                'original_text': data.get('original_text', ''),
                'imageUrl': data.get('imageUrl', ''),
            }
            batch.append(doc)
            updated += 1

            if len(batch) >= BATCH_SIZE:
                solr.add(batch)
                batch = []
                print(f"  [{i}/{total}] indexed={updated} errors={errors}")

        except Exception as e:
            errors += 1
            print(f"  ⚠️  Error on {key}: {e}")

    # Flush remaining
    if batch:
        solr.add(batch)

    solr.commit()
    print(f"\n✅ Done. indexed={updated} errors={errors}")

    # Quick verification
    results = solr.search('*:*', rows=0,
        facet='true',
        **{'facet.field': ['category', 'source_lang'], 'facet.limit': '20'}
    )
    print(f"\n📊 Solr now has {results.hits} documents")
    for field in ['category', 'source_lang']:
        facets = results.facets.get('facet_fields', {}).get(field, [])
        pairs = list(zip(facets[::2], facets[1::2]))
        print(f"\n{field}:")
        for name, count in sorted(pairs, key=lambda x: -x[1])[:15]:
            if count > 0:
                print(f"  {name}: {count}")

if __name__ == '__main__':
    main()
