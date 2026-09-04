#!/usr/bin/env python3
# kasmir7.py - Arc Codex Admin Console v7.4
# Data operations: search, inspect, remove, trim, re-index, intelligence
#
# Changelog v7.2:
#   - [9]  Intelligence Dashboard — corpus health: source distribution, language
#          breakdown, directive breakdown, Sentinel verdicts, chimera score
#          histogram, articles missing key fields. Full epistemic fingerprint.
#   - [10] A.R.C. Pattern Scanner — scans purple_team_analysis across corpus,
#          ranks ARC-0001..0048 by detection frequency, drills into articles
#          per pattern. Shows the rhetorical fingerprint of the news cycle.
#   - [2d] Remove by Chimera Score threshold — prune by readability
#          difficulty below a score, or outliers above one.
#   - [2e] Remove by Sentinel verdict — batch-delete SYNTHETIC, UNCERTAIN,
#          or HUMAN-flagged articles.
#   - [3]  Trim by directive — rebalance corpus by pruning oldest N from one
#          directive without touching others.
#   - [4]  Inspect now shows ARC patterns detected in purple_team_analysis
#          and domain / language / sentinel fields.
#   - [1]  Research now supports chimera score filter (e.g. >70 or <20).
#
# Changelog v7.1:
#   - Emergency removal: [2b] Remove by Domain (TLD) — full domain match
#   - Emergency removal: [2c] Remove by Language — matches source_lang field
#
# Changelog v7.0:
#   - Rebranded: HapEnews → Arc Codex
#   - Emergency removal now also deletes from Solr
#   - Research now uses Solr full-text search (falls back to Redis title scan)
#   - [5] Re-index Solr: finds and indexes articles missing from Solr
#   - [6] Solr diagnostics: count, latest doc, connection check

import os, sys, json, re, redis, time, csv, pysolr, urllib.parse
from collections import Counter, defaultdict
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
║       Arc Codex Admin Console  v7.2         ║
║       kasmir — Data Operations              ║
╚══════════════════════════════════════════════╝
"""

# All 48 A.R.C. patterns — code + canonical name
ARC_PATTERNS = {
    "ARC-0001": "Siren's Trap",
    "ARC-0002": "Deniability Decoy",
    "ARC-0003": "Wolf's Gambit",
    "ARC-0004": "Configuration Drift",
    "ARC-0005": "Appeal to Ridicule",
    "ARC-0006": "Appeal to Spite",
    "ARC-0007": "Appeal to Force",
    "ARC-0008": "Ad Hominem",
    "ARC-0009": "Straw Man",
    "ARC-0010": "False Dilemma",
    "ARC-0011": "Slippery Slope",
    "ARC-0012": "Appeal to Nature",
    "ARC-0013": "Appeal to Tradition",
    "ARC-0014": "Appeal to Novelty",
    "ARC-0015": "Bandwagon",
    "ARC-0016": "Appeal to Authority",
    "ARC-0017": "Hasty Generalization",
    "ARC-0018": "Anecdotal Evidence",
    "ARC-0019": "Texas Sharpshooter",
    "ARC-0020": "Post Hoc",
    "ARC-0021": "Correlation Causation",
    "ARC-0022": "False Analogy",
    "ARC-0023": "Equivocation",
    "ARC-0024": "Ambiguity",
    "ARC-0025": "Composition Fallacy",
    "ARC-0026": "Division Fallacy",
    "ARC-0027": "Begging the Question",
    "ARC-0028": "Circular Reasoning",
    "ARC-0029": "Red Herring",
    "ARC-0030": "Irrelevant Conclusion",
    "ARC-0031": "Moving the Goalposts",
    "ARC-0032": "No True Scotsman",
    "ARC-0033": "Tu Quoque",
    "ARC-0034": "Two Wrongs",
    "ARC-0035": "Appeal to Pity",
    "ARC-0036": "Appeal to Flattery",
    "ARC-0037": "Loaded Question",
    "ARC-0038": "Burden of Proof Shift",
    "ARC-0039": "Argument from Ignorance",
    "ARC-0040": "Black-or-White",
    "ARC-0041": "Middle Ground Fallacy",
    "ARC-0042": "Nirvana Fallacy",
    "ARC-0043": "Motte-and-Bailey",
    "ARC-0044": "Gish Gallop",
    "ARC-0045": "Sealioning",
    "ARC-0046": "Kafka Trap",
    "ARC-0047": "Sanewashing",
    "ARC-0048": "Kalisti Principle",
}

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
    """Convert any timestamp format to ISO 8601 for Solr date field."""
    try:
        if not raw_ts:
            return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if str(raw_ts).isdigit():
            return datetime.fromtimestamp(int(raw_ts) / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        return parser.parse(str(raw_ts)).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def solr_delete(solr, article_id):
    """Delete a single doc from Solr WITHOUT committing (caller must commit)."""
    if not solr:
        return False
    try:
        solr.delete(id=article_id)
        return True
    except Exception as e:
        print(colored(f"  ⚠️  Solr delete failed for {article_id}: {e}", "yellow"))
        return False

def solr_delete_batch(solr, article_ids, batch_size=100):
    """Delete a list of IDs from Solr in batches with a single commit at the end."""
    if not solr or not article_ids:
        return 0, 0
    deleted = failed = 0
    ids = list(article_ids)
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        try:
            for aid in batch:
                solr.delete(id=aid)
            deleted += len(batch)
            print(f"  Solr: {deleted}/{len(ids)} queued...", end='\r')
        except Exception as e:
            print(colored(f"\n  ⚠️  Solr batch failed: {e}", "yellow"))
            failed += len(batch)
    try:
        solr.commit()
    except Exception as e:
        print(colored(f"  ⚠️  Solr commit failed: {e}", "yellow"))
    if deleted:
        print(f"  Solr: {deleted}/{len(ids)} deleted, committed.    ")
    return deleted, failed

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

def _extract_registered_domain(url):
    """Extract registered domain from a URL. 'https://blogs.ft.com/...' -> 'ft.com'"""
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        host = host.split(':')[0]
        parts = host.lstrip('www.').split('.')
        return '.'.join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ''

def _get_chimera_score(data):
    """Extract chimera_score from article data. Returns None if not present."""
    score = data.get('chimera_score')
    if score is not None:
        try:
            return float(score)
        except (ValueError, TypeError):
            pass
    try:
        dossier = json.loads(data.get('dossier', '{}'))
        s = dossier.get('chimera_score')
        if s is not None:
            return float(s)
    except Exception:
        pass
    return None


# chimera_score means different things on the two stacks (same fork split
# documented in mailer.py and IntelligenceCard.tsx): on Hunt it's a 0-1
# objectivity ratio, on Arc — this stack — it's a 0-100 readability
# difficulty composite (compute_chimera in main.py: avg of FK/Coleman-Liau/
# SMOG/Dale-Chall grade levels, 0=Kindergarten .. 100=Quantum
# Electrodynamics). Hunt's kasmir7.py has near-identical inspect-article
# code that's CORRECT there (0-1 thresholds, "divisive/low-quality"
# framing) — this file inherited it unchanged, which on Arc's 0-100 scale
# meant `chimera < 0.3`/`< 0.6` were true for almost nothing, the bar's
# max_value=1.0 overflowed to hundreds of block characters, and the label
# described objectivity for a field that measures difficulty. Fixed
# 2026-08-27 — see ops/RUNBOOK.md. Don't resync this block from Hunt's copy.
def _chimera_color(score):
    """Color band for Arc's 0-100 chimera_score. Not a value judgment the
    way objectivity's red/green was — green/accessible, red/dense is just
    the readable convention for a difficulty metric on a general news feed."""
    return 'green' if score < 30 else ('yellow' if score < 60 else 'red')


def _scan_arc_patterns(text):
    """Return list of ARC codes mentioned in a text block."""
    found = []
    text_upper = text.upper()
    for code, name in ARC_PATTERNS.items():
        if code in text_upper or name.upper() in text_upper:
            found.append(code)
    return found

def _bar(value, max_value, width=30):
    """Simple ASCII progress bar."""
    if max_value == 0:
        return '░' * width
    filled = int(width * value / max_value)
    return '█' * filled + '░' * (width - filled)

# --- Content-protection guards ------------------------------------------------
# Bulk remove/trim flows operate on content_type == news (the default) only.
# reference articles (curated permanent profiles — Plantorium etc.) and
# arc:pinned_articles members (course-referenced ephemera) are excluded from
# every bulk path. [2f] is the single deliberate per-id override.
from retention import PINNED_SET, purge_article_satellites, _character_state_keys

def _protection(r, aid):
    """'reference' / 'pinned' / None for one article id."""
    if (r.hget(f"article:{aid}", "content_type") or "news") == "reference":
        return "reference"
    if r.sismember(PINNED_SET, aid):
        return "pinned"
    return None

def partition_protected(r, rows, aid_index=1):
    """Split delete candidates into (deletable, {'reference': X, 'pinned': Y}).
    Rows are the (key, aid, ...) tuples the removal flows build, or bare ids."""
    deletable, excluded = [], {"reference": 0, "pinned": 0}
    for row in rows:
        aid = row[aid_index] if isinstance(row, (tuple, list)) else row
        p = _protection(r, aid)
        if p:
            excluded[p] += 1
        else:
            deletable.append(row)
    return deletable, excluded

def _print_exclusions(n_selected, excluded):
    print(colored(
        f"  🛡️  {n_selected} news article(s) selected; excluded: "
        f"{excluded['reference']} reference, {excluded['pinned']} pinned (arc:pinned_articles)",
        "yellow"))

def _delete_articles(r, solr, matching, label):
    """Common delete loop for (key, aid, ...) tuples. Batches Solr deletes.
    Drops reference/pinned rows as a last line of defense — flows partition
    before their DRY RUN so previews are honest; this catches new callers."""
    matching, excluded = partition_protected(r, matching)
    if excluded["reference"] or excluded["pinned"]:
        _print_exclusions(len(matching), excluded)
    aids = []
    char_state_keys = _character_state_keys(r)
    for row in matching:
        key, aid = row[0], row[1]
        r.delete(key)
        r.zrem("feed", aid)
        r.srem("processed_hashes", aid)
        purge_article_satellites(r, aid, char_state_keys)
        aids.append(aid)
    solr_delete_batch(solr, aids)
    print(colored(f"✅ Deleted {len(aids)} {label} article(s) from Redis and Solr.", "green"))

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

    query            = input("Search query (leave blank for filter-only): ").strip()
    start_date_input = input("Start date (YYYY-MM-DD, optional): ").strip()
    end_date_input   = input("End date (YYYY-MM-DD, optional): ").strip()
    # Arc's chimera_score is 0-100 readability difficulty, not Hunt's 0-1
    # objectivity ratio — see the note above _chimera_color. The comparison
    # below is scale-agnostic (just compares whatever's typed against the
    # raw stored value), so this only needed the example text fixed.
    score_filter     = input("Chimera score filter (e.g. >70  <20  blank=none): ").strip()

    score_op, score_val = None, None
    if score_filter:
        m = re.match(r'([<>]=?)\s*([\d.]+)', score_filter)
        if m:
            score_op  = m.group(1)
            score_val = float(m.group(2))
        else:
            print(colored("⚠️  Score filter ignored — use format >70 or <20", "yellow"))

    def passes_score(data):
        if score_op is None:
            return True
        s = _get_chimera_score(data)
        if s is None:
            return False
        if score_op == '>':  return s > score_val
        if score_op == '>=': return s >= score_val
        if score_op == '<':  return s < score_val
        if score_op == '<=': return s <= score_val
        return True

    # Solr path — fast full-text, no score filter
    if query and solr and not score_filter:
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

    # Redis scan path — supports all filters including chimera score
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
        if not passes_score(data):            continue

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

        s = _get_chimera_score(data)
        score_str = f'  χ={s:.0f}' if s is not None else ''
        matches.append((raw_ts, data.get("title", ""), article_id, score_str))

    print(f"Found {colored(str(len(matches)), 'cyan')} results:")
    for ts_str, title, aid, score_str in matches[:20]:
        print(f"  {str(ts_str)[:10]:10} | {title[:65]}{score_str}")
    if len(matches) > 20:
        print(f"  ... {len(matches)-20} more not shown")

    _maybe_export_csv([(ts, t, aid) for ts, t, aid, _ in matches], ('timestamp','title','article_id'))

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

# ==============================================================================
# [2] Emergency Removal sub-menu
# ==============================================================================

def emergency_removal_menu(r, solr):
    print(colored("\n--- [2] Emergency Content Removal ---", "cyan"))
    print("  [a] Remove by title phrase")
    print("  [b] Remove by domain          (e.g. ft.com — all subdomains)")
    print("  [c] Remove by language         (e.g. ru, de, zh)")
    print("  [d] Remove by Chimera score    (e.g. divisive articles below threshold)")
    print("  [e] Remove by Sentinel verdict  (SYNTHETIC / UNCERTAIN / HUMAN)")
    print("  [f] Remove ONE article by exact id (override — may target reference/pinned)")
    print("  [q] Back\n")
    sub = input("Select: ").strip().lower()
    if   sub == 'a': emergency_removal(r, solr)
    elif sub == 'b': remove_by_domain(r, solr)
    elif sub == 'c': remove_by_language(r, solr)
    elif sub == 'd': remove_by_score(r, solr)
    elif sub == 'e': remove_by_sentinel(r, solr)
    elif sub == 'f': remove_by_id_override(r, solr)
    elif sub in ('q', ''): return
    else: print(colored("Invalid selection.", "red"))


def emergency_removal(r, solr):
    print(colored("\n--- [2a] Remove by Title Phrase ---", "cyan"))
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

    matching, excluded = partition_protected(r, matching)
    _print_exclusions(len(matching), excluded)
    if not matching:
        print(colored("All matches are protected content — nothing deletable. Use [2f] to override.", "green"))
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

    _delete_articles(r, solr, matching, "matched")


def remove_by_id_override(r, solr):
    """[2f] The ONLY flow that can delete reference/pinned content. One article
    per run, exact id required, and the id itself is the confirmation phrase —
    no bulk selection can reach this path."""
    print(colored("\n--- [2f] Deliberate Removal by Exact ID (override) ---", "cyan"))
    aid = input("Exact article id: ").strip()
    if not aid:
        return
    key = f"article:{aid}"
    if not r.exists(key):
        print(colored("No such article.", "red"))
        return
    title = r.hget(key, "title") or "(no title)"
    prot = _protection(r, aid)
    print(f"  {title[:70]}")
    print(f"  protection: {colored(prot or 'none (news)', 'red' if prot else 'green')}")
    print(colored("\n⚠️  Type the article id again to confirm deletion (anything else aborts):", "yellow"))
    if input("> ").strip() != aid:
        print("Aborted.")
        return
    r.delete(key)
    r.zrem("feed", aid)
    r.srem("processed_hashes", aid)
    r.srem(PINNED_SET, aid)
    purge_article_satellites(r, aid)
    solr_delete_batch(solr, [aid])
    print(colored(f"✅ Deleted {aid} (override).", "green"))


def remove_by_domain(r, solr):
    print(colored("\n--- [2b] Remove by Domain ---", "cyan"))
    print("Deletes ALL articles from a given domain (e.g. ft.com).")
    print("Matches any subdomain: www.ft.com, blogs.ft.com, amp.ft.com → all gone.\n")

    domain_input = input("Domain to purge (e.g. ft.com): ").strip().lower()
    if not domain_input:
        return
    if domain_input.startswith('www.'):
        domain_input = domain_input[4:]

    print(colored(f"\nScanning all articles for domain '{domain_input}'...", "yellow"))

    matching = []
    for key in r.scan_iter("article:*"):
        url = r.hget(key, "url") or r.hget(key, "sourceUrl") or ''
        if not url:
            continue
        if _extract_registered_domain(url) == domain_input:
            aid   = key.split(":", 1)[-1]
            title = r.hget(key, "title") or "(no title)"
            matching.append((key, aid, title, url))

    if not matching:
        print(colored(f"No articles found from '{domain_input}'.", "green"))
        return

    matching, excluded = partition_protected(r, matching)
    _print_exclusions(len(matching), excluded)
    if not matching:
        print(colored("All matches are protected content — nothing deletable. Use [2f] to override.", "green"))
        return

    print(colored(f"\nDRY RUN — {len(matching)} article(s) from '{domain_input}' would be deleted:", "yellow"))
    for _, aid, title, url in matching[:20]:
        solr_status = ''
        if solr:
            try:
                res = solr.search(f'id:"{aid}"', rows=1, fl='id')
                solr_status = colored(' [in Solr]', 'blue') if res.hits > 0 else colored(' [not in Solr]', 'dark_grey')
            except Exception:
                pass
        print(f"  - {title[:65]}{solr_status}")
    if len(matching) > 20:
        print(f"  ... and {len(matching) - 20} more")

    if input(f"\nDelete ALL {len(matching)} articles from '{domain_input}' (Redis + Solr)? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    _delete_articles(r, solr, matching, f"'{domain_input}'")


def remove_by_language(r, solr):
    print(colored("\n--- [2c] Remove by Language ---", "cyan"))
    print("Deletes ALL articles with a given source_lang (ISO 639-1 code).")
    print("Examples: ru = Russian, de = German, zh = Chinese, ar = Arabic\n")

    lang_input = input("Language code to purge (e.g. ru): ").strip().lower()
    if not lang_input:
        return

    print(colored(f"\nScanning for source_lang='{lang_input}'...", "yellow"))

    matching = []
    for key in r.scan_iter("article:*"):
        lang = r.hget(key, "source_lang") or ''
        if lang.lower() == lang_input:
            aid   = key.split(":", 1)[-1]
            title = r.hget(key, "title") or "(no title)"
            url   = r.hget(key, "url") or r.hget(key, "sourceUrl") or ''
            matching.append((key, aid, title, url))

    if not matching:
        print(colored(f"No articles found with source_lang='{lang_input}'.", "green"))
        return

    matching, excluded = partition_protected(r, matching)
    _print_exclusions(len(matching), excluded)
    if not matching:
        print(colored("All matches are protected content — nothing deletable. Use [2f] to override.", "green"))
        return

    print(colored(f"\nDRY RUN — {len(matching)} article(s) with lang='{lang_input}' would be deleted:", "yellow"))
    for _, aid, title, url in matching[:20]:
        domain = _extract_registered_domain(url)
        print(f"  - [{domain:20}] {title[:55]}")
    if len(matching) > 20:
        print(f"  ... and {len(matching) - 20} more")

    if input(f"\nDelete ALL {len(matching)} '{lang_input}' articles (Redis + Solr)? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    _delete_articles(r, solr, matching, f"'{lang_input}'")


def remove_by_score(r, solr):
    """[2d] Remove articles above or below a chimera_score threshold.

    On Arc — this stack — chimera_score is a 0-100 readability-difficulty
    composite (FK/Coleman-Liau/SMOG/Dale-Chall averaged; see main.py's
    compute_chimera), NOT an objectivity ratio. Hunt's copy of this
    function is correct for its own 0-1 objectivity field; don't resync
    this prompt text from there. Fixed 2026-08-27 — see ops/RUNBOOK.md,
    same fork-split confusion as the mailer digest bug and kasmir7's own
    inspect-article display.
    """
    print(colored("\n--- [2d] Remove by Chimera Score ---", "cyan"))
    print("Chimera score: 0 = easiest (Kindergarten), 100 = hardest (Quantum Electrodynamics).")
    print("Examples:")
    print("  <10   — suspiciously trivial (likely a stub/junk scrape, not real prose)")
    print("  >90   — extreme outliers (genuinely dense text, or a parsing artifact worth checking)")
    print("  >70   — prune the densest tier if it's skewing the feed's reading level\n")

    expr = input("Score expression (e.g. <0.2): ").strip()
    if not expr:
        return

    m = re.match(r'([<>]=?)\s*([\d.]+)', expr)
    if not m:
        print(colored("Invalid format. Use <0.2 or >=0.5 etc.", "red"))
        return

    op  = m.group(1)
    val = float(m.group(2))

    def passes(score):
        if op == '<':  return score < val
        if op == '<=': return score <= val
        if op == '>':  return score > val
        if op == '>=': return score >= val
        return False

    print(colored(f"\nScanning for articles with chimera_score {op}{val}...", "yellow"))

    matching = []
    no_score  = 0
    for key in r.scan_iter("article:*"):
        data = r.hgetall(key)
        s = _get_chimera_score(data)
        if s is None:
            no_score += 1
            continue
        if passes(s):
            aid   = key.split(":", 1)[-1]
            title = data.get("title", "(no title)")
            matching.append((key, aid, title, s))

    if no_score:
        print(colored(f"  ℹ️  {no_score} articles have no chimera_score — skipped", "yellow"))

    if not matching:
        print(colored(f"No articles found with score {op}{val}.", "green"))
        return

    matching, excluded = partition_protected(r, matching)
    _print_exclusions(len(matching), excluded)
    if not matching:
        print(colored("All matches are protected content — nothing deletable. Use [2f] to override.", "green"))
        return

    # Sort worst-first (lowest score first for < ops, highest for > ops)
    reverse = op.startswith('>')
    matching.sort(key=lambda x: x[3], reverse=reverse)

    print(colored(f"\nDRY RUN — {len(matching)} article(s) with score {op}{val}:", "yellow"))
    for _, aid, title, s in matching[:25]:
        bar = _bar(s, 100.0, width=20)
        print(f"  χ={colored(f'{s:.0f}', _chimera_color(s))} [{bar}] {title[:52]}")
    if len(matching) > 25:
        print(f"  ... and {len(matching) - 25} more")

    if input(f"\nDelete ALL {len(matching)} articles with score {op}{val} (Redis + Solr)? (yes/no): ").lower() != 'yes':
        print("Aborted.")
        return

    _delete_articles(r, solr, matching, f"score {op}{val}")


def remove_by_sentinel(r, solr):
    """[2e] Remove articles by Sentinel verdict."""
    print(colored("\n--- [2e] Remove by Sentinel Verdict ---", "cyan"))
    print("Sentinel verdicts:")
    print(f"  {colored('HUMAN',     'green')}      — likely human-authored  (<20% synthetic probability)")
    print(f"  {colored('UNCERTAIN', 'yellow')}  — ambiguous              (20–60%)")
    print(f"  {colored('SYNTHETIC', 'red')}  — likely AI-generated    (>80%)\n")

    verdict_input = input("Verdict to purge (HUMAN / UNCERTAIN / SYNTHETIC): ").strip().upper()
    if verdict_input not in ("HUMAN", "UNCERTAIN", "SYNTHETIC"):
        print(colored("Invalid verdict. Must be HUMAN, UNCERTAIN, or SYNTHETIC.", "red"))
        return

    print(colored(f"\nScanning for sentinel_verdict='{verdict_input}'...", "yellow"))

    matching = []
    for key in r.scan_iter("article:*"):
        verdict = r.hget(key, "sentinel_verdict") or ''
        if verdict.upper() == verdict_input:
            aid   = key.split(":", 1)[-1]
            title = r.hget(key, "title") or "(no title)"
            url   = r.hget(key, "url") or r.hget(key, "sourceUrl") or ''
            matching.append((key, aid, title, url))

    if not matching:
        print(colored(f"No articles found with verdict '{verdict_input}'.", "green"))
        return

    matching, excluded = partition_protected(r, matching)
    _print_exclusions(len(matching), excluded)
    if not matching:
        print(colored("All matches are protected content — nothing deletable. Use [2f] to override.", "green"))
        return

    print(colored(f"\nDRY RUN — {len(matching)} {verdict_input} article(s) would be deleted:", "yellow"))
    for _, aid, title, url in matching[:20]:
        domain = _extract_registered_domain(url)
        print(f"  - [{domain:20}] {title[:55]}")
    if len(matching) > 20:
        print(f"  ... and {len(matching) - 20} more")

    # Extra confirmation for HUMAN (probably a mistake)
    confirm_phrase = f"delete {verdict_input.lower()}"
    print(colored(f"\n⚠️  Type '{confirm_phrase}' to confirm (anything else aborts):", "yellow"))
    if input("> ").strip().lower() != confirm_phrase:
        print("Aborted.")
        return

    _delete_articles(r, solr, matching, f"{verdict_input}")


# ==============================================================================
# [3] Trim Database
# ==============================================================================

def trim_database(r, solr):
    print(colored("\n--- [3] Trim Database ---", "cyan"))
    print("  count N              → keep latest N articles (oldest deleted)")
    print("  days N               → delete articles older than N days")
    print("  hours N              → delete articles older than N hours")
    print("  directive NAME N     → keep latest N in directive NAME (partial match ok)")
    print()
    print("  Examples:")
    print("    count 4000         → keep newest 4000, delete the rest")
    print("    days 14            → delete everything older than 2 weeks")
    print("    directive Tech 500 → keep 500 newest Technology articles")

    trim_cmd = input("\nTrim command: ").strip()
    parts = trim_cmd.split()

    if not parts:
        print(colored("No command entered.", "red"))
        return

    method = parts[0].lower()

    # --- directive trim ---
    if method == 'directive':
        if len(parts) < 3:
            print(colored("Usage: directive <name_fragment> <keep_count>", "red"))
            return
        directive_fragment = parts[1].lower()
        try:
            keep = int(parts[2])
        except ValueError:
            print(colored("keep_count must be an integer.", "red"))
            return

        print(colored(f"\nScanning for directive matching '{directive_fragment}'...", "yellow"))
        dir_articles = []
        for aid in r.zrange("feed", 0, -1):
            cat = (r.hget(f"article:{aid}", "category") or
                   r.hget(f"article:{aid}", "directive") or '').lower()
            if directive_fragment in cat:
                ts_raw = r.hget(f"article:{aid}", "timestamp") or '0'
                try:
                    ts = parser.parse(ts_raw).timestamp()
                except Exception:
                    ts = 0
                dir_articles.append((ts, aid))

        if not dir_articles:
            print(colored(f"No articles found matching directive '{directive_fragment}'.", "yellow"))
            return

        dir_articles.sort()  # oldest first
        to_delete = dir_articles[:-keep] if keep < len(dir_articles) else []

        if not to_delete:
            print(f"  {len(dir_articles)} articles in directive — nothing to trim (keep={keep}).")
            return

        to_delete, excluded = partition_protected(r, to_delete)
        _print_exclusions(len(to_delete), excluded)
        if not to_delete:
            print(colored("All candidates are protected content — nothing deletable.", "green"))
            return

        print(colored(f"\nDRY RUN — keeping {keep} newest, deleting {len(to_delete)} oldest:", "yellow"))
        for ts, aid in to_delete[:10]:
            title = r.hget(f"article:{aid}", "title") or "(no title)"
            print(f"  {datetime.fromtimestamp(ts).strftime('%Y-%m-%d'):10} | {title[:65]}")
        if len(to_delete) > 10:
            print(f"  ... and {len(to_delete) - 10} more")

        if input(f"\nDelete {len(to_delete)} oldest '{directive_fragment}' articles? (yes/no): ").lower() != 'yes':
            print("Aborted.")
            return

        deleted = 0
        aids = []
        char_state_keys = _character_state_keys(r)
        for ts, aid in to_delete:
            r.delete(f"article:{aid}")
            r.zrem("feed", aid)
            r.srem("processed_hashes", aid)
            purge_article_satellites(r, aid, char_state_keys)
            aids.append(aid)
            deleted += 1
        solr_delete_batch(solr, aids)
        print(colored(f"✅ Trimmed {deleted} oldest '{directive_fragment}' articles.", "green"))
        return

    # --- standard trims ---
    try:
        value = int(parts[1])
    except (IndexError, ValueError):
        print(colored("Invalid format. Use: method value", "red"))
        return

    if method == 'count':
        total = r.zcard("feed")
        if value >= total:
            print(f"Feed has {total} articles — nothing to trim.")
            return
        ids_to_delete = r.zrange("feed", 0, total - value - 1)
        if not ids_to_delete:
            print("No articles matched the trim criteria.")
            return
        ids_to_delete, excluded = partition_protected(r, ids_to_delete)
        _print_exclusions(len(ids_to_delete), excluded)
        if not ids_to_delete:
            print(colored("All candidates are protected content — nothing deletable.", "green"))
            return
        print(colored(f"\nDRY RUN — {len(ids_to_delete)} article(s) would be deleted.", "yellow"))
        if input("Proceed? (yes/no): ").lower() != 'yes':
            print("Aborted.")
            return
        deleted = 0
        char_state_keys = _character_state_keys(r)
        for aid in ids_to_delete:
            pipe = r.pipeline()
            pipe.delete(f"article:{aid}")
            pipe.zrem("feed", aid)
            pipe.srem("processed_hashes", aid)
            pipe.execute()
            purge_article_satellites(r, aid, char_state_keys)
            deleted += 1
            if deleted % 500 == 0:
                print(f"  Redis: {deleted}/{len(ids_to_delete)} removed...", end='\r')
        print(f"  Redis: {deleted} articles removed.           ")
        solr_delete_batch(solr, list(ids_to_delete))
        print(colored(f"✅ Trim complete. Deleted {deleted} article(s) from Redis and Solr.", "green"))
        return

    if method in ('days', 'hours'):
        # Delegate to shared library so scribe's automated pruner and the
        # interactive menu share one code path (retention.py).
        from retention import trim_by_hours
        hours = value * 24 if method == 'days' else value
        preview = trim_by_hours(r, solr, hours, dry_run=True)
        exc = preview.get('excluded', {"reference": 0, "pinned": 0})
        protected = exc['reference'] + exc['pinned']
        if preview['found'] == 0:
            # Distinguish "nothing that old" from "matched, but all protected" —
            # a zero-delete on a corpus full of pinned/reference must never again
            # read as a bug (it cost an hour on 2026-07-18).
            if protected:
                print(colored(
                    f"  {protected} article(s) older than {value} {method} matched, but ALL are "
                    f"protected ({exc['pinned']} pinned, {exc['reference']} reference) — nothing "
                    f"deletable. Not an error.", "green"))
            else:
                print(f"No articles older than {value} {method} — nothing to trim.")
            return
        _print_exclusions(preview['found'], exc)
        print(colored(f"\nDRY RUN — {preview['found']} article(s) would be deleted.", "yellow"))
        if input("Proceed? (yes/no): ").lower() != 'yes':
            print("Aborted.")
            return
        result = trim_by_hours(r, solr, hours, dry_run=False)
        exc = result.get('excluded', {"reference": 0, "pinned": 0})
        print(colored(f"✅ Trim complete. Deleted {result['deleted']} news article(s) from Redis and Solr "
                      f"(excluded: {exc['reference']} reference, {exc['pinned']} pinned).", "green"))
        return

    print(colored(f"Unknown method: {method}", "red"))


# ==============================================================================
# [4] Inspect Article
# ==============================================================================

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
    print(f"  Domain     : {_extract_registered_domain(data.get('url', data.get('sourceUrl', '')))}")
    print(f"  SourceURL  : {data.get('sourceUrl', colored('MISSING', 'red'))}")
    print(f"  Image URL  : {data.get('imageUrl', 'N/A')}")
    print(f"  Timestamp  : {data.get('timestamp', 'N/A')}")
    print(f"  Category   : {data.get('category', data.get('directive', 'N/A'))}")
    print(f"  Language   : {data.get('source_lang', colored('N/A', 'dark_grey'))}")
    verdict = data.get('sentinel_verdict', '')
    if verdict:
        vc = 'green' if 'HUMAN' in verdict.upper() else ('red' if 'SYNTHETIC' in verdict.upper() else 'yellow')
        print(f"  Sentinel   : {colored(verdict, vc)}")
    else:
        print(f"  Sentinel   : {colored('N/A', 'dark_grey')}")

    print(colored("\n--- Chimera Score ---", "yellow"))
    chimera = _get_chimera_score(data)
    if chimera is not None:
        bar = _bar(chimera, 100.0, width=35)
        score_color = _chimera_color(chimera)
        print(f"  {colored(f'{chimera:.0f}/100', score_color)} [{bar}]")
        if chimera < 30:
            print(colored("  ℹ️  Accessible — general-audience reading level", "green"))
        elif chimera < 60:
            print(colored("  ℹ️  Moderate — some technical/dense language", "yellow"))
        else:
            print(colored("  ⚠️  Dense — advanced reading level, verify NLP quality", "red"))
    else:
        print(colored("  No chimera score available", "dark_grey"))

    print(colored("\n--- Other Scores ---", "yellow"))
    dossier_raw = data.get('dossier', '{}')
    try:
        dossier = json.loads(dossier_raw)
        for k, v in dossier.items():
            if k != 'chimera_score':
                print(f"  {k}: {v}")
    except Exception:
        if dossier_raw and dossier_raw != '{}':
            print(f"  (raw) {dossier_raw[:200]}")

    print(colored("\n--- Content Lengths ---", "yellow"))
    for field in ('article_text', 'red_team_analysis', 'blue_team_analysis', 'purple_team_analysis'):
        val = data.get(field, '')
        status = colored(f'{len(val):6} chars', 'green' if val else 'red')
        print(f"  {field:28}: {status}")

    # ARC pattern scan on purple_team_analysis
    purple = data.get('purple_team_analysis', '')
    if purple:
        print(colored("\n--- A.R.C. Patterns Detected ---", "yellow"))
        found = _scan_arc_patterns(purple)
        if found:
            for code in found:
                name = ARC_PATTERNS.get(code, '?')
                print(f"  {colored(code, 'magenta')} — {name}")
        else:
            print(colored("  No specific ARC pattern codes flagged.", "dark_grey"))
    else:
        print(colored("\n  ⚠️  No purple_team_analysis — ARC pattern scan skipped", "yellow"))

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


# ==============================================================================
# [5] Re-index Solr
# ==============================================================================

def reindex_solr(r, solr):
    print(colored("\n--- [5] Re-index Solr ---", "cyan"))
    if not solr:
        print(colored("❌ Solr unavailable.", "red"))
        return

    all_keys = [f"article:{aid}" for aid in r.zrange("feed", 0, -1)]
    total = len(all_keys)
    print(f"Checking {total} feed articles against Solr...")

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
    print(f"\nAlready in Solr  : {colored(str(len(indexed_ids)), 'green')}")
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


# ==============================================================================
# [6] Solr Diagnostics
# ==============================================================================

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


# ==============================================================================
# [7] Purge Solr Orphans
# ==============================================================================

def purge_solr_orphans(r, solr):
    print(colored("\n--- [7] Purge Solr Orphans ---", "cyan"))
    print("Finds Solr documents with no matching Redis article and removes them.")
    if not solr:
        print(colored("❌ Solr unavailable.", "red"))
        return

    print("Loading Redis article IDs...", end="\r")
    redis_ids = {k.replace("article:", "") for k in r.keys("article:*")}
    print(f"Redis articles   : {colored(str(len(redis_ids)), 'cyan')}          ")

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


# ==============================================================================
# [8] Purge Redis Orphans
# ==============================================================================

def purge_redis_orphans(r, solr):
    print(colored("\n--- [8] Purge Redis Orphans ---", "cyan"))
    print("Finds article: hashes in Redis with no matching feed entry and removes them.")
    print("Also clears each orphan's satellite state (comments, translations, grade,")
    print("character state, images, audio) — the same purge_article_satellites call")
    print("cleanup.py's automated sweep and every other delete flow here already make.")

    feed_ids = set(r.zrange("feed", 0, -1))
    all_keys = r.keys("article:*")
    orphan_keys = [k for k in all_keys if k.replace("article:", "") not in feed_ids]

    protected = [k for k in orphan_keys if _protection(r, k.replace("article:", ""))]
    if protected:
        print(colored(f"  🛡️  {len(protected)} orphan(s) are reference/pinned — excluded from purge", "yellow"))
        orphan_keys = [k for k in orphan_keys if k not in set(protected)]

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
    char_state_keys = _character_state_keys(r)
    for key in orphan_keys:
        aid = key.replace("article:", "")
        r.delete(key)
        r.srem("processed_hashes", aid)
        purge_article_satellites(r, aid, char_state_keys)
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

    print(colored(f"✅ Purged {deleted} orphaned Redis hash(es) and their satellite state.", "green"))


# ==============================================================================
# [9] Intelligence Dashboard
# ==============================================================================

def intelligence_dashboard(r, solr):
    print(colored("\n--- [9] Intelligence Dashboard ---", "cyan"))
    print("Scanning corpus for epistemic health metrics...\n")

    total            = 0
    domain_counts    = Counter()
    lang_counts      = Counter()
    directive_counts = Counter()
    sentinel_counts  = Counter()
    ctype_counts     = Counter()
    scores           = []
    score_buckets    = Counter()
    missing_fields   = Counter()

    TRACKED_FIELDS = [
        'title', 'sourceUrl', 'red_team_analysis', 'blue_team_analysis',
        'purple_team_analysis', 'sentinel_verdict', 'source_lang', 'chimera_score'
    ]

    for key in r.scan_iter("article:*"):
        data = r.hgetall(key)
        total += 1

        # Use sourceUrl (original story) not url (arc-codex.com page)
        source_url = data.get('sourceUrl') or data.get('url') or ''
        domain_counts[_extract_registered_domain(source_url) or '(unknown)'] += 1

        lang = data.get('source_lang') or '(unknown)'
        lang_counts[lang] += 1

        cat = data.get('category') or data.get('directive') or '(unknown)'
        directive_counts[cat] += 1

        ctype_counts[data.get('content_type') or 'news'] += 1

        # sentinel_verdict lives inside sentinel_analysis JSON blob
        sentinel_verdict = data.get('sentinel_verdict', '')
        if not sentinel_verdict:
            try:
                sa = json.loads(data.get('sentinel_analysis', '{}'))
                assessment = sa.get('assessment', '')
                # Normalize: LIKELY_HUMAN -> HUMAN, UNCERTAIN, SYNTHETIC
                if 'HUMAN' in assessment.upper():
                    sentinel_verdict = 'HUMAN'
                elif 'SYNTHETIC' in assessment.upper():
                    sentinel_verdict = 'SYNTHETIC'
                elif assessment:
                    sentinel_verdict = 'UNCERTAIN'
            except Exception:
                pass
        sentinel_counts[(sentinel_verdict.upper() or '(NONE)')] += 1

        s = _get_chimera_score(data)
        if s is not None:
            scores.append(s)
            # Arc's chimera_score is 0-100, not Hunt's 0-1 — see the note
            # above _chimera_color. int(s * 10) collapsed every real score
            # into bucket 9 via the min() clamp; int(s / 10) buckets by
            # actual 10-point grade-level bands. Fixed 2026-08-27.
            bucket = min(int(s / 10), 9)
            score_buckets[bucket] += 1

        for field in TRACKED_FIELDS:
            if field == 'chimera_score':
                present = _get_chimera_score(data) is not None
            elif field == 'sentinel_verdict':
                # Check both top-level field and sentinel_analysis blob
                present = bool(data.get('sentinel_verdict') or data.get('sentinel_analysis'))
            else:
                val = data.get(field, '')
                present = bool(val and val != '{}')
            if not present:
                missing_fields[field] += 1

    W = 28  # bar width

    print(colored(f"  ═══ CORPUS OVERVIEW ═══", "white"))
    print(f"  Total articles scanned : {colored(str(total), 'cyan')}")
    scored_count = len(scores)
    if total:
        print(f"  Scored articles        : {scored_count} ({scored_count/total*100:.1f}%)")
    ctype_str = ", ".join(f"{k}={v}" for k, v in ctype_counts.most_common())
    print(f"  Content types          : {colored(ctype_str, 'cyan')}; pinned={colored(str(r.scard(PINNED_SET)), 'cyan')}")
    print()

    # --- Top sources ---
    print(colored("  TOP 20 SOURCES", "yellow"))
    print(f"  {'Domain':<30} {'N':>5}  {'%':>5}  Bar")
    print(f"  {'─'*30} {'─'*5}  {'─'*5}  {'─'*W}")
    top_domains = domain_counts.most_common(20)
    max_d = top_domains[0][1] if top_domains else 1
    for domain, count in top_domains:
        pct = count / total * 100
        print(f"  {domain:<30} {count:>5}  {pct:>4.1f}%  {_bar(count, max_d, W)}")

    # --- Language ---
    print()
    print(colored("  LANGUAGE BREAKDOWN", "yellow"))
    print(f"  {'Lang':<12} {'N':>5}  {'%':>5}  Bar")
    print(f"  {'─'*12} {'─'*5}  {'─'*5}  {'─'*W}")
    for lang, count in lang_counts.most_common(15):
        pct = count / total * 100
        print(f"  {lang:<12} {count:>5}  {pct:>4.1f}%  {_bar(count, lang_counts.most_common(1)[0][1], W)}")

    # --- Directives ---
    print()
    print(colored("  DIRECTIVE / CATEGORY BREAKDOWN", "yellow"))
    print(f"  {'Directive':<36} {'N':>5}  {'%':>5}  Bar")
    print(f"  {'─'*36} {'─'*5}  {'─'*5}  {'─'*W}")
    top_dirs = directive_counts.most_common(20)
    max_dir  = top_dirs[0][1] if top_dirs else 1
    for directive, count in top_dirs:
        pct = count / total * 100
        print(f"  {directive[:36]:<36} {count:>5}  {pct:>4.1f}%  {_bar(count, max_dir, W)}")

    # --- Sentinel ---
    print()
    print(colored("  SENTINEL VERDICT BREAKDOWN", "yellow"))
    verdict_colors = {'HUMAN': 'green', 'UNCERTAIN': 'yellow', 'SYNTHETIC': 'red', '(NONE)': 'dark_grey'}
    for verdict in ['HUMAN', 'UNCERTAIN', 'SYNTHETIC', '(NONE)']:
        count = sentinel_counts.get(verdict, 0)
        pct   = count / total * 100 if total else 0
        vc    = verdict_colors.get(verdict, 'white')
        print(f"  {colored(f'{verdict:<12}', vc)} {count:>5}  {pct:>4.1f}%  {_bar(count, total, W)}")

    # --- Chimera score histogram ---
    print()
    print(colored("  CHIMERA SCORE DISTRIBUTION   0=accessible → 100=dense (readability difficulty)", "yellow"))
    if scores:
        avg_score = sum(scores) / len(scores)
        max_bucket_val = max(score_buckets.values()) if score_buckets else 1
        for i in range(10):
            label = f"{i*10:>3}–{(i+1)*10:<3}"
            count = score_buckets.get(i, 0)
            pct   = count / scored_count * 100 if scored_count else 0
            bucket_color = 'green' if i < 3 else ('yellow' if i < 6 else 'red')
            bar = _bar(count, max_bucket_val, W)
            print(f"  {colored(label, bucket_color)}  {count:>5}  {pct:>4.1f}%  {bar}")

        avg_color = _chimera_color(avg_score)
        print()
        print(f"  Average  : {colored(f'{avg_score:.1f}', avg_color)}  {_bar(avg_score, 100.0, W)}")
        low_count = sum(1 for s in scores if s < 30)
        high_count = sum(1 for s in scores if s >= 70)
        print(f"  Accessible (<30) : {colored(str(low_count), 'green')} articles  "
              f"({low_count/scored_count*100:.1f}% of scored)")
        print(f"  Dense      (≥70) : {colored(str(high_count), 'red')} articles  "
              f"({high_count/scored_count*100:.1f}% of scored)")
    else:
        print(colored("  No scored articles found.", "yellow"))

    # --- Completeness ---
    print()
    print(colored("  CORPUS COMPLETENESS", "yellow"))
    print(f"  {'Field':<28}  {'Present':>8}  {'%':>6}  Bar")
    print(f"  {'─'*28}  {'─'*8}  {'─'*6}  {'─'*W}")
    for field in TRACKED_FIELDS:
        missing = missing_fields.get(field, 0)
        present = total - missing
        pct_present = present / total * 100 if total else 0
        status_color = 'green' if pct_present > 95 else ('yellow' if pct_present > 80 else 'red')
        bar = _bar(present, total, W)
        print(f"  {field:<28}  {colored(f'{present:>5}/{total}', status_color)}  "
              f"{pct_present:>5.1f}%  {bar}")

    # --- Course reference integrity (SoC) ---
    print()
    print(colored("  COURSE REFERENCE INTEGRITY (SoC db 2 + /plants catalog)", "yellow"))
    try:
        dangling = _soc_dangling_refs(r)
        if dangling is None:
            print(colored("  SoC Redis (db 2) unreachable — check skipped", "yellow"))
        elif not dangling:
            print(colored("  ✅ every course/badge/catalog reference resolves to a live article", "green"))
        else:
            print(colored(f"  ⚠️  {len(dangling)} dangling reference(s) — restore or unlink:", "red"))
            for aid, src in dangling[:10]:
                print(f"    {aid}  ← {src}")
            if len(dangling) > 10:
                print(f"    ... and {len(dangling) - 10} more")
    except Exception as e:
        print(colored(f"  integrity check failed: {e}", "red"))

    print()
    input(colored("  Press Enter to return to menu...", "dark_grey"))


def _soc_dangling_refs(r):
    """Article ids referenced by SoC durable keys (badges/passes/certs, db 2)
    and the /plants catalog that no longer resolve to a live article in arc
    (db 0), huntaegis (db 1), or SoC's own injected content (db 2). Returns
    [(aid, referencing_source)], or None if SoC's db is unreachable. Cache and
    feed keys are deliberately ignored — they expire and self-heal."""
    try:
        soc  = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                           db=2, decode_responses=True)
        hunt = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                           db=1, decode_responses=True)
        soc.ping()
    except Exception:
        return None

    hex32 = re.compile(r"[0-9a-f]{32}")
    refs = {}
    for pattern in ("soc:badge_issued:*", "soc:dynamic_pass:*", "soc:cert*", "soc:user*"):
        for key in soc.scan_iter(pattern):
            blob = key + " "
            t = soc.type(key)
            if t == "string":
                blob += soc.get(key) or ""
            elif t == "hash":
                blob += json.dumps(soc.hgetall(key))
            elif t == "set":
                blob += " ".join(soc.smembers(key))
            elif t == "list":
                blob += " ".join(soc.lrange(key, 0, -1))
            for aid in hex32.findall(blob):
                refs.setdefault(aid, key)

    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:5005/api/plants", timeout=10) as resp:
            catalog = json.loads(resp.read())
        for group in catalog.values():
            for entry in group:
                m = hex32.search(entry.get("url", ""))
                if m:
                    refs.setdefault(m.group(0), "/plants catalog")
    except Exception:
        pass

    dangling = []
    for aid, src in sorted(refs.items()):
        if not (r.exists(f"article:{aid}") or hunt.exists(f"article:{aid}")
                or soc.exists(f"article:{aid}")):
            dangling.append((aid, src))
    return dangling


# ==============================================================================
# [10] A.R.C. Pattern Scanner
# ==============================================================================

def arc_pattern_scanner(r, solr):
    print(colored("\n--- [10] A.R.C. Pattern Scanner ---", "cyan"))
    print("Scans purple_team_analysis across all articles to surface the most")
    print("prevalent rhetorical manipulation patterns in your corpus.\n")
    print("This is the epistemic fingerprint of your news cycle.")
    print("High prevalence of a pattern = readers are being systematically exposed to it.\n")

    limit_input = input("Articles to scan? (blank = all, or enter N for newest N): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None

    print(colored("\nScanning corpus for A.R.C. patterns...", "yellow"))

    pattern_counts   = Counter()
    pattern_articles = defaultdict(list)
    scanned = no_purple = 0

    all_ids = r.zrange("feed", 0, -1)
    if limit:
        all_ids = all_ids[-limit:]

    total = len(all_ids)
    for i, aid in enumerate(all_ids):
        purple = r.hget(f"article:{aid}", "purple_team_analysis") or ''
        if not purple:
            no_purple += 1
            scanned += 1
            continue

        title = r.hget(f"article:{aid}", "title") or "(no title)"
        found = _scan_arc_patterns(purple)
        for code in found:
            pattern_counts[code] += 1
            if len(pattern_articles[code]) < 5:
                pattern_articles[code].append((title, aid))

        scanned += 1
        if scanned % 200 == 0:
            print(f"  Scanned {scanned}/{total}...", end='\r')

    print(f"  Scanned {scanned}/{total} articles.                    ")
    if no_purple:
        print(colored(f"  ℹ️  {no_purple} articles had no purple_team_analysis", "yellow"))

    if not pattern_counts:
        print(colored("\nNo A.R.C. patterns detected. Either purple analyses are missing "
                      "or the AI isn't citing pattern codes explicitly.", "yellow"))
        return

    print()
    print(colored(f"  A.R.C. PATTERN FREQUENCY  (scanned {scanned} articles)", "yellow"))
    print(f"  {'Code':<12} {'Pattern Name':<30} {'Hits':>5}  {'% articles':>10}  Prevalence")
    print(f"  {'─'*12} {'─'*30} {'─'*5}  {'─'*10}  {'─'*25}")

    top_patterns = pattern_counts.most_common()
    max_hits = top_patterns[0][1] if top_patterns else 1

    for code, count in top_patterns:
        name = ARC_PATTERNS.get(code, '?')
        pct  = count / scanned * 100
        bar  = _bar(count, max_hits, width=25)
        count_color = 'red' if pct > 20 else ('yellow' if pct > 10 else 'green')
        print(f"  {colored(code, 'magenta'):<12} {name:<30} "
              f"{colored(str(count), count_color):>5}  {pct:>9.1f}%  {bar}")

    # Undetected patterns
    absent = set(ARC_PATTERNS.keys()) - set(pattern_counts.keys())
    if absent:
        print()
        print(colored(f"  {len(absent)} patterns NOT detected in this scan:", "dark_grey"))
        absent_names = [f"{code} ({ARC_PATTERNS[code]})" for code in sorted(absent)]
        # Print in 2 columns
        for i in range(0, len(absent_names), 2):
            left  = absent_names[i]
            right = absent_names[i+1] if i+1 < len(absent_names) else ''
            print(colored(f"    {left:<40} {right}", "dark_grey"))

    # Drill-down
    print()
    drill = input("Drill into pattern? Enter ARC code (e.g. ARC-0043) or blank to skip: ").strip().upper()
    if drill and drill in pattern_articles:
        name = ARC_PATTERNS.get(drill, '?')
        count = pattern_counts[drill]
        print(colored(f"\n  {drill} — {name}  ({count} articles, "
                      f"{count/scanned*100:.1f}% of corpus)", "magenta"))
        print(f"  Sample articles featuring this pattern:")
        for title, aid in pattern_articles[drill]:
            ts = r.hget(f"article:{aid}", "timestamp") or ''
            print(f"    {str(ts)[:10]:10}  {aid[:12]}  {title[:65]}")
        print()
        view = input("  Inspect one? Enter article ID (or blank): ").strip()
        if view:
            # Temporarily redirect to inspect with the given id
            _inspect_by_id(r, solr, view)

    print()
    input(colored("  Press Enter to return to menu...", "dark_grey"))


def _inspect_by_id(r, solr, article_id):
    """Helper: inspect without re-prompting for ID."""
    key = f"article:{article_id}"
    if not r.exists(key):
        print(colored(f"❌ Not found: {article_id}", "red"))
        return
    # Temporarily monkey-patch input to return the pre-known id — simpler to
    # just inline a stripped version of the display logic here.
    data = r.hgetall(key)
    print(colored(f"\n=== {article_id[:20]}... ===", "cyan"))
    print(f"  Title    : {data.get('title', 'N/A')}")
    print(f"  Domain   : {_extract_registered_domain(data.get('url', data.get('sourceUrl', '')))}")
    print(f"  Lang     : {data.get('source_lang', 'N/A')}")
    print(f"  Sentinel : {data.get('sentinel_verdict', 'N/A')}")
    s = _get_chimera_score(data)
    if s is not None:
        print(f"  Chimera  : {colored(f'{s:.0f}/100', _chimera_color(s))}")
    purple = data.get('purple_team_analysis', '')
    if purple:
        found = _scan_arc_patterns(purple)
        print(f"  ARC tags : {', '.join(found) if found else '(none flagged)'}")
        print(f"\n  Purple team excerpt:\n  {purple[:400]}...")

# ==============================================================================
# My Publications
# ==============================================================================
def my_publications(r, solr):
    """List articles published by the current owner (identified by owner field in Redis)."""
    # Your Google sub ID — set when X-User-Id header is passed from Next.js session
    MY_USER_ID = '106447029965347101642'
    print(colored("\n--- [11] My Publications ---", "cyan"))

    all_ids = r.zrange('feed', 0, -1)
    matches = []

    print(f"Scanning {len(all_ids)} articles...", end='\r')
    for aid in all_ids:
        owner = r.hget(f"article:{aid}", "owner") or ''
        origin = r.hget(f"article:{aid}", "origin") or ''
        # Match by owner (new articles) OR by origin != rss (pre-owner articles)
        if owner == MY_USER_ID or (not owner and origin and origin != 'rss'):
            title = r.hget(f"article:{aid}", "title") or 'Untitled'
            ts_raw = r.hget(f"article:{aid}", "timestamp") or ''
            try:
                ts = parser.parse(ts_raw).strftime('%Y-%m-%d %H:%M') if ts_raw else 'unknown'
            except Exception:
                ts = ts_raw[:16]
            matches.append((ts, title, aid, origin))
    matches.sort(reverse=True)
    print(f"Found {len(matches)} publication(s).          ")
    print("─────────────────────────────────────────────────────────")
    for i, (ts, title, aid, origin) in enumerate(matches, 1):
        src_color = 'green' if origin == 'text' else 'magenta' if origin == 'prompt' else 'yellow'
        print(f"  [{i:2}] {ts}  {colored(origin[:20], src_color):30}  {title[:55]}")
    print("─────────────────────────────────────────────────────────")

    if not matches:
        print(colored("  No manual publications found.", "yellow"))
        return

    choice = input("\nInspect or remove? Enter number (or q to return): ").strip().lower()
    if choice == 'q' or choice == '':
        return
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(matches):
            print(colored("Invalid selection.", "red"))
            return
        ts, title, aid, source = matches[idx]
        print(colored(f"\n=== {title[:60]} ===", "cyan"))
        data = r.hgetall(f"article:{aid}")
        print(f"  ID       : {aid}")
        print(f"  Source   : {source}")
        print(f"  Date     : {ts}")
        print(f"  URL      : {data.get('sourceUrl', 'N/A')}")
        print(f"  Image    : {data.get('imageUrl', 'N/A')}")
        s = _get_chimera_score(data)
        if s is not None:
            print(f"  Chimera  : {colored(f'{s:.0f}/100', _chimera_color(s))}")
        action = input("\n  [r] Remove  [q] Back: ").strip().lower()
        if action == 'r':
            confirm = input(f"  Remove '{title[:50]}'? (yes/no): ").strip()
            if confirm == 'yes':
                _delete_articles(r, solr, [(None, aid, title)], "manual publication")
    except (ValueError, IndexError):
        print(colored("Invalid selection.", "red"))

def generate_sitemap(r):
        """Generates sitemap.xml. Includes homepage, wiki directives, articles, library.
        Excludes visibility=private articles (mirrors main.py /api/sitemap filter)."""
        import xml.etree.ElementTree as ET
        import json
        import re
        from datetime import datetime
        print(colored("\n[!] Scanning Redis for published intelligence...", "yellow"))

        output_path = "/home/www/arc_stack/frontend/public/sitemap.xml"
        directives_path = "/home/www/arc_stack/frontend/public/directives.json"

        def _slugify(name):
            s = re.sub(r'[^a-z0-9]+', '-', name.lower())
            return re.sub(r'^-|-$', '', s)

        try:
            feed_ids = r.zrevrange('feed', 0, -1)
            root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

            # Static Homepage
            url_node = ET.SubElement(root, "url")
            ET.SubElement(url_node, "loc").text = "https://arc-codex.com/"
            ET.SubElement(url_node, "priority").text = "1.0"

            # Wiki index + per-directive pages (source of truth: directives.json)
            wiki_count = 0
            try:
                with open(directives_path, 'r', encoding='utf-8') as f:
                    groups = json.load(f)
                url_node = ET.SubElement(root, "url")
                ET.SubElement(url_node, "loc").text = "https://arc-codex.com/wiki"
                ET.SubElement(url_node, "priority").text = "0.8"
                wiki_count += 1
                for group in groups:
                    if group.get('topic') == 'System Directives':
                        continue
                    for d in group.get('directives', []):
                        name = d.get('name', '')
                        if not name:
                            continue
                        url_node = ET.SubElement(root, "url")
                        ET.SubElement(url_node, "loc").text = f"https://arc-codex.com/wiki/{_slugify(name)}"
                        ET.SubElement(url_node, "priority").text = "0.7"
                        wiki_count += 1
            except Exception as e:
                print(colored(f"[!] Wiki section skipped: {e}", "yellow"))

            count = 0
            for aid in feed_ids:
                aid_str = aid.decode('utf-8') if isinstance(aid, bytes) else aid
                article = r.hgetall(f"article:{aid_str}")

                vis_raw = article.get(b'visibility') or article.get('visibility')
                vis = vis_raw.decode('utf-8') if isinstance(vis_raw, bytes) else vis_raw
                if vis == 'private':
                    continue

                slug_raw = article.get(b'slug') or article.get('slug')
                ts_raw = article.get(b'timestamp') or article.get('timestamp')

                if slug_raw:
                    slug = slug_raw.decode('utf-8') if isinstance(slug_raw, bytes) else slug_raw
                else:
                    slug = aid_str

                url_node = ET.SubElement(root, "url")
                ET.SubElement(url_node, "loc").text = f"https://arc-codex.com/article/{slug}"

                if ts_raw:
                    ts = ts_raw.decode('utf-8') if isinstance(ts_raw, bytes) else ts_raw
                    if ts.isdigit():
                        lastmod = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
                    else:
                        lastmod = ts[:10]
                    ET.SubElement(url_node, "lastmod").text = lastmod

                ET.SubElement(url_node, "priority").text = "0.8"
                count += 1

            # --- Library section (top-100 index, shelves, individual works) ---
            today = datetime.now().strftime("%Y-%m-%d")

            def _lastmod(fetched_at):
                if not fetched_at:
                    return today
                fa = fetched_at.decode('utf-8') if isinstance(fetched_at, bytes) else fetched_at
                return fa[:10] if len(fa) >= 10 else today

            lib_count = 0

            # Static library landing pages
            for path in ("/library", "/library/shelves"):
                url_node = ET.SubElement(root, "url")
                ET.SubElement(url_node, "loc").text = f"https://arc-codex.com{path}"
                ET.SubElement(url_node, "lastmod").text = today
                ET.SubElement(url_node, "priority").text = "0.6"
                lib_count += 1

            # Shelf + work pages from SQLite (library moved out of Redis 2026-07-08)
            import library_db
            with library_db.db() as lib_conn:
                for shelf in library_db.list_shelves(lib_conn):
                    url_node = ET.SubElement(root, "url")
                    ET.SubElement(url_node, "loc").text = f"https://arc-codex.com/library/shelf/{shelf['slug']}"
                    ET.SubElement(url_node, "lastmod").text = _lastmod(shelf['fetched_at'])
                    ET.SubElement(url_node, "priority").text = "0.6"
                    lib_count += 1

                for row in library_db.iter_work_meta(lib_conn, ["gutenberg_id", "fetched_at"]):
                    url_node = ET.SubElement(root, "url")
                    ET.SubElement(url_node, "loc").text = f"https://arc-codex.com/library/{row['gutenberg_id']}"
                    ET.SubElement(url_node, "lastmod").text = _lastmod(row['fetched_at'])
                    ET.SubElement(url_node, "priority").text = "0.4"
                    lib_count += 1

            tree = ET.ElementTree(root)
            with open(output_path, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(f, encoding='utf-8', xml_declaration=False)

            print(colored(f"[✓] Success: {count} articles + {wiki_count} wiki + {lib_count} library URLs synced to {output_path}", "green"))
        except Exception as e:
            print(colored(f"[!] Sitemap generation failed: {e}", "red"))

def generate_rss(r):
        """Enriched RSS Generator for Arc Codex Elite."""
        import xml.etree.ElementTree as ET
        from datetime import datetime
        from email.utils import formatdate
        print(colored("\n[!] Broadcasting Elite RSS feed...", "magenta"))

        output_path = "/home/www/arc_stack/frontend/public/rss.xml"

        # RSS 2.0 spec: dates are RFC 822. Handles ISO 8601 (arc) + epoch-ms.
        def _to_rfc822(ts):
            try:
                if ts.isdigit():
                    return formatdate(int(ts) / 1000, usegmt=True)
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return formatdate(dt.timestamp(), usegmt=True)
            except Exception:
                return None

        try:
            rss = ET.Element("rss", version="2.0")
            rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
            channel = ET.SubElement(rss, "channel")
            ET.SubElement(channel, "title").text = "Arc Codex | Intelligence Discovery"
            ET.SubElement(channel, "link").text = "https://arc-codex.com"
            ET.SubElement(channel, "description").text = "AI for the Independent Mind"
            atom_self = ET.SubElement(channel, "atom:link")
            atom_self.set("href", "https://arc-codex.com/rss.xml")
            atom_self.set("rel", "self")
            atom_self.set("type", "application/rss+xml")
            ET.SubElement(channel, "lastBuildDate").text = formatdate(usegmt=True)

            feed_ids = r.zrevrange('feed', 0, -1)
            articles = []
            for aid in feed_ids:
                aid_str = aid.decode('utf-8') if isinstance(aid, bytes) else aid
                data = r.hgetall(f"article:{aid_str}")
                vis_raw = data.get(b'visibility') or data.get('visibility')
                vis = vis_raw.decode('utf-8') if isinstance(vis_raw, bytes) else vis_raw
                if vis == 'private':
                    continue
                articles.append((aid_str, data))
                if len(articles) >= 100:
                    break

            for aid_str, data in articles:
                item = ET.SubElement(channel, "item")
                title_raw = data.get(b'title') or data.get('title', 'Untitled Intel')
                title = title_raw.decode('utf-8') if isinstance(title_raw, bytes) else title_raw
                slug_raw = data.get(b'slug') or data.get('slug', aid_str)
                slug = slug_raw.decode('utf-8') if isinstance(slug_raw, bytes) else slug_raw
                source_raw = data.get(b'source_name') or data.get('source_name', '')
                source = source_raw.decode('utf-8') if isinstance(source_raw, bytes) else source_raw
                ts_raw = data.get(b'timestamp') or data.get('timestamp', '')
                ts = ts_raw.decode('utf-8') if isinstance(ts_raw, bytes) else ts_raw

                link = f"https://arc-codex.com/article/{slug}"
                ET.SubElement(item, "title").text = title
                ET.SubElement(item, "link").text = link
                ET.SubElement(item, "description").text = f"Source: {source}" if source else title
                guid = ET.SubElement(item, "guid")
                guid.set("isPermaLink", "true")
                guid.text = link
                pubdate = _to_rfc822(ts)
                if pubdate:
                    ET.SubElement(item, "pubDate").text = pubdate

            tree = ET.ElementTree(rss)
            with open(output_path, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(f, encoding='utf-8', xml_declaration=False)

            print(colored(f"[✓] Elite Feed live: {len(articles)} items → {output_path}", "green"))
        except Exception as e:
            print(colored(f"[!] Elite RSS failed: {e}", "red"))

def generate_news_sitemap(r):
        """Generates a high-velocity Google News sitemap for the last 48 hours."""
        import xml.etree.ElementTree as ET
        from datetime import datetime, timedelta
        print(colored("\n[!] Filtering for fresh intelligence (Last 48h)...", "yellow"))

        output_path = "/home/www/arc_stack/frontend/public/news-sitemap.xml"
        cutoff = datetime.now() - timedelta(hours=48)

        try:
            feed_ids = r.zrevrange('feed', 0, -1)
            root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
            root.set("xmlns:news", "http://www.google.com/schemas/sitemap-news/0.9")

            count = 0
            for aid in feed_ids:
                aid_str = aid.decode('utf-8') if isinstance(aid, bytes) else aid
                article = r.hgetall(f"article:{aid_str}")

                vis_raw = article.get(b'visibility') or article.get('visibility')
                vis = vis_raw.decode('utf-8') if isinstance(vis_raw, bytes) else vis_raw
                if vis == 'private':
                    continue

                # News sitemap is for 48h news velocity — reference articles
                # (permanent profiles) belong in the standard sitemap instead.
                ct_raw = article.get(b'content_type') or article.get('content_type')
                ct = ct_raw.decode('utf-8') if isinstance(ct_raw, bytes) else ct_raw
                if ct == 'reference':
                    continue

                ts_raw = article.get(b'timestamp') or article.get('timestamp')

                if ts_raw:
                    ts_str = ts_raw.decode('utf-8') if isinstance(ts_raw, bytes) else ts_raw
                    try:
                        # Parse with timezone awareness
                        article_date = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if article_date.replace(tzinfo=None) < cutoff:
                            continue
                    except Exception:
                        continue

                    slug_raw = article.get(b'slug') or article.get('slug')
                    title_raw = article.get(b'title') or article.get('title', 'Untitled Intel')

                    if slug_raw:
                        slug = slug_raw.decode('utf-8') if isinstance(slug_raw, bytes) else slug_raw
                    else:
                        slug = aid_str
                    title = title_raw.decode('utf-8') if isinstance(title_raw, bytes) else title_raw

                    url_node = ET.SubElement(root, "url")
                    ET.SubElement(url_node, "loc").text = f"https://arc-codex.com/article/{slug}"

                    news_node = ET.SubElement(url_node, "news:news")
                    pub_node = ET.SubElement(news_node, "news:publication")
                    ET.SubElement(pub_node, "news:name").text = "Arc Codex"
                    ET.SubElement(pub_node, "news:language").text = "en"

                    ET.SubElement(news_node, "news:publication_date").text = ts_str
                    ET.SubElement(news_node, "news:title").text = title
                    count += 1

            tree = ET.ElementTree(root)
            with open(output_path, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                tree.write(f, encoding='utf-8', xml_declaration=False)

            print(colored(f"[✓] News Wire live: {count} recent stories at {output_path}", "green"))
        except Exception as e:
            print(colored(f"[!] News Sitemap failed: {e}", "red"))

    # ==============================================================================
    # Main
    # ==============================================================================

def main():
        print(colored(BANNER, "cyan"))
        r    = connect_redis()
        solr = connect_solr()

        while True:
            get_db_status(r, solr)
            print("\n  [1]  Research / Search")
            print("  [2]  Emergency Removal")
            print("  [3]  Trim Database")
            print("  [4]  Inspect Article")
            print("  [5]  Re-index Solr")
            print("  [6]  Solr Diagnostics")
            print("  [7]  Purge Solr Orphans")
            print("  [8]  Purge Redis Orphans")
            print("  [9]  Intelligence Dashboard")
            print("  [10] A.R.C. Pattern Scanner")
            print("  [11] My Publications")
            print("  [12] Generate Sitemap")
            print("  [13] Generate RSS Feed")
            print("  [14] Generate News Sitemap")
            print("  [q]  Quit\n")

            choice = input("Select: ").strip().lower()

            if   choice == '1':  research_articles(r, solr)
            elif choice == '2':  emergency_removal_menu(r, solr)
            elif choice == '3':  trim_database(r, solr)
            elif choice == '4':  inspect_article(r, solr)
            elif choice == '5':  reindex_solr(r, solr)
            elif choice == '6':  solr_diagnostics(solr)
            elif choice == '7':  purge_solr_orphans(r, solr)
            elif choice == '8':  purge_redis_orphans(r, solr)
            elif choice == '9':  intelligence_dashboard(r, solr)
            elif choice == '10': arc_pattern_scanner(r, solr)
            elif choice == '11': my_publications(r, solr)
            elif choice == '12': generate_sitemap(r)
            elif choice == '13': generate_rss(r)
            elif choice == '14': generate_news_sitemap(r)
            elif choice in ('', 'q', 'quit', 'exit'):
                print("Goodbye.")
                break
            else:
                print(colored("Invalid selection.", "red"))

if __name__ == "__main__":
        main()

