#!/usr/bin/env python3
"""validate_sites.py — cross-site isolation validator (schema v2, 2026-07-21).

Loads ALL site cfgs under SITES_ROOT (default /home/www) and asserts the
uniqueness invariants across every pair of sites. This is the check that
would have caught the 'feeds' Solr fallback and the 9101/9090/3001 port
collisions before they existed.

MUST BE UNIQUE: slug, domain, base_url, stack_path, backend_port,
frontend_port, redis_db, solr_core, cold backup dir, every [monitoring]
port, container prefix (derived from slug), guid_prefix. Additionally no
port number may be reused anywhere across sites.

MAY BE SHARED (deliberately): redis host/port, Solr server, physical Ollama
hosts, model names, shared-policy timing fields, mastodon instance.
DECIDED SHARED: the Bluesky handle — all sites publish as arc-codex.com
(Ross, 2026-07-21) — so it is intentionally NOT checked.

Run in CI and at service startup. Exits non-zero on any violation.
"""

import glob
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_config import SiteConfig, SiteConfigError  # noqa: E402

MUST_BE_UNIQUE = [
    ("site", "slug"),
    ("site", "domain"),
    ("site", "base_url"),
    ("site", "stack_path"),
    ("network", "backend_port"),
    ("network", "frontend_port"),
    ("storage", "redis_db"),
    ("storage", "solr_core"),
    ("backup", "cold_dir"),
    ("branding", "guid_prefix"),
]


def discover(root: str) -> list[SiteConfig]:
    """Find every site cfg under root (stack roots only, one level deep).
    A .cfg without a [site] table is not a site cfg and is skipped; a .cfg
    WITH one must fully validate — those errors are fatal, not skippable."""
    sites = []
    for path in sorted(glob.glob(os.path.join(root, "*", "*.cfg"))):
        try:
            with open(path, "rb") as f:
                raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise SiteConfigError(f"{path}: not valid TOML: {e}")
        if "site" not in raw:
            continue
        sites.append(SiteConfig(path))
    return sites


def check(sites: list[SiteConfig]) -> list[str]:
    errors = []

    for section, key in MUST_BE_UNIQUE:
        seen = {}
        for site in sites:
            value = site.get(section, key)
            if value is None:
                errors.append(f"{site.path}: [{section}].{key} is not set")
                continue
            if value in seen:
                errors.append(
                    f"[{section}].{key} = {value!r} collides: "
                    f"{seen[value]} vs {site.path}"
                )
            else:
                seen[value] = site.path
        del seen

    # Derived container prefix must be unique even if the derivation changes.
    seen = {}
    for site in sites:
        prefix = site.container_prefix
        if prefix in seen:
            errors.append(
                f"container prefix {prefix!r} collides: "
                f"{seen[prefix]} vs {site.path}"
            )
        else:
            seen[prefix] = site.path

    # Global port pool: backend, frontend, and every [monitoring] *_port.
    # No number may appear twice anywhere — a Grafana on one site colliding
    # with a frontend on another is just as fatal as a same-field collision.
    pool = {}
    for site in sites:
        ports = [
            ("network.backend_port", site.backend_port),
            ("network.frontend_port", site.frontend_port),
        ]
        for key, value in site["monitoring"].items():
            if key.endswith("_port"):
                ports.append((f"monitoring.{key}", value))
        for label, port in ports:
            owner = pool.get(port)
            if owner:
                errors.append(
                    f"port {port} collides: {owner} vs {site.path} ({label})"
                )
            else:
                pool[port] = f"{site.path} ({label})"

    return errors


def main() -> int:
    root = os.environ.get("SITES_ROOT", "/home/www")
    try:
        sites = discover(root)
    except SiteConfigError as e:
        print(f"❌ {e}")
        return 1

    if not sites:
        print(f"❌ no site cfgs found under {root}")
        return 1

    errors = check(sites)
    if errors:
        for e in errors:
            print(f"❌ {e}")
        print(f"\n{len(errors)} isolation violation(s) across {len(sites)} site(s)")
        return 1

    names = ", ".join(s.slug for s in sites)
    print(f"✅ {len(sites)} site(s) validated, no isolation violations: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
