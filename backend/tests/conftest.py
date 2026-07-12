"""Smoke-test fixtures for arc_stack backend.

Imports main.py without a live Redis (main.py handles r=None gracefully).
No live services required: Redis / library.db / Ollama are all monkey-patched
per-test as needed.
"""
import os
import sys
import pathlib

# backend/ is on sys.path so 'import main' works from the tests dir.
BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)  # prompts.yaml is opened by relative path at import time

# Valid-shape URL so redis-py's from_url can parse without connecting.
# Nothing dials it — every test monkey-patches main.r to a MagicMock/None.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SCRIBE_SECRET_KEY", "test-scribe-secret")

# R16-followup (2026-07-11): auth.py builds Limiter's Redis URI from
# REDIS_HOST/PORT/PASSWORD at import time. Tests must NOT hit real Redis —
# point at a host that will never resolve so the limiter's
# in_memory_fallback_enabled path fires transparently and per-process
# limits still enforce (which is exactly what the test wants: 30/hour hit
# from a single pytest process → 31st is 429).
os.environ.setdefault("REDIS_HOST", "test-redis-unreachable.invalid")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")

import pytest
import main as arc_main

# After main imports (which imports auth's limiter), swap storage to a
# plain MemoryStorage so tests don't spin on the unreachable host every
# request. Fallback would kick in eventually, but this is deterministic.
from limits.storage import MemoryStorage
arc_main.limiter._storage = MemoryStorage()
arc_main.limiter.init_app(arc_main.app)


@pytest.fixture
def app():
    arc_main.app.config["TESTING"] = True
    return arc_main.app


@pytest.fixture
def client(app):
    return app.test_client()
