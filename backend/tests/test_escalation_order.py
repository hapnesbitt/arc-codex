"""Regression guard for the escalation counter ordering invariants (2026-07-08
hardening). Converted 2026-08-21 from the standalone
manual_test_escalation_order.py (itself a 2026-07-11 rename of
test_escalation_order.py -- see ops/RUNBOOK.md's Wave B-proper entry): it was
renamed OUT of pytest's test_*.py collection specifically because it dials
prod Redis via analyzer.r and "cannot run in a GH-Actions runner," which
provisions none.

That's still true here -- this file is NOT stubbed at the Redis boundary,
only at the Ollama one, same as the original.

Two things make this safe to auto-collect where the original wasn't:

1. analyzer.py does NOT leave `r = None` on a bad connection the way it
   looks like it might from a skim -- it catches ConnectionError and calls
   `sys.exit(1)`. A bare `import analyzer` in an environment with no Redis
   (CI provisions none) kills the whole pytest process with an
   INTERNALERROR, not a clean per-test failure. So the import itself is
   wrapped below, catching SystemExit and skipping the whole module
   (`pytest.skip(..., allow_module_level=True)`) before any test is
   collected, regardless of *why* the connection failed.
2. conftest.py deliberately blanks REDIS_PASSWORD (empty string) so
   main.py's rate limiter sees an unreachable Redis and falls back to
   in-memory -- correct for that test, but it also poisons analyzer.py's
   *real* connection attempt, since nothing had imported analyzer in this
   suite before this file existed. The real password is read from .env and
   restored just long enough to import analyzer + escalation, then put
   back exactly as conftest left it, so later test modules (test_smoke.py)
   see the same blanked environment they were written against. Skips (not
   silently mis-passes) if .env isn't present, e.g. in CI.

  1. UNREACHABLE cloud host -> record_cloud_call is never invoked (the weekly
     cap counter must not consume cap on a dead host -- the 2026-07-07
     incident recorded 2,755 doomed escalations)
  2. REACHABLE cloud host -> record_cloud_call runs BEFORE the HTTP attempt
     (record-before-HTTP is deliberate: a mid-flight crash over-counts a
     failed call rather than under-counting a successful one)
  3. record_cloud_call itself: increments + TTL, and WARNs exactly once at
     90% of WEEKLY_CAP (verified against a scratch key, never the production
     counter)
"""
import logging
import os

import pytest
from dotenv import dotenv_values

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
_real_password = dotenv_values(_ENV_PATH).get("REDIS_PASSWORD")
if not _real_password:
    pytest.skip(f"no REDIS_PASSWORD in {_ENV_PATH} -- can't test a real Redis connection",
                allow_module_level=True)

_saved_password = os.environ.get("REDIS_PASSWORD")
os.environ["REDIS_PASSWORD"] = _real_password
try:
    import analyzer
    import escalation
except SystemExit:
    pytest.skip("analyzer.py exits at import time when Redis is unreachable "
                "(sys.exit(1) on ConnectionError, not a clean None) -- see docstring",
                allow_module_level=True)
finally:
    if _saved_password is None:
        os.environ.pop("REDIS_PASSWORD", None)
    else:
        os.environ["REDIS_PASSWORD"] = _saved_password

TEST_ID = "escalation-order-selftest"
TEST_KEY = f"article:{TEST_ID}"

PARTIAL_LOCAL = "<BLUE>Only a blue section, left unterminated"  # 1/3 sections
FULL_CLOUD = (
    "<BLUE>b.</BLUE><RED>r.</RED>"
    "<PURPLE>p. Patterns detected: none</PURPLE>"
)


def _fake_local_only(prompt, timeout=900):
    return (PARTIAL_LOCAL, 42.0, "gemma4:e2b")


def _run_case(monkeypatch, reachable: bool) -> list[str]:
    events: list[str] = []

    def fake_cloud_call(prompt, timeout=900, models=None):
        events.append("http")
        return (FULL_CLOUD, 42.0, "gemma4:31b-cloud")

    def spy_record(r):
        events.append("record")
        return 9

    monkeypatch.setattr(analyzer, "call_ollama_local_only", _fake_local_only)
    monkeypatch.setattr(analyzer, "call_ollama_with_fallback", fake_cloud_call)
    monkeypatch.setattr(analyzer, "record_cloud_call", spy_record)
    monkeypatch.setattr(analyzer, "is_cloud_reachable", lambda: reachable)
    monkeypatch.setattr(analyzer, "is_cloud_available", lambda: True)
    monkeypatch.setattr(analyzer, "cloud_capacity_available", lambda r: True)
    monkeypatch.setattr(analyzer, "publish_analysis",
                         lambda r, aid, mission, text: events.append(f"publish:{mission}"))
    monkeypatch.setattr(analyzer, "update_source_stats", lambda *a, **kw: None)

    analyzer.r.hset(TEST_KEY, mapping={
        "title": "Escalation order self-test",
        "original_text": "x" * 500,
        "sourceUrl": "https://example.invalid/selftest",
    })
    try:
        analyzer.analyze_article(TEST_ID)
    finally:
        analyzer.r.delete(TEST_KEY)
    return events


def test_unreachable_cloud_skips_record_and_http_but_still_publishes(monkeypatch):
    ev = _run_case(monkeypatch, reachable=False)
    assert "record" not in ev, f"unreachable case recorded cloud usage: {ev}"
    assert "http" not in ev, f"unreachable case called cloud HTTP: {ev}"
    assert "publish:blue" in ev, f"unreachable case failed to degrade to local: {ev}"


def test_reachable_cloud_records_before_http(monkeypatch):
    ev = _run_case(monkeypatch, reachable=True)
    assert "record" in ev and "http" in ev, f"reachable case missing record/http: {ev}"
    assert ev.index("record") < ev.index("http"), f"record did not precede HTTP: {ev}"


def test_record_cloud_call_increments_ttls_and_warns_once_at_90_percent(monkeypatch):
    scratch = "arc:cloud_calls:weekly:selftest"
    r = analyzer.r
    monkeypatch.setattr(escalation, "_weekly_key", lambda now=None: scratch)
    warn_at = int(escalation.WEEKLY_CAP * 0.9)
    r.set(scratch, warn_at - 1)

    warnings = []
    handler = logging.Handler()
    handler.emit = lambda rec: warnings.append(rec.getMessage())
    escalation.logger.addHandler(handler)
    try:
        count = escalation.record_cloud_call(r)
        ttl = r.ttl(scratch)
        again = escalation.record_cloud_call(r)
    finally:
        escalation.logger.removeHandler(handler)
        r.delete(scratch)

    assert count == warn_at, f"counter incr wrong: {count} != {warn_at}"
    assert 0 < ttl <= 8 * 86400, f"TTL not set: {ttl}"
    ninety = [w for w in warnings if "90%" in w]
    assert len(ninety) == 1, f"expected exactly one 90% warning, got {len(ninety)}: {warnings}"
    assert again == warn_at + 1, f"second incr wrong: {again}"
