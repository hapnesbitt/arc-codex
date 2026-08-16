#!/usr/bin/env python3
"""
Arc Codex — mailer.py
Alert and digest daemon for Arc Codex stack monitoring.

Responsibilities:
  1. Log-pattern alerts — scans stack logs for regexes in ALERT_PATTERNS,
     level-triggered dedup via should_alert() (ALERT_COOLDOWN)
  2. Condition alerts — edge-triggered fires with matched all-clears:
       check_scribe_liveness  — <site>:scribe:last_cycle age > 3× cycle_minutes
       check_publish_volume   — <site>:last_publish age > stall_threshold_hours
     Both use should_fire()/should_clear() and include a diagnosis snapshot.
  3. Daily digest — 7am summary of top 10 articles by objectivity

Every alert / all-clear email carries a diagnosis body from build_diagnosis()
so recovery notices show the same snapshot the mailer used to decide.

Mail is sent via local Postfix (already configured with DKIM/SPF/DMARC).

Configuration is hardcoded here — same pattern as scribe.py.
Future: arc_admin.py or admin UI will expose these settings.

Start via: ./arc.sh start mailer
"""

import os
import re
import json
import time
import logging
import smtplib
import subprocess
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import redis
import yaml
from dotenv import load_dotenv

from site_config import load_site_config

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_mailer_cfg() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'arc_config.yaml')
    try:
        with open(path) as f:
            return (yaml.safe_load(f) or {}).get('mailer', {}) or {}
    except Exception:
        return {}

_CFG  = _load_mailer_cfg()
SITE  = load_site_config()

ALERT_FROM    = "ross@arc-codex.com"
ALERT_TO      = "rossnesbitt@gmail.com"
DIGEST_HOUR   = 7       # 7am local time
CHECK_INTERVAL = 60     # seconds between alert checks

# All of these have yaml overrides in <stack>_config.yaml [mailer].
ALERT_COOLDOWN         = int(_CFG.get('alert_cooldown_seconds', 14400))   # anti-flap window on edge-triggered alerts (4h)
LOG_LOOKBACK_MINUTES   = int(_CFG.get('log_lookback_minutes', 2))         # was hardcoded 2 in get_recent_log_lines
LOG_TAIL_BYTES         = int(_CFG.get('log_tail_bytes', 131072))          # 128 KiB — bytes-anchored beats line-anchored on multi-MB logs
LOG_READ_TIMEOUT_S     = int(_CFG.get('log_read_timeout_seconds', 10))    # was hardcoded 5; 5.7MB watchdog.log timed out 106× Aug 11-14
STALL_THRESHOLD_HOURS  = float(_CFG.get('stall_threshold_hours', 2))      # was hardcoded 2 in check_pipeline_stall
LIVENESS_MULTIPLIER    = int(_CFG.get('scribe_liveness_multiplier', 3))   # "3x cycle_minutes with no sweep" → liveness alert

# cycle_minutes is operator-owned in <site>.cfg [ingestion]; site_config.py
# reads it fresh on module import so a mailer restart is required to pick up
# changes — which is already the arc.sh workflow.
CYCLE_MINUTES               = int(SITE.get('ingestion', 'cycle_minutes', 30))
SCRIBE_LIVENESS_THRESHOLD_S = LIVENESS_MULTIPLIER * CYCLE_MINUTES * 60

# Site-scoped Redis keys — same shape on both stacks via SITE.redis_key().
LAST_PUBLISH_KEY   = SITE.redis_key("last_publish")
LAST_CYCLE_KEY     = SITE.redis_key("scribe:last_cycle")
PRIORITY_QUEUE_KEY = SITE.redis_key("priority_uploads")
ANALYZER_QUEUE_KEY = "analyzer:queue"
# Counters hash from operational_state.py — hardcoded there as "arc:ops:scribe:counters"
# on BOTH stacks (byte-identical file); may be absent on stacks whose scribe.py
# doesn't call operational_state (e.g. Hunt scribe uses its own refresh_heartbeat).
SCRIBE_COUNTERS_KEY = "arc:ops:scribe:counters"

LOG_FILES = {
    "scribe":    "/home/www/arc_stack/logs/scribe.log",
    "analyzer":  "/home/www/arc_stack/logs/analyzer.log",
    "gunicorn":  "/home/www/arc_stack/logs/gunicorn_error.log",
    "watchdog":  "/home/www/arc_stack/logs/watchdog.log",
    "frontend":  "/home/www/arc_stack/logs/frontend.log",
}

# Patterns that trigger alerts — (regex, alert_key, friendly description)
ALERT_PATTERNS = [
    (r"manual intervention needed",   "watchdog_manual",      "Watchdog: manual intervention needed"),
    (r"Too many open files",           "fd_exhaustion",        "File descriptor exhaustion"),
    (r"MAIN LOOP ERROR",               "scribe_loop_error",    "Scribe main loop crashed"),
    # Cluster escalation only — individual "All Ollama models failed" lines
    # are transient and get downgraded to WARNING in the analyzer log. The
    # analyzer emits this specific line after N consecutive total-failures
    # (see analyzer.py _record_analysis_failure).
    (r"CLUSTER FAILURE:.*consecutive analysis-total-failures", "ollama_cluster_failure", "Analysis pipeline cluster failure"),
    (r"Redis connection failed",       "redis_conn_failed",    "Redis connection failed"),
    (r"OSError.*sources\.json",        "sources_json_error",   "sources.json OS error"),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [MAILER] - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/home/www/arc_stack/logs/mailer.log")],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

def get_redis():
    return redis.Redis.from_url(
        os.environ['REDIS_URL'],
        decode_responses=True,
    )

# ---------------------------------------------------------------------------
# Mail sending
# ---------------------------------------------------------------------------

def send_email(subject: str, body_text: str, body_html: str = None) -> bool:
    """Send via local Postfix. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative") if body_html else MIMEText(body_text)
        msg["From"]    = ALERT_FROM
        msg["To"]      = ALERT_TO
        msg["Subject"] = subject

        if body_html:
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("localhost", 25, timeout=10) as smtp:
            smtp.sendmail(ALERT_FROM, [ALERT_TO], msg.as_string())

        logger.info("✅ Email sent: %s", subject)
        return True
    except Exception as e:
        logger.warning("❌ Failed to send email '%s': %s", subject, e)
        return False

# ---------------------------------------------------------------------------
# Alert deduplication
# ---------------------------------------------------------------------------

def should_alert(r: redis.Redis, alert_key: str) -> bool:
    """Level-triggered dedup for LOG-PATTERN alerts (a matching line either
    appears in a scan window or it doesn't — there is no "cleared" transition
    to detect, so edge semantics don't apply). Returns True at most once per
    ALERT_COOLDOWN per key."""
    redis_key = f"mailer:alerted:{alert_key}"
    if r.exists(redis_key):
        return False
    r.setex(redis_key, ALERT_COOLDOWN, "1")
    return True


def should_fire(r: redis.Redis, alert_key: str) -> bool:
    """Edge-triggered fire for CONDITION alerts (stall, liveness).

    Returns True only on the transition from clear-to-alerted. While the
    active flag is set, repeat calls return False no matter how long the
    condition persists — this is what stops the "every 4h forever" re-alert
    pattern we saw on 2026-07-25 (8 emails over 22h for one stall event).

    The active flag has NO TTL — it is cleared explicitly by should_clear().
    That makes recovery detection possible; without it, "alert active" was
    just the same fact as "cooldown key present."

    ALERT_COOLDOWN is retained as an anti-flap guard on the transition
    itself, so a condition that oscillates faster than the cooldown does not
    generate a stream of fire/clear pairs.
    """
    active_key   = f"mailer:alert_active:{alert_key}"
    cooldown_key = f"mailer:alerted:{alert_key}"
    if r.exists(active_key) or r.exists(cooldown_key):
        return False
    r.set(active_key, "1")
    r.setex(cooldown_key, ALERT_COOLDOWN, "1")
    return True


def should_clear(r: redis.Redis, alert_key: str) -> bool:
    """Return True on the transition from alerted back to clear.
    Deletes the active flag so the next fire can be emitted after any
    subsequent breach (subject to anti-flap cooldown)."""
    active_key = f"mailer:alert_active:{alert_key}"
    if not r.exists(active_key):
        return False
    r.delete(active_key)
    return True

# ---------------------------------------------------------------------------
# Log monitoring
# ---------------------------------------------------------------------------

def get_recent_log_lines(filepath: str, minutes: int | None = None,
                         service: str | None = None,
                         r: redis.Redis | None = None) -> list[str]:
    """Return log lines from the last N minutes.

    Bytes-anchored tail: `tail -c LOG_TAIL_BYTES` completes in constant
    time regardless of file size. Line-anchored (`-n 200`) scanned backwards
    until it found 200 newlines, which on the 5.7MB watchdog.log timed out
    106 times across 2026-08-11..14 — those windows were silent to alerting.
    The first (possibly partial) line is discarded when its timestamp
    doesn't parse; the existing timestamp regex already handled that shape.

    On timeout / read error, the caller still gets [] (so the scan loop
    doesn't crash), but we now increment mailer:log_read_failures:<service>
    so the diagnosis email body can surface silent scanner failures.
    """
    if minutes is None:
        minutes = LOG_LOOKBACK_MINUTES
    if not os.path.exists(filepath):
        return []
    try:
        result = subprocess.run(
            ["tail", "-c", str(LOG_TAIL_BYTES), filepath],
            capture_output=True, text=True, timeout=LOG_READ_TIMEOUT_S,
        )
        lines = result.stdout.splitlines()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = []
        for line in lines:
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if match:
                try:
                    ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        recent.append(line)
                except ValueError:
                    pass
            else:
                recent.append(line)  # include lines without timestamps
        return recent
    except subprocess.TimeoutExpired:
        logger.warning("Log read timed out: %s (tail -c %d, timeout %ds)",
                       filepath, LOG_TAIL_BYTES, LOG_READ_TIMEOUT_S)
        if r is not None and service:
            try:
                r.incr(f"mailer:log_read_failures:{service}")
            except Exception:
                pass
        return []
    except Exception as e:
        logger.warning("Failed to read log %s: %s", filepath, e)
        if r is not None and service:
            try:
                r.incr(f"mailer:log_read_failures:{service}")
            except Exception:
                pass
        return []


def check_logs(r: redis.Redis):
    """Scan recent log lines for alert patterns."""
    for service, logfile in LOG_FILES.items():
        lines = get_recent_log_lines(logfile, service=service, r=r)
        for line in lines:
            for pattern, alert_key, description in ALERT_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    full_key = f"{service}_{alert_key}"
                    if should_alert(r, full_key):
                        logger.warning("🚨 Alert triggered: %s in %s", description, service)
                        send_alert_email(r, service, description, line)
                    break  # one alert per line


def send_alert_email(r: redis.Redis, service: str, description: str, log_line: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"⚠️ {SITE.name} Alert — {description}"
    diagnosis = build_diagnosis(r)

    text = f"""{SITE.name} Stack Alert
{'=' * 50}
Time:        {now}
Service:     {service}
Issue:       {description}

Log line:
{log_line}

{diagnosis}

{'=' * 50}
{SITE.name} — {SITE.domain}
"""

    html = f"""<html><body style="font-family:monospace;background:#0f172a;color:#e2e8f0;padding:24px;">
<h2 style="color:#f59e0b;">⚠️ {SITE.name} Alert</h2>
<table style="border-collapse:collapse;width:100%;">
  <tr><td style="color:#94a3b8;padding:4px 12px 4px 0">Time</td><td>{now}</td></tr>
  <tr><td style="color:#94a3b8;padding:4px 12px 4px 0">Service</td><td style="color:#f59e0b;">{service}</td></tr>
  <tr><td style="color:#94a3b8;padding:4px 12px 4px 0">Issue</td><td style="color:#fca5a5;">{description}</td></tr>
</table>
<pre style="background:#1e293b;border:1px solid #334155;border-radius:6px;padding:12px;margin-top:16px;color:#94a3b8;font-size:12px;overflow-x:auto;">{log_line}</pre>
<pre style="background:#0b1220;border:1px solid #334155;border-radius:6px;padding:12px;margin-top:12px;color:#94a3b8;font-size:11px;overflow-x:auto;">{diagnosis}</pre>
<hr style="border-color:#334155;margin-top:24px;">
<p style="color:#475569;font-size:12px;">{SITE.name} — <a href="{SITE.base_url}" style="color:#f59e0b;">{SITE.domain}</a></p>
</body></html>"""

    send_email(subject, text, html)

# ---------------------------------------------------------------------------
# Diagnosis body — shared by all alert/recovery emails
# ---------------------------------------------------------------------------

def _fmt_age(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:  return f"{seconds}s"
    if seconds < 3600: return f"{seconds // 60}m{seconds % 60}s"
    hours = seconds / 3600
    return f"{hours:.1f}h"


def _read_epoch_age(r: redis.Redis, key: str, now: float) -> tuple[str, float | None]:
    """Return (raw_value_str, age_seconds_or_None) for a Redis key that
    stores a Unix epoch seconds integer (as scribe.last_cycle does)."""
    v = r.get(key)
    if v is None:
        return "(missing)", None
    try:
        return v, now - int(v)
    except (TypeError, ValueError):
        return f"{v!r}", None


def _read_iso_age(r: redis.Redis, key: str, now_dt: datetime) -> tuple[str, float | None]:
    """Same shape as _read_epoch_age, for an ISO-8601 timestamp string."""
    v = r.get(key)
    if v is None:
        return "(missing)", None
    try:
        ts = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v, (now_dt - ts).total_seconds()
    except (TypeError, ValueError):
        return f"{v!r}", None


def build_diagnosis(r: redis.Redis) -> str:
    """KV block appended to every alert / all-clear email so the operator
    has the same snapshot the mailer used when it decided to fire.

    Cumulative scribe counters are shown as-is (they're since-forever, not
    per-window) — the operator can eyeball the errors_* vs poll_success
    ratio. Snapshot-based deltas are a follow-up."""
    now_s  = time.time()
    now_dt = datetime.now(timezone.utc)
    lines = [f"--- diagnosis ({SITE.name}, checked {now_dt.isoformat()}) ---"]

    v, age = _read_iso_age(r, LAST_PUBLISH_KEY, now_dt)
    lines.append(f"  {LAST_PUBLISH_KEY:32s} = {v}"
                 + (f"   (age: {_fmt_age(age)})" if age is not None else ""))
    v, age = _read_epoch_age(r, LAST_CYCLE_KEY, now_s)
    lines.append(f"  {LAST_CYCLE_KEY:32s} = {v}"
                 + (f"   (age: {_fmt_age(age)})" if age is not None else ""))
    lines.append(f"  liveness threshold               = {SCRIBE_LIVENESS_THRESHOLD_S}s "
                 f"({LIVENESS_MULTIPLIER}x cycle_minutes={CYCLE_MINUTES})")
    lines.append(f"  publish stall threshold          = {STALL_THRESHOLD_HOURS:.1f}h")

    for label, key in [("analyzer:queue LLEN", ANALYZER_QUEUE_KEY),
                       (f"{PRIORITY_QUEUE_KEY} LLEN", PRIORITY_QUEUE_KEY)]:
        try:
            lines.append(f"  {label:32s} = {r.llen(key)}")
        except Exception as e:
            lines.append(f"  {label:32s} = (error: {e})")

    try:
        counters = r.hgetall(SCRIBE_COUNTERS_KEY) or {}
    except Exception as e:
        counters = {}
        lines.append(f"  {SCRIBE_COUNTERS_KEY} read error: {e}")
    if counters:
        lines.append(f"  {SCRIBE_COUNTERS_KEY} (cumulative since start):")
        for k in sorted(counters):
            lines.append(f"    {k:30s} = {counters[k]}")
    else:
        lines.append(f"  {SCRIBE_COUNTERS_KEY:32s} = (empty — operational_state.py counters not being written on this stack)")

    try:
        failures = {}
        for key in r.scan_iter(match="mailer:log_read_failures:*", count=100):
            failures[key.split(":")[-1]] = r.get(key)
        if failures:
            lines.append("  log-read failures (since key creation): "
                         + ", ".join(f"{k}={v}" for k, v in sorted(failures.items())))
    except Exception:
        pass

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Condition alerts — edge-triggered, with all-clear
# ---------------------------------------------------------------------------

# alert_key -> (subject, body_lead) resolved fresh from Redis for the
# all-clear email. Kept centralised so the fire and recovery messages read
# as a matched pair.
_LIVENESS_KEY = "scribe_liveness"
_PUBLISH_KEY  = "publish_volume"


def _fire(r: redis.Redis, alert_key: str, subject: str, body_lead: str):
    logger.warning("🚨 %s", subject)
    send_email(subject, body_lead + "\n\n" + build_diagnosis(r))


def _clear(r: redis.Redis, alert_key: str, subject: str, body_lead: str):
    logger.info("✅ Recovery: %s", subject)
    send_email(subject, body_lead + "\n\n" + build_diagnosis(r))


def check_scribe_liveness(r: redis.Redis):
    """Fire once when the scribe hasn't completed a sweep in
    LIVENESS_MULTIPLIER × cycle_minutes; all-clear once when it does.

    Reads <site>:scribe:last_cycle written by scribe.py (~ SETEX with TTL
    900s). Absent key means no sweep in 15 minutes AND no boot marker —
    that's a stronger signal than a stale timestamp, so we treat it as
    the same alert condition.
    """
    try:
        raw = r.get(LAST_CYCLE_KEY)
        now = time.time()
        if raw is None:
            age = None
            in_breach = True
        else:
            try:
                age = now - int(raw)
            except (TypeError, ValueError):
                logger.warning("Scribe liveness: %s value %r is not an integer — skipping",
                               LAST_CYCLE_KEY, raw)
                return
            in_breach = age > SCRIBE_LIVENESS_THRESHOLD_S

        threshold_str = (f"threshold: {_fmt_age(SCRIBE_LIVENESS_THRESHOLD_S)} "
                         f"= {LIVENESS_MULTIPLIER}× cycle_minutes ({CYCLE_MINUTES}m)")
        if in_breach:
            reason = (f"{LAST_CYCLE_KEY} is missing" if age is None
                      else f"No successful scribe sweep for {_fmt_age(age)}")
            if should_fire(r, _LIVENESS_KEY):
                _fire(r, _LIVENESS_KEY,
                      f"⚠️ {SITE.name} — Scribe liveness lost",
                      f"{reason}. {threshold_str}.")
        else:
            if should_clear(r, _LIVENESS_KEY):
                _clear(r, _LIVENESS_KEY,
                       f"✅ {SITE.name} — Scribe liveness restored",
                       f"Scribe last swept {_fmt_age(age)} ago. {threshold_str}.")
    except Exception as e:
        logger.warning("Scribe liveness check failed: %s", e)


def check_publish_volume(r: redis.Redis):
    """Slower, separate signal: no new article for STALL_THRESHOLD_HOURS.
    Publish volume depends on scribe alive AND analyzer keeping up AND
    sources returning content — a liveness alert may already have fired
    (in which case this one adds no signal until it clears).

    TODO: weekday/weekend-aware thresholds. Deferred from this batch.
    """
    try:
        raw = r.get(LAST_PUBLISH_KEY)
        if raw is None:
            # Fall back to feed head, mirroring the pre-existing shape.
            head = r.zrevrange("feed", 0, 0)
            if not head:
                # Nothing to compare against — silence rather than false-clear.
                return
            data = r.hgetall(f"article:{head[0]}")
            raw = data.get("timestamp", "")
            if not raw:
                return
        try:
            newest = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Publish-volume check: last_publish %r is not ISO — skipping", raw)
            return
        age_hours = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
        in_breach = age_hours > STALL_THRESHOLD_HOURS
        threshold_str = f"threshold: {STALL_THRESHOLD_HOURS:.1f}h"
        if in_breach:
            if should_fire(r, _PUBLISH_KEY):
                _fire(r, _PUBLISH_KEY,
                      f"⚠️ {SITE.name} — Publish volume stalled ({age_hours:.1f}h)",
                      f"No new article published in {age_hours:.1f}h ({threshold_str}). "
                      f"Last: {raw}.")
        else:
            if should_clear(r, _PUBLISH_KEY):
                _clear(r, _PUBLISH_KEY,
                       f"✅ {SITE.name} — Publish volume recovered",
                       f"Latest article is {age_hours:.1f}h old ({threshold_str}). "
                       f"Latest: {raw}.")
    except Exception as e:
        logger.warning("Publish-volume check failed: %s", e)

# ---------------------------------------------------------------------------
# Daily digest
# ---------------------------------------------------------------------------

def should_send_digest(r: redis.Redis) -> bool:
    """Return True once per day at DIGEST_HOUR."""
    now = datetime.now()
    if now.hour != DIGEST_HOUR:
        return False
    date_key = f"mailer:digest:{now.strftime('%Y-%m-%d')}"
    if r.exists(date_key):
        return False
    r.setex(date_key, 90000, "1")  # 25h TTL — covers DST edge cases
    return True


def get_top_articles(r: redis.Redis, n: int = 10) -> list[dict]:
    """Fetch top N articles by objectivity (0-1) from the last 24h."""
    try:
        article_ids = r.zrevrange("feed", 0, 199)  # scan last 200
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles = []
        for aid in article_ids:
            data = r.hgetall(f"article:{aid}")
            if not data or not data.get("title"):
                continue
            ts_str = data.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass
            try:
                # Rank by objectivity, on a 0-1 scale so the int(score*100)
                # formatter below yields a real percentage.
                #
                # Why not chimera_score, the way Hunt does? Because
                # chimera_score means different things on the two stacks:
                # on Arc it is a 0-100 readability composite (compute_chimera
                # in main.py — FK/Coleman-Liau/SMOG/Dale-Chall averaged),
                # on Hunt it is a 0-1 objectivity ratio. Reading it here
                # gave last week's Arc digest "8000% tone" values and
                # ranked short/simple text (title fragments, WHO press
                # releases, untranslated headlines) to the top. Mirrors
                # the note in corpus_exporter.py that also refuses to read
                # chimera_score across the fork for the same reason.
                import json as _json
                dossier_raw = data.get("dossier", "{}")
                dossier = _json.loads(dossier_raw) if dossier_raw else {}
                obj = dossier.get("objectivity_score")
                if obj is None and dossier.get("subjectivity") is not None:
                    obj = (1.0 - float(dossier["subjectivity"])) * 100.0
                score = float(obj) / 100.0 if obj is not None else 0.0
            except (ValueError, Exception):
                score = 0
            articles.append({
                "id":       aid,
                "title":    data.get("title", "Untitled"),
                "source":   data.get("source", ""),
                "score":    score,
                "timestamp": ts_str,
            })

        articles.sort(key=lambda x: x["score"], reverse=True)
        return articles[:n]
    except Exception as e:
        logger.error("Failed to get top articles: %s", e)
        return []


def send_digest(r: redis.Redis):
    articles = get_top_articles(r, 10)
    if not articles:
        logger.info("No articles for digest — skipping")
        return

    date_str = datetime.now().strftime("%B %d, %Y")
    subject = f"Arc Codex Daily Digest — {date_str}"

    # Plain text
    lines = [f"Arc Codex Daily Digest — {date_str}", "=" * 50, ""]
    for i, a in enumerate(articles, 1):
        score_pct = int(a["score"] * 100)
        lines.append(f"{i:2}. [{score_pct:3d}% obj] {a['title']}")
        lines.append(f"     {a['source']}  —  https://arc-codex.com/article/{a['id']}")
        lines.append("")
    lines += ["=" * 50, "Arc Codex — arc-codex.com", "Unsubscribe: reply with 'unsubscribe'"]
    text = "\n".join(lines)

    # HTML
    rows = ""
    for i, a in enumerate(articles, 1):
        score_pct = int(a["score"] * 100)
        if score_pct >= 70:
            score_color = "#fca5a5"
        elif score_pct >= 40:
            score_color = "#fcd34d"
        else:
            score_color = "#6ee7b7"
        rows += f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #1e293b;color:#64748b;font-size:13px;">{i}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #1e293b;">
            <a href="https://arc-codex.com/article/{a['id']}"
               style="color:#e2e8f0;text-decoration:none;font-weight:500;">{a['title']}</a>
            <div style="color:#64748b;font-size:12px;margin-top:4px;">{a['source']}</div>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #1e293b;text-align:center;">
            <span style="color:{score_color};font-weight:bold;font-size:13px;">{score_pct}%</span>
            <div style="color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:1px;">objectivity</div>
          </td>
        </tr>"""

    html = f"""<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:0;margin:0;">
<div style="max-width:600px;margin:0 auto;padding:32px 16px;">
  <div style="margin-bottom:24px;">
    <h1 style="color:#f59e0b;font-size:20px;margin:0;">Arc Codex</h1>
    <p style="color:#64748b;margin:4px 0 0;font-size:14px;">Daily Intelligence Digest — {date_str}</p>
  </div>
  <table style="width:100%;border-collapse:collapse;background:#1e293b;border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#0f172a;">
        <th style="padding:10px 8px;text-align:left;color:#475569;font-size:11px;text-transform:uppercase;letter-spacing:1px;">#</th>
        <th style="padding:10px 8px;text-align:left;color:#475569;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Article</th>
        <th style="padding:10px 8px;text-align:center;color:#475569;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Objectivity</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <hr style="border-color:#1e293b;margin:24px 0;">
  <p style="color:#334155;font-size:12px;text-align:center;">
    <a href="https://arc-codex.com" style="color:#f59e0b;">arc-codex.com</a> · 
    Reply with "unsubscribe" to stop receiving digests
  </p>
</div>
</body></html>"""

    send_email(subject, text, html)
    logger.info("✅ Daily digest sent (%d articles)", len(articles))

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    logger.info("🚀 Arc Codex Mailer starting... (ALERT_COOLDOWN=%ds)", ALERT_COOLDOWN)
    r = get_redis()

    # No startup email — boot notices were noise (watchdog restarts, reboots).
    # The log line above is the record that the daemon came up.

    while True:
        try:
            check_logs(r)
            check_scribe_liveness(r)
            check_publish_volume(r)
            if should_send_digest(r):
                send_digest(r)
        except Exception as e:
            logger.error("Main loop error: %s", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
