"""Regression: the cloud-breaker treats auth failures (401/403) as TERMINAL
alongside rate-limit (429), so a bad OLLAMA_API_KEY / OLLAMA_CLOUD_HOST auth
does not silently degrade to local on every request forever.

Motivation (2026-08-28): before this, `_trip_cloud_breaker` fired only on
HTTP 429. Hunt's Spectre host had cloud models registered but no Ollama Cloud
credential, so it returned 401 on every escalation attempt — and the breaker
never tripped. `logs/analyzer.log` on Hunt logged 3,717 "Cloud model failed
(status 401)" lines with cloud calls still being attempted between them.

Same failure class as the AuthenticationError-subclassing-ConnectionError bug
in wait_for_redis (2026-08-27): a permanent error being retried as transient.

The membership check is the invariant. If someone later reintroduces
`if resp.status_code == 429 and label == "cloud":` at the callsite, this test
fails at import-time already — the constant is what the callsite reads.
"""
from ollama_utils import _CLOUD_BREAKER_STATUSES


def test_401_and_403_are_terminal_alongside_429():
    for status in (401, 403, 429):
        assert status in _CLOUD_BREAKER_STATUSES, (
            f"HTTP {status} must trip the cloud breaker — see module docstring"
        )


def test_no_transient_statuses_leak_into_the_set():
    # Sanity: statuses that ARE transient (server errors that Ollama's own
    # retry logic handles, or that indicate the model is loading) must not
    # trip a 24h breaker.
    for status in (500, 502, 503, 504, 408):
        assert status not in _CLOUD_BREAKER_STATUSES, (
            f"HTTP {status} is transient — do NOT add it to the breaker set. "
            "The 24h TTL is too long for these; they heal in minutes."
        )
