"""Coverage for redis_readiness.wait_for_redis.

The regression these guard against: AuthenticationError inherits from
ConnectionError in redis-py, so a naive `except ConnectionError` catches
it — turning a permanent-config error into a 60s hang and a re-raise.
Uncovered by test_react_rate_limit_burst_31 the same day the module was
written; it took the rate-limit test's fake-Redis URL against real
password-protected Redis to surface it.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusyLoadingError,
    ConnectionError as RedisConnErr,
    ExternalAuthProviderError,
    MaxConnectionsError,
)

from redis_readiness import wait_for_redis


def _client_that_raises(*exc_sequence):
    """MagicMock client whose ping() raises each exc in turn, then returns."""
    it = iter(exc_sequence)

    def side_effect():
        try:
            raise next(it)
        except StopIteration:
            return True

    client = MagicMock()
    client.ping.side_effect = side_effect
    return client


def test_ready_redis_returns_after_one_ping():
    client = MagicMock()
    client.ping.return_value = True
    wait_for_redis(client, timeout_s=1, interval_s=0.01)
    assert client.ping.call_count == 1


def test_busy_loading_error_is_retried_until_success():
    client = _client_that_raises(
        BusyLoadingError("Redis is loading the dataset in memory"),
        BusyLoadingError("Redis is loading the dataset in memory"),
    )
    t = time.monotonic()
    wait_for_redis(client, timeout_s=5, interval_s=0.05)
    assert time.monotonic() - t < 5
    assert client.ping.call_count == 3  # 2 loading + 1 success


def test_plain_connection_error_is_retried():
    client = _client_that_raises(
        RedisConnErr("Error 111 connecting to 127.0.0.1:6379. Connection refused."),
    )
    wait_for_redis(client, timeout_s=5, interval_s=0.05)
    assert client.ping.call_count == 2


@pytest.mark.parametrize("exc_cls,msg", [
    (AuthenticationError, "Authentication required."),
    (AuthorizationError, "no permission"),
    (ExternalAuthProviderError, "external auth failed"),
    (MaxConnectionsError, "Too many connections"),
])
def test_permanent_conn_errors_fast_fail(exc_cls, msg):
    """AUTH / permission / pool errors are misconfig — never retry.

    Left unchecked these subclass ConnectionError and would wait the full
    timeout; test_react_rate_limit_burst_31 in test_smoke.py hit exactly
    that pattern before this coverage existed.
    """
    client = MagicMock()
    client.ping.side_effect = exc_cls(msg)
    t = time.monotonic()
    with pytest.raises(exc_cls):
        wait_for_redis(client, timeout_s=10, interval_s=0.05)
    assert time.monotonic() - t < 1, "permanent error should not consume timeout"
    assert client.ping.call_count == 1


def test_deadline_reraises_last_exception():
    client = MagicMock()
    client.ping.side_effect = BusyLoadingError("still loading")
    with pytest.raises(BusyLoadingError):
        wait_for_redis(client, timeout_s=0.2, interval_s=0.05)
    assert client.ping.call_count >= 2
