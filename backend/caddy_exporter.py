#!/usr/bin/env python3
"""Prometheus exporter for Arc/Huntaegis Caddy JSON access logs.

The exporter tails each configured newline-delimited JSON log from a durable
per-site checkpoint.  A first deployment starts at the current EOF; later
starts replay records written while the exporter was unavailable.  Checkpoint
writes are atomic and occur only after a complete record has been handled.
"""

import argparse
import glob
import gzip
import hashlib
import json
import logging
import os
import re
import signal
import stat
import sys
import threading
import time
from collections import Counter as CollectionCounter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

from prometheus_client import (
    PROCESS_COLLECTOR,
    PLATFORM_COLLECTOR,
    REGISTRY,
    Counter,
    Gauge,
    Summary,
    start_http_server,
)

try:
    REGISTRY.unregister(PROCESS_COLLECTOR)
    REGISTRY.unregister(PLATFORM_COLLECTOR)
except Exception:
    pass


LOG = logging.getLogger("caddy_exporter")
STATE_VERSION = 1
DEFAULT_STATE_DIR = "/var/lib/arc-traffic-exporter"
DEFAULT_PORT = 9102
MAX_PATH_SERIES_PER_SITE = 64
MAX_ROTATED_ARCHIVES = 8
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_AGE_SECONDS = 30 * 24 * 60 * 60

LOGS = {
    "arc-codex": "/var/log/caddy/arc-codex-access.log",
    "huntaegis": "/var/log/caddy/huntaegis-access.log",
}

TOP_PATHS = int(os.getenv("CADDY_TOP_PATHS", 20))
ROLLUP_INTERVAL = int(os.getenv("CADDY_ROLLUP_INTERVAL", 60))

PATH_GROUPS = [
    (r"^/api/get_feed", "api_feed"),
    (r"^/api/translate", "api_translate"),
    (r"^/api/article/", "api_articles"),
    (r"^/api/library/", "api_library"),
    (r"^/api/search", "api_search"),
    (r"^/api/submit", "api_submit"),
    (r"^/api/auth", "api_auth"),
    (r"^/api/user", "api_user"),
    (r"^/api/rss", "api_rss"),
    (r"^/api/feed\.xml", "api_rss"),
    (r"^/api/stats", "api_stats"),
    (r"^/api/", "api_other"),
    (r"^/article/", "page_article"),
    (r"^/search", "page_search"),
    (r"^/publish", "page_publish"),
    (r"^/about", "page_about"),
    (r"^/uploads/", "static_uploads"),
    (r"^/_next/static", "static_next"),
    (r"^/_next/", "next_internal"),
    (r"^/favicon", "static_favicon"),
    (r"^/$", "page_home"),
]
PATH_GROUP_VOCABULARY = frozenset(group for _pattern, group in PATH_GROUPS) | {"other"}
if len(PATH_GROUP_VOCABULARY) > MAX_PATH_SERIES_PER_SITE:
    raise RuntimeError("path-group vocabulary exceeds the configured series bound")
BOT_PATTERNS = [
    "bot", "crawler", "spider", "slurp", "bingpreview",
    "facebookexternalhit", "meta-externalagent", "twitterbot",
    "linkedinbot", "whatsapp", "telegrambot", "discordbot",
    "applebot", "googlebot", "baiduspider", "yandex",
    "semrush", "ahrefs", "mj12bot", "dotbot", "petalbot",
]

REQUESTS = Counter(
    "arc_http_requests_total", "Total HTTP requests", ["site", "method", "status", "path_group"]
)
BYTES = Counter("arc_http_response_bytes_total", "Total HTTP response bytes", ["site"])
STATUS_CLASS = Counter("arc_http_status_class_total", "HTTP requests by status class", ["site", "status_class"])
UA_CLASS = Counter("arc_http_ua_class_total", "HTTP requests by user-agent class", ["site", "ua_class"])
DURATION = Summary("arc_http_request_duration_seconds", "HTTP request duration in seconds", ["site", "path_group"])
TOP_PATH_GAUGE = Gauge(
    "arc_http_top_paths_total",
    "Normalized route-group hit counts since exporter start (compatibility metric; never raw URI paths)",
    ["site", "path"],
)
TOP_IP_GAUGE = Gauge(
    "arc_http_top_ip_prefix_total", "Top /16 IP prefix hit counts (since exporter start)", ["site", "ip_prefix"]
)
REQUESTS_PER_MINUTE = Gauge(
    "arc_http_requests_per_minute", "Requests observed in the last 60 seconds", ["site"]
)

_path_counts = defaultdict(CollectionCounter)
_ip_counts = defaultdict(CollectionCounter)
_req_timestamps = defaultdict(list)
_state_lock = threading.Lock()
_published_path_groups = defaultdict(set)

CHECKPOINT_OFFSET = Gauge(
    "arc_traffic_exporter_checkpoint_offset_bytes", "Durable checkpoint byte offset", ["site"]
)
LOG_SIZE = Gauge("arc_traffic_exporter_log_size_bytes", "Current active log size", ["site"])
LAG_BYTES = Gauge("arc_traffic_exporter_lag_bytes", "Unread bytes in the active log", ["site"])
LAG_SECONDS = Gauge(
    "arc_traffic_exporter_lag_seconds", "Wall-clock age of the last processed event while behind", ["site"]
)
REPLAYED = Counter("arc_traffic_exporter_replayed_lines_total", "Records replayed during startup recovery", ["site"])
PARSE_ERRORS = Counter("arc_traffic_exporter_parse_errors_total", "Malformed or unusable Caddy records", ["site"])
ROTATIONS = Counter("arc_traffic_exporter_rotations_total", "Rename-and-recreate rotations observed", ["site"])
TRUNCATIONS = Counter("arc_traffic_exporter_truncations_total", "Copytruncate events observed", ["site"])
CHECKPOINT_ERRORS = Counter("arc_traffic_exporter_checkpoint_errors_total", "Checkpoint read/write errors", ["site"])
DUPLICATES = Counter(
    "arc_traffic_exporter_duplicate_records_total", "Known duplicate records incorporated", ["site"]
)
PATH_OVERFLOW = Counter(
    "arc_traffic_exporter_path_series_overflow_total",
    "Requests whose proposed route group was outside the fixed allow-listed vocabulary",
    ["site"],
)
RECOVERY_ERRORS = Counter(
    "arc_traffic_exporter_recovery_errors_total", "Fail-closed continuity recovery errors", ["site"]
)
LAST_EVENT = Gauge(
    "arc_traffic_exporter_last_event_timestamp_seconds", "Timestamp of the most recently handled event", ["site"]
)
LAST_CHECKPOINT = Gauge(
    "arc_traffic_exporter_last_checkpoint_timestamp_seconds", "Timestamp of the latest durable checkpoint", ["site"]
)
READY = Gauge(
    "arc_traffic_exporter_ready", "1 after startup replay is complete and normal tailing has begun", ["site"]
)


class ContinuityError(RuntimeError):
    """Raised when a saved boundary cannot be recovered without data loss."""


class OperationalMetrics:
    def initialize(self, site: str) -> None:
        for metric in (
            REPLAYED,
            PARSE_ERRORS,
            ROTATIONS,
            TRUNCATIONS,
            CHECKPOINT_ERRORS,
            DUPLICATES,
            PATH_OVERFLOW,
            RECOVERY_ERRORS,
        ):
            metric.labels(site)

    def checkpoint(self, site: str, offset: int, timestamp: float) -> None:
        CHECKPOINT_OFFSET.labels(site).set(offset)
        LAST_CHECKPOINT.labels(site).set(timestamp)

    def file_state(self, site: str, size: int, offset: int, last_event: Optional[float]) -> None:
        LOG_SIZE.labels(site).set(size)
        lag = max(0, size - offset)
        LAG_BYTES.labels(site).set(lag)
        if lag and last_event:
            LAG_SECONDS.labels(site).set(max(0, time.time() - last_event))
        else:
            LAG_SECONDS.labels(site).set(0)

    def replayed(self, site: str) -> None:
        REPLAYED.labels(site).inc()

    def parse_error(self, site: str) -> None:
        PARSE_ERRORS.labels(site).inc()

    def rotation(self, site: str) -> None:
        ROTATIONS.labels(site).inc()

    def truncation(self, site: str) -> None:
        TRUNCATIONS.labels(site).inc()

    def checkpoint_error(self, site: str) -> None:
        CHECKPOINT_ERRORS.labels(site).inc()

    def duplicate(self, site: str) -> None:
        DUPLICATES.labels(site).inc()

    def recovery_error(self, site: str) -> None:
        RECOVERY_ERRORS.labels(site).inc()

    def event(self, site: str, timestamp: Optional[float]) -> None:
        if timestamp:
            LAST_EVENT.labels(site).set(timestamp)


OPS = OperationalMetrics()


class PositionStore:
    """Human-readable per-site checkpoints written by fsync + atomic rename."""

    def __init__(self, directory: str, metrics: OperationalMetrics = OPS):
        self.directory = Path(directory)
        self.metrics = metrics

    def ensure(self) -> None:
        self.directory.mkdir(mode=0o750, parents=True, exist_ok=True)
        if not os.access(self.directory, os.R_OK | os.W_OK | os.X_OK):
            raise PermissionError(f"checkpoint directory is not accessible: {self.directory}")

    def path_for(self, site: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_-]+", site):
            raise ValueError(f"unsafe site identifier: {site!r}")
        return self.directory / f"{site}.json"

    def load(self, site: str) -> Optional[Dict]:
        path = self.path_for(site)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            self._validate(value)
            return value
        except Exception as exc:
            self.metrics.checkpoint_error(site)
            raise ContinuityError(f"invalid checkpoint {path}: {exc}") from exc

    @staticmethod
    def _validate(value: Dict) -> None:
        required = {
            "version": int,
            "canonical_path": str,
            "device": int,
            "inode": int,
            "offset": int,
            "last_successful_update": (int, float),
            "file_size": int,
            "file_mtime": (int, float),
            "recovery_pending": bool,
        }
        if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
            raise ValueError("unsupported checkpoint version")
        for key, expected in required.items():
            if key not in value or not isinstance(value[key], expected):
                raise ValueError(f"missing or invalid {key}")
        if value["offset"] < 0 or value["file_size"] < 0:
            raise ValueError("negative offset or file size")
        if value["offset"] > value["file_size"]:
            raise ValueError("checkpoint offset exceeds its recorded file size")
        digest = value.get("last_record_sha256")
        if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid last_record_sha256")

    def save(self, site: str, value: Dict) -> None:
        path = self.path_for(site)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        value = dict(value)
        value["version"] = STATE_VERSION
        value["last_successful_update"] = time.time()
        try:
            with temp.open("w", encoding="utf-8") as handle:
                os.chmod(temp, 0o600)
                json.dump(value, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            os.chmod(path, 0o600)
            directory_fd = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self.metrics.checkpoint(site, value["offset"], value["last_successful_update"])
        except Exception:
            self.metrics.checkpoint_error(site)
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
            raise

    def archive_existing(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for path in self.directory.glob("*.json"):
            os.replace(path, path.with_suffix(path.suffix + f".reset.{stamp}"))


def line_digest(line: bytes) -> str:
    return hashlib.sha256(line.rstrip(b"\r\n")).hexdigest()


def event_timestamp(line: bytes) -> Optional[float]:
    try:
        value = json.loads(line)
        timestamp = value.get("ts")
        return float(timestamp) if timestamp is not None else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def classify_ua(user_agent: str) -> str:
    value = str(user_agent or "").lower()
    if any(pattern in value for pattern in BOT_PATTERNS):
        return "bot"
    if "mozilla" in value or "webkit" in value or "gecko" in value:
        return "browser"
    if not value or value == "-":
        return "unknown"
    return "api_client"


def group_path(path: str) -> str:
    for pattern, group in PATH_GROUPS:
        if re.match(pattern, path):
            return group
    return "other"


def bounded_path_group(site: str, proposed: str) -> str:
    """Return only a fixed path-group label; arbitrary values collapse to other."""
    if proposed in PATH_GROUP_VOCABULARY:
        return proposed
    PATH_OVERFLOW.labels(site).inc()
    return "other"


def ip_prefix(ip: str) -> str:
    try:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
        return ip.split(":")[0] or "ipv6"
    except Exception:
        return "unknown"


def incorporate_record(site: str, line: bytes) -> Tuple[bool, Optional[float]]:
    """Parse and incorporate one complete record; return success and event time."""
    try:
        record = json.loads(line)
        request = record.get("request") or {}
        headers = request.get("headers") or {}
        status = str(record.get("status", 0))
        method = str(request.get("method") or "unknown").upper()
        size = max(0, int(record.get("size") or 0))
        duration = max(0.0, float(record.get("duration") or 0.0))
        uri = str(request.get("uri") or "/")
        path = uri.split("?", 1)[0]
        client_ip = request.get("client_ip") or request.get("remote_ip") or "unknown"
        user_agents = headers.get("User-Agent") or headers.get("user-agent") or []
        if isinstance(user_agents, list):
            user_agent = user_agents[0] if user_agents else ""
        else:
            user_agent = user_agents
        timestamp = float(record["ts"]) if record.get("ts") is not None else None
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False, None

    path_group = bounded_path_group(site, group_path(path))
    status_class = f"{status[0]}xx" if status and status[0].isdigit() else "unknown"
    ua_class = classify_ua(user_agent)
    network = ip_prefix(client_ip)
    REQUESTS.labels(site=site, method=method, status=status, path_group=path_group).inc()
    BYTES.labels(site=site).inc(size)
    STATUS_CLASS.labels(site=site, status_class=status_class).inc()
    UA_CLASS.labels(site=site, ua_class=ua_class).inc()
    DURATION.labels(site=site, path_group=path_group).observe(duration)
    now = time.time()
    with _state_lock:
        _path_counts[site][path_group] += 1
        _ip_counts[site][network] += 1
        _req_timestamps[site].append(now)
        _req_timestamps[site] = [item for item in _req_timestamps[site] if now - item < 60]
    return True, timestamp


def prime_record_labels(site: str, line: bytes):
    """Instantiate the bounded metric labels for a record without counting it."""
    try:
        record = json.loads(line)
        request = record.get("request") or {}
        headers = request.get("headers") or {}
        status = str(record.get("status", 0))
        method = str(request.get("method") or "unknown").upper()
        path = str(request.get("uri") or "/").split("?", 1)[0]
        user_agents = headers.get("User-Agent") or headers.get("user-agent") or []
        if isinstance(user_agents, list):
            user_agent = user_agents[0] if user_agents else ""
        else:
            user_agent = user_agents
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    path_group = bounded_path_group(site, group_path(path))
    status_class = f"{status[0]}xx" if status and status[0].isdigit() else "unknown"
    REQUESTS.labels(site=site, method=method, status=status, path_group=path_group)
    BYTES.labels(site=site)
    STATUS_CLASS.labels(site=site, status_class=status_class)
    UA_CLASS.labels(site=site, ua_class=classify_ua(user_agent))
    DURATION.labels(site=site, path_group=path_group)
    return method, status, path_group, status_class, classify_ua(user_agent)


def publish_rollup_gauges() -> None:
    with _state_lock:
        for site in list(_path_counts):
            bounded_counts = CollectionCounter()
            for proposed, count in _path_counts[site].items():
                path_group = bounded_path_group(site, proposed)
                bounded_counts[path_group] += count
            if len(bounded_counts) > MAX_PATH_SERIES_PER_SITE:
                raise RuntimeError(f"{site}: bounded path vocabulary exceeded its hard limit")
            current = {path for path, _count in bounded_counts.most_common(TOP_PATHS)}
            for stale in _published_path_groups[site] - current:
                TOP_PATH_GAUGE.remove(site, stale)
            for path, count in bounded_counts.most_common(TOP_PATHS):
                TOP_PATH_GAUGE.labels(site=site, path=path).set(count)
            _published_path_groups[site] = current
            for network, count in _ip_counts[site].most_common(20):
                TOP_IP_GAUGE.labels(site=site, ip_prefix=network).set(count)
            now = time.time()
            rpm = sum(1 for timestamp in _req_timestamps[site] if now - timestamp < 60)
            REQUESTS_PER_MINUTE.labels(site=site).set(rpm)


def rollup_gauges(stop_event: threading.Event) -> None:
    while not stop_event.wait(ROLLUP_INTERVAL):
        publish_rollup_gauges()


class DurableTailer:
    def __init__(
        self,
        site: str,
        path: str,
        store: PositionStore,
        handler: Callable[[str, bytes], Tuple[bool, Optional[float]]] = incorporate_record,
        metrics: OperationalMetrics = OPS,
        poll_interval: float = 0.5,
        initial_policy: str = "end",
        backfill_since: Optional[float] = None,
    ):
        self.site = site
        self.path = Path(path).resolve()
        self.store = store
        self.handler = handler
        self.metrics = metrics
        self.poll_interval = poll_interval
        self.initial_policy = initial_policy
        self.backfill_since = backfill_since
        self.handle = None
        self.device = 0
        self.inode = 0
        self.offset = 0
        self.last_hash = None
        self.last_event = None
        self._old_eof_polls = 0
        self._primed_label_sets = set()

    def _checkpoint(self, *, recovery_pending: bool = False, stat_result=None) -> None:
        stat_result = stat_result or os.fstat(self.handle.fileno())
        value = {
            "canonical_path": str(self.path),
            "device": int(self.device),
            "inode": int(self.inode),
            "offset": int(self.offset),
            "last_event_timestamp": self.last_event,
            "last_record_sha256": self.last_hash,
            "file_size": int(stat_result.st_size),
            "file_mtime": float(stat_result.st_mtime),
            "recovery_pending": recovery_pending,
        }
        self.store.save(self.site, value)
        self.metrics.file_state(self.site, stat_result.st_size, self.offset, self.last_event)

    def _open_active(self, offset: int) -> None:
        handle = self.path.open("rb")
        stat_result = os.fstat(handle.fileno())
        if offset > stat_result.st_size:
            handle.close()
            raise ContinuityError(
                f"{self.site}: checkpoint offset {offset} exceeds active log size {stat_result.st_size}"
            )
        handle.seek(offset)
        if self.handle:
            self.handle.close()
        self.handle = handle
        self.device = stat_result.st_dev
        self.inode = stat_result.st_ino
        self.offset = offset
        self._old_eof_polls = 0

    def _recovery_failure(self, message: str):
        self.metrics.recovery_error(self.site)
        raise ContinuityError(f"{self.site}: {message}")

    def _archive_scheme_and_order(self, path: Path, stat_result):
        base = re.escape(self.path.name[:-4] if self.path.name.endswith(".log") else self.path.name)
        timestamped = re.fullmatch(
            rf"{base}-(\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}-\d{{2}}-\d{{2}}(?:\.\d+)?)(?:-[^.]+)?\.log(?:\.gz)?",
            path.name,
        )
        if timestamped:
            value = timestamped.group(1)
            fmt = "%Y-%m-%dT%H-%M-%S.%f" if "." in value else "%Y-%m-%dT%H-%M-%S"
            try:
                timestamp = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp()
                return "timestamp", (timestamp, path.name)
            except ValueError:
                self._recovery_failure(f"unparseable rotation timestamp in {path.name}")
        numbered = re.fullmatch(rf"{re.escape(self.path.name)}\.(\d+)(?:\.gz)?", path.name)
        if numbered:
            return "numbered", (-int(numbered.group(1)), path.name)
        self._recovery_failure(f"unrecognized rotation ordering scheme for {path.name}")

    def _rotation_candidates(self) -> Iterable[Path]:
        parent = self.path.parent.resolve(strict=True)
        base_name = self.path.name[:-4] if self.path.name.endswith(".log") else self.path.name
        escaped_base = re.escape(base_name)
        escaped_active = re.escape(self.path.name)
        allowed_name = re.compile(
            rf"(?:{escaped_base}-\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}-\d{{2}}-\d{{2}}(?:\.\d+)?(?:-[^.]+)?\.log(?:\.gz)?|"
            rf"{escaped_active}\.\d+(?:\.gz)?)"
        )
        patterns = (
            str(parent / f"{base_name}-*.log"),
            str(parent / f"{base_name}-*.log.gz"),
            str(parent / f"{self.path.name}.*"),
        )
        candidate_paths = set()
        for pattern in patterns:
            candidate_paths.update(Path(item) for item in glob.glob(pattern))
        candidate_paths.discard(self.path)
        validated = []
        total_bytes = 0
        now = time.time()
        for candidate in candidate_paths:
            if candidate.parent.resolve(strict=True) != parent or not allowed_name.fullmatch(candidate.name):
                self._recovery_failure(f"unsafe or unrelated rotation candidate {candidate}")
            try:
                candidate_lstat = candidate.lstat()
            except OSError as exc:
                self._recovery_failure(f"cannot inspect rotation candidate {candidate.name}: {exc}")
            if stat.S_ISLNK(candidate_lstat.st_mode) or not stat.S_ISREG(candidate_lstat.st_mode):
                self._recovery_failure(f"rotation candidate is not a regular non-symlink file: {candidate.name}")
            resolved = candidate.resolve(strict=True)
            if resolved.parent != parent:
                self._recovery_failure(f"rotation candidate escapes active log directory: {candidate.name}")
            age = now - candidate_lstat.st_mtime
            if age > MAX_ARCHIVE_AGE_SECONDS:
                self._recovery_failure(f"rotation candidate exceeds {MAX_ARCHIVE_AGE_SECONDS}s age limit: {candidate.name}")
            total_bytes += candidate_lstat.st_size
            if total_bytes > MAX_ARCHIVE_BYTES:
                self._recovery_failure(f"rotation candidates exceed {MAX_ARCHIVE_BYTES} cumulative bytes")
            scheme, order_key = self._archive_scheme_and_order(resolved, candidate_lstat)
            validated.append((resolved, candidate_lstat, scheme, order_key))
        if len(validated) > MAX_ROTATED_ARCHIVES:
            self._recovery_failure(f"rotation candidates exceed {MAX_ROTATED_ARCHIVES} archive limit")
        schemes = {item[2] for item in validated}
        if len(schemes) > 1:
            self._recovery_failure("mixed timestamped and numbered rotation schemes are ambiguous")
        ordered = [item[0] for item in sorted(validated, key=lambda item: item[3])]
        ordered.append(self.path)
        return ordered

    @staticmethod
    def _open_candidate(path: Path):
        return gzip.open(path, "rb") if path.name.endswith(".gz") else path.open("rb")

    @staticmethod
    def _complete_lines(handle):
        while True:
            line = handle.readline()
            if not line or not line.endswith(b"\n"):
                return
            yield line

    @staticmethod
    def _boundary_matches_at(handle, offset: int, digest: Optional[str]) -> bool:
        if offset == 0:
            return digest is None
        if not digest:
            return False
        saved_position = handle.tell()
        window_start = max(0, offset - 1024 * 1024)
        try:
            handle.seek(window_start)
            data = handle.read(offset - window_start)
        finally:
            handle.seek(saved_position)
        if not data.endswith(b"\n"):
            return False
        lines = data.rstrip(b"\r\n").splitlines()
        if not lines:
            return False
        return hashlib.sha256(lines[-1]).hexdigest() == digest

    def prime_replay_labels(self) -> int:
        """Read only the pending backlog and create zero-valued label series."""
        checkpoint = self.store.load(self.site)
        if checkpoint is None:
            return 0
        active_stat = self.path.stat()
        count = 0
        same_inode = (checkpoint["device"], checkpoint["inode"]) == (
            active_stat.st_dev,
            active_stat.st_ino,
        )
        if same_inode and not checkpoint.get("recovery_pending"):
            offset = checkpoint["offset"] if active_stat.st_size >= checkpoint["offset"] else 0
            with self.path.open("rb") as handle:
                if offset and not self._boundary_matches_at(
                    handle, offset, checkpoint.get("last_record_sha256")
                ):
                    offset = 0
                handle.seek(offset)
                for line in self._complete_lines(handle):
                    labels = prime_record_labels(self.site, line)
                    if labels is not None and labels not in self._primed_label_sets:
                        self._primed_label_sets.add(labels)
                        count += 1
            return count

        boundary = checkpoint.get("last_record_sha256")
        if not boundary:
            if checkpoint["offset"] == 0 and checkpoint["file_size"] == 0:
                with self.path.open("rb") as handle:
                    for line in self._complete_lines(handle):
                        labels = prime_record_labels(self.site, line)
                        if labels is not None and labels not in self._primed_label_sets:
                            self._primed_label_sets.add(labels)
                            count += 1
                return count
            self._recovery_failure("cannot prime a rotated checkpoint without a boundary hash")
        candidates = list(self._rotation_candidates())
        matches = []
        for candidate_index, candidate in enumerate(candidates):
            with self._open_candidate(candidate) as handle:
                for line in self._complete_lines(handle):
                    if line_digest(line) == boundary:
                        matches.append((candidate_index, handle.tell()))
        if len(matches) != 1:
            self._recovery_failure(
                f"cannot prime ambiguous/missing retained boundary ({len(matches)} matches)"
            )
        boundary_candidate, boundary_offset = matches[0]
        for candidate_index, candidate in enumerate(candidates):
            if candidate_index < boundary_candidate:
                continue
            with self._open_candidate(candidate) as handle:
                if candidate_index == boundary_candidate:
                    handle.seek(boundary_offset)
                for line in self._complete_lines(handle):
                    labels = prime_record_labels(self.site, line)
                    if labels is not None and labels not in self._primed_label_sets:
                        self._primed_label_sets.add(labels)
                        count += 1
        return count

    def _consume(self, line: bytes, *, replay: bool, checkpoint: bool = True) -> None:
        ok, timestamp = self.handler(self.site, line)
        if not ok:
            self.metrics.parse_error(self.site)
        elif timestamp:
            self.last_event = timestamp
            self.metrics.event(self.site, timestamp)
        self.last_hash = line_digest(line)
        if replay:
            self.metrics.replayed(self.site)
        if checkpoint:
            self._checkpoint(recovery_pending=replay)

    def _initial_eof(self) -> None:
        self._open_active(0)
        last_complete_offset = 0
        last_line = None
        while True:
            start = self.handle.tell()
            line = self.handle.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                self.handle.seek(start)
                break
            last_complete_offset = self.handle.tell()
            last_line = line
        self.offset = last_complete_offset
        self.handle.seek(self.offset)
        if last_line:
            self.last_hash = line_digest(last_line)
            self.last_event = event_timestamp(last_line)
        self._checkpoint()
        LOG.info("%s: initial deployment checkpointed at EOF offset %d", self.site, self.offset)

    def _initial_beginning(self) -> None:
        self._open_active(0)
        self._checkpoint()
        self._drain(replay=True)
        self._checkpoint(recovery_pending=False)

    def _initial_backfill(self) -> None:
        active_stat = self.path.stat()
        self._open_active(0)
        found_any = False
        for candidate in self._rotation_candidates():
            with self._open_candidate(candidate) as handle:
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        break
                    timestamp = event_timestamp(line)
                    if timestamp is None or timestamp < self.backfill_since:
                        continue
                    found_any = True
                    if candidate == self.path:
                        self.offset = handle.tell()
                    else:
                        self.device, self.inode = active_stat.st_dev, active_stat.st_ino
                        self.offset = 0
                    self._consume(line, replay=True, checkpoint=True)
        self._open_active(self.path.stat().st_size)
        self._checkpoint()
        LOG.info("%s: bounded backfill completed (records=%s)", self.site, "present" if found_any else "none")

    def _recover_rotated(self, checkpoint: Dict) -> None:
        boundary = checkpoint.get("last_record_sha256")
        if not boundary:
            if checkpoint["offset"] == 0 and checkpoint["file_size"] == 0:
                self._open_active(0)
                self._checkpoint(recovery_pending=False)
                self.metrics.rotation(self.site)
                LOG.info("%s: recovered an empty rotated log at active offset zero", self.site)
                return
            self._recovery_failure("rotated checkpoint has no record boundary hash")
        candidates = list(self._rotation_candidates())
        matches = []
        for candidate_index, candidate in enumerate(candidates):
            with self._open_candidate(candidate) as handle:
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        break
                    if line_digest(line) == boundary:
                        matches.append((candidate_index, handle.tell()))
        if len(matches) != 1:
            detail = "not found" if not matches else f"ambiguous ({len(matches)} matches)"
            self._recovery_failure(
                f"saved boundary is {detail} in retained rotated logs; refusing to skip to EOF"
            )

        boundary_candidate, boundary_offset = matches[0]
        active_offset = 0
        active_stat = self.path.stat()
        self._open_active(0)
        for candidate_index, candidate in enumerate(candidates):
            if candidate_index < boundary_candidate:
                continue
            with self._open_candidate(candidate) as handle:
                if candidate_index == boundary_candidate:
                    handle.seek(boundary_offset)
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        break
                    if candidate == self.path:
                        active_offset = handle.tell()
                        self.offset = active_offset
                    else:
                        self.device, self.inode = active_stat.st_dev, active_stat.st_ino
                        self.offset = 0
                    self._consume(line, replay=True, checkpoint=True)
        self._open_active(active_offset)
        self._checkpoint(recovery_pending=False)
        self.metrics.rotation(self.site)
        LOG.info("%s: recovered across retained rotation boundary to offset %d", self.site, active_offset)

    def prepare(self) -> None:
        self.metrics.initialize(self.site)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        checkpoint = self.store.load(self.site)
        if checkpoint is None:
            if self.backfill_since is not None:
                self._initial_backfill()
            elif self.initial_policy == "beginning":
                self._initial_beginning()
            else:
                self._initial_eof()
            return
        if Path(checkpoint["canonical_path"]).resolve() != self.path:
            raise ContinuityError(f"{self.site}: checkpoint path does not match configured log")
        active_stat = self.path.stat()
        self.last_hash = checkpoint.get("last_record_sha256")
        self.last_event = checkpoint.get("last_event_timestamp")
        if checkpoint.get("recovery_pending"):
            self._recover_rotated(checkpoint)
            return
        if (checkpoint["device"], checkpoint["inode"]) == (active_stat.st_dev, active_stat.st_ino):
            offset = checkpoint["offset"]
            if active_stat.st_size < offset:
                self.metrics.truncation(self.site)
                LOG.warning("%s: copytruncate detected; restarting active inode at byte zero", self.site)
                offset = 0
                self.last_hash = None
            self._open_active(offset)
            if offset and not self._boundary_matches_at(self.handle, offset, self.last_hash):
                self.metrics.truncation(self.site)
                LOG.warning(
                    "%s: saved boundary hash does not match the same inode at offset %d; "
                    "stopped-period truncation/rewrite detected, replaying from byte zero",
                    self.site,
                    offset,
                )
                self.handle.seek(0)
                self.offset = 0
                self.last_hash = None
            self._checkpoint()
            self._drain(replay=True)
            self._checkpoint(recovery_pending=False)
        else:
            self._recover_rotated(checkpoint)

    def _drain(self, *, replay: bool) -> int:
        count = 0
        while True:
            start = self.handle.tell()
            line = self.handle.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                self.handle.seek(start)
                break
            self.offset = self.handle.tell()
            self._consume(line, replay=replay)
            count += 1
        return count

    def _boundary_matches(self) -> bool:
        """Verify the complete record immediately before the current offset."""
        return self._boundary_matches_at(self.handle, self.offset, self.last_hash)

    def poll_once(self) -> int:
        current_stat = os.fstat(self.handle.fileno())
        if current_stat.st_size < self.offset or not self._boundary_matches():
            self.metrics.truncation(self.site)
            LOG.warning("%s: active inode was truncated or rewritten; reading from byte zero", self.site)
            self.handle.seek(0)
            self.offset = 0
            self.last_hash = None
            self._checkpoint()
        count = self._drain(replay=False)
        try:
            active_stat = self.path.stat()
        except FileNotFoundError:
            return count
        if (active_stat.st_dev, active_stat.st_ino) != (self.device, self.inode):
            if self.handle.tell() < os.fstat(self.handle.fileno()).st_size:
                return count
            self._old_eof_polls += 1
            if self._old_eof_polls >= 2:
                self.metrics.rotation(self.site)
                self._open_active(0)
                self.last_hash = None
                self._checkpoint()
                count += self._drain(replay=False)
                LOG.info("%s: switched to newly created active log", self.site)
        else:
            self._old_eof_polls = 0
            self.metrics.file_state(self.site, active_stat.st_size, self.offset, self.last_event)
        return count

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception:
                LOG.exception("%s: tailing failure", self.site)

    def close(self) -> None:
        if self.handle:
            self.handle.close()
            self.handle = None


def parse_backfill_since(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.getenv("CADDY_EXPORTER_PORT", DEFAULT_PORT)))
    parser.add_argument("--state-dir", default=os.getenv("CADDY_EXPORTER_STATE_DIR", DEFAULT_STATE_DIR))
    parser.add_argument("--start-at-beginning", action="store_true")
    parser.add_argument("--backfill-since", type=parse_backfill_since)
    parser.add_argument("--positions-reset", action="store_true")
    parser.add_argument("--initialize-positions-only", action="store_true")
    parser.add_argument(
        "--scrape-grace-seconds",
        type=float,
        default=float(os.getenv("CADDY_EXPORTER_SCRAPE_GRACE_SECONDS", "20")),
        help="expose reset counters for this long before startup replay",
    )
    parser.add_argument("--log", action="append", metavar="SITE=PATH", help="override configured logs (repeatable)")
    args = parser.parse_args(argv)
    if args.start_at_beginning and args.backfill_since is not None:
        parser.error("--start-at-beginning and --backfill-since are mutually exclusive")
    return args


def configured_logs(overrides) -> Dict[str, str]:
    if not overrides:
        return dict(LOGS)
    result = {}
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"invalid --log value: {item!r}")
        site, path = item.split("=", 1)
        result[site] = path
    return result


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = PositionStore(args.state_dir)
    store.ensure()
    if args.positions_reset:
        store.archive_existing()
        LOG.warning("existing positions archived by explicit operator request")

    tailers = [
        DurableTailer(
            site,
            path,
            store,
            initial_policy="beginning" if args.start_at_beginning else "end",
            backfill_since=args.backfill_since,
        )
        for site, path in configured_logs(args.log).items()
    ]

    if args.initialize_positions_only:
        try:
            for tailer in tailers:
                tailer.prepare()
        except Exception:
            LOG.exception("position initialization failed")
            for tailer in tailers:
                tailer.close()
            return 1
        for tailer in tailers:
            tailer.close()
        LOG.info("durable positions initialized; HTTP server was not started")
        return 0

    stop_event = threading.Event()

    def stop(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for tailer in tailers:
            OPS.initialize(tailer.site)
            READY.labels(tailer.site).set(0)
            BYTES.labels(site=tailer.site)
            for status_class in ("1xx", "2xx", "3xx", "4xx", "5xx", "unknown"):
                STATUS_CLASS.labels(site=tailer.site, status_class=status_class)
            primed = tailer.prime_replay_labels()
            LOG.info("%s: primed %d pending metric label combinations", tailer.site, primed)
    except Exception:
        LOG.exception("startup continuity preflight failed before opening the metrics port")
        return 1
    start_http_server(args.port)
    LOG.info(
        "exporter listening on :%d; waiting %.1fs for a reset baseline scrape before replay",
        args.port,
        args.scrape_grace_seconds,
    )
    grace = max(0, args.scrape_grace_seconds)
    while True:
        if stop_event.wait(grace):
            return 0
        newly_primed = 0
        try:
            for tailer in tailers:
                new_labels = tailer.prime_replay_labels()
                newly_primed += new_labels
                if new_labels:
                    LOG.info("%s: primed %d new label combinations during scrape grace", tailer.site, new_labels)
        except Exception:
            LOG.exception("startup continuity preflight failed during scrape grace")
            return 1
        if newly_primed == 0:
            break
        LOG.info("waiting another %.1fs so newly primed zero series are scraped", grace)

    prepared = []
    try:
        for tailer in tailers:
            tailer.prepare()
            prepared.append(tailer)
            READY.labels(tailer.site).set(1)
    except Exception:
        LOG.exception("startup continuity validation failed")
        for tailer in prepared:
            tailer.close()
        return 1
    threads = []
    rollup_thread = threading.Thread(target=rollup_gauges, args=(stop_event,), name="rollup", daemon=True)
    rollup_thread.start()
    threads.append(rollup_thread)
    for tailer in tailers:
        thread = threading.Thread(target=tailer.run, args=(stop_event,), name=f"tail-{tailer.site}", daemon=True)
        thread.start()
        threads.append(thread)
    LOG.info("exporter listening on :%d with %d durable log tailers", args.port, len(tailers))
    while not stop_event.wait(1):
        pass
    for thread in threads:
        thread.join(timeout=2)
    for tailer in tailers:
        tailer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
