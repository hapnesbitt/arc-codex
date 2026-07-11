# Arc Stack Ops Runbook

Records host-level changes that live outside git (redis.conf, fstab, sysctl),
so the repo history stays the single narrative of what changed and why.

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
