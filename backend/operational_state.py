"""Bounded operational-state contracts for Arc workers and exporters.

P0-A uses :class:`ExporterHealthState`; P0-B adds the bounded Scribe writer;
P0-C adds analyzer lifecycle and occurrence-preserving queue tracking.
"""

from __future__ import annotations

import threading
import time
import hashlib
import math
from dataclasses import dataclass


OPS_PREFIX = "arc:ops"

# Fixed operational names prevent ad-hoc key construction and label growth.
SCRIBE_HEARTBEAT_KEY = f"{OPS_PREFIX}:scribe:heartbeat"
SCRIBE_STATE_KEY = f"{OPS_PREFIX}:scribe:state"
SCRIBE_COUNTERS_KEY = f"{OPS_PREFIX}:scribe:counters"
ANALYZER_HEARTBEAT_KEY = f"{OPS_PREFIX}:analyzer:heartbeat"
ANALYZER_STATE_KEY = f"{OPS_PREFIX}:analyzer:state"
ANALYZER_COUNTERS_KEY = f"{OPS_PREFIX}:analyzer:counters"
ANALYZER_DURATION_KEY = f"{OPS_PREFIX}:analyzer:duration"
ANALYZER_QUEUE_TIMELINE_KEY = f"{OPS_PREFIX}:analyzer:queue:timeline"
ANALYZER_QUEUE_TRACKING_KEY = f"{OPS_PREFIX}:analyzer:queue:tracking_valid"
ANALYZER_ACTIVE_KEY = f"{OPS_PREFIX}:analyzer:active"

ANALYZER_QUEUE_KEY = "analyzer:queue"
ANALYZER_TRACKING_VERSION = "arc-analyzer-timeline-v1"
ANALYZER_TRACKING_LIMIT = 10_000
ANALYZER_ACTIVE_LIMIT = 1_000
ANALYZER_JOB_OUTCOMES = frozenset({"completed", "failed", "skipped"})
ANALYZER_FAILURE_STAGES = frozenset(
    {"missing_article", "invalid_text", "oversize", "inference", "publish",
     "redis", "malformed_payload", "unexpected"}
)
ANALYZER_DURATION_BUCKETS = (5, 15, 30, 60, 120, 300, 600, 900)

HEARTBEAT_TTL_SECONDS = 180
HEARTBEAT_REFRESH_SECONDS = 30
STATE_TTL_SECONDS = 7 * 24 * 60 * 60

WORKER_STATES = frozenset({"starting", "idle", "active", "failed"})
SCRIBE_POLL_RESULTS = frozenset({"success", "malformed", "error"})
SCRIBE_ERROR_STAGES = frozenset(
    {
        "redis",
        "priority",
        "source_poll",
        "fetch",
        "pre_analyze",
        "publish",
        "retention",
        "main_loop",
    }
)
SCRIBE_COUNTER_FIELDS = frozenset(
    {
        "poll_success",
        "poll_malformed",
        "poll_error",
        "articles_discovered",
        "articles_new",
        "articles_duplicate",
        "articles_rejected",
        "articles_skipped",
        *(f"errors_{stage}" for stage in SCRIBE_ERROR_STAGES),
    }
)
EXPORTER_SCAN_RESULTS = frozenset({"success", "failure"})
EXPORTER_ERROR_STAGES = frozenset(
    {
        "redis_scan",
        "pipeline_stats",
        "publish_timestamp",
        "operational_state",
        "fast_state",
    }
)

# The real queue push is deliberately first and unprotected. Every sidecar
# command is protected so a WRONGTYPE or other instrumentation error cannot
# undo or prevent the queue occurrence. Redis does not roll back earlier Lua
# writes on a later protected-call failure.
ANALYZER_ENQUEUE_LUA = r"""
local direction = ARGV[1]
local payload = ARGV[2]
local timeline_record = ARGV[3]
local version = ARGV[4]
local limit = tonumber(ARGV[5])
local depth
if direction == 'left' then
  depth = redis.call('LPUSH', KEYS[1], payload)
else
  depth = redis.call('RPUSH', KEYS[1], payload)
end
local status = 0
if redis.call('GET', KEYS[3]) == version then
  if depth <= limit then
    local result
    if direction == 'left' then
      result = redis.pcall('LPUSH', KEYS[2], timeline_record)
    else
      result = redis.pcall('RPUSH', KEYS[2], timeline_record)
    end
    if type(result) == 'table' and result.err then
      redis.pcall('DEL', KEYS[3])
      redis.pcall('DEL', KEYS[2])
      status = -1
    else
      status = 1
    end
  else
    redis.pcall('DEL', KEYS[3])
    redis.pcall('DEL', KEYS[2])
    status = -2
  end
else
  redis.pcall('DEL', KEYS[2])
end
return {depth, status}
"""

ANALYZER_REINITIALIZE_LUA = r"""
if redis.call('LLEN', KEYS[1]) ~= 0 then return 0 end
redis.call('DEL', KEYS[2])
redis.call('SET', KEYS[3], ARGV[1])
return 1
"""

ANALYZER_DEQUEUE_LUA = r"""
if redis.call('GET', KEYS[2]) ~= ARGV[1] then return false end
local record = redis.pcall('RPOP', KEYS[1])
if type(record) == 'table' and record.err then
  redis.pcall('DEL', KEYS[2])
  redis.pcall('DEL', KEYS[1])
  return false
end
return record
"""


def require_allowed(value: str, allowed: frozenset[str], field: str) -> str:
    """Reject arbitrary values before they can become metric labels."""
    if value not in allowed:
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def analyzer_timeline_record(article_id: str, timestamp: float) -> str:
    """Return the privacy-safe, occurrence-preserving timeline record."""
    if not isinstance(article_id, str) or not article_id:
        raise ValueError("article ID must be a non-empty string")
    timestamp = float(timestamp)
    if timestamp <= 0 or not math.isfinite(timestamp):
        raise ValueError("enqueue timestamp must be finite and positive")
    digest = hashlib.sha256(article_id.encode("utf-8")).hexdigest()
    return f"{digest}|{timestamp:.6f}"


def invalidate_analyzer_queue_tracking(redis_client) -> bool:
    try:
        redis_client.delete(ANALYZER_QUEUE_TRACKING_KEY, ANALYZER_QUEUE_TIMELINE_KEY)
        return True
    except Exception:
        return False


def reinitialize_analyzer_queue_tracking(redis_client) -> bool:
    """Atomically initialize tracking only while the real queue is empty."""
    try:
        return bool(redis_client.eval(
            ANALYZER_REINITIALIZE_LUA, 3, ANALYZER_QUEUE_KEY,
            ANALYZER_QUEUE_TIMELINE_KEY, ANALYZER_QUEUE_TRACKING_KEY,
            ANALYZER_TRACKING_VERSION,
        ))
    except Exception:
        return False


def enqueue_analysis(redis_client, article_id: str, direction: str, now=None):
    """Push one unchanged queue payload and atomically mirror its occurrence.

    The caller retains the existing SET-NX dedup decision. A connection error
    has the same ambiguity as the historical direct list push; tracking is
    invalidated best-effort and the exception is re-raised to the existing
    non-fatal caller path.
    """
    require_allowed(direction, frozenset({"left", "right"}), "queue direction")
    timestamp = float(time.time() if now is None else now)
    record = analyzer_timeline_record(article_id, timestamp)
    reinitialize_analyzer_queue_tracking(redis_client)
    try:
        depth, status = redis_client.eval(
            ANALYZER_ENQUEUE_LUA, 3, ANALYZER_QUEUE_KEY,
            ANALYZER_QUEUE_TIMELINE_KEY, ANALYZER_QUEUE_TRACKING_KEY,
            direction, article_id, record, ANALYZER_TRACKING_VERSION,
            ANALYZER_TRACKING_LIMIT,
        )
        return int(depth), int(status)
    except Exception:
        invalidate_analyzer_queue_tracking(redis_client)
        raise


def reconcile_analyzer_dequeue(redis_client, article_id: str) -> bool:
    """Reconcile one BRPOP occurrence; any ambiguity fails tracking closed."""
    expected = analyzer_timeline_record(article_id, 1).split("|", 1)[0]
    try:
        record = redis_client.eval(
            ANALYZER_DEQUEUE_LUA, 2, ANALYZER_QUEUE_TIMELINE_KEY,
            ANALYZER_QUEUE_TRACKING_KEY, ANALYZER_TRACKING_VERSION,
        )
        if not record or not isinstance(record, str):
            invalidate_analyzer_queue_tracking(redis_client)
            return False
        digest, separator, timestamp = record.partition("|")
        parsed = float(timestamp) if separator else float("nan")
        if digest != expected or len(digest) != 64 or parsed <= 0 or not math.isfinite(parsed):
            invalidate_analyzer_queue_tracking(redis_client)
            return False
        return True
    except Exception:
        invalidate_analyzer_queue_tracking(redis_client)
        return False
    finally:
        reinitialize_analyzer_queue_tracking(redis_client)


class ScribeOperationalState:
    """Best-effort, bounded Scribe state writer.

    Instrumentation must never interrupt ingestion. Every Redis operation is
    therefore contained here and returns False on failure. Values are fixed
    status/stage names, timestamps, and integers only.
    """

    def __init__(self, redis_client, logger=None, clock=time.time) -> None:
        self._redis = redis_client
        self._logger = logger
        self._clock = clock
        self._last_warning = 0.0

    def _warn(self, operation: str) -> None:
        now = self._clock()
        if self._logger is not None and now - self._last_warning >= 300:
            self._logger.warning("Scribe operational-state write failed during %s", operation)
            self._last_warning = now

    def _safe(self, operation: str, callback) -> bool:
        try:
            callback()
            return True
        except Exception:
            self._warn(operation)
            return False

    def heartbeat(self, now: float | None = None) -> bool:
        timestamp = int(now if now is not None else self._clock())
        return self._safe(
            "heartbeat",
            lambda: self._redis.setex(SCRIBE_HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, timestamp),
        )

    def set_status(self, status: str, now: float | None = None) -> bool:
        require_allowed(status, WORKER_STATES, "worker state")
        timestamp = int(now if now is not None else self._clock())

        def write():
            pipe = self._redis.pipeline()
            pipe.hset(SCRIBE_STATE_KEY, mapping={"status": status, "status_since": timestamp})
            pipe.expire(SCRIBE_STATE_KEY, STATE_TTL_SECONDS)
            pipe.execute()

        return self._safe("status", write)

    def mark_poll_attempt(self, now: float | None = None) -> bool:
        timestamp = int(now if now is not None else self._clock())

        def write():
            pipe = self._redis.pipeline()
            pipe.hset(SCRIBE_STATE_KEY, "last_poll", timestamp)
            pipe.expire(SCRIBE_STATE_KEY, STATE_TTL_SECONDS)
            pipe.execute()

        return self._safe("poll timestamp", write)

    def mark_success(self, now: float | None = None) -> bool:
        timestamp = int(now if now is not None else self._clock())

        def write():
            pipe = self._redis.pipeline()
            pipe.hset(
                SCRIBE_STATE_KEY,
                mapping={
                    "status": "idle",
                    "status_since": timestamp,
                    "last_success": timestamp,
                    "last_error_stage": "",
                },
            )
            pipe.expire(SCRIBE_STATE_KEY, STATE_TTL_SECONDS)
            pipe.execute()

        return self._safe("cycle success", write)

    def mark_failure(self, stage: str, now: float | None = None) -> bool:
        require_allowed(stage, SCRIBE_ERROR_STAGES, "scribe error stage")
        timestamp = int(now if now is not None else self._clock())

        def write():
            pipe = self._redis.pipeline()
            pipe.hset(
                SCRIBE_STATE_KEY,
                mapping={
                    "status": "failed",
                    "status_since": timestamp,
                    "last_failure": timestamp,
                    "last_error_stage": stage,
                },
            )
            pipe.expire(SCRIBE_STATE_KEY, STATE_TTL_SECONDS)
            pipe.hincrby(SCRIBE_COUNTERS_KEY, f"errors_{stage}", 1)
            pipe.execute()

        return self._safe("failure", write)

    def increment(self, field: str, amount: int = 1) -> bool:
        require_allowed(field, SCRIBE_COUNTER_FIELDS, "scribe counter field")
        if not isinstance(amount, int) or amount < 0:
            raise ValueError("counter increment must be a non-negative integer")
        return self._safe(
            "counter",
            lambda: self._redis.hincrby(SCRIBE_COUNTERS_KEY, field, amount),
        )

    def record_poll(self, result: str) -> bool:
        require_allowed(result, SCRIBE_POLL_RESULTS, "scribe poll result")
        return self.increment(f"poll_{result}")


def run_heartbeat_loop(state: ScribeOperationalState, stop_event=None) -> None:
    """Refresh a heartbeat until stopped; intended for a daemon thread."""
    stopper = stop_event or threading.Event()
    while not stopper.is_set():
        state.heartbeat()
        stopper.wait(HEARTBEAT_REFRESH_SECONDS)


class AnalyzerOperationalState:
    """Best-effort analyzer lifecycle and persistent histogram writer."""

    def __init__(self, redis_client, logger=None, clock=time.time) -> None:
        self._redis = redis_client
        self._logger = logger
        self._clock = clock
        self._last_warning = 0.0

    def _safe(self, operation, callback):
        try:
            callback()
            return True
        except Exception:
            now = self._clock()
            if self._logger is not None and now - self._last_warning >= 300:
                self._logger.warning("Analyzer operational-state write failed during %s", operation)
                self._last_warning = now
            return False

    def heartbeat(self, now=None):
        timestamp = int(self._clock() if now is None else now)
        return self._safe("heartbeat", lambda: self._redis.setex(
            ANALYZER_HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, timestamp))

    def set_status(self, status, now=None):
        require_allowed(status, WORKER_STATES, "worker state")
        timestamp = int(self._clock() if now is None else now)

        def write():
            pipe = self._redis.pipeline()
            pipe.hset(ANALYZER_STATE_KEY, mapping={"status": status, "status_since": timestamp})
            pipe.expire(ANALYZER_STATE_KEY, STATE_TTL_SECONDS)
            pipe.execute()
        return self._safe("status", write)

    def start_job(self, article_id, now=None):
        timestamp = float(self._clock() if now is None else now)

        def write():
            pipe = self._redis.pipeline()
            pipe.hset(ANALYZER_STATE_KEY, mapping={
                "status": "active", "status_since": timestamp, "last_started": timestamp})
            pipe.expire(ANALYZER_STATE_KEY, STATE_TTL_SECONDS)
            pipe.zadd(ANALYZER_ACTIVE_KEY, {article_id: timestamp})
            pipe.zremrangebyrank(ANALYZER_ACTIVE_KEY, 0, -(ANALYZER_ACTIVE_LIMIT + 1))
            pipe.expire(ANALYZER_ACTIVE_KEY, STATE_TTL_SECONDS)
            pipe.execute()
        return self._safe("job start", write)

    def finish_job(self, article_id, outcome, duration_seconds, stage=None, now=None):
        require_allowed(outcome, ANALYZER_JOB_OUTCOMES, "analyzer outcome")
        if stage is not None:
            require_allowed(stage, ANALYZER_FAILURE_STAGES, "analyzer failure stage")
        duration = float(duration_seconds)
        if duration < 0 or not math.isfinite(duration):
            raise ValueError("duration must be finite and non-negative")
        timestamp = float(self._clock() if now is None else now)

        def write():
            fields = {"status": "idle", "status_since": timestamp}
            fields["last_failure" if outcome == "failed" else "last_success"] = timestamp
            fields["last_error_stage"] = stage or ""
            pipe = self._redis.pipeline()
            pipe.hset(ANALYZER_STATE_KEY, mapping=fields)
            pipe.expire(ANALYZER_STATE_KEY, STATE_TTL_SECONDS)
            pipe.hincrby(ANALYZER_COUNTERS_KEY, f"jobs_{outcome}", 1)
            if stage:
                pipe.hincrby(ANALYZER_COUNTERS_KEY, f"failures_{stage}", 1)
            for bound in ANALYZER_DURATION_BUCKETS:
                if duration <= bound:
                    pipe.hincrby(ANALYZER_DURATION_KEY, f"bucket_{bound}", 1)
            pipe.hincrby(ANALYZER_DURATION_KEY, "bucket_inf", 1)
            pipe.hincrby(ANALYZER_DURATION_KEY, "count", 1)
            pipe.hincrbyfloat(ANALYZER_DURATION_KEY, "sum", duration)
            pipe.zrem(ANALYZER_ACTIVE_KEY, article_id)
            pipe.execute()
        return self._safe("job finish", write)


def run_analyzer_heartbeat_loop(state: AnalyzerOperationalState, stop_event=None) -> None:
    stopper = stop_event or threading.Event()
    while not stopper.is_set():
        state.heartbeat()
        stopper.wait(HEARTBEAT_REFRESH_SECONDS)


@dataclass(frozen=True)
class ExporterHealthSnapshot:
    ready: bool
    stale: bool
    scan_in_progress: bool
    last_scan_success: bool
    last_scan_timestamp: float
    last_scan_attempt_timestamp: float
    last_fast_state_timestamp: float


class ExporterHealthState:
    """Thread-safe readiness state shared by the hourly and fast loops.

    Scrapeability is intentionally outside this state: Prometheus ``up``
    reports whether the HTTP endpoint responds. ``ready`` instead requires a
    fully successful scan plus a recent successful fast-state read.
    """

    def __init__(
        self,
        *,
        stale_after_seconds: float,
        fast_state_ttl_seconds: float = HEARTBEAT_TTL_SECONDS,
        requires_fast_state: bool = True,
        clock=time.time,
    ) -> None:
        if stale_after_seconds <= 0 or fast_state_ttl_seconds <= 0:
            raise ValueError("health timeouts must be positive")
        self._stale_after = float(stale_after_seconds)
        self._fast_state_ttl = float(fast_state_ttl_seconds)
        # On stacks that don't run the fast loop (cross_stack_operational=false,
        # e.g. Huntaegis) there is no fast-state read, so readiness must not
        # require one — otherwise the exporter reports itself perpetually
        # not-ready despite healthy scans.
        self._requires_fast_state = bool(requires_fast_state)
        self._clock = clock
        self._lock = threading.Lock()
        self._scan_in_progress = False
        self._last_scan_success = False
        self._last_scan_timestamp = 0.0
        self._last_scan_attempt_timestamp = 0.0
        self._last_fast_state_timestamp = 0.0

    def begin_scan(self, now: float | None = None) -> None:
        with self._lock:
            self._scan_in_progress = True
            self._last_scan_attempt_timestamp = float(now if now is not None else self._clock())

    def finish_scan(self, success: bool, now: float | None = None) -> None:
        finished = float(now if now is not None else self._clock())
        with self._lock:
            self._scan_in_progress = False
            self._last_scan_attempt_timestamp = finished
            self._last_scan_success = bool(success)
            if success:
                self._last_scan_timestamp = finished

    def mark_fast_state_success(self, now: float | None = None) -> None:
        with self._lock:
            self._last_fast_state_timestamp = float(now if now is not None else self._clock())

    def mark_fast_state_failure(self) -> None:
        # An explicit failure invalidates an earlier good fast-state read.
        with self._lock:
            self._last_fast_state_timestamp = 0.0

    def snapshot(self, now: float | None = None) -> ExporterHealthSnapshot:
        current = float(now if now is not None else self._clock())
        with self._lock:
            scan_ts = self._last_scan_timestamp
            fast_ts = self._last_fast_state_timestamp
            stale = not scan_ts or current - scan_ts > self._stale_after
            fast_fresh = bool(fast_ts) and current - fast_ts <= self._fast_state_ttl
            fast_ok = fast_fresh if self._requires_fast_state else True
            ready = self._last_scan_success and not stale and fast_ok
            return ExporterHealthSnapshot(
                ready=bool(ready),
                stale=bool(stale),
                scan_in_progress=self._scan_in_progress,
                last_scan_success=self._last_scan_success,
                last_scan_timestamp=scan_ts,
                last_scan_attempt_timestamp=self._last_scan_attempt_timestamp,
                last_fast_state_timestamp=fast_ts,
            )
