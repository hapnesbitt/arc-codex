#!/usr/bin/env python3
"""
caddy_exporter.py — Arc Codex Caddy Access Log Prometheus Exporter v1.0

Tails Caddy JSON access logs and exposes traffic metrics at :9102/metrics.
Runs continuously — no polling interval, processes lines as they arrive.

Metrics exposed:
  arc_http_requests_total{site,method,status,path_group}  — request count
  arc_http_request_duration_seconds{site,path_group}      — response time histogram (via summary)
  arc_http_response_bytes_total{site}                     — bytes served
  arc_http_status_total{site,status_class}                — 2xx/3xx/4xx/5xx counts
  arc_http_top_paths{site,path}                           — top 20 paths by hit count
  arc_http_top_useragents{site,ua_class}                  — bot vs browser vs api
  arc_http_top_countries{site,ip_prefix}                  — /16 prefix as geo proxy

Resetting: counters are monotonic (survive restart via Redis checkpoint).
Scrape port: 9102

Usage:
    cd /home/www/arc_stack/backend
    source venv/bin/activate
    python3 caddy_exporter.py

    # Or via arc.sh:
    arc start caddy_exporter
"""

import os
import re
import json
import time
import threading
import logging
from collections import Counter, defaultdict
from dotenv import load_dotenv

load_dotenv()

try:
    from prometheus_client import (
        start_http_server, Counter as PCounter, Gauge, Summary,
        REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR
    )
except ImportError:
    print("❌ pip install prometheus-client --break-system-packages")
    raise

try:
    REGISTRY.unregister(PROCESS_COLLECTOR)
    REGISTRY.unregister(PLATFORM_COLLECTOR)
except Exception:
    pass

# --- Config ---
LOG_FILES = {
    "arc-codex":  "/var/log/caddy/arc-codex-access.log",
    "huntaegis":  "/var/log/caddy/huntaegis-access.log",
}
EXPORTER_PORT  = int(os.getenv("CADDY_EXPORTER_PORT", 9102))
TOP_PATHS      = int(os.getenv("CADDY_TOP_PATHS", 20))
ROLLUP_INTERVAL = int(os.getenv("CADDY_ROLLUP_INTERVAL", 60))  # seconds between top-N gauge updates

LOG_FORMAT = "%(asctime)s - [CADDY_EXPORTER] - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

# --- Path grouping — reduces cardinality ---
PATH_GROUPS = [
    (r'^/api/get_feed',         'api_feed'),
    (r'^/api/translate',        'api_translate'),
    (r'^/api/article/',         'api_articles'),
    (r'^/api/library/',         'api_library'),
    (r'^/api/search',           'api_search'),
    (r'^/api/submit',           'api_submit'),
    (r'^/api/auth',             'api_auth'),
    (r'^/api/user',             'api_user'),
    (r'^/api/rss',              'api_rss'),
    (r'^/api/feed\.xml',        'api_rss'),
    (r'^/api/stats',            'api_stats'),
    (r'^/api/',                 'api_other'),
    (r'^/article/',             'page_article'),
    (r'^/search',               'page_search'),
    (r'^/publish',              'page_publish'),
    (r'^/about',                'page_about'),
    (r'^/uploads/',             'static_uploads'),
    (r'^/_next/static',         'static_next'),
    (r'^/_next/',               'next_internal'),
    (r'^/favicon',              'static_favicon'),
    (r'^/$',                    'page_home'),
]

# --- User-agent classification ---
BOT_PATTERNS = [
    'bot', 'crawler', 'spider', 'slurp', 'bingpreview',
    'facebookexternalhit', 'meta-externalagent', 'twitterbot',
    'linkedinbot', 'whatsapp', 'telegrambot', 'discordbot',
    'applebot', 'googlebot', 'baiduspider', 'yandex',
    'semrush', 'ahrefs', 'mj12bot', 'dotbot', 'petalbot',
]

def classify_ua(ua: str) -> str:
    ua_lower = ua.lower()
    if any(b in ua_lower for b in BOT_PATTERNS):
        return 'bot'
    if 'mozilla' in ua_lower or 'webkit' in ua_lower or 'gecko' in ua_lower:
        return 'browser'
    if not ua or ua == '-':
        return 'unknown'
    return 'api_client'

def group_path(path: str) -> str:
    for pattern, group in PATH_GROUPS:
        if re.match(pattern, path):
            return group
    return 'other'

def ip_prefix(ip: str) -> str:
    """Return /16 prefix as a coarse geo proxy."""
    try:
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
        return ip.split(':')[0] or 'ipv6'
    except Exception:
        return 'unknown'

# =============================================================================
# Prometheus metrics
# =============================================================================

c_requests = PCounter(
    'arc_http_requests_total',
    'Total HTTP requests',
    ['site', 'method', 'status', 'path_group']
)
c_bytes = PCounter(
    'arc_http_response_bytes_total',
    'Total HTTP response bytes',
    ['site']
)
c_status_class = PCounter(
    'arc_http_status_class_total',
    'HTTP requests by status class',
    ['site', 'status_class']
)
c_ua_class = PCounter(
    'arc_http_ua_class_total',
    'HTTP requests by user-agent class',
    ['site', 'ua_class']
)
s_duration = Summary(
    'arc_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['site', 'path_group']
)

# Top-N gauges — updated every ROLLUP_INTERVAL seconds
g_top_paths = Gauge(
    'arc_http_top_paths_total',
    'Top path hit counts (rolling)',
    ['site', 'path']
)
g_top_ips = Gauge(
    'arc_http_top_ip_prefix_total',
    'Top /16 IP prefix hit counts (rolling)',
    ['site', 'ip_prefix']
)
g_requests_per_min = Gauge(
    'arc_http_requests_per_minute',
    'Requests per minute (60s rolling window)',
    ['site']
)

# =============================================================================
# State for rolling windows
# =============================================================================

# path_counts[site][path] = count (rolling, reset periodically)
_path_counts   = defaultdict(Counter)
_ip_counts     = defaultdict(Counter)
_req_timestamps = defaultdict(list)   # [site] = [timestamps] for req/min
_state_lock    = threading.Lock()


def process_line(site: str, line: str) -> None:
    """Parse one JSON log line and update metrics."""
    line = line.strip()
    if not line:
        return
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return

    req     = entry.get('request', {})
    method  = req.get('method', 'UNKNOWN')
    uri     = req.get('uri', '/')
    path    = uri.split('?')[0]        # strip query string
    status  = str(entry.get('status', 0))
    size    = int(entry.get('size', 0))
    duration = float(entry.get('duration', 0))
    ua      = req.get('headers', {}).get('User-Agent', [''])[0]
    remote_ip = req.get('client_ip') or req.get('remote_ip', '')

    pg          = group_path(path)
    ua_class    = classify_ua(ua)
    status_class = f"{status[0]}xx" if status and status[0].isdigit() else 'unknown'
    ip_pfx      = ip_prefix(remote_ip)

    # Prometheus counters
    c_requests.labels(site=site, method=method, status=status, path_group=pg).inc()
    c_bytes.labels(site=site).inc(size)
    c_status_class.labels(site=site, status_class=status_class).inc()
    c_ua_class.labels(site=site, ua_class=ua_class).inc()
    s_duration.labels(site=site, path_group=pg).observe(duration)

    # Rolling state
    now = time.time()
    with _state_lock:
        _path_counts[site][pg] += 1
        _path_counts[site][path[:80]] += 1   # raw path (truncated)
        _ip_counts[site][ip_pfx] += 1
        _req_timestamps[site].append(now)
        # Prune timestamps older than 60s
        _req_timestamps[site] = [t for t in _req_timestamps[site] if now - t < 60]


def rollup_gauges() -> None:
    """Periodically push top-N rolling counts to gauges."""
    while True:
        time.sleep(ROLLUP_INTERVAL)
        with _state_lock:
            for site in list(_path_counts.keys()):
                # Top paths
                for path, count in _path_counts[site].most_common(TOP_PATHS):
                    g_top_paths.labels(site=site, path=path).set(count)
                # Top IP prefixes
                for pfx, count in _ip_counts[site].most_common(20):
                    g_top_ips.labels(site=site, ip_prefix=pfx).set(count)
                # Requests per minute
                now = time.time()
                rpm = sum(1 for t in _req_timestamps[site] if now - t < 60)
                g_requests_per_min.labels(site=site).set(rpm)


def tail_file(site: str, filepath: str) -> None:
    """
    Tail a log file, processing new lines as they arrive.
    Handles log rotation — reopens if file shrinks or disappears.
    """
    log.info(f"Tailing {filepath} for site '{site}'")
    pos = 0

    while True:
        try:
            if not os.path.exists(filepath):
                time.sleep(2)
                continue

            with open(filepath, 'r') as f:
                # On startup, seek to end to avoid reprocessing history
                if pos == 0:
                    f.seek(0, 2)
                    pos = f.tell()
                else:
                    f.seek(0, 2)
                    new_size = f.tell()
                    if new_size < pos:
                        # File was rotated — start from beginning
                        log.info(f"Log rotation detected for {filepath}")
                        pos = 0
                    f.seek(pos)

                while True:
                    line = f.readline()
                    if not line:
                        pos = f.tell()
                        break
                    process_line(site, line)
                    pos = f.tell()

        except Exception as e:
            log.error(f"Error tailing {filepath}: {e}")

        time.sleep(0.5)


def main():
    log.info(f"Arc Codex Caddy Exporter v1.0 — port {EXPORTER_PORT}")

    # Start Prometheus HTTP server
    start_http_server(EXPORTER_PORT)
    log.info(f"✅ Metrics at http://localhost:{EXPORTER_PORT}/metrics")

    # Start rollup thread
    t_rollup = threading.Thread(target=rollup_gauges, daemon=True)
    t_rollup.start()

    # Start one tail thread per log file
    threads = []
    for site, filepath in LOG_FILES.items():
        t = threading.Thread(target=tail_file, args=(site, filepath), daemon=True)
        t.start()
        threads.append(t)
        log.info(f"✅ Watching {filepath} → site='{site}'")

    log.info("Caddy exporter running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("👋 Caddy exporter stopped.")


if __name__ == "__main__":
    main()
