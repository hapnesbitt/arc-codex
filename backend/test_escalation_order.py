#!/usr/bin/env python3
"""
Verifies the escalation counter ordering invariants (2026-07-08 hardening):

  1. UNREACHABLE cloud host → record_cloud_call is never invoked
     (the weekly cap counter must not consume cap on a dead host —
     the 2026-07-07 incident recorded 2,755 doomed escalations)
  2. REACHABLE cloud host → record_cloud_call runs BEFORE the HTTP attempt
     (record-before-HTTP is deliberate: a mid-flight crash over-counts a
     failed call rather than under-counting a successful one)
  3. record_cloud_call itself: increments + TTL, and WARNs exactly once
     at 90% of WEEKLY_CAP (verified against a scratch key, never the
     production counter)

No network and no model calls — everything at the Ollama boundary is stubbed.

Run:
    cd /home/www/arc_stack/backend && source venv/bin/activate
    python3 test_escalation_order.py
"""
import logging
import sys

import analyzer
import escalation

TEST_ID = "escalation-order-selftest"
TEST_KEY = f"article:{TEST_ID}"

PARTIAL_LOCAL = "<BLUE>Only a blue section, left unterminated"  # T1: 1/3 sections
FULL_CLOUD = (
    "<BLUE>b.</BLUE><RED>r.</RED>"
    "<PURPLE>p. Patterns detected: none</PURPLE>"
)

events: list[str] = []


def fake_local_only(prompt, timeout=900):
    return (PARTIAL_LOCAL, 42.0, "gemma4:e2b")


def fake_cloud_call(prompt, timeout=900, models=None):
    events.append("http")
    return (FULL_CLOUD, 42.0, "gemma4:31b-cloud")


def spy_record(r):
    events.append("record")
    return 9


def run_case(reachable: bool) -> list[str]:
    events.clear()
    analyzer.call_ollama_local_only = fake_local_only
    analyzer.call_ollama_with_fallback = fake_cloud_call
    analyzer.record_cloud_call = spy_record
    analyzer.is_cloud_reachable = lambda: reachable
    analyzer.is_cloud_available = lambda: True
    analyzer.cloud_capacity_available = lambda r: True
    analyzer.publish_analysis = lambda r, aid, mission, text: events.append(f"publish:{mission}")
    analyzer.update_source_stats = lambda *a, **kw: None

    analyzer.r.hset(TEST_KEY, mapping={
        "title": "Escalation order self-test",
        "original_text": "x" * 500,
        "sourceUrl": "https://example.invalid/selftest",
    })
    try:
        analyzer.analyze_article(TEST_ID)
    finally:
        analyzer.r.delete(TEST_KEY)
    return list(events)


def main() -> int:
    failures = []

    # Case 1 — unreachable: no record, no HTTP, local result still publishes
    ev = run_case(reachable=False)
    if "record" in ev or "http" in ev:
        failures.append(f"unreachable case recorded/called cloud: {ev}")
    if "publish:blue" not in ev:
        failures.append(f"unreachable case failed to degrade to local: {ev}")
    print(f"case 1 (unreachable): {ev}")

    # Case 2 — reachable: record strictly before HTTP
    ev = run_case(reachable=True)
    if "record" not in ev or "http" not in ev:
        failures.append(f"reachable case missing record/http: {ev}")
    elif ev.index("record") > ev.index("http"):
        failures.append(f"record did not precede HTTP: {ev}")
    print(f"case 2 (reachable): {ev}")

    # Case 3 — record_cloud_call against a scratch key: incr, TTL, 90% WARN
    scratch = "arc:cloud_calls:weekly:selftest"
    escalation._weekly_key = lambda now=None: scratch
    warn_at = int(escalation.WEEKLY_CAP * 0.9)
    r = analyzer.r
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
    if count != warn_at:
        failures.append(f"counter incr wrong: {count} != {warn_at}")
    if not (0 < ttl <= 8 * 86400):
        failures.append(f"TTL not set: {ttl}")
    ninety = [w for w in warnings if "90%" in w]
    if len(ninety) != 1:
        failures.append(f"expected exactly one 90% warning, got {len(ninety)}: {warnings}")
    if again != warn_at + 1:
        failures.append(f"second incr wrong: {again}")
    print(f"case 3 (counter): count={count} ttl={ttl} warnings={len(ninety)}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
