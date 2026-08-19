"""Regression test for the byte-cut mid-multibyte UnicodeDecodeError in
get_recent_log_lines (introduced 2026-08-16, investigated 2026-08-19).

Background — `tail -c LOG_TAIL_BYTES` cuts the file at an exact byte offset.
When the offset falls inside a multi-byte UTF-8 sequence (very common with
this stack's emoji-heavy log lines: 🚀 🛑 ✅ ⚠️ 🚨), the leading bytes are
UTF-8 continuation bytes. `subprocess.run(text=True)` decodes with strict
UTF-8 by default, which raises UnicodeDecodeError, which the outer
except-Exception handler swallows as a "Failed to read log" warning and
returns []. Effect: on peak days ~14-16% of scans on hot logs returned no
lines at all — the alert scanner was silently blind for those windows.

The fix decodes the tail's stdout ourselves with errors='replace', so the
partial leading character becomes �; the surrounding line has no
matching timestamp and is dropped by the existing timestamp filter, and
every real log line after the cut comes through unharmed.

The test uses a real temporary log file and a real tail(1) invocation —
no mocking of subprocess. LOG_TAIL_BYTES is monkeypatched to a small
value chosen so the tail's byte cut lands inside a 4-byte emoji.
"""
from datetime import datetime
import logging
from unittest.mock import MagicMock, patch


with patch.object(logging, "FileHandler", return_value=logging.NullHandler()):
    import mailer


def test_get_recent_log_lines_survives_byte_cut_mid_emoji(monkeypatch, tmp_path, caplog):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Prefix is eight consecutive rocket emojis (4 bytes each) + a newline —
    # 33 bytes total. Any tail cut whose start offset is in [1..32] and not on
    # a 4-byte boundary lands inside an emoji, producing UTF-8 continuation
    # bytes at the head of the tail output.
    prefix_bytes = ("🚀" * 8 + "\n").encode("utf-8")
    real_line = f"{now} - [SVC] - INFO - real event that must survive the cut\n"
    real_bytes = real_line.encode("utf-8")

    log_path = tmp_path / "svc.log"
    log_path.write_bytes(prefix_bytes + real_bytes)

    # Take the real line + 3 bytes → cut lands two bytes into the last emoji.
    # This is the same failure shape reported in the mailer log:
    # "'utf-8' codec can't decode byte 0x9a in position 0: invalid start byte"
    monkeypatch.setattr(mailer, "LOG_TAIL_BYTES", len(real_bytes) + 3)

    r = MagicMock()

    with caplog.at_level(logging.WARNING, logger=mailer.__name__):
        lines = mailer.get_recent_log_lines(
            str(log_path), minutes=5, service="svc", r=r,
        )

    # The real, timestamped line MUST come through — this is the whole point
    # of alerting still working when the boundary is unlucky.
    assert any("real event that must survive the cut" in ln for ln in lines), (
        f"real timestamped line was lost by the byte-cut; got lines={lines!r}"
    )

    # No "Failed to read log" warning must fire on the boundary case, and the
    # log-read-failure counter must NOT get incremented — that counter drives
    # the diagnosis email's "silent scanner failures" line, so a false bump
    # would misdirect the operator.
    read_warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "Failed to read log" in rec.getMessage()
    ]
    assert read_warnings == [], (
        f"boundary cut must not surface as a read failure; got {read_warnings!r}"
    )
    r.incr.assert_not_called()
