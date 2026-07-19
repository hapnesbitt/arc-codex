# TODO — carried out of session ending 2026-07-17 → 2026-07-18

Items diagnosed but not landed. A fresh session should pick up cold from here.

---

## /library UI: "works" count double-counts shelf memberships

`/library` reports **34,717 works**, but that is the `shelf_members`
row count — a book on N shelves is counted N times. Distinct works =
**25,415** (verified 2026-07-18: `SELECT COUNT(*) FROM works`). The
sitemap is already correct (all 25,415 works + 34 shelves indexed) — this
is a display-label bug only. Fix: report distinct works, not
shelf-membership rows, in the `/library` count (frontend/library-endpoint
change — its own commit, separate from the /about accuracy pass). While in
there: 6 orphan `shelf_members` rows reference deleted works (cheap cleanup).

## SW: stop caching HTML (deferred from PWA audit)

**Source**: [`docs/pwa-audit-2026-07-17.md`](docs/pwa-audit-2026-07-17.md) §2, §3.

**Symptom / risk**: `frontend/public/sw.js` currently uses network-first with
cache-fallback for every non-API GET, so all HTML responses land in the SW
cache keyed by URL only. Since our new server-side ISR contract
(`docs/perf-2026-07-17.md`) explicitly relies on the SSR path never touching
cookies so it can serve one cached anonymous view, and the SW's HTML cache
does not partition by cookie either, the failure mode is:

1. Authed user visits `/article/private-x` — HTML lands in `arc-v1`.
2. User logs out.
3. Network flakes / backend outage / offline.
4. SW returns the still-cached authed HTML.

Same-device only, no cross-user leak, but a real "logged out, still see my
old private view" bug. Also: `CACHE_NAME` is hardcoded `'arc-v1'` and grows
unbounded between manual bumps.

**Fix** (~30-line rewrite; skipped this session per <5-line rule):
- Precache only `/manifest.json` + the three icon files. Drop `/`.
- On fetch: pass through pages entirely (no cache read, no cache write). Keep
  cache-first only for `/_next/static/*` (content-hashed, safe forever).
- Bump `CACHE_NAME` to `arc-v2` so `activate()` drops the old cache on next
  visit.
- Ship in the same deploy as any next frontend rebuild; users pick it up
  automatically because `/sw.js` is served with `max-age=0`.

**Do not partially do this.** Half-applying (e.g. bumping the cache name
without changing the fetch strategy) just resets the accumulated HTML cache
and leaves the underlying pattern intact.

## SW: update-flow UX (nice-to-have)

Currently `skipWaiting()` + `clients.claim()` swap the worker mid-session
but the active tab keeps its old asset references until the next navigation.
Consider a `controllerchange` listener that soft-reloads once, or a
"new version available — reload" toast. Not urgent.

## SW: automate CACHE_NAME bumps

Hardcoded string is easy to forget. Wire to the Next.js build ID or a
git-sha env at build time so every deploy naturally bumps the cache.

## iOS installed-app session parity (SoC pattern)

`display: standalone` + `appleWebApp.capable: true` = SoC-incident shape.
On some iOS versions, the installed home-screen app runs in a separate
storage partition from Safari; a user signed in on Safari may not be signed
in in the installed app. Not a security bug (installed app needs its own
sign-in), but user-facing confusing.

**Decision needed** (not code):
- Accept + document, or
- Add a first-launch prompt in the installed app telling users they'll need
  to sign in there separately, or
- Drop `display: standalone` (loses installable-app feel).

## Lighthouse baseline

Never captured. Run once via the `claude-in-chrome` skill, commit the report,
so future PWA/perf regressions have a numeric baseline.

---

## Plant warm run — resume when Ollama is back

**State at session end**: Stopped at 11:07:58 on 2026-07-17 with a dump of
~65 UNRESOLVED lines. Last plant completed successfully: **Alyssum
(178914b2)** at 10:40:03. Runtime coincided with M1 Ollama going down —
every subsequent call refused, run bailed with unresolved dump.

**Root cause**: `192.168.1.185:11434` refusing TCP connections (M1 pings
fine at 73ms; Ollama daemon itself down). See "M1 Ollama daemon down"
below.

**Resume command** (assumes cached-skip works as documented — restart is a
noop for the 3 already-completed plants and picks up from Amaranth or
whichever the next uncached plant is):

```bash
# From /home/www/claude_stack (Session-on-Claude for plants, DB2):
# TODO: fill in the exact plant-warm invocation — I did not observe it
# start, only its log at /home/www/claude_stack/logs/plant_warm.log.
# Look for the script that wrote "warm run start: 76 plants, local tier,
# sequential" at 10:34:51.
```

The tail -f watcher (PID 417806 at session end) is a passive log-follower;
it survives independent of any Claude session. Nothing to restart on the
watcher side. **The warm run process itself is dead** — must be re-invoked
manually.

## dlb: re-run A.R.C. analyses for article `89c049b724d24503b3b0eb000e7c8d83`

**State**: On-demand cycle fired successfully 2026-07-17 16:18 —
event posted, article renders on https://dlb.arc-codex.com/ with title,
narrative, and structured data. But the three A.R.C. analyses
(red/blue/purple) are empty because Ollama on the M1 was down when the
analyzer picked it up (same root cause as the plant warm run stop).

**Fix once Ollama is back**:

```bash
# Re-enqueue the article for the dlb analyzer:
REDIS_PASSWORD=$(grep '^REDIS_PASSWORD=' /home/www/deliberation_stack/backend/.env | cut -d= -f2- | tr -d '"')
redis-cli -a "$REDIS_PASSWORD" -n 6 LPUSH dlb:analyzer:queue 89c049b724d24503b3b0eb000e7c8d83
# Verify it processed:
tail -f /home/www/deliberation_stack/logs/analyzer.log
```

The analyzer is running (dlb.sh status confirmed at session end); it just
needs a healthy Ollama upstream. Article + digest are intact — only the
A.R.C. bullets missing.

## M1 Ollama daemon down (blocking both above)

**State**: `ping 192.168.1.185` OK (73ms); `TCP 192.168.1.185:11434`
connection refused. Every Ollama request today has failed cloud+local
fallback (arc's analyzer.log and dlb's analyzer.log both show identical
errors from ~14:00 through session end).

**Fix**: SSH to the M1 (or physically), restart `ollama serve`. Not
scriptable from the Z230 without existing SSH setup — needs the human.

Once Ollama is back, the two items above cascade:
1. Re-run the dlb LPUSH for article 89c049b7.
2. Kick the plant warm run resume.

## Ross's scribe.py edit — leave alone

`backend/scribe.py` has `CYCLE_MINUTES = 1` in the working tree (was `69`).
Left unstaged per session-closeout instruction. If Ross forgot about it,
this is worth flagging — 1-min scribe cycles will exhaust the weekly
gemma4:31b cloud allowance in hours. Not touched here.

---

## Perf work — done, deployed, committed

- Report: `docs/perf-2026-07-17.md` — layer table, real-traffic baseline,
  RSS math, before/after numbers, auth-bypass + revalidate + mobile-viewport
  verification.
- Commit: `5890fed` on `main`, pushed.
- Deploy: `docker compose up -d --no-deps frontend` — **must use
  `--no-deps`** to avoid Compose trying to recreate the bare-metal
  gunicorn container (port 5005 conflict). Noted in the report.
- Numbers: full-chain `/` 74.7 → 219 req/s (+2.9×), 622ms → 218ms avg (−65%).
  Node-direct SSR 76 → 1106 req/s (+14.5×), 636ms → 50ms (−92%).
