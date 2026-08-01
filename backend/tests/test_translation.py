"""Tests for the translation blueprint's shared predicates and rate limits.

`_cached_only_requested` is called both by the route (to short-circuit
before inference) and by the rate-limiter's `exempt_when` callbacks (to
route the request into the fresh 10/hour bucket or the cached-only
120/hour bucket). If any caller reimplemented the truthy-set logic and
disagreed on a value, a request the route treats as fresh could land in
the 120/hour bucket -- 120 real inferences per hour per IP through a
gate designed to allow zero. The predicate tests pin exactly that.

The rate-limit tests exercise the factory wiring: they burn the fresh
bucket via the fast 400 path (missing lang) since the limiter's
before_request check fires before the view function returns.
"""
import pytest

import main
from translation import _cached_only_requested, translation_bp, apply_rate_limits

# The conftest's Redis env cannot authenticate to the local Redis, so main.py's
# blueprint-registration block never runs. Register the translate blueprint
# and apply the same rate-limit wiring here so the tests exercise the exact
# path the production main.py takes. Missing-lang returns 400 before ever
# touching Redis, which is enough to drive the limiter's before_request check.
if "translation" not in main.app.blueprints:
    main.app.register_blueprint(translation_bp)
    apply_rate_limits(main.app, main.limiter)


TRUTHY = ["1", "true", "yes", "on", "TRUE", "Yes", " 1 ", "  true  "]
FALSY = ["0", "false", "no", "off", "", " ", "maybe", "true1", "y", "yeah", "2"]


def _reset_limiter():
    try:
        main.limiter.reset()
    except Exception:
        pass


@pytest.mark.parametrize("value", TRUTHY)
def test_cached_only_truthy(app, value):
    with app.test_request_context(f"/?cached_only={value}"):
        assert _cached_only_requested() is True, f"{value!r} should be truthy"


@pytest.mark.parametrize("value", FALSY)
def test_cached_only_falsy(app, value):
    with app.test_request_context(f"/?cached_only={value}"):
        assert _cached_only_requested() is False, f"{value!r} should be falsy"


def test_cached_only_missing_param_is_falsy(app):
    with app.test_request_context("/"):
        assert _cached_only_requested() is False


def test_fresh_bucket_11th_is_429(client):
    _reset_limiter()
    codes = [client.get("/api/translate/x").status_code for _ in range(11)]
    assert codes[:10] == [400] * 10, f"unexpected pre-limit statuses: {codes[:10]}"
    assert codes[10] == 429, f"expected 429 on 11th fresh; got {codes[10]}"


def test_cached_bucket_is_independent_from_fresh(client):
    _reset_limiter()
    for _ in range(11):
        client.get("/api/translate/x")
    resp = client.get("/api/translate/x?cached_only=1")
    assert resp.status_code != 429, (
        f"cached_only bucket collapsed into fresh; got {resp.status_code}"
    )


def test_cached_bucket_121st_is_429(client):
    _reset_limiter()
    codes = [client.get("/api/translate/x?cached_only=1").status_code for _ in range(121)]
    assert codes[120] == 429, f"expected 429 on 121st cached_only; got {codes[120]}"


def test_429_json_body_and_retry_after_header(client):
    _reset_limiter()
    for _ in range(10):
        client.get("/api/translate/x")
    resp = client.get("/api/translate/x")
    assert resp.status_code == 429
    body = resp.get_json()
    assert body["error"] == "rate_limited"
    assert body["detail"], "expected non-empty detail message"
    assert isinstance(body["retry_after"], int) and body["retry_after"] >= 1
    header = resp.headers.get("Retry-After")
    assert header is not None, "Retry-After header missing"
    header_int = int(header)  # RFC 7231 allows delta-seconds; our config emits int
    # Handler sets header from the window duration, Flask-Limiter's
    # after_request __inject_headers overlays its own precise reset_at
    # diff. Small clock skew between the two reads is expected; the
    # invariant is both agree within a few seconds, not to the millisecond.
    assert abs(header_int - body["retry_after"]) <= 5, (
        f"header {header_int} and body retry_after {body['retry_after']} "
        f"diverged more than 5s -- limit window mismatch, not clock skew"
    )
    assert 1 <= header_int <= 3600, f"header {header_int} outside 1..3600s (10/hour window)"
