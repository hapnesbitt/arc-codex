"""net_safety.py — SSRF guard shared by scribe.py's content fetcher and
image_rehost.py.

Split out of scribe.py 2026-08-27 (scribe recon/cleanup — see
ops/RUNBOOK.md). Two independent scribe.py call sites depend on this same
check (the redirect-chasing fetch guard in the CONTENT FETCHING section, and
image_rehost.rehost_article_image); a shared module keeps both importing
from one place instead of one importing the other for an unrelated reason.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def resolves_to_private_ip(url: str) -> bool:
    """True if the host resolves to any private/loopback/link-local address.

    Scraped pages and submitted URLs are not trusted input — never let a
    fetch land on an internal target (Ollama, Solr, the M1, cloud metadata
    endpoints) because a page or a redirect pointed there.
    """
    try:
        host = urlparse(url).hostname
        if not host:
            return True
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        return False
    except Exception:
        return True
