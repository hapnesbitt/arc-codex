"""image_rehost.py — fetch and re-host a scraped hero image.

Split out of scribe.py 2026-08-27 (scribe recon/cleanup — see
ops/RUNBOOK.md). rehost_article_image was already close to pure: article_id
and a URL in, a served path or None out, touching only these constants and
net_safety's SSRF guard — no scribe.py module state.

scraped_dir is passed in (not imported) since it's derived from the
caller's own BASE_DIR — this module doesn't need to know where its caller
lives on disk.
"""

from __future__ import annotations

import io
import logging
import os

import requests
from PIL import Image, ImageOps

from net_safety import resolves_to_private_ip

logger = logging.getLogger('scribe')

REHOST_W, REHOST_H = 1200, 675          # 16:9 — matches the aspect-video card container
REHOST_ORIG_MAX = 1920                  # longest-side cap for the preserved source; matches main.py:_upload_image_inner
REHOST_MAX_BYTES = 10 * 1024 * 1024     # same cap as the manual-upload endpoint
REHOST_FETCH_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
}


def rehost_article_image(article_id: str, image_url: str, scraped_dir: str) -> str | None:
    """Fetch an external hero image, save two normalized outputs under
    scraped_dir — idempotent per article. Returns the relative serving
    path (the card), or None on any failure: callers must then fall back to
    the site default image (never ship the failed hotlink); the article
    publishes regardless.

    Outputs:
      {article_id}.jpg      — 1200x675 center-crop, the card derivative.
                              Byte-for-byte the same as before the split;
                              filename unchanged so imageUrl, the 480/800/
                              1200 WebP variants, and Caddy's /uploads/*
                              handler all keep pointing at this exact path.
      {article_id}-orig.jpg — Preserved source, longest side ≤ 1920, no
                              crop. Enables re-deriving the card (or new
                              presentations) without a re-fetch of an
                              upstream URL that may have rotted.
    """
    try:
        if not image_url.startswith(('http://', 'https://')):
            return None
        if resolves_to_private_ip(image_url):
            logger.warning(f"🖼️  Rehost skipped (private address): {image_url[:80]}")
            return None

        resp = requests.get(image_url, timeout=10, stream=True, headers=REHOST_FETCH_HEADERS)
        if resp.status_code != 200:
            logger.info(f"🖼️  Rehost fetch HTTP {resp.status_code}: {image_url[:80]}")
            return None
        content_type = resp.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            logger.info(f"🖼️  Rehost non-image content-type '{content_type[:30]}': {image_url[:80]}")
            return None
        raw = b''
        for chunk in resp.iter_content(chunk_size=65536):
            raw += chunk
            if len(raw) > REHOST_MAX_BYTES:
                logger.info(f"🖼️  Rehost over size cap: {image_url[:80]}")
                return None

        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')  # flattens GIF/PNG alpha; animated GIFs keep first frame only
        src_w, src_h = img.size
        os.makedirs(scraped_dir, exist_ok=True)

        # Preserved source. Resize only — longest side ≤ REHOST_ORIG_MAX,
        # aspect kept, no crop. Copies main.py:_upload_image_inner's pattern
        # so manual and scraped originals normalize identically. Both files
        # exist because the card crop below is non-destructive: the source
        # survives, so future presentation changes (article-page full-image
        # hero, dimensions-in-hash, saliency cropping) become a re-derivation
        # off this file rather than a re-fetch of a URL that may have
        # rotted. Cleanup: backend/cleanup.py:purge_scraped_images splits
        # filename on '-' to extract the article_id, so `{id}-orig.jpg`
        # sweeps under the same [retention].image_days rule as the card and
        # its variants.
        # TODO: dimensions-in-hash, article-page full-image hero, saliency
        # cropping — deferred; this file is what makes them possible.
        preserved = img.copy()
        if max(preserved.size) > REHOST_ORIG_MAX:
            preserved.thumbnail((REHOST_ORIG_MAX, REHOST_ORIG_MAX), Image.LANCZOS)
        preserved.save(os.path.join(scraped_dir, f"{article_id}-orig.jpg"),
                       format='JPEG', quality=88, optimize=True)

        # Card derivative — 1200x675 center-crop. Byte-for-byte identical to
        # pre-split output; filename intentionally unchanged.
        scale = max(REHOST_W / src_w, REHOST_H / src_h)
        new_w, new_h = round(src_w * scale), round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - REHOST_W) // 2
        top = (new_h - REHOST_H) // 2
        img = img.crop((left, top, left + REHOST_W, top + REHOST_H))

        img.save(os.path.join(scraped_dir, f"{article_id}.jpg"),
                 format='JPEG', quality=85, optimize=True)
        logger.info(f"🖼️  Rehosted image for {article_id}: {src_w}x{src_h} → {REHOST_W}x{REHOST_H} + orig ({max(preserved.size)}px longest)")

        # WebP variants for responsive srcset (see frontend IntelligenceCard <picture>).
        # Non-fatal: any variant failure logs and continues; the JPEG serves as fallback.
        for variant_w in (480, 800, 1200):
            try:
                variant = img.copy()
                variant.thumbnail((variant_w, variant_w * 10), Image.LANCZOS)
                variant.save(os.path.join(scraped_dir, f"{article_id}-{variant_w}.webp"),
                             format='WEBP', quality=80, method=6)
            except Exception as e:
                logger.info(f"🖼️  Variant -{variant_w}.webp failed for {article_id}: {type(e).__name__}: {e}")

        return f"/uploads/scraped/{article_id}.jpg"
    except Exception as e:
        logger.info(f"🖼️  Rehost failed ({type(e).__name__}) for {image_url[:80]}")
        return None
