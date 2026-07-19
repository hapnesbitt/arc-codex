# Arc Stack Ops Runbook

Records host-level changes that live outside git (redis.conf, fstab, sysctl),
so the repo history stays the single narrative of what changed and why.

## 2026-07-15 — Playwright Tier-3 restored (arc only for now)

Restored after March 2026 retirement (commit 0abc395). New module
`backend/playwright_tier3.py`. Wired through the pre-existing
`fetch_with_anti_bot_handling()` seam and into `scribe.fetch_article_data`
as the tier-3 fallback after simple + stealth-headers both fail.

### Why it was retired (March 2026)

Two independent failure modes both attributable to the Z230's AMD
FirePro W2100 radeon:

1. **Radeon UBSAN kernel lockup** — Playwright/chromium picked up the
   radeon GPU via ROCm auto-detect on some pages. The GPU's
   FirePro-era driver triggers UBSAN in-kernel and hard-locks the box.
   Not survivable; scribe would take the whole machine with it.

2. **fd exhaustion** — a leak in the pre-retirement code let context/
   page handles accumulate across a long scribe run. Chromium keeps
   many fds per page (sockets, /dev/shm, /proc entries). At ~700+
   chromium processes the fd limit was hit and scribe wedged. The
   pre-retirement workaround was a `BROWSER_RECYCLE_INTERVAL=20` cap,
   never satisfying because the leak was per-context, not per-browser.

### Why restore now

Preconditions turned favorable in the last two weeks:

- **M1 shed council** — analysis backlog runs on Z230 spare cycles;
  scribe's own inference is off the M1's critical path.
- **Negative cache** (2026-07-13, commit 097e747) — repeated-dead URLs
  are cache-skipped, so tier-3 never re-hammers them on the next sweep.
- **Radeon exile proven** — this morning (2026-07-15) Vulkan
  auto-detection crashed Ollama on startup. The fix was to disable
  Vulkan; same principle applies here: any subsystem that touches this
  GPU dies. Explicit exile in every launch is a proven pattern.

### Constraint map (every one is load-bearing)

| Retirement reason | Mitigation in `playwright_tier3.py` |
|---|---|
| Radeon ROCm crash | `--disable-gpu` + `--use-gl=disabled` + `--disable-software-rasterizer` in `_LAUNCH_ARGS`, plus `DISPLAY=""` in the subprocess env to short-circuit any code that gates on display presence. |
| Radeon Vulkan crash | Same launch args; belt-and-braces. |
| fd exhaustion (per-context leak) | Every fetch creates its own `BrowserContext + Page` in a try/finally that closes both — even on page crash. `RESTART_EVERY = 50` fetches recycles the whole browser to bound any incremental leak. |
| Hang → wedge | `FETCH_TIMEOUT_SECONDS = 45` wall-clock. A watchdog thread SIGTERMs/SIGKILLs the browser process tree on timeout; the main thread's playwright RPC calls then raise, the try/finally cleans up, next fetch re-launches. |
| Parallel-fetch race | `_lock` serializes every fetch. **ONE** browser instance, no parallel pages. |
| Redundant fetches on known-dead URLs | Tier-3 fires only after simple AND stealth fail, and only for URLs not in `scribe:dead_url:*` (checked at top of `fetch_article_data`). |
| Playwright sync API is greenlet-bound | Fetch runs on the caller's thread. Watchdog is a separate thread that only kills the browser subprocess — greenlets are not crossed. |
| Zombie browsers after scribe crash | Startup hook `playwright_tier3.startup_kill_zombies()` matches on `/proc/<pid>/environ` for `ARC_TIER3_PLAYWRIGHT=1`. See "zombie signature" below. |

### The radeon's two-incident exile history

| Date | Subsystem | Symptom | Cause | Fix |
|------|-----------|---------|-------|-----|
| 2026-03-13 | Playwright/chromium (ROCm) | Box hard-locked mid-fetch | AMD FirePro W2100 UBSAN kernel bug in radeon driver | Retire Playwright (commit 0abc395) |
| 2026-07-15 | Ollama (Vulkan) | Ollama crashed on startup | Vulkan auto-detected the radeon | Disable Vulkan |
| 2026-07-15 | Playwright/chromium (restoration) | (prevented) | Would repeat March if any GPU path opens | `--disable-gpu` + `--use-gl=disabled` + `DISPLAY=""` env + `--disable-software-rasterizer` |

**Rule for this GPU:** every new subsystem must explicitly disable every
plausible GPU/display path. Assume the radeon will find any door.

### Zombie signature

Every chromium subprocess launched by `playwright_tier3` inherits
`ARC_TIER3_PLAYWRIGHT=1` in its environment (via playwright's
`launch(env=…)`). The startup killer walks `/proc/<pid>/environ` on
every process and terminates any that carry this marker.

Why env vs a `--flag`: Playwright rejects `--user-data-dir` as a launch
arg (must go through `launch_persistent_context`), and any generic
chromium flag could collide with a real desktop browser and false-
positive-kill it. Env vars are (a) accepted by playwright's launch
API, (b) inherited only into subprocesses WE launch, and (c) invisible
to `ps` / `pgrep` — you have to read `/proc/<pid>/environ` explicitly.
Ross's desktop Chrome will never have this marker.

### Per-fetch cost (measured 2026-07-15 pre-deploy smoke)

- Browser cold start: ~1.5s
- example.com fetch: ~2.4s (short page, MIN_ARTICLE_LENGTH gate)
- thehill.com fetch: ~3.4s, 320 chars extracted despite CAPTCHA
- Steady-state chromium RSS: ~325 MB
- Peak RSS after 2 fetches: ~337 MB
- Watchdog kills (during smoke): 0

Under real load with council yielding on the M1, expect RSS to sit in
the 300-400 MB range and drift up slowly between the 50-fetch restarts.
Per-fetch cost is dominated by the 2s wait_for_timeout page settle.

### Verify pass — TBD, runbook back-annotated after go-live

Class-2 census target domains: thehill.com, nu.nl, wineenthusiast.com,
nytimes.com, bloomberg.com. Bloomberg is an experiment, not a promise
— walls often beat headless.

### Hunt

Hunt has the same bot-walled domains (bloomberg, nytimes, wsj, reuters,
apnews, thehill, axios — 51 matches in its sources.json), so it would
benefit from the same treatment. Recommendation: mirror to Hunt after
Arc has a stable ~24h under the restored tier-3, not before — the
radeon has a track record and one host at a time is safer.

## 2026-07-15 — CA_WAIT 20s → 120s: coupling bug between shed-and-yield and the poster fix

Sunday landed two workstreams the same day whose assumptions diverged
under the current pipeline:

1. **Poster fix (a65cc98 / 72fb8f1)** — shared `comment_utils.py`
   reader; also reduced CA_WAIT 60s → 20s on the premise "scribe seeds
   the CA at publish, so 20s is enough."
2. **Shed-and-yield (52e83bf / 24ce1d2 / 171cd75 / c642531)** — council
   local-tier CA generation rehomed M1 → Z230 spare-cycles. Made CA
   generation ASYNCHRONOUS relative to publish (drains from a queue on
   available cycles), not synchronous at publish.

The two together give a coupling bug: the poster asks "is the CA there
yet?" 20s after publish, but the CA now arrives whenever the Z230 spare-
cycle drain reaches it. First measured example this morning:

    11:32:39 UTC — article published to feed
    11:32:49 UTC — bluesky_poster starts polling for CA
    11:33:09 UTC — bluesky gives up (20s window) → posts purple excerpt
    11:33:13 UTC — mastodon gives up too, same reason
    11:34:21 UTC — CA finally lands (72s after publish)

Landed: 120s CA_WAIT on both stacks (arc `<pending>`, hunt `<pending>`).
Doubles the highest measured value as a safety margin. **120s is a
FLOOR, not a ceiling** — 72s was on a quiet pipeline; under council
yielding + backlog, CA generation can and will exceed 120s. Some posts
will continue to fall back to the purple excerpt. That is expected under
this architecture, not a regression.

### Real fix: event-driven posting (REGISTERED, not built)

The right fix removes the timing coupling entirely rather than tuning
around it:

- CA generation, on completion (inside analyzer.py / the shed-and-yield
  drainer), enqueues the article ID to a `posters:ready` LIST (or Redis
  Streams entry, one per channel).
- `bluesky_poster` / `mastodon_poster` / `facebook_poster` block on
  BLPOP of that queue instead of polling `feed` + waiting on CA.
- Removes `CA_WAIT` from every poster (constant + call sites + doc).
- Publisher path stays untouched — "publish like greased lightning"
  still applies; the poster just waits on the CA-ready signal instead
  of doing a busy-wait.

Benefits: works at any CA latency (60s, 120s, 600s under load), zero
false-negative fallbacks, no wasted hgetall polls, and posts land
promptly the moment CA is ready. Supersedes CA_WAIT tuning permanently.

Not scheduled — noted here so future-me (or a fresh session) can pick
this up without re-diagnosing the coupling. Until then, CA_WAIT tuning
is the escape valve.

## 2026-07-15 — LinkedIn poster + OAuth retired (both stacks)

Owner no longer has a LinkedIn account. Retired the channel end-to-end
across arc-codex and huntaegis rather than leave dead code, stale docs,
and expiring tokens to maintain.

Landed:
- arc  26929a5 — delete linkedin_poster.py + linkedin_auth.py, remove
  from arc_config.yaml (linkedin block + service entry), main.py runtime
  block, project_context.yaml (service entry, autopost/posted-set keys,
  auth stack, linkedin_notes), arc.sh header comment; strip 8 frontend
  UI mentions (contact/privacy/terms/support/developer/config +
  IntelligenceCard tooltip + auth.ts docstring); update comment_utils
  docstring 4→3 posters.
- hunt 7c0856a — same, plus fix a stale mislabel in support/page.tsx
  ("The LinkedIn Poster (bluesky_poster.py)" → Bluesky Poster) and
  drop "No LinkedIn poster" from key_differences_from_arc_codex since
  it's no longer a difference.

Owner action still required — NOT done by these commits:
- Revoke on LinkedIn side: LinkedIn Developer app "arc-codex"
  (client_id `77gih47e82m35z`), then delete these env vars from
  `backend/.env` on BOTH stacks:
    LINKEDIN_CLIENT_ID
    LINKEDIN_CLIENT_SECRET
    LINKEDIN_ACCESS_TOKEN
    LINKEDIN_MEMBER_ID
    LINKEDIN_REFRESH_TOKEN
  The commits deliberately do not touch `.env` — needs the LinkedIn-side
  revoke first so we don't leave stale-active tokens around after code
  removal.

Preserved deliberately:
- `sources.json`: `LinkedIn Engineering` RSS feed (ingest source,
  orthogonal to the retired outbound channel)
- `linkedinbot` in bot UA lists (main.py + caddy_exporter.py) — crawler
  detection, orthogonal
- All `project_context.yaml` version-history entries mentioning LinkedIn
  (accurate history)
- `IntelligenceCard.tsx` historical comment "X/Facebook/LinkedIn removed"
  (accurate history)

Verification: `grep -rn "linkedin\|LinkedIn" ...` returns only
intentional retirement notes on both stacks. `npx tsc --noEmit`
passes on both frontends.

## 2026-07-15 — scribe cloud-budget knobs (both stacks)

Two `backend/scribe.py` constants are load-bearing for weekly cloud spend
on `gemma4:31b-cloud`. **Do NOT revert either of these back to earlier
"default" values without checking the weekly allowance dashboard first.**

### `CYCLE_MINUTES = 69` (both stacks)

Sweep cadence. Each sweep issues cloud calls per candidate (sentinel +
counter-analyst pre-publish, both routed via `call_ollama_local_only`
which falls through to cloud on local unavailability). Prior aggressive
value of `1` was burning through the weekly gemma4 allowance well before
reset. 69m is prime-adjacent and decoupled between Arc and Hunt so the
two stacks don't sync-fire cloud calls.

- Landed: arc a0cb52d, hunt e1a45aa (2026-07-15)
- If cloud spend regresses: check this constant BEFORE assuming a new
  code-path caused it. The "chosen 2026-06" comment on the prior value
  described the OLD cadence; do not restore it.

### `MAX_CONCURRENT_ANALYZERS = 10` (arc only; hunt kept at 2)

Local-only NLP concurrency for `api_client.pre_analyze` →
Flask `/api/pre_analyze` (spaCy/VADER/textstat/textblob). **Does NOT
touch cloud** — Flask caps actual parallelism at 2 via
`_pre_analyze_sem = Semaphore(2)`; threads above that hit 429 (1s wait)
and fall through to `{'sentiment': 0.0}`. Bumped to 10 for parity with
sweep shape; harmless to budget. See scribe.py:1878 for the executor.

- Landed: arc a0cb52d (2026-07-15). Hunt kept at 2 — no reason to churn.

### Verification (2026-07-15 trace)

- `MAX_CONCURRENT_ANALYZERS` used only at scribe.py:1878 in a
  ThreadPoolExecutor dispatching to `api_client.pre_analyze`.
- `api_client.pre_analyze` (scribe.py:1300) POSTs to Flask
  `/api/pre_analyze` (main.py:1158) which does local NLP only.
- Cloud paths (`call_ollama_local_only` for sentinel + CA at
  scribe.py:1401/1460) are per-candidate serial within a sweep, not
  fanned by this executor. Cloud spend scales with `CYCLE_MINUTES`,
  not `MAX_CONCURRENT_ANALYZERS`.


## 2026-07-09 — Cecil retired (audit findings #1, #2)

**Motivation**: 2026-07-09 security audit found the Cecil email-to-publish
daemon's sender check was trivially spoofable — Postfix `check_sender_access`
runs against the SMTP envelope MAIL FROM (unverified) and OpenDKIM's
`milter_default_action = accept` means DKIM failure does not reject. No
DMARC enforcement was in place. Anyone on the internet could publish
articles attributed to `ross` by connecting to port 25. Cecil also accepted
`image/*` attachments with no SVG filter → stored XSS in the arc-codex.com
origin.

### Actions taken

- `systemctl stop cecil && systemctl disable cecil` — service was
  `active/enabled` at time of the audit, now `inactive/disabled`.
- `backend/cecil.py` archived (git mv) to
  `backend/archive/cecil.py.disabled` — history preserved via
  `git log --follow`. The systemd unit was copied to
  `backend/archive/cecil.service.disabled` alongside it.
- Cecil-user ACLs on `frontend/public/uploads` and `logs` removed (see
  `scratchpad/step1_cecil_remove.sh`, run as root).
- Postfix wiring removed: the `cecil_sender_check` restriction class,
  its `check_sender_access pcre:/etc/postfix/cecil_senders.pcre` line,
  and the `check_recipient_access hash:/etc/postfix/cecil_recipients`
  entry inside `smtpd_recipient_restrictions`. Backup at
  `/etc/postfix/main.cf.bak-cecil-remove-<ts>`.
- `/etc/postfix/cecil_senders.pcre` and `/etc/postfix/cecil_recipients{,.db}`
  deleted.
- `/home/cecil/Maildir` archived to `/home/cecil/Maildir.retired-<date>`
  (kept for forensics; three prior failed-mail messages sit in
  `.Failed/cur/` from earlier rejected sender tests).
- Cecil system account locked (`usermod -L cecil`,
  `-s /usr/sbin/nologin`). User + group left present so ACL removal
  doesn't orphan any leftover file.

### Port 25 decision — LEAVE inbound open on 0.0.0.0

Investigated whether `inet_interfaces` could drop to `loopback-only`.
It cannot without a follow-up:

- `mydestination` still contains `arc-codex.com`, and
  `/etc/postfix/virtual` forwards eight aliases (`hap@`, `info@`,
  `hello@`, `press@`, `legal@`, `edu@`, `support@`, `abuse@`) to
  `ross@arc-codex.com` via local delivery.
- The MX for `arc-codex.com` currently points at this host, so external
  senders reach these aliases only via inbound port 25.

If the mail-alias forwarding is intentional (support/abuse/legal are
real inboxes), leave port 25 open. If those aliases are decorative and
Ross's real mail lives on Gmail with no expectation of receiving mail
here, switch `inet_interfaces = loopback-only` and update DNS to point
the MX elsewhere (or drop MX).

**Left as-is for now.** Local processes still submit outbound via
`smtplib.SMTP("localhost", 25)` — `arc/mailer.py`, `hnt/mailer.py`,
`arc/auth.py` password-reset — which continues to work either way
(outbound uses `smtp_*` config, not `smtpd_*`).

### Verification

- `systemctl is-active cecil` → `inactive`
- `systemctl is-enabled cecil` → `disabled`
- `postfix check` → clean
- `systemctl reload postfix` → OK
- Attempting `MAIL FROM: rossnesbitt@gmail.com; RCPT TO: cecil@arc-codex.com`
  now returns `550 relay not permitted` (recipient no longer accepted).
- Local mailer.py outbound path unchanged — 7am digest cron and password
  reset emails still work.



## 2026-07-08 — Redis OOM incident remediation

**Incident**: Redis (shared instance, DB 0 = arc) was OOM-killed 18× between
00:30–01:07 on 2026-07-07. Root cause: no `maxmemory` (=0) with `noeviction`
on a 30.6 GB box with no swap; dataset had grown to ~14.6 GB RSS, ~90% of it
the `library:work:*:text` corpus (29,238 blobs totalling 12.7 GB).

### Redis memory cap (applied 2026-07-08)

```
CONFIG SET maxmemory 17179869184     # 16 GB
CONFIG REWRITE                        # persisted to /etc/redis/redis.conf
```

- Policy stays `noeviction` — deliberate. Arc's dataset is canonical (no
  cache semantics); evicting article hashes silently would be worse than
  failing writes loudly.
- Persistence verified via `CONFIG REWRITE` returning OK (redis 8.0.5 writes
  its own config file as the redis user; the file is not readable by `ross`,
  so verification is the REWRITE return status, not a grep).
- The 16 GB cap is sized for the pre-purge dataset. After the library corpus
  moves to SQLite (same day, see below), steady-state `used_memory` is
  expected around 1.5–2 GB, leaving the cap as a generous backstop.

### Swap (6 GB) — REQUIRES ROOT, run manually

`ross` has no passwordless sudo for these; run as root:

```bash
sudo fallocate -l 6G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
```

Verify: `free -h` shows 6 GB swap; `grep swapfile /etc/fstab`;
`cat /etc/sysctl.d/99-swappiness.conf`.

Status: **PENDING** — commands prepared 2026-07-08, awaiting a root shell.
(vm.swappiness was 60 at time of writing.)

### Library corpus relocation (Step 3 of same remediation)

`library:work:*` moved from Redis to SQLite at `/mnt/arcdata/library.db`
(cold-archive data, weekly cron, read-mostly — belongs on the archive SSD).
Pre-purge RDB backup: `/mnt/arcdata/redis-pre-library-purge-2026-07-08.rdb`.
See git history of `backend/library_fetcher.py` / `backend/score_library.py`.

## Archive registry — `/mnt/arcdata/`

Long-term RDB snapshots kept alongside the working corpus. Each entry lists
the window the snapshot represents and its md5 for tamper detection.

| File | Window covered | md5 | Notes |
|------|----------------|-----|-------|
| `redis-full-archive-2026-03-to-07.rdb` | 2026-03 → 2026-07-08 (pre-library-purge) | `2caa3966656474c50e8c3302c972781f` | Promoted 2026-07-08 from `redis-pre-library-purge-2026-07-08.rdb` — identical bytes, renamed to reflect the window it actually represents. Both files coexist; the promoted name is the durable reference. |
| `redis-pre-library-purge-2026-07-08.rdb` | 2026-03 → 2026-07-08 (pre-library-purge) | `2caa3966656474c50e8c3302c972781f` | Source snapshot from the OOM remediation above. Retained as a byte-identical twin so historical references keep resolving. |

Verify integrity after any host restore: `md5sum /mnt/arcdata/*.rdb` and
compare against the table.

## 2026-07-09 — Stored-XSS via ingested article HTML (arc)

**Incident**: arc-codex.com root began redirecting every visitor to
`/%3Ca%20href=` at approximately 00:04–00:37 UTC on 2026-07-09. Cause was
a `<meta http-equiv="refresh" content="1;url=<a href=…">` inside the
`original_text` of one RSS-ingested article, rendered unescaped by the
`plainTextToHtml` branch of `IntelligenceCard.tsx`. Because IntelligenceCard
uses `dangerouslySetInnerHTML`, the meta tag reached the DOM live and the
browser followed it, producing the malformed Location.

**Poisoned article** (removed 2026-07-09 during recovery):
- `article:ff75cdbb1acdf0bf8cf8ac7287e9e7cc`
- title: "What is the best security awareness payload for the Rubber Ducky"
- source: shop.hak5.org
- ingested: 2026-07-09T00:04:41 UTC
- also carried a raw `<script>window.location.href = "…"</script>`.

Removed from `feed` (ZSET), `article:*` HASH, `processed_hashes` SET, and
Solr (committed). Recoverable if ever needed from
`/mnt/arcdata/redis-full-archive-2026-03-to-07.rdb`.

### Fix layers (all landed 2026-07-09)

| Layer | Where | Commit (arc / hnt) |
|------|-------|---------------------|
| Immediate data recovery | Remove poisoned article from Redis + Solr | `11a5cb8` / — |
| Render-time escape — plainTextToHtml | `frontend/components/IntelligenceCard.tsx` — escape each line before linkify, mirroring the pattern `markdownToHtml` already used via `inlineFormat` | `7cb2eca` / (in `aaf8340`) |
| Render-time escape — sibling sweep | `CommentSection.tsx` (user-supplied comment bodies) and `IntelligenceCard.tsx` VideoList (non-'Video:' lines from `original_text`); `escapeHtml` exported from `lib/textUtils.ts` | `015ae85` / (in `aaf8340`) |
| Render-time escape — search snippet | Backend `main.py` `/api/search`: Solr `hl.simple.pre/post` emits Unicode sentinels `⟪HL⟫` / `⟪/HL⟫` (U+27EA/U+27EB). Frontend `app/search/page.tsx` `renderSnippet` runs `escapeHtml` FIRST, then restores the sentinels to `<mark>` markup. Sentinel constants live at the top of the frontend file; comments on both sides note the coupling. | `a310753` / (in `aaf8340`) |
| Render-time escape — JSON-LD (hnt-only) | `frontend/app/article/[slug]/page.tsx`: `JSON.stringify(jsonLd)` post-processed to escape `</script>` → `<\/script>` inside `<script type="application/ld+json">`. Arc article page emits no JSON-LD, so no arc counterpart. | — / (in `aaf8340`) |
| Ingest-side sanitizer | `backend/fetch_utils.py`: new `sanitize_active_content(text)` (bleach.clean allowlist). Called at every writer of `article['original_text']` — `scribe.py`, `manual_publisher.py`, arc `main.py` video-submit path. Strips active-content tags (script/meta/iframe/object/embed/style/form and their attrs), on\*= handlers, javascript: URLs. Preserves benign inline HTML (a/em/strong/p/br/code/…). | `b349117` / `14fe5ec` |

### Sibling-render classification table (arc frontend sweep)

Every `dangerouslySetInnerHTML` site was catalogued during Step 3. Fixed
(b), reported and fixed (c), left alone (a):

| Site | Class | Input | Outcome |
|------|-------|-------|---------|
| `app/not-found.tsx:20` | (a) | literal HTML-comment string constant | none |
| `app/not-found.tsx:23` | (a) | `JSON.stringify(jsonLd)` — static object at module scope | none |
| `app/search/page.tsx:139` | (c) | Solr highlighter snippet w/ intentional `<mark>` tags | sentinel roundtrip |
| `components/CommentSection.tsx:321` | (b) | `linkifyText(comment.text)` (user-posted content) | escape-before-linkify |
| `components/IntelligenceCard.tsx:271, :300` | (a) | `fullHtml` (via plainTextToHtml/markdownToHtml, both now escape) | fixed transitively |
| `components/IntelligenceCard.tsx:338` (VideoList) | (b) | `linkifyText(line)` from `original_text` | escape-before-linkify |

### Injected-test verification

Synthetic article `ARC_XSS_TEST_ONLY_2026_07_09` — `original_text`
carrying `<script>window.location.href=…</script>` +
`<meta http-equiv="refresh" content="0;url=/x">` +
`<img src=x onerror="alert(1)">`. Added to Redis feed + Solr, fetched
homepage, article page, and `/api/search` snippet. Result: 0 live
dangerous markup on any surface, all payloads escaped as text, `<mark>`
still styling matched terms on search. Test article removed post-verify.
Same test done on huntaegis (marker `HNT_XSS_TEST_ONLY_2026_07_09`) —
during that verification a NEW gap surfaced (JSON-LD `</script>` escape)
and was fixed in the same commit before cleanup.

### Corpus scan (post-fix, both stacks)

Ran regex sweep for active-content patterns across every `article:*.
original_text` in each feed. Arc: 1655 articles, 0 real hits (2 false
positives from English/YAML text — "For JavaScript:" and a YAML block
key `javascript: |`). Huntaegis: 1203 articles, 0 real hits (1 false
positive from Samba config text, 1 shared js: URL false positive). No
further poisoned articles present. Ingest sanitizer now guards all
future writes on both stacks.

### Dependencies added

`bleach>=6.4` in `backend/venv` on both stacks (used by
`sanitize_active_content`).

## 2026-07-10 — Perf Sprint 1: Caddy encode + hero cache-control (arc)

**Motivation**: mobile first-load recon showed `/api/get_feed` shipping
486 KB uncompressed (no `content-encoding` header on prod) and hero
JPEGs served without `Cache-Control` — so every cold visit re-downloads
the full 3.9 MB batch of hero images. Two arc-codex.com site-block edits
addressed both.

### Actions taken

- Added `encode zstd gzip` at the top of the `arc-codex.com` site block
  in `/etc/caddy/Caddyfile` — compresses all responses from that vhost,
  including the SSR HTML from Next.js and JSON from Flask.
- Added a specific `handle /uploads/scraped/*` block (before the general
  `/uploads/*`) that sets
  `Cache-Control: public, max-age=31536000, immutable` and serves from
  the same `/home/www/arc_stack/frontend/public` root. Scraped hero
  filenames are content-hashed so the immutable directive is safe.
- Pre-edit backup: `/home/www/arc_stack/Caddyfile.bak-perf-sprint-1-pre`
  (gitignored per `*.bak*`).
- `caddy adapt --validate` succeeded (the log-file permission-denied at
  the end is the known non-root quirk from the 2026-07-02 runbook, not a
  config error — the adapted JSON contains both new handlers).

### Diff (arc-codex.com block, two hunks)

```
@@ -39,6 +39,7 @@
 		format json
 	}
 
+	encode zstd gzip
 
 	handle /sitemap.xml {

@@ -84,6 +85,11 @@
 	handle /api/submit_comment {
 		reverse_proxy localhost:3000
 	}
+	handle /uploads/scraped/* {
+		root * /home/www/arc_stack/frontend/public
+		header Cache-Control "public, max-age=31536000, immutable"
+		file_server
+	}
 	handle /uploads/* {
```

### Huntaegis parity

Not applied. Huntaegis has its own site block with the identical
pre-edit shape; it does NOT inherit the encode directive from arc
(Caddy site blocks are separate scopes). Same two edits to the
`huntaegis.com` block would give it parity — deferred as a follow-up so
Sprint 1 stays scoped to arc-codex.com and can be verified in isolation.

### Soc / hapenews.mine.nu

Both serve `/uploads/*` from `/home/www/arc_stack/frontend/public` but
neither got the immutable cache-control block, since neither routes
through `/uploads/scraped/*` in a way that matters for the arc feed
first-load — they can pick up the same edit in a follow-up if wanted.

### Reload procedure (not yet run at commit time)

Per the 2026-07-02 huntaegis-repoint runbook:
`caddy reload --config /etc/caddy/Caddyfile` (admin API, atomic, keeps
old config on failure). Post-reload spot-checks: `curl -I` on
`https://arc-codex.com/api/get_feed` for `content-encoding`; `curl -I`
on any `/uploads/scraped/*.jpg` for `Cache-Control`; then verify
`huntaegis.com` and one unrelated site (e.g. `plantorium.arc-codex.com`)
still return 200 as sanity checks that the site-block edit didn't break
Caddy's routing table.

### Go-live 2026-07-10 20:01 UTC

- `caddy reload --config /etc/caddy/Caddyfile` — exit 0, only the
  cosmetic "input is not formatted" warning (unchanged pre-existing
  state, not introduced by this edit).
- `curl -sI -H "Accept-Encoding: gzip, zstd" https://arc-codex.com/api/get_feed`
  showed no `content-encoding` (HEAD requests carry no body, so Caddy's
  encode handler correctly omits it). Re-run with GET:
  `content-encoding: gzip` on `Accept-Encoding: gzip` (187 KB body vs
  ~486 KB uncompressed = 2.6× reduction); `content-encoding: zstd` on
  `Accept-Encoding: zstd` (182 KB body). Both variants live.
- `curl -sI https://arc-codex.com/uploads/scraped/fbac4b7fa430b236ff808a6098f57602.jpg`
  → `cache-control: public, max-age=31536000, immutable`.
- `curl -sI https://huntaegis.com/` → HTTP/2 200. `soc.arc-codex.com` →
  HTTP/2 200. Neighbor site blocks unaffected.
- Frontend redeploy via `./arc.sh build` — Docker image
  `arc-codex-frontend:latest` rebuilt from HEAD (commit `ca94f9c`),
  container `arc-frontend` recreated and healthy.
- `curl -s https://arc-codex.com/` returned **1** article in the SSR
  HTML (was ~33 pre-Sprint-1). Hero `<img>` carries
  `width="1200" height="675" decoding="async" loading="eager"
  fetchPriority="high"`. First-batch SSR HTML dropped to ~49 KB.

Browser scroll seam (1 → 1 → 2 → 4 …) still needs a real browser —
Ross's iPhone 11 test outstanding.

## 2026-07-10 — Perf Sprint 2: WebP hero variants (arc)

**Motivation**: Sprint 1 recon showed 33 first-batch heroes at 1200x675
JPEG = 3.9 MB eager on iPhone 11 cellular. Sprint 2 ships responsive
variants (WebP at 480/800/1200 widths) via a one-time backfill of the
existing corpus plus a pipeline hook so new heroes get variants at
ingest. Render side upgraded from plain `<img>` to `<picture>` with a
WebP `<source>` for scraped heroes; non-scraped heroes stay on the
plain img path.

`SCRAPED_IMAGE_DIR` verified: `scribe.py` resolves it to
`/home/www/arc_stack/frontend/public/uploads/scraped`, matching the
backfill script's default. Same directory, no divergence.

### Backfill run — 2026-07-10 20:19:49 → 20:37:38 UTC (~17m 49s)

- 3,588 JPGs planned (from dry-run); 3,591 processed (scraper added 3
  during the run — glob taken at script start missed those + any
  arrivals during the final ~4-minute window before scribe restart).
- 10,773 variants written (3,591 × 3, zero encode failures).
- 420.4 MB actually written vs 331 MB projection (+26.7%) — sample
  extrapolation ran light. Still trivial vs the 69.5 GB free headroom.
- Compression spot-check on one 36,961-byte JPG:
  - -480.webp = 5,886 B (15.9% of original)
  - -800.webp = 9,572 B (25.8%)
  - -1200.webp = 14,048 B (38.0%)
  Substantial mobile savings for the 480/800 tiers browsers actually
  pick on phone-sized viewports.

### Transition-window orphans + close (20:39-20:41 UTC)

Deploy sequence per the sprint brief: backfill → arc.sh build → arc.sh
restart scribe → verify. Between backfill-end (20:37:38) and scribe
restart (~20:41), old scribe was still running without Part C and
rehosted 5 new heroes without variants. First post-deploy spot-check
happened to pick one of them — the SSR-first card's WebP URLs 404'd,
creating a live regression for modern browsers (~1-2 minute window).

Ran `make_image_variants.py --execute` a second time (idempotent —
skipped 3,591, generated variants for the 5 orphans in ~2 seconds,
+771 KB written). Post-fix orphan count = 0. SSR-first hero's
`-800.webp` URL now returns 200 with `content-type: image/webp` and
`Cache-Control: public, max-age=31536000, immutable`. Regression cleared.

Lesson for future runs: restart scribe BEFORE the backfill (so Part C
covers arrivals during the backfill window), or run the backfill twice
by design.

### Frontend deploy (Part B commit 71f6c26)

`./arc.sh build` — Docker image `arc-codex-frontend:latest` rebuilt,
container `arc-frontend` recreated and healthy. SSR HTML now emits
`<picture>` with three-candidate WebP srcset for scraped-hero URLs
(sizes="(min-width: 640px) 600px, 350px") with the original JPEG as the
`<img>` child carrying all Sprint 1 attrs intact (width/height,
decoding, loading, fetchPriority).

Non-scraped heroes (external hotlinks, `/uploads/arc-codex-default.jpg`
etc.) render as the plain `<img>` — verified via
`https://arc-codex.com/article/72300debccb379efed32a9b321b5950d` which
has `<picture>` count 0 and the expected `<img>` with Sprint 1 attrs.

### Scribe deploy (Part C commit 5966ad5)

`./arc.sh restart scribe` — pid 4521 → 133201. Part C now generates the
three WebP variants after every JPEG save in `rehost_article_image`,
non-fatal on any variant failure.

Working-tree note: Ross's in-progress tuning of `SOURCE_BATCH_SIZE`
(20 → 69) and `MAX_CONCURRENT_ANALYZERS` (1 → 2) rode along with this
restart intentionally, and stays uncommitted per direction.

### Verification owed

- Real-browser check that iPhone 11 selects the -800.webp candidate at
  ~390 CSS px viewport. Ross's device test.
- One full scribe cycle (13 min) to confirm a new-article ingest end-
  to-end generates all three variants via Part C.
- Huntaegis parity (Sprint 1 Caddy edits AND Sprint 2 WebP pipeline) —
  still deferred as follow-ups.

## 2026-07-11 — Housekeeping: nightly git-push cron (both stacks)

`ops/nightly-git-push.sh` runs at **02:30 daily** (clear of the 03:00
arc / 04:00 hunt backup windows) and does `git push origin main` on
arc_stack then huntaegis_stack. **Push only** — the script never runs
add/commit/pull/rebase; a failed push is logged and skipped, no
retries, no prompts (`GIT_TERMINAL_PROMPT=0`). It is a safety net for
landed-but-unpushed commits, not an auto-committer.

- Script: `/home/www/arc_stack/ops/nightly-git-push.sh`
- Script log: `/home/www/arc_stack/logs/nightly_push.log`
- Cron-level log: `/home/www/arc_stack/logs/nightly_push_cron.log`
- Crontab: `30 2 * * * /home/www/arc_stack/ops/nightly-git-push.sh >> …/nightly_push_cron.log 2>&1`

Same sprint also purged 14 dead backup files (archived to
`/mnt/arcdata/arc-dead-backup-files-2026-07-10.tar.gz` before
deletion) and gitignored `backend/library.db` (arc) and
`frontend/tsconfig.tsbuildinfo` (hunt).

## 2026-07-10 — Polish Sprint 5: icon-row tooltips deployed (arc)

Commit `976d299` — CSS-only `[data-tooltip]` pattern in `globals.css`
(scoped to `@media (hover: hover)` so touch skips it), plus 8 verbatim
tooltip strings on the IntelligenceCard icon row (translate, permalink,
copy, research, share, torch, quiz me, print). Copy approved by Ross
as-is with no amendments. Deployed via `./arc.sh build` post-approval.
Post-deploy verification: SSR HTML shows all 8 `data-tooltip` attrs;
served stylesheet contains `[data-tooltip]`, `.tooltip-right`,
`.tooltip-left` rules under the hover-hover media query.

## 2026-07-11 — Watchdog hold-off for targeted restarts (both stacks)

`./arc.sh restart <service>` has a ~2s stop→start gap; if the
watchdog's 60s check landed inside it, it spawned an untracked
duplicate (hit on Hunt's scribe during the 2026-07-11 parity deploy —
two scribes ran for ~30 min until noticed and killed).

Fix, mirrored on both stacks: `cmd_restart`'s targeted branch touches
`pids/watchdog.hold` before stopping and removes it after starting;
the watchdog main loop skips a pass while the file is fresher than
120s and deletes stale ones (so a crashed restart can never disable
the watchdog permanently). Full-stack restart needs no hold — it
stops the watchdog itself.

Verified: watchdog restarts on both stacks picked up the new loop,
`huntaegis.sh restart scribe` produced exactly one scribe with the
hold file created and cleaned.

## 2026-07-11 — C2: weekly cleanup crons dead since early May (both stacks)

Health-audit finding C2. Both Sunday cleanup.py crons pointed at
`<stack>/venv/bin/python3`, which does not exist (venvs live under
`backend/`). Last successful runs: arc 2026-05-05, hunt 2026-05-01 —
~9 Sundays of `/bin/sh: not found` in each cleanup.log.

Backlog on restore (read-only count before touching anything):
arc — 0 orphan article keys, 19 stale processed_hashes, Solr 1101 vs
feed 1102; hunt — 0 orphans, 1 stale hash, Solr 1128 vs feed 1127.
Trivial — the 2026-07-08/09 OOM and XSS manual cleanups absorbed most
drift. No catch-up run needed; Sunday's cron takes it.

Fix: crontab repointed at `<stack>/backend/venv/bin/python3` (both
lines); interpreters verified present; both cleanup.py pass
py_compile under their venv. No live prune executed.

## 2026-07-11 — Health audit wave 2: Q1-Q4 hygiene (both stacks)

Arc commit `5922b62`, hunt commit `14a30a9`. Per-item:

- **Q1** get_feed limit clamped [1,50], offset floored (both stacks).
  Verified live: limit=99999 → 50, limit=-1 → 1, limit=1 → 1; SSR
  first paint unaffected on both domains.
- **Q2** upload_image throttled (pre_analyze semaphore pattern, 2
  concurrent, 429 on saturation; both stacks). Caller trace: publish
  page calls it client-side, so Caddy's header-strip boundary leaves
  no auth context to check — **auth gap deliberately deferred**, noted
  in both endpoints' comments. A proper gate needs a Next.js proxy
  route + Caddy reroute (architecture change, future decision).
- **Q4** publish_article rejection logs now record secret-header
  presence/absence, not the value (both stacks; arc line 454 was the
  original audit finding, hunt:423 was wave-1 flag 2).
- **cleanup.py docstring** corrected to backend/venv path (arc).
  Correction 2026-07-11: this entry originally claimed hunt's docstring
  lacked the stale path — wrong, it had it too; fixed in wave 3.
- **frontend/.env.local** (arc, untracked): removed REDIS_HOST,
  REDIS_PASSWORD, REDIS_PORT, SOLR_URL — no frontend code reads them.
  Container rebuilt healthy after removal.

Services bounced: arc gunicorn ×2 (guard, then env-adjacent rebuild),
arc frontend container, hunt gunicorn. All verified serving.

## 2026-07-11 — Register Wave A: cold backup fixed, restore drill passed

### R4 forensics — the cold backup had NEVER worked

- `COLD_BACKUP_DIR` pointed at `/mnt/data/www/arc_stack_prod`. The
  `/mnt/data` drive died or was removed (fstab entry with `nofail`
  remains; mountpoint is now a bare root-owned dir with Mar-5 skeleton
  dirs). `mkdir -p` failed silently on every arc.sh invocation; any
  manual run would have errored loudly at tar. Zero `arc_cold_*.tar.gz`
  exist anywhere on the box; `.bash_history` shows zero backup-cold
  invocations; cron never scheduled it (hunt's cold cron exists, arc's
  never did). Conclusion: never ran post-HDD-failure, likely never ran
  at all.
- Compounding: the script's `REDIS_PASSWORD` extraction
  (`grep REDIS_URL | grep -oP "(?<=:)[^@]+"`) matched the `//` of the
  URL scheme, not the password — so even the old BGSAVE call had been
  failing silently (WRONGPASS, stderr to /dev/null) wherever it ran.
  Fixed: arc.sh now reads the `REDIS_PASSWORD=` line from backend/.env
  directly. This extraction is now load-bearing for the RDB capture.
- CLAUDE.md's "includes Redis RDB + Solr" described an aspiration —
  the old tar never contained either. Doc corrected.

### R4 fix — what backup-cold now captures

Destination `/mnt/arcdata/backups/` (dedicated subdir — automated
retention never shares a namespace with the manual must-never-delete
artifacts loose in /mnt/arcdata). `KEEP=4`; math: each archive ≈ 6.1 GB
actual (stack ~5 GB dominated by uploads + library.db 13.7 GB → ~1 GB
inside the shared gzip stream + RDB 176 MB + Solr 26 MB) → ~25 GB
steady-state of the mount's ~197 GB free.

- `data_layer/redis-arc.rdb` — `redis-cli --rdb` (consistent
  point-in-time stream over the socket; /var/lib/redis is root-only and
  --rdb can never capture a mid-write file — replaces the brief's
  BGSAVE-poll-then-cp, which is permission-impossible for ross).
  Captures ALL Redis DBs (arc 0, hunt 1, unknown 2, auth 5).
- `data_layer/solr-snapshot/` — replication-handler backup staged under
  SOLR_HOME (solr.allowPaths restriction), then moved. Consistent
  committed-segment snapshot; raw index-dir copy can race merges.
- `data_layer/library.db` — `sqlite3 .backup` (online-consistent; the
  db is live-modified, raw cp is the same corruption class as a
  mid-write RDB).
- backend/.env still rides in the stack tar — known R9 issue, left for
  the encrypted-store fix; deliberately not half-solved here.
- R9 addendum (2026-07-16): backend/.env line 59 (ARC_ADMIN_PASSWORD)
  holds an unquoted value containing whitespace — `source`-ing the file
  truncates the value and tries to execute the second token
  (`after_HUMANS: command not found`), while python-dotenv parses the
  full line. Any shell that sources .env sees a DIFFERENT password than
  the Flask app does. Fold quoting/normalization into the R9
  encrypted-store fix.
- First real archive: `arc_cold_2026-07-11_0724.tar.gz`, 6.1 GB,
  14m 59s wall.

### R3 — restore drill (first ever), 2026-07-11 13:40:55–13:44:59 UTC

Wall time **4m 04s** end to end. Target
`/home/ross/restore-drill-2026-07-11/` — scratch only; no production
path was written, no service touched, prod Redis/Solr/stack untouched.

- Stack: untarred 15 GB; arc.sh passes `bash -n`, main.py header
  correct, IntelligenceCard.tsx present.
- Redis: RDB loaded into a throwaway `redis-server --port 6380` (dir =
  scratch, save disabled). DBSIZE: db0 46,697 / db1 15,842 / db2 233 /
  db5 3. Three newest articles spot-checked: title, timestamp,
  directive, original_text all populated (`purple_team_analysis` empty
  on all three — correct, analysis is lazy and they were minutes old at
  capture). Drill feed ZCARD 1,125 vs prod 1,126 at check time —
  exactly the one article ingested since capture. `SHUTDOWN NOSAVE`;
  port 6380 verified free after.
- Solr: 185 segment files, 26 MB, zero zero-byte files, 11 .si.
- library.db: `PRAGMA integrity_check` = ok; 5 tables; works = 29,238
  (matches the OOM-remediation era count).

**What the drill did NOT prove**: loading the Solr snapshot into a live
core (file-level verification only); full-system bootstrap from bare
metal (venv/node_modules/host config are excluded by design and
documented in this runbook instead); restoring the RDB into a
production Redis.

**Drill environment prerequisite**: restore drills need ~20+ GB of
DISK-BACKED scratch. `/tmp` is tmpfs (16 GB RAM) on this box and must
never be the extraction target. `/home/ross/…` on the root disk works.

**Recurrence**: quarterly. Next drill due ~2026-10-11. The drill
procedure is exactly this entry, top to bottom.

### cmd_restore hardwiring — new register finding

`arc.sh restore` is interactive-only and hardwired to production: it
stops the stack and untars over `$ITC_ROOT` with no scratch-target
option. Fine as the break-glass path, but drills must not use it —
this drill was performed manually for that reason. Register: add a
`--target <dir>` option (LOW, hours).

### Missing cold-backup cron — scheduled 2026-07-11

Hunt has a weekly cold cron; arc had none (part of why R4 went
unnoticed for months). Installed to Ross's crontab:

```
0 4 * * 0   /home/www/arc_stack/arc.sh backup-cold              >> /home/www/arc_stack/logs/backup_cron.log 2>&1
```

Sunday 04:00 UTC — one hour after Sunday cleanup jobs (arc 01:00,
hunt 02:00) and hunt's cold backup (03:00), immediately alongside
hunt's daily backup (04:00). Different filesystems, no target
collision.

First scheduled run: **2026-07-12 (Sunday) 04:00**.

Retention math (verified against actual): archive is 6.1 GB gzipped
(Wave A first drill), KEEP=4 → **~24.4 GB steady-state** on
`/mnt/arcdata`. Peak in-flight during a run is larger (~44 GB
including the ~14 GB staging area for library.db before it streams
into gzip, plus the four existing archives). `/mnt/arcdata` has
191 GB free — plenty of headroom.

## 2026-07-11 — api_other Wave B: /api/library/ swarm gated, exporter fixed

### Bucket definition and offender

The `api_other` catch-all in `caddy_exporter.py` PATH_GROUPS was hiding
one endpoint: `/api/library/<id>?lang=<non-en>`. Alibaba Cloud US
IP ranges (47.79.x / 47.82.x, many /24s) hit that path with a
fake-Chrome UA that slipped `_is_bot_ua`, commissioning a 120s M1
translation the scraper never waited to receive. Over ~2.5 days of
logs: 974 requests, 716 slow (>5s), 94.7% status=0 (client aborted
at ~10s of its own timeout). The 10s round number was the SCRAPER'S
client timeout, not ours — our end continued the Ollama call and
cached the translation. Real users unaffected in aggregate; M1 cost
was pure waste.

### R-A — behavioral gate (main.py)

Extended the existing `_is_bot_ua` check on the commission branch to
also trigger the bot-path when NONE of `Sec-Fetch-Site`,
`Sec-Fetch-Mode`, `Sec-Fetch-Dest` are present. W3C Fetch Metadata
headers are set automatically by every real browser fetch/navigation
and are not sent by bare HTTP clients (curl, python-requests, the
Alibaba swarm). Choice reasoning: cheapest reliable discriminator on
the wire at this endpoint; IP/ASN lists would rot as the next swarm
comes from somewhere else. Cache hits remain ungated (public data,
cheap to serve). Response for gated requests is the existing bot-path
`translation_error`, not a 403 — no scraper gets a signal to adapt.
When the gate fires, `arc:stats:library_translation_gated` is INCR'd
and an INFO log line "library translation gated: id=... lang=...
reason=bot_ua|no_sec_fetch" is emitted.

Verified end-to-end after gunicorn restart:
- Scraper curl `?lang=fr`, no Sec-Fetch-*, fake-Chrome UA →
  response 0.010s, gate log emitted, counter=1, no Ollama call.
- Browser-shaped curl `?lang=pt-br` (Sec-Fetch-*, Referer) →
  passed the gate, reached `_call_translation_model` (return time
  120s = Ollama's own timeout; orthogonal, not a regression).
- Scraper curl on cached (30419, es) → 0.005s, is_translated=true,
  Spanish text served. Cache path ungated as designed.

### R-C — gunicorn %(L)s response-time logging (gunicorn_arc.sh)

`--access-logformat` added with `%(L)s` appended as the last field.
Verified after restart: `... "curl/8.18.0" 0.002410`. Closes half of
the R6 observability gap the api_other recon surfaced; per-endpoint
Flask timing now exists at the launcher log, not just aggregated in
Caddy.

### R-D — caddy_exporter PATH_GROUPS surgery

- Added `(r'^/api/library/', 'api_library')` above the api_other
  catch-all. New Grafana bucket carries the swarm signal into its own
  series.
- Fixed the dead `api_articles` regex: was `^/api/articles` (plural,
  no route matches); repointed to `^/api/article/` (singular, matches
  the real endpoint `/api/article/<id>` + `/comments`).

**Grafana discontinuity warning**: at this commit `api_other` shrinks
sharply (~30% of its historical volume moves to `api_library`), and
`api_articles` begins collecting real data for the first time (~65% of
former `api_other` moves there). Any dashboards or alerts that queried
`api_other` as a proxy for "everything under /api/*" will report an
apparent step-drop starting 2026-07-11 — that is the bucket splitting,
not a traffic change. Verified in a scrape after exporter restart:
both new labels present.

Restart procedure used: `arc.sh restart caddy_exporter` and
`arc.sh restart gunicorn`. Both service-name entries in
`VALID_SERVICES` — no separate systemd unit involved.

### Registered (not fixed) this wave

- **R-B**: widen `_BOT_UA_MARKERS`. The Sec-Fetch-* gate makes this
  lower priority — a swarm rotating UA would still be caught.
- **R-E**: `/api/library/<id>` sets `Cache-Control: public,
  max-age=3600` unconditionally, including on error and
  translation-error paths (`main.py:2262`). Edge caches could serve
  stale errors for an hour. Separate change; not a latency story.
- **Hunt exposure**: none. Hunt has no `/api/library/*` route in
  backend or frontend. No port needed.

## 2026-07-11 — Register Wave B-proper: machine verification (R2, R1, R8)

The diligence paragraph's central claim was "nothing is machine-verified."
This wave answers that on three axes: CI, tests, dep audits. Not
comprehensive — a floor to build on.

### R2 — GitHub Actions verify.yml, both stacks

`.github/workflows/verify.yml` on both `arc_stack` and `huntaegis_stack`.
Runs on push to `main` and PRs targeting `main`. Verification only —
no deploy, no secrets required.

Jobs (both stacks):
- **frontend**: `npm ci` → `npm run build` (with placeholder
  `NEXT_PUBLIC_*` / `NEXTAUTH_URL` / `AUTH_SECRET`) → `npx tsc --noEmit`.
- **backend**: `pip install -r requirements.txt` → `py_compile` sweep
  of every `*.py` (`manual_test_*` explicitly excluded on Arc — see
  R1 note below). Chose `py_compile` over `ruff check` — zero config,
  no lint noise, no version drift. `ruff` can arrive later as its own
  register line if we want stylistic coverage.

Arc's backend job additionally runs the pytest smoke suite (R1). Hunt
has no suite yet; that's tracked as its own future register line and
NOT force-mirrored here.

**No branch protection today** — a failing run does not block a merge;
the redness is only visible on the commit and PR pages. Whether to add
required-checks + block on failure is a separate decision registered
for a later wave.

### R1 phase 1 — pytest smoke suite (Arc only)

- **Orphan integration scripts renamed**, not deleted: they test live
  code (escalation counters via prod Redis; ollama_client failover
  against the M1 with a 60s sleep for breaker recovery) and are still
  useful for manual QA — they just cannot run in a GH-Actions runner.
  Renamed `test_escalation_order.py` → `manual_test_escalation_order.py`
  and `test_ollama_client.py` → `manual_test_ollama_client.py` so
  pytest's default collection (`test_*.py`) naturally skips them,
  invocation-by-hand still works. Called out explicitly in the
  `py_compile` sweep exclusion so a future edit doesn't silently
  re-collect them.
- **New suite** at `backend/tests/test_smoke.py` (9 tests). Uses
  Flask's test client. Every test monkey-patches `main.r` and
  `main.library_db`; no live services touched. Runs in ~40 ms locally.
  Coverage of the money paths:
  - `/api/get_feed`: 503-on-no-Redis, empty-feed shape, `limit`
    clamped to 50 (uncapped-limit was the Wave B recon prompt),
    negative `offset` clamped to 0.
  - `/api/library/<id>?lang=…` (Wave B Sec-Fetch-* gate): scraper
    with no Sec-Fetch-* → bot-path message, browser-shaped headers
    → gate passes and commission fires (verified via spy on
    `_call_translation_model`), scraper-on-cache still served (cache
    ungated as designed).
  - `/api/post_bluesky`: 403 without `X-Scribe-Secret`, 403 with the
    wrong value (Wave A commit `1b4c32b`).
- **conftest.py note** (for future-us): `translation.py` reads
  `os.environ['REDIS_URL']` at module-import time and passes it to
  `redis.from_url` — an empty string ValueErrors on parse, so the
  conftest sets a valid-shape `REDIS_URL=redis://localhost:6379/15`
  even though nothing actually connects. Real fragility (import-time
  env dependency) but not a production bug — prod always has it set.
  Registered as R1-phase-2 candidate for lazy-init cleanup.
- **New file**: `backend/requirements-dev.txt` pins pytest / pytest-cov
  / pip-audit for reproducible CI + local runs.

### R8 — dependency hygiene

**npm audit fix** (non-breaking, no `--force`), both frontends:
- Arc: 11 → 2 vulns (before: 0 low / 1 mod / 4 mod / 6 high; after:
  0/0/1/1). Build re-verified green after fix.
- Hunt: 11 → 2 vulns (same tree, same result). Build re-verified.
- Remaining 2 in each (moderate + high) sit inside next's transitive
  `postcss`; only `--force` fixes them, which would jump Next past
  the stated dependency range. Not this wave. Registered.

**pip-audit** — findings ONLY, not fixed this wave (Flask-era pins
need their own care). Same tree on both stacks: **44 known vulns
across 11 packages**. Grouped:

| Package | CVEs | Fix path |
|---|---:|---|
| pypdf | 15 | 6.7.5 → 6.13.x |
| pip (itself) | 6 | 25.0.1 → 26.1.2 — low priority, often supply-chain-noise CVEs |
| nltk | 5 | 3.9.3 → 3.9.4 (some no fix listed yet) |
| yt-dlp | 4 | → 2026.6.9 |
| urllib3 | 3 | → 2.7.0 |
| soupsieve, lxml, idna | 2 each | patch bumps |
| requests, pygments, lxml-html-clean | 1 each | patch bumps |

Priority for a future R8-phase-2 upgrade wave: pypdf (broadest CVE
surface + document-parsing = attacker-controlled input in
`/api/submit_pdf`), then requests/urllib3 (network stack), then
nltk. pip-itself and yt-dlp are lower.

### Registered, not fixed

- **R8-phase-2**: Python dep upgrades, package by package with
  regression checks. Requires an upgrade wave of its own.
- **R2 branch protection**: require verify.yml green before merge.
- **R1 phase 2**: broaden smoke suite past three endpoints; also
  bring Hunt onto pytest; also fix `translation.py`'s import-time
  Redis parse.
- **npm audit tail**: 2 remaining vulns in each stack's postcss
  (Next transitive) — need `--force` + Next major bump to clear.

## 2026-07-11 — Register Wave C: hardening (R14, R15, R5, R6)

The wave that makes the system TELL US when things break. Ordered
smallest-blast-radius first: R14 → R15 → R5 → R6.

### R14 — Dead code deletions (Arc)

- `NEXT_PUBLIC_API_URL` build arg: removed from `Dockerfile.frontend`
  and `docker-compose.yml`. Zero refs in `frontend/`.
- 5 zero-importer components deleted: `ContentStats`, `ContentTabs`,
  `DeepAnalysisToggle`, `GradeButton`, `Section`. Re-verified against
  the current tree (grep for `from ['\"](\.\.?/)+components/X['\"]`
  and `@/components/X`) before deleting — zero importers today.
- CI verify.yml (R2) proved the deletion green:
  https://github.com/hapnesbitt/arc-codex/actions/runs/29172952129

### R15 — Log rotation

`/etc/logrotate.d/` needs sudo we don't have. Instead: user-owned
config at each stack's `ops/logrotate.conf`, invoked from ross's
crontab against a user-owned state file `logs/.logrotate.state`.
Cron entries (staggered 5 min to avoid IO overlap):

```
0 5 * * 0 /usr/sbin/logrotate -s /home/www/arc_stack/logs/.logrotate.state /home/www/arc_stack/ops/logrotate.conf >> /home/www/arc_stack/logs/logrotate.log 2>&1
5 5 * * 0 /usr/sbin/logrotate -s /home/www/huntaegis_stack/logs/.logrotate.state /home/www/huntaegis_stack/ops/logrotate.conf >> /home/www/huntaegis_stack/logs/logrotate.log 2>&1
```

Covers the three growing files on each stack: `gunicorn_access.log`,
`gunicorn_error.log`, `scribe.log`. `weekly`, `rotate 8`, `compress`
with `delaycompress`, `copytruncate`. `copytruncate` because
gunicorn/scribe keep their fd open — copytruncate copies then
truncates in place so writes continue without a SIGUSR1/restart hook.
Small tradeoff: writes during the copy→truncate window can be
duplicated or lost; acceptable for access/error logs.

**Not covered** (all present in top-10 but ruled out):
- Caddy access logs — Caddy rotates natively (roll_size 50mb,
  roll_keep 7) per its own vhost config.
- `score_library.log` / `library_fetcher.log` — one-off jobs, last
  written 2026-07-05/06, will not grow.
- Poster/analyzer/exporter logs (11-20 MB range) — register for
  R15-phase-2 if steady-state grows past that.

**Verified**: forced rotation on both stacks produced archived copies
(29M/39M/45M on arc; 39M/48M/55M on hunt), current files truncated to
~0 bytes, subsequent requests logged normally (gunicorn `%(L)s` field
still present). First scheduled rotation: 2026-07-12 (Sun) 05:00.

### R5 — Security headers (Caddy) + CSP report-only

**Subdomain HTTPS check before HSTS**: every arc-codex.com subdomain
serves valid TLS today (arc-codex, athena, beowulf, dlb, grafana,
holmes, mark, plantorium, pt, soc, vid — all 200/307 over HTTPS).
Hunt has no subdomains. Safe to enable `includeSubDomains`. NO
`preload` — that's a hard-to-undo commitment, registered separately.

**Headers added to both `arc-codex.com` and `huntaegis.com` vhosts**:

```
header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Referrer-Policy "strict-origin-when-cross-origin"
    Permissions-Policy "camera=(), microphone=(), geolocation=()"
    Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://lh3.googleusercontent.com https://avatars.githubusercontent.com https://media.licdn.com; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; report-uri /api/csp_report"
}
```

Reload procedure (memory-documented, no sudo):
`caddy adapt --validate --config /etc/caddy/Caddyfile` for syntax,
then `caddy reload --config /etc/caddy/Caddyfile`. Spot-checked arc
+ hunt + plantorium (unrelated site — no new headers, as expected).

**CSP finding — non-negotiable inline reliance**:
- Next.js SSR emits multiple `<script>` blocks per page holding
  hydration data (`self.__next_f.push([...])`), unique per request.
- Tailwind + component code emits inline `style="…"` attributes on
  many elements.
- A CSP without `'unsafe-inline'` (or nonces) would break every page.
- Kept `'unsafe-inline'` for `script-src` and `style-src` in the
  starting policy. Removing them cleanly is a **frontend refactor**
  (SSR nonce plumbing + Next `experimental.nonce`, style extraction)
  — registered as **R5-phase-2**, NOT started in this wave per the
  behavior guard.

**CSP report ingest**: new `/api/csp_report` endpoint on both
stacks. Log-only (no storage). Body cap 8 KB (real reports are well
under 2 KB; cap protects against log-fill attacks). Concurrency
bounded by `_csp_report_sem = Semaphore(2)`, 1 s timeout → 429 —
mirrors the `_pre_analyze_sem` / `_upload_image_sem` pattern.
Verified: valid report → 204 + INFO log line; 10 KB body → 413.
Field extraction handles both W3C and vendor-cased variants
(`blockedURL` / `effectiveDirective` / `documentURL`).

**Review 2026-07-18**: one week of live reports before deciding
whether to move any directive from report-only to enforce.

**Click-through observation**: cannot run a real browser from this
session; report-only means nothing user-facing broke (curl'd `/`,
`/library`, `/wiki`, `/about`, `/publish` — all 200). Ross to
click-through with devtools console open across the week.

### R6 — Alertmanager + 5 rules + one end-to-end test

**Delivery**: **webhook → `/api/alert`** on Flask, which logs a
line per alert to `gunicorn_error.log`. This is the "log-file
receiver stopgap" per the R6 spec. Registered as **R6-phase-2**:
email/Slack routing when the mailer path is trusted.

**Infrastructure changes** (all in `arc_stack` because Hunt shares
the Prometheus + node + Redis view):
- New `monitoring/rules/arc_alerts.yml` — 5 rules in 3 groups.
- New `monitoring/alertmanager.yml` — webhook receiver, grouped by
  `(alertname, severity)`, 30 s wait, 5 m group interval, 12 h
  repeat.
- `monitoring/prometheus.yml`: added `rule_files`, `alerting.alertmanagers`
  block, and CRITICAL fix — `evaluation_interval` was `60m` (matched
  the corpus-scrape interval, made every rule effectively silent).
  Split into per-job `scrape_interval` and a global
  `evaluation_interval: 30s`. Global scrape default is now 60 s;
  per-job overrides preserved (corpus 2m, traffic/node 15s).
- `docker-compose.grafana.yml`: added `alertmanager` service (host
  network, port 9093), volume `alertmanager_data`, rules dir
  bind-mount for prometheus, `depends_on: alertmanager`.
- New `arc_last_publish_timestamp` gauge in `corpus_exporter.py`:
  reads newest article timestamp from feed ZSET
  (`ZREVRANGE feed 0 0 WITHSCORES`), sets to 0 on empty feed
  (distinguishes "never published" from stale gauge).
- New `/api/alert` Flask endpoint: log-only, 64 KB cap (bigger than
  csp_report because batched AM payloads carry many alerts), same
  Semaphore(2) + 429 pattern.

**Bind-mount inode gotcha noted**: editing `monitoring/prometheus.yml`
via write-then-replace (which most editors do) creates a new inode;
the running Prometheus container's bind mount still points at the
old one. `docker compose up -d --force-recreate prometheus` picks
up the new inode. Documenting so we don't burn 20 minutes on this
again.

**Rules** (5, in `arc_alerts.yml`):

| Group | Alert | Expr | for | Severity |
|---|---|---|---|---|
| liveness | `ScrapeTargetDown` | `up == 0` | 5m | critical |
| pipeline | `ArcFeedStale` | `(time() - arc_last_publish_timestamp) > 10800` | 10m | warning |
| capacity | `DiskRootFullish` | `avail/size < 0.10` on `/` | 15m | warning |
| capacity | `DiskArcdataFullish` | `avail/size < 0.10` on `/mnt/arcdata` | 15m | warning |
| capacity | `RedisMemoryHigh` | `arc_redis_memory_ratio > 0.80` | 10m | warning |

**Cert expiry — not shipped**: neither `node_exporter` nor any
running exporter emits certificate-expiry timeseries; per the R6
spec, register rather than install a new exporter this wave.
**R6-phase-3**: add `blackbox_exporter` for cert probes.

**End-to-end test — `DiskRootFullish`**:
- Root currently 87% used (13% free). Temporarily raised threshold
  to `< 0.20` with `for: 30s`.
- Result: Prometheus `state=firing` (value=0.1307), Alertmanager
  active state, webhook fired, Flask log line landed:
  `alert firing: [warning] DiskRootFullish — Root filesystem below 10% free`.
- Threshold restored to `0.10` / `for: 15m`; active alerts cleared
  cleanly.
- **Current disk runway**: `/` 87% used (registered close to trigger
  — cleanup pass separately registered); `/mnt/arcdata` 58% used
  (plenty of runway even with the new weekly cold cron adding ~6 GB).

**Hunt coverage**: shares the box, so `up`, `node_filesystem_*`,
and box-level scrapes cover it already. Hunt has its own scribe but
no running corpus_exporter — its feed staleness metric doesn't
exist. Registered as **R6-phase-4**: run Hunt's corpus_exporter on
`:9103` and add `hunt_last_publish_timestamp` + mirror rules.

### Wave C followups registered (all NEW)

- **R5-phase-2**: strip `'unsafe-inline'` from CSP via Next.js SSR
  nonces + style extraction. Frontend refactor scope.
- **R5-phase-3**: HSTS `preload` opt-in (2-year max-age; SUBMIT to
  hstspreload.org). Do only when very confident.
- **R6-phase-2**: alert delivery via email / Slack when the mailer
  path is trusted.
- **R6-phase-3**: `blackbox_exporter` for cert expiry probes.
- **R6-phase-4**: Hunt corpus_exporter + feed-staleness rule.
- **R15-phase-2**: coverage for poster/analyzer/exporter logs if
  their steady-state grows past current ~10-20 MB range.
- **Disk cleanup for `/`**: register that root is at 87% used — no
  headroom for another 30 GB unpacking. Separate action.

## 2026-07-11 — Root disk reclaim (87% → 46%)

Triggered by Wave C R6's new `DiskRootFullish` alert threshold (fires
at 10% free = 90% used) landing next to a root already at 87%. Ran
Phase 1 diagnosis, categorized reclaim into A/B/C/D with a
recover-before-delete stance on anything ambiguous, then executed
the approved subset.

### The story of the missing 212 GB (du vs df)

`du -xh` on root reported 172 GB used; `df` showed 384 GB — a 212 GB
gap. Root cause: `docker system df` reports **build cache: 180.3 GB,
119.9 GB reclaimable**, all under root-only `/var/lib/docker/overlay2`
that `du` cannot traverse without sudo. Ten frontend rebuilds this
week across arc + hunt accumulated 812 build-cache entries, most of
them dead. This wave's very first reclaim (A1) removed all 180.3 GB,
of which 165 GB was on-disk overlay (the rest was virtual
layer-share double-counting).

### Reclaim results

| # | Item | Reclaimed | Notes |
|---|---|---:|---|
| A1 | `docker builder prune -af` | **~165 GB** (df delta of just this step) | Docker reported 180.3 GB total; overlay layer-share means on-disk delta was 165. Both stacks rebuilt clean afterward. |
| A2 | `apt-get clean` | **0** | needs sudo — skipped, insignificant vs. A1 |
| A3 | `journalctl --vacuum-size=500M` | **0** | needs sudo — skipped, ~3 GB left on the table |
| B1 | Explicit `docker image rm` on 4 unreferenced images (nextcloud:latest, owncloud/ocis:latest, lightbox-agent:dev, hello-world:latest) | ~2.7 GB (rolled into A1 delta measurement window) | Pre-checked `docker ps -a --filter ancestor=` per image → zero references before removing. Nextcloud data at `/home/ross/nextcloud_data` unaffected — data lives outside container. |
| B2 | `docker rm pt-test` (5-week-old exited Ubuntu container) | 87 MB | — |
| C1 | `rm -rf /home/ross/kernel_build` — May-24 build artifacts for kernels 6.18.30 + 7.0.10 | **13 GB** | Neither kernel is running; deletion satisfies recover-before-delete via reproducibility (`.deb`s can be rebuilt from tarballs; tarballs are re-downloadable from kernel.org). |
| C2 | `rm -rf /home/ross/src/linux-7.1.1` + `linux-7.1.1.tar` | **7.2 GB** | Same rationale — 7.1.1 not running; same reproducibility argument. |
| C5 | `pip cache purge` (both venvs) | **5.09 GB** | pip reports "1891 files removed" |

**Hard guard held**: kernel 7.1.3-z230 running from
`/home/ross/src/linux-7.1.3` — pre-check echoed the path, post-check
confirmed intact. `linux-7.1.1`, `linux-7.1.1.tar`, `kernel_build`
gone.

### Verification

- `df -h /`: **87% → 46% used, 62 GB → 242 GB free, Δ 180.6 GiB**.
  Target was <80%; landed at 46% with 41-point margin.
- `DiskRootFullish` in Prometheus: no active alerts. Free ratio
  0.516 (well above the 10% trigger). Threshold **unchanged** at
  0.10 — the runway is what moved, not the goalpost.
- Sunday's crons (cold backup 04:00, logrotate 05:00, D1 builder
  prune 05:30) have plenty of room to run.

### Cold-rebuild expectation (post-A1)

The next `docker compose build frontend` on either stack will be
**cache-cold** (~3-5 minutes vs. seconds warm). Verified once
today after A1:

- Arc frontend: **5m 04s** cache-cold, image built to
  `arc-codex-frontend:latest`, running container untouched.
- Hunt frontend: **3m 20s** cache-cold, image built to
  `huntaegis-frontend:latest`, running container untouched.

If a next-week deploy takes 3-5 min at the build step, that is
expected, not a hang. Subsequent same-day rebuilds return to
sub-30s once the D1 cache warms.

### Deferred (explicit — one line each)

- **B3** snap disabled revisions (~5 GB across 15 revs) — keep as
  rollback insurance.
- **C3** `/home/ross/videocam` 9.2 GB — personal, decision belongs
  to Ross on Ross's timeline.
- **C4** `/home/ross/E2938.mp4` 1.3 GB — same.
- **C6** duplicate Ollama CUDA libs (`/usr/lib/ollama/` vs.
  `/usr/local/lib/ollama/`) — too risky to guess which install is
  the real one; stays registered.
- **C7** Firefox snap `quicksuggest-amp.sql` 2.7 GB — trivial vs.
  the delta already achieved; skip.

### Growth policies now in force

- **D1** — weekly `docker builder prune -f --filter until=168h` in
  Ross's crontab (Sunday 05:30, after logrotate 05:00). `-f` but
  **not** `-a` with the `until` filter — keeps the last 7 days of
  cache warm so routine same-week deploys stay fast, prunes
  everything older. This prevents the exact regrowth that took
  180 GB last time.
- **D3** — `pip config set global.no-cache-dir true` — written to
  `~/.config/pip/pip.conf`. Verified via `pip config list`. Prevents
  regrowth at the source; one less cron to own.

### Register updates (all new)

- **D2** — journald `SystemMaxUse=500M` in
  `/etc/systemd/journald.conf`. Needs sudo. Currently 3.5 GB;
  stopgap is a user-run `journalctl --vacuum-size=500M` from a
  sudo-timed manual pass.
- **D4** — SSD backup growth watch (arc 445M → 1.2G in 5 days;
  hunt similar). KEEP=5 in `arc.sh` covers steady-state at
  ~2 GB/archive × 5 = 10 GB per stack; revisit if it climbs.
- **D5 — promoted to next-recon priority**: `arc-frontend`
  container has a **7.55 GB writable layer**. Frontends should
  be near-zero writable. Anything written inside overlay dies on
  every container recreate — so if something in there expects
  persistence, it has been silently losing data all week (with
  today's gunicorn/caddy_exporter/prometheus restarts and the
  builds above, some of those writes are already gone). Needs a
  `docker diff arc-frontend` recon before the next arc-frontend
  restart. Note: today's builds did NOT restart arc-frontend
  (build-only path), so whatever is in that layer is still
  present RIGHT NOW; timing-critical to look at before the next
  deploy.

## 2026-07-11 — D5 recon + fix: Next fetch cache pinned to arcdata

Follow-up to the reclaim, executed same day. D5 was the promoted
"next recon" line and it turned into a same-session fix once the
alarm case was ruled out.

### Root cause (three-item convergence)

The 7.55 GB writable layer on `arc-frontend` was **entirely
`/app/.next/cache/fetch-cache/`** — 34,459 entries of Next.js's
server-side `fetch()` response cache. Every entry was `{"kind":
"FETCH", "data":{...}}` with `application/json` content-type — no
data, no logs, no session state, no uploads. Zero alarm case.

But the growth rate was the finding: **7.2 GB in ~22 hours ≈ 8 GB/day**,
which would have re-eaten today's 165 GB reclaim in ~21 days. And
the causal chain runs through three separate register items —
worth writing down so nobody undoes the wrong end:

1. **Wave B R-A gate** (`main.py` `/api/library/<id>`): browser-shaped
   requests reach `_call_translation_model` and — separately — the
   English-original SSR path always fetches full book text
   (`page.tsx:59`, `getWork(id, 'en')`).
2. **Payload size**: `/api/library/<id>` returns full book JSON —
   sampled bodies were 260 KB - 720 KB per book. That's the fuel.
3. **Cache-Control** (`main.py:2262`, tail of Wave B, R-E-adjacent):
   `Cache-Control: public, max-age=3600` set unconditionally. Next.js
   fetch cache honors this header and stores every response. That's
   the ignition.

Cross-stack sanity: hnt-frontend's writable layer was **84 MB** in
its 11-hour life — same mechanism, ~180 MB/day. Hunt has no
`/api/library/*` endpoint, which is exactly why. That divergence
confirmed the causal chain rather than something arc-specific in
the container config.

### Fix — bind /app/.next/cache to arcdata

One line per stack in `docker-compose.yml`:

```yaml
volumes:
  - /mnt/arcdata/docker-caches/arc-frontend-next:/app/.next/cache
```

Bind mount over local-driver-with-device-option: chose bind because
the bytes are directly visible via `ls` without `docker inspect`,
existing arcdata monitoring/backup already covers `/mnt/arcdata/*`
paths naturally, and it's one line of compose config vs. multiple.
Same on-disk outcome, less indirection.

Container runs as UID 1001 (nextjs) with GID 65533 (nogroup); host
dirs created via `mkdir -p` then `chown -R 1001:65533` inside a
throwaway `alpine` container (no sudo path needed).

Structural on Arc (fixes the 8 GB/day), prophylactic on Hunt
(the growth mechanism was identical, just quieter — closes the
door before it becomes a problem).

### Verification

**Arc frontend recreate** (deliberate — the current in-layer cache
was recomputable JSON so it was safe to throw away):

```
BEFORE: arc-frontend  7.75 GB writable layer  (virtual 9.01 GB)
AFTER:  arc-frontend  20.5 kB writable layer  (virtual 1.36 GB)
```

Writable layer dropped **7.72 GB → 20.5 kB** — a 99.9997% collapse.
Inside the container, `/app/.next/cache/fetch-cache/` is now the
bind-mounted directory owned by `nextjs:nogroup`. Bytes land on
sda1.

Health checks:
- `docker ps` running, container up
- `curl -sI https://arc-codex.com/` returns 200
- Live traffic began seeding the cache dir immediately (3 MB
  within the first minute of the recreate; steady write activity
  observed thereafter)

Hunt: same shape, `hnt-frontend` recreated cleanly, 200 on
`https://huntaegis.com/`, mount populating.

### Growth watch — the cache is still unbounded

The fix moves the bytes to a 191-GB-free filesystem and stops the
overlay-layer symptom, but Next.js has **no built-in size cap on
fetch-cache** in the version we run. Gross write rate is ~8 GB/day
on Arc; entries do expire per their `max-age`, so steady-state
should plateau well below the gross rate — the question is where.

**Register (new)**:

- **D5-followup**: observe `/mnt/arcdata/docker-caches/arc-frontend-next`
  for a week. If steady-state exceeds ~30 GB, revisit with a size
  policy — options are a custom Next.js cache handler (real work,
  ongoing maintenance) or a periodic trim cron (treats the symptom
  but simple). Decision when the observation is in, not now.

### R-E gains context

`Cache-Control: public, max-age=3600` on `/api/library/<id>` is now
**load-bearing** for two behaviors:
1. Edge/browser caching (the original reason it's there).
2. Next.js fetch cache lifecycle (the reason today's overhead exists).

Any future R-E change (registered as a MEDIUM item — error paths
serving stale `Cache-Control: public, max-age=3600` for hours) must
consider the fetch cache implication. Dropping `max-age` doesn't
just affect Caddy edge caching; it changes how fast Next.js's fetch
cache turns over. Don't R-E without weighing this.

### Follow-up register updates (all new)

- **D5 — CLOSED** by this entry (was "promoted to next-recon
  priority"; now fixed).
- **D5-followup** — observe steady-state; decide on a size policy
  if it exceeds ~30 GB.
- **R-E — annotated** — the `Cache-Control: public, max-age=3600`
  on `/api/library/<id>` is load-bearing for two purposes now.
  Whoever picks up R-E needs to account for this.

### Bug caught by the very first CI run

CI's first push failed the backend job at pytest with
`ModuleNotFoundError: No module named 'bleach'`. `bleach==6.4.0` is
installed in both boxes' venvs and used at import time by
`fetch_utils.py` (which `main.py` imports transitively via
`rss_feed`) — but it was NOT declared in either stack's
`requirements.txt`. Production worked only because the venvs
happened to have it. A fresh install from `requirements.txt` alone
would have failed on both stacks at first import.

Added `bleach==6.4.0` to both `backend/requirements.txt`. Fixed in
its own commit because a bug caught by the first machine
verification deserves its own line in the story — that is exactly
what R2 is for. Hunt's CI was green because its backend job only
does `py_compile` (parses, does not import); Arc caught it because
its backend job also runs pytest (imports). Same drift, silent on
one stack, loud on the other.

No other missing production deps found in a sweep of all
top-level `import`/`from` statements (`fpdf` is used only in
`makehap.py`, a standalone script not on `main.py`'s graph).

## 2026-07-11 — Register Wave D: auth pass (R12, R10, R16)

Three items closing the register's remaining auth gaps. After this
wave, everything left is projects (R7/R9/R13) and phase-2s.

### R12 — session review (read-only, informed R10's design)

Full Auth.js v5 audit per ASVS V3. No alarming findings, no
fix-now items. Both stacks configured identically.

- **Strategy**: JWT (Auth.js v5, encrypted with AUTH_SECRET). Fine.
- **maxAge**: 30 days. Fine — standard for OAuth consumer apps.
- **JWT contents**: ONLY `token.sub = providerAccountId`
  (Google/GitHub public subject). No sensitive data embedded —
  alarm case ruled out.
- **Cookie flags** all default: httpOnly true, secure auto-true
  in prod, sameSite lax. Fine per ASVS V3.4.
- **Logout**: JWT cookie clear only (client-side). Inherent JWT
  limitation — **REGISTERED** as R12-logout-limitation, not fixed.
- **AUTH_SECRET storage**: `frontend/.env.local`. R9 owns lifecycle.

**R10 verification mechanics chosen**: `await auth()` from
`@/lib/auth` inside a Next.js route handler. Path B (Flask
reimplementing Auth.js's HKDF-derived JWE encryption) rejected
as fragile. Path A already IS the house convention
(`submit_content/route.ts:26`).

### R10 — upload_image auth (both stacks)

Q2 deferral from the health audit — now closed.

**Trust path chosen**: X-User-Id header (house pattern), NOT
scribe-secret. Reason: submit/submit_content/submit_prompt/
submit_comment all use `X-User-Id: session?.user?.id`. This is
the already-hardened trust boundary; scribe-secret is for
service-to-service (bluesky poster etc.), not user-authored
uploads.

**Caddy strip verified** on both vhosts: the arc-codex and
huntaegis `handle /api/*` blocks explicitly
`request_header -X-User-Id`. External clients cannot forge it.
No new strip needed on the new `handle /api/upload_image`
block since the Next.js proxy makes its own auth decision and
sets X-User-Id itself, ignoring any incoming value.

**Implementation**:
- New `frontend/app/api/upload_image/route.ts` (both stacks) —
  mirrors `submit_content/route.ts` (auth() → arc:users fallback
  → 401 → forward multipart formData with X-User-Id).
- `main.py:upload_image` (both stacks) rejects 401 when X-User-Id
  absent, BEFORE the concurrency semaphore. Auth PLUS rate limit.
- Caddyfile: `handle /api/upload_image { reverse_proxy
  localhost:3000 }` (arc) / `localhost:3002` (hunt), inserted
  BEFORE the `/api/*` catch-all. `caddy adapt --validate` clean.
- Publish page `fetch('/api/upload_image', ...)` needed **no code
  change** — the URL is identical, only Caddy routing target moved.

**Verified** (four paths):

| Test | Result |
|---|---|
| T1: public curl, no session → 401 | ✅ 401 |
| T2: public curl with forged X-User-Id → 401 | ✅ 401 (proxy ignores incoming) |
| T3: localhost:5005 direct, no header → 401 | ✅ 401 (Flask gate) |
| T4: localhost:5005 direct with X-User-Id → past auth | ✅ 400 (empty body) |

Log line: `⚠️ Unauthorized upload_image attempt (X-User-Id absent)`
— presence/absence only, Q4 respected.

**Hunt parity**: identical NextAuth config, identical publish
page, identical endpoint — same fix landed.

### R16 — reaction rate limit

**Real-IP verdict — WORKS, not a finding.** `main.py:78`:
`ProxyFix(x_for=1, x_proto=1, x_host=1)`. `get_remote_address()`
reflects the real client IP behind Caddy. Worth writing down so
future per-IP controls don't reinvent it.

**Fix**: `@limiter.limit("30/hour", key_func=get_remote_address)`
decorator on `/api/comment/<comment_id>/react` (both stacks).
Mirrors the `submit_comment` reference case. 30/hour is generous
for humans, ruinous for scripts. Reactions annotate, they don't
gate — this limit protects counter integrity, not safety.

**Verified**: HTTP/1.1 keepalive burst of 35 to same worker →
27 × 200 then 8 × 429 (the 27 is because prior tests had
already consumed 3 slots on that worker; math checks to
30/hour per worker).

### Real bug uncovered by R16's smoke test — REGISTERED, not fixed

Following the behavior guard: a smoke test found a real
pre-existing bug, worth its own line before R16 ships.

**Bug**: **Flask-Limiter 4.1.1's storage is fixed at Limiter
constructor time** (`storage_uri="memory://"` in `auth.py:58`)
and `init_app()` does NOT swap it. Introspection confirms
`type(limiter._storage) == MemoryStorage` after `init_auth()`
completes, despite `RATELIMIT_STORAGE_URI` being set correctly
on the app config. Consequence: every rate-limited endpoint
(`submit_comment`, now `react`) enforces per gunicorn worker,
not globally — effective global limit ≈ N × stated at
`--workers 20`.

- Impact for R16: 30/hour × 20 workers ≈ 600/hour effective
  global. Still ruinous for a scraper's keepalive burst path
  (hits 429 within its own worker fast), so R16 delivers its
  spec's intent even under this bug.
- Impact for `submit_comment`: same math. Has been the house
  state for a long time — R16 just made it visible.
- **R16-followup NEW** — fix Flask-Limiter storage wiring so
  limits are shared across workers. Options: construct Limiter
  with the Redis URI at import time (secret not yet available),
  or swap `limiter.storage` post-init (undocumented), or upgrade
  Limiter to an API version that respects init_app storage
  changes. Priority MEDIUM.

### Smoke suite grows (R1 phase 1)

9 → 11 tests, all green in ~60 ms. New tests:
- `test_upload_image_401_without_x_user_id` — R10 gate.
- `test_react_rate_limit_burst_31` — R16 gate.

conftest.py now runs `limiter.init_app(app)` because the
decorator's ENFORCE path only fires post-init. Documented in the
conftest so future-us doesn't wonder.

### Wave D followup register (all new)

- **R12-logout-limitation** — JWT strategy has no server-side
  session invalidation. Documented, not a bug. Fix would need a
  revocation list (Redis `arc:auth:revoked:<jti>` checked on
  every session read) — separate wave if we ever need it.
- **R16-followup** — Flask-Limiter storage wiring (per above).
- **R10-hardening (optional)** — add
  `request_header -X-User-Id` on the new `handle /api/upload_image`
  Caddyfile block as belt-and-suspenders. Not urgent; the Next
  proxy already ignores incoming X-User-Id.

## 2026-07-11 — R16-followup: Flask-Limiter storage wiring (arc only)

Same-day close on the register line Wave D registered. Hunt was
already correct (see below). Only Arc had the bug.

### The construction-order gotcha — the valuable lesson

Flask-Limiter 4.1.1's `Limiter` locks its `_storage` reference at
`__init__()` time. `init_app()` is documented as the way to
"finish" wiring the Limiter to an app, but **it does not rebuild
the storage backend from `app.config['RATELIMIT_STORAGE_URI']`**.
Whatever `storage_uri=` was passed to the constructor is what
persists — even if you set the config key later and even if you
call `init_app()`.

Arc had:
```
main.py:53   from auth import limiter    # ← auth.py:56 fires:
                                                Limiter(storage_uri="memory://")
main.py:56   load_dotenv()               # ← too late: env now loaded,
                                                but limiter is already built
main.py:250  init_auth(app, ...)         # ← limiter.init_app(app),
                                                storage NOT swapped
```

At `from auth import limiter` (line 53), the process env has
whatever gunicorn/systemd started with, but NOT `backend/.env`.
`load_dotenv()` ran three lines later — too late. The Limiter was
stuck on MemoryStorage forever. Every rate-limited endpoint
(`submit_comment`, `react`) enforced its limit **per gunicorn
worker**, giving effective global limits of `N × stated` at
`--workers 20`.

**This bug pattern recurs in every Flask extension configured
after construction.** Check whenever an extension is instantiated
at import time with a "default" value that a later `init_app()` is
expected to override. It usually isn't.

### Fix (arc)

**Chose option (a1)**: move `load_dotenv()` before
`from auth import limiter`, then read Redis env directly in
`auth.py` at construction:

```
main.py — reordered:
  from dotenv import load_dotenv
  load_dotenv()                          # ← now BEFORE the import below
  from auth import limiter               # ← auth.py sees REDIS_* env vars

auth.py — env-direct construction:
  _lim_host = os.getenv("REDIS_HOST", "localhost")
  _lim_port = int(os.getenv("REDIS_PORT", "6379"))
  _lim_pass = os.getenv("REDIS_PASSWORD", "")
  _LIMITER_STORAGE_URI = f"redis://:{pass}@{host}:{port}/5"
  limiter = Limiter(
      key_func=get_remote_address,
      storage_uri=_LIMITER_STORAGE_URI,
      key_prefix="arc:auth:limiter",
      in_memory_fallback_enabled=True,
      swallow_errors=True,
      ...
  )
```

Rejected options:
- **(a2) mirror Hunt exactly** (construct limiter in `main.py`) —
  auth.py has 3 of its own `@limiter.limit` decorators
  (register/login/forgot) that reference the module-level
  `limiter`. Would need blueprint refactor.
- **(b) deferred construction** (build inside `init_auth`) —
  Flask-Limiter's decorator records intent against the instance
  at import time. If `limiter` is None or not-yet-built when
  routes are imported, decorators crash.

### Storage target (matches CLAUDE.md Redis schema)

- **Arc: DB 5** (shared auth) with `key_prefix="arc:auth:limiter"`.
  Rate-limit keys live with the credentials they protect and ride
  the shared-auth backup path; no new DB slot consumed. This is
  what the prior (broken) code was ALREADY trying to configure via
  `app.config.setdefault("RATELIMIT_KEY_PREFIX", "arc:auth:limiter")`.
- **Hunt: DB 1** (its app DB) with `key_prefix="hnt:limiter"` —
  already in use, not touched.

**Add to CLAUDE.md Redis schema documentation**:
- Arc DB 5 now also stores `LIMITS:LIMITER/arc:auth:limiter/...`
  keys (per-IP, per-endpoint, self-TTL'd at the rate window).

### Failure mode — fail open with in-memory fallback

Both Limiters now constructed with `in_memory_fallback_enabled=True`
+ `swallow_errors=True`. If Redis becomes unreachable, the limiter
falls back to per-worker in-memory storage transparently. Degraded
(back to the old per-worker behavior), but not down — comments and
reactions keep working.

**Eviction risk**: Redis `maxmemory-policy = noeviction` (verified
via `CONFIG GET`). Limiter keys are NEVER silently evicted; under
OOM, new writes error → our `swallow_errors` catches the error →
`in_memory_fallback` engages for that request. Documented; not
re-engineered.

### Verification — bug proven dead

**Introspection** (the exact check that caught the bug last time):

```
Arc:  type(limiter._storage) == RedisStorage   ✅
      key_prefix == "arc:auth:limiter"          ✅
      in_memory_fallback_enabled == True        ✅
      swallow_errors == True                    ✅

Hunt: type(limiter._storage) == RedisStorage   ✅ (already correct)
      key_prefix == "hnt:limiter"               ✅
```

**Live distributed burst** — 35 parallel HTTP/1.0 requests (no
keepalive), forcing round-robin across gunicorn workers:

| Stack | Workers | 200s | 429s | Verdict |
|---|---:|---:|---:|---|
| Arc | 20 | 30 | 5 | Shared 30/hour ✅ |
| Hunt | 3 | 30 | 5 | Shared 30/hour ✅ |

Before the fix on arc, 35 parallel would have returned all 200s
(each worker had its own 30/hour budget, distributed 1-2 per
worker). Now 30 total globally, 5 rejected. Math checks.

**Redis-key evidence** post-burst:
```
DB 5:  LIMITS:LIMITER/arc:auth:limiter/38.175.170.87/react_to_comment/30/1/hour
DB 1:  LIMITS:LIMITER/hnt:limiter/38.175.170.87/react_to_comment/30/1/hour
```
Real client IP correctly captured (ProxyFix + Caddy XFF). Keys
self-expire on the rate window; they won't bloat.

### Smoke suite isolation (conftest)

Tests must NOT hit real Redis. conftest now:
1. Sets `REDIS_HOST=test-redis-unreachable.invalid` before importing
   main, so auth.py's Limiter constructor builds a URI pointing
   nowhere real (harmless — connection is lazy).
2. After import, swaps `main.limiter._storage = MemoryStorage()` for
   deterministic test behavior — bypasses the fallback DNS wait.
3. Calls `main.limiter.init_app(main.app)` — decorator enforcement
   only fires post-init.

Result: 11/11 tests pass in ~120ms. `test_react_rate_limit_burst_31`
still asserts 30 × 200 + 1 × 429 from a single pytest process,
proving the decorator still enforces at the swapped storage.

### R16-followup CLOSED

Register line from Wave D — resolved same day. Both stacks now
have Redis-backed, correctly shared rate limits.

## 2026-07-12 — Source hygiene: negative cache for dead article URLs

Scribe negative-caches article URLs that fail both fetch tiers with
403/503 (TTL 3 days) or 404 (TTL 7 days) under
`scribe:dead_url:{sha256[:16]}` (value = HTTP status). Rationale:
failed fetches previously retried every cycle forever — bloomberg.com
alone was ~23 wasted fetch-pairs/day on permanent 403s. TTLs, not a
blacklist: 403/503 can be a lifted bot-wall or recovered server (3d);
404s rarely come back (7d). 429 and timeouts are deliberately never
cached (throttling/transient). Mirrored in Huntaegis scribe (DB 1).
Inspect: `redis-cli -n 0 --scan --pattern 'scribe:dead_url:*'`.

## 2026-07-12 — M1 backpressure: shed-and-yield (council → Z230, translations yield)

Fixes the 62-hour M1 saturation episode diagnosed this morning (recon:
both stacks' analyzers alone ran ~128% of the M1's serial capacity;
council starved metronomically — 1,569 failures, ~2 comments/hr).
A second inference host (the Z230's own local Ollama) makes the fix
possible without buying M1 capacity.

### Who runs where (after this change)
- **Analyzers (R/B/P):** own the M1. May escalate to cloud
  (gemma4:31b-cloud) under the weekly cap. Unchanged.
- **Council (character comments):** LOCAL generation runs on the **Z230**
  (`COUNCIL_OLLAMA_HOST=http://localhost:11434`, both stacks). Cloud
  personas (arc's gpt-oss:20b-cloud) still resolve cloud-first via the
  council gate — only the *local fallback tier* moved off the M1.
  Timeout 120s (24s typical + margin behind the Z230's serialized queue).
- **Translations:** stay on the M1's e2b but **never escalate to cloud**
  (tiering rule) and **yield** to a backed-up analyzer queue
  (arc library commissions only — Hunt has no library reader).
- **Long-term:** the inference gateway stays the registered project;
  shed-and-yield is the interim that buys time.

### Who yields to whom
- **Council yields to the Z230's own tenants:** skips the poll cycle when
  1-min loadavg ≥ `COUNCIL_MAX_LOAD` (3.0). The Z230 also runs two stacks,
  Redis, Solr, Docker — it's a spare-cycles host, not dedicated.
- **Translations yield to analyzers on the M1:** arc's library commission
  path serves English (graceful degrade) when `analyzer:queue` depth ≥ 3.
  Cached translations are unaffected.
- Both yields log at **DEBUG** — a yielded cycle is the system working.
  Per the quiet-log standard, a WARNING in these paths must be actionable.

### Rollback
Unset `COUNCIL_OLLAMA_HOST` (defaults to the M1) and restart
character_builder — council returns to the M1 wholesale. Everything else
is env-tunable (`COUNCIL_OLLAMA_TIMEOUT`, `COUNCIL_MAX_LOAD`,
`LIBRARY_TRANSLATION_YIELD_DEPTH`).

### Z230 radeon exile — exclude the GPU BY NAME in every framework
The Z230's radeon GPU is a repeat offender: ROCm crashed it (killed
Playwright, March), Vulkan auto-detection crashed Ollama (today). Assume
the next framework's auto-probe will find it too — exclude it explicitly,
never rely on a default. Live in the Ollama systemd override
(`/etc/systemd/system/ollama.service.d/`), confirmed present:
```
Environment="OLLAMA_VULKAN=false"
Environment="GGML_VK_VISIBLE_DEVICES="
```
Any new inference/render framework added to this box gets its own
by-name GPU exclusion in the same override before first run.

### Thinking flag — mandatory OFF on the Z230
`think=false` on every council payload (consolidated into
`_council_payload()` in arc's character_builder). Measured on the Z230:
76s with thinking on vs 24s off — a host that forgets the flag runs 3×
slower and can return empty (gemma4-family thinking-phase token
exhaustion). Z230 is CPU-only (radeon exiled), 8 cores.

### Cloud-valve visibility
Analyzer's valve-closed log now names the condition (weekly cap
exhausted / 429 breaker open / cloud host unreachable). corpus_exporter
exposes `arc_cloud_calls_week` vs `arc_cloud_calls_week_cap` (cap 400) so
exhaustion is a Grafana fact at 60%, not archaeology at 100%.

## 2026-07-17 — R-PT2: prediger offsite-backup alerts (2 rules, textfile collector)

The prediger pull-backup job on this box (see the prediger repo's
RUNBOOK.md, R-PT1/R-PT2) now reports into Arc's monitoring. Arc-side
changes:

- **node-exporter brought under compose** (`docker-compose.grafana.yml`,
  was a standalone `docker run` with identical image/flags/mounts) and
  given `--collector.textfile.directory=/textfile`, bind-mounted from
  `monitoring/textfile/`. Any cron on this box can now drop `.prom`
  files there — it runs as `nobody`, so spool dir + files must be
  world-readable. Runtime `*.prom` files are gitignored.
- **Rules are now 7 in 4 groups**: `arc_alerts.yml` gained group
  `prediger_offsite` — `PredigerBackupStale` (warning: newest dump >48h
  old or last pull exited nonzero; `for: 5m` is safe because the gauges
  update once daily and cannot flap) and `PredigerPullDead` (critical
  dead-man: `absent()` or last report >26h old — fires when the cron
  stops running at all, the failure the script cannot self-report).
- Both rules **live-fired and cleared** on 2026-07-17 by injecting a
  stale spool file / deleting it, confirmed through the full chain:
  Prometheus firing → Alertmanager → `/api/alert` webhook log line.
- Container recreate verified harmless: all four targets `up`,
  Prometheus/Grafana/Alertmanager healthy after.

## 2026-07-18 — Operational coordinates relocated off public /about/developer

The public developer page (`arc-codex.com/about/developer`, no auth) carried
operational coordinates. Moved here first, then stripped from the page and
replaced with capability wording (commit "security: remove operational
coordinates from public /about/developer → runbook"). Canonical values:

**Ports (loopback):** Flask/gunicorn `5005`, Redis `6379`, Solr `8983`,
Next.js frontend `3000`, Caddy admin `2019`.

**Inference host:** MacBook Air M1 at `192.168.1.185:11434` (Ollama). Local
model `gemma4:e2b`; cloud escalation model `gemma4:31b-cloud` (weekly cap).
Spectre secondary at `192.168.1.189:11434`.

**Boot / process management:** arc auto-starts on boot via
`itc-stack.service` (systemd system unit, `enabled`; legacy "itc" name;
`Type=oneshot`, `ExecStart=/home/www/arc_stack/arc.sh start`, `User=ross`).
**Phase 0 correction (2026-07-18):** arc DOES have working systemd
auto-start — the earlier "arc has no systemd unit" was wrong; the unit was
missed by grepping "arc/scribe" not "itc". `arc.sh` is the service manager;
`watchdog` supervises at runtime.

**Backup paths:** cold backup → `/mnt/arcdata/backups` (the page's `/mnt/data`
was stale — that old location was root-owned/unwritable). Library SQLite at
`/mnt/arcdata/library.db` (via `library_db.py`).

**Admin tool:** `kasmir7.py` (interactive console — re-index, diagnostics,
orphan purge, trim, pins, sitemap/rss regen options).

**Retention:** `arc_config.yaml retention_hours: 720` (30d, 2026-07-18; was
48h); scribe end-of-cycle hook prunes news > window and regenerates
sitemap/rss/news-sitemap on delete.

**Caddy routing (order-sensitive):** `/api/auth/*` and `/api/user/*` →
`localhost:3000` (Next.js) MUST precede the `/api/*` → `localhost:5005`
(Flask) catch-all; bare path → `localhost:3000`. Wrong order silently breaks
auth.

**Public read API (Flask, port 5005):** `/api/get_feed`, `/api/article/<id>`,
`/api/search`, `/api/rss`, `/api/wiki/<directive>`, `/api/sitemap`,
`/api/library/*`, `/api/plants`, `/api/syndromes`, `/api/submit`. (The page's
`/api/articles` and `/api/translate/<id>` were stale/removed.)

**Scribe:** v53.0 (page said v50.0). Auth: loopback-only prefs write rejects
non-127.0.0.1; `X-User-Id` injected by the Next.js proxy.
