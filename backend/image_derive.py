"""
Card-image derivation that stops decapitating designed graphics.

Drop-in for the derivative half of scribe.py:rehost_article_image. The preserved
`{article_id}-orig.jpg` written by Stage 1 is the input; this decides how to get
from that to a 1200x675 card image without destroying the source.

The rule: PHOTOGRAPHS get center-cropped (invisible, subject is central, cover
keeps the card grid uniform). DESIGNED GRAPHICS get letterboxed onto a
background sampled from their own edges (any crop clips logos, axes, captions,
ground lines -- and saliency cropping clips them harder, because designers put
those elements on flat ground and flat ground scores lowest on every energy
metric).

Status (2026-08-01):
  - NOT YET WIRED INTO scribe.rehost_article_image. See TODO T2. The audit
    said the swap at scribe.py:665-675 is contained, but the primary
    signal below has to be settled first.
  - Calibration over 542 preserved originals found the top-16 palette
    concentration is NOT bimodal: photograph mass at 0.30-0.65, gradual
    transition through 0.65-0.90, one clean spike at 0.95-1.00 (74 files,
    13.7%). The threshold below is set to 0.95 to act only where the
    signal is genuinely bimodal; everything else is a judgment call the
    data does not support.
  - The palette-concentration detector is expected to be replaced with a
    center-crop-harm test (does the strip we'd discard actually contain
    meaningful content?), which needs no population split and has
    checkable ground truth. See TODO T1. This module ships as scaffold.
"""

from PIL import Image, ImageFilter
import numpy as np

CARD_W, CARD_H = 1200, 675
CARD_RATIO = CARD_W / CARD_H            # 1.7778

# --- tunables -------------------------------------------------------------
# Fraction of pixels covered by the 16 most common quantized colors. Designed
# graphics concentrate hard (the KFF "On Air" weekly measures 0.934); continuous
# -tone photographs spread out. UNCALIBRATED against a real corpus -- run
# report() over a directory of -orig.jpg and set this from the histogram.
GRAPHIC_PALETTE_THRESHOLD = 0.95

# Ratios within this tolerance of 16:9 crop with negligible loss; don't
# letterbox and introduce bars to save 2%.
RATIO_TOLERANCE = 0.06

# If letterboxing would leave more than this fraction of the card as background,
# crop instead -- a tall portrait pillarboxed into 16:9 is mostly bars and looks
# more broken than a crop does.
MAX_BACKGROUND_FRACTION = 0.42
# --------------------------------------------------------------------------


def palette_concentration(img, top_n=16):
    """Fraction of pixels covered by the top_n most common quantized colors.

    Median filter first: many designed graphics carry a deliberate paper-grain
    or noise texture that pushes raw unique-color counts into photograph
    territory (the KFF graphic returns 94,936 colors from getcolors()). The
    filter removes the grain and leaves the flat regions flat.
    """
    small = img.convert("RGB")
    # Downscale before filtering -- 20x faster, same answer to 3 decimals.
    small.thumbnail((640, 640), Image.LANCZOS)
    a = np.asarray(small.filter(ImageFilter.MedianFilter(size=5)))
    q = (a >> 4).astype(np.uint32)                       # 4 bits per channel
    packed = (q[..., 0] << 8) | (q[..., 1] << 4) | q[..., 2]
    counts = np.sort(np.bincount(packed.ravel()))[::-1]
    return float(counts[:top_n].sum() / counts.sum())


def is_graphic(img):
    return palette_concentration(img) >= GRAPHIC_PALETTE_THRESHOLD


def edge_background(img):
    """Modal color of the image border -- the letterbox fill.

    Sampling the image's own edge means the bars read as part of the design
    rather than as black rails around a broken image.
    """
    a = np.asarray(img.convert("RGB"))
    h, w, _ = a.shape
    band = max(2, min(h, w) // 100)
    edges = np.concatenate([
        a[:band].reshape(-1, 3), a[-band:].reshape(-1, 3),
        a[:, :band].reshape(-1, 3), a[:, -band:].reshape(-1, 3),
    ])
    q = (edges >> 3).astype(np.uint32)
    packed = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
    modal = np.bincount(packed).argmax()
    mask = packed == modal
    return tuple(int(v) for v in edges[mask].mean(axis=0).round())


def center_crop(img, w=CARD_W, h=CARD_H):
    """Existing behaviour: fill the card, discard the overflow."""
    src_ratio = img.width / img.height
    target = w / h
    if src_ratio > target:
        new_w = int(img.height * target)
        box = ((img.width - new_w) // 2, 0,
               (img.width - new_w) // 2 + new_w, img.height)
    else:
        new_h = int(img.width / target)
        box = (0, (img.height - new_h) // 2,
               img.width, (img.height - new_h) // 2 + new_h)
    return img.crop(box).resize((w, h), Image.LANCZOS)


def letterbox(img, w=CARD_W, h=CARD_H, bg=None):
    """Fit the whole image inside the card, pad with the edge color."""
    fitted = img.copy()
    fitted.thumbnail((w, h), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), bg or edge_background(img))
    canvas.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
    return canvas


def background_fraction(img, w=CARD_W, h=CARD_H):
    scale = min(w / img.width, h / img.height)
    return 1.0 - (img.width * scale * img.height * scale) / (w * h)


def derive_card(img, w=CARD_W, h=CARD_H):
    """Returns (card_image, mode, diagnostics)."""
    ratio = img.width / img.height
    target = w / h
    conc = palette_concentration(img)
    diag = {"ratio": round(ratio, 4), "palette_top16": round(conc, 4)}

    if abs(ratio - target) / target <= RATIO_TOLERANCE:
        return center_crop(img, w, h), "crop:near-ratio", diag

    if conc < GRAPHIC_PALETTE_THRESHOLD:
        return center_crop(img, w, h), "crop:photo", diag

    bg_frac = background_fraction(img, w, h)
    diag["background_fraction"] = round(bg_frac, 4)
    if bg_frac > MAX_BACKGROUND_FRACTION:
        return center_crop(img, w, h), "crop:graphic-too-tall", diag

    return letterbox(img, w, h), "letterbox:graphic", diag


def report(directory, pattern="*-orig.jpg"):
    """Calibration pass: print the palette histogram over preserved originals."""
    import glob, os
    rows = []
    for path in sorted(glob.glob(os.path.join(directory, pattern))):
        try:
            im = Image.open(path).convert("RGB")
        except Exception as exc:
            print(f"  SKIP {os.path.basename(path)}: {exc}")
            continue
        rows.append((os.path.basename(path), im.width / im.height,
                     palette_concentration(im)))
    if not rows:
        print("no images matched"); return rows
    vals = np.array([r[2] for r in rows])
    print(f"\n{len(rows)} images")
    print("  deciles: " + " ".join(f"{np.percentile(vals, p):.3f}"
                                   for p in range(10, 100, 10)))
    hist, edges = np.histogram(vals, bins=20, range=(0, 1))
    for c, lo in zip(hist, edges):
        print(f"  {lo:.2f}-{lo+0.05:.2f} | {'#' * min(c, 60)} {c}")
    n = int((vals >= GRAPHIC_PALETTE_THRESHOLD).sum())
    print(f"\n  >= {GRAPHIC_PALETTE_THRESHOLD}: {n} ({n/len(rows)*100:.1f}%) "
          f"would letterbox")
    return rows


if __name__ == "__main__":
    import sys
    report(sys.argv[1] if len(sys.argv) > 1 else ".")
