# Arc Stack Recon for Claude

## Executive Summary

This is a static, read-only reconnaissance of `/home/www/arc_stack` performed on 2026-08-15. It did not inspect another `/home/www` project, invoke live AI, run application/integration tests, query Redis/Solr/SQLite, inspect installed Caddy/systemd/crontab state, restart services, or modify application code or data. Generated dependencies, build output, logs, uploads, backups, and data were excluded. The review covered 259 repository source/configuration/documentation files through targeted full reads and mechanical searches.

Arc is currently a Flask/Gunicorn API plus a Next.js App Router frontend. Redis DB 0 is the primary article/work-queue/cache store, Redis DB 5 holds a still-active Flask local-auth realm and its limiter, Solr is a derived search index, and SQLite holds the Gutenberg library. The normal ingestion path is RSS/manual input -> scribe -> Flask publish -> Redis/Solr -> analyzer/stream consumer -> Next.js/API. Several other producer, analysis, publishing, and cleanup paths coexist.

The highest-risk result is that `visibility == "private"` is enforced independently in selected list surfaces rather than at the canonical article boundary. The direct article and comment APIs, anonymous ISR article rendering, Solr indexing/search, translation, grading, dynamic RSS, and three of four social posters do not apply the same ownership check. Static generators and Threads do filter private content, proving the intended rule but also demonstrating fragmented enforcement.

Other high-value findings are: three materially different configuration sources remain active; Gunicorn documentation/config/script values disagree; OAuth/JWT and Flask password authentication coexist with dead frontend fallback calls to the removed `/api/me`; old filesystem submissions and new Redis submissions are both reachable; Red/Blue/Purple work is now queued at ingest despite prominent “lazy on first view” documentation; Redis Stream failures can be acknowledged and lost; and frontend feed pagination treats post-filter result counts as source offsets.

Static totals used in this report are: **22 potential conflict/source-of-truth cases**, **16 candidate legacy/shadow areas**, **18 documentation mismatches**, **22 important test gaps**, and **48 prioritized findings** (**P0 5 / P1 19 / P2 20 / P3 4**). These are evidence categories, not assertions that code is safe to delete.

## Current Architecture

### Components

| Area | Current repository evidence |
|---|---|
| API/backend | Flask application factory/global app in `backend/main.py`; blueprints in `auth.py`, `user_prefs.py`, `translation.py`, `grade.py`, `rss_feed.py`, and `quiz_api.py`. |
| WSGI | `backend/gunicorn_arc.sh` starts `main:app` on `127.0.0.1:5005`, currently with 20 workers, 8 threads, preload, and a 600-second timeout. |
| Frontend | Next.js 16 / React 19 / TypeScript App Router under `frontend/app`; the frontend container listens on 3000. No Pages Router directory was found. |
| Edge | Caddy is described as TLS terminator and route splitter. Only historical Caddy backups and runbook snapshots are in this repository; the installed configuration is not a repository source of truth. |
| Primary state | Redis DB 0: article hashes, chronological feed, queues, streams, comments, reactions, preferences, translation/grade caches, social/character state, quiz state, and operational metrics. |
| Authentication state | Redis DB 5: Flask local usernames/password hashes/reset tokens/admin state and Flask-Limiter keys (`backend/auth.py`). OAuth preferences are in DB 0 as `user:{providerAccountId}`. |
| Search | Solr core/collection `feeds`, written during scribe publication/reindex and queried by `backend/main.py:search_articles`; treated as derived state. |
| Library | SQLite at `LIBRARY_DB_PATH` (default `/mnt/arcdata/library.db`), WAL mode, tables `works`, `work_texts`, `shelves`, `shelf_members`, `translations`. |
| Ingestion | `backend/scribe.py` polls RSS sources and `arc:priority_uploads`; `backend/manual_publisher.py` watches `backend/upload/pending`; direct video submissions write Redis from Flask. |
| Analysis | Scribe performs Sentinel and Counter-Analyst locally. `backend/analyzer.py` performs unified Red/Blue/Purple local-first analysis with policy-gated cloud escalation; `stream_consumer.py` persists stream results. Character and quiz workers perform additional local/cloud work. |
| Publishing | Flask publish endpoint, Redis feed, Solr indexing, static sitemap/RSS/news generation, Bluesky/Mastodon/Facebook/Threads workers, manual Bluesky endpoint, and email alerts/digest. |
| Supervision | `arc.sh` owns normal start/stop/build/status; `watchdog.sh` is a separate systemd-supervised restart loop. Unit files are under `ops/systemd/`. |
| Monitoring/logging | File logs under `logs/`; Prometheus/Grafana/Loki/Alloy configuration; `corpus_exporter.py` and `caddy_exporter.py`; operational Redis heartbeats/counters. |
| Host/external dependencies | Redis, Solr, Caddy, Postfix, OAuth providers, social APIs, Ollama-compatible endpoints, an SSH audio host alias, and three curated catalog files hard-coded under `/home/ross`. Their live state was not inspected. |

### Data and control flow

```text
RSS feeds / authenticated URL-text-doc-prompt-video submissions
    -> scribe priority/RSS paths OR legacy manual_publisher filesystem path
    -> normalization, sanitization, metadata, optional image/audio work
    -> local Sentinel + local Counter-Analyst (scribe/manual path semantics differ)
    -> POST /api/publish_article
    -> Redis article:{id} + feed + processed_hashes
       + Solr document (scribe-side, best effort)
       + analyzer:queue at ingest (tail)
    -> analyzer local unified R/B/P
       -> optional cloud rerun through escalation policy
       -> analysis:pending Redis Stream
    -> stream_consumer -> article hash analysis fields
    -> Flask APIs -> Next.js ISR/client feed/article/search/wiki/library surfaces
    -> static sitemap/RSS/news generation and social/email publishers
    -> retention/cleanup reconcile Redis, Solr, caches, and rehosted files

Article view -> direct Flask article lookup -> priority analyzer enqueue (head) if incomplete
OAuth -> Auth.js JWT -> Next server proxy sets X-User-Id -> Flask write/preferences endpoints
Flask local auth -> Redis DB 5 session realm (still registered, largely disconnected from Next UI)
Gutenberg fetch -> SQLite WAL database -> Flask library APIs -> Next library pages
```

### Route/auth map

- Public reads include feed, direct article, comments, search, stats, config dashboard, RSS, translation, grade, wiki, sources, sitemap, library, syndromes, plants, and quiz.
- OAuth-authenticated writes flow through Next route handlers that call `auth()` and set `X-User-Id`; Flask validates loopback for most submission/prefs paths through `_client_user_id()` / `_require_authed_user_id()` or `user_prefs._require_user_id()`.
- Flask local-auth routes `/auth/register`, `/auth/login`, reset flows, logout, and admin routes remain registered and store password hashes in Redis DB 5.
- Internal/secret paths include `/api/publish_article`, `/api/post_bluesky`, and library revalidation. Their safety depends on a configured secret and/or loopback proxy topology.
- Privileged local-auth admin operations are decorator-protected, but their form POSTs have no evident CSRF token.

## Confirmed Sources of Truth

These are the strongest *static* sources of truth; runtime installation can still override them.

- `backend/gunicorn_arc.sh` is the effective Gunicorn command used by both `arc.sh` and Docker Compose. Its command-line values override prose and `[gunicorn]` values that are not consumed by the script.
- `backend/main.py` and its registered blueprints are the Flask route truth. Comments in `main.py` explicitly say `/api/me` was removed, and no such route exists.
- `frontend/lib/auth.ts` is the current Next authentication truth: Auth.js v5 beta, Google/GitHub providers, JWT sessions, and `providerAccountId` copied to `token.sub`/`session.user.id`.
- `frontend/components/UserPrefsContext.tsx` is the shared browser preference state. `backend/user_prefs.py` is its DB 0 persistence endpoint.
- `backend/site_config.py` + `arc.cfg` govern scribe ingestion/retention, analyzer/character timing, quiz enablement inputs, monitoring, and several derived Redis prefixes. They do **not** govern every model, service, or Gunicorn setting.
- `backend/prompts.yaml` is the active Red/Blue/Purple/Sentinel prompt catalog for analyzer/scribe/manual publisher. Prompt-to-article and grade prompts are embedded in Python instead.
- `backend/ollama_utils.py` and `backend/ollama_client.py` are the active shared AI transport/model defaults for most calls; environment variables take precedence. `backend/escalation.py` separately reads `arc_config.yaml`.
- `backend/retention.py` is the shared age-pruning implementation used by scribe and `kasmir7.py`; `backend/cleanup.py` is the later orphan/image backstop.
- `backend/library_db.py` is the canonical Gutenberg persistence contract. `backend/library_fetcher.py` is the writer and the Flask library routes are readers.
- `arc.sh` is the normal operator lifecycle entry point, but its service array is literal. `watchdog.sh` contains a second literal, active service array.

## Conflicting / Duplicate Implementations

The count for this section is **22**. “Reachable” is based on static call/registration/supervision evidence; live execution still requires runtime confirmation.

| ID | Files / symbols | Evidence and apparent behavior | Reachability / conflict |
|---|---|---|---|
| C01 | `CLAUDE.md:26`; `arc.cfg:[gunicorn]`; `backend/gunicorn_arc.sh` | Values are respectively 1 worker, 16 workers, and a hard-coded 20 workers; script comments also describe a single worker while invoking 20. | Script is reached by `arc.sh` and Compose. Active behavior conflicts with two documented/configured values. |
| C02 | `arc.cfg`; `arc_config.yaml`; `backend/site_config.py`; `backend/escalation.py:_load_escalation_config`; `backend/main.py:get_config`; `backend/mailer.py` | New TOML configuration, old YAML configuration, environment variables, and hard-coded constants all remain consumers. | Both config files are reachable; neither is globally authoritative. Runtime env adds a third layer. |
| C03 | `arc.cfg:[services]`; `arc.sh:SERVICES`; `watchdog.sh:SERVICES`; `arc_config.yaml:services`; `docker-compose.yml` | Five service inventories disagree. Threads exists in none; newer poster/character/exporter services are absent from older lists; watchdog is represented differently. | `arc.sh` and watchdog are active ownership paths; Compose can also run a partial worker set. Duplicate starts require runtime/operator action. |
| C04 | `backend/main.py:submit_content`; `backend/manual_publisher.py`; `backend/main.py:submit`; `backend/scribe.py:process_priority_queue` | Filesystem pending files and Redis priority queue are old/new ingestion implementations. Metadata, AI routing, retry, visibility, and job semantics differ. | Both Flask endpoints and both supervised workers are reachable. New endpoint comments explicitly call filesystem path old. |
| C05 | `main.py:publish_article`; `main.py:get_single_article`; `analyzer.py` | R/B/P jobs are queued at ingest tail and again as view-priority head with the same dedup key. | Both are active by design, but documentation still calls analysis first-view lazy. Runtime ordering depends on queue state. |
| C06 | `scribe.py:run_sentinel_analysis/run_counter_analyst`; `manual_publisher.py` same symbols | Duplicated prompt assembly/parsing/persistence. Scribe uses local-only calls; manual publisher uses cloud-first fallback. | Both workers are supervised and feed publish. Semantics and cloud accounting conflict. |
| C07 | `ollama_utils.py`; `ollama_client.py`; `arc.cfg:[models]/[inference]`; `arc_config.yaml:models`; `character_builder.py`; `quiz_generator.py:QUIZ_MODELS` | Model/host selection comes from env defaults, TOML, old YAML, character-specific TOML, and quiz hard-coding. | Multiple active callers; availability can differ from dashboard/config claims. Runtime env/model inventory required. |
| C08 | `auth.py`; `frontend/lib/auth.ts`; seven `frontend/app/api/*/route.ts:getLocalAuthUserId` functions | Flask password sessions and OAuth JWT are separate identity realms. Proxies still attempt the removed `/api/me`. | Flask auth blueprint is registered; OAuth is UI path; local fallback is statically unreachable because endpoint is absent. |
| C09 | `UserPrefsContext.tsx`; `ClientLayout.tsx:MobileAuthButton`; `UserMenu.tsx` | One shared data context, but two independently implemented settings/delete-account interfaces and dialog behavior. | Mobile and desktop layouts make both UI controllers reachable. State is shared; presentation/control logic is duplicated. |
| C10 | `user_prefs.py:patch_prefs`; `UserPrefsContext.clearPreferredLang` | Client intentionally sends JSON `null`; backend applies `str(None)` and stores the literal `"None"`, while client assumes empty string. | Active cross-layer mismatch; deterministic request test can confirm without external services using a fake Redis client. |
| C11 | `main.py:get_feed`; `FeedClient.tsx:fetchMoreItems` | Backend applies private filtering after slicing raw ZSET rows. Client advances offset by returned rows and stops when returned count is below requested limit. | Active. Private rows can cause early termination, repeated/omitted source positions, and an empty initial page. |
| C12 | `main.py:get_single_article`; feed/wiki/sitemap filters; Next article ISR | Feed/wiki/sitemap enforce visibility; canonical direct article lookup does not. | Both public paths are active. This is a conflicting privacy contract, not merely duplicated code. |
| C13 | `scribe.py` Solr document writer; `reindex_solr.py`; `kasmir7.py:_build_solr_doc` | Multiple Solr serializers classify/category-map differently and omit ownership/visibility. `reindex_solr.py` scans all `article:*`, including non-feed/orphan/private hashes. | Scribe is active; other two are operator-reachable. Reindex can materially change search results. |
| C14 | `rss_feed.py`; `kasmir7.py` static RSS generator; Next `sitemap.ts`; Flask `/api/sitemap`; historical Caddy backups | Dynamic and static RSS/sitemap implementations overlap. Static paths filter private; dynamic Flask RSS does not. Historical Caddy routing may shadow dynamic Next output. | Generators/routes are reachable; which public file wins requires installed Caddy inspection. |
| C15 | `retention.py`; `cleanup.py`; `kasmir7.py` removal/reindex tools | Automated age pruning, scheduled orphan cleanup, and interactive maintenance all mutate overlapping Redis/Solr/file representations. | Intended complementary ownership, but Solr is best effort and each path has different selection/protection rules. Runtime schedules matter. |
| C16 | `bluesky_poster.py`, `mastodon_poster.py`, `facebook_poster.py`, `threads_poster.py`; `main.py:post_bluesky` | Four loop implementations plus a manual post endpoint maintain separate posted sets, seed/restart semantics, privacy handling, and retries. | Three posters supervised; Threads unsupervised; manual endpoint secret-reachable. Same external outcome is governed in several places. |
| C17 | `stream_utils.py:get_redis_connection`; analyzer/site config Redis clients; manual publisher | Stream helper selects `REDIS_DB`; analyzer and other consumers derive/use site Redis DB. | Active if env DB differs. Could publish and consume analysis in different databases; character builder alone validates some env/config drift. |
| C18 | `stream_consumer.py:recover_pending/process_messages`; Redis consumer-group semantics | Recovery reads only pending entries owned by fixed `consumer-1`; processing acknowledges even when `apply_analysis` returns false. | Active. Multiple/replaced consumer names or transient write failure can strand or drop work. |
| C19 | `globals.css`; `LayoutTheme.module.css`; `frontend/themes/candy.css`, `coals.css` | Global Tailwind/theme rules and component module are active; two standalone theme files have no imports found. | Active sources coexist with likely shadow styles. Visual runtime inspection needed for cascade conflicts. |
| C20 | `frontend/lib/utils.js`; `frontend/lib/utils.ts` | Both export `cn`; JS additionally exports `slugify`. Extensionless `@/lib/utils` imports depend on resolver precedence. | Both files are present and imports are widespread; TypeScript is the likely selected file, but bundler resolution should be encoded as a build contract. |
| C21 | `quiz_generator.py` vs `arc.cfg:[quiz]` | Worker reads enablement but hard-codes `CYCLE_MINUTES=300`, lock TTL, and local model instead of consuming all documented settings. Disabled mode sleeps forever while the service remains supervised. | Worker is in active service lists. Manual `--once` remains reachable. |
| C22 | `main.py` catalog constants; `backend/catalog_loader.py`; repository frontend catalogs | Plant/syndrome pages depend on `/home/ross/dual.py`, `/home/ross/perennials.py`, and `/home/ross/syndromes.py`, outside repository configuration/versioning. | API routes are active; files were not inspected under this task boundary. Repository alone cannot reproduce those pages. |

## Candidate Legacy or Shadow Code

Exactly **16 candidate areas** were identified. None should be removed without reachability/runtime confirmation.

1. **Candidate legacy/shadow code L01 — old YAML control plane:** `arc_config.yaml` and `frontend/app/about/developer/config/arc_config.yaml`. Evidence: `CODEX.md` calls the root YAML legacy, but escalation/config API/mailer still read it; the frontend copy appears unreferenced by its page.
2. **L02 — Flask local authentication realm:** `backend/auth.py`. Evidence: fully registered and functional, but current UI/docs say OAuth-only; the Next local bridge endpoint `/api/me` no longer exists.
3. **L03 — seven dead local-auth proxy fallbacks:** `getLocalAuthUserId()` in get-feed and submission/comment/upload route handlers. Evidence: every function calls an absent Flask route and silently returns empty identity.
4. **L04 — filesystem publishing pipeline:** `main.py:submit_content`, `backend/upload/pending`, `manual_publisher.py`. Evidence: new `/api/submit` comments say it replaces this for URL/text, but legacy endpoint/worker remain active.
5. **L05 — `/api/submit_pdf` compatibility alias:** `main.py:1644`. Evidence: explicit “kept for backwards-compat” alias to `submit_doc`.
6. **L06 — optional ensemble branch:** analyzer optional import/`ARC_ENSEMBLE_ENABLED`. Evidence: environment key exists by name, but no `ensemble.py` exists in the repository; import falls back disabled.
7. **L07 — Threads poster:** `backend/threads_poster.py`. Evidence: implementation exists and has the only social privacy check, but no `arc.sh`, watchdog, `arc.cfg`, or Compose service entry; docs already note no process/log.
8. **L08 — standalone reindexer:** `backend/reindex_solr.py`. Evidence: uses older Greek-deity category mapping and a serializer that differs from current scribe/kasmir implementations.
9. **L09 — Redis-to-SQLite library migration:** `ops/migrate_library_to_sqlite.py`. Evidence: library docs and `library_db.py` say migration completed in July 2026; script remains operator-runnable.
10. **L10 — disabled Cecil ingestion:** `backend/archive/cecil.py.disabled`. Evidence: deliberately disabled/archive suffix; still contains a complete submitter.
11. **L11 — historical Caddy backups:** root `Caddyfile.bak-*`. Evidence: snapshots document past routing but are not the installed config and can mislead current topology review.
12. **L12 — manual benchmark/live-model scripts:** `backend/arc_benchmark.py`, `manual_test_*.py`. Evidence: use live Ollama and, in one case, stop/start scribe; excluded from CI and unsafe as routine regression tests.
13. **L13 — unreferenced theme files:** `frontend/themes/candy.css`, `frontend/themes/coals.css`. Evidence: no imports found.
14. **L14 — duplicate utility module:** `frontend/lib/utils.js` beside `utils.ts`. Evidence: same `cn` API, likely superseded TS version, but resolver/runtime confirmation needed.
15. **L15 — static/dynamic public-file overlap:** static RSS/sitemap/news generation in `kasmir7.py` beside Flask/Next routes. Evidence: historical Caddy maps public paths to generated files, potentially shadowing routes.
16. **L16 — broad cross-stack maintenance/preflight hooks:** `backend/validate_sites.py` defaults to `/home/www/*_stack`; `kasmir7.py` explicitly opens other Redis DB families. Evidence: analyzer/scribe/character startup call validation; these paths couple Arc operation to state outside this repository. They were not executed.

## Documentation Drift

There are **18 significant comparisons**.

| ID | Classification | Claim vs implementation |
|---|---|---|
| D01 | **Contradicted** | `CLAUDE.md` says Gunicorn is 1 worker/8 threads; `arc.cfg` says 16/8; active `gunicorn_arc.sh` invokes 20/8. |
| D02 | **Contradicted** | `CODEX.md` presents `arc.cfg`/`site_config` as current and YAML as legacy; `escalation.py`, `main.py:get_config`, and `mailer.py` still consume `arc_config.yaml`. |
| D03 | **Stale/unclear** | `site_config.py` says “No consumers yet”; scribe, analyzer, character builder, retention, quiz/corpus/cleanup paths consume it. |
| D04 | **Partially confirmed** | Architecture docs correctly identify Flask/Next/Redis/Solr/SQLite and Caddy topology, but installed Caddy is outside the repo and cannot be confirmed statically. |
| D05 | **Contradicted** | Terms/privacy/developer pages say OAuth-only and “we never store passwords”; registered `auth.py` stores password hashes and reset tokens in Redis DB 5. |
| D06 | **Contradicted** | Private workspace content is promised not to be publicly visible or shared; direct article/comments, Solr/search, RSS, translation/grade, and several posters omit the visibility boundary. |
| D07 | **Partially confirmed** | Public browsing and OAuth-enabled publishing/preferences are implemented, but local Flask auth is also present and its Next bridge is stale. |
| D08 | **Contradicted** | `CLAUDE.md`, developer page, retention doc, and runbook call R/B/P first-view lazy; `main.py:publish_article` now queues every incomplete article at ingest and view only changes priority. |
| D09 | **Contradicted** | Translation module header says cloud -> local; `_call_translation_model` passes a local-only model list. `CLAUDE.md` correctly says the dedicated model retired, while old configs still advertise TranslateGemma. |
| D10 | **Stale/unclear** | Old YAML documents `translation:active`; `ollama_utils.wait_for_translation` still checks it, but current translation code does not set the key. |
| D11 | **Confirmed** | Scribe Sentinel and Counter-Analyst use `call_ollama_local_only`; analyzer R/B/P is local-first with gated cloud escalation. |
| D12 | **Confirmed** | Current TOML and retention code use 720 hours, protect reference/pinned items, prune Redis first, and treat Solr deletion as best effort. |
| D13 | **Contradicted** | `CLAUDE.md` describes mailer and Bluesky poster as cron jobs; both are continuously supervised polling loops. |
| D14 | **Partially confirmed** | Social posters retry failures on later cycles, but Bluesky/Mastodon/Threads seed all current feed rows on each startup and therefore intentionally discard outage backlog. Facebook uses a one-time seed flag instead. |
| D15 | **Confirmed** | Search lazily reconnects to Solr (`main.py:search_articles`), but failed indexing is not automatically replayed; cleanup/reindex is separate. |
| D16 | **Stale/unclear** | `ops/RUNBOOK.md` quick reference still names `itc-stack.service`; later sections say it was disabled/replaced by `arc-stack.service`. Repo unit files support the latter. Installed/enablement state was not read. |
| D17 | **Partially confirmed** | Docs call Compose a full stack, but the Compose file includes only a subset of backend workers plus frontend and points Redis/Solr at native services. Normal `arc.sh` starts most workers as host processes. |
| D18 | **Contradicted** | Feed is described as Tribonacci/roughly 33 cards. Homepage starts at 1; client requests 1, then 2, 4, 7... because it uses `b` before rotating `(1,1,2)`, not the documented 2,3,5,10,18 sequence. |

## Authentication / Authorization

### Identity systems

- **OAuth/JWT:** `frontend/lib/auth.ts` uses Google and GitHub Auth.js providers and a 30-day JWT. The raw `providerAccountId`, without a provider namespace, becomes the owner/preference ID. A numeric/string collision between providers is possible; a local username shares the same article `owner` namespace.
- **Flask local auth:** `backend/auth.py` stores password hashes, email lookup, reset tokens, and admin flags in Redis DB 5. `login_required` and `admin_required` protect its own routes. Redirect handling validates scheme/netloc and rejects protocol-relative targets.
- **Proxy trust:** `_client_user_id()` trusts `X-User-Id` only from loopback, then falls back to Flask session. `user_prefs._require_user_id()` has the same loopback rule. `upload_image()` checks only header presence rather than loopback and therefore relies on Caddy stripping plus intended proxy routing.
- **Write routes:** modern submit/text/doc/prompt/comment handlers require a user through Next proxy/loopback or Flask session. The legacy proxy fallback cannot currently translate a Flask session because `/api/me` is absent.
- **Internal secret routes:** `/api/publish_article` and `/api/post_bluesky` compare the header to `SCRIBE_SECRET_KEY`. When the API env secret is missing, both sides of the comparison can be `None`, so an absent header passes. Scribe/manual publisher use a separate `"default_secret_for_dev"` fallback and would then disagree with Flask.
- **CSRF:** OAuth route handlers rely on Auth.js/session behavior. Flask local-auth HTML forms, logout GET, and admin mutation forms have no visible CSRF token/middleware.

### Private-content boundary matrix

| Surface | Static behavior |
|---|---|
| Feed | Filters `private` unless `owner == _client_user_id()`, but after pagination slice. |
| Direct article | No ownership/visibility check. Public raw Redis lookup. |
| Article comments | No article privacy check. Public lookup by article ID. |
| Next article page/metadata | Anonymous fetch with 60-second ISR; consumes the unguarded direct endpoint and can cache title/body/metadata. |
| Wiki, sitemap, static generators, quiz | Explicitly skip private content. |
| Solr/search/reindex | Solr documents omit visibility/owner; search does not reconcile results against Redis ownership. |
| Translation | Public article lookup, no visibility check; DELETE cache endpoint also public. |
| Grade | Public article lookup, no visibility check; default model chain begins with cloud; DELETE cache endpoint public. Fresh generation currently has a separate tuple-unpack defect. |
| Dynamic Flask RSS | No visibility check and a public-cache header. |
| Bluesky/Mastodon/Facebook loops | No visibility check found. |
| Threads | Explicitly skips private, but worker is not supervised. |
| Manual Bluesky endpoint | Secret-protected, but does not reject private articles. |
| Mail digest | No visibility filter before composing operator digest entries. |

### Authorization conclusions

- The intended private rule is clear from feed/wiki/sitemap/Threads code, but it is not centralized at article retrieval or publication boundaries.
- `visibility` is not validated as an enum. Only exact lowercase `"private"` receives protection; arbitrary values are effectively public.
- Frontend-only hiding is not a boundary because direct Flask, Solr, RSS, and social workers bypass it.
- Installed Caddy rules are material to `X-User-Id`, upload routing, and static/dynamic route precedence and require a controlled runtime/configuration review.

## AI Pipeline

### Invocation inventory

| Caller / purpose | Selection and prompt | Timeout / retry / failure | Parse, persistence, consumer |
|---|---|---|---|
| `analyzer.py:analyze_article` unified R/B/P | `prompts.yaml`; local `OLLAMA_LOCAL_FALLBACK`, then cloud-only rerun if `decide_escalate`, cap, and reachability allow. | 900s each phase; queue loop retries failures; local result retained if cloud fails. | XML-ish team parser; metadata to article hash; team outputs sent to `analysis:pending`; stream consumer writes final fields. |
| `analyzer.py:generate_reply` | Embedded Counter-Analyst reply prompt; default shared cloud -> local chain. | 600s; queue retry behavior. | Parses plain response; writes `comment:{uuid}` + `comments:{article}`. Cloud usage is not recorded against weekly cap. |
| `scribe.py:run_sentinel_analysis` | Sentinel mission from `prompts.yaml`; local-only. | 900s, one model attempt; publish continues on failure. | JSON repair/parser; included in article payload. |
| `scribe.py:run_counter_analyst` | Mission from `prompts.yaml` plus embedded wrapper; local-only. | 900s, one model attempt; failure logged. | JSON/plain response -> comment hash/list. |
| `scribe.py:generate_article_from_prompt` | Hard-coded system instruction plus user prompt; local-only. | 900s, one attempt; job marked failed if empty/error. | Plain generated article -> normal publish pipeline. |
| `manual_publisher.py` Sentinel/Counter | Duplicates scribe prompts/parsers but calls default cloud-first fallback. | 900s; filesystem item retry/rename semantics. | Sentinel in publish payload; Counter comment in Redis. Cloud calls are not weekly-cap counted. |
| `translation.py:_call_translation_model` | Embedded translation prompt; explicitly supplies local model only despite stale header/config. | 300s per field; semaphore/rate limits; partial result returned but not cached. | Plain field output; Redis `translation:{id}:{lang}` and `translation:langs:{id}` on full success. Article API/UI consume. |
| `main.py` library translation | Same translation helper over library preview (first ~8K) with route-level 120s future bound. | Bounded request; stores error/status on failure. | SQLite `translations`; library page consumer. |
| `grade.py:grade_article` | Embedded grade system prompt; default shared cloud -> local. | 300s, no explicit retry beyond model chain. | **Bug:** expects two return values although shared helper returns three; fresh request likely returns 503. Intended output cached seven days. Cloud calls uncounted. |
| `character_builder.py` persona council | Character/site config prompt; local normally, cloud model when article escalation score/cap/reachability permit. | Transport 180s/read constant; infrastructure failures do not consume attempt; generated failures capped and parked with backoff. | Plain comment -> comment hash/list; per-character pending/skipped/posted/attempt keys. |
| `quiz_generator.py` daily/weekly quiz | Embedded schema-heavy prompt; hard-coded local `gemma4:e2b`. | 300s, up to 4 attempts with temperatures/reminders. | JSON validation; Redis staging key then rename to current/archive. |
| `arc_benchmark.py`, `manual_test_*.py` | Live diagnostic/benchmark prompts and model endpoints. | Manual semantics; some script actions stop/start scribe. | Console/report only; deliberately excluded from CI and not invoked here. |

### AI contract issues

- Prompt sources are split: `prompts.yaml` for core roles, embedded strings for grade, prompt-to-article, quiz, and several wrappers. There is no prompt/schema version stored consistently with outputs.
- `arc_config.yaml` escalation settings are active while the primary pipeline settings moved to `arc.cfg`.
- The weekly cloud cap records analyzer escalations and cloud character selection, but not analyzer replies, manual Sentinel/Counter, or grade. Translation was changed to local-only specifically to avoid this earlier accounting gap.
- `ollama_utils.wait_for_translation()` still polls `translation:active`; current translation no longer sets that lock, so the coordination is one-sided.
- `character_builder.REQUIRED_FIELDS` requires R/B/P/Sentinel, not Counter-Analyst despite documentation. `build_dossier_text` reads UUIDs from `comments:{id}` and attempts `json.loads(uuid)` instead of fetching `comment:{uuid}`, so existing comments are silently omitted.
- Ingest-time R/B/P queueing makes the pipeline eager in coverage but preserves view-time priority. This is reasonable behavior only if treated as a documented hybrid contract.
- No expensive/live invocation was made for this report.

## Background Workers / Scheduling

| Worker/job | Ownership and state | Recon concern |
|---|---|---|
| Gunicorn | Host process via `arc.sh`, also definable in Compose. | 20-worker script conflicts with config/docs; random Flask secret fallback can invalidate sessions across restarts/workers. |
| Scribe | Continuous RSS/priority loop; priority cycles can skip the normal RSS/retention tail. | Owns ingestion, local Sentinel/CA, Solr publication, retention, audio; broad responsibility and multiple retry state stores. |
| Analyzer | Blocking Redis list consumer; publishes to stream. | Eager + view queues; fixed dedup TTL; optional absent ensemble; cloud/accounting split. |
| Stream consumer | Redis consumer group `analysis_workers`, consumer `consumer-1`. | Acks failed applies and does not claim another consumer's stale pending messages. |
| Manual publisher | Five-second filesystem polling loop. | Old ingestion path, duplicated AI, cloud-first behavior, deterministic filenames upstream. |
| Mailer | 60-second loop; 7am digest logic. | Docs call it cron; YAML config dependency; no private filter; HTML interpolation needs deterministic escaping tests. |
| Social posters | 15-second polling loops and independent posted sets. | Restart/backlog behavior differs; no claim lock; duplicate workers could duplicate external posts; privacy differs. |
| Threads | Complete loop file. | Not in service ownership lists and may be abandoned or manually run. |
| Character builder | Polls feed, waits for analyses, schedules personas, retries parked state. | Comment reader mismatch; several Redis state sets can drift. |
| Quiz generator | Supervised even when auto generation disabled; sleeps indefinitely in disabled mode. | TOML cycle/TTL/model not fully consumed; manual `--once` path differs from daemon behavior. |
| Corpus/Caddy exporters | Continuous fast/slow loops and HTTP metrics endpoints. | Cross-stack operational setting means Arc exporter intentionally reads broader state; static repo cannot validate live cardinality/targets. |
| Cleanup | Script intended for cron, deletes orphans/images. | Schedule is only documentary in repo; overlaps retention and manual maintenance. |
| Library fetch | One-shot/weekly cron writer with a file lock and publish/revalidation handshake. | Strong tests exist; actual crontab and recovery behavior remain runtime facts. |
| Static sync/backup/log rotation | Shell/manual/cron-described operations. | Crontab is outside repo; runbook contains historical and current entries together. |
| Watchdog | Separate systemd loop, 60-second checks, exponential backoff, orphan sweep. | Duplicates `arc.sh` service definitions; `arc.sh` uses a hold marker during restart. Installed unit/enablement not checked. |

Two scheduler/owner risks merit runtime validation: Compose can define the same worker names that `arc.sh` launches as host processes, and social workers have no per-article distributed claim. A second worker instance can therefore race on external posts even though posted sets reduce the ordinary single-worker case.

## Persistence

### Redis DB 0

- Core: `article:{id}` hashes, `feed` sorted set, `processed_hashes` set.
- Ingestion/jobs: `arc:priority_uploads`, `job:{uuid}`.
- Analysis: `analyzer:queue`, `analyzer:queued:{id}`, `counteranalyst:reply_queue`, `analysis:pending` stream/group.
- Comments/reactions: `comment:{uuid}`, `comments:{article}`, reaction count/user-toggle keys.
- Preferences: `user:{providerAccountId}` hashes.
- AI caches: `translation:{article}:{lang}`, `translation:langs:{article}`, grade cache keys, quiz current/staging/archive keys.
- Social: `bluesky:posted`, `mastodon:posted`, `facebook:posted`, `threads:posted`, session/backoff/seed state.
- Characters: per-handle pending/posted/skipped/attempt hashes/sets.
- Operations: source statistics, escalation counters, heartbeats, queue timelines, metrics, circuit-breaker state.
- Protection: derived `arc:pinned_articles` and reference/preservation rules.

### Redis DB 5

- `arc:users`, `arc:user:{username}`, `arc:email:{email}`, `arc:reset:{token}`.
- Flask-Limiter keys under `arc:auth:limiter`.
- This is described as shared across applications in `auth.py`, creating an intentional identity dependency outside the OAuth realm.

### SQLite

- `backend/library_db.py` defines `works`, `work_texts`, `shelves`, `shelf_members`, and `translations`, enables WAL/foreign keys, and performs additive column migration in `init_schema()`.
- `library_fetcher.py` uses a lock, stages/fetches, replaces shelf membership transactionally, prunes unreferenced works only after successful ingestion, then authenticates a frontend revalidation request.
- A completed Redis-library migration script remains available as an operator tool.

### Solr

- Scribe writes a derived article document. Search queries Solr directly and does not reapply Redis visibility or existence checks.
- Retention deletes Redis first and Solr best effort. `cleanup.py`/`kasmir7.py` later remove search ghosts; no automatic replay was found for a failed add.
- Multiple serializers/category maps mean a full reindex can change fields/categories compared with incremental ingestion.

### Filesystem and external state

- `backend/upload/pending` is the legacy manual-publisher queue.
- `frontend/public/uploads` stores user/rehosted images; cleanup/retention remove derived image variants.
- Static RSS/sitemap/news files may be generated for Caddy.
- Logs, PID files, backups, `.env`, and frontend `.env.local` are mutable operational state. `facebook_poster.py` can persist a refreshed token back into `.env`, making configuration a runtime token store.
- Catalog source files under `/home/ross`, installed Caddy/systemd/crontab, and `/mnt/arcdata/library.db` are outside the permitted inspection boundary.

### Lifecycle/format conflicts

- Article truth spans Redis hash + feed membership + processed set + Solr doc + caches/static outputs/social state; writes are not one transaction.
- Comments use a list of UUIDs plus separate comment hashes; character builder reads the list as if it held JSON objects.
- Visibility is stored as free text. Readers vary between exact private filtering and no filtering.
- Redis Stream `MAXLEN ~10000` is bounded, but approximate trimming can theoretically remove entries during prolonged consumer outage, including pending history depending on Redis trimming semantics and lag.
- Retention intentionally tolerates Redis/Solr divergence and relies on later reconciliation.

## Frontend

- App Router pages cover feed, article, search, publish, wiki, library, quiz, sources, plants, syndromes, reporter pages, and about/legal surfaces. API route handlers proxy auth-sensitive calls to Flask.
- `ClientLayout.tsx` wraps `SessionProvider` and `UserPrefsProvider`. It also owns a mobile settings sheet; `UserMenu.tsx` owns a desktop preferences dialog.
- Homepage anonymous ISR fetches one article for 60 seconds; the client then infinite-scrolls via `/api/get_feed`.
- Article page and metadata are anonymous ISR for 60 seconds and fetch direct article/comments without user identity.
- Translation is click-triggered in feed; deep-linked article language can trigger/cache translation. `TranslateButton` has materially better focus/keyboard menu handling than `UserMenu`.
- `IntelligenceCard.tsx` is the main article renderer and uses several fields missing from the `Article` type via casts/loose assumptions. The type omits visibility/owner/cached language and several analysis metadata fields.
- `globals.css` is the broad visual source; `LayoutTheme.module.css` controls layout theme. Two old standalone theme files were not referenced.
- `public/sw.js` correctly avoids `/api/*`, but caches every other same-origin GET by URL only. Authenticated/private HTML can remain available after logout/offline on the same device. The cache name is now build-stamped by Docker, so older docs saying it is only manually bumped are stale; the HTML privacy issue remains.
- `UserMenu.tsx` renders `<LogIn>` but does not import it from `lucide-react`; this is a static compile error candidate. CI would normally catch it if the exact worktree is pushed, but no build was run here.
- No analytics/tracker SDK was found. Fonts are local. External interactions include OAuth providers, original-source/social links, profile images, and browser speech synthesis.

## Accessibility / Privacy

### Positive static evidence

- A skip link, main/navigation landmarks, `role=feed`, feed positions, visible focus utility, explicit labels on many icon controls, live status/error regions, and keyboard-aware search/translation menus are present.
- Decorative icons are frequently `aria-hidden`; dialogs generally expose labels and Escape/return-focus behavior.
- No third-party font/CDN tracker was found in the application source.

### Issues to encode as deterministic checks

- `frontend/app/layout.tsx` sets `maximumScale: 1`, blocking pinch zoom and conflicting with WCAG resize expectations. Existing docs already identify this.
- `UserMenu` desktop dialog sets `aria-modal=true` but does not move initial focus or trap focus. The mobile sheet moves focus but likewise has no full focus containment. Publish confirmation should receive the same browser-level focus regression coverage.
- Local Flask auth forms use visible labels without consistent `for`/`id` associations; password visibility controls need accessible-name/state checks.
- Service-worker HTML caching can expose a prior authenticated/private page after logout on the same device/offline.
- Publish drafts store title/content/description in `localStorage`; privacy/legal pages do not disclose local draft persistence. This matters on shared devices.
- Legal copy says private work is not shared with third parties, while grade uses a cloud-first model path and private-boundary omissions could feed social/API consumers.
- Browser speech synthesis is used for listening; it is a browser API rather than an evident tracker, but should remain in privacy inventory.

## Security

This was code review only, not penetration testing.

- **Private authorization is fragmented:** see the boundary matrix. This is the principal security issue.
- **Missing-secret fail-open:** if Flask `SCRIBE_SECRET_KEY` is unset, `None != None` is false and secret endpoints accept an absent header. Worker defaults use a known development string, causing a second failure mode.
- **CSRF:** local-auth mutation forms and GET logout have no evident CSRF protection.
- **SSRF:** scribe's main article fetch has a redirect-aware address guard, but `main.fetch_and_process_url`, legacy/manual publisher fetches, social thumbnail fetches, and scribe image rehosting use ordinary `requests` paths. The image path validates only the initial host and follows redirects, enabling a redirect-boundary bypass candidate.
- **Proxy trust:** most `X-User-Id` consumers verify loopback; `upload_image` verifies only header presence and depends on Caddy stripping/routing. Historical Caddy backups are insufficient proof of the installed boundary.
- **Secret/config fallbacks:** Auth.js provider dummy credentials are build-friendly and should fail visibly at runtime; Flask random `SECRET_KEY` fallback invalidates sessions across restarts/workers rather than exposing a fixed secret. This reliability failure can mask auth issues.
- **Unsafe output:** RSS analysis is bleach-sanitized. React rendering is generally escaped/sanitized, but mailer builds HTML from article/log-derived strings without a clear escaping boundary. Add a deterministic injection regression before assuming safety.
- **Logging endpoints:** `/api/alert` and `/api/csp_report` are public bounded log-ingest surfaces. Size/semaphore controls exist; structured sanitization/log-forging coverage does not.
- **Mutable `.env`:** Facebook poster rewrites refreshed credentials into `.env`; concurrent deployment/backup/process readers can see inconsistent state.
- **Visibility validation:** non-enum values bypass the only exact private comparison.
- **Identity collision:** OAuth IDs are not prefixed with provider name and share article owner namespace with local usernames.
- **External command/path handling:** scribe audio uses argument-list `subprocess.run` and fixed host/path structure rather than `shell=True`. No unsafe Python deserialization was found; YAML uses safe loading in reviewed paths.
- **Catalog reproducibility:** `catalog_loader.py` imports Python files by absolute path outside the repo. This is executable configuration and not covered by repository review/versioning.

## Existing Test Coverage

No tests were executed. Static inventory:

- `backend/tests/test_retention.py`: satellite/image purge and idempotence.
- `backend/tests/test_library_refresh.py`: library schema/API, locks, interruption, pagination integrity, idempotence, publication/revalidation failure contracts.
- `backend/tests/test_intelligence_instrumentation.py`: operational namespace/labels/readiness, queue timeline Lua/state, duplicate ordering, Redis failure behavior, analyzer process/heartbeat metrics. Some tests can use temporary Redis.
- `backend/tests/test_quiz_generator.py`: attribution-removal and retry-reminder helpers only.
- `backend/tests/test_translation.py`: cached-only semantics and rate-limit buckets/headers.
- `backend/tests/test_smoke.py`: feed offline/empty/clamps, library gate, Bluesky secret rejection (with configured secret), upload header absence, reaction rate limit.
- `backend/tests/test_publication_metadata.py`: SQLite additive migration, publication-year extraction/rejection, idempotence, API serialization, backfill resume.
- `monitoring/tests/test_alloy_config.py`: monitoring configuration checks.
- `frontend/tests/library-revalidation-route.test.mjs`: method/secret fail-closed behavior for one route.
- `.github/workflows/verify.yml`: frontend `npm ci`, build, `tsc`; backend `py_compile` and pytest. It explicitly does not deploy and is not branch-protection-blocking. The package's `test:library-route` script is not invoked by this workflow.
- No Playwright/Cypress/browser suite, axe/Lighthouse gate, frontend component unit suite, API schema suite, security regression suite, or deterministic mocked AI contract suite was found.
- `arc_benchmark.py` and `manual_test_*` are manual live-service tools, not permanent safe regression coverage.

## Important Untested Contracts

There are **22 important gaps**—behaviors likely to be rediscovered manually because they are not encoded as permanent regression tests.

1. **T01:** private owner vs anonymous behavior for direct article, comments, metadata, feed, wiki, sitemap, RSS, search, translation, grade, social, and digest.
2. **T02:** visibility enum normalization/rejection at every submission type.
3. **T03:** OAuth proxy loopback/header contract and installed Caddy header stripping/routing.
4. **T04:** local Flask auth coexistence, `/api/me` removal, admin authorization, CSRF, and safe redirects.
5. **T05:** missing `SCRIBE_SECRET_KEY` must fail closed for publish/social/library-style internal endpoints.
6. **T06:** preference `null` clear round-trip and OAuth identity/provider namespacing.
7. **T07:** feed pagination across interspersed private/orphan rows, including empty anonymous first slice.
8. **T08:** article ISR/service-worker behavior before and after login/logout/offline.
9. **T09:** Solr serializer parity, private exclusion, failed-add replay, lazy reconnect, and Redis/Solr ghost reconciliation.
10. **T10:** analyzer ingest-tail/view-head ordering, dedup TTL, partial-analysis requeue, and crash recovery.
11. **T11:** Redis Stream at-least-once behavior, stale PEL claiming, failed apply, acknowledgement, and trim under lag.
12. **T12:** model selection precedence across env/TOML/YAML/hard-coded callers and installed model availability.
13. **T13:** cloud cap accounting for every cloud-capable caller and reachability-before-count.
14. **T14:** deterministic AI output schemas/parsers for R/B/P XML, Sentinel JSON, grade tuple, translation partials, character comments, and quiz JSON.
15. **T15:** timeout/retry/failure labeling when local model, cloud model, or one inference host is unavailable.
16. **T16:** social poster privacy, per-article claims, restart backlog, duplicate-post prevention, and platform retry state.
17. **T17:** legacy filesystem same-title collision and equivalence with Redis submission metadata/visibility.
18. **T18:** worker/service inventory consistency across `arc.cfg`, `arc.sh`, watchdog, Compose, and unit files.
19. **T19:** retention/cleanup failure ordering, pinned/reference preservation, static regeneration, and social/cache satellite cleanup.
20. **T20:** browser publish/login/preferences/translation/search/article flows plus keyboard/focus/zoom/ARIA checks.
21. **T21:** SSRF redirect/DNS-rebinding defenses for article, image, social-card, and manual fetch paths.
22. **T22:** configuration/dashboard/docs contract, catalog file availability, and prevention of accidental cross-project dependencies.

## Recommended SDET / Preflight Priorities

### Fast deterministic

- Compile/import Python without importing live services; run TypeScript/build and include the existing frontend Node test.
- Validate all configuration sources and assert effective values/service lists agree or are explicitly delegated.
- Schema-contract tests for article visibility/owner, comments, analysis stream messages, translations, grade, quizzes, SQLite rows, and Solr documents.
- Fail-closed tests for missing internal secrets and forged `X-User-Id` from non-loopback.
- Static route inventory with required auth/privacy policy per endpoint.
- Known security regressions: CSRF expectations, redirect validation, SSRF URL/redirect guards, HTML/email sanitization, path collision.

### API / integration

- Flask test clients with fake Redis/Solr/SQLite for public/owner/other-user matrices.
- Redis-backed contract suite for list/stream ordering, pending recovery, social claims, TTLs, retention, and preferences.
- Solr integration fixture for index/search/reconnect/private exclusion and reindex parity.
- SQLite temporary-db migrations, WAL concurrency, library refresh/revalidation, translations, and prune invariants.
- Caddy adapted-config test fixture that asserts path routing and header stripping without touching the installed service.

### Browser

- Anonymous public feed and article; OAuth-stubbed login; owner private feed/article; other-user denial.
- Infinite-scroll pagination across private gaps and directive filters.
- Preferences save/clear/delete; publish URL/text/doc/prompt/video; job polling.
- Search, article metadata, translation cache/fresh/partial, comments/reactions, service-worker logout/offline behavior.
- Use deterministic browser fixtures; do not depend on live OAuth/social/model providers.

### AI

- Inject a fake Ollama transport and snapshot prompt/schema versions rather than call live inference.
- Table-test routing: local success, parser failure, escalation policy, cloud cap, cloud unreachable, local unavailable, timeout, partial output.
- Verify three-value helper contracts at every caller and cap accounting at every cloud-capable call.
- Deterministic parser/post-processing tests for every role and persistence payload.

### Resilience

- Redis unavailable/OOM-write failure, Solr unavailable/reconnect/replay, SQLite locked, model host failover, worker crash between write/ack, duplicate worker start, watchdog restart, and social retry/backlog.
- Assert idempotence/claims so a restart cannot double-publish or silently drop analysis.

### Accessibility / privacy

- axe plus targeted keyboard/focus tests for menus/dialogs/search/translation/publish/quiz.
- Assert zoom is not disabled and landmarks/headings/labels are stable.
- Mechanical dependency inventory for trackers/CDNs/external resources/browser storage.
- Service-worker cache-policy tests that forbid authenticated/private HTML retention.

Suggested preflight tiers: `fast` on every commit, hermetic `api/integration` on every PR, browser/a11y/security on PR or nightly, mocked AI contracts on every PR, and live-service/model resilience only in an explicitly isolated release environment.

## Findings by Severity

The following 48 findings are deduplicated for prioritization. Severity reflects plausible impact, not proof of live exploitation.

### P0 — 5

1. **P0-01:** Direct article/comments and anonymous ISR omit private ownership checks (`main.py:get_single_article`, comment route, `frontend/app/article/[slug]/page.tsx`). Potential public/cached private-content disclosure.
2. **P0-02:** Solr writers/search omit visibility/owner (`scribe.py`, `reindex_solr.py`, `main.py:search_articles`). Potential private-content search disclosure.
3. **P0-03:** Translation and grade fetch private articles without auth; grade is cloud-first when its tuple bug is corrected/cached paths exist. Potential processing/disclosure outside intended boundary.
4. **P0-04:** Dynamic RSS and Bluesky/Mastodon/Facebook publishers omit private filters; manual Bluesky can post any article ID. Potential irreversible external publication.
5. **P0-05:** Legacy `submit_content` names pending files as `secure_filename(title).txt`; two same-title pending submissions overwrite before processing. Potential user-content data loss.

### P1 — 19

1. **P1-01:** Missing Flask scribe secret can fail open because absent header equals `None`.
2. **P1-02:** Active filesystem and Redis ingestion paths have incompatible visibility, AI, retry, and job contracts.
3. **P1-03:** Stream consumer acknowledges unsuccessful applies and cannot claim another consumer's stale pending work.
4. **P1-04:** Feed/private post-filter pagination advances by returned count and can stop early or omit content.
5. **P1-05:** Preference clear stores `"None"` rather than clearing language.
6. **P1-06:** Three active config mechanisms select different models/escalation/services.
7. **P1-07:** Model selection/dashboard can advertise retired or unavailable models; current availability is not preflighted.
8. **P1-08:** Grade caller expects two values from a three-value helper, breaking fresh grading.
9. **P1-09:** Manual publisher/analyzer reply/grade cloud calls bypass weekly cap accounting.
10. **P1-10:** Social workers have no distributed claim; duplicate worker ownership can duplicate external posts.
11. **P1-11:** Social restart seeding differs and three posters discard outage backlog.
12. **P1-12:** Upload auth checks header presence but not loopback, relying entirely on installed Caddy routing/stripping.
13. **P1-13:** Several authenticated URL/image/social fetch paths lack the redirect-aware SSRF guard.
14. **P1-14:** Flask password/admin mutation forms have no evident CSRF protection.
15. **P1-15:** `visibility` accepts arbitrary strings; only exact `private` is protected.
16. **P1-16:** Character dossier silently omits comments because it parses UUID list members as JSON.
17. **P1-17:** Redis DB selection for analysis streams can diverge between env and site config.
18. **P1-18:** Gunicorn effective worker count conflicts with config/docs and magnifies memory/session/rate-limit behavior.
19. **P1-19:** `UserMenu.tsx` references `LogIn` without importing it, a frontend build failure candidate.

### P2 — 20

1. **P2-01:** OAuth and Flask auth realms coexist while proxy fallback calls a removed endpoint.
2. **P2-02:** OAuth owner IDs are not provider-namespaced and can collide with each other/local usernames.
3. **P2-03:** R/B/P documentation says lazy while code queues at ingest and prioritizes on view.
4. **P2-04:** Service inventories are duplicated across five files and Threads is unowned.
5. **P2-05:** Compose “full stack” wording can lead operators to duplicate/omit host workers.
6. **P2-06:** Multiple Solr serializers/category maps can alter results during reindex.
7. **P2-07:** Redis-first/Solr-best-effort retention creates temporary search ghosts with no automatic replay.
8. **P2-08:** One-sided obsolete `translation:active` coordination remains in shared AI helper.
9. **P2-09:** Mailer may interpolate unescaped article/log-derived content into HTML.
10. **P2-10:** Public alert/CSP log-ingest endpoints need log-forging/pollution regression coverage.
11. **P2-11:** Facebook poster persists refreshed secrets into `.env` at runtime.
12. **P2-12:** Service worker caches same-origin HTML without auth/private discrimination.
13. **P2-13:** `maximumScale:1` prevents pinch zoom.
14. **P2-14:** Desktop preferences dialog lacks initial focus/focus containment; other modal flows need equivalent checks.
15. **P2-15:** Local auth label/control semantics and password-toggle accessible state are inconsistent.
16. **P2-16:** Publish drafts persist content in localStorage without privacy-page disclosure.
17. **P2-17:** Frontend `Article` type omits fields the renderer/API use, encouraging `any` casts and schema drift.
18. **P2-18:** External Python catalog files make repo builds non-reproducible and untested.
19. **P2-19:** Static and dynamic sitemap/RSS ownership depends on installed Caddy route order.
20. **P2-20:** Quiz service consumes only part of its TOML config and remains supervised in permanent sleep when disabled.

### P3 — 4

1. **P3-01:** Duplicate desktop/mobile preference UIs increase maintenance and accessibility drift.
2. **P3-02:** `utils.js`/`utils.ts` and unreferenced candy/coals themes are simplification candidates.
3. **P3-03:** Compatibility aliases, migration scripts, old Caddy snapshots, and manual benchmarks need explicit archival labels/indexing.
4. **P3-04:** Comments, config notes, and service tables contain stale version prose/naming that obscures otherwise sound current mechanisms.

## Files Claude Should Inspect First

1. `backend/main.py` — canonical routes, publish/feed/direct article/auth trust, submission variants, Solr search, Bluesky endpoint.
2. `backend/scribe.py` — ingestion, SSRF-aware article fetch vs image fetch, Solr document, local AI, priority/RSS loops, retention.
3. `backend/analyzer.py`, `backend/stream_consumer.py`, `backend/stream_utils.py` — R/B/P queue, escalation, stream delivery/persistence.
4. `backend/translation.py`, `backend/grade.py`, `backend/user_prefs.py` — concrete cross-layer tuple/privacy/null contracts.
5. `backend/auth.py` and `frontend/lib/auth.ts` — two auth realms and identity namespace.
6. `frontend/app/article/[slug]/page.tsx`, `frontend/app/page.tsx`, `frontend/components/FeedClient.tsx` — ISR/private/pagination behavior.
7. `frontend/app/api/get_feed/route.ts` and sibling submission proxies — repeated dead `/api/me` fallback.
8. `backend/bluesky_poster.py`, `mastodon_poster.py`, `facebook_poster.py`, `threads_poster.py` — privacy and restart/claim differences.
9. `arc.cfg`, `arc_config.yaml`, `backend/site_config.py`, `backend/ollama_utils.py`, `backend/escalation.py` — configuration/model split.
10. `arc.sh`, `watchdog.sh`, `docker-compose.yml`, `ops/systemd/*` — service ownership and duplicate-start boundaries.
11. `backend/retention.py`, `backend/cleanup.py`, `backend/reindex_solr.py`, `backend/kasmir7.py` — persistence reconciliation and old/new operator paths.
12. `frontend/public/sw.js`, `frontend/app/ClientLayout.tsx`, `frontend/components/UserMenu.tsx`, `frontend/app/layout.tsx` — privacy/accessibility/build issues.

## Questions That Require Runtime Testing

- Which Caddyfile is installed, which handler wins for `/api/upload_image`, `/rss.xml`, sitemap paths, and Next API proxies, and are untrusted identity headers stripped?
- Are `arc-stack.service` and `arc-watchdog.service` installed/enabled, and is the legacy unit disabled as the later runbook says?
- What crontab/timer entries actually run cleanup, library refresh, static generation, backup, and log rotation?
- Which service instances are live: host workers, Compose workers, or both? Is Threads intentionally off?
- What values/models/endpoints are effective from env/TOML/YAML, and which local/cloud models are actually installed/reachable?
- Are any private articles currently indexed in Solr, cached in translations/grades/service worker, included in RSS, or present in social posted queues?
- Does live Redis DB selection match for analyzer, stream producer/consumer, manual publisher, and operational tooling?
- Does the consumer group contain pending messages owned by obsolete consumer names; has stream trimming occurred under lag?
- Does the current worktree frontend build fail on the missing `LogIn` import or resolve it through an unexpected mechanism?
- Are catalog files under `/home/ross` present and version-matched? They were deliberately not read.
- Do OAuth provider account IDs collide in the current user corpus, and are local-auth accounts still used?
- Does the service worker currently control clients built before/after cache stamping, and can logged-out/offline browsing recover authenticated HTML?
- Which static generator output is served publicly, and how recently was it regenerated?
- Are Solr schema fields compatible with every serializer, particularly date/category and any future visibility field?

## Suggested Next Steps

1. Treat private-content handling as a single architecture contract and build a hermetic owner/other/anonymous matrix before changing code.
2. Capture effective runtime configuration (without secrets) and installed Caddy/systemd/crontab/model inventories in a controlled follow-up; reconcile that evidence with this static map.
3. Define explicit canonical owners for configuration, service inventory, article serialization, auth identity, visibility, and social claim/retry state.
4. Convert P0/P1 findings first into failing deterministic tests; only then decide whether each duplicate/legacy path remains supported, migrates, or is retired.
5. Add browser/service-worker and mocked AI contract suites. Keep live AI/social/OAuth tests opt-in and isolated.
6. Update public/legal/developer documentation only after runtime behavior and privacy boundaries are verified.
7. Archive or label historical tools/configs rather than deleting them until reachability and rollback needs are established.

## SDET / Engineering Practice Note

This reconnaissance is a test-plan seed, not evidence that the proposed tests exist. Each route/worker/storage table can become a machine-readable architecture contract: endpoints mapped to auth and visibility policy; Redis/Solr/SQLite serializers checked against schemas; service/config lists compared in preflight; known security and accessibility failures preserved as regressions; and AI calls run against deterministic fake transports with fixed parser outputs, timeouts, and escalation signals. A release preflight can then compose fast compile/schema/security checks, hermetic API/storage integration, browser/accessibility/privacy flows, mocked AI-agent contracts, and isolated resilience scenarios. That converts future “rediscovery” into a reproducible failure with an owner and expected outcome.
