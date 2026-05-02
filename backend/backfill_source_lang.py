#!/usr/bin/env python3
"""Backfill source_lang on existing articles using langdetect."""
import os, sys, redis
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scribe import detect_language

load_dotenv('/home/www/arc_stack/backend/.env')
r = redis.Redis(host='localhost',
                password=os.environ.get('REDIS_PASSWORD'),
                db=0, decode_responses=True)

updated = 0
unchanged = 0
for key in r.scan_iter('article:*'):
    data = r.hgetall(key)
    if not data:
        continue
    text = data.get('original_text', '') or data.get('article_text', '')
    lang = detect_language(text)
    if lang != data.get('source_lang'):
        r.hset(key, 'source_lang', lang)
        updated += 1
        if updated % 100 == 0:
            print(f'Updated {updated} articles...')
    else:
        unchanged += 1
print(f'Done: {updated} updated, {unchanged} unchanged')
