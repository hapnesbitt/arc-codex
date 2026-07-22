"""P0-A through P0-C Arc Intelligence instrumentation tests."""

import pathlib
import sys
import math
import os
import subprocess
import tempfile
import time

import pytest
import redis as redis_lib
from prometheus_client import generate_latest


BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import corpus_exporter as exporter  # noqa: E402
from operational_state import (  # noqa: E402
    ANALYZER_ACTIVE_KEY,
    ANALYZER_COUNTERS_KEY,
    ANALYZER_DEQUEUE_LUA,
    ANALYZER_DURATION_KEY,
    ANALYZER_ENQUEUE_LUA,
    ANALYZER_HEARTBEAT_KEY,
    ANALYZER_QUEUE_KEY,
    ANALYZER_QUEUE_TIMELINE_KEY,
    ANALYZER_QUEUE_TRACKING_KEY,
    ANALYZER_REINITIALIZE_LUA,
    ANALYZER_STATE_KEY,
    ANALYZER_TRACKING_LIMIT,
    ANALYZER_TRACKING_VERSION,
    AnalyzerOperationalState,
    EXPORTER_ERROR_STAGES,
    EXPORTER_SCAN_RESULTS,
    OPS_PREFIX,
    SCRIBE_COUNTERS_KEY,
    SCRIBE_HEARTBEAT_KEY,
    SCRIBE_STATE_KEY,
    HEARTBEAT_TTL_SECONDS,
    STATE_TTL_SECONDS,
    ExporterHealthState,
    ScribeOperationalState,
    analyzer_timeline_record,
    enqueue_analysis,
    reconcile_analyzer_dequeue,
    reinitialize_analyzer_queue_tracking,
    require_allowed,
)


class FakePipeline:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.operations = []

    def hset(self, *args, **kwargs):
        self.operations.append(('hset', args, kwargs))
        return self

    def expire(self, *args):
        self.operations.append(('expire', args, {}))
        return self

    def hincrby(self, *args):
        self.operations.append(('hincrby', args, {}))
        return self

    def hincrbyfloat(self, *args):
        self.operations.append(('hincrbyfloat', args, {}))
        return self

    def zadd(self, *args):
        self.operations.append(('zadd', args, {}))
        return self

    def zrem(self, *args):
        self.operations.append(('zrem', args, {}))
        return self

    def zremrangebyrank(self, *args):
        self.operations.append(('zremrangebyrank', args, {}))
        return self

    def execute(self):
        for method, args, kwargs in self.operations:
            getattr(self.redis, method)(*args, **kwargs)


class FakeRedis:
    def __init__(self, fail=False):
        self.fail = fail
        self.strings = {}
        self.hashes = {}
        self.ttls = {}
        self.lists = {}
        self.zsets = {}
        self.timeline_wrongtype = False
        self.raise_after_eval = False

    def _check(self):
        if self.fail:
            raise ConnectionError('redis unavailable')

    def pipeline(self):
        self._check()
        return FakePipeline(self)

    def setex(self, key, ttl, value):
        self._check()
        self.strings[key] = str(value)
        self.ttls[key] = ttl

    def get(self, key):
        self._check()
        return self.strings.get(key)

    def hset(self, key, field=None, value=None, mapping=None):
        self._check()
        target = self.hashes.setdefault(key, {})
        if mapping:
            target.update({str(k): str(v) for k, v in mapping.items()})
        elif field is not None:
            target[str(field)] = str(value)

    def hgetall(self, key):
        self._check()
        return dict(self.hashes.get(key, {}))

    def hincrby(self, key, field, amount):
        self._check()
        target = self.hashes.setdefault(key, {})
        target[field] = str(int(target.get(field, 0)) + amount)

    def hincrbyfloat(self, key, field, amount):
        self._check()
        target = self.hashes.setdefault(key, {})
        target[field] = str(float(target.get(field, 0)) + amount)

    def expire(self, key, ttl):
        self._check()
        self.ttls[key] = ttl

    def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            for store in (self.strings, self.hashes, self.lists, self.zsets):
                if key in store:
                    removed += 1
                    del store[key]
        return removed

    def lpush(self, key, value):
        self._check()
        self.lists.setdefault(key, []).insert(0, str(value))
        return len(self.lists[key])

    def rpush(self, key, value):
        self._check()
        self.lists.setdefault(key, []).append(str(value))
        return len(self.lists[key])

    def rpop(self, key):
        self._check()
        values = self.lists.get(key, [])
        return values.pop() if values else None

    def llen(self, key):
        self._check()
        return len(self.lists.get(key, []))

    def lrange(self, key, start, stop):
        self._check()
        values = self.lists.get(key, [])
        if stop == -1:
            return list(values[start:])
        return list(values[start:stop + 1])

    def zadd(self, key, mapping):
        self._check()
        self.zsets.setdefault(key, {}).update({str(k): float(v) for k, v in mapping.items()})

    def zrem(self, key, member):
        self._check()
        self.zsets.get(key, {}).pop(str(member), None)

    def zremrangebyrank(self, key, start, stop):
        self._check()
        ordered = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        end = len(ordered) + stop + 1 if stop < 0 else stop + 1
        for member, _score in ordered[start:end]:
            self.zsets[key].pop(member, None)

    def zrange(self, key, start, stop, withscores=False):
        self._check()
        ordered = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        selected = ordered[start:] if stop == -1 else ordered[start:stop + 1]
        return selected if withscores else [member for member, _score in selected]

    def eval(self, script, numkeys, *args):
        self._check()
        keys, argv = args[:numkeys], args[numkeys:]
        if script == ANALYZER_REINITIALIZE_LUA:
            if self.llen(keys[0]) != 0:
                return 0
            self.delete(keys[1])
            self.strings[keys[2]] = str(argv[0])
            return 1
        if script == ANALYZER_ENQUEUE_LUA:
            direction, payload, record, version, limit = argv
            depth = self.lpush(keys[0], payload) if direction == 'left' else self.rpush(keys[0], payload)
            status = 0
            if self.get(keys[2]) == version:
                if depth <= int(limit):
                    if self.timeline_wrongtype:
                        self.delete(keys[2], keys[1])
                        status = -1
                    else:
                        self.lpush(keys[1], record) if direction == 'left' else self.rpush(keys[1], record)
                        status = 1
                else:
                    self.delete(keys[2], keys[1])
                    status = -2
            else:
                self.delete(keys[1])
            if self.raise_after_eval:
                raise ConnectionError('response lost')
            return [depth, status]
        if script == ANALYZER_DEQUEUE_LUA:
            if self.get(keys[1]) != argv[0]:
                return None
            return self.rpop(keys[0])
        raise AssertionError('unexpected script')



def _fresh_state(clock):
    return ExporterHealthState(
        stale_after_seconds=100,
        fast_state_ttl_seconds=20,
        clock=clock,
    )


def _sample_value(metric, sample_name):
    for family in metric.collect():
        for sample in family.samples:
            if sample.name == sample_name:
                return sample.value
    raise AssertionError(f"missing sample {sample_name}")


@pytest.fixture(scope="module")
def temporary_redis():
    with tempfile.TemporaryDirectory(prefix="arc-p0c-redis-") as directory:
        socket_path = os.path.join(directory, "redis.sock")
        process = subprocess.Popen(
            ["redis-server", "--port", "0", "--unixsocket", socket_path,
             "--unixsocketperm", "700", "--save", "", "--appendonly", "no"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                if os.path.exists(socket_path):
                    break
                time.sleep(0.02)
            client = redis_lib.Redis(unix_socket_path=socket_path, decode_responses=True)
            client.ping()
            yield client
        finally:
            process.terminate()
            process.wait(timeout=5)


def test_operational_namespace_is_fixed_and_arc_scoped():
    assert OPS_PREFIX == "arc:ops"
    assert all(stage.isidentifier() for stage in EXPORTER_ERROR_STAGES)
    assert EXPORTER_SCAN_RESULTS == {"success", "failure"}


def test_bounded_metric_labels_reject_arbitrary_values():
    assert require_allowed("redis_scan", EXPORTER_ERROR_STAGES, "stage") == "redis_scan"
    with pytest.raises(ValueError):
        require_allowed("exception:token=secret", EXPORTER_ERROR_STAGES, "stage")


def test_startup_is_stale_and_not_ready():
    state = _fresh_state(lambda: 1000)
    snapshot = state.snapshot()
    assert snapshot.stale is True
    assert snapshot.ready is False
    assert snapshot.last_scan_timestamp == 0
    assert snapshot.last_fast_state_timestamp == 0


def test_scan_in_progress_is_distinct_from_ready():
    state = _fresh_state(lambda: 1000)
    state.begin_scan()
    snapshot = state.snapshot()
    assert snapshot.scan_in_progress is True
    assert snapshot.ready is False
    assert snapshot.last_scan_attempt_timestamp == 1000


def test_successful_scan_alone_is_not_ready_without_fast_state():
    state = _fresh_state(lambda: 1000)
    state.begin_scan()
    state.finish_scan(True)
    snapshot = state.snapshot()
    assert snapshot.last_scan_success is True
    assert snapshot.stale is False
    assert snapshot.ready is False


def test_ready_requires_successful_scan_and_fresh_fast_state():
    state = _fresh_state(lambda: 1000)
    state.begin_scan()
    state.finish_scan(True)
    state.mark_fast_state_success()
    assert state.snapshot().ready is True


def test_failed_scan_immediately_clears_readiness_but_preserves_last_success_time():
    now = [1000.0]
    state = _fresh_state(lambda: now[0])
    state.begin_scan()
    state.finish_scan(True)
    state.mark_fast_state_success()
    previous_success = state.snapshot().last_scan_timestamp
    now[0] += 5
    state.begin_scan()
    state.finish_scan(False)
    snapshot = state.snapshot()
    assert snapshot.ready is False
    assert snapshot.last_scan_success is False
    assert snapshot.last_scan_timestamp == previous_success


def test_stale_scan_becomes_unready_even_with_fresh_fast_state():
    now = [1000.0]
    state = _fresh_state(lambda: now[0])
    state.begin_scan()
    state.finish_scan(True)
    now[0] = 1101
    state.mark_fast_state_success()
    snapshot = state.snapshot()
    assert snapshot.stale is True
    assert snapshot.ready is False


def test_fast_state_expiry_and_explicit_failure_clear_readiness():
    now = [1000.0]
    state = _fresh_state(lambda: now[0])
    state.begin_scan()
    state.finish_scan(True)
    state.mark_fast_state_success()
    now[0] = 1021
    assert state.snapshot().ready is False
    now[0] = 1022
    state.mark_fast_state_success()
    assert state.snapshot().ready is True
    state.mark_fast_state_failure()
    snapshot = state.snapshot()
    assert snapshot.ready is False
    assert snapshot.last_fast_state_timestamp == 0


def test_run_scan_once_records_success(monkeypatch):
    now = [2000.0]
    state = _fresh_state(lambda: now[0])
    state.mark_fast_state_success()
    monkeypatch.setattr(exporter, "exporter_health", state)
    monkeypatch.setattr(exporter, "scrape", lambda _redis: None)
    before = exporter.c_intel_scans.labels(result="success")._value.get()
    histogram_before = _sample_value(
        exporter.h_intel_scan_duration,
        "arc_intelligence_exporter_scan_duration_seconds_count",
    )

    assert exporter.run_scan_once(object()) is True

    assert exporter.c_intel_scans.labels(result="success")._value.get() == before + 1
    assert _sample_value(
        exporter.h_intel_scan_duration,
        "arc_intelligence_exporter_scan_duration_seconds_count",
    ) == histogram_before + 1
    assert state.snapshot().ready is True


def test_run_scan_once_records_bounded_stage_failure_without_secret(monkeypatch):
    now = [3000.0]
    state = _fresh_state(lambda: now[0])
    state.mark_fast_state_success()
    monkeypatch.setattr(exporter, "exporter_health", state)
    secret = "authorization-bearer-do-not-export"

    def fail(_redis):
        raise exporter.ScanStageError([("pipeline_stats", RuntimeError(secret))])

    monkeypatch.setattr(exporter, "scrape", fail)
    scans_before = exporter.c_intel_scans.labels(result="failure")._value.get()
    errors_before = exporter.c_intel_scan_errors.labels(stage="pipeline_stats")._value.get()

    assert exporter.run_scan_once(object()) is False

    assert exporter.c_intel_scans.labels(result="failure")._value.get() == scans_before + 1
    assert exporter.c_intel_scan_errors.labels(stage="pipeline_stats")._value.get() == errors_before + 1
    assert state.snapshot().ready is False
    assert secret.encode() not in generate_latest()


def test_unclassified_redis_failure_uses_fixed_redis_scan_stage(monkeypatch):
    state = _fresh_state(lambda: 4000)
    monkeypatch.setattr(exporter, "exporter_health", state)
    monkeypatch.setattr(
        exporter,
        "scrape",
        lambda _redis: (_ for _ in ()).throw(ConnectionError("redis unavailable")),
    )
    before = exporter.c_intel_scan_errors.labels(stage="redis_scan")._value.get()
    assert exporter.run_scan_once(object()) is False
    assert exporter.c_intel_scan_errors.labels(stage="redis_scan")._value.get() == before + 1


def test_metrics_expose_distinct_scrapeability_readiness_and_scan_state():
    payload = generate_latest().decode()
    required = (
        "arc_intelligence_exporter_ready",
        "arc_intelligence_exporter_stale",
        "arc_intelligence_exporter_scan_in_progress",
        "arc_intelligence_exporter_last_scan_success",
        "arc_intelligence_exporter_last_scan_timestamp_seconds",
        "arc_intelligence_exporter_last_scan_attempt_timestamp_seconds",
        "arc_intelligence_exporter_scans_total",
        "arc_intelligence_exporter_scan_duration_seconds_bucket",
        "arc_intelligence_exporter_scan_errors_total",
    )
    for metric in required:
        assert metric in payload
    # Prometheus up is supplied by the scraper, not forged by the exporter.
    assert "# HELP up" not in payload


def test_scribe_writer_uses_bounded_namespaced_keys_and_ttls():
    fake = FakeRedis()
    state = ScribeOperationalState(fake, clock=lambda: 1000)
    assert state.heartbeat()
    assert state.set_status('active')
    assert state.mark_poll_attempt()
    assert state.mark_success()
    assert fake.ttls[SCRIBE_HEARTBEAT_KEY] == HEARTBEAT_TTL_SECONDS
    assert fake.ttls[SCRIBE_STATE_KEY] == STATE_TTL_SECONDS
    assert all(key.startswith('arc:ops:') for key in (*fake.strings, *fake.hashes))


def test_scribe_writer_is_best_effort_when_redis_is_unavailable():
    state = ScribeOperationalState(FakeRedis(fail=True), clock=lambda: 1000)
    assert state.heartbeat() is False
    assert state.set_status('idle') is False
    assert state.increment('articles_new') is False


def test_scribe_writer_rejects_unbounded_fields_and_tracks_failure():
    fake = FakeRedis()
    state = ScribeOperationalState(fake, clock=lambda: 1000)
    with pytest.raises(ValueError):
        state.increment('article_id=secret')
    assert state.mark_failure('main_loop')
    assert fake.hashes[SCRIBE_STATE_KEY]['status'] == 'failed'
    assert fake.hashes[SCRIBE_COUNTERS_KEY]['errors_main_loop'] == '1'


def test_scribe_idle_worker_is_ready_with_fresh_heartbeat(monkeypatch):
    fake = FakeRedis()
    writer = ScribeOperationalState(fake, clock=lambda: 1000)
    writer.heartbeat()
    writer.mark_success()
    monkeypatch.setattr(exporter, '_registered_scribe_process_exists', lambda: True)
    exporter.scrape_scribe_operational(fake, now=1010)
    assert _sample_value(exporter.g_scribe_ready_p0, 'arc_scribe_ready') == 1
    assert _sample_value(exporter.g_scribe_stale_p0, 'arc_scribe_stale') == 0


def test_scribe_expired_heartbeat_is_stale_and_unready(monkeypatch):
    fake = FakeRedis()
    writer = ScribeOperationalState(fake, clock=lambda: 1000)
    writer.heartbeat()
    writer.mark_success()
    monkeypatch.setattr(exporter, '_registered_scribe_process_exists', lambda: True)
    exporter.scrape_scribe_operational(fake, now=1000 + HEARTBEAT_TTL_SECONDS + 1)
    assert _sample_value(exporter.g_scribe_ready_p0, 'arc_scribe_ready') == 0
    assert _sample_value(exporter.g_scribe_stale_p0, 'arc_scribe_stale') == 1


def test_scribe_failed_state_is_distinct_from_stale(monkeypatch):
    fake = FakeRedis()
    writer = ScribeOperationalState(fake, clock=lambda: 1000)
    writer.heartbeat()
    writer.mark_failure('source_poll')
    monkeypatch.setattr(exporter, '_registered_scribe_process_exists', lambda: True)
    exporter.scrape_scribe_operational(fake, now=1010)
    assert _sample_value(exporter.g_scribe_ready_p0, 'arc_scribe_ready') == 0
    assert _sample_value(exporter.g_scribe_stale_p0, 'arc_scribe_stale') == 0
    failed = exporter.g_scribe_state_p0.labels(state='failed')._value.get()
    assert failed == 1


def test_scribe_malformed_state_fails_visible_not_green(monkeypatch):
    fake = FakeRedis()
    fake.strings[SCRIBE_HEARTBEAT_KEY] = '1000'
    fake.hashes[SCRIBE_STATE_KEY] = {'status': 'idle', 'status_since': 'not-a-time'}
    monkeypatch.setattr(exporter, '_registered_scribe_process_exists', lambda: True)
    exporter.scrape_scribe_operational(fake, now=1010)
    assert _sample_value(exporter.g_scribe_ready_p0, 'arc_scribe_ready') == 0
    assert _sample_value(exporter.g_scribe_state_valid_p0, 'arc_scribe_state_valid') == 0


def test_scribe_counters_are_bounded_and_mirrored(monkeypatch):
    fake = FakeRedis()
    writer = ScribeOperationalState(fake, clock=lambda: 1000)
    writer.heartbeat()
    writer.mark_success()
    writer.record_poll('success')
    writer.increment('articles_discovered', 3)
    writer.increment('articles_new', 2)
    fake.hashes[SCRIBE_COUNTERS_KEY]['arbitrary_secret_label'] = '999'
    monkeypatch.setattr(exporter, '_registered_scribe_process_exists', lambda: True)
    exporter._scribe_counter_seen.clear()
    before = exporter.c_scribe_articles_new_p0._value.get()
    exporter.scrape_scribe_operational(fake, now=1010)
    assert exporter.c_scribe_articles_new_p0._value.get() == before + 2
    assert b'arbitrary_secret_label' not in generate_latest()


def test_scribe_active_state_that_exceeds_bound_is_stalled(monkeypatch):
    fake = FakeRedis()
    writer = ScribeOperationalState(fake, clock=lambda: 1000)
    writer.heartbeat(now=5000)
    writer.set_status('active', now=1000)
    monkeypatch.setattr(exporter, '_registered_scribe_process_exists', lambda: True)
    exporter.scrape_scribe_operational(fake, now=5000)
    assert _sample_value(exporter.g_scribe_ready_p0, 'arc_scribe_ready') == 0
    assert _sample_value(exporter.g_scribe_stale_p0, 'arc_scribe_stale') == 1


def test_duplicate_occurrences_keep_separate_timestamps_and_rpush_order():
    fake = FakeRedis()
    assert reinitialize_analyzer_queue_tracking(fake)
    enqueue_analysis(fake, 'same-id', 'right', now=1000)
    enqueue_analysis(fake, 'same-id', 'right', now=1001)
    assert fake.lists[ANALYZER_QUEUE_KEY] == ['same-id', 'same-id']
    assert len(fake.lists[ANALYZER_QUEUE_TIMELINE_KEY]) == 2
    assert fake.lists[ANALYZER_QUEUE_TIMELINE_KEY][0] != fake.lists[ANALYZER_QUEUE_TIMELINE_KEY][1]


def test_lua_helpers_against_real_temporary_redis(temporary_redis):
    client = temporary_redis
    client.flushdb()
    assert reinitialize_analyzer_queue_tracking(client)
    enqueue_analysis(client, 'duplicate', 'right', now=1000)
    enqueue_analysis(client, 'duplicate', 'right', now=1001)
    assert client.lrange(ANALYZER_QUEUE_KEY, 0, -1) == ['duplicate', 'duplicate']
    assert client.llen(ANALYZER_QUEUE_TIMELINE_KEY) == 2
    _queue, payload = client.brpop(ANALYZER_QUEUE_KEY, timeout=1)
    assert reconcile_analyzer_dequeue(client, payload)

    # Protected sidecar WRONGTYPE: the real push succeeds and certainty closes.
    client.flushdb()
    client.rpush(ANALYZER_QUEUE_KEY, 'legacy')
    client.set(ANALYZER_QUEUE_TRACKING_KEY, ANALYZER_TRACKING_VERSION)
    client.set(ANALYZER_QUEUE_TIMELINE_KEY, 'wrong-type')
    depth, status = enqueue_analysis(client, 'still-queued', 'right', now=1002)
    assert (depth, status) == (2, -1)
    assert client.lrange(ANALYZER_QUEUE_KEY, 0, -1) == ['legacy', 'still-queued']
    assert client.get(ANALYZER_QUEUE_TRACKING_KEY) is None


def test_lpush_and_rpush_timeline_alignment_preserves_payload_order():
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    enqueue_analysis(fake, 'ingest', 'right', now=1000)
    enqueue_analysis(fake, 'reader', 'left', now=1001)
    assert fake.lists[ANALYZER_QUEUE_KEY] == ['reader', 'ingest']
    digests = [record.split('|')[0] for record in fake.lists[ANALYZER_QUEUE_TIMELINE_KEY]]
    assert digests == [analyzer_timeline_record('reader', 1).split('|')[0],
                       analyzer_timeline_record('ingest', 1).split('|')[0]]


def test_brpop_rpop_reconciliation_and_empty_reinitialization():
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    enqueue_analysis(fake, 'one', 'right', now=1000)
    assert fake.rpop(ANALYZER_QUEUE_KEY) == 'one'
    assert reconcile_analyzer_dequeue(fake, 'one') is True
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) == ANALYZER_TRACKING_VERSION
    assert fake.llen(ANALYZER_QUEUE_TIMELINE_KEY) == 0


@pytest.mark.parametrize('timeline_value', [None, 'malformed', '0' * 64 + '|nan'])
def test_missing_or_malformed_timeline_fails_closed(timeline_value):
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    fake.rpush(ANALYZER_QUEUE_KEY, 'one')
    if timeline_value is not None:
        fake.rpush(ANALYZER_QUEUE_TIMELINE_KEY, timeline_value)
    fake.rpop(ANALYZER_QUEUE_KEY)
    assert reconcile_analyzer_dequeue(fake, 'one') is False
    # Empty queue is safely reinitialized only after invalidation.
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) == ANALYZER_TRACKING_VERSION


def test_digest_mismatch_and_interleaved_consumers_fail_closed():
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    enqueue_analysis(fake, 'first', 'right', now=1000)
    enqueue_analysis(fake, 'second', 'right', now=1001)
    popped_first = fake.rpop(ANALYZER_QUEUE_KEY)
    popped_second = fake.rpop(ANALYZER_QUEUE_KEY)
    assert (popped_first, popped_second) == ('second', 'first')
    # Reconcile in the opposite consumer order: first comparison mismatches.
    assert reconcile_analyzer_dequeue(fake, popped_second) is False
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) == ANALYZER_TRACKING_VERSION  # queue now empty, reset safely


def test_sidecar_wrongtype_preserves_real_push_and_invalidates_tracking():
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    fake.timeline_wrongtype = True
    depth, status = enqueue_analysis(fake, 'queued', 'right', now=1000)
    assert (depth, status) == (1, -1)
    assert fake.lists[ANALYZER_QUEUE_KEY] == ['queued']
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) is None


def test_connection_response_ambiguity_invalidates_best_effort():
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    fake.raise_after_eval = True
    with pytest.raises(ConnectionError):
        enqueue_analysis(fake, 'queued', 'right', now=1000)
    assert fake.lists[ANALYZER_QUEUE_KEY] == ['queued']
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) is None


def test_tracking_limit_invalidates_without_trimming_or_growth():
    fake = FakeRedis()
    reinitialize_analyzer_queue_tracking(fake)
    fake.lists[ANALYZER_QUEUE_KEY] = ['legacy'] * ANALYZER_TRACKING_LIMIT
    fake.lists[ANALYZER_QUEUE_TIMELINE_KEY] = ['x'] * ANALYZER_TRACKING_LIMIT
    depth, status = enqueue_analysis(fake, 'overflow', 'right', now=1000)
    assert (depth, status) == (ANALYZER_TRACKING_LIMIT + 1, -2)
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) is None
    assert fake.llen(ANALYZER_QUEUE_TIMELINE_KEY) == 0
    enqueue_analysis(fake, 'later', 'right', now=1001)
    assert fake.llen(ANALYZER_QUEUE_TIMELINE_KEY) == 0


def test_legacy_nonempty_queue_does_not_initialize_tracking():
    fake = FakeRedis()
    fake.rpush(ANALYZER_QUEUE_KEY, 'legacy')
    assert reinitialize_analyzer_queue_tracking(fake) is False
    enqueue_analysis(fake, 'new', 'right', now=1000)
    assert fake.get(ANALYZER_QUEUE_TRACKING_KEY) is None
    assert fake.llen(ANALYZER_QUEUE_TIMELINE_KEY) == 0


def test_reinitialization_does_nothing_after_producer_wins_race():
    fake = FakeRedis()
    fake.rpush(ANALYZER_QUEUE_KEY, 'producer-won')
    fake.rpush(ANALYZER_QUEUE_TIMELINE_KEY, analyzer_timeline_record('producer-won', 1000))
    assert reinitialize_analyzer_queue_tracking(fake) is False
    assert fake.llen(ANALYZER_QUEUE_TIMELINE_KEY) == 1


def _healthy_analyzer_fake(now=1000):
    fake = FakeRedis()
    writer = AnalyzerOperationalState(fake, clock=lambda: now)
    writer.heartbeat()
    writer.set_status('idle')
    reinitialize_analyzer_queue_tracking(fake)
    return fake, writer


def test_analyzer_idle_empty_queue_is_ready_and_age_is_nan(monkeypatch):
    fake, _writer = _healthy_analyzer_fake()
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 1)
    exporter.scrape_analyzer_operational(fake, now=1010)
    assert exporter.g_analyzer_ready.labels(stack='arc')._value.get() == 1
    assert exporter.g_analyzer_queue_age_known.labels(stack='arc', queue='analysis')._value.get() == 1
    assert math.isnan(exporter.g_analyzer_oldest_age.labels(stack='arc', queue='analysis')._value.get())


def test_analyzer_active_and_expired_heartbeat_semantics(monkeypatch):
    fake, writer = _healthy_analyzer_fake()
    writer.start_job('internal-id', now=1000)
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 1)
    exporter.scrape_analyzer_operational(fake, now=1010)
    assert exporter.g_analyzer_ready.labels(stack='arc')._value.get() == 1
    assert exporter.g_analyzer_active_locks.labels(stack='arc')._value.get() == 1
    exporter.scrape_analyzer_operational(fake, now=1000 + HEARTBEAT_TTL_SECONDS + 1)
    assert exporter.g_analyzer_ready.labels(stack='arc')._value.get() == 0
    assert exporter.g_analyzer_stale.labels(stack='arc')._value.get() == 1


def test_duplicate_queue_occurrences_have_known_oldest_age(monkeypatch):
    fake, _writer = _healthy_analyzer_fake()
    private_id = 'sensitive-article-9472-private'
    enqueue_analysis(fake, private_id, 'right', now=1000)
    enqueue_analysis(fake, private_id, 'right', now=1005)
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 1)
    exporter.scrape_analyzer_operational(fake, now=1010)
    assert exporter.g_analyzer_queue_age_known.labels(stack='arc', queue='analysis')._value.get() == 1
    assert exporter.g_analyzer_oldest_age.labels(stack='arc', queue='analysis')._value.get() == 10
    payload = generate_latest().decode()
    assert private_id not in payload
    assert analyzer_timeline_record(private_id, 1).split('|')[0] not in payload


def test_malformed_timeline_timestamp_is_unknown(monkeypatch):
    fake, _writer = _healthy_analyzer_fake()
    fake.rpush(ANALYZER_QUEUE_KEY, 'one')
    fake.rpush(ANALYZER_QUEUE_TIMELINE_KEY, '0' * 64 + '|not-a-time')
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 1)
    exporter.scrape_analyzer_operational(fake, now=1010)
    assert exporter.g_analyzer_queue_age_known.labels(stack='arc', queue='analysis')._value.get() == 0
    assert math.isnan(exporter.g_analyzer_oldest_age.labels(stack='arc', queue='analysis')._value.get())


def test_queue_mismatch_and_legacy_timestamp_are_unknown(monkeypatch):
    fake, _writer = _healthy_analyzer_fake()
    fake.rpush(ANALYZER_QUEUE_KEY, 'legacy')
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 1)
    exporter.scrape_analyzer_operational(fake, now=1010)
    assert exporter.g_analyzer_queue_depth.labels(stack='arc', queue='analysis')._value.get() == 1
    assert exporter.g_analyzer_queue_age_known.labels(stack='arc', queue='analysis')._value.get() == 0
    assert math.isnan(exporter.g_analyzer_oldest_age.labels(stack='arc', queue='analysis')._value.get())


def test_analyzer_job_counters_histogram_and_active_lock(monkeypatch):
    fake, writer = _healthy_analyzer_fake()
    writer.start_job('private-article-id', now=1000)
    writer.finish_job('private-article-id', 'failed', 16, stage='inference', now=1020)
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 1)
    exporter._analyzer_counter_seen.clear()
    exporter.scrape_analyzer_operational(fake, now=1021)
    payload = generate_latest().decode()
    assert 'arc_analyzer_job_duration_seconds_bucket{le="15.0",stack="arc"} 0.0' in payload
    assert 'arc_analyzer_job_duration_seconds_bucket{le="30.0",stack="arc"} 1.0' in payload
    assert 'arc_analyzer_job_duration_seconds_count{stack="arc"} 1.0' in payload
    assert 'private-article-id' not in payload
    first_count = payload.count('arc_analyzer_job_duration_seconds_count{stack="arc"} 1.0')
    exporter.scrape_analyzer_operational(fake, now=1022)
    assert generate_latest().decode().count(
        'arc_analyzer_job_duration_seconds_count{stack="arc"} 1.0') == first_count


def test_multiple_analyzer_processes_fail_readiness_and_queue_age(monkeypatch):
    fake, _writer = _healthy_analyzer_fake()
    monkeypatch.setattr(exporter, '_matching_analyzer_process_count', lambda: 2)
    exporter.scrape_analyzer_operational(fake, now=1010)
    assert exporter.g_analyzer_ready.labels(stack='arc')._value.get() == 0
    # Queue is empty/aligned, but multiple consumers make positional certainty unsafe.
    # Force the exported certainty closed in the implementation contract.
    assert exporter.g_analyzer_stale.labels(stack='arc')._value.get() == 1
    assert exporter.g_analyzer_queue_age_known.labels(stack='arc', queue='analysis')._value.get() == 0


def test_main_enqueue_paths_use_helper_without_changing_directions():
    source = (BACKEND / 'main.py').read_text()
    assert "enqueue_analysis(r, article_id, 'right')" in source
    assert "enqueue_analysis(r, actual_id, 'left')" in source
    assert "r.rpush('analyzer:queue', article_id)" not in source
    assert "r.lpush('analyzer:queue', actual_id)" not in source


def test_analyzer_operational_writes_are_best_effort_when_redis_fails():
    writer = AnalyzerOperationalState(FakeRedis(fail=True), clock=lambda: 1000)
    assert writer.heartbeat() is False
    assert writer.start_job('internal-id') is False
    assert writer.finish_job('internal-id', 'failed', 1, stage='redis') is False
