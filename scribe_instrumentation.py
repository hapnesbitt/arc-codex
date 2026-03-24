# =============================================================================
# SCRIBE INSTRUMENTATION PATCH — v52.1
#
# These are targeted additions to scribe.py. Nothing is removed or restructured.
# Apply each section at the indicated insertion point.
#
# Summary of additions:
#   1. Redis counter keys (constants) — add near top with other constants
#   2. _inc() helper — tiny Redis HINCRBY wrapper, add after constants
#   3. _record_source_health() — writes per-domain fetch outcome to Redis
#   4. Updated fetch_article_data() — calls _record_source_health()
#   5. Updated main loop — instruments bozo feeds, quality gate rejections
#   6. Updated pre_analyze API call in scribe — passes article_id
#
# All Redis counters live under arc:stats:* keys.
# corpus_exporter.py reads these and exposes them as Prometheus metrics.
# Counters are HINCRBY — monotonically increasing, reset only on explicit flush.
# =============================================================================


# =============================================================================
# SECTION 1: Add these constants near the top of scribe.py
# (after the existing REDIS_PRIORITY_QUEUE_KEY line)
# =============================================================================

# --- Instrumentation Redis keys ---
# All pipeline telemetry lives under arc:stats:* hashes.
# corpus_exporter reads these; nothing else writes them.
STATS_FETCH          = "arc:stats:fetch"          # hash: {domain: tier1_ok|tier2_ok|failed count}
STATS_QUALITY        = "arc:stats:quality"         # hash: {reason: count} — quality gate rejections
STATS_RSS            = "arc:stats:rss"             # hash: bozo, ok, empty
STATS_PUBLISH        = "arc:stats:publish"         # hash: ok, failed, duplicate
STATS_PRIORITY       = "arc:stats:priority"        # hash: {origin: count}
STATS_SOURCE_LATENCY = "arc:stats:source_latency"  # hash: {domain: cumulative_ms} for avg latency


# =============================================================================
# SECTION 2: Add this helper after the constants block
# =============================================================================

def _inc(key: str, field: str, amount: int = 1) -> None:
    """
    Increment a Redis hash counter. Fire-and-forget — never raises.
    Used throughout scribe for pipeline telemetry.
    """
    try:
        r.hincrby(key, field, amount)
    except Exception:
        pass  # telemetry must never break the pipeline


# =============================================================================
# SECTION 3: Add this new function before fetch_article_data()
# =============================================================================

def _record_source_health(url: str, tier: str, elapsed_ms: float) -> None:
    """
    Record fetch outcome for a source URL into Redis.

    tier values:
        'tier1_ok'   — simple requests succeeded
        'tier2_ok'   — stealth requests succeeded
        'youtube_ok' — yt-dlp metadata succeeded
        'failed'     — all tiers failed

    Counters written:
        arc:stats:fetch          hash  {domain}:{tier}  HINCRBY 1
        arc:stats:source_latency hash  {domain}         HINCRBY elapsed_ms (for avg)
        arc:stats:fetch          hash  {domain}:calls   HINCRBY 1 (denominator for avg)
    """
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
        domain = netloc.replace('www.', '') or '(unknown)'
        _inc(STATS_FETCH, f"{domain}:{tier}")
        _inc(STATS_FETCH, f"{domain}:calls")
        if elapsed_ms > 0:
            r.hincrbyfloat(STATS_SOURCE_LATENCY, domain, round(elapsed_ms, 1))
    except Exception:
        pass


# =============================================================================
# SECTION 4: Updated fetch_with_requests() — wrap both tiers with timing
#
# Replace the existing fetch_article_data() function body with this version.
# The tier1/tier2 logic is unchanged — only timing + _record_source_health added.
# =============================================================================

def fetch_article_data(url):
    """
    Main article fetching function. Instruments fetch outcomes to Redis.

    YouTube: yt-dlp metadata extraction (no download)
    Tier 1:  Simple requests + trafilatura/BS4
    Tier 2:  Stealth requests (referer + sec-fetch headers)
    Tier 3:  Skip — no browser on this machine (radeon GPU crash risk)
    """
    import time as _time

    # YouTube fast path
    if is_youtube_url(url):
        t0 = _time.perf_counter()
        result = fetch_youtube_metadata(url)
        elapsed = (_time.perf_counter() - t0) * 1000
        _record_source_health(url, 'youtube_ok' if result else 'failed', elapsed)
        return result

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    # Tier 1: simple
    t0 = _time.perf_counter()
    result = fetch_with_requests(url, headers, stealth=False)
    elapsed = (_time.perf_counter() - t0) * 1000
    if result:
        _record_source_health(url, 'tier1_ok', elapsed)
        return result

    # Tier 2: stealth headers
    if is_problematic_news_site(url):
        logger.info(f"🛡️  Protected site detected, trying stealth headers: {url}")
    else:
        logger.info(f"🔄 Simple fetch failed, trying stealth headers: {url}")

    t0 = _time.perf_counter()
    result = fetch_with_requests(url, headers, stealth=True)
    elapsed = (_time.perf_counter() - t0) * 1000
    if result:
        _record_source_health(url, 'tier2_ok', elapsed)
        return result

    _record_source_health(url, 'failed', 0)
    logger.warning(f"❌ Both fetch tiers failed for {url} — skipping (no browser fallback)")
    return None


# =============================================================================
# SECTION 5: Main loop instrumentation
#
# In the main() while loop, inside the RSS cycle, patch these three spots:
# =============================================================================

# --- 5a: RSS feed parse — after feedparser.parse(source['url']) ---
# Replace:
#     if feed.bozo:
#         continue
# With:
#     if feed.bozo:
#         _inc(STATS_RSS, 'bozo')
#         continue
#     _inc(STATS_RSS, 'ok')

# --- 5b: Quality gate rejection — after assess_content_quality() call ---
# Replace:
#     if not is_quality:
#         logger.info(f"⛔ Skipping article: {reason}")
#         continue
# With:
#     if not is_quality:
#         logger.info(f"⛔ Skipping article: {reason}")
#         _inc(STATS_QUALITY, reason.split(' ')[0])  # normalise reason to first word
#         continue

# --- 5c: Successful candidate found ---
# After:
#     candidates.append(new_candidate)
#     logger.info(f"✅ Candidate: {metadata['title'][:60]}")
# Add:
#     _inc(STATS_RSS, 'candidates')

# --- 5d: Publish outcome — after publish_and_prepare_comments() ---
# Replace:
#     success = publish_and_prepare_comments(target, recently_published, api_client)
#     if success:
#         r.sadd('processed_hashes', target['article']['article_hash'])
# With:
#     success = publish_and_prepare_comments(target, recently_published, api_client)
#     if success:
#         r.sadd('processed_hashes', target['article']['article_hash'])
#         _inc(STATS_PUBLISH, 'ok')
#     else:
#         _inc(STATS_PUBLISH, 'failed')

# --- 5e: Priority queue publish outcome ---
# In process_priority_queue(), after:
#     success = publish_and_prepare_comments(target, recently_published, api_client)
#     if success:
#         r.sadd('processed_hashes', article_hash)
#         published += 1
#         logger.info(f"⚡ Priority item published: '{title[:60]}'")
# Add:
#     _inc(STATS_PRIORITY, origin)

# --- 5f: Duplicate skip in main loop ---
# After any r.sismember('processed_hashes', ...) that leads to a skip, add:
#     _inc(STATS_PUBLISH, 'duplicate')


# =============================================================================
# SECTION 6: Pass article_id to pre_analyze
#
# In scribe.py, APIClient.pre_analyze() currently sends:
#     return self._post('pre_analyze', {'inputText': text}, add_secret=False)
#
# Replace with:
#     def pre_analyze(self, text, article_id=''):
#         return self._post('pre_analyze', {'inputText': text, 'article_id': article_id}, add_secret=False)
#
# And in the main loop where pre_analyze is called:
# Replace:
#     executor.submit(api_client.pre_analyze, cand['article_text']): cand
# With:
#     executor.submit(api_client.pre_analyze, cand['article_text'], cand['article_hash']): cand
# =============================================================================
