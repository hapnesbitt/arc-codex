import contextlib
import json
import gzip
import os
import re
import shlex
import shutil
import ctypes
import ctypes.util
import threading
import socket
import subprocess
import tempfile
import time
import uuid
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
LOKI_CONFIG = REPO_ROOT / "monitoring" / "loki" / "loki-config.yml"
ALLoy_IMAGE = "grafana/alloy:v1.16.1"
LOKI_IMAGE = "grafana/loki:3.7.2@sha256:191d4fdfb7264f16989f0a57f320872620a5a7c2ceeec6229212c4190ec49b86"
TARGETS = {
    "arc-codex-access.log": ("arc", "arc-codex"),
    "huntaegis-access.log": ("huntaegis", "huntaegis"),
    "dlb-access.log": ("dlb", "dlb"),
    "soc-access.log": ("school_of_chat", "soc"),
    "plantorium-access.log": ("plantorium", "plantorium"),
    "athena-access.log": ("athena", "athena"),
    "mark-access.log": ("mark", "mark"),
    "holmes-access.log": ("holmes", "holmes"),
    "beowulf-access.log": ("beowulf", "beowulf"),
}
ALLOWED_LABELS = {"job", "environment", "site", "logger", "method", "status_class", "protocol"}
ALLOWED_FIELDS = {
    "timestamp",
    "site",
    "host",
    "method",
    "path",
    "status",
    "status_class",
    "duration_seconds",
    "response_size_bytes",
    "protocol",
    "client_ip",
    "remote_ip",
    "user_agent",
    "referer",
    "tls_version",
    "tls_cipher",
}
METHODS = {"GET", "POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"}

_SNAPPY_LIB = ctypes.CDLL(ctypes.util.find_library("snappy"))
_SNAPPY_LIB.snappy_uncompressed_length.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_SNAPPY_LIB.snappy_uncompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)]


def decompress_snappy(payload):
    out_len = ctypes.c_size_t()
    if _SNAPPY_LIB.snappy_uncompressed_length(payload, len(payload), ctypes.byref(out_len)) != 0:
        raise RuntimeError("snappy length decode failed")
    out = ctypes.create_string_buffer(out_len.value)
    out_len2 = ctypes.c_size_t(out_len.value)
    if _SNAPPY_LIB.snappy_uncompress(payload, len(payload), out, ctypes.byref(out_len2)) != 0:
        raise RuntimeError("snappy decode failed")
    return out.raw[:out_len2.value]


def docker(*args, check=True, capture_output=True):
    proc = subprocess.run(
        ["docker", *args],
        text=True,
        capture_output=capture_output,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "docker command failed:\n"
            f"cmd: {' '.join(shlex.quote(part) for part in ['docker', *args])}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def allocate_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(url, expected=200, timeout=60):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status == expected:
                    return resp.read()
                last_error = f"unexpected status {resp.status}"
        except Exception as exc:  # pragma: no cover - exercised in retry loops.
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {url}: {last_error}")


def wait_query(port, query, timeout=90):
    deadline = time.monotonic() + timeout
    now = time.time()
    params = {
        "query": query,
        "start": str(int((now - 300) * 1_000_000_000)),
        "end": str(int(now * 1_000_000_000)),
        "limit": "200",
    }
    url = f"http://127.0.0.1:{port}/loki/api/v1/query_range?{urlencode(params)}"
    last = None
    while time.monotonic() < deadline:
        try:
            payload = json.loads(wait_http(url, timeout=10))
            return payload["data"]["result"]
        except Exception as exc:  # pragma: no cover - retry helper.
            last = exc
        time.sleep(0.5)
    raise AssertionError(f"query failed for {query}: {last}")


def find_lines(results):
    lines = []
    for item in results:
        labels = item["stream"]
        for _, line in item["values"]:
            lines.append((labels, line))
    return lines


def stringify_scalars(value):
    if isinstance(value, dict):
        return {key: stringify_scalars(val) for key, val in value.items()}
    if isinstance(value, list):
        return [stringify_scalars(val) for val in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def wait_captured_entry(capture, marker, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for text in capture.entries():
            if marker not in text:
                continue
            label_match = re.search(
                r'\{environment="([^"]+)", job="([^"]+)", logger="([^"]+)", method="([^"]+)", protocol="([^"]+)", site="([^"]+)", status_class="([^"]+)"\}',
                text,
            )
            line_match = re.search(r'(\{"client_ip":.*?\})', text)
            if line_match is None:
                line_match = re.search(r'(\{"timestamp":.*?\})', text)
            if label_match and line_match:
                labels = {
                    "environment": label_match.group(1),
                    "job": label_match.group(2),
                    "logger": label_match.group(3),
                    "method": label_match.group(4),
                    "protocol": label_match.group(5),
                    "site": label_match.group(6),
                    "status_class": label_match.group(7),
                }
                return labels, line_match.group(1)
        time.sleep(0.5)
    raise AssertionError(f"no captured Loki push for marker {marker}")


def render_config(tmp_root, push_url):
    alloy_config = (ROOT / "config.alloy").read_text(encoding="utf-8")
    alloy_config = alloy_config.replace(
        "http://127.0.0.1:3100/loki/api/v1/push",
        push_url,
    )
    config_path = tmp_root / "config.alloy"
    config_path.write_text(alloy_config, encoding="utf-8")
    return config_path


def make_record(*, ts, host, method="GET", uri="/", status=200, size=1234, duration=0.125,
                client_ip="198.51.100.7", remote_ip="203.0.113.9", proto="HTTP/2.0",
                headers=None, resp_headers=None, tls_version=772, tls_cipher=4865):
    request = {
        "remote_ip": remote_ip,
        "client_ip": client_ip,
        "proto": proto,
        "method": method,
        "host": host,
        "uri": uri,
    }
    if headers is not None:
        request["headers"] = headers
    if tls_version is not None or tls_cipher is not None:
        request["tls"] = {"version": tls_version, "cipher_suite": tls_cipher}
    record = {
        "ts": ts,
        "request": request,
        "status": status,
        "size": size,
        "duration": duration,
    }
    if resp_headers is not None:
        record["resp_headers"] = resp_headers
    return record


def write_line(path, line):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextlib.contextmanager
def running_container(args):
    proc = docker("run", "-d", *args)
    cid = proc.stdout.strip()
    try:
        yield cid
    finally:
        docker("rm", "-f", cid, check=False)


class PushCaptureServer:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="alloy-push-")
        self.root = Path(self.tmp.name)
        self.port = allocate_port()
        self.requests = []
        self.lock = threading.Lock()

        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - stdlib callback naming.
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length)
                if self.headers.get("Content-Encoding") == "gzip" or payload.startswith(b"\x1f\x8b"):
                    payload = gzip.decompress(payload)
                elif self.headers.get("Content-Encoding") == "snappy" or payload[:1] in (b"\x8f", b"\x82", b"\x01"):
                    payload = decompress_snappy(payload)
                with parent.lock:
                    parent.requests.append(payload)
                self.send_response(204)
                self.end_headers()

            def log_message(self, format, *args):  # noqa: A003 - stdlib callback naming.
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/loki/api/v1/push"

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.tmp.cleanup()

    def entries(self):
        parsed = []
        with self.lock:
            for payload in self.requests:
                parsed.append(payload.decode("latin1", errors="ignore"))
        return parsed


class AlloyHarness:
    def __init__(self, push_url=None):
        self.tmp = tempfile.TemporaryDirectory(prefix="alloy-int-")
        self.root = Path(self.tmp.name)
        self.log_root = self.root / "caddy"
        self.alloy_state = self.root / "alloy-state"
        self.loki_state = self.root / "loki-state"
        self.log_root.mkdir()
        self.alloy_state.mkdir()
        self.loki_state.mkdir()
        (self.alloy_state / "loki.source.file.caddy_access").mkdir(parents=True)
        (self.alloy_state / "loki.write.local" / "wal").mkdir(parents=True)
        self.loki_port = allocate_port()
        self.alloy_port = allocate_port()
        self.config_path = render_config(self.root, push_url or f"http://127.0.0.1:{self.loki_port}/loki/api/v1/push")
        self.loki_name = f"test-loki-{uuid.uuid4().hex[:12]}"
        self.alloy_name = f"test-alloy-{uuid.uuid4().hex[:12]}"
        self.loki_cid = None
        self.alloy_cid = None

    def set_push_url(self, push_url):
        self.config_path = render_config(self.root, push_url)

    def cleanup(self):
        if self.alloy_cid:
            docker("rm", "-f", self.alloy_cid, check=False)
        if self.loki_cid:
            docker("rm", "-f", self.loki_cid, check=False)
        self.tmp.cleanup()

    def start_loki(self):
        args = [
            "run",
            "-d",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--name", self.loki_name,
            "-p", f"127.0.0.1:{self.loki_port}:3100",
            "-v", f"{LOKI_CONFIG}:/etc/loki/loki-config.yml:ro",
            "-v", f"{self.loki_state}:/loki",
            LOKI_IMAGE,
            "-config.file=/etc/loki/loki-config.yml",
            "-target=all",
        ]
        self.loki_cid = docker(*args).stdout.strip()
        wait_http(f"http://127.0.0.1:{self.loki_port}/ready", expected=200, timeout=60)
        wait_http(f"http://127.0.0.1:{self.loki_port}/metrics", expected=200, timeout=60)

    def stop_loki(self):
        if self.loki_cid:
            docker("stop", "-t", "5", self.loki_cid, check=False)

    def restart_loki(self):
        if self.loki_cid:
            docker("start", self.loki_cid)
        wait_http(f"http://127.0.0.1:{self.loki_port}/ready", expected=200, timeout=90)

    def start_alloy(self):
        args = [
            "run",
            "-d",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--network", "host",
            "--name", self.alloy_name,
            "-v", f"{self.config_path}:/etc/alloy/config.alloy:ro",
            "-v", f"{self.log_root}:/var/log/caddy:ro",
            "-v", f"{self.alloy_state}:/var/lib/alloy",
            ALLoy_IMAGE,
            "run",
            "--stability.level=experimental",
            "--disable-reporting",
            f"--server.http.listen-addr=127.0.0.1:{self.alloy_port}",
            "--storage.path=/var/lib/alloy",
            "/etc/alloy/config.alloy",
        ]
        self.alloy_cid = docker(*args).stdout.strip()
        wait_http(f"http://127.0.0.1:{self.alloy_port}/metrics", expected=200, timeout=90)

    def stop_alloy(self):
        if self.alloy_cid:
            docker("stop", "-t", "5", self.alloy_cid, check=False)

    def restart_alloy(self):
        if self.alloy_cid:
            docker("restart", "-t", "5", self.alloy_cid)
        wait_http(f"http://127.0.0.1:{self.alloy_port}/metrics", expected=200, timeout=90)

    def query(self, selector, marker, timeout=120):
        q = f'{selector} |= "{marker}"'
        return wait_query(self.loki_port, q, timeout=timeout)

    def assert_entry(self, selector, marker, expected_body, expected_labels, timeout=120):
        deadline = time.monotonic() + timeout
        lines = []
        while time.monotonic() < deadline:
            lines = find_lines(self.query(selector, marker, timeout=15))
            if lines:
                break
            time.sleep(0.5)
        assert lines, f"no Loki line for marker {marker}"
        assert len(lines) == 1, lines
        labels, line = lines[0]
        assert set(labels) == ALLOWED_LABELS, labels
        assert labels == expected_labels, labels
        body = json.loads(line)
        assert set(body) == ALLOWED_FIELDS, body
        assert body == stringify_scalars(expected_body), body
        rendered = json.dumps(body, sort_keys=True)
        for forbidden in expected_body.get("_forbidden", []):
            assert forbidden not in rendered, forbidden


class AlloyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.harness = AlloyHarness()

    def tearDown(self):
        self.harness.cleanup()

    def test_real_pipeline_reconstructs_bodies_and_labels(self):
        capture = PushCaptureServer()
        self.addCleanup(capture.close)
        self.harness.set_push_url(capture.url)
        base = int(time.time())

        cases = [
            (
                "arc-codex-access.log",
                "ARCMARKER1",
                make_record(
                    ts=base,
                    host="arc-codex.com",
                    uri="/articles/ARCMARKER1?access_token=FAKE_TOKEN#fragment",
                    headers={
                        "User-Agent": ["SyntheticBrowser/1.0\nInjected"],
                        "Referer": ["https://search.example/results?q=FAKE_QUERY"],
                        "Authorization": ["Bearer FAKE_AUTH_SECRET"],
                        "Cookie": ["session=FAKE_COOKIE_SECRET"],
                        "X-Sentry-Trace": ["FAKE_TRACE_SECRET"],
                        "X-Trace-Id": ["FAKE_TRACE_ID"],
                        "X-Request-Id": ["FAKE_REQUEST_ID"],
                    },
                    resp_headers={
                        "Set-Cookie": ["session=FAKE_SET_COOKIE_SECRET"],
                        "Authorization": ["FAKE_RESPONSE_SECRET"],
                    },
                ),
                {
                    "timestamp": base,
                    "site": "arc",
                    "host": "arc-codex.com",
                    "method": "GET",
                    "path": "/articles/ARCMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "arc", "logger": "arc-codex", "method": "GET", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "huntaegis-access.log",
                "HUNTMARKER1",
                make_record(
                    ts=base + 1,
                    host="www.huntaegis.com",
                    uri="/rss/HUNTMARKER1.xml?key=FAKE_QUERY",
                    method="HEAD",
                    proto="HTTP/3.0",
                    client_ip="2001:db8::10",
                    remote_ip="2001:db8::20",
                    headers={
                        "User-Agent": ["AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" * 40],
                        "Referer": ["https://ref.example/path?oauth_token=FAKE_OAUTH"],
                        "Proxy-Authorization": ["FAKE_PROXY_AUTH"],
                    },
                ),
                {
                    "timestamp": base + 1,
                    "site": "huntaegis",
                    "host": "huntaegis.com",
                    "method": "HEAD",
                    "path": "/rss/HUNTMARKER1.xml",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http3",
                    "client_ip": "2001:db8::10",
                    "remote_ip": "2001:db8::20",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "huntaegis", "logger": "huntaegis", "method": "HEAD", "status_class": "2xx", "protocol": "http3"},
            ),
            (
                "soc-access.log",
                "SOCMARKER1",
                make_record(
                    ts=base + 2,
                    host="soc.arc-codex.com",
                    uri="/content/SOCMARKER1?oauth_token=FAKE_OAUTH#frag",
                    method="POST",
                    proto="HTTP/1.1",
                ),
                {
                    "timestamp": base + 2,
                    "site": "school_of_chat",
                    "host": "soc.arc-codex.com",
                    "method": "POST",
                    "path": "/content/SOCMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http1",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "school_of_chat", "logger": "soc", "method": "POST", "status_class": "2xx", "protocol": "http1"},
            ),
            (
                "dlb-access.log",
                "DLBMARKER1",
                make_record(
                    ts=base + 3,
                    host="dlb.arc-codex.com",
                    uri="/dlb/DLBMARKER1?access_token=FAKE_TOKEN#frag",
                    method="PUT",
                ),
                {
                    "timestamp": base + 3,
                    "site": "dlb",
                    "host": "dlb.arc-codex.com",
                    "method": "PUT",
                    "path": "/dlb/DLBMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "dlb", "logger": "dlb", "method": "PUT", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "plantorium-access.log",
                "PLANTMARKER1",
                make_record(
                    ts=base + 4,
                    host="plantorium.arc-codex.com",
                    uri="/plantorium/PLANTMARKER1?access_token=FAKE_TOKEN#frag",
                    method="PATCH",
                ),
                {
                    "timestamp": base + 4,
                    "site": "plantorium",
                    "host": "plantorium.arc-codex.com",
                    "method": "PATCH",
                    "path": "/plantorium/PLANTMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "plantorium", "logger": "plantorium", "method": "PATCH", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "athena-access.log",
                "ATHENAMARKER1",
                make_record(
                    ts=base + 5,
                    host="athena.arc-codex.com",
                    uri="/athena/ATHENAMARKER1?access_token=FAKE_TOKEN#frag",
                    method="DELETE",
                ),
                {
                    "timestamp": base + 5,
                    "site": "athena",
                    "host": "athena.arc-codex.com",
                    "method": "DELETE",
                    "path": "/athena/ATHENAMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "athena", "logger": "athena", "method": "DELETE", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "mark-access.log",
                "MARKMARKER1",
                make_record(
                    ts=base + 6,
                    host="mark.arc-codex.com",
                    uri="/mark/MARKMARKER1?access_token=FAKE_TOKEN#frag",
                    method="OPTIONS",
                ),
                {
                    "timestamp": base + 6,
                    "site": "mark",
                    "host": "mark.arc-codex.com",
                    "method": "OPTIONS",
                    "path": "/mark/MARKMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "mark", "logger": "mark", "method": "OPTIONS", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "holmes-access.log",
                "HOLMESMARKER1",
                make_record(
                    ts=base + 7,
                    host="holmes.arc-codex.com",
                    uri="/holmes/HOLMESMARKER1?access_token=FAKE_TOKEN#frag",
                    method="GET",
                ),
                {
                    "timestamp": base + 7,
                    "site": "holmes",
                    "host": "holmes.arc-codex.com",
                    "method": "GET",
                    "path": "/holmes/HOLMESMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "holmes", "logger": "holmes", "method": "GET", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "beowulf-access.log",
                "BEOWULFMARKER1",
                make_record(
                    ts=base + 8,
                    host="beowulf.arc-codex.com",
                    uri="/beowulf/BEOWULFMARKER1?access_token=FAKE_TOKEN#frag",
                    method="HEAD",
                ),
                {
                    "timestamp": base + 8,
                    "site": "beowulf",
                    "host": "beowulf.arc-codex.com",
                    "method": "HEAD",
                    "path": "/beowulf/BEOWULFMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "beowulf", "logger": "beowulf", "method": "HEAD", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "arc-codex-access.log",
                "OTHERMARKER1",
                make_record(
                    ts=base + 3,
                    host="evil.example:443",
                    method="BREW",
                    proto="HTTP/9",
                    uri="/weird/OTHERMARKER1?secret=FAKE_QUERY#frag",
                    headers={
                        "User-Agent": ["MixedCase/2.0\r\nInjected"],
                        "Referer": ["https://bad.example/path?token=FAKE_QUERY"],
                    },
                    status=404,
                ),
                {
                    "timestamp": base + 3,
                    "site": "other",
                    "host": "other",
                    "method": "OTHER",
                    "path": "/weird/OTHERMARKER1",
                    "status": 404,
                    "status_class": "4xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "other",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "other", "logger": "arc-codex", "method": "OTHER", "status_class": "4xx", "protocol": "other"},
            ),
            (
                "arc-codex-access.log",
                "PORTMARKER1",
                make_record(
                    ts=base + 9,
                    host="arc-codex.com:443",
                    uri="/port/PORTMARKER1?secret=FAKE_QUERY",
                    method="GET",
                ),
                {
                    "timestamp": base + 9,
                    "site": "other",
                    "host": "other",
                    "method": "GET",
                    "path": "/port/PORTMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "other", "logger": "arc-codex", "method": "GET", "status_class": "2xx", "protocol": "http2"},
            ),
            (
                "arc-codex-access.log",
                "MISSINGMARKER1",
                make_record(
                    ts=base + 10,
                    host=None,
                    uri="/missing/MISSINGMARKER1?secret=FAKE_QUERY",
                    method="GET",
                ),
                {
                    "timestamp": base + 10,
                    "site": "other",
                    "host": "other",
                    "method": "GET",
                    "path": "/missing/MISSINGMARKER1",
                    "status": 200,
                    "status_class": "2xx",
                    "duration_seconds": 0.125,
                    "response_size_bytes": 1234,
                    "protocol": "http2",
                    "client_ip": "198.51.100.7",
                    "remote_ip": "203.0.113.9",
                    "user_agent": None,
                    "referer": None,
                    "tls_version": 772,
                    "tls_cipher": 4865,
                },
                {"job": "caddy_access", "environment": "production", "site": "other", "logger": "arc-codex", "method": "GET", "status_class": "2xx", "protocol": "http2"},
            ),
        ]

        for filename, *_ in cases:
            (self.harness.log_root / filename).touch()

        self.harness.start_alloy()

        for filename, marker, record, expected_body, expected_labels in cases:
            write_line(self.harness.log_root / filename, json.dumps(record, separators=(",", ":")))
            labels, line = wait_captured_entry(capture, marker, timeout=60)
            assert set(labels) == ALLOWED_LABELS, labels
            assert labels == expected_labels, labels
            body = json.loads(line)
            assert set(body) == ALLOWED_FIELDS, body
            assert body == stringify_scalars(expected_body), body
            rendered = json.dumps(expected_body, sort_keys=True)
            for secret in (
                "FAKE_TOKEN",
                "FAKE_AUTH_SECRET",
                "FAKE_COOKIE_SECRET",
                "FAKE_SET_COOKIE_SECRET",
                "FAKE_TRACE_SECRET",
                "FAKE_TRACE_ID",
                "FAKE_REQUEST_ID",
                "FAKE_QUERY",
                "FAKE_OAUTH",
                "FAKE_PROXY_AUTH",
                "FAKE_RESPONSE_SECRET",
            ):
                self.assertNotIn(secret, rendered)
            self.assertLessEqual(len(expected_body["path"]), 2048)
            if expected_body["referer"] is not None:
                self.assertLessEqual(len(expected_body["referer"]), 2048)
            if expected_body["user_agent"] is not None:
                self.assertLessEqual(len(expected_body["user_agent"]), 1024)

        malformed = "this is deliberately malformed JSON with FAKE_MALFORMED_SECRET"
        write_line(self.harness.log_root / "arc-codex-access.log", malformed)
        write_line(
            self.harness.log_root / "arc-codex-access.log",
            json.dumps(
                {
                    "ts": "not-a-timestamp",
                    "request": {"host": "arc-codex.com", "uri": {"bad": "FAKE_URI_OBJECT"}, "headers": {"User-Agent": [{"bad": "FAKE_BAD_UA"}]}},
                    "status": {"bad": "FAKE_STATUS_OBJECT"},
                    "duration": 0.5,
                    "size": 12,
                },
                separators=(",", ":"),
            ),
        )
        time.sleep(2)
        self.assertEqual([text for text in capture.entries() if "FAKE_MALFORMED_SECRET" in text], [])
        self.assertEqual([text for text in capture.entries() if "FAKE_URI_OBJECT" in text], [])
        self.assertEqual([text for text in capture.entries() if "FAKE_STATUS_OBJECT" in text], [])
        self.assertEqual([text for text in capture.entries() if "FAKE_BAD_UA" in text], [])

    def test_startup_at_eof_and_restart_persistence(self):
        log_path = self.harness.log_root / "arc-codex-access.log"
        old = make_record(ts=int(time.time()) - 30, host="arc-codex.com", uri="/prestart/EOFMARKER")
        write_line(log_path, json.dumps(old, separators=(",", ":")))

        capture = PushCaptureServer()
        self.addCleanup(capture.close)
        self.harness.set_push_url(capture.url)
        self.harness.start_alloy()
        time.sleep(2)

        with self.assertRaises(AssertionError):
            wait_captured_entry(capture, "EOFMARKER", timeout=5)

        first = make_record(ts=int(time.time()), host="arc-codex.com", uri="/poststart/RESTARTMARKER1")
        write_line(log_path, json.dumps(first, separators=(",", ":")))
        labels, line = wait_captured_entry(capture, "RESTARTMARKER1", timeout=60)
        self.assertEqual(labels, {"job": "caddy_access", "environment": "production", "site": "arc", "logger": "arc-codex", "method": "GET", "status_class": "2xx", "protocol": "http2"})
        self.assertEqual(json.loads(line)["path"], "/poststart/RESTARTMARKER1")

        self.harness.restart_alloy()
        second = make_record(ts=int(time.time()) + 1, host="arc-codex.com", uri="/afterrestart/RESTARTMARKER2")
        write_line(log_path, json.dumps(second, separators=(",", ":")))
        labels2, line2 = wait_captured_entry(capture, "RESTARTMARKER2", timeout=60)
        self.assertEqual(labels2["site"], "arc")
        self.assertEqual(json.loads(line2)["path"], "/afterrestart/RESTARTMARKER2")
        self.assertFalse(any("EOFMARKER" in entry for payload in capture.entries() for stream in payload.get("streams", []) for _, entry in stream["values"]))

    def test_positions_error_restarts_from_end_and_logs_failure(self):
        log_path = self.harness.log_root / "arc-codex-access.log"
        log_path.touch()
        capture = PushCaptureServer()
        self.addCleanup(capture.close)
        self.harness.set_push_url(capture.url)
        self.harness.start_alloy()
        marker = "POSITIONERRORMARKER"
        write_line(log_path, json.dumps(make_record(ts=int(time.time()), host="arc-codex.com", uri=f"/seed/{marker}"), separators=(",", ":")))
        self.assertTrue(wait_captured_entry(capture, marker, timeout=60))

        self.harness.stop_alloy()
        positions = list(self.harness.alloy_state.rglob("positions.yml"))
        self.assertTrue(positions, "expected Alloy positions file to exist")
        positions[0].write_text("invalid: [\n", encoding="utf-8")

        skipped = "SKIPPED_AFTER_POSITION_ERROR"
        write_line(log_path, json.dumps(make_record(ts=int(time.time()) + 1, host="arc-codex.com", uri=f"/during/{skipped}"), separators=(",", ":")))

        self.harness.restart_alloy()
        time.sleep(3)
        with self.assertRaises(AssertionError):
            wait_captured_entry(capture, skipped, timeout=5)
        alloy_logs = docker("logs", self.harness.alloy_cid).stdout
        self.assertIn("positions", alloy_logs.lower())
        self.assertIn("restart_from_end", self.harness.config_path.read_text(encoding="utf-8"))

    def test_wal_replays_after_loki_outage_and_alloy_restart(self):
        log_path = self.harness.log_root / "arc-codex-access.log"
        log_path.touch()
        self.harness.start_loki()
        self.harness.start_alloy()

        selector = '{job="caddy_access",environment="production",site="arc",logger="arc-codex"}'
        write_line(log_path, json.dumps(make_record(ts=int(time.time()), host="arc-codex.com", uri="/wal/WALEVENT1"), separators=(",", ":")))
        self.assertTrue(find_lines(wait_query(self.harness.loki_port, selector + ' |= "WALEVENT1"', timeout=60)))

        self.harness.stop_loki()
        write_line(log_path, json.dumps(make_record(ts=int(time.time()) + 1, host="arc-codex.com", uri="/wal/WALEVENT2"), separators=(",", ":")))
        write_line(log_path, json.dumps(make_record(ts=int(time.time()) + 2, host="arc-codex.com", uri="/wal/WALEVENT3"), separators=(",", ":")))
        time.sleep(2)

        self.harness.stop_alloy()
        self.harness.restart_alloy()
        self.harness.restart_loki()

        for marker in ("WALEVENT1", "WALEVENT2", "WALEVENT3"):
            self.assertTrue(find_lines(wait_query(self.harness.loki_port, selector + f' |= "{marker}"', timeout=90)))

        alloy_metrics = urlopen(f"http://127.0.0.1:{self.alloy_port}/metrics", timeout=5).read().decode("utf-8")
        self.assertIn("loki_write", alloy_metrics)
        self.assertNotIn('loki_write_dropped_entries_total{', alloy_metrics)


if __name__ == "__main__":
    unittest.main()
