"""Guard the CAPTCHA-boilerplate gate against false positives on articles
that legitimately quote checkpoint phrases in their own prose.

The gate lives in `_extracted_looks_like_captcha_boilerplate` (scribe.py).
Its job is to drop pages that made it past the fetch tiers as
CAPTCHA/checkpoint HTML instead of real content, but tech and security
reporting routinely quotes the same phrases ("cloudflare ray id", "ddos
protection by cloudflare", "verify you are a human", "checking your
browser", "attention required | cloudflare").

An earlier revision ran the text-side regex with no HTML-marker precondition,
so on-topic articles quoting those phrases were silently dropped at
ingestion. Pin the current shape (both branches require an HTML CAPTCHA
marker) so the two-branch guard cannot be quietly weakened.

Ported from huntaegis_stack/backend/tests/test_scribe_captcha.py alongside
the underlying fix. Arc runs playwright_tier3 so a false positive here is
often recoverable via retry, but the gate runs before tier-3 selection so
the regression is still worth pinning.
"""
import logging
import sys
import types
from unittest.mock import MagicMock, patch


# scribe.py runs Redis + Solr connections at import time and calls exit() on
# ConnectionError — conftest.py points REDIS_HOST at an unreachable host, so a
# bare `import scribe` under pytest raises SystemExit. Neuter the boot-time
# side effects: a MagicMock stands in for redis.Redis, redis_readiness is
# stubbed, pysolr.Solr is a no-op, and FileHandler routes to /dev/null. We
# only need the pure regex helper — the surrounding boot state is irrelevant.
_fake_readiness = types.ModuleType("redis_readiness")
_fake_readiness.wait_for_redis = lambda *_a, **_kw: None
sys.modules.setdefault("redis_readiness", _fake_readiness)

with patch.object(logging, "FileHandler", return_value=logging.NullHandler()), \
        patch("redis.Redis", return_value=MagicMock()), \
        patch("pysolr.Solr", return_value=MagicMock()):
    import scribe


# ---------------------------------------------------------------------------
# False-positive regression: on-topic prose without HTML-side markers
# ---------------------------------------------------------------------------

CYBER_PROSE = [
    "Attackers used a novel technique to bypass the Cloudflare Ray ID "
    "verification system deployed by mid-tier ecommerce sites this quarter.",
    "A recent report describes how DDoS protection by Cloudflare deflected a "
    "record-breaking layer-7 flood targeting a European ISP.",
    "The malware pretends to be a checkpoint page and asks victims to "
    "verify you are a human before proceeding to a credential-harvest form.",
    "When users encounter a fake checking your browser page mid-purchase, "
    "few realize the interstitial is attacker-controlled rather than a CDN.",
    "This CVE affects the Attention Required | Cloudflare interstitial "
    "path and lets a crafted cookie skip the challenge entirely.",
]


def _pad_to_captcha_gate(text: str) -> str:
    """Length-pad so the extract clears MIN_ARTICLE_CHARS_CAPTCHA — the tests
    are aimed at the text-side regex path, not the short-extract path."""
    padding = "This is legitimate editorial commentary continuing the article. " * 60
    return text + " " + padding


def test_cyber_prose_without_captcha_html_markers_is_not_rejected():
    """Neither branch may fire when the source HTML has no CAPTCHA marker —
    otherwise a security-news article that names checkpoint phrases in its
    own prose gets silently dropped."""
    clean_html = (
        "<html><body><article><p>Standard news article body — no CDN "
        "challenge markers here.</p></article></body></html>"
    )
    for prose in CYBER_PROSE:
        text = _pad_to_captcha_gate(prose)
        is_captcha, reason = scribe._extracted_looks_like_captcha_boilerplate(text, clean_html)
        assert is_captcha is False, (
            f"CAPTCHA gate false-positive on on-topic prose: {prose!r} "
            f"(reason={reason!r})"
        )


# ---------------------------------------------------------------------------
# True-positive: an actual CAPTCHA extract (HTML marker + short body) fires
# ---------------------------------------------------------------------------

def test_short_extract_with_captcha_html_marker_is_rejected():
    short_text = "Checking your browser before you access the site."
    captcha_html = (
        "<html><body>Attention Required! | Cloudflare<br>"
        "Please turn JavaScript on and reload the page.</body></html>"
    )
    is_captcha, reason = scribe._extracted_looks_like_captcha_boilerplate(short_text, captcha_html)
    assert is_captcha is True, "short extract + CAPTCHA HTML marker must fire"
    assert reason and "captcha" in reason.lower()


# ---------------------------------------------------------------------------
# True-positive: long extract but checkpoint prose + HTML marker still fires
# ---------------------------------------------------------------------------

def test_long_extract_with_checkpoint_prose_and_captcha_html_is_rejected():
    text = _pad_to_captcha_gate(
        "Checking your browser before you access this site. "
        "Please complete the security check to access the resource."
    )
    captcha_html = (
        "<html><body><div class='cf-browser-verification'>"
        "Attention Required! | Cloudflare</div></body></html>"
    )
    is_captcha, reason = scribe._extracted_looks_like_captcha_boilerplate(text, captcha_html)
    assert is_captcha is True, (
        "checkpoint prose + CAPTCHA HTML marker in a long extract must fire — "
        "this is the intended defense, distinct from the short-extract branch"
    )
    assert reason and "captcha" in reason.lower()


# ---------------------------------------------------------------------------
# Negative: no HTML marker at all → both branches must skip
# ---------------------------------------------------------------------------

def test_empty_html_never_fires_even_on_short_extract():
    """The gate must never fire when the HTML side has no marker at all —
    even a very short extract has to be judged by other quality checks."""
    short_text = "Short article body."
    is_captcha, reason = scribe._extracted_looks_like_captcha_boilerplate(short_text, "")
    assert is_captcha is False, (
        f"empty HTML must not trigger the CAPTCHA gate; got reason={reason!r}"
    )
