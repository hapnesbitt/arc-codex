# Arc Stack Ops Runbook

Records host-level changes that live outside git (redis.conf, fstab, sysctl),
so the repo history stays the single narrative of what changed and why.

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
