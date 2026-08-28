"""Regression: scribe:last_cycle TTL must always exceed one full cycle.

Aug 2026 diagnosis: scribe.py wrote the heartbeat key with a hardcoded
SETEX 900 (15 min). Fine when cycle_minutes was in [1..12]; broken the
day the cadence moved past 15 min. At cycle_minutes=97 the key expires
~82 min before the next sweep refreshes it, so the mailer sees
'arc:scribe:last_cycle = (missing)' as the STEADY state, not a fault.

This test asserts the TTL formula strictly exceeds one full cycle at every
cadence Ross has actually run (0 for stress tests, 12 for the old default,
30 for the interim, 97 for current) and at the neighbouring Hunt cadence
(137). The 900s floor is asserted separately so SETEX with TTL=0 never
raises on the stress-test setting.

scribe.py cannot be imported at module load time (module-level threads),
so we extract _liveness_ttl_seconds by AST — a change to the function
signature or body still causes this test to fail with the actual code
under test, not a duplicated formula in the test.
"""
import ast
import pathlib


BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
SCRIBE_SRC = BACKEND_DIR / "scribe.py"


def _extract_ttl_fn():
    tree = ast.parse(SCRIBE_SRC.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_liveness_ttl_seconds":
            mod = ast.Module(body=[node], type_ignores=[])
            code = compile(mod, str(SCRIBE_SRC), "exec")
            ns: dict = {}
            exec(code, ns)
            return ns["_liveness_ttl_seconds"]
    raise AssertionError(
        "_liveness_ttl_seconds not found in scribe.py — heartbeat TTL is back "
        "to being a literal, which is exactly the bug this test guards."
    )


TTL_FN = _extract_ttl_fn()


def test_ttl_strictly_exceeds_one_full_cycle():
    """The would-have-caught-it-on-Aug-1 assertion."""
    for cycle_minutes in (0, 12, 30, 97, 137):
        ttl = TTL_FN(cycle_minutes)
        cycle_s = cycle_minutes * 60
        assert ttl > cycle_s, (
            f"cycle_minutes={cycle_minutes} → TTL={ttl}s is not strictly "
            f"greater than one cycle ({cycle_s}s). The heartbeat key will "
            f"expire before the next sweep can refresh it — same regression "
            f"as 2026-08-28."
        )


def test_ttl_floor_protects_stress_test_setting():
    """cycle_minutes=0 must not translate to SETEX TTL 0 (which raises)."""
    assert TTL_FN(0) >= 900, (
        f"cycle_minutes=0 → TTL={TTL_FN(0)}s; SETEX with TTL 0 raises. "
        f"The floor is load-bearing for the operator's stress tests."
    )


def test_ttl_scales_with_cycle_above_the_floor():
    """Above 7.5 min the formula, not the floor, must govern — otherwise the
    scaling code is dead."""
    small = TTL_FN(8)
    big   = TTL_FN(97)
    assert big > small, (
        f"TTL did not scale with cycle_minutes: 8m→{small}s, 97m→{big}s. "
        f"The formula has regressed to a constant."
    )
