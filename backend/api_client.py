"""api_client.py — thin HTTP client for pre_analyze/publish_article calls.

Split out of scribe.py 2026-08-27 (scribe recon/cleanup — see
ops/RUNBOOK.md). The cleanest seam of the four: a plain class, nothing but
requests, no scribe.py state at all.

2026-08-27, second pass: manual_publisher.py had its own independent copy
of this class, drifted (its pre_analyze didn't take article_id — reconciled
below by giving it a default, since main.py's endpoint doesn't currently
read the field either way; see ops/RUNBOOK.md for the trace). Consolidated
onto this module instead of leaving the duplicate.

The logger is caller-supplied, not a hardcoded module logger: scribe.py and
audio_backfill.py both transitively configure logging.getLogger('scribe')
by importing scribe.py, so a hardcoded 'scribe' logger happened to work for
them — but manual_publisher.py deliberately does NOT import scribe.py
("Completely isolated from scribe.py" is its own file's header comment),
so that same hardcoded logger would have gone to an unconfigured logger and
silently dropped its errors instead of landing in manual_publisher.log.
Each caller passes its own logger; defaults to 'scribe' only so scribe.py's
existing construction (APIClient(base_url, key), no logger arg) keeps
working unchanged.
"""

from __future__ import annotations

import logging

import requests


class APIClient:
    def __init__(self, base_url, secret_key, logger=None):
        self.base_url = base_url
        self.secret_key = secret_key
        self.logger = logger or logging.getLogger('scribe')

    def _post(self, endpoint, json_data, add_secret=True, timeout=90):
        url = f"{self.base_url}/{endpoint}"
        headers = {'X-Scribe-Secret': self.secret_key} if add_secret else {}
        try:
            response = requests.post(url, json=json_data, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed for {endpoint}: {e}")
            return None

    def pre_analyze(self, text, article_id=''):
        return self._post('pre_analyze', {'inputText': text, 'article_id': article_id}, add_secret=False)

    def publish_article(self, article_payload):
        return self._post('publish_article', article_payload)
