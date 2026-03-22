#!/usr/bin/env python3
"""
Arc Codex — mailer.py
Alert and digest daemon for Arc Codex stack monitoring.

Responsibilities:
  1. Alert emails — monitors logs and Redis for error conditions,
     sends immediate notifications with deduplication (1/hour per issue)
  2. Daily digest — 7am summary of top 10 articles by chimera score

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
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALERT_FROM    = "ross@arc-codex.com"
ALERT_TO      = "rossnesbitt@gmail.com"
DIGEST_HOUR   = 7       # 7am local time
CHECK_INTERVAL = 60     # seconds between alert checks
ALERT_COOLDOWN = 14400   # seconds before re-alerting on same issue (4 hours)

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
    (r"All Ollama models failed",      "ollama_all_failed",    "All Ollama models failed"),
    (r"Redis connection failed",       "redis_conn_failed",    "Redis connection failed"),
    (r"OSError.*sources\.json",        "sources_json_error",   "sources.json OS error"),
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [MAILER] - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/home/www/arc_stack/logs/mailer.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

def get_redis():
    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://:simplenes@localhost:6379/0"),
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
        logger.error("❌ Failed to send email '%s': %s", subject, e)
        return False

# ---------------------------------------------------------------------------
# Alert deduplication
# ---------------------------------------------------------------------------

def should_alert(r: redis.Redis, alert_key: str) -> bool:
    """Return True if we haven't alerted on this key within ALERT_COOLDOWN."""
    redis_key = f"mailer:alerted:{alert_key}"
    if r.exists(redis_key):
        return False
    r.setex(redis_key, ALERT_COOLDOWN, "1")
    return True

# ---------------------------------------------------------------------------
# Log monitoring
# ---------------------------------------------------------------------------

def get_recent_log_lines(filepath: str, minutes: int = 2) -> list[str]:
    """Return log lines from the last N minutes."""
    if not os.path.exists(filepath):
        return []
    try:
        # Use tail for efficiency on large log files
        result = subprocess.run(
            ["tail", "-n", "200", filepath],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()
        cutoff = datetime.now() - timedelta(minutes=minutes)
        recent = []
        for line in lines:
            # Try to parse timestamp from log line
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
    except Exception as e:
        logger.warning("Failed to read log %s: %s", filepath, e)
        return []


def check_logs(r: redis.Redis):
    """Scan recent log lines for alert patterns."""
    for service, logfile in LOG_FILES.items():
        lines = get_recent_log_lines(logfile, minutes=2)
        for line in lines:
            for pattern, alert_key, description in ALERT_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    full_key = f"{service}_{alert_key}"
                    if should_alert(r, full_key):
                        logger.warning("🚨 Alert triggered: %s in %s", description, service)
                        send_alert_email(service, description, line)
                    break  # one alert per line


def send_alert_email(service: str, description: str, log_line: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"⚠️ Arc Codex Alert — {description}"

    text = f"""Arc Codex Stack Alert
{'=' * 50}
Time:        {now}
Service:     {service}
Issue:       {description}

Log line:
{log_line}

{'=' * 50}
Arc Codex — arc-codex.com
"""

    html = f"""<html><body style="font-family:monospace;background:#0f172a;color:#e2e8f0;padding:24px;">
<h2 style="color:#f59e0b;">⚠️ Arc Codex Alert</h2>
<table style="border-collapse:collapse;width:100%;">
  <tr><td style="color:#94a3b8;padding:4px 12px 4px 0">Time</td><td>{now}</td></tr>
  <tr><td style="color:#94a3b8;padding:4px 12px 4px 0">Service</td><td style="color:#f59e0b;">{service}</td></tr>
  <tr><td style="color:#94a3b8;padding:4px 12px 4px 0">Issue</td><td style="color:#fca5a5;">{description}</td></tr>
</table>
<pre style="background:#1e293b;border:1px solid #334155;border-radius:6px;padding:12px;margin-top:16px;color:#94a3b8;font-size:12px;overflow-x:auto;">{log_line}</pre>
<hr style="border-color:#334155;margin-top:24px;">
<p style="color:#475569;font-size:12px;">Arc Codex — <a href="https://arc-codex.com" style="color:#f59e0b;">arc-codex.com</a></p>
</body></html>"""

    send_email(subject, text, html)

# ---------------------------------------------------------------------------
# Pipeline stall detection
# ---------------------------------------------------------------------------

def check_pipeline_stall(r: redis.Redis):
    """Alert if no new articles have been published in the last 2 hours."""
    try:
        # Fast path — scribe sets this key on every publish
        newest_str = r.get('arc:last_publish')
        if not newest_str:
            # Fallback — scan all articles (catches pre-fix data)
            keys = r.keys("article:*")
            if not keys:
                return
            pipe = r.pipeline()
            for key in keys:  # check all articles
                pipe.hget(key, "timestamp")
            timestamps = [t for t in pipe.execute() if t]
            if not timestamps:
                return
            timestamps.sort(reverse=True)
            newest_str = timestamps[0]
        newest = datetime.fromisoformat(newest_str.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
        if age_hours > 2:
            if should_alert(r, "pipeline_stall"):
                logger.warning("🚨 Pipeline stall detected — no new articles in %.1fh", age_hours)
                send_email(
                    f"⚠️ Arc Codex — Pipeline Stall ({age_hours:.1f}h)",
                    f"No new articles have been published in {age_hours:.1f} hours.\n\nLast article: {newest_str}\n\nCheck scribe and analyzer logs.",
                )
    except Exception as e:
        logger.warning("Pipeline stall check failed: %s", e)

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
    """Fetch top N articles by chimera score from the last 24h."""
    try:
        article_ids = r.zrevrange("feed", 0, 199)  # scan last 200
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        articles = []
        for aid in article_ids:
            data = r.hgetall(f"article:{aid}")
            if not data:
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
                # chimera_score lives inside the dossier JSON blob
                score = float(data.get("chimera_score", 0))
                if score == 0:
                    import json as _json
                    dossier_raw = data.get("dossier", "{}")
                    dossier = _json.loads(dossier_raw) if dossier_raw else {}
                    score = float(dossier.get("chimera_score", dossier.get("sentiment", 0)))
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
        lines.append(f"{i:2}. [{score_pct:3d}% tone] {a['title']}")
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
            <div style="color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:1px;">tone</div>
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
        <th style="padding:10px 8px;text-align:center;color:#475569;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Tone</th>
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
    logger.info("🚀 Arc Codex Mailer starting...")
    r = get_redis()

    # Send startup notification
    send_email(
        "✅ Arc Codex Mailer Started",
        f"Mailer daemon started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nMonitoring: logs, pipeline stall\nDaily digest: {DIGEST_HOUR}:00 local time",
    )

    while True:
        try:
            check_logs(r)
            check_pipeline_stall(r)
            if should_send_digest(r):
                send_digest(r)
        except Exception as e:
            logger.error("Main loop error: %s", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
