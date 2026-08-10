# Arc Codex Library refresh lifecycle

## Canonical count and publication flow

The canonical public work count is the row count of the SQLite `works` table
in `/mnt/arcdata/library.db`:

```sql
SELECT COUNT(*) FROM works;
```

`GET /api/library/stats` reads that count through `library_db.count_works()`.
The `/library` Server Component caches its landing API fetches for up to one
hour under the Next cache tag `library-landing`.

The weekly lifecycle is:

```text
library_fetcher.py
    -> acquires pids/library_fetcher.lock without waiting
    -> commits each valid work and completed shelf
    -> emits a final SUCCESS/FAILURE summary and exits 0/nonzero
    -> on SUCCESS only, POSTs to the authenticated local Next route
       /api/internal/revalidate-library
    -> Next immediately expires the library-landing tag and /library path
    -> the next /library request reads the current Flask API values
```

Chimera scoring remains a separate annotation job. `score_library.py` is not
a publication gate and does not revalidate the Library landing page.

`arc.sh` creates one scoped `LIBRARY_REVALIDATE_SECRET` when the frontend is
started and stores the same value in the ignored `backend/.env` and
`frontend/.env.local` files. The value is never printed. If the two files
contain different values, frontend startup fails rather than rotating either
credential silently. The endpoint is also reached directly on localhost;
Caddy's public `/api/*` route continues to target Flask.

Real runtime environment files are excluded from the repository-root Docker
build context. `.env.example`, `.env.sample`, and `.env.template` files remain
available as non-secret documentation/templates; runtime secrets continue to
enter the frontend through Compose's existing `env_file` configuration.

## Fetcher outcomes

Only one refresh can run at a time. The fetcher holds a nonblocking advisory
`flock` on `/home/www/arc_stack/pids/library_fetcher.lock` for ingestion and
publication. A second invocation logs that a refresh is already active and
exits successfully without doing work. The kernel releases the lock when the
file descriptor closes, including process exit or crash; the persistent empty
lock file is not a PID file and needs no cleanup.

Every successful work upsert is committed immediately, so an interrupted run
can be rerun safely without duplicating Gutenberg IDs. Each Gutenberg shelf
page must include self-consistent `totalResults`, `startIndex`, and
`itemsPerPage` metadata, the exact number of `li.booklink` results implied by it,
and the expected Next link while more results remain. A terminal page has no
Next link. A malformed, challenged, inconsistent, or incomplete page leaves
the prior shelf membership untouched.

Expected Gutenberg entries with no published plain-text rendition are counted
as skipped. Transport, parse, configuration, database, or unexpected work
failures are counted as failures, produce a nonzero exit, and prevent cache
publication. Pruning occurs only after work and shelf processing is otherwise
clean. SIGTERM/SIGINT stops further work, prevents pruning/publication, and is
reported through the interrupted failure summary when shutdown permits.

A publication failure also produces a nonzero exit, although all already
committed Library data remains valid. Publication intentionally makes only
three immediate attempts; there is no durable publication queue in this
change. Next's hourly revalidation remains a fallback, and an operator can
retry only publication after the frontend recovers with:

```bash
cd /home/www/arc_stack/backend
/home/www/arc_stack/backend/venv/bin/python -c 'import library_fetcher; library_fetcher.publish_library()'
```

The final log line begins `LIBRARY REFRESH SUMMARY` and includes start/finish
timestamps, runtime, examined/inserted/updated/skipped/failed/pruned counts,
shelf completion, final `COUNT(*)`, publication state, and exit status.

## Manual verification

Run these read-only checks after a successful refresh:

```bash
sqlite3 -readonly /mnt/arcdata/library.db 'SELECT COUNT(*) FROM works;'
curl -sS http://127.0.0.1:5005/api/library/stats
curl -sS https://arc-codex.com/library | rg -o '[0-9,]+<!-- --> Works' -m 1
```

The database count, API `works` value, and public page count should agree.
No frontend rebuild or container restart is required for future successful
refreshes.

## 2026-08-09 incident and implementation audit

The Sunday cron began at 05:00 MDT. Its last fetcher line was written at
07:09:09 while processing the `politics` shelf (1236/1467). Host journal boot
boundaries show the old boot ended at 07:09:09 and the next began at 07:09:30.
At 07:08:36 `systemd-logind` recorded `The system will reboot now!`; cron was
stopped and PID 622255 (the fetcher's Python process) remained until shutdown
sent SIGTERM to remaining processes at 07:09:09. There is no evidence of an
OOM, SQLite lock, Gutenberg exception, or application early exit causing that
truncation.

Old publication behavior retained a previously valid API result in Next's
one-hour persistent cache, so ingestion and visibility were decoupled until
expiry or a clean frontend build. New behavior invalidates only the Library
landing tag/path after a clean ingest. The weekly Sunday fetch and Monday
scoring schedules remain unchanged.

Implementation validation records belong in the completion report for the
change, including before/after database, API, and public counts and whether the
one-time deployment restarted the frontend container.

### Deployment validation (2026-08-09)

- The pre-deployment read-only count was 26,501 works. A manual fetcher process
  that predated this change (PID 45020, started 16:37 MDT) remained in flight,
  so the authoritative count continued to increase during validation. It was
  not stopped or modified.
- The new frontend image compiled successfully on Next 16.2.12 and the
  production frontend container was recreated once at 16:58 MDT to deploy the
  route. No backend process was restarted.
- A direct unauthenticated request to the Next route returned 401. The public
  HTTPS `/api/internal/revalidate-library` path continued to terminate at
  Flask/Caddy with 404, so the purge handler was not exposed through Caddy.
- Authenticated production revalidation completed on its first attempt. At the
  final 17:02 MDT snapshot, SQLite, `/api/library/stats`, local `/library`, and
  public HTTPS `/library` all returned 26,509.
- A disposable loopback-only container tested a true changing value without
  touching live data: the built image initially rendered its baked 26,502;
  after one authenticated revalidation, its next request rendered the mock
  API's 424,242. The same image was used before and after, proving no rebuild
  or restart is required for count publication. The container and mock server
  were removed after the test.
- `score_library.py` was not run; `logs/score_library.log` retained its
  2026-08-03 timestamp.
