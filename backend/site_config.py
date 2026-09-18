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
    # sources.json floor guard — a truncated JSONL parses cleanly line by line,
    # so a shrunk sources.json produces no error signal anywhere downstream:
    # scribe just quietly sweeps a fraction of the corpus. Both bounds default
    # to 0 = disabled; each site opts in via its own [integrity] block.
    "integrity": {"min_sources": 0, "warn_sources": 0},
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
    # audio_backfill.py is the sole narrator (scribe's own audio pass was
    # retired 2026-08-27 — it never took arc:audio:active, so it had no
    # exclusion against the daemon and the two could double-synthesize the
    # same article; see ops/RUNBOOK.md 2026-08-27). Under the 2026-09-17
    # newest-first redesign there is no candidacy window any more — the
    # daemon narrates the newest silent article anywhere in feed. Only
    # the peak-hour throttle survives from the old sliding-window shape:
    # weekday 14:00-19:00 half-open, weekends unfenced, one mutex acquire
    # per peak_throttle_minutes as a symbolic lightening around Ross's
    # business hours (arc.cfg [audio] has the current tuning).
    "audio": {
        "peak_start_hour": 14,
        "peak_end_hour": 19,
        "peak_weekdays_only": True,
        "peak_throttle_minutes": 15,
        # Poison-pill guard — see arc.cfg [audio] for the full rationale.
        # Observed median chars/s from 191 historical narrations; used to
        # skip (not attempt) any article whose estimated synthesis time
        # would exceed scribe.AUDIO_TIMEOUT_SECONDS.
        "estimated_synthesis_cps": 15.0,
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

        # ARC_LOCAL_ONLY hard-gate: the ollama_utils flag disables cloud
        # for every path that routes through call_ollama_with_fallback /
        # is_cloud_available, but character_builder.py (council) hits
        # site.council_url directly with requests.post and does NOT go
        # through that module. Without this check, a customer who set
        # council_url to a cloud endpoint would silently bypass the mode.
        # This is the difference between local-only as a convention and
        # local-only as a provable invariant — worth ~5 lines to hold.
        if os.environ.get("ARC_LOCAL_ONLY", "").strip().lower() in ("1", "true", "yes"):
            council_url = self.data["inference"]["council_url"]
            _LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            if not any(f"//{host}" in council_url for host in _LOCAL_HOSTS):
                raise SiteConfigError(
                    f"{self.path}: ARC_LOCAL_ONLY=1 requires [inference].council_url "
                    f"to point at a localhost address, got {council_url!r}. "
                    f"The council path (character_builder.py) does not route "
                    f"through ollama_utils and would bypass the local-only gate."
                )

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

    # ── branding — one accessor per hardcoded-brand pattern the parity
    # audit turned up. Each reads a cfg key under [branding] (arc.cfg and
    # huntaegis.cfg both already have this section); a cfg that omits a
    # key falls back to a sensible construction from the site identity
    # so a minimal cfg still works. Key names match the existing schema
    # (rss_title, rss_generator, guid_prefix, mail_sender, default_image).
    @property
    def email_from(self) -> str:
        """Site-scoped sender address. Reads [branding].mail_sender;
        defaults to ross@<domain> — every stack today uses ross@ as the
        operator handle."""
        return self.data.get("branding", {}).get("mail_sender") or f"ross@{self.domain}"

    @property
    def default_image_url(self) -> str:
        """Site-scoped OG fallback image, always absolute. cfg's
        [branding].default_image can be relative ("/uploads/foo.jpg") or
        absolute ("https://cdn.example/foo.jpg"); relative paths get the
        site's base_url prefixed. Defaults to <base_url>/uploads/<slug>-default.jpg
        when the cfg omits it — matches the file convention every stack
        already follows."""
        raw = self.data.get("branding", {}).get("default_image")
        if raw:
            if raw.startswith(("http://", "https://")):
                return raw
            return f"{self.base_url}{raw if raw.startswith('/') else '/' + raw}"
        return f"{self.base_url}/uploads/{self.slug}-default.jpg"

    def article_url(self, article_id: str) -> str:
        """Canonical public URL for an article. Used by every social
        poster, the RSS feed, mailer, and manual_publisher — replaces
        11+ hardcoded `f"https://arc-codex.com/article/{id}"` constructions
        across the backend."""
        return f"{self.base_url}/article/{article_id}"

    @property
    def rss_title(self) -> str:
        """RSS channel <title>. Reads [branding].rss_title; defaults to
        '<name> — A.R.C. Intelligence Feed'."""
        return (
            self.data.get("branding", {}).get("rss_title")
            or f"{self.name} — A.R.C. Intelligence Feed"
        )

    @property
    def rss_generator(self) -> str:
        return (
            self.data.get("branding", {}).get("rss_generator")
            or f"{self.name} A.R.C. Framework"
        )

    @property
    def rss_guid_prefix(self) -> str:
        """RSS <guid> prefix. Reads [branding].guid_prefix; defaults to
        the slug with a trailing dash, so guids look like arc-codex-<aid>
        / hapenews-<aid> / etc. Existing cfgs already ship the trailing
        dash in the string, so we strip a trailing dash from the read
        value to normalize (callers append their own separator)."""
        raw = self.data.get("branding", {}).get("guid_prefix")
        if raw is not None:
            return raw.rstrip("-")
        return self.slug

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
