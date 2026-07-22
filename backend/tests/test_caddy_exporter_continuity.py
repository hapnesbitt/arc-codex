import gzip
import importlib.util
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path

from prometheus_client import generate_latest


MODULE_PATH = Path(__file__).resolve().parents[1] / "caddy_exporter.py"
SPEC = importlib.util.spec_from_file_location("caddy_exporter_continuity", MODULE_PATH)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class FakeMetrics:
    def __init__(self):
        self.counts = {name: 0 for name in (
            "replayed", "parse_error", "rotation", "truncation",
            "checkpoint_error", "duplicate",
            "recovery_error",
        )}
        self.last_file_state = {}

    def checkpoint(self, site, offset, timestamp):
        pass

    def initialize(self, site):
        pass

    def file_state(self, site, size, offset, last_event):
        self.last_file_state[site] = (size, offset, last_event)

    def event(self, site, timestamp):
        pass

    def __getattr__(self, name):
        if name in self.counts:
            return lambda site: self.counts.__setitem__(name, self.counts[name] + 1)
        raise AttributeError(name)


def record(identifier, *, timestamp=None):
    return (json.dumps({"id": identifier, "ts": timestamp or time.time()}) + "\n").encode()


class TailerFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.log = self.root / "site-access.log"
        self.log.touch()
        self.state = self.root / "state"
        self.metrics = FakeMetrics()
        self.store = exporter.PositionStore(str(self.state), self.metrics)
        self.store.ensure()
        self.seen = []

    def tearDown(self):
        self.temp.cleanup()

    def append(self, *lines):
        with self.log.open("ab") as handle:
            for line in lines:
                handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def handler(self, site, line):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return False, None
        self.seen.append(value["id"])
        return True, float(value["ts"])

    def tailer(self, **kwargs):
        return exporter.DurableTailer(
            "site", str(self.log), self.store, self.handler,
            metrics=self.metrics, poll_interval=0.01, **kwargs,
        )

    def checkpoint(self):
        return json.loads((self.state / "site.json").read_text())

    def test_01_initial_startup_at_eof(self):
        self.append(record("old"))
        tailer = self.tailer()
        tailer.prepare()
        self.assertEqual([], self.seen)
        self.assertEqual(self.log.stat().st_size, self.checkpoint()["offset"])
        tailer.close()

    def test_02_restart_replays_downtime_records(self):
        first = self.tailer()
        first.prepare()
        first.close()
        self.append(record("missed-1"), record("missed-2"))
        second = self.tailer()
        second.prepare()
        self.assertEqual(["missed-1", "missed-2"], self.seen)
        self.assertEqual(2, self.metrics.counts["replayed"])
        self.assertFalse(self.checkpoint()["recovery_pending"])
        second.close()

    def test_03_catchup_from_saved_offset(self):
        first_line = record("live")
        self.append(first_line)
        tailer = self.tailer(initial_policy="beginning")
        tailer.prepare()
        tailer.close()
        self.seen.clear()
        self.append(record("after"))
        resumed = self.tailer()
        resumed.prepare()
        self.assertEqual(["after"], self.seen)
        resumed.close()

    def test_04_clean_counter_reset_has_complete_replay(self):
        first = self.tailer()
        first.prepare()
        self.append(record("one"))
        first.poll_once()
        first.close()
        self.seen.clear()
        self.append(record("two"))
        second = self.tailer()
        second.prepare()
        self.assertEqual(["two"], self.seen)
        second.close()

    def test_05_rename_recreate_rotation(self):
        tailer = self.tailer()
        tailer.prepare()
        self.append(record("old-inode"))
        rotated = self.root / "site-access-2026-07-22T00-00-00.log"
        self.log.rename(rotated)
        self.log.touch()
        self.append(record("new-inode"))
        tailer.poll_once()
        tailer.poll_once()
        self.assertEqual(["old-inode", "new-inode"], self.seen)
        self.assertEqual(1, self.metrics.counts["rotation"])
        tailer.close()

    def test_06_copytruncate_rotation(self):
        tailer = self.tailer()
        tailer.prepare()
        self.append(record("before"))
        tailer.poll_once()
        self.log.write_bytes(record("after"))
        tailer.poll_once()
        self.assertEqual(["before", "after"], self.seen)
        self.assertEqual(1, self.metrics.counts["truncation"])
        tailer.close()

    def test_07_rotation_while_stopped(self):
        old = record("boundary")
        self.append(old)
        first = self.tailer(initial_policy="beginning")
        first.prepare()
        first.close()
        rotated = self.root / "site-access-2026-07-22T00-00-00.log"
        self.log.rename(rotated)
        with rotated.open("ab") as handle:
            handle.write(record("old-tail"))
        self.log.write_bytes(record("new-head"))
        self.seen.clear()
        second = self.tailer()
        second.prepare()
        self.assertEqual(["old-tail", "new-head"], self.seen)
        second.close()

    def test_08_rotation_during_active_reading(self):
        tailer = self.tailer()
        tailer.prepare()
        rotated = self.root / "site-access-2026-07-22T00-00-00.log"
        self.log.rename(rotated)
        with rotated.open("ab") as handle:
            handle.write(record("late-old"))
        self.log.write_bytes(record("new"))
        tailer.poll_once()
        tailer.poll_once()
        self.assertEqual(["late-old", "new"], self.seen)
        tailer.close()

    def test_09_partial_line_completed_later(self):
        line = record("partial")
        self.append(line[:8])
        tailer = self.tailer(initial_policy="beginning")
        tailer.prepare()
        self.assertEqual([], self.seen)
        self.append(line[8:])
        tailer.poll_once()
        self.assertEqual(["partial"], self.seen)
        tailer.close()

    def test_10_malformed_then_valid(self):
        tailer = self.tailer()
        tailer.prepare()
        self.append(b"not-json\n", record("valid"))
        tailer.poll_once()
        self.assertEqual(["valid"], self.seen)
        self.assertEqual(1, self.metrics.counts["parse_error"])
        tailer.close()

    def test_11_invalid_checkpoint_fails_closed(self):
        (self.state / "site.json").write_text("not json")
        with self.assertRaises(exporter.ContinuityError):
            self.tailer().prepare()

    def test_12_offset_beyond_file_size_fails_closed(self):
        tailer = self.tailer()
        tailer.prepare()
        tailer.close()
        checkpoint = self.checkpoint()
        checkpoint["offset"] = 100
        (self.state / "site.json").write_text(json.dumps(checkpoint))
        with self.assertRaises(exporter.ContinuityError):
            self.tailer().prepare()

    def test_13_permission_failure(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses test directory permissions")
        os.chmod(self.state, 0o500)
        try:
            with self.assertRaises(PermissionError):
                self.store.ensure()
        finally:
            os.chmod(self.state, 0o700)

    def test_14_atomic_checkpoint_and_mode(self):
        tailer = self.tailer()
        tailer.prepare()
        path = self.state / "site.json"
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual([], list(self.state.glob("*.tmp")))
        json.loads(path.read_text())
        tailer.close()

    def test_15_no_duplicate_on_ordinary_restart(self):
        first = self.tailer()
        first.prepare()
        self.append(record("once"))
        first.poll_once()
        first.close()
        second = self.tailer()
        second.prepare()
        self.assertEqual(["once"], self.seen)
        second.close()

    def test_16_forced_crash_window_is_bounded_to_one_record(self):
        tailer = self.tailer()
        tailer.prepare()
        line = record("crash-window")
        self.append(line)
        original_save = self.store.save

        def fail_save(site, value):
            self.store.save = original_save
            raise OSError("synthetic crash before checkpoint persistence")

        self.store.save = fail_save
        with self.assertRaises(OSError):
            tailer.poll_once()
        tailer.close()
        resumed = self.tailer()
        resumed.prepare()
        self.assertEqual(["crash-window", "crash-window"], self.seen)
        resumed.close()

    def test_17_multiple_logs_advance_independently(self):
        other_log = self.root / "other-access.log"
        other_log.touch()
        other_seen = []

        def other_handler(site, line):
            value = json.loads(line)
            other_seen.append(value["id"])
            return True, float(value["ts"])

        first = self.tailer()
        second = exporter.DurableTailer(
            "other", str(other_log), self.store, other_handler,
            metrics=self.metrics, initial_policy="end",
        )
        first.prepare()
        second.prepare()
        self.append(record("site-one"))
        with other_log.open("ab") as handle:
            handle.write(record("other-one"))
        first.poll_once()
        second.poll_once()
        self.assertEqual(["site-one"], self.seen)
        self.assertEqual(["other-one"], other_seen)
        self.assertNotEqual(
            self.store.load("site")["canonical_path"],
            self.store.load("other")["canonical_path"],
        )
        first.close()
        second.close()

    def test_retained_gzip_rotation_boundary(self):
        self.append(record("boundary"))
        first = self.tailer(initial_policy="beginning")
        first.prepare()
        first.close()
        raw = self.log.read_bytes() + record("gzip-tail")
        archive = self.root / "site-access-2026-07-22T00-00-00.log.gz"
        with gzip.open(archive, "wb") as handle:
            handle.write(raw)
        self.log.unlink()
        self.log.write_bytes(record("active"))
        self.seen.clear()
        resumed = self.tailer()
        resumed.prepare()
        self.assertEqual(["gzip-tail", "active"], self.seen)
        resumed.close()

    def test_missing_retained_boundary_fails_closed(self):
        self.append(record("boundary"))
        first = self.tailer(initial_policy="beginning")
        first.prepare()
        first.close()
        self.log.unlink()
        self.log.write_bytes(record("replacement"))
        with self.assertRaises(exporter.ContinuityError):
            self.tailer().prepare()

    def test_prime_replay_labels_is_read_only(self):
        first = self.tailer()
        first.prepare()
        first.close()
        saved = self.checkpoint()
        self.append(record("pending"))
        second = self.tailer()
        self.assertEqual(1, second.prime_replay_labels())
        self.assertEqual(saved, self.checkpoint())
        self.assertEqual([], self.seen)
        second.prepare()
        self.assertEqual(["pending"], self.seen)
        second.close()

    def test_stopped_copytruncate_regrown_beyond_offset_replays_from_zero(self):
        self.append(record("old-1"), record("old-2"))
        first = self.tailer(initial_policy="beginning")
        first.prepare()
        old_offset = self.checkpoint()["offset"]
        first.close()
        self.seen.clear()

        rewritten = [record(f"new-{index}") for index in range(12)]
        self.log.write_bytes(b"".join(rewritten))
        self.assertGreater(self.log.stat().st_size, old_offset)

        resumed = self.tailer()
        resumed.prepare()
        self.assertEqual([f"new-{index}" for index in range(12)], self.seen)
        self.assertEqual(1, self.metrics.counts["truncation"])
        self.assertEqual(self.log.stat().st_size, self.checkpoint()["offset"])
        self.assertEqual(
            (self.log.stat().st_size, self.log.stat().st_size),
            self.metrics.last_file_state["site"][:2],
        )
        self.assertFalse(self.checkpoint()["recovery_pending"])
        resumed.close()

    def test_same_inode_matching_boundary_resumes_without_prior_replay(self):
        self.append(record("old-1"), record("old-2"))
        first = self.tailer(initial_policy="beginning")
        first.prepare()
        first.close()
        self.seen.clear()
        self.append(record("new-only"))

        resumed = self.tailer()
        resumed.prepare()
        self.assertEqual(["new-only"], self.seen)
        self.assertEqual(0, self.metrics.counts["truncation"])
        resumed.close()

    def test_path_metric_uses_only_fixed_groups_and_removes_stale_children(self):
        site = "bounded-path-test"
        old_top_paths = exporter.TOP_PATHS
        try:
            exporter.TOP_PATHS = 1
            with exporter._state_lock:
                exporter._path_counts[site].clear()
                exporter._published_path_groups[site].clear()
                exporter._path_counts[site]["page_home"] = 10
                exporter._path_counts[site]["api_feed"] = 1
            exporter.publish_rollup_gauges()
            before = generate_latest().decode()
            self.assertIn(f'arc_http_top_paths_total{{path="page_home",site="{site}"}}', before)

            with exporter._state_lock:
                exporter._path_counts[site]["api_feed"] = 20
            exporter.publish_rollup_gauges()
            after = generate_latest().decode()
            self.assertNotIn(f'arc_http_top_paths_total{{path="page_home",site="{site}"}}', after)
            self.assertIn(f'arc_http_top_paths_total{{path="api_feed",site="{site}"}}', after)
            for forbidden in ("/article/123", "?token=", "arbitrary-attacker-path"):
                self.assertNotIn(forbidden, after)
        finally:
            exporter.TOP_PATHS = old_top_paths
            with exporter._state_lock:
                exporter._path_counts.pop(site, None)
                exporter._published_path_groups.pop(site, None)
            for label in ("page_home", "api_feed"):
                try:
                    exporter.TOP_PATH_GAUGE.remove(site, label)
                except KeyError:
                    pass

    def test_unknown_path_group_overflows_to_other_without_arbitrary_label(self):
        site = "overflow-path-test"
        before = exporter.PATH_OVERFLOW.labels(site)._value.get()
        self.assertEqual("other", exporter.bounded_path_group(site, "/attacker/value/123"))
        self.assertEqual(before + 1, exporter.PATH_OVERFLOW.labels(site)._value.get())
        metrics = generate_latest().decode()
        self.assertNotIn('path="/attacker/value/123"', metrics)

    def _make_archive(self, name, content=b"{}\n"):
        path = self.root / name
        if name.endswith(".gz"):
            with gzip.open(path, "wb") as handle:
                handle.write(content)
        else:
            path.write_bytes(content)
        return path

    def test_archive_count_limit_fails_closed(self):
        for index in range(exporter.MAX_ROTATED_ARCHIVES + 1):
            self._make_archive(f"site-access.log.{index + 1}")
        with self.assertRaises(exporter.ContinuityError):
            list(self.tailer()._rotation_candidates())
        self.assertEqual(1, self.metrics.counts["recovery_error"])

    def test_archive_cumulative_size_limit_fails_closed(self):
        archive = self._make_archive("site-access.log.1", b"x" * 128)
        old_limit = exporter.MAX_ARCHIVE_BYTES
        try:
            exporter.MAX_ARCHIVE_BYTES = archive.stat().st_size - 1
            with self.assertRaises(exporter.ContinuityError):
                list(self.tailer()._rotation_candidates())
        finally:
            exporter.MAX_ARCHIVE_BYTES = old_limit

    def test_archive_age_limit_fails_closed(self):
        archive = self._make_archive("site-access.log.1")
        old = time.time() - exporter.MAX_ARCHIVE_AGE_SECONDS - 60
        os.utime(archive, (old, old))
        with self.assertRaises(exporter.ContinuityError):
            list(self.tailer()._rotation_candidates())

    def test_archive_symlink_or_escape_fails_closed(self):
        outside = self.root.parent / f"{self.root.name}-outside.log"
        outside.write_bytes(b"{}\n")
        link = self.root / "site-access.log.1"
        link.symlink_to(outside)
        try:
            with self.assertRaises(exporter.ContinuityError):
                list(self.tailer()._rotation_candidates())
        finally:
            outside.unlink()

    def test_archive_non_regular_candidate_fails_closed(self):
        (self.root / "site-access.log.1").mkdir()
        with self.assertRaises(exporter.ContinuityError):
            list(self.tailer()._rotation_candidates())

    def test_ambiguous_archive_boundary_fails_closed(self):
        boundary = record("same-boundary", timestamp=1234)
        self.append(boundary)
        first = self.tailer(initial_policy="beginning")
        first.prepare()
        first.close()
        self._make_archive("site-access.log.2", boundary)
        self._make_archive("site-access.log.1", boundary)
        self.log.unlink()
        self.log.write_bytes(record("replacement"))
        with self.assertRaises(exporter.ContinuityError):
            self.tailer().prepare()
        self.assertEqual(1, self.metrics.counts["recovery_error"])

    def test_archive_order_uses_rotation_timestamp_not_lexical_or_mtime(self):
        newer = self._make_archive("site-access-2026-07-22T10-00-00.000-size.log.gz")
        older = self._make_archive("site-access-2026-07-21T10-00-00.000-size.log.gz")
        now = time.time()
        os.utime(older, (now, now))
        os.utime(newer, (now - 100, now - 100))
        candidates = list(self.tailer()._rotation_candidates())
        self.assertEqual([older.resolve(), newer.resolve(), self.log.resolve()], candidates)

    def test_numbered_archive_order_is_descending_number_not_mtime(self):
        oldest = self._make_archive("site-access.log.3")
        middle = self._make_archive("site-access.log.2.gz")
        newest = self._make_archive("site-access.log.1")
        now = time.time()
        os.utime(oldest, (now, now))
        os.utime(newest, (now - 100, now - 100))
        candidates = list(self.tailer()._rotation_candidates())
        self.assertEqual(
            [oldest.resolve(), middle.resolve(), newest.resolve(), self.log.resolve()],
            candidates,
        )

    def test_mixed_rotation_schemes_fail_closed(self):
        self._make_archive("site-access.log.1")
        self._make_archive("site-access-2026-07-22T10-00-00.000-size.log.gz")
        with self.assertRaises(exporter.ContinuityError):
            list(self.tailer()._rotation_candidates())


if __name__ == "__main__":
    unittest.main()
