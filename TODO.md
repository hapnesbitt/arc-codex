# TODO — carried out of session ending 2026-07-17 → 2026-07-18

Items diagnosed but not landed. A fresh session should pick up cold from here.

---

## arc_stack's git working tree IS the production serving directory (TOP STRUCTURAL)

**Source**: hit directly on 2026-07-30 while branching the sources.json split.

**The hazard, stated plainly**: `/home/www/arc_stack` is both the git working
tree and the live serving directory. `backend/sources.json` is **live state
under version control** — it is read from disk by two running consumers:

| Consumer | Read pattern |
|---|---|
| `backend/main.py:2175` `/api/sources` | opens the file **per request**, no in-memory cache |
| `backend/scribe.py:1904` | reloads inside the `while True:` at 1876, i.e. **every ingest cycle** |

Therefore **a branch switch rewrites production, instantly and silently.**

This is not theoretical. On 2026-07-30 `main` held 2183 sources and the working
tree held the operator-confirmed 2052. A plain `git checkout main` would have
restored 131 removed feeds to the live ingest loop within one scribe cycle,
with no deploy, no restart, and no log line saying so. The observability branch
had to be **stacked on the sources branch** specifically to avoid touching the
file — which is a workaround, not a fix, and it couples two unrelated branches.

**Why it is worse than it looks**: the same property means `git stash`,
`git checkout -- .`, `git reset --hard`, a rebase, or a failed merge all mutate
production state. None of them prints a warning. The blast radius is the whole
ingest corpus.

**This needs a real fix before any further branch work in this repo.** Options,
cheapest first:

1. **Move live state out of the tree.** `sources.json` becomes a deployed
   artifact (or a Redis-backed list) with the tracked file as its *source*,
   copied into place by an explicit deploy step. Removes the coupling entirely.
2. **Serve from a separate checkout.** Production reads a deploy directory;
   the git tree is for editing only. Standard, but a bigger change to `arc.sh`.
3. **Guard the switch.** A `post-checkout` hook that refuses (or loudly warns)
   when a tracked live-state file would change. Cheap, but a hook is advisory
   and does not cover `reset --hard`.

**Recommendation: option 1** for `sources.json` specifically, since it is the
only file identified so far with this property. But the audit is not complete —
**UNVERIFIED**: whether other tracked files are read live by running processes.
`directives.json` and `prompts.yaml` are both loaded by scribe and are both
tracked; neither has been checked for the same per-cycle reload pattern.

**Depends on**: nothing. Blocks: safe branch work in arc_stack.

---

## monitoring/alloy: 3 of 4 integration tests fail, with no passing baseline

**Source**: observed 2026-07-30, immediately after committing the pipeline in
`9d4e18b`. Recorded rather than hidden — the commit was deliberately **not**
amended, because rewriting a commit to bury a real finding is worse than the
finding.

**The failures**, from `monitoring/alloy/tests/test_alloy_integration.py`:

```
FAILED  test_positions_error_restarts_from_end_and_logs_failure
FAILED  test_startup_at_eof_and_restart_persistence
FAILED  test_wal_replays_after_loki_outage_and_alloy_restart
3 failed, 1 passed in 147.80s
```

All three fail identically: `wait_query(self.harness.loki_port, selector)`
returns `[]`, i.e. a line written to the tailed file never arrives in the
harness's Loki inside the 60s timeout.

**All three are durability tests** — WAL replay after a Loki outage,
positions-file recovery, and restart persistence. That is precisely the
property that decides whether access logs survive a restart or an outage, so
these are not cosmetic failures if they are real.

**There is no passing baseline.** The test file was untracked until `9d4e18b`,
so it has never run in CI and there is no commit at which it is known to have
passed. It is therefore **UNKNOWN** whether these are:

- real defects in `config.alloy`'s WAL/positions handling, or
- harness problems (port binding, container startup timing, the 60s timeout
  being too short on a loaded box).

Distinguishing the two is the first task, before any fix.

**What DOES pass**: `tests/test_sanitization.py`, 7/7. That is the test holding
the allow-list property (a new Caddy log field is dropped by default rather
than forwarded unreviewed), and it was run before the commit landed.

**Depends on**: nothing.

---

## Hero images: scribe's ingest crop discards source detail permanently (TOP PRIORITY)

**Source**: diagnosed 2026-07-29. The reversible half already landed
(arc `8cad8a4`, hunt `bdc1901`); this is the half that actually matters.

**Symptom**: `scribe.rehost_article_image` (`backend/scribe.py:632-637`,
`REHOST_W/REHOST_H = 1200, 675`) center-crops every fetched hero to 16:9 and
**discards the original**. Source images are not 16:9 — measured across 7,429
rehost log lines: 34% 16:9-ish, 26% 3:2-ish, 24% wide, 6.9% 4:3, 5.3% square,
1.7% portrait. The crop is lossy for everything outside that middle band, and
because the original is never kept the loss is unrecoverable.

**Measurements** (from scribe's own `NNNxNNN → 1200x675` log lines):

| metric | value |
|---|---|
| mean source discarded | **11.8%** |
| median | 7.4% |
| p90 | **26.2%** |
| p99 | 56.9% |
| worst | 86.8% (an 889x66 banner) |
| images losing >10% | 47.1% |
| images losing >25% | 10.7% |
| **images losing >40%** | **6.8%** |

That 6.8% tail is the number that justifies the work: charts, maps, and
captioned graphics in it are destroyed as information, not merely tightened.

**Fix**: store a less aggressive derivative — clamp the source ratio into a
sane band instead of forcing a single 16:9, and let the card decide
presentation. Projected cost, same dataset (mean stored pixels per image vs
today's flat 810,000):

| policy | px/img | vs today | mean loss | >40% tail |
|---|---|---|---|---|
| 1.778 fixed (today) | 810,000 | — | 11.8% | 6.8% |
| clamp [1.50, 2.00] | 850,677 | +5% | 4.0% | 1.9% |
| **clamp [1.33, 2.00]** | 866,728 | **+7%** | **2.7%** | **1.5%** |
| clamp [1.25, 2.35] | 869,207 | +7% | 2.0% | 0.7% |
| no clamp | 893,399 | +10% | 0% | 0% |

`[1.33, 2.00]` looks like the sweet spot: mean loss 11.8% → 2.7% and the
>40% tail 6.8% → 1.5%, for +7% storage (~85MB against Arc's current 1.2G
`uploads/scraped`). Cheap. **The ratio clamp is the decision to make.**

**Constraints, read before starting**:
- **Only helps new images.** A backfill is *impossible*, not merely pending —
  the originals were never retained. Only re-fetching from
  `image_source_url` could recover them, and scribe already notes ~3% of
  those 403 on hotlink with URLs rotting over time.
- **Not a variant-pipeline change.** `scripts/make_image_variants.py` and the
  inline variant loop (`scribe.py:646-653`) both derive from the
  already-cropped file, so smart cropping there fixes nothing. The change
  belongs at `scribe.py:637`.
- **Pillow cannot smart-crop.** Pillow 12.2.0 has `ImageOps.fit()` (same
  deterministic anchor crop we already do) and `Image.entropy()` (a
  whole-image scalar). Entropy cropping is hand-rollable via a sliding
  window; real attention-based cropping needs `pyvips` (`crop="attention"`),
  which is a libvips system dependency, not a pip add. `pyvips`, `smartcrop`
  and `opencv` are all currently absent. **A variable ratio clamp gets most
  of the benefit with none of this**, so do the clamp first and treat smart
  cropping as a separate question.
- Changing the stored ratio means changing the card container with it — see
  the comment at `IntelligenceCard.tsx` hero div. One decision, not two.
- Applies to **both stacks**; `huntaegis_stack/backend/scribe.py:504` carries
  the identical constant.

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
