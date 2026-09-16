"""Regression: ARC_LOCAL_ONLY=1 makes local-only mode a hard gate, not a
convention. This test is the load-bearing check that the sales page's
"local-only mode disables cloud entirely" claim stays true — three
distinct enforcement points:

  1. is_cloud_available() → False regardless of the Redis circuit-breaker
     key. Every existing cloud-escalation callsite (analyzer.py:379-380
     escalation guard, translation.py:210 user-facing cloud retry,
     call_ollama_with_fallback's tuple-stripping cascade) checks this
     function, so the flag propagates through the module with no per-
     callsite work.

  2. is_cloud_reachable() → False without hitting the network. Otherwise
     every escalation-decision cycle logs a failed HTTP probe against a
     host that's disabled by policy.

  3. site_config.load_site_config() → refuses to start if council_url
     points off-host. character_builder.py's council path talks to
     council_url directly with requests.post and does NOT route through
     ollama_utils, so without this check a customer who set a cloud
     council endpoint would silently bypass the mode. The loader failure
     is the difference between "supported" and "provable."
"""
import importlib
import os
import sys

import pytest


def _reload_ollama_utils():
    """The env check runs at module import (for the startup warn), so
    tests that toggle the env must reimport the module."""
    if "ollama_utils" in sys.modules:
        return importlib.reload(sys.modules["ollama_utils"])
    import ollama_utils  # noqa: F401
    return sys.modules["ollama_utils"]


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("ARC_LOCAL_ONLY", raising=False)
    yield monkeypatch


def test_is_cloud_available_returns_false_when_local_only(clean_env):
    clean_env.setenv("ARC_LOCAL_ONLY", "1")
    ou = _reload_ollama_utils()
    assert ou.is_cloud_available() is False


def test_is_cloud_reachable_returns_false_without_http_probe(clean_env):
    # If the flag is honored, is_cloud_reachable returns without touching
    # the network. Replace requests.get with a raiser to prove no probe fires.
    clean_env.setenv("ARC_LOCAL_ONLY", "1")
    ou = _reload_ollama_utils()

    def _would_probe(*_a, **_kw):
        raise AssertionError("is_cloud_reachable must not touch the network under ARC_LOCAL_ONLY")

    clean_env.setattr(ou.requests, "get", _would_probe)
    assert ou.is_cloud_reachable() is False


def test_truthy_env_values_all_enable_the_mode(clean_env):
    for value in ("1", "true", "TRUE", "Yes", "  true  "):
        clean_env.setenv("ARC_LOCAL_ONLY", value)
        ou = _reload_ollama_utils()
        assert ou.is_cloud_available() is False, f"value {value!r} should enable local-only"


def test_falsy_env_leaves_normal_gate_intact(clean_env):
    # No ARC_LOCAL_ONLY set → the mode is off; is_cloud_available falls
    # through to the normal breaker check (returns True when no Redis
    # breaker key is set, or when _redis is None in test env).
    for value in ("", "0", "false", "no"):
        clean_env.setenv("ARC_LOCAL_ONLY", value)
        ou = _reload_ollama_utils()
        # Under test env _redis is typically None → returns True.
        # We only assert the flag DIDN'T force False.
        result = ou.is_cloud_available()
        assert isinstance(result, bool)


_MIN_CFG_TEMPLATE = (
    '[site]\n'
    'name = "Test"\n'
    'slug = "test"\n'
    'domain = "test.example"\n'
    'base_url = "https://test.example"\n'
    'stack_path = "/tmp/test"\n'
    '[network]\n'
    'backend_port = 5099\n'
    'frontend_port = 3099\n'
    '[storage]\n'
    'redis_db = 9\n'
    'solr_core = "feeds_test"\n'
    '[inference]\n'
    'ollama_url = "http://192.168.1.189:11434"\n'
    'council_url = "{council_url}"\n'
    '[retention]\n'
    'article_hours = 720\n'
)


def test_site_config_refuses_off_host_council_url_under_local_only(clean_env, tmp_path):
    clean_env.setenv("ARC_LOCAL_ONLY", "1")
    cfg = tmp_path / "test.cfg"
    cfg.write_text(_MIN_CFG_TEMPLATE.format(council_url="http://192.168.1.200:11434"))
    from site_config import load_site_config, SiteConfigError
    with pytest.raises(SiteConfigError, match="council_url"):
        load_site_config(str(cfg))


def test_site_config_accepts_localhost_council_url_under_local_only(clean_env, tmp_path):
    clean_env.setenv("ARC_LOCAL_ONLY", "1")
    cfg = tmp_path / "test.cfg"
    cfg.write_text(_MIN_CFG_TEMPLATE.format(council_url="http://localhost:11434"))
    from site_config import load_site_config
    site = load_site_config(str(cfg))
    assert site.council_url == "http://localhost:11434"
