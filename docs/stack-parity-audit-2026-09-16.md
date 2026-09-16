# Arc ↔ Hunt parity audit — 2026-09-16

Read-only accounting of what legitimately differs between `arc_stack` and
`huntaegis_stack`, and what differs only by drift. **This is a report, not
a refactor.** Nothing here has been reconciled; the point is to answer
"if I re-cloned Arc to Hunt tomorrow, what would I have to put back, and
what would I be glad to lose?"

Scope: everything under `/home/www/arc_stack` and
`/home/www/huntaegis_stack` except `node_modules`, `venv`,
`__pycache__`, `.git`, `.pytest_cache`, `.next`, `logs`, `pids`,
`backups`, `archive`, `upload{,s}`, generated `plantorium_qrcodes` /
`qr_codes`, and generated media (`*.mp3`, `*.webm`, `*.pdf`, `*.png`,
`*.jpg`, `*.zip`, `*.bak-*`).

After exclusions: **344 files on Arc, 235 on Hunt, 194 in common** —
of which 118 differ. Full raw lists and byte-level diffs are in
`/tmp/claude-1000/-home-www-arc-stack/a4a1309b-.../scratchpad/`
(session-scoped; regenerable from the two trees).

---

## Executive verdict

- **The "four shared files" invariant in CLAUDE.md is false.**
  `ollama_utils.py`, `fetch_utils.py`, `stream_utils.py` are all drifted;
  `auth.py` doesn't exist on Hunt at all. Drift is mostly Arc-forward
  fixes that never landed on Hunt (transport-error taxonomy, exception
  types, cloud-reachability probe, Playwright Tier-3 extraction, per-call
  host/model overrides). CLAUDE.md needs its wording changed — either
  drop the claim or make it true.
- **`site_config.py` exists on both stacks but has only ~20% adoption.**
  Everything the loader was built to centralize (Redis env, backend port,
  brand strings, domain, log paths) is still re-derived from `os.getenv`
  or hardcoded in 20+ modules per stack. The port default (`5005` /
  `5006`) is copy-pasted across four Python files and eight TS route
  handlers per stack. Every change to those defaults has to be applied
  in ~12 places.
- **A large slice of Arc-only files is genuine product surface** — the
  Library reader, Quiz, Reporters, Plantorium, Syndromes, YouTube
  ingestion, the four dashboards under `monitoring/`. Cloning Arc to
  Hunt today would re-import all of that into Hunt whether or not Hunt
  wants it.
- **A smaller slice of Arc-only files is missed mirroring** — most
  notably `net_safety.py` (Hunt inlines a private copy in `scribe.py`),
  `caddy_exporter.py` (docstring says "for Arc/Huntaegis" but only
  Arc runs it), `escalation.py`, `image_rehost.py`, and the
  `ops/systemd/`, `docs/`, `provision.sh`, per-stack watchdog units.

---

## A. Files that exist in one stack only

### A.1. Arc-only, deliberate (product / operational)

Do NOT expect these on Hunt.

**Product surfaces Hunt doesn't have:**
- Library: `backend/library.db`, `library_db.py`, `library_fetcher.py`,
  `publication_metadata.py`, `publication_year_backfill.py`,
  `catalogs/`, `catalog_loader.py`, `frontend/app/library/**`,
  `frontend/app/api/internal/revalidate-library/route.ts`,
  `frontend/lib/library-cache.ts`,
  `docs/library-*.md`, `ops/migrate_library_to_sqlite.py`.
- Quiz: `backend/quiz_api.py`, `quiz_generator.py`, `score_library.py`,
  `frontend/app/quiz/**`, `frontend/components/Quiz*.tsx`,
  `frontend/public/shows/*`.
- Reporters + audio + narration:
  `backend/audio_backfill.py`, `makehap.py` (differs on Hunt too — see B),
  `frontend/app/reporters/**`, `ops/systemd/{arc-audio-backfill,warden,spectre}*`,
  `ops/systemd/audio-backfill.service`.
- Plantorium: `backend/kasmir7.py`'s `/api/plants` path,
  `frontend/app/plants/page.tsx`, `plantorium_qrcodes/`.
  (`kasmir7.py` exists on both — see B: heavy diff, mostly Arc-specific
  product logic.)
- Syndromes / EDS: `frontend/app/syndromes/**`.
- YouTube ingest: `backend/youtube_ingest.py`.
- Prompt-to-article: `backend/prompt_to_article.py`.
- Threads (Meta): `backend/threads_poster.py` (Hunt does not post to
  Threads — bluesky/mastodon/facebook are the poster set on Hunt).
- Sources page: `frontend/app/sources/page.tsx`.
- Wiki: `frontend/app/wiki/**` (index + `[slug]`). Hunt has the backend
  `/api/wiki/<directive>` endpoint listed in `main.py` but no frontend
  pages.
- Playwright Tier-3: `backend/playwright_tier3.py` — the extracted
  module lives on Arc only. Hunt still has the pre-extraction inline
  version in `fetch_utils.py` (see C).
- Escalation gate: `backend/escalation.py`.
- Grading: `backend/grade.py`.
- Image rehost: `backend/image_rehost.py` (Hunt has `backfill_images.py`
  which serves a similar purpose but is not the same code).
- Domain registry: `backend/domain_registry.py`.
- Caddy exporter: `backend/caddy_exporter.py` — docstring says
  "for Arc/Huntaegis Caddy JSON access logs" but only Arc runs it.
  This one is genuinely dual-purpose; today it runs from Arc and
  exports for both, so it's cleaner to leave the file on Arc alone.
- SSRF guard module: `backend/net_safety.py` — but see A.3, this
  is also duplicated inline in Hunt's `scribe.py`.
- Benchmark JSONs: `backend/arc_benchmark_*.json` (Arc has 8; Hunt has
  just the `arc_benchmark_results.json` that Arc also has).
- Auth: `backend/auth.py`. See section C.

**Operational surfaces only Arc has:**
- Full `docs/` directory (9 files: perf, pwa, retention capacity,
  state-of-arc, traffic asymmetry, reporter governance, library-*).
- Full `ops/` directory (~15 files: `ARTICLE_LIFECYCLE.md`, `REBOOT.md`,
  `caddy-uploads-audio-cors.conf`, cecil mailer, m1/spectre backup
  pullers, migrate scripts, per-host systemd units, `nightly-git-push.sh`).
  Hunt's `ops/` has only `RUNBOOK.md` (shared filename, big diff).
- Monitoring: full `monitoring/alertmanager.yml`, `alloy/`, `loki/`,
  `rules/arc_alerts.yml`, `grafana/.../corpus-intelligence-v2.json`,
  `textfile/`. Hunt has an older `grafana/.../corpus.json` and nothing
  else under monitoring/.
- `provision.sh` (28 KB host bootstrap) — Arc only. Hunt has no
  provision path in the repo.
- `arc_env.sh`, `arc.sh` — Arc's `arc.sh` is 42 KB. Hunt has
  `huntaegis.sh` (38 KB) and `huntaegis_env.sh`. These are per-stack by
  name so they will always look "only-in-X" from a tree diff; content
  parity is a separate question (see B for the sibling script
  `watchdog.sh` which is in both and drifts by 126 diff lines).
- Top-level configs: `characters.yaml` and `shelves.yaml` (Arc) vs
  Hunt's `characters.yaml` only. Different intents — Hunt has no
  library so no shelves.
- Dashboards: `Arc_dash.json`. Hunt uses provisioned Grafana dashboards
  under `monitoring/grafana/`.
- Wiki / directive companion: `frontend/public/directives.json`. Hunt
  doesn't ship this to the frontend even though it maintains the
  backend copy.

**In-flight or session artifacts, safe to leave on Arc:**
- `TODO.md` (115 KB), `WO`, `CODEX_RECON_FOR_CLAUDE.md`,
  `auth_integration_notes.txt`, `.claude/RESUME.md`,
  `May1.shelves.yaml`, `arc_eval.py` + `eval/`.
- Backups & swap files under `secret/`: `.linkedin.txt.swp`,
  `FB_arc_codex_access_token`, `bluesky`, `facebook`, `mastodon`
  (Hunt has these secrets too — they live outside the repo tree there).

### A.2. Hunt-only, deliberate

Do NOT expect these on Arc.

- `backend/backfill_{images,readability_index,reading_label,source_lang}.py`
  — Hunt migration scripts written after the equivalent Arc work landed
  inline in scribe/analyzer. Not needed on Arc.
- `backend/reindex_solr.py` — Hunt-side Solr reindex tool for
  `feeds_huntaegis` core. Arc has an equivalent under `tools/reindex_solr.py`
  (Arc-only path — same purpose, different location, different core).
- `backend/huntaegis_project_context.yaml` — companion to the shared
  `project_context.yaml`. (Note: Hunt has both. Arc has only
  `project_context.yaml`.)
- `frontend/public/~partytown/**` — Partytown web-worker library ships
  with Hunt only. Arc's frontend build does not include it.
- `frontend/public/{watch.mp4, storm.gif, 20260121_0918_01kfgndcx3fkatbgeesh946vss.mp4, ross-nesbitt-resume.docx, google7c719d55a878e7a9.html}`
  — Hunt-specific hero media and Google Search Console verification.
- `DOCKERENV` at repo root — Hunt-specific docker-run helper.
- `frontend/.dockerignore` — Hunt has a per-frontend ignore file; Arc
  relies on the root `.dockerignore` alone.
- `ops/systemd/huntaegis-{stack,watchdog}.service` — per-stack systemd
  units (parity with Arc's `arc-{stack,watchdog}.service`, so this pair
  is "different by design").
- Tests: `tests/test_{mailer, quiz_deeplink_contract, scribe_captcha, sources_loader}.py`
  — Hunt-specific test coverage.

### A.3. Missed mirroring (would want back if re-cloned)

The clean-up-and-clone list. Every entry is Arc-side infrastructure that
Hunt would want too but doesn't have (or Hunt-side that Arc lacks):

**Arc → would want on Hunt:**
- `backend/net_safety.py` — SSRF guard module. Hunt has a private
  inline copy `_resolves_to_private_ip` in `scribe.py:610` (with its
  own local `_SSRFBlocked` exception class) that has drifted from
  Arc's module. Extract Hunt's copy to a module named `net_safety.py`
  and drop the inline duplicates.
- `backend/auth.py` — 741-line auth blueprint that the current CLAUDE.md
  claims is shared with Hunt. It isn't there at all. Hunt has no
  Flask-Limiter, no shared-DB-5 login. See section C.
- `backend/playwright_tier3.py` — dedicated Tier-3 fetch module.
  Hunt still has the pre-extraction fat version of the same logic
  inline in `fetch_utils.py`. See C.

**Hunt → would want on Arc:**
- `backend/tests/test_mailer.py`, `test_scribe_captcha.py`,
  `test_sources_loader.py` — decent regression coverage; Arc's test
  suite would benefit.

---

## B. Files that exist in both — deliberate vs drift

118 common files differ. Ranked by content-line count (`diff | grep -c '^[<>]'`).

Full sorted list at
`/tmp/claude-1000/.../scratchpad/file_diffs_sorted.txt`. Highlights:

### B.1. Deliberate — brand, domain, DB, port

These SHOULD differ. The diff is real product configuration.

| File | Nature of divergence |
|---|---|
| `arc_config.yaml` vs `huntaegis.cfg` layer | Brand, port (5005/5006), DB (0/1), Solr core (`feeds`/`feeds_huntaegis`). Both use the schema-v2 loader now. |
| `backend/rss_feed.py` (16 diff lines) | "Arc Codex" ↔ "HapEnews", `arc-codex.com` ↔ `whirled-news.barrel-of-knowledge.info`, `arc-codex-{aid}` ↔ `hapenews-{aid}` GUID prefix. Pure branding. |
| `backend/mailer.py` (401 diff lines) | Mixed — branding is deliberate, but this size is too large for branding alone (see B.2). |
| `backend/bluesky_poster.py` (9 diff lines) | Branding + default image URL. Deliberate. |
| `backend/mastodon_poster.py` (1 diff line) | Effectively identical after branding — the "good" mirror. |
| `backend/facebook_poster.py` (84 diff lines) | Branding + account handles + one small structural difference in log-setup. Mostly deliberate. |
| `frontend/lib/cardConfig.ts` (25 diff lines) | siteName, baseUrlFallback, videoDomainFallback, feature toggles per site (Hunt disables `readingScore`, etc.). Deliberate. |
| `frontend/public/sw.js` (18 diff lines) | Only the CACHE_NAME prefix (`arc-v1` / `hunt-v1`) and doc-comment references to `arc.sh`/`huntaegis.sh`. Deliberate. |
| All `frontend/app/api/*/route.ts` handlers with tiny diffs | Only the port default in `BACKEND_INTERNAL_URL ?? "http://localhost:5005"` vs `5006`. Deliberate — but see D.1: the fact that this appears in 8 files rather than one shared constant is a within-stack duplication problem, not an Arc-vs-Hunt one. |
| `Dockerfile.frontend` (67 diff lines) | Mostly the SW_CACHE_STAMP sed for arc-v1/hunt-v1, plus a few build-time env differences. Mostly deliberate. |
| `docker-compose.yml` (138 diff lines) | Ports, container names, volume paths, hostnames. Mostly deliberate; the diff is bigger than it needs to be because port/hostname strings are embedded rather than templated. |
| `backend/sources.json` (2,594 diff lines) | Different feed lists. Deliberate (Arc = general news, Hunt = cybersecurity). |
| `backend/directives.json` (1,685 diff lines) | Different taxonomies. Deliberate. |
| `backend/prompts.yaml` (134 diff lines) | Some prompt phrasing tuned per site (Hunt is more security-tone). Partly deliberate; a few "prompt polish only on Arc" lines look like missed mirroring — worth a dedicated pass someday but not in scope here. |
| `frontend/public/{sitemap,rss,news-sitemap}.xml` (1-line "diffs") | Generated content — the diff is the whole document. Ignore. |
| `frontend/package-lock.json` (5,523 diff lines) | Slightly different `package.json` (Hunt has partytown, react-share differences) → whole lock differs. Deliberate consequence of a small deliberate difference. |
| About pages (`frontend/app/about/*/page.tsx`, ~200-900 diff lines each) | Copy per site. Deliberate content, though these have drifted structurally too (the layout scaffolding could be shared but currently isn't; see D.2). |
| Top-level `.claude/settings.local.json` (652 diff lines) | Per-machine allow-list state, expected to drift. Ignore. |

### B.2. Drift — big files, mostly missed mirroring

These are the files where the diff is large enough that a single feature
or fix landed on one side and never crossed to the other. Ordered by
diff impact:

| File | Diff lines | Verdict |
|---|---|---|
| `backend/main.py` | 1,734 | Arc has ~1,144 more content lines. Includes wiki, plants, quiz, library endpoints — deliberate. But even after subtracting product endpoints, there are Arc-side fixes (rate-limit shape, request-id logging, sitemap batching) that are worth mirroring. Realistically Arc's main.py is the source of truth and Hunt should copy delta by delta. |
| `backend/scribe.py` | 1,590 | Arc has ~552 more content lines. Similar shape: Arc has audio/reporter/library/plants logic that Hunt doesn't (deliberate), but also stronger scribe internals (retry accounting, feed liveness TTL, retention delegation) that Hunt still runs the older version of. |
| `backend/kasmir7.py` | 763 | Both have this file; Arc has Plantorium (`/api/plants` + QR generation), Hunt doesn't. Most of the diff is Plantorium. Deliberate. |
| `backend/character_builder.py` | 197 | Refactor + council host wiring that landed on Arc; Hunt hasn't caught up. Drift. |
| `backend/analyzer.py` | 316 | Cloud circuit breaker + M1-retirement branch on Arc; Hunt has an older shape. Drift. |
| `backend/cleanup.py` | 127 | Arc absorbed image-days into `site_config`; Hunt still hardcodes. Drift. |
| `backend/arc_benchmark.py` | 541 | Both have it — Arc's is the actively maintained one. Hunt's copy is stale. Ambiguous; both may need it or one may be dead. |
| `backend/mailer.py` | 401 | Branding accounts for ~120 lines; the rest is Arc-side digest / opt-in / retry logic. Drift. |
| `backend/manual_publisher.py` | 61 | Deliberate: Hunt uses `babel` for language names (self-contained image); Arc reads `backend/languages.json`. Small — good state. Also the port default (`5005`/`5006`). |
| `backend/api_client.py` | 36 | Both stacks did the same consolidation independently on different dates (Arc: 2026-08-27; Hunt: 2026-09-10). Code is materially the same; comments have drifted. Fine. |
| `backend/ollama_client.py` | 30 | Small feature deltas. Should be reconciled. |
| `backend/site_config.py` | 30 | Slight difference in `DEFAULTS`. Ambiguous — some of it is deliberate per-site policy that should have moved into the cfg instead of into the loader. |
| `backend/tests/test_smoke.py` | 186 | Arc's is much richer. Drift; port the coverage. |
| `ops/RUNBOOK.md` | 3,554 | Arc's is 182 KB, Hunt's is 15 KB. Deliberate (Hunt's runbook is a stub pointing back at Arc's for shared procedures). |
| `CLAUDE.md` | 308 | Different personalities of each stack — Hunt's is minimal, Arc's is comprehensive. Deliberate but Hunt's is arguably too thin. |
| `characters.yaml` | 620 | Different character sets per site. Deliberate. |
| `watchdog.sh` | 126 | Same shape, different service lists. Deliberate + some drift. |
| `frontend/components/IntelligenceCard.tsx` | 128 | Almost identical structure; drift is small enhancements (icons, torch button destination). Should be mirrored. |
| `frontend/components/FeedClient.tsx` | 110 | Small drift. |
| `frontend/components/TranslateButton.tsx` | 168 | Small drift. |
| `frontend/components/UserMenu.tsx` | 59 | Small drift. |

### B.3. Config files with intentional operator tune (leave alone)

`arc.cfg` and `huntaegis.cfg` `[ingestion]` blocks (per CLAUDE.md
constraint): `cycle_minutes`, `startup_delay_s`, `sources_per_sweep`,
`concurrent_scrapers` are operator-owned. Do NOT flag as drift.

---

## C. The four "shared" files claimed by CLAUDE.md

CLAUDE.md says:

> Shared utilities: `auth.py`, `ollama_utils.py`, `fetch_utils.py`,
> `stream_utils.py` — changes here may need mirroring.

Actual state as of 2026-09-16:

| File | Arc lines | Hunt lines | Diff (content) | Verdict |
|---|---|---|---|---|
| `auth.py` | 741 | — | — | **MISSING on Hunt.** The Hunt `main.py` has no `from auth import init_auth` call and no Flask-Limiter setup. This means the CLAUDE.md statement "shared with huntaegis" is false and has been false for however long Hunt has been running without central auth. Two possibilities: (1) Hunt doesn't want NextAuth/Flask-Limiter — deliberate — in which case CLAUDE.md needs to say so; (2) Hunt has drifted off the shared path and is running unauthenticated moderation endpoints — a real gap. Ross should decide. |
| `ollama_utils.py` | 436 | 291 | 205 lines | Heavy drift. Arc-forward: `OllamaTransportError` and `OllamaNoResponseError` exception taxonomy (introduced 2026-09-12 after a spectre firewall gap), `is_cloud_reachable()` pre-flight (introduced 2026-07-07 after the M1 outage burned 2,755 doomed escalations), `BROADCAST_OLLAMA_HOST/MODEL` support for the 2026-09-11 narration split, richer `call_ollama_with_fallback` signature (`format_schema`, `temperature`, `models`, `num_ctx`), richer `call_ollama_local_only` (`host`, `model`, `num_predict` per-call overrides), `num_ctx` cap now 16384. Hunt has none of it. **This is unambiguous missed-mirroring drift.** The core call semantics still work on Hunt, but Hunt's narration will silently absorb load on the wrong host and its cloud breaker won't distinguish "not reachable" from "429". |
| `fetch_utils.py` | 290 | 355 | 119 lines | Structural drift. Arc extracted the Playwright Tier-2/3 body into `playwright_tier3.py` (fd-safe context-per-fetch, radeon exile, process-tree kill-on-timeout, zombie killer) and left `fetch_utils.fetch_with_anti_bot_handling` as an 80-line stub that delegates. Hunt still has the original ~180-line inline body with `context.add_init_script`, `page.goto`, per-attempt teardown, and no `enable_tier3` flag. Behaviorally similar; operationally worse (no zombie protection, no single-serialized browser). Missed mirroring. |
| `stream_utils.py` | 86 | 84 | 18 lines | Comment-only drift. Arc's docstrings mention `quiz_generator` (which is Arc-only) and the 2026-07-18 trim rationale; Hunt's still references the pre-trim 41k-entry snapshot. Code is identical. Fine. |

**Bottom line:** the CLAUDE.md invariant is broken 3 of 4 ways. Either
mirror the Arc changes to Hunt and re-assert the invariant, or delete
the "shared" wording so future work stops treating these as safe to
edit in one place.

---

## D. Within-stack duplication (same logic, N copies)

The user's callouts (APIClient was 3 copies, port 5005 was 4 files,
0600 umask fix hit 2 of 3 generators) are all true and still present.
Beyond those:

### D.1. The port default appears in ~12 places per stack

Backend Python (Arc):
- `backend/manual_publisher.py:42` — `"http://127.0.0.1:5005/api"`
- `backend/kasmir7.py:1528` — `"http://localhost:5005/api/plants"` (hardcoded, no env override)
- `backend/main.py:2723` — `app.run(host='0.0.0.0', port=5005, debug=False)`
- `backend/bluesky_poster.py:42` — `"http://localhost:5005"`

Frontend TS (Arc):
- `frontend/lib/auth.ts:47` — `?? "http://localhost:5005"`
- `frontend/app/page.tsx:12`
- `frontend/app/api/submit/route.ts:5`
- `frontend/app/api/submit_doc/route.ts:5`
- `frontend/app/api/submit_comment/route.ts:5`
- `frontend/app/api/submit_content/route.ts:5`
- `frontend/app/api/submit_prompt/route.ts:5`
- `frontend/app/api/upload_image/route.ts:13`
- `frontend/app/api/user/prefs/route.ts:18`
- `frontend/app/api/get_feed/route.ts:5`

Each of these has to be edited in both stacks any time the port
convention changes. There is no `getBackendUrl()` helper on the
frontend or a `SITE.backend_internal_url` used from Python; the
schema-v2 `site_config` module was built to provide the latter but
none of the above imports it.

**Suggestion (out of scope for this report):** one `backendUrl()`
helper in `frontend/lib/backend.ts`, one `SITE.backend_url()` on the
Python side, then this whole surface collapses to two files.

### D.2. Redis env re-derivation in 12+ files

Every file that touches Redis re-does the same 5 `os.getenv` calls
(HOST, PORT, PASSWORD, URL, DB). Grep:

```
character_builder.py, facebook_poster.py, corpus_exporter.py,
threads_poster.py, quiz_api.py, bluesky_poster.py, quiz_generator.py,
main.py, mastodon_poster.py, kasmir7.py, cleanup.py, auth.py
```

`site_config.py` was written to be the single source (`SITE.redis_db`,
`SITE.redis_password`), and is used by ~11 files. The other ~15 still
grab `os.getenv("REDIS_URL")` directly. Adoption is stalled.

### D.3. `class APIClient` — the fix landed, but the pattern repeats

The class was 3 copies on Arc (`scribe.py`, `manual_publisher.py`,
plus `api_client.py`). Extracted to `api_client.py` on Arc 2026-08-27
and Hunt 2026-09-10. **This one is resolved.** Both stacks now import
from `api_client`. The comment blocks in `scribe.py:1801` and
`manual_publisher.py:324` are the leftover markers, not stale copies.

### D.4. Log-file `0o600` chmod is inconsistent across posters

On Arc, four social posters open a log file the same way:

- `bluesky_poster.py:71` — `logging.FileHandler(...)` — no chmod
- `mastodon_poster.py:53` — same, no chmod
- `threads_poster.py:49` — same, no chmod
- `facebook_poster.py:97` — same, **followed by** `os.chmod(_log_path, 0o600)` at line 105

Only Facebook's poster locks its log to 0600. The other three write
world-readable logs to `/home/www/arc_stack/logs/`. On Hunt the
picture is the same (facebook_poster only). The umask/chmod fix was
never extracted into a shared helper, so it stayed in the one file it
was applied to.

There is also a second chmod pattern in `caddy_exporter.py:280,286`
around atomic file writes — a different code path, not the log file.

### D.5. SSRF guard: extracted on Arc, still inline on Hunt

Already covered in A.3 and C. Arc has `backend/net_safety.py`;
Hunt has `_resolves_to_private_ip` + `_SSRFBlocked` inline in
`scribe.py:610-654`. Two copies of the same logic on Hunt: the inline
scribe copy and — if anything else on Hunt wanted the guard — nothing
to import.

### D.6. Language ISO→name mapping

- Arc: `backend/languages.json` + inline `ISO_TO_NAME` dict loaded in
  `manual_publisher.py:57-72`.
- Hunt: uses `babel.Locale` in `manual_publisher.py:76-80` (no JSON).

The comment in `manual_publisher.py` notes this is "duplicated from
scribe.py rather than imported". Both scribe and manual_publisher
still carry their own language mapping code. Two copies per stack;
Arc's uses a JSON file, Hunt's uses babel. Both work; neither is
shared.

### D.7. `about/` layout scaffolding, repeated per page

Each `frontend/app/about/*/page.tsx` re-implements the same page-shell
pattern (header, sidebar, "recently updated" band). Every diff between
Arc and Hunt in about/* is amplified by this — a small copy change
edits 8 files. Not a correctness problem, but the reason the diff
totals in B.2 look bigger than the actual content change.

---

## E. Recommended next steps (report the choices, don't take them)

The user asked for a report, not a refactor. In priority order:

1. **Fix CLAUDE.md's "shared utilities" section.** Either mirror
   ollama_utils/fetch_utils/auth to Hunt, or drop the claim.
2. **Decide whether Hunt should have `auth.py`.** If yes, port it.
   If no, remove `auth.py` from the CLAUDE.md list and document what
   Hunt uses instead.
3. **Extract `net_safety.py` on Hunt** — one-file lift-and-shift from
   Arc, drop the inline scribe copies. Trivial and closes a real
   duplication.
4. **Land the ollama_utils exception taxonomy on Hunt.** The
   `OllamaTransportError` / `OllamaNoResponseError` distinction is
   the reason Arc knows the difference between "spectre firewall gap"
   and "content rejection". Hunt still can't tell.
5. **Extract the port/backend-URL constant.** One `lib/backend.ts` +
   one `SITE.backend_internal_url` in Python. Deletes 12 hardcoded
   strings per stack.
6. **Extract log-open+chmod into `log_utils.py`.** Fix the three
   social posters at once.

Everything else in this doc is either genuine product difference or
low-priority polish.

---

## Appendix — regenerating the raw data

```bash
S=/tmp/parity && mkdir -p $S
find /home/www/arc_stack -type f \
  -not -path '*/node_modules/*' -not -path '*/venv/*' \
  -not -path '*/__pycache__/*' -not -path '*/.git/*' \
  -not -path '*/.pytest_cache/*' -not -path '*/.next/*' \
  -not -path '*/logs/*' -not -path '*/pids/*' \
  -not -path '*/backups/*' -not -path '*/archive/*' \
  -not -path '*/upload/*' -not -path '*/uploads/*' \
  -not -path '*/plantorium_qrcodes/*' \
  -not -name '*.mp3' -not -name '*.webm' -not -name '*.pdf' \
  -not -name '*.png' -not -name '*.jpg' -not -name '*.zip' \
  -not -name '*.bak-*' \
  | sed 's|/home/www/arc_stack/||' | LC_ALL=C sort > $S/arc.txt
# same for huntaegis_stack with '*/qr_codes/*' and '*/run/*' added
LC_ALL=C comm -23 $S/arc.txt $S/hunt.txt   # arc-only
LC_ALL=C comm -13 $S/arc.txt $S/hunt.txt   # hunt-only
LC_ALL=C comm -12 $S/arc.txt $S/hunt.txt   # in both
# then diff each in-both file to rank drift
```
