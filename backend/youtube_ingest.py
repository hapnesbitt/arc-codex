"""youtube_ingest.py — YouTube URL detection and metadata-only ingestion.

Split out of scribe.py 2026-08-27 (scribe recon/cleanup — see
ops/RUNBOOK.md). A real seam: both functions were already pure — URL/text
in, dict/bool out — touching nothing but yt-dlp and the two caller-supplied
constants below. No scribe.py state crosses this boundary.

default_image_url and min_article_length are passed in rather than
imported: they're arc-codex.com branding and scribe's publish-quality bar,
not properties of YouTube ingestion — this module works unchanged for any
caller with its own values for both.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import yt_dlp

logger = logging.getLogger('scribe')


def is_youtube_url(url: str) -> bool:
    """Detect YouTube URLs including youtu.be short links."""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc in (
            'www.youtube.com', 'youtube.com',
            'youtu.be', 'www.youtu.be',
            'm.youtube.com',
        )
    except Exception:
        return False


def fetch_youtube_metadata(url: str, default_image_url: str, min_article_length: int):
    """
    Extract YouTube video metadata without downloading.
    Uses yt-dlp in metadata-only mode.
    Returns same dict shape as fetch_with_requests.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title       = info.get('title', 'Untitled')
        channel     = info.get('channel') or info.get('uploader', 'Unknown')
        description = (info.get('description') or '').strip()[:3000]
        duration    = info.get('duration_string') or str(info.get('duration', ''))
        upload_date = info.get('upload_date', '')   # YYYYMMDD
        view_count  = info.get('view_count') or 0
        thumbnail   = info.get('thumbnail') or default_image_url

        if upload_date and len(upload_date) == 8:
            upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        # Build structured text — this is what the ARC pipeline will analyze
        article_text = (
            f"Title: {title}\n"
            f"Channel: {channel}\n"
            f"Published: {upload_date}\n"
            f"Duration: {duration}\n"
            f"Views: {view_count:,}\n\n"
            f"Description:\n{description}"
        ).strip()

        if len(article_text) < min_article_length:
            logger.warning(f"▶️  YouTube metadata too sparse for {url} — skipping")
            return None

        logger.info(f"▶️  YouTube metadata extracted: '{title[:60]}' ({channel})")
        return {
            'text': article_text,
            'image_url': thumbnail,
            'html_content': '',
        }

    except Exception as e:
        logger.error(f"▶️  YouTube metadata extraction failed for {url}: {e}")
        return None
