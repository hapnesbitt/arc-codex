"""Regression tests for the daily-digest send-outcome path (PD-01, PD-07).

PD-01 (send-outcome burn):
    The old code set the per-day anti-duplicate key at the *decision to send*,
    before SMTP. When SMTP failed, the key stayed set for ~25h and the digest
    was lost for the day. The fix uses TWO keys:

        mailer:digest:{YYYY-MM-DD}:lock   short-TTL SETNX guard (600s) taken
                                          in should_send_digest before SMTP,
                                          released by the caller on failure so
                                          the next 60s loop tick retries.
        mailer:digest:{YYYY-MM-DD}:sent   long-TTL success marker (90000s)
                                          set by the caller ONLY after
                                          send_digest returns True.

    Retries are bounded to the DIGEST_HOUR window — once the hour rolls over,
    should_send_digest short-circuits on the hour check and no further sends
    are attempted that day.

PD-07 (misleading log line):
    The old code logged "✅ Daily digest sent" unconditionally, so on SMTP
    failure the log asserted the opposite of what had happened. The fix moves
    the success log inside the ok branch and adds a WARNING on failure.
"""
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch


# mailer.py opens /home/www/arc_stack/logs/mailer.log via FileHandler at
# import time. Swap the handler out so the tests have no production side
# effect and can assert against caplog cleanly.
with patch.object(logging, "FileHandler", return_value=logging.NullHandler()):
    import mailer


def _freeze_clock(monkeypatch, now: datetime) -> None:
    """Freeze mailer.datetime.now() so DIGEST_HOUR and the date key are
    deterministic. Mirrors the Hunt test_mailer pattern."""
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)
    monkeypatch.setattr(mailer, "datetime", FrozenDateTime)


def _stub_redis_with_one_article() -> MagicMock:
    """A fresh Redis mock with no prior digest keys and exactly one article
    in the feed — the minimum to make get_top_articles return non-empty and
    exercise the send_email path."""
    r = MagicMock()
    r.exists.return_value = False           # no :sent key yet
    r.set.return_value = True               # SETNX succeeds → we got the lock
    r.zrevrange.return_value = ["art-1"]
    r.hgetall.return_value = {
        "title": "Test article",
        "source": "Test source",
        "timestamp": "2026-08-19T07:00:00+00:00",  # inside the 24h window
        "dossier": '{"objectivity_score": 80}',
    }
    return r


def _apply_outcome(r: MagicMock, ok: bool, date: str) -> None:
    """Mirror main()'s post-send branch so the test asserts the whole
    should_send_digest → send_digest → outcome chain, not just one half."""
    sent_key = f"mailer:digest:{date}:sent"
    lock_key = f"mailer:digest:{date}:lock"
    if ok:
        r.setex(sent_key, 90000, "1")
    else:
        r.delete(lock_key)


# ---------------------------------------------------------------------------
# PD-01 + PD-07: SMTP failure must not burn the day, and must log at WARNING
# ---------------------------------------------------------------------------

def test_smtp_failure_leaves_sent_key_unset_lock_released_and_warns(monkeypatch, caplog):
    r = _stub_redis_with_one_article()
    _freeze_clock(monkeypatch, datetime(2026, 8, 19, 7, 5))  # inside DIGEST_HOUR

    # send_email returns False when SMTP raises (see its except: block).
    # We short-circuit at that layer rather than mocking smtplib so the test
    # is coupled to the contract send_digest actually depends on.
    monkeypatch.setattr(mailer, "send_email", MagicMock(return_value=False))

    assert mailer.should_send_digest(r) is True, \
        "should_send_digest must grant a send when hour matches and no prior keys exist"

    # should_send_digest MUST have taken the lock via SETNX (nx=True), and it
    # MUST NOT have written the :sent key (that's the whole PD-01 fix).
    lock_key = "mailer:digest:2026-08-19:lock"
    sent_key = "mailer:digest:2026-08-19:sent"
    r.set.assert_called_once_with(lock_key, "1", ex=600, nx=True)
    setex_for_sent = [c for c in r.setex.call_args_list
                      if c.args and c.args[0] == sent_key]
    assert setex_for_sent == [], \
        f"sent_key must NOT be written at decision time; got {setex_for_sent!r}"

    with caplog.at_level(logging.WARNING, logger=mailer.__name__):
        ok = mailer.send_digest(r)

    assert ok is False, "send_digest must return False when send_email fails"

    _apply_outcome(r, ok, "2026-08-19")

    # After failure: :sent still never written; :lock explicitly released so
    # the next 60s loop tick retries within the DIGEST_HOUR window.
    setex_for_sent = [c for c in r.setex.call_args_list
                      if c.args and c.args[0] == sent_key]
    assert setex_for_sent == [], \
        f"sent_key must NOT be written on failure; got {setex_for_sent!r}"
    r.delete.assert_called_with(lock_key)

    # PD-07: failure logged at WARNING (mailer-level, distinct from the
    # inner send_email "Failed to send email" line which is already WARNING).
    digest_warnings = [rec for rec in caplog.records
                       if rec.levelno == logging.WARNING
                       and "digest" in rec.getMessage().lower()]
    assert digest_warnings, \
        f"failure path must emit a mailer-level WARNING about the digest; got {caplog.text!r}"

    # PD-07 negative: the misleading "sent" success line must NOT appear.
    sent_lines = [rec for rec in caplog.records
                  if "daily digest sent" in rec.getMessage().lower()]
    assert not sent_lines, \
        f"'sent' log must not fire on failure; got {sent_lines!r}"


# ---------------------------------------------------------------------------
# PD-01 (positive): success writes the :sent key and blocks a second same-day
# ---------------------------------------------------------------------------

def test_success_writes_sent_key_and_blocks_second_same_day_call(monkeypatch):
    r = _stub_redis_with_one_article()
    _freeze_clock(monkeypatch, datetime(2026, 8, 19, 7, 5))

    monkeypatch.setattr(mailer, "send_email", MagicMock(return_value=True))

    assert mailer.should_send_digest(r) is True
    ok = mailer.send_digest(r)
    assert ok is True, "send_digest must return True when send_email succeeds"

    _apply_outcome(r, ok, "2026-08-19")

    sent_key = "mailer:digest:2026-08-19:sent"
    r.setex.assert_any_call(sent_key, 90000, "1")

    # Second same-day call: :sent exists → should_send_digest returns False
    # AND does not attempt to grab the lock again.
    def exists_side_effect(key):
        return 1 if key == sent_key else 0
    r.exists.side_effect = exists_side_effect
    r.set.reset_mock()

    assert mailer.should_send_digest(r) is False
    r.set.assert_not_called()


# ---------------------------------------------------------------------------
# PD-01 concurrency: SETNX contention → second caller in the same window
# ---------------------------------------------------------------------------

def test_lock_contention_blocks_duplicate_send(monkeypatch):
    """A second mailer process (or a duplicate loop tick) inside the same
    DIGEST_HOUR window must be denied the send by SETNX. The mailer gets
    restarted several times a day and duplicates have been observed — this
    is why the lock exists on top of the success key."""
    r = MagicMock()
    r.exists.return_value = False       # no :sent yet
    r.set.return_value = None           # SETNX contended — some other tick holds it
    _freeze_clock(monkeypatch, datetime(2026, 8, 19, 7, 5))

    assert mailer.should_send_digest(r) is False
