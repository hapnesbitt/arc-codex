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

import pytest
import main as arc_main

# Wave D R16 (2026-07-11): Flask-Limiter decorators on endpoints are only
# ENFORCED after limiter.init_app(app) runs. Production does that via
# init_auth(), which needs a live Redis. In tests we skip auth's Redis
# wiring, so the limiter's default in-memory storage stays and we init the
# limiter here directly — enough to make @limiter.limit fire.
from auth import limiter as _test_limiter
_test_limiter.init_app(arc_main.app)


@pytest.fixture
def app():
    arc_main.app.config["TESTING"] = True
    return arc_main.app


@pytest.fixture
def client(app):
    return app.test_client()
