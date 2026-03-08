#!/usr/bin/env python3
"""
backfill_source_lang.py
One-time script to detect and set source_lang on existing articles in Redis.
Run from arc_stack root with the backend venv activated.
"""
import os
import sys
import redis
from dotenv import load_dotenv

load_dotenv('/home/www/arc_stack/backend/.env')

try:
    from langdetect import detect as detect_lang
except ImportError:
    print("❌ langdetect not installed. Run: venv/bin/pip install langdetect")
    sys.exit(1)

REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'simplenes')
r = redis.Redis(host='localhost', port=6379, password=REDIS_PASSWORD, decode_responses=True)

LANGDETECT_MAP = {
    'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
    'it': 'Italian', 'pt': 'Portuguese', 'nl': 'Dutch', 'ru': 'Russian',
    'zh-cn': 'Chinese (Simplified)', 'zh-tw': 'Chinese (Traditional)',
    'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'hi': 'Hindi',
    'tr': 'Turkish', 'pl': 'Polish', 'sv': 'Swedish', 'no': 'Norwegian',
    'da': 'Danish', 'fi': 'Finnish', 'cs': 'Czech', 'ro': 'Romanian',
    'hu': 'Hungarian', 'uk': 'Ukrainian', 'he': 'Hebrew', 'fa': 'Persian',
    'id': 'Indonesian', 'ms': 'Malay', 'th': 'Thai', 'vi': 'Vietnamese',
    'el': 'Greek', 'bg': 'Bulgarian', 'hr': 'Croatian', 'sk': 'Slovak',
    'sl': 'Slovenian', 'sr': 'Serbian', 'lt': 'Lithuanian', 'lv': 'Latvian',
    'et': 'Estonian', 'ca': 'Catalan', 'af': 'Afrikaans', 'sq': 'Albanian',
    'bn': 'Bengali', 'ur': 'Urdu', 'ta': 'Tamil', 'te': 'Telugu',
    'ml': 'Malayalam', 'sw': 'Swahili', 'tl': 'Filipino',
}

def detect_language(text):
    if not text or len(text) < 50:
        return 'English'
    try:
        code = detect_lang(text[:2000])
        return LANGDETECT_MAP.get(code, 'English')
    except Exception:
        return 'English'

def main():
    keys = r.keys('article:*')
    total = len(keys)
    print(f"📚 Found {total} articles to process")

    skipped = 0
    updated = 0
    errors = 0
    lang_counts = {}

    for i, key in enumerate(keys, 1):
        try:
            # Skip if already has source_lang
            existing = r.hget(key, 'source_lang')
            if existing:
                skipped += 1
                continue

            text = r.hget(key, 'original_text') or ''
            lang = detect_language(text)
            r.hset(key, 'source_lang', lang)
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            updated += 1

            if i % 100 == 0:
                print(f"  [{i}/{total}] updated={updated} skipped={skipped} errors={errors}")

        except Exception as e:
            errors += 1
            print(f"  ⚠️  Error on {key}: {e}")

    print(f"\n✅ Done. updated={updated} skipped={skipped} errors={errors}")
    print("\n📊 Language distribution:")
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {lang}: {count}")

if __name__ == '__main__':
    main()
