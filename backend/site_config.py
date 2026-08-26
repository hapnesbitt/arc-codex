"""site_config.py — per-site configuration loader (schema v2, 2026-07-21).

One TOML cfg per site at the stack root (<slug>.cfg). Code is identical
across stacks; everything site-specific comes from the cfg. Secrets stay in
backend/.env — the loader refuses to start if a cfg key looks like one.

Design principles (from the v2 spec):
  - Derive, don't repeat: slug-prefixed Redis families, session keys,
    container prefixes, internal URLs all derive from the cfg here.
  - Generic Redis keys (analyzer:queue, characters:*, translation:* ...) are
    isolated by each site owning a unique Redis DB, never by prefixing.
  - Shared policy lives in DEFAULTS below; a cfg overrides what differs and
    a minimal cfg omits the rest.
  - Fail loud on required fields — a missing slug/port/DB/core/host must
    stop the service, never fall back to a sibling site's value.

No consumers yet (migration step 1); services adopt this module one per
commit in later steps. Cross-site invariants: see validate_sites.py.
"""

import os
import tomllib

# Shared policy defaults — the committed cross-stack values as of 2026-07-21.
# Tuning is a separate later pass. Required fields (REQUIRED below) have no
# defaults on purpose.
DEFAULTS = {
    "site": {},
    "network": {"cors_origins": []},
    "gunicorn": {"workers": 3, "threads": 8, "timeout": 600},
    "storage": {"redis_host": "localhost", "redis_port": 6379},
    "backup": {
        "warm_retention": 5,
        "cold_retention": 4,
        "log_days": 9,
        "log_max_mb": 50,
    },
    "inference": {
        "primary_url": "",      # "" → ollama_url
        "fallback_url": "",     # "" → ollama_url
        "council_url": "http://localhost:11434",
        "council_num_ctx": 4096,  # KV footprint scales with this — see arc.cfg comment
        "translation_url": "",  # "" → ollama_url
    },
    "models": {
        "cloud": "gemma4:31b-cloud",
        "local": "gemma4:e2b",
        "general": "gemma4:e2b",
        "character": "gemma4:e2b",
        "quiz": "gemma4:e2b",
        "translation": "MedAIBase/TranslateGemma:4b",
    },
    "ingestion": {
        "cycle_minutes": 30,
        "startup_delay_s": 900,
        "sources_per_sweep": 69,
        "concurrent_scrapers": 5,
        "concurrent_preproc": 10,
        "fetch_timeout_s": 15,
        "feed_timeout_s": 30,
        "courtesy_delay_s": 2.5,
        "sources_file": "backend/sources.json",
    },
    "pipeline": {
        "sentinel_timeout_s": 900,
        "ca_timeout_s": 900,
        "background_workers": 2,
        "analyzer_pop_s": 5,
        "analysis_hold_ttl_s": 600,
        "analysis_max_chars": 100_000,
        "analysis_garbage_chars": 250_000,
        "character_feed_poll_s": 20,
        "character_analysis_wait_s": 120,
        "character_analysis_poll_s": 10,
        "character_retry_backoff_s": 600,
        "character_giveup_days": 7,
        "character_max_attempts": 12,
        "council_load_gate": 3.0,
    },
    "posters": {
        "poll_s": 15,
        "ca_wait_s": 120,
        "fb_jitter": [30, 180],
        "fb_cooldown_h": 6,
        "bsky_login_refresh_min": 90,
        # DECIDED shared (Ross, 2026-07-21): all sites publish as arc-codex.com
        "bluesky": {"handle": "arc-codex.com"},
        "mastodon": {"instance": "https://mastodon.social"},
    },
    "branding": {},
    "services": {"enabled": []},
    "quiz": {"cycle_minutes": 300, "lock_ttl_s": 600},
    # Peak-hour blackout for offline audio backfill runs — a courtesy fence
    # so a catch-up pass on old silence doesn't drop a Kokoro subprocess on
    # this box during the window Ross is reading. Half-open [start, end):
    # 14 ≤ hour < 19 pauses; peak_weekdays_only leaves weekends unfenced.
    # Backfill checks this between articles, never mid-synthesis — see
    # backend/audio_backfill.py. Scribe's own audio pass ignores it: that
    # path is already gated by the AUDIO_MIN_FREE_MB preflight and only
    # ever narrates one article per sweep.
    #
    # scan_lookback_hours / scan_window_floor / scan_window_ceiling drive the
    # scribe audio pass's live-derived scan window: window = clamp(floor,
    # count of articles published in the last lookback_hours, ceiling). Same
    # pattern as the mailer's liveness threshold — floor keeps the pass from
    # going myopic on a slow hour, ceiling caps a publish-rate spike so the
    # window can't run away. Fixed 50 (v52 and earlier) let bursty publishing
    # push silent articles out of view before their turn.
    "audio": {
        "peak_start_hour": 14,
        "peak_end_hour": 19,
        "peak_weekdays_only": True,
        "scan_lookback_hours": 6,
        "scan_window_floor": 50,
        "scan_window_ceiling": 500,
    },
    "monitoring": {"exporter_interval_s": 3600},
    "health": {
        "backend_interval_s": 30,
        "backend_timeout_s": 10,
        "backend_retries": 3,
        "frontend_start_s": 20,
        "watchdog_interval_s": 60,
    },
}

# Missing any of these → refuse to start.
REQUIRED = [
    ("site", "slug"),
    ("site", "domain"),
    ("site", "base_url"),
    ("site", "stack_path"),
    ("network", "backend_port"),
    ("network", "frontend_port"),
    ("storage", "redis_db"),
    ("storage", "solr_core"),
    ("inference", "ollama_url"),
    ("retention", "article_hours"),
]

# Belt-and-braces: cfgs are committed to the repo and must stay secret-free.
SECRET_KEY_PATTERNS = ("TOKEN", "SECRET", "PASSWORD", "KEY")


class SiteConfigError(RuntimeError):
    pass


def _stack_slug(stack_root: str) -> str:
    """Return the canonical site slug derived from a stack root path."""
    name = os.path.basename(os.path.abspath(stack_root))
    if name.endswith("_stack"):
        name = name[:-6]
    return name


def expected_site_cfg_name(stack_root: str) -> str:
    """Return the exact cfg filename that belongs to this stack root."""
    return f"{_stack_slug(stack_root)}.cfg"


def expected_site_cfg_path(stack_root: str) -> str:
    """Return the exact absolute path to this stack's site cfg."""
    return os.path.join(os.path.abspath(stack_root), expected_site_cfg_name(stack_root))


def _merge(defaults: dict, override: dict) -> dict:
    out = dict(defaults)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _scan_secret_keys(table: dict, path: str = "") -> list[str]:
    hits = []
    for k, v in table.items():
        dotted = f"{path}.{k}" if path else k
        if any(p in k.upper() for p in SECRET_KEY_PATTERNS):
            hits.append(dotted)
        if isinstance(v, dict):
            hits.extend(_scan_secret_keys(v, dotted))
    return hits


class SiteConfig:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        with open(self.path, "rb") as f:
            raw = tomllib.load(f)

        secret_hits = _scan_secret_keys(raw)
        if secret_hits:
            raise SiteConfigError(
                f"{self.path}: keys matching secret patterns "
                f"{SECRET_KEY_PATTERNS} are not allowed in a committed cfg: "
                f"{', '.join(secret_hits)} — secrets belong in backend/.env"
            )

        missing = [
            f"[{sec}].{key}" for sec, key in REQUIRED
            if key not in raw.get(sec, {})
        ]
        if missing:
            raise SiteConfigError(
                f"{self.path}: missing required fields: {', '.join(missing)}"
            )

        self.data = _merge(DEFAULTS, raw)

    def __getitem__(self, section: str) -> dict:
        return self.data[section]

    def get(self, section: str, key: str, default=None):
        return self.data.get(section, {}).get(key, default)

    # ── identity ──────────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        return self.data["site"].get("name", self.slug)

    @property
    def slug(self) -> str:
        return self.data["site"]["slug"]

    @property
    def domain(self) -> str:
        return self.data["site"]["domain"]

    @property
    def base_url(self) -> str:
        return self.data["site"]["base_url"]

    @property
    def stack_path(self) -> str:
        return self.data["site"]["stack_path"]

    # ── derived — never repeated in the cfg ───────────────────────────────
    @property
    def backend_port(self) -> int:
        return self.data["network"]["backend_port"]

    @property
    def frontend_port(self) -> int:
        return self.data["network"]["frontend_port"]

    @property
    def backend_internal_url(self) -> str:
        return f"http://127.0.0.1:{self.backend_port}"

    @property
    def warm_backup_dir(self) -> str:
        return os.path.join(self.stack_path, "backups")

    @property
    def container_prefix(self) -> str:
        return self.slug

    def redis_key(self, family: str) -> str:
        """Slug-prefixed Redis key for site-owned families (stats, quiz,
        auth, ...). Generic pipeline keys stay unprefixed — they are isolated
        by the unique-Redis-DB invariant, never by prefix."""
        return f"{self.slug}:{family}"

    # ── storage ───────────────────────────────────────────────────────────
    @property
    def redis_db(self) -> int:
        return self.data["storage"]["redis_db"]

    @property
    def solr_core(self) -> str:
        return self.data["storage"]["solr_core"]

    # ── inference — every URL defaults to ollama_url ──────────────────────
    @property
    def ollama_url(self) -> str:
        return self.data["inference"]["ollama_url"]

    @property
    def primary_url(self) -> str:
        return self.data["inference"]["primary_url"] or self.ollama_url

    @property
    def fallback_url(self) -> str:
        return self.data["inference"]["fallback_url"] or self.ollama_url

    @property
    def council_url(self) -> str:
        return self.data["inference"]["council_url"]

    @property
    def council_num_ctx(self) -> int:
        return int(self.data["inference"]["council_num_ctx"])

    @property
    def translation_url(self) -> str:
        return self.data["inference"]["translation_url"] or self.ollama_url


def load_site_config(path: str | None = None) -> SiteConfig:
    """Load this stack's cfg. The cfg lives at the stack root (the parent of
    backend/); exactly one *.cfg must exist there — zero or several is a
    deployment error and we refuse to guess."""
    if path is None:
        stack_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = expected_site_cfg_path(stack_root)
        if not os.path.isfile(path):
            raise SiteConfigError(
                f"expected site cfg {os.path.basename(path)!r} in {stack_root}, "
                f"but it was not found"
            )
    return SiteConfig(path)
