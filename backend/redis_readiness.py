"""Shared Redis readiness gate for boot-time consumers.

Why this exists
---------------
`redis-server.service` reports "started" to systemd the moment its process
forks — *before* it finishes replaying its AOF/RDB into memory. Any
`After=redis-server.service` consumer that connects and issues a command
during that load window gets `BusyLoadingError "Redis is loading the
dataset in memory"`, and until 2026-08-27 no backend daemon in either arc
or hunt caught it. Sampled that day's boot: Hunt logged five Redis-loading
errors from sync_intel's boot-adjacent cron fire, Arc logged a
Solr-connect failure of the same shape (systemd said Solr was started,
Solr wasn't ready). Neither crashed anything — both degraded quietly.
That's the same failure mode as the counter-analyst fallback: designed to
survive, so nobody notices it's been the normal case.

Correct systemd `After=` ordering is *necessary but not sufficient* — the
retry is what makes ordering actually protect the consumer.

Usage
-----
Call `wait_for_redis(client)` immediately after constructing a redis
client, before the first real read/write::

    import redis
    from redis_readiness import wait_for_redis
    r = redis.Redis(host=..., port=..., password=..., db=...)
    wait_for_redis(r)  # blocks up to 60s during a boot-adjacent start

On a ready Redis the extra PING returns sub-millisecond, so callers can
gate every startup unconditionally without a runtime cost when Redis is
healthy. The 60s/2s shape is the same proven pattern used by
`sync_intel.sh` on this host.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import redis
from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusyLoadingError,
    ConnectionError as RedisConnErr,
    ExternalAuthProviderError,
    MaxConnectionsError,
)

_log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_INTERVAL_S = 2.0

# Every one of these subclasses ConnectionError in redis-py, so a naive
# `except ConnectionError` catches them — and turns a permanent config
# error into a 60s hang and a re-raise. Uncovered by
# test_react_rate_limit_burst_31 the same day this module was written:
# the test's conftest sets a password-less REDIS_URL against a real
# password-protected Redis, main.py's readiness gate caught the NOAUTH
# reply as retriable, and the test import blocked for 60s before failing
# in a way that also corrupted the limiter storage swap. Kept as a tuple
# so future subclasses of ConnectionError that name a permanent-config
# failure can be added in one place.
_PERMANENT_CONN_ERRORS: tuple[type[Exception], ...] = (
    AuthenticationError,          # wrong / missing password
    AuthorizationError,           # ACL denies
    ExternalAuthProviderError,    # external auth flow failed
    MaxConnectionsError,          # client-side pool exhausted — not a
                                  # server-loading condition
)


def wait_for_redis(
    client: "redis.Redis",
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    interval_s: float = DEFAULT_INTERVAL_S,
    log: Optional[logging.Logger] = None,
) -> None:
    """Block until `client.ping()` returns.

    Retries on BusyLoadingError (the actual load-window signal) and on
    plain ConnectionError (connection refused / socket timeout while
    redis-server is still starting). Fast-fails on AuthenticationError,
    AuthorizationError, ExternalAuthProviderError, and MaxConnectionsError
    — these mean the client is misconfigured, not that the server is
    loading, and retrying just delays the real error and pollutes the log.

    Raises the last exception if the deadline is reached — the caller
    decides whether to exit, fall back to a degraded mode, or crash-loop
    through systemd. On a Redis that has already finished loading this
    returns after one PING (sub-millisecond).

    Only the first miss is logged at WARNING; a boot-adjacent start would
    otherwise emit up to 30 identical lines. If a slow start finally
    resolves, a single INFO records how long it took.
    """
    log = log or _log
    deadline = time.monotonic() + timeout_s
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            client.ping()
            if attempt > 1:
                log.info(
                    "Redis ready after %.1fs (attempt %d)",
                    time.monotonic() - started, attempt,
                )
            return
        except _PERMANENT_CONN_ERRORS:
            # config problem, not a load-window state — do not swallow
            raise
        except (BusyLoadingError, RedisConnErr) as e:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.error(
                    "Redis not ready after %.0fs (last error: %s)",
                    timeout_s, e,
                )
                raise
            if attempt == 1:
                log.warning(
                    "Redis still loading (%s) — retrying up to %.0fs",
                    e, timeout_s,
                )
            time.sleep(min(interval_s, max(remaining, 0.1)))
