#!/usr/bin/env python3
"""
Arc Codex — cecil.py
Email-to-publish daemon. Watches /home/cecil/Maildir/new/ for incoming mail,
verifies sender + subject, and submits to the scribe priority queue via
the existing /api/submit endpoint.

Trust model:
  Postfix is configured to reject non-allowlisted senders at SMTP time
  (5xx response, message never reaches the mailbox). The application
  allowlist below is belt-and-suspenders.

Reply mechanism mirrors mailer.py: local Postfix on port 25.
"""

import email
import hashlib
import json
import logging
import mimetypes
import os
import shutil
import smtplib
import sys
import time
import traceback
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.mime.text import MIMEText
from email.utils import parseaddr

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CECIL_FROM       = "cecil@arc-codex.com"
ALLOWED_SENDER   = "rossnesbitt@gmail.com"
SUBJECT_PREFIX   = "#PublishNow"
OWNER_USER_ID    = "ross"
SUBMIT_URL       = "http://127.0.0.1:5005/api/submit"

MAILDIR_ROOT     = "/home/cecil/Maildir"
MAILDIR_NEW      = os.path.join(MAILDIR_ROOT, "new")
MAILDIR_PROCESSED = os.path.join(MAILDIR_ROOT, ".Processed", "cur")
MAILDIR_FAILED   = os.path.join(MAILDIR_ROOT, ".Failed", "cur")

UPLOADS_DIR      = "/home/www/arc_stack/frontend/public/uploads"
UPLOADS_URL_BASE = "/uploads"

MIN_BODY_CHARS   = 200
POLL_INTERVAL    = 30   # seconds, fallback if inotify is unavailable

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [CECIL] - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/home/www/arc_stack/logs/cecil.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mail parsing
# ---------------------------------------------------------------------------

def normalize_sender(raw_from: str) -> str:
    """'Ross Nesbitt <rossnesbitt@gmail.com>' -> 'rossnesbitt@gmail.com'."""
    _, addr = parseaddr(raw_from or "")
    return addr.strip().lower()


def strip_signature(text: str) -> str:
    """Remove a standard RFC 3676 signature block (lines after '-- ')."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.rstrip() == "--" or line == "-- ":
            return "\n".join(lines[:i]).rstrip()
    return text.rstrip()


def extract_plain_body(msg) -> str:
    """Pull the best-effort plain-text body from an email.message.EmailMessage."""
    plain_part = None
    html_part  = None
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        cdisp = (part.get("Content-Disposition") or "").lower()
        if "attachment" in cdisp:
            continue
        if ctype == "text/plain" and plain_part is None:
            plain_part = part
        elif ctype == "text/html" and html_part is None:
            html_part = part

    if plain_part is not None:
        try:
            text = plain_part.get_content()
        except Exception:
            payload = plain_part.get_payload(decode=True) or b""
            charset = plain_part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
        return strip_signature(text).strip()

    if html_part is not None:
        try:
            html = html_part.get_content()
        except Exception:
            payload = html_part.get_payload(decode=True) or b""
            charset = html_part.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return strip_signature(text).strip()

    return ""


def extract_first_image(msg):
    """Return (image_bytes, extension) for the first image attachment, or (None, None)."""
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        if not ctype.startswith("image/"):
            continue
        data = part.get_payload(decode=True)
        if not data:
            continue
        # Prefer extension from filename, fall back to mimetypes
        ext = None
        fname = part.get_filename() or ""
        if "." in fname:
            ext = fname.rsplit(".", 1)[-1].lower()
        if not ext:
            guessed = mimetypes.guess_extension(ctype) or ".jpg"
            ext = guessed.lstrip(".").lower()
        if ext == "jpeg":
            ext = "jpg"
        return data, ext
    return None, None


def save_image(data: bytes, ext: str) -> str:
    """Write image to uploads dir keyed by content hash; return the public URL path."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    filename = f"{digest}.{ext}"
    target = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(target):
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.rename(tmp, target)
    return f"{UPLOADS_URL_BASE}/{filename}"

# ---------------------------------------------------------------------------
# Submit + reply
# ---------------------------------------------------------------------------

def submit_to_scribe(title: str, body: str, image_url, owner: str) -> dict:
    payload = {
        "content_type": "text",
        "content":      body,
        "title":        title,
        "image_url":    image_url,
        "visibility":   "public",
    }
    headers = {"X-User-Id": owner}
    r = requests.post(SUBMIT_URL, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def send_reply(to_addr: str, original_subject: str, body_text: str) -> bool:
    """Reply via local Postfix. mailer.py:103 pattern."""
    try:
        msg = MIMEText(body_text)
        msg["From"]    = CECIL_FROM
        msg["To"]      = to_addr
        msg["Subject"] = f"Re: {original_subject}" if original_subject else "Re: Cecil"
        with smtplib.SMTP("localhost", 25, timeout=10) as smtp:
            smtp.sendmail(CECIL_FROM, [to_addr], msg.as_string())
        logger.info("📤 Reply sent to %s", to_addr)
        return True
    except Exception as e:
        logger.error("❌ Failed to send reply to %s: %s", to_addr, e)
        return False

# ---------------------------------------------------------------------------
# Maildir filing
# ---------------------------------------------------------------------------

def move_to(src_path: str, dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    base = os.path.basename(src_path)
    # Maildir convention: ':2,S' marks message as Seen
    if ":2," not in base:
        base += ":2,S"
    dest = os.path.join(dest_dir, base)
    shutil.move(src_path, dest)
    return dest

# ---------------------------------------------------------------------------
# Per-message processing
# ---------------------------------------------------------------------------

def process_message(path: str):
    logger.info("📬 New mail arrived: %s", os.path.basename(path))

    try:
        with open(path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
    except Exception as e:
        logger.error("Failed to parse %s: %s", path, e)
        move_to(path, MAILDIR_FAILED)
        return

    sender   = normalize_sender(msg.get("From", ""))
    subject  = (msg.get("Subject") or "").strip()
    msg_id   = msg.get("Message-Id", os.path.basename(path))

    # Sender allowlist
    if sender != ALLOWED_SENDER:
        logger.warning("🚫 Rejected unauthorized sender: %r (msg %s)", sender, msg_id)
        move_to(path, MAILDIR_FAILED)
        return
    logger.info("✅ Sender verified: %s", sender)

    # Subject prefix
    if not subject.startswith(SUBJECT_PREFIX):
        logger.warning("🚫 Rejected subject without prefix: %r", subject)
        move_to(path, MAILDIR_FAILED)
        return
    logger.info("✅ Subject matched: %s", subject)

    # Title is everything after the prefix + space
    title = subject[len(SUBJECT_PREFIX):].strip() or "Untitled"

    # Body
    try:
        body = extract_plain_body(msg)
    except Exception as e:
        logger.error("Body extraction failed: %s", e)
        body = ""

    if len(body) < MIN_BODY_CHARS:
        err = f"Body too short ({len(body)} chars; need at least {MIN_BODY_CHARS})."
        logger.warning("🚫 %s", err)
        send_reply(
            sender,
            subject,
            f"Cecil could not publish your article: {err}\n\n"
            f"Send the body inline as plain text. Subject was: {subject}\n",
        )
        move_to(path, MAILDIR_FAILED)
        return

    # Image (optional)
    image_url = None
    try:
        img_data, img_ext = extract_first_image(msg)
        if img_data:
            image_url = save_image(img_data, img_ext)
            logger.info("✅ Image saved: %s (%d bytes)", image_url, len(img_data))
    except Exception as e:
        logger.warning("Image extraction failed (continuing without image): %s", e)

    # Submit
    try:
        result = submit_to_scribe(title, body, image_url, OWNER_USER_ID)
        job_id = result.get("job_id", "")
        logger.info("✅ Submitted to scribe queue (job_id: %s)", job_id)
    except Exception as e:
        logger.error("❌ Submit failed: %s\n%s", e, traceback.format_exc())
        send_reply(
            sender,
            subject,
            f"Cecil could not publish your article: {e}\n\n"
            f"Subject was: {subject}\n",
        )
        move_to(path, MAILDIR_FAILED)
        return

    # Confirmation reply
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reply_body = (
        f"Published: https://arc-codex.com/article/{job_id}\n\n"
        f"Submitted at {timestamp}. Scribe will analyze and post within ~2 minutes.\n"
    )
    send_reply(sender, subject, reply_body)
    move_to(path, MAILDIR_PROCESSED)
    logger.info("✅ Done: %s", title)

# ---------------------------------------------------------------------------
# Watcher (inotify with polling fallback)
# ---------------------------------------------------------------------------

def drain_existing():
    """Process any files that landed before the watcher started."""
    if not os.path.isdir(MAILDIR_NEW):
        return
    for name in sorted(os.listdir(MAILDIR_NEW)):
        full = os.path.join(MAILDIR_NEW, name)
        if os.path.isfile(full):
            try:
                process_message(full)
            except Exception:
                logger.error("Unhandled error processing %s:\n%s", full, traceback.format_exc())


def run_inotify():
    import pyinotify
    wm = pyinotify.WatchManager()
    # IN_MOVED_TO: Postfix delivers via tmp/ -> new/ rename, this is the safe trigger.
    mask = pyinotify.IN_MOVED_TO

    class Handler(pyinotify.ProcessEvent):
        def process_IN_MOVED_TO(self, event):
            try:
                process_message(event.pathname)
            except Exception:
                logger.error(
                    "Unhandled error processing %s:\n%s",
                    event.pathname, traceback.format_exc(),
                )

    notifier = pyinotify.Notifier(wm, Handler())
    wm.add_watch(MAILDIR_NEW, mask)
    logger.info("👀 inotify watching %s", MAILDIR_NEW)
    notifier.loop()


def run_polling():
    logger.info("👀 polling %s every %ds", MAILDIR_NEW, POLL_INTERVAL)
    seen = set()
    while True:
        try:
            current = set(os.listdir(MAILDIR_NEW)) if os.path.isdir(MAILDIR_NEW) else set()
            for name in sorted(current - seen):
                full = os.path.join(MAILDIR_NEW, name)
                if os.path.isfile(full):
                    try:
                        process_message(full)
                    except Exception:
                        logger.error("Unhandled error: %s", traceback.format_exc())
            seen = current
        except Exception as e:
            logger.error("Poll loop error: %s", e)
        time.sleep(POLL_INTERVAL)


def main():
    logger.info("🚀 Cecil starting (watching %s)", MAILDIR_NEW)
    for d in (MAILDIR_PROCESSED, MAILDIR_FAILED, UPLOADS_DIR):
        os.makedirs(d, exist_ok=True)

    if not os.path.isdir(MAILDIR_NEW):
        logger.error("Maildir does not exist: %s — exiting", MAILDIR_NEW)
        sys.exit(1)

    drain_existing()

    try:
        import pyinotify  # noqa: F401
        run_inotify()
    except ImportError:
        logger.warning("pyinotify not available — falling back to polling")
        run_polling()


if __name__ == "__main__":
    main()
