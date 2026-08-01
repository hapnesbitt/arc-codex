"""Pin the scraped-derivative sweep in `purge_article_satellites`.

Regression guard for Stage 1 (Jul 30 2026): `-orig.jpg` was added to
scribe.py's write path but not to retention.py's enumeration, silently
orphaning ~500 files after a single trim. The fix is a prefix glob; this
test pins it so a future derivative can't reintroduce the same drift.
"""
import glob
import os
from unittest.mock import MagicMock

import retention


def test_purge_sweeps_every_scraped_derivative_for_the_article(tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "SCRAPED_IMAGE_DIR", str(tmp_path))

    aid = "00112233445566778899aabbccddeeff"
    decoy = "ffeeddccbbaa99887766554433221100"

    satellite_names = [
        f"{aid}.jpg",
        f"{aid}-orig.jpg",
        f"{aid}-480.webp",
        f"{aid}-800.webp",
        f"{aid}-1200.webp",
    ]
    decoy_name = f"{decoy}.jpg"

    for name in satellite_names + [decoy_name]:
        (tmp_path / name).write_bytes(b"x")

    r = MagicMock()
    r.lrange.return_value = []
    r.smembers.return_value = set()

    retention.purge_article_satellites(r, aid, char_state_keys=[])

    remaining = sorted(os.path.basename(p) for p in glob.glob(str(tmp_path / "*")))
    assert remaining == [decoy_name], (
        f"expected only decoy to remain; got {remaining}"
    )


def test_purge_is_idempotent_when_no_files_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "SCRAPED_IMAGE_DIR", str(tmp_path))

    r = MagicMock()
    r.lrange.return_value = []
    r.smembers.return_value = set()

    retention.purge_article_satellites(r, "0" * 32, char_state_keys=[])
