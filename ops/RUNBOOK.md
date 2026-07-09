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

Root-cause fix landing separately — see commits following this entry.
