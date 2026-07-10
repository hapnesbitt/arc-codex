#!/usr/bin/env python3
"""
Backfill WebP variants for scraped hero images.

Walks /uploads/scraped/*.jpg and, for each JPEG, emits WebP variants at
480 / 800 / 1200 pixel widths (downscale-only, aspect preserved) alongside
the original. Originals are never modified or deleted. Idempotent — a
JPEG whose three variants already exist is skipped.

Dry-run by default: reports file count, projected new bytes, and free
space on the target mount. Actual generation requires --execute.

Usage:
    # Dry-run (default)
    python3 make_image_variants.py

    # Actually generate
    python3 make_image_variants.py --execute

    # Override the target dir
    python3 make_image_variants.py --path /some/other/dir
"""

import argparse
import io
import random
import shutil
import sys
from pathlib import Path

from PIL import Image

DEFAULT_ROOT = Path("/home/www/arc_stack/frontend/public/uploads/scraped")
VARIANT_WIDTHS = (480, 800, 1200)
WEBP_QUALITY = 80
DEFAULT_SAMPLE_SIZE = 20


def variant_paths(jpg: Path) -> list[Path]:
    return [jpg.with_name(f"{jpg.stem}-{w}.webp") for w in VARIANT_WIDTHS]


def needs_generation(jpg: Path) -> bool:
    return not all(v.exists() for v in variant_paths(jpg))


def encode_variant(im: Image.Image, target_width: int) -> bytes:
    v = im.copy()
    # thumbnail is downscale-only; if original is smaller than target,
    # the variant retains original dimensions (no upscale).
    v.thumbnail((target_width, target_width * 10), Image.LANCZOS)
    if v.mode not in ("RGB", "RGBA"):
        v = v.convert("RGB")
    buf = io.BytesIO()
    v.save(buf, "WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue()


def project_bytes(pending: list[Path], sample_size: int) -> tuple[int, int]:
    """Sample-based projection. Returns (projected_total_bytes, sample_used)."""
    if not pending:
        return 0, 0
    sample = random.sample(pending, min(sample_size, len(pending)))
    sample_bytes = 0
    for jpg in sample:
        try:
            with Image.open(jpg) as im:
                im.load()
                for w in VARIANT_WIDTHS:
                    variant = jpg.with_name(f"{jpg.stem}-{w}.webp")
                    if variant.exists():
                        continue
                    sample_bytes += len(encode_variant(im, w))
        except Exception as e:
            print(f"  [sample] error on {jpg.name}: {e}", file=sys.stderr)
    per_file = sample_bytes / len(sample) if sample else 0
    return int(per_file * len(pending)), len(sample)


def check_webp_support() -> None:
    """Fail fast if Pillow lacks WebP encode support."""
    buf = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buf, "WEBP")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--path", type=Path, default=DEFAULT_ROOT, help="scraped uploads dir")
    p.add_argument("--execute", action="store_true", help="actually write variants (default: dry-run)")
    p.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE, help="dry-run sample size")
    args = p.parse_args()

    root: Path = args.path
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 1

    try:
        check_webp_support()
    except Exception as e:
        print(f"ERROR: Pillow WebP support missing ({e}). Install libwebp or fall back to cwebp.", file=sys.stderr)
        return 1

    jpgs = sorted(root.glob("*.jpg"))
    total = len(jpgs)
    pending = [j for j in jpgs if needs_generation(j)]
    already_done = total - len(pending)

    print(f"scanning: {root}")
    print(f"  total .jpg files:      {total:,}")
    print(f"  fully variantised:     {already_done:,}")
    print(f"  pending:               {len(pending):,}")

    if not pending:
        print("all files fully variantised — nothing to do.")
        return 0

    if not args.execute:
        print(f"  sampling {min(args.sample_size, len(pending))} pending files to project disk cost...")
        projected, sample_used = project_bytes(pending, args.sample_size)
        usage = shutil.disk_usage(root)
        print()
        print(f"projected new bytes:     {projected:>15,}  (~{projected / 1024 / 1024:.1f} MB)")
        print(f"target mount free bytes: {usage.free:>15,}  (~{usage.free / 1024 / 1024 / 1024:.1f} GB)")
        print(f"target mount total:      {usage.total:>15,}  (~{usage.total / 1024 / 1024 / 1024:.1f} GB)")
        post_free = usage.free - projected
        print(f"post-generation free:    {post_free:>15,}  (~{post_free / 1024 / 1024 / 1024:.1f} GB, "
              f"{post_free / usage.total * 100:.1f}% of mount)")
        print()
        print(f"DRY RUN — no files written. Sampled {sample_used} of {len(pending)} pending. "
              f"Re-run with --execute to generate variants.")
        return 0

    generated = 0
    errors = 0
    written_bytes = 0
    for jpg in pending:
        try:
            with Image.open(jpg) as im:
                im.load()
                for w in VARIANT_WIDTHS:
                    variant = jpg.with_name(f"{jpg.stem}-{w}.webp")
                    if variant.exists():
                        continue
                    data = encode_variant(im, w)
                    variant.write_bytes(data)
                    written_bytes += len(data)
                    generated += 1
        except Exception as e:
            print(f"  ERROR on {jpg.name}: {e}", file=sys.stderr)
            errors += 1
    print(f"  generated: {generated} variant files")
    print(f"  written:   {written_bytes:,} bytes ({written_bytes / 1024 / 1024:.1f} MB)")
    if errors:
        print(f"  errors:    {errors} file(s) skipped")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
