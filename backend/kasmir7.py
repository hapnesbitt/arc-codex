#!/usr/bin/env python3
# kasmir7.py - Arc Codex Admin Console v7.0
# Data operations: search, inspect, remove, trim, re-index
# Changelog v7.0:
#   - Rebranded: HapEnews → Arc Codex
#   - Emergency removal now also deletes from Solr
#   - Research now uses Solr full-text search (falls back to Redis title scan)
#   - [5] Re-index Solr: finds and indexes articles missing from Solr
#   - [6] Solr diagnostics: count, latest doc, connection check

import os, sys, json, redis, time, csv, pysolr
from datetime import datetime, timezone
from termcolor import colored
from dotenv import load_dotenv
from dateutil import parser

# --- Configuration ---
load_dotenv()
REDIS_HOST     = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT     = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB       = int(os.getenv("REDIS_DB", 0))
SOLR_URL       = os.getenv("SCRIBE_SOLR_URL", "http://localhost:8983/solr/feeds/")

BANNER = """
╔══════════════════════════════════════════════╗
║       Arc Codex Admin Console  v7.0         ║
║       kasmir — Data Operations              ║
╚══════════════════════════════════════════════╝
"""

# --- Connections ---
def connect_redis():
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                        db=REDIS_DB, decode_responses=True)
        r.ping()
        print(colored("✅ Redis connected.", "green"))
        return r
    except Exception as e:
        print(colored(f"🔥 Redis connection failed: {e}", "red"))
        sys.exit(1)

def connect_solr():
    try:
        s = pysolr.Solr(SOLR_URL, timeout=10)
        s.ping()
        print(colored("✅ Solr connected.", "green"))
        return s
    except Exception as e:
        print(colored(f"⚠️  Solr unavailable: {e}", "yellow"))
        return None

# --- Helpers ---
def normalize_timestamp(raw_ts):
    """Convert any timestamp format to ISO 8601 for Solr."""
    if not raw_ts:
        return ''
    try:
        return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, OSError):
        return raw_ts

def solr_delete(solr, article_id):
    """Delete a single doc from Solr by ID."""
    if not solr:
        return False
    try:
        solr.delete(id=article_id)
        solr.commit()
        return True
    except Exception as e:
        print(colored(f"  ⚠️  Solr delete failed for {article_id}: {e}", "yellow"))
        return False

def build_solr_doc(article_id, data):
    """Build a Solr document from Redis article hash."""
    dossier = {}
    try:
        dossier = json.loads(data.get('dossier', '{}'))
    except Exception:
        pass
    return {
        'id': article_id,
        'title': data.get('title', ''),
        'content': data.get('article_text', '') or data.get('content', ''),
        'source': data.get('source_name', 'Unknown'),
        'url': data.get('sourceUrl', '') or data.get('url', ''),
        'timestamp': normalize_timestamp(data.get('timestamp', '')),
        'sentiment': dossier.get('sentiment', 0.0),
        'directive': data.get('category', data.get('directive', 'Unknown')),
        'chimera_score': dossier.get('chimera_score', 0.0),
    }

# --- DB Status ---
def get_db_status(r, solr):
    feed_count = r.zcard("feed")
    all_ids = r.zrange("feed", 0, -1)
    first_ts = r.hget(f"article:{all_ids[0]}", "timestamp") if all_ids else None
    last_ts  = r.hget(f"article:{all_ids[-1]}", "timestamp") if all_ids else None
    solr_count = '?'
    if solr:
        try:
            results = solr.search('*:*', rows=0)
            solr_count = results.hits
        except Exception:
            pass
    print(f"\n{'─'*50}")
    print(f"  Redis feed : {colored(str(feed_count), 'cyan')} articles")
    print(f"  Solr index : {colored(str(solr_count), 'cyan')} documents")
    print(f"  Oldest     : {first_ts or 'N/A'}")
    print(f"  Newest     : {last_ts or 'N/A'}")
    print(f"{'─'*50}")

# --- [1] Research / Search ---
def research_articles(r, solr):
    print(colored("\n--- [1] Research / Search Articles ---", "cyan"))

    query = input("Search query (leave blank for date-only filter): ").strip()
    start_date_input = input("Start date (YYYY-MM-DD, optional): ").strip()
    end_date_input   = input("End date (YYYY-MM-DD, optional): ").strip()

    # Try Solr first for full-text search
    if query and solr:
        print(colored("\n🔍 Searching via Solr (full-text)...", "yellow"))
        try:
            words = query.split()
            if len(words) > 1:
                phrase = f'"{query}"'
                and_terms = ' AND '.join(words)
                solr_query = (
                    f'title:{phrase}^10 OR content:{phrase}^5 '
                    f'OR title:({and_terms})^3 OR content:({and_terms})'
                )
            else:
                solr_query = f'title:({query})^3 OR content:({query})'

            results = solr.search(solr_query, rows=50, sort='score desc, timestamp desc',
                                  fl='id,title,source,timestamp,score')
            matches = [(doc.get('timestamp', [''])[0] if isinstance(doc.get('timestamp'), list) else doc.get('timestamp', ''),
                        doc.get('title', [''])[0] if isinstance(doc.get('title'), list) else doc.get('title', ''),
                        doc.get('id', ''),
                        f"score:{doc.get('score', 0):.2f}")
                       for doc in results]

            print(f"Found {colored(str(len(matches)), 'cyan')} Solr results for '{query}':")
            for ts, title, aid, score in matches[:20]:
                print(f"  {ts[:10] if ts else '?':10} | {score:12} | {title[:60]}")
            if len(matches) > 20:
                print(f"  ... {len(matches)-20} more not shown")

            _maybe_export_csv(matches, ('timestamp','title','article_id','score'))
            return
        except Exception as e:
            print(colored(f"⚠️  Solr search failed, falling back to Redis scan: {e}", "yellow"))

    # Redis fallback — title scan
    print(colored("\n🔍 Searching via Redis (title scan)...", "yellow"))
    start_ts = parser.parse(start_date_input).timestamp() if start_date_input else None
    end_ts   = parser.parse(end_date_input).timestamp() if end_date_input else None

    ids = r.zrange("feed", 0, -1)
    matches = []
    for article_id in ids:
        data = r.hgetall(f"article:{article_id}")
        title  = data.get("title", "").lower()
        raw_ts = data.get("timestamp", "")
        try:
            ts = parser.parse(raw_ts).timestamp() if raw_ts else None
        except Exception:
            ts = None

        if start_ts and ts and ts < start_ts: continue
        if end_ts   and ts and ts > end_ts:   continue

        if query:
            q = query.lower()
            if " or " in q:
                terms = [t.strip() for t in q.split(" or ")]
                if not any(term in title for term in terms): continue
            elif " and " in q:
                terms = [t.strip() for t in q.split(" and ")]
                if not all(term in title for term in terms): continue
            elif q not in title:
                continue

        matches.append((raw_ts, data.get("title", ""), article_id))

    print(f"Found {colored(str(len(matches)), 'cyan')} Redis results:")
    for ts_str, title, aid in matches[:20]:
        print(f"  {str(ts_str)[:10]:10} | {title[:70]}")
    if len(matches) > 20:
        print(f"  ... {len(matches)-20} more not shown")

    _maybe_export_csv(matches, ('timestamp','title','article_id'))

def _maybe_export_csv(matches, headers):
    if not matches:
        return
    csv_file = input("\nExport to CSV? (filename or blank to skip): ").strip()
    if csv_file:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in matches:
                writer.writerow(row)
        print(colored(f"✅ Exported {len(matches)} rows to {csv_file}", "green"))

# --- [2] Emergency Removal ---
def emergency_removal(r, solr):
    print(colored("\n--- [2] Emergency Content Removal ---", "cyan"))
    search_phrase = input("Title phrase to search for: ").strip()
    if not search_phrase:
        return

    matching = []
    for key in r.scan_iter("article:*"):
        title = r.hget(key, "title") or ''
        if search_phrase.lower() in title.lower():
            matching.append((key, key.split(":")[-1], title))

    if not matching:
        print("No matches found.")
        return

    print(colored(f"\nDRY RUN — {len(matching)} article(s) would be deleted:", "yellow"))
    for key, aid, title in matching:
        solr_status = ''
        if solr:
            try:
                res = solr.search(f'id:"{aid}"', rows=1, fl='id')
                solr_status = colored(' [in Solr]', 'blue') if res.hits > 0 else colored(' [not in Solr]', 'dark_grey')
            except Exception:
                pass
        print(f"  - {title[:70]}{solr_status}")

    if input("\nDelete these articles from Redis AND Solr? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    deleted = 0
    for key, aid, title in matching:
        r.delete(key)
        r.zrem("feed", aid)
        r.srem("processed_hashes", aid)
        solr_delete(solr, aid)
        deleted += 1

    print(colored(f"✅ Deleted {deleted} article(s) from Redis and Solr.", "green"))

# --- [3] Trim Database ---
def trim_database(r, solr):
    print(colored("\n--- [3] Trim Database ---", "cyan"))
    print("  count N  → keep latest N articles")
    print("  days N   → delete articles older than N days")
    print("  hours N  → delete articles older than N hours")

    trim_cmd = input("\nTrim command: ").strip().lower()
    try:
        method, value_str = trim_cmd.split()
        value = int(value_str)
    except ValueError:
        print(colored("Invalid format. Use: method value", "red"))
        return

    ids_to_delete = []
    if method == 'count':
        total = r.zcard("feed")
        if value >= total:
            print(f"Feed has {total} articles — nothing to trim.")
            return
        ids_to_delete = r.zrange("feed", 0, total - value - 1)
    elif method in ('days', 'hours'):
        cutoff = time.time() - (value * 86400 if method == 'days' else value * 3600)
        ids_to_delete = r.zrangebyscore("feed", "-inf", cutoff)
    else:
        print(colored(f"Unknown method: {method}", "red"))
        return

    if not ids_to_delete:
        print("No articles matched the trim criteria.")
        return

    print(colored(f"\nDRY RUN — {len(ids_to_delete)} article(s) would be deleted.", "yellow"))

    if input("Proceed? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    deleted = 0
    for aid in ids_to_delete:
        r.delete(f"article:{aid}")
        r.zrem("feed", aid)
        r.srem("processed_hashes", aid)
        solr_delete(solr, aid)
        deleted += 1

    if solr:
        try:
            solr.commit()
        except Exception:
            pass

    print(colored(f"✅ Trim complete. Deleted {deleted} article(s) from Redis and Solr.", "green"))

# --- [4] Inspect Article ---
def inspect_article(r, solr):
    print(colored("\n--- [4] Inspect Article ---", "cyan"))
    article_id = input("Article ID (without 'article:' prefix): ").strip()
    if not article_id:
        return

    key = f"article:{article_id}"
    if not r.exists(key):
        print(colored(f"❌ Not found in Redis: {article_id}", "red"))
        return

    data = r.hgetall(key)

    print(colored(f"\n=== {article_id} ===", "cyan"))
    print(colored("--- Core Metadata ---", "yellow"))
    print(f"  Title      : {data.get('title', 'N/A')}")
    print(f"  Source     : {data.get('source_name', data.get('source', 'N/A'))}")
    print(f"  SourceURL  : {data.get('sourceUrl', colored('MISSING', 'red'))}")
    print(f"  Image URL  : {data.get('imageUrl', 'N/A')}")
    print(f"  Timestamp  : {data.get('timestamp', 'N/A')}")
    print(f"  Category   : {data.get('category', data.get('directive', 'N/A'))}")

    print(colored("\n--- Scores ---", "yellow"))
    dossier_raw = data.get('dossier', '{}')
    try:
        dossier = json.loads(dossier_raw)
        for k, v in dossier.items():
            print(f"  {k}: {v}")
    except Exception:
        print(f"  (raw) {dossier_raw[:200]}")

    print(colored("\n--- Content Lengths ---", "yellow"))
    for field in ('article_text', 'red_team_analysis', 'blue_team_analysis', 'purple_team_analysis'):
        val = data.get(field, '')
        print(f"  {field:28}: {len(val):6} chars")

    print(colored("\n--- Solr Status ---", "yellow"))
    if solr:
        try:
            res = solr.search(f'id:"{article_id}"', rows=1, fl='id,title,timestamp')
            if res.hits > 0:
                print(colored("  ✅ Indexed in Solr", "green"))
            else:
                print(colored("  ❌ NOT in Solr", "red"))
                if input("  Re-index now? (yes/no): ").lower() == 'yes':
                    doc = build_solr_doc(article_id, data)
                    solr.add([doc])
                    solr.commit()
                    print(colored("  ✅ Re-indexed.", "green"))
        except Exception as e:
            print(colored(f"  ⚠️  Solr check failed: {e}", "yellow"))
    else:
        print(colored("  ⚠️  Solr unavailable", "yellow"))

# --- [5] Re-index Solr ---
def reindex_solr(r, solr):
    print(colored("\n--- [5] Re-index Solr ---", "cyan"))
    if not solr:
        print(colored("❌ Solr unavailable.", "red"))
        return

    all_keys = [f"article:{aid}" for aid in r.zrange("feed", 0, -1)]
    total = len(all_keys)
    print(f"Checking {total} feed articles against Solr...")

    # Find missing in batches
    batch_size = 100
    indexed_ids = set()
    for i in range(0, total, batch_size):
        batch = all_keys[i:i+batch_size]
        ids = [k.replace('article:', '') for k in batch]
        id_list = ' OR '.join(f'"{i}"' for i in ids)
        try:
            results = solr.search(f'id:({id_list})', rows=len(ids), fl='id')
            indexed_ids |= {doc['id'] for doc in results}
        except Exception as e:
            print(colored(f"  ⚠️  Batch check failed: {e}", "yellow"))
        print(f"  Checked {min(i+batch_size, total)}/{total}...", end='\r')

    missing_keys = [k for k in all_keys if k.replace('article:', '') not in indexed_ids]
    print(f"\nAlready in Solr : {colored(str(len(indexed_ids)), 'green')}")
    print(f"Missing from Solr: {colored(str(len(missing_keys)), 'yellow' if missing_keys else 'green')}")

    if not missing_keys:
        print(colored("✅ Nothing to re-index.", "green"))
        return

    print("\nSample missing:")
    for key in missing_keys[:10]:
        title = r.hget(key, 'title') or '(no title)'
        ts = r.hget(key, 'timestamp') or ''
        print(f"  {str(ts)[:10]:10} | {title[:60]}")

    if input(f"\nIndex all {len(missing_keys)} missing articles? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    success = failed = 0
    batch = []

    def flush_batch(b):
        nonlocal success, failed
        try:
            solr.add(b)
            success += len(b)
        except Exception as e:
            print(colored(f"\n  ⚠️  Batch failed, trying individually: {e}", "yellow"))
            for doc in b:
                try:
                    solr.add([doc])
                    success += 1
                except Exception as e2:
                    print(colored(f"  ❌ Skipped {doc['id'][:12]}: {e2}", "red"))
                    failed += 1

    for key in missing_keys:
        aid = key.replace('article:', '')
        data = r.hgetall(key)
        if not data:
            continue
        doc = build_solr_doc(aid, data)
        if not doc['title'] and not doc['content']:
            continue
        batch.append(doc)
        if len(batch) >= 50:
            flush_batch(batch)
            batch = []
            print(f"  Indexed {success} so far...", end='\r')

    if batch:
        flush_batch(batch)

    solr.commit()
    print(f"\n{colored('✅ Done.', 'green')} Indexed: {success} | Failed: {failed}")

# --- [6] Solr Diagnostics ---
def solr_diagnostics(solr):
    print(colored("\n--- [6] Solr Diagnostics ---", "cyan"))
    if not solr:
        print(colored("❌ Solr unavailable.", "red"))
        return

    try:
        total = solr.search('*:*', rows=0).hits
        print(f"  Total documents : {colored(str(total), 'cyan')}")

        latest = solr.search('*:*', rows=1, sort='timestamp desc', fl='id,title,timestamp')
        for doc in latest:
            ts = doc.get('timestamp', ['?'])
            ts = ts[0] if isinstance(ts, list) else ts
            title = doc.get('title', ['?'])
            title = title[0] if isinstance(title, list) else title
            print(f"  Latest doc      : {str(ts)[:19]} | {title[:60]}")

        oldest = solr.search('*:*', rows=1, sort='timestamp asc', fl='id,title,timestamp')
        for doc in oldest:
            ts = doc.get('timestamp', ['?'])
            ts = ts[0] if isinstance(ts, list) else ts
            title = doc.get('title', ['?'])
            title = title[0] if isinstance(title, list) else title
            print(f"  Oldest doc      : {str(ts)[:19]} | {title[:60]}")

        test_q = solr.search('title:*', rows=0)
        print(f"  Docs with title : {test_q.hits}")
        test_c = solr.search('content:*', rows=0)
        print(f"  Docs with content:{test_c.hits}")

    except Exception as e:
        print(colored(f"  ❌ Diagnostics failed: {e}", "red"))


# --- [7] Purge Solr Orphans ---
def purge_solr_orphans(r, solr):
    print(colored("\n--- [7] Purge Solr Orphans ---", "cyan"))
    print("Finds Solr documents with no matching Redis article and removes them.")
    if not solr:
        print(colored("❌ Solr unavailable.", "red"))
        return

    # Get all Redis article IDs
    print("Loading Redis article IDs...", end="\r")
    redis_ids = {k.replace("article:", "") for k in r.keys("article:*")}
    print(f"Redis articles   : {colored(str(len(redis_ids)), 'cyan')}          ")

    # Paginate through all Solr docs using cursorMark
    print("Scanning Solr documents...")
    solr_ids = set()
    cursor = "*"
    page_size = 1000
    while True:
        try:
            results = solr.search(
                '*:*', rows=page_size, fl='id',
                sort='id asc',
                cursorMark=cursor
            )
            for doc in results.docs:
                solr_ids.add(doc['id'])
            next_cursor = results.raw_response['nextCursorMark']
            print(f"  Scanned {len(solr_ids)} Solr docs...", end="\r")
            if next_cursor == cursor:
                break
            cursor = next_cursor
        except Exception as e:
            print(colored(f"\n  ❌ Solr scan failed: {e}", "red"))
            return

    orphan_ids = solr_ids - redis_ids
    print(f"\nSolr documents   : {colored(str(len(solr_ids)), 'cyan')}")
    print(f"Orphaned in Solr : {colored(str(len(orphan_ids)), 'yellow' if orphan_ids else 'green')}")

    if not orphan_ids:
        print(colored("✅ No orphans found. Solr is clean.", "green"))
        return

    print(f"\nSample orphan IDs:")
    for oid in list(orphan_ids)[:10]:
        print(f"  {oid}")

    if input(f"\nDelete all {len(orphan_ids)} orphans from Solr? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    # Delete in batches
    deleted = failed = 0
    orphan_list = list(orphan_ids)
    batch_size = 100
    for i in range(0, len(orphan_list), batch_size):
        batch = orphan_list[i:i+batch_size]
        try:
            for oid in batch:
                solr.delete(id=oid)
            deleted += len(batch)
            print(f"  Deleted {deleted}/{len(orphan_ids)}...", end="\r")
        except Exception as e:
            print(colored(f"\n  ⚠️  Batch failed: {e}", "yellow"))
            failed += len(batch)

    try:
        solr.commit()
    except Exception as e:
        print(colored(f"  ⚠️  Commit failed: {e}", "yellow"))

    print(f"\n{colored('✅ Purge complete.', 'green')} Deleted: {deleted} | Failed: {failed}")


# --- [8] Purge Redis Orphans ---
def purge_redis_orphans(r, solr):
    print(colored("\n--- [8] Purge Redis Orphans ---", "cyan"))
    print("Finds article: hashes in Redis with no matching feed entry and removes them.")

    feed_ids = set(r.zrange("feed", 0, -1))
    all_keys = r.keys("article:*")
    orphan_keys = [k for k in all_keys if k.replace("article:", "") not in feed_ids]

    print(f"Feed articles    : {colored(str(len(feed_ids)), 'cyan')}")
    print(f"article:* keys   : {colored(str(len(all_keys)), 'cyan')}")
    print(f"Orphaned hashes  : {colored(str(len(orphan_keys)), 'yellow' if orphan_keys else 'green')}")

    if not orphan_keys:
        print(colored("✅ No Redis orphans found.", "green"))
        return

    print("\nSample orphans:")
    for key in orphan_keys[:10]:
        title = r.hget(key, 'title') or '(no title)'
        print(f"  {key} | {title[:55]}")

    if input(f"\nDelete all {len(orphan_keys)} orphaned hashes from Redis (and Solr if present)? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    deleted = 0
    for key in orphan_keys:
        aid = key.replace("article:", "")
        r.delete(key)
        r.srem("processed_hashes", aid)
        if solr:
            try:
                solr.delete(id=aid)
            except Exception:
                pass
        deleted += 1

    if solr:
        try:
            solr.commit()
        except Exception:
            pass

    print(colored(f"✅ Purged {deleted} orphaned Redis hash(es).", "green"))

# --- Main ---
def main():
    print(colored(BANNER, "cyan"))
    r    = connect_redis()
    solr = connect_solr()

    while True:
        get_db_status(r, solr)
        print("\n  [1] Research / Search")
        print("  [2] Emergency Removal")
        print("  [3] Trim Database")
        print("  [4] Inspect Article")
        print("  [5] Re-index Solr")
        print("  [6] Solr Diagnostics")
        print("  [7] Purge Solr Orphans")
        print("  [8] Purge Redis Orphans")
        print("  [q] Quit\n")

        choice = input("Select: ").strip().lower()

        if   choice == '1': research_articles(r, solr)
        elif choice == '2': emergency_removal(r, solr)
        elif choice == '3': trim_database(r, solr)
        elif choice == '4': inspect_article(r, solr)
        elif choice == '5': reindex_solr(r, solr)
        elif choice == '6': solr_diagnostics(solr)
        elif choice == '7': purge_solr_orphans(r, solr)
        elif choice == '8': purge_redis_orphans(r, solr)
        elif choice in ('', 'q', 'quit', 'exit'):
            print("Goodbye.")
            break
        else:
            print(colored("Invalid selection.", "red"))

if __name__ == "__main__":
    main()
