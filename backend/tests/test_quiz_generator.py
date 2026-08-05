"""Focused tests for quiz-generation retries and attribution rewrites."""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_quiz_generator():
    """Import quiz_generator with its Redis ping stubbed out.

    The module connects at import time. In the test sandbox we do not want a
    live socket dependency, so we patch redis.from_url to return a fake client
    whose ping succeeds.
    """
    if "quiz_generator" in sys.modules:
        return sys.modules["quiz_generator"]
    fake_r = MagicMock()
    fake_r.ping.return_value = True
    with patch("redis.from_url", return_value=fake_r):
        return importlib.import_module("quiz_generator")


def test_strip_simple_attribution_opening_rewrites_question_and_explanation():
    qg = load_quiz_generator()
    question = "According to the article, what caused the delay?"
    explanation = "According to the article, the delay was caused by a queue buildup."

    assert qg.strip_simple_attribution_opening(question) == "What caused the delay?"
    assert qg.strip_simple_attribution_opening(explanation) == "The delay was caused by a queue buildup."


def test_strip_simple_attribution_opening_leaves_non_attribution_text_unchanged():
    qg = load_quiz_generator()
    text = "What caused the delay?"
    assert qg.strip_simple_attribution_opening(text) == text


def test_build_retry_reminder_calls_out_banned_phrase():
    qg = load_quiz_generator()
    reminder = qg.build_retry_reminder("banned phrase: 'according to'")

    assert "exact error: banned phrase: 'according to'" in reminder
    assert "Do NOT use attribution openings like 'according to the article' or 'according to'." in reminder
