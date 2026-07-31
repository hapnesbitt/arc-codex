import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "config.alloy").read_text(encoding="utf-8")
SERVICE = (ROOT / "alloy.service").read_text(encoding="utf-8")
FIXTURE = ROOT / "fixtures" / "caddy-synthetic.jsonl"

ALLOWED_FIELDS = {
    "timestamp", "site", "host", "method", "path", "status",
    "status_class", "duration_seconds", "response_size_bytes", "protocol",
    "client_ip", "remote_ip", "user_agent", "referer", "tls_version",
    "tls_cipher",
}
ALLOWED_LABELS = {"job", "environment", "site", "logger", "method", "status_class", "protocol"}
METHODS = {"GET", "POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"}
SITES = {"arc", "huntaegis", "dlb", "school_of_chat", "plantorium", "athena", "mark", "holmes", "beowulf", "other"}


def clean(value, limit):
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value if ord(c) >= 32 and ord(c) != 127)[:limit]


def sanitize(record, source_site="arc"):
    request = record.get("request") or {}
    tls = request.get("tls") or {}
    headers = request.get("headers") or {}
    method_raw = request.get("method", "")
    method = method_raw if method_raw in METHODS else "OTHER"
    proto = request.get("proto", "")
    protocol = {"HTTP/1.0": "http1", "HTTP/1.1": "http1", "HTTP/2.0": "http2", "HTTP/2": "http2", "HTTP/3.0": "http3", "HTTP/3": "http3"}.get(proto, "other")
    status = record.get("status")
    status_class = f"{status // 100}xx" if isinstance(status, int) and 100 <= status < 600 else "other"
    raw_path = clean(request.get("uri", ""), 4096).split("?", 1)[0].split("#", 1)[0][:2048]
    referer_values = headers.get("Referer") or []
    referer = clean(referer_values[0] if referer_values else "", 4096)
    if referer:
        parsed = urlsplit(referer)
        referer = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"[:2048]
    ua_values = headers.get("User-Agent") or []
    host_map = {
        "arc-codex.com": ("arc", "arc-codex.com"),
        "www.arc-codex.com": ("arc", "arc-codex.com"),
        "huntaegis.com": ("huntaegis", "huntaegis.com"),
        "www.huntaegis.com": ("huntaegis", "huntaegis.com"),
        "dlb.arc-codex.com": ("dlb", "dlb.arc-codex.com"),
        "soc.arc-codex.com": ("school_of_chat", "soc.arc-codex.com"),
        "plantorium.arc-codex.com": ("plantorium", "plantorium.arc-codex.com"),
        "athena.arc-codex.com": ("athena", "athena.arc-codex.com"),
        "mark.arc-codex.com": ("mark", "mark.arc-codex.com"),
        "holmes.arc-codex.com": ("holmes", "holmes.arc-codex.com"),
        "beowulf.arc-codex.com": ("beowulf", "beowulf.arc-codex.com"),
    }
    site, canonical = host_map.get(request.get("host"), ("other", "other"))
    event = {
        "timestamp": record.get("ts"), "site": site, "host": canonical,
        "method": method, "path": raw_path, "status": status,
        "status_class": status_class, "duration_seconds": record.get("duration"),
        "response_size_bytes": record.get("size"), "protocol": protocol,
        "client_ip": clean(request.get("client_ip", ""), 64),
        "remote_ip": clean(request.get("remote_ip", ""), 64),
        "user_agent": clean(ua_values[0] if ua_values else "", 1024),
        "referer": referer, "tls_version": tls.get("version"),
        "tls_cipher": tls.get("cipher_suite"),
    }
    labels = {"job": "caddy_access", "environment": "production", "site": site,
              "logger": source_site if source_site in SITES else "other", "method": method, "status_class": status_class,
              "protocol": protocol}
    return event, labels


class SanitizationContractTest(unittest.TestCase):
    def fixture_records(self):
        records, malformed = [], 0
        for line in FIXTURE.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
        return records, malformed

    def test_allow_list_reconstruction_removes_secrets_and_queries(self):
        records, malformed = self.fixture_records()
        self.assertEqual(malformed, 1)
        event, labels = sanitize(records[0])
        rendered = json.dumps(event, sort_keys=True)
        self.assertEqual(set(event), ALLOWED_FIELDS)
        self.assertEqual(set(labels), ALLOWED_LABELS)
        for secret in ("FAKE_TOKEN", "FAKE_AUTH_SECRET", "FAKE_COOKIE_SECRET",
                       "FAKE_SET_COOKIE_SECRET", "FAKE_TRACE_SECRET", "FAKE_QUERY"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(event["path"], "/articles/abc")
        self.assertEqual(event["referer"], "https://search.example/results")
        self.assertNotIn("\n", event["user_agent"])

    def test_host_is_fixed_by_source_not_untrusted_header(self):
        record = self.fixture_records()[0][0]
        event, labels = sanitize(record, "unknown_source")
        self.assertEqual(event["site"], "other")
        self.assertEqual(event["host"], "other")
        self.assertEqual(labels["site"], "other")
        self.assertNotIn("evil.example", json.dumps(event))

    def test_missing_optional_fields_and_ipv6_are_safe(self):
        records, _ = self.fixture_records()
        minimal, _ = sanitize(records[2])
        ipv6, labels = sanitize(records[1])
        self.assertEqual(minimal["client_ip"], "")
        self.assertEqual(ipv6["remote_ip"], "2001:db8::10")
        self.assertEqual(ipv6["path"], "/rss.xml")
        self.assertEqual(labels["method"], "OTHER")
        self.assertEqual(labels["protocol"], "http3")

    def test_ips_and_body_dimensions_never_become_labels(self):
        forbidden = {"client_ip", "remote_ip", "path", "raw_uri", "user_agent", "referer", "raw_host"}
        label_keep = re.search(r"stage\.label_keep\s*\{.*?values\s*=\s*\[(.*?)\]", CONFIG, re.S)
        self.assertIsNotNone(label_keep)
        kept = set(re.findall(r'"([a-z_]+)"', label_keep.group(1)))
        self.assertEqual(kept, ALLOWED_LABELS)
        self.assertFalse(kept & forbidden)

    def test_configuration_starts_at_eof_and_avoids_archives(self):
        self.assertIn("tail_from_end           = true", CONFIG)
        self.assertIn('on_positions_file_error = "restart_from_end"', CONFIG)
        self.assertNotIn("*.gz", CONFIG)
        self.assertNotIn("decompression", CONFIG)

    def test_configuration_reconstructs_output_and_drops_malformed(self):
        self.assertIn("drop_malformed = true", CONFIG)
        self.assertIn('source = "sanitized"', CONFIG)
        self.assertIn("stage.output", CONFIG)
        self.assertNotIn("stage.pack", CONFIG)
        self.assertIn("queue_config", CONFIG)
        self.assertIn("wal {", CONFIG)
        for field in ALLOWED_FIELDS:
            self.assertIn(f"`{field}`", CONFIG)

    def test_service_waits_for_loki_and_uses_experimental_flags(self):
        self.assertIn("ExecStartPre=/bin/sh -ec", SERVICE)
        self.assertIn("http://127.0.0.1:3100/ready", SERVICE)
        self.assertIn("--stability.level=experimental", SERVICE)
        self.assertIn("--disable-reporting", SERVICE)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", SERVICE)
        self.assertIn("TimeoutStartSec=30s", SERVICE)


if __name__ == "__main__":
    unittest.main()
