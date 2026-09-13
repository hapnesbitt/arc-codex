# TODO — carried out of session ending 2026-07-17 → 2026-07-18

Items diagnosed but not landed. A fresh session should pick up cold from here.

---

## 2026-09-13 session handoff — analyzer throughput, -np 2 rolled back before reboot

### URGENT before reboot: spectre's `-np 2` drop-in must be removed

At session close, spectre was running `ollama` with `OLLAMA_NUM_PARALLEL=2` via
`/etc/systemd/system/ollama.service.d/20-parallel.conf`, and llama-server had
spawned with `-c 65536 -np 2`. That is the OOM state: projected RSS ~16.5 GiB
on 14 GiB physical, zero swap. Memory read fine only because just one KV slot
was populated at a time; the second slot's pages materialize on first
concurrent inference. A spectre reboot in this state will OOM-kill Ollama on
the first request, taking all analysis down.

**Rollback command** (run before reboot if the drop-in is still there):

```bash
ssh spectre 'sudo rm /etc/systemd/system/ollama.service.d/20-parallel.conf && \
             sudo systemctl daemon-reload && sudo systemctl restart ollama'
```

### Committed but runtime-reverted: `analyzer` local-path context cap

Two commits landed and pushed on `main`:

- `46f7a17` — `analyzer: cap local-path num_ctx at 16384 (from 32768)`
- `44a99a4` — `analyzer: cap analysis_max_chars at 50000 for 16k n_ctx budget`

Purpose: fit a second parallel slot on spectre inside 14 GiB. The code and
config are correct for `-np 2`; the reason the runner still used 32k per slot
this session was **three analyzer.py processes on resolute (PIDs 5891, 468566,
497131) were started before the commits and had the old `ollama_utils.py`
cached in memory** — they kept requesting `num_ctx=32768`. Ollama sized
llama-server from the first stale request: `32768 × 2 = -c 65536`.
`OLLAMA_CONTEXT_LENGTH` on the server is a floor for lazy clients, not a
ceiling — it cannot clamp a client's 32k request down.

**Safe re-enable sequence** (after reboot resolves the stale-code issue by
itself):

```bash
# Verify analyzer processes started with the committed code:
grep -c '^    opts.setdefault("num_ctx", 16384)' /home/www/arc_stack/backend/ollama_utils.py
ps -o pid,etime,cmd -C python3 | grep analyzer.py    # expect ONE, not three

# Re-apply the drop-in:
ssh spectre 'sudo tee /etc/systemd/system/ollama.service.d/20-parallel.conf >/dev/null <<EOF
[Service]
Environment="OLLAMA_NUM_PARALLEL=2"
EOF
sudo systemctl daemon-reload && sudo systemctl restart ollama'

# Wait 30s, then verify:
ssh spectre 'systemctl show ollama --property=Environment; \
             ps -eo cmd | grep -E "[l]lama-server" | grep -oE "(-np [0-9]+|-c [0-9]+)"'
# Expected: OLLAMA_NUM_PARALLEL=2 in env, and `-c 32768 -np 2` on llama-server
```

Trade-off accepted at 50k cap + 16k n_ctx: **~1.4% of articles on the far tail
(bodies over ~50k chars → prompts over ~16k gemma tokens) will silently
truncate.** Measured against 218 recently-analyzed articles with tiktoken
cl100k_base + 1.15× gemma multiplier: p50 3,837 tok / p90 8,804 tok / p99
16,406 tok / max 19,726 tok. If truncation-signal `done_reason=length` shows
up frequently in `logs/analyzer.log`, lower `arc.cfg` `analysis_max_chars`
further (~24000 is the safe number with 4k output headroom).

### Silent data loss — the real finding, still uncounted

Over the 24h ending at session close, **65 articles aged out of the 6h audio
window unanalyzed with zero log lines and zero retry counters** — the failure
mode audio_backfill's `find_newest_silent` produces when it passes over an
unanalyzed article. Method: articles whose `feed_ts + 6h` boundary crossed in
the last 24h, minus those that got audio, minus retries, minus private —
`grand_total_permanently_silent_unanalyzed = 65 of 208 whose window closed`.
Plus a further 46 that were analyzed but not narrated in time (different bug).

**No metric exists for this.** corpus_exporter.py has no counter for
"candidate passed to next pass because unanalyzed." Adding one to
`find_newest_silent` (increment `arc:stats:aged_out_unanalyzed` when
`_is_analyzed` returns False AND `feed_ts` is close to the window cutoff)
would surface the loss without needing to grep across two log files.

### Ingestion recon — cycle_minutes=3 fills the queue permanently

`arc.cfg [ingestion] cycle_minutes = 3` (operator-tuned, dirty as a standing
exception; the committed default is 97). With Ross publishing one story per
sweep, that sets **arrival rate = 20 articles/hr**. Analyzer measured
throughput this session: **10.3 completions/hr** (247 in 24h, of which 62%
were `local_full` at 368s mean on spectre, 38% `cloud` at 4.5s). Queue depth
grew from 149 → 156 → 153 across the session with no restart able to change
the arithmetic on its own.

**Ross's proposal: 15**. At `cycle_minutes = 15`, arrival rate drops to ~4/hr,
below the 10.3/hr drain, and the queue empties. Zero code change. Best move
before considering `-np 2` again — the parallel-slot work only matters if
arrival ≥ drain and you want the drain to catch up.

Second-order: `[ingestion]` is protected by the CLAUDE.md rule about
operator-tuned fields. Any change to `cycle_minutes` needs to be Ross's
edit, not a normalization pass. Session left `cycle_minutes = 3` dirty
exactly as found.

### Stale inference routing in `arc.cfg` (informational, still routes correctly via .env)

`arc.cfg [inference]` at line 62 has:

```
ollama_url  = "http://192.168.1.185:11434"   ← the M1 — verified this session, models=[] empty
council_url = "http://localhost:11434"        ← resolute — has qwen2.5:1.5b and gpt-oss:latest,
                                                 NOT gemma4:e2b, which is what character_builder wants
```

`backend/.env` overrides both for real routing (`OLLAMA_URL`,
`OLLAMA_PRIMARY`, `OLLAMA_FALLBACK` all point at `http://192.168.1.189:11434`,
i.e. spectre). Production is unaffected today. But arc.cfg is what
`site_config.py` documents to a reader — the M1 pointer is a lie the next
audit will trip over. Same for the council pointer: character_builder assumes
gemma4:e2b is on `council_url`; if the .env override ever slips or a fresh
deploy uses cfg defaults, council calls will fail with `model not found`.

Not fixed this session because arc.cfg is a standing dirty exception and
the wire-through would need Ross's operator-mode edit — but this is exactly
the kind of drift the [[caddy-api-routing-topology]] and [[cloud-model-migration-in-flight]]
audits caught after it broke something. The right change is either update
both defaults to `http://192.168.1.189:11434` and drop the .env overrides, or
add a `.example` cfg documenting the .env-owned fields and delete the stale
lines here.

### Three duplicate analyzer.py processes on resolute (reboot will resolve)

`arc-watchdog` spawned two extra processes over the last day (PIDs 468566
~4h ago, 497131 ~3h ago) without stopping the original 5891 (18h). All three
BRPOP the same queue but with spectre serialising at one slot, only one is
ever active. Reboot restarts arc.sh cleanly and should leave exactly one
analyzer.py. If it doesn't, `watchdog.sh` has a bug worth chasing — see the
duplicate-start logic in its analyzer entry.

### Session-only findings not carried forward

- 62% of analyzer traffic is `local_full` (spectre), not cloud — the earlier
  assumption that gemma4:31b-cloud was the serialization point was wrong.
  Every article gets a Phase-1 local pass on spectre regardless; cloud only
  fires for the 38% that `decide_escalate` flags.
- Cloud call latency: mean 4.5s / p50 3.7s / p90 7.4s / max 10.4s. Cloud is
  not a bottleneck at any observed rate.
- Local call latency: mean 368s / p50 344s / p90 540s / max 885s. That's
  where the analyzer's hours actually go.
- `character_builder.py:64-67` comment still describes the July "M1 belongs
  to the analyzers, council on Z230" decision as current. Void — the M1 has
  no models, gemma4:e2b lives on spectre.


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

## monitoring/alloy: committed but NEVER DEPLOYED — corrects a false claim in 9d4e18b

**Source**: verified 2026-07-30, during reboot-readiness recon.

**Correction first.** Commit `9d4e18b` states:

> This was already running in production from uncommitted files
> (arc-loki container up, Alloy host unit active) before this commit —
> the code is not new, only its version control.

**The second half of that is false.** `arc-loki` being up is true and was
verified. "Alloy host unit active" was inferred from the container running
and `monitoring/alloy/alloy.service` existing in the tree, and was never
checked. It is wrong.

`9d4e18b` is deliberately NOT amended — it is pushed, and rewriting history
to erase a wrong claim is worse than the claim. This item is the correction
of record.

**What is actually true on this host:**

| Check | Result |
|---|---|
| `alloy` / `grafana-alloy` on PATH | absent |
| `alloy` binary anywhere (`find /`) | absent |
| systemd unit (`/etc/systemd`, `/lib/systemd`, `/usr/lib/systemd`) | none |
| running process | none |
| container, **including stopped** (`docker ps -a`) | none |
| `grafana/alloy:v1.16.1` image | **pulled** (684MB) — test harness only |
| Loki `/loki/api/v1/labels` | `{"status":"success"}`, **zero labels** |
| Loki series for `{job="caddy_access"}` | `[]` — **zero streams** |
| `arc-loki` container | up, `unless-stopped` — genuinely deployed |

So: **Loki is deployed and empty. Alloy has never run.** The pipeline has
never carried a single log line. `alloy.service` in this repo is a proposed
unit, not an installed one.

**Consequence**: the pipeline is config-complete and version-controlled but
has zero production evidence behind it. Nothing about it — sanitization,
allow-listing, WAL behaviour — has been observed against real Caddy traffic.
Treat every property of it as untested in production until Alloy is actually
installed and Loki shows streams.

**Deploying it needs**, none of which has been done: install the Alloy
binary, install `monitoring/alloy/alloy.service` to `/etc/systemd/system`,
`systemctl enable --now` it — **enable, not just start**, or it dies at the
next reboot with no warning — and confirm `{job="caddy_access"}` returns
streams before believing any of it works.

**Related**: the `.service` file grants Alloy read access to
`/var/log/caddy/*.log`, some of which are `-rw-------` (athena, dlb). Whether
the unit's user can actually read those is **UNVERIFIED** and would surface
immediately on first start.

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

**Ruled out as the cause**: the missing host Alloy binary (see the item
above). The harness runs `grafana/alloy:v1.16.1` as a Docker image
(`test_alloy_integration.py:26`), not a host binary, so the deployment gap
does not explain the failures. Checked rather than assumed.

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

---

# Session close 2026-09-03 — next steps (recorded, not built)

Filed at session end. Nothing here was implemented today. Sections are
ordered as they should be picked up, not by size.

## 1. Faculty index for School of Chat

34 characters exist as LDAP records with no public presence.
`web_app.py` already renders `/faculty/<uid>` and builds faculty cards
internally on port 8765 — the work is surfacing that at
`soc.arc-codex.com` in SoC's design, not building the endpoint.

**Ordering matters.** The faculty index comes before the About page
(which would otherwise read as faculty appearing from nowhere) and
before the reporter portfolio.

**Open question to resolve first**, before writing any UI: how much of
a faculty page is public, given most records have never been through
the gates and Miriam's precedent is a public profile with a withheld
class. This is a decision, not code — do not proceed to layout until
Ross has answered it.

---

## 2. Practice the page template on `elias.grant`

Once #1's shape is decided, `elias.grant` is the right first character
to build against. Economics / Monetary Policy / Public Finance maps to
`economic-policy-and-financial-markets` — newsradio's largest and
best-populated directive, so the page won't be sparse.

**Generalize** the `externalStation` field that was added for
`af_heart` into **one station slot on the faculty template**, rather
than shipping a second per-character special case. Any future faculty
member with a radio presence points at that same slot.

---

## 3. Per-professor radio — shared voice, per-directive slice

Mapping professors onto existing directives is nearly free; the
newsradio builder already slices one corpus into 25 programs, so
"Elias's program" is a filter on the existing pipeline. That part is
cheap.

**Per-professor voices are not cheap.** Record the arithmetic here so
nobody plans a multi-voice rollout without seeing it:

- Kokoro runs ~15 chars/s.
- `audio_backfill.py` is the sole narrator, holding a single mutex,
  one article at a time.
- Throttled to one acquire per 95 minutes in the weekday peak window.
- Coverage today is 74.9% against one station.
- `validate_native_format` skips any directive whose source audio
  doesn't match the configured voice — so introducing a second voice
  doesn't just double the queue, it fragments validation.

**Design conclusion**: shared voice, per-directive slice. One voice
per language, always — this matches the existing
[[audio-voice-one-per-language]] policy. Per-professor voice is
off-the-table until the throughput/validation story changes. **The
Kokoro-move + chunked-synthesis work in Section 6 below is
exactly that story changing** — cross-reference forward.

---

## 4. Reporter portfolio

Showcase demonstrating the framework as a **configurable agent
harness** — reporters as (directives + sourceScope + threshold +
cadence + escalation + outputs).

**Current state**: only `miriam.vale` carries `reporter` in `roles`.
Torchy doesn't, despite the byline. Fix the role tagging before
building the portfolio page, or the portfolio will misrepresent what
exists.

**Blocked on**: the topic scorer fix (see "Still open" below). A
portfolio pitching routing precision cannot ship on a scorer that puts
finance stories in Mathematics — the demo would undercut the pitch on
its first click.

---

## 5. American history since 1650 — for Ross's son

Build as a **primer_engine** work with its own YAML config, alongside
Beowulf / Holmes / Mark / Athena. This is the machine that has been
proven four times.

**Not newsradio.** Arc's corpus is news and has no history directive;
this is the primer machine, not the radio pipeline.

**Sources**: public-domain material for the 1650→present American
period is abundant — no acquisition problem.

**Optional later tie-in**: bookradio-style narration once the text
work is stable. Don't design for it upfront; if Ross would rather
listen than read, it layers on after.

---

## Still open from earlier sessions (unchanged, carried forward)

Not re-explained here — each has its own section elsewhere in this
file or its own commit history. Listed so this session-close block is
a complete pickup point.

- **Topic scorer fix** — confirmed, unfixed. **Highest value of any
  item on the list**, and gates #4 above.
- **`min_article_chars_captcha`** — designed, unlanded.
- **`kasmir7` shared-utility pull** — pending.
- **Alloy** — never installed. Also documented above in the
  "monitoring/alloy: committed but NEVER DEPLOYED" section (2026-07-30)
  and in `ops/REBOOT.md` known-gaps #1. Mentioned here only so the
  pickup list is complete; the root record is those two.

---

## 6. Move Kokoro to spectre; then chunked synthesis to remove the 9,000-char ceiling

**Status at filing (2026-09-03)**: plan and decisions locked with Ross;
nothing built. This is a three-phase piece of work, sequenced
deliberately so each phase measures against the surface the next phase
runs on. Cross-linked from Section 3.

### The problem, restated with measured numbers

Resolute (Z230) is saturated: load 7.28 / 6.39 / 6.27 at the time of
scoping, 614 MB free of 31 GB (16 GB available including buff/cache).
Kokoro synthesis at PID 498047 was **328% CPU, 2.2 GB RSS** —
the single largest consumer, 3.3× the runner-up. Kokoro is CPU-bound
and lives inside `audio_backfill.py` in this stack only because that's
where the module was originally written, not because the Z230 was ever
chosen for it. The Z230 also carries gunicorn, scribe, analyzer, the
frontend, Caddy, Redis, Solr, and the monitoring stack.

Spectre (192.168.1.189) is bare: base Ubuntu, 8 cores, 14 GB RAM
(6.4 GB available after Ollama holds ~8 GB resident despite receiving
zero traffic), no Docker, no `/home/www`. Ollama is **active** with
only `gemma4:e2b` (7.2 GB) on disk locally, plus `gemma4:31b-cloud`
and `gpt-oss:20b-cloud` shims — the resident ~8 GB is that one local
model. ffmpeg is **absent** — install before anything else. Python is
**3.14.4** (system).

### Decisions locked (2026-09-03 exchange)

| Question | Decision | Rationale |
|---|---|---|
| Audio path | **Option B1 — push-per-file rsync** | Failure domains stay separate. Today a synthesis failure is a Kokoro failure; Option A (NFS) folds mount unreachability, stale handles, and server-side hangs into the same code path — you'd be debugging "is this Kokoro or the mount" at 3am. B1 keeps "did rsync succeed for this file" as one boolean, surfaced as a Redis counter so a silently-stopped syncer is visible. Option A also puts nfsd on the box we're trying to relieve. |
| Python on spectre | **Install 3.12 alongside 3.14** | Kokoro + misaki + torch on 3.14 is untested here; the failure mode is subtle — it might import fine and produce audio with different characteristics. Not worth finding out. |
| Voice provisioning | **rsync the `.kokoro-venv/` from resolute wholesale; record sha256 of `af_heart.pt`** | If weights differ even slightly, `validate_native_format` starts skipping the af_heart directive the moment the first spectre file lands — silently, every show, no error. Reinstall-from-PyPI is the failure path here. |
| Cutover window | **Quiet overnight** | No reason to do it under any load. Peak-throttle window (14:00–19:00 weekdays) narrates once per 95 min, so overnight is not distinguishable from that in throughput anyway. |

### Phase 1 — the move

**Goal**: Kokoro synthesis executes on spectre; the finished mp3 lands
in `arc_stack/frontend/public/uploads/audio/` on resolute; newsradio's
`build_wiki_show.py` reads the same directory it does today, unchanged.

**Write-path facts** (from source read, not assumption):
`scribe.synthesize_article_audio` (`backend/scribe.py:665-748`) creates
`workdir = /tmp/arc-audio-{article_id[:12]}-XXXX`, invokes
`AUDIO_KOKORO_PYTHON` (hard-coded `/home/www/lecture_pipeline/.kokoro-venv/bin/python`
at `scribe.py:993`), Kokoro renders wav → ffmpeg encodes to 64 kbps
mono 24 kHz mp3 in workdir, then **`os.replace(temp_path, final_path)`**
at `scribe.py:741`. Same-filesystem atomic rename — that's what
protects newsradio's ffprobe from ever seeing a partial file today.

**Under B1, the invariant is preserved on both ends:**
- On spectre: `os.replace` is local (workdir in `/tmp`, `final_path` on
  `/var/lib/arc-audio/`, both on the same ext4 root). Atomic.
- Push-per-file: after `os.replace` succeeds, invoke rsync (over ssh,
  keyed) for that single file to resolute. rsync without `--inplace`
  writes `.<name>.XXXXXX` in the destination dir then renames — also
  atomic on the destination filesystem. newsradio ffprobes only the
  post-rename path.

**Pre-flight, all before wiring any daemon on spectre:**

1. Install Python 3.12 alongside 3.14 on spectre (`apt install
   python3.12` + venv path pinning); mirror the venv location so
   `AUDIO_KOKORO_PYTHON = "/home/www/lecture_pipeline/.kokoro-venv/bin/python"`
   resolves. Symlink the directory tree rather than editing scribe.py's
   hard-coded path.
2. rsync `/home/www/lecture_pipeline/.kokoro-venv/` from resolute to
   spectre wholesale. `sha256sum` every file in the voice weights
   (`af_heart`, whatever `.pt`/`.bin` files misaki 0.9.4 uses); store
   the reference file alongside so future drift is checkable.
3. Install ffmpeg on spectre matching the major version resolute has
   (`ffmpeg -version` on resolute first; libmp3lame framing at 64 kbps
   is inside newsradio's ±4 kbps validator tolerance but only if the
   encoder produces the same CBR structure).
4. Reach Redis from spectre. **Design changed 2026-09-03: use an SSH
   tunnel, not a LAN bind of Redis** — see the "Redis reachability —
   SSH tunnel" subsection below for the landed shape and why. Behavior
   remains: `arc:audio:active` mutex, `POLL_SECONDS = 30`,
   `redis_db = 0`, peak throttling — all host-agnostic by design and
   unchanged.
5. Stand up ssh key from spectre → resolute (arc-audio-syncer user,
   restricted to `rsync --server` in `authorized_keys` command=).

**Then a standalone measurement pass on spectre** — 5 known articles
of varying length pushed through the installed Kokoro without the
daemon in the loop. Record wall-clock, chars/s p50 and p95. Derive
`AUDIO_TIMEOUT_SECONDS = p95 × 1.5` (same safety multiple the current
600s implies against the 15 chars/s median observed on resolute). This
number **feeds Phase 2 directly**; do not skip it.

**Daemon wiring**: `audio_backfill.py`'s systemd unit moves to spectre;
resolute's copy is disabled. Add a Redis counter — call it
`arc:audio:sync_ok` / `arc:audio:sync_fail` — incremented from the
push-per-file wrapper so the corpus_exporter can chart it. A silent
syncer failure is the specific thing this counter exists to catch.

### Phase 1 measurement — 2026-09-03 (executed)

Standalone Kokoro on spectre against 5 pre-picked article bodies
spanning 400 → 10,993 chars. Provisioning was Python 3.12 (patch-level
3.12.14 vs resolute's 3.12.13 — pip-freeze-rehydrated via `uv`, all 91
packages including torch 2.13.0+cpu, kokoro/misaki 0.9.4 matching),
stock Ubuntu ffmpeg `8.0.1-3ubuntu2+esm1` with libmp3lame, and the
byte-identical HF Kokoro cache (af_heart.pt sha
`0ab5709b8ffab19bfd849cd11d98f75b60af7733253ad0d67b12382a102cb4ff`,
revision `f3ff3571791e39611d31c381e3a41a3af07b4987`).

**Wall-clock results:**

| Chars | Chunks | Wall (s) | chars/s | mp3 duration | bit_rate | valid |
|---:|---:|---:|---:|---:|---:|:---:|
| 400 | 1 | 17.5 | 23.1 | 27.25s | 64,214 | ✓ |
| 1,721 | 1 | 56.0 | 31.0 | 120.85s | 64,048 | ✓ |
| 5,036 | 2 | 151.7 | 33.5 | 339.27s | 64,017 | ✓ |
| 7,957 | 3 | 224.0 | 35.9 | 519.80s | 64,011 | ✓ |
| **10,993** | 4 | **331.0** | **33.6** | 785.35s | 64,006 | ✓ |

- **p50 wall = 151.7s, p95 wall = 331.0s**
- **p50 chars/s = 33.5** — **2.24× resolute's 15 chars/s median**
- **Derived AUDIO_TIMEOUT_SECONDS on spectre = p95 × 1.5 = 496s** (down
  from 600s used on resolute). For Phase 1's wrapper-style budget if we
  keep one; Phase 2 removes the wrapper.
- 5/5 mp3s pass `validate_native_format` (sample_rate 24000, channels 1,
  bitrate inside ±4 kbps of 64,000).

**Identity check — spectre-produced vs resolute-reference for
`0ae71d41ef63c0bc56eb816f20ac3ed9`** (Ross's step 4):

| | resolute | spectre |
|---|---:|---:|
| File size | 4,159,148 bytes | **4,159,148 bytes** |
| Duration | 519.800000s | **519.800000s** |
| PCM sample count @ 24 kHz | 12,475,200 | **12,475,200** |
| Overall RMS | −26.28 dBFS | **−26.28 dBFS** |
| 20 ms-window envelope Pearson r | — | **r = 0.999689** |

**PASS on every objective metric.** Same file size to the byte, same
PCM length to the sample, same overall energy to the hundredth of a
dB, same speech envelope to r ≈ 1. Fine-detail PCM diverges at
~17 dB SNR in speech and ~11 dB in silence — well below what "different
speech" would produce and consistent with torch CPU float-op drift
across microarchitectures (the SNR is high enough to rule out gross
divergence and low enough that a pure encoder-quantization difference
alone probably wouldn't explain it). Ross's subjective listen accepted
the result — **option A (stock Ubuntu ffmpeg) is confirmed; the
ffmpeg-source-build question is closed.**

**The 10,993-char article is the Phase 2 proof-of-concept.** On
resolute today (`AUDIO_TIMEOUT_SECONDS × 15 chars/s = 9,000` ceiling)
it would be poison-pilled and never narrated. On spectre it ran in
331s wall, 33.6 chars/s, 4 chunks through the existing sentence
splitter, produced 785 s (~13 min) of valid af_heart audio. The
synthesis path already handles it end-to-end; Phase 2's remaining work
is the per-chunk timeout accounting and Redis chunk-state resume, not
new synthesis code.

### Redis reachability — SSH tunnel (landed 2026-09-03)

**Design change from the original plan.** The Phase 1 pre-flight
called for binding resolute's Redis to the LAN interface so spectre
could reach it directly. Recon killed that plan:

- `ufw status` on resolute returned `inactive` — no host firewall at
  all. A LAN bind would put Redis on `192.168.1.0/24` behind only the
  40-char `requirepass`, with nothing else in front of it.
- Redis is currently correctly configured: `bind 127.0.0.1 -::1`,
  `protected-mode yes`, `requirepass` set. That posture is worth
  preserving, not loosening.
- A LAN bind means restarting a Redis that Arc, Hunt, DLB, SoC and
  plants all depend on, in the same window that the audio-tunnel goes
  live — coupling two unrelated blast radii for no gain.

**Landed shape.** An SSH tunnel from spectre forwards its own
`127.0.0.1:6379` to resolute's loopback Redis. `audio_backfill.py`
needs zero config change — it connects to `127.0.0.1:6379` exactly as
it does today, on whichever host it runs. Redis on resolute stays
bound to loopback only.

**Dedicated key** (not ross's general SSH key):
`~/.ssh/arc_redis_tunnel_ed25519` on spectre, mode 600. Pubkey
comment `arc-redis-tunnel@spectre`.

**Restricted `authorized_keys` entry on resolute** (`/home/ross/.ssh/authorized_keys`):
```
restrict,port-forwarding,permitopen="127.0.0.1:6379",command="/bin/false" ssh-ed25519 <pubkey> arc-redis-tunnel@spectre
```
`restrict` disables everything by default (no pty, no shell, no
agent-fwd, no X11-fwd, no user-rc); `port-forwarding` re-enables that
one class; `permitopen="127.0.0.1:6379"` locks the forward target so
sshd refuses any other `-L`; `command="/bin/false"` is
belt-and-suspenders if `restrict` is ever relaxed.

**Systemd user unit on spectre**, `~/.config/systemd/user/arc-redis-tunnel.service`:

```
[Unit]
Description=Arc Redis tunnel — spectre 127.0.0.1:6379 → resolute 127.0.0.1:6379 (ssh, dedicated key)
Documentation=file:///home/www/arc_stack/TODO.md
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
ExecStart=/usr/bin/ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=accept-new \
  -i %h/.ssh/arc_redis_tunnel_ed25519 \
  -L 127.0.0.1:6379:127.0.0.1:6379 \
  ross@192.168.1.198
Restart=always
RestartSec=5s
RestartMaxDelaySec=60s
RestartSteps=5

[Install]
WantedBy=default.target
```

Notes on the choices:
- `Type=exec` is stricter than `simple` — systemd waits for successful
  `exec()` before marking active, catching a broken keypath faster.
- `ExitOnForwardFailure=yes` means a failed port bind on spectre exits
  ssh and lets systemd restart it, rather than silently running with
  no tunnel. This is the specific case the option exists for.
- `ServerAliveInterval=30`, `ServerAliveCountMax=3` — a dead tunnel
  is detected within ~90 s and the service restarts.
- No `autossh` — not installed on spectre; plain `ssh + Restart=always`
  covers the same ground with one fewer dependency.
- Backoff spikes to 60 s (`RestartMaxDelaySec=60s`, `RestartSteps=5`)
  so a persistent outage doesn't hammer resolute.
- `WantedBy=default.target` — user-session equivalent of
  `multi-user.target` for system units.

**Linger** was already enabled on spectre (`loginctl show-user ross`
reported `Linger=yes`), so the user's systemd survives across reboot
and starts the tunnel without a login session. Explicitly named here
because that's the specific thing that makes user units come back at
boot — noted so no one wonders later why this "just worked."

**Verification, both pre- and post-reboot**:

| | pre-reboot | post-reboot (fresh boot 2026-09-03 06:29 MDT) |
|---|---|---|
| `systemctl --user is-enabled arc-redis-tunnel.service` | `enabled` | **`enabled`** |
| `systemctl --user is-active arc-redis-tunnel.service` | `active` | **`active`** |
| `NRestarts` | 0 | **0** |
| Listening on `127.0.0.1:6379` on spectre | ✓ | ✓ |
| RESP `AUTH` reply | `+OK` | `+OK` |
| RESP `PING` reply | `+PONG` | `+PONG` |
| DBSIZE arc (db 0) | 54,243 | (same value) |
| DBSIZE hunt (db 1) | 23,002 | (same value) |

The `enabled` (not `linked`) result is the specific state
[[ops/REBOOT.md]] flagged for `school-of-chat-directory.service` — a
`linked` unit doesn't auto-start at boot even though it looks fine to
`systemctl status`. This one is genuinely `enabled` and proven so by
the fresh boot's `NRestarts=0` + auto-start.

**What `audio_backfill.py` doesn't need to change**: nothing. Its
`redis.Redis(host="127.0.0.1", port=6379, ...)` call works identically
on either host through the tunnel. Same mutex key
(`arc:audio:active`), same DB (`redis_db=0`), same poll cadence — the
daemon is host-agnostic exactly as designed.

### Phase 2 — chunked synthesis, remove the 9,000-char ceiling

**Reframe from the original spec, based on source read**: scribe.py
**already** sentence-chunks Kokoro calls at `AUDIO_MAX_CHARS = 3500`
(`scribe.py:637-654`). The 9,000-char article ceiling is not a Kokoro
request-size limit — it's a **wrapper wall-clock budget**:
`AUDIO_TIMEOUT_SECONDS = 600` × 15 chars/s = 9,000. Kokoro is called
with chunks; the timeout bounds the sum.

So Phase 2 is smaller than it sounded. The chunking primitive exists.
What's missing:

1. **Per-chunk timeout accounting** — each Kokoro invocation gets its
   own `per_chunk_timeout`. **Decided from the Phase 1 measurement:
   200s per chunk.** A max-size 3,500-char chunk runs ~104 s at
   spectre's observed 33.5 chars/s p50, so 200 s is ~2× cushion. The
   timeout exists to catch a hung Kokoro process, not to accommodate
   slow-but-working synthesis — that's what the cushion sizes for. The
   article no longer has a whole-of-corpus timeout; the poison-pill
   guard becomes per-chunk. A single chunk that estimates over its own
   budget is still unrecoverable — the guard doesn't go away, its
   scope narrows.
2. **Chunk persistence + resume** — a failure on chunk 7 of 12 must
   not discard chunks 1–6. Persist chunk state in Redis:
   `arc:audio:chunks:{article_id}` HASH storing `chunk_idx →
   {path, sha256, chars, wall_s}`. On resume, skip completed chunks
   and pick up at the first missing index. Redis (not disk) because it
   composes with the existing mutex and survives a spectre reboot
   without a boot-time cleanup pass.
3. **Concat step** — use `build_wiki_show.py`'s pattern verbatim
   (`build_wiki_show.py:870` `write_concat_file` + the `ffmpeg -c copy`
   invocation at ~line 950). All chunks are same-codec/rate/channels/
   bitrate by construction, so it's a bit-identical stream copy — no
   re-encode, orders of magnitude faster than lame'ing again, and
   `validate_native_format` continues to pass.
4. **Final atomic rename** unchanged: concat lands in workdir, then
   `os.replace` to `final_local`, then push-per-file rsync to resolute
   as in Phase 1.

**Per-chunk budget was derived on spectre, not resolute.** The whole
reason Phase 1 came first was so Phase 2's numbers wouldn't be fitted
to a machine they won't run on — done, the 200 s figure above is the
result.

#### 2026-09-03 addendum — live data recalibrates per-chunk budget

Phase 1's 200 s came from p50 wall 33.5 chars/s across 5 pre-picked
articles. First pass after the 11004-char raise (see arc.cfg [audio]
2026-09-03 comment) gave 8 live completions with a much slower spread:

| stat | wall chars/s |
|---|---|
| min | 16.72 |
| median | 22.36 |
| max | 23.30 |
| p95-ish (n=8) | ~23.2 |

Plus one timeout at ≤ 16.56 chars/s wall (`656c30ce3e35`, 9940c hit
600.4s and returned None — the exact per-article poison-pill guard
scenario, reintroduced in a narrower band as the accepted cost of
raising the budget). The Phase 1 numbers were optimistic: live
traffic runs ~1.5× slower.

**Recalibrate per-chunk budget from live data**: 3500-char chunk at
the low tail (17 chars/s) needs ~206 s — the Phase 1 200 s figure is
UNDER the low tail. Recommend **per_chunk_timeout_s = 300** (≈1.5×
worst-observed chunk, ≈2× the low-tail estimate; catches a stalled
Kokoro cleanly but doesn't false-positive on a slow-but-live chunk).
That's the number to design Phase 2 against.

#### 2026-09-03 addendum — enforcement mechanic decision

The Phase 2 spec above leaves open HOW the per-chunk timeout is
enforced against the current one-subprocess-per-article model
(`scribe.py:573-579` docstring: "importing torch and loading the
pipeline costs ~5s, and that is per-process, not per-chunk").
Options considered:

| Option | Mechanic | Startup cost | Complexity |
|---|---|---|---|
| **A** subprocess-per-chunk | parent loops, one `subprocess.run(synth.py, timeout=300)` per chunk, Redis committed between calls | ~5s × N chunks (30-chunk poison-pill ≈ 150 s = 5% overhead) | low; chunk-resume-across-restart is natural |
| B one subprocess, parent watches PROGRESS on stderr via Popen, kills child if a chunk stalls | ~5s / article | custom parent/child protocol; kill-mid-chunk partial WAV handling; no cross-restart resume |
| C child self-enforces per-chunk deadline via signal.alarm | ~5s / article | signals + torch is fragile (CUDA/MPS ops don't interrupt cleanly) |

**Choose A.** The 5% startup overhead buys durable chunk-resume
(parent's Redis commit after each `subprocess.run` returns IS the
checkpoint — a daemon crash mid-article resumes at chunk N+1 next
pass) and a small failure surface (each subprocess writes one chunk
WAV; on TimeoutExpired the parent kills, marks the chunk failed in
Redis, moves on). Modify `_KOKORO_SYNTH` to take a `chunk_idx` argv
and write `chunk_{idx}.wav` instead of `article.wav`; parent
orchestrates and concats via `build_wiki_show.py`'s ffmpeg `-c copy`
pattern. Concurrency invariant preserved: exactly one Kokoro
subprocess at any moment, still guarded by `arc:audio:active`.

**Overall safety net**: no article-level timeout. Worst case is a
truly pathological article where every chunk stalls to the 300s
budget: 100k chars / 3500 = 29 chunks × 300s ≈ 145 min. Finite,
per-chunk-abortable, and burns less than one full daemon-restart-loop
of 600s all-or-nothing before returning something usable.

**Ship behind an off switch** (`arc.cfg [audio] per_chunk_synthesis =
true`) for one release so we can revert to the current per-article
model if Phase 2 misbehaves overnight — the spectre cutover set the
bar for cautious rollout and Phase 2 deserves the same posture.

### Phase 3 — backlog reindex (promoted from parenthetical)

**Ross's addition, and the one that turns Phase 2 from "future coverage"
into "actual coverage gain."** ~21% of articles were skipped by the
9,000-char threshold. After Phase 2 ships, chunking removes that
gate — but a new article > 9,000 chars is the only case that benefits
automatically. Existing skipped articles stay silent forever unless
something scans them.

**Concrete because there is no cache to invalidate.** Verified by
source and Redis scan (2026-09-03): the poison-pill exclusion is
applied at query time in `find_newest_silent(..., max_chars)`
(`audio_backfill.py:440`), and `failed_this_run` is a process-local set
that resets on each `run()`. Redis has **no** `audio:skip:*` /
`audio:poison:*` keys — the SCAN came back empty. So "reindex" here is
not a cache clear.

**The real gate is `backfill_window_hours = 2` (ceiling 6h).** The
daemon deliberately narrates breaking news, not history — see the long
comment at `arc.cfg:222`. Anything skipped a week ago is out-of-window
forever from the daemon's perspective, even after Phase 2 makes it
technically eligible.

**What Phase 3 actually is**: a one-shot backlog script — call it
`scripts/audio_backfill_history.py` — that scans the full feed ZSET
(not just the trailing window), filters `audio_url` unset AND
`len(body) > 9000`, and enqueues them through the same
Phase-2-hardened `synthesize_article_audio` path, respecting the
mutex, off-peak only. Idempotent (re-runs skip already-narrated
articles). Rate-limited to not swamp the newly-relieved spectre.

Deliberately a **separate script from the daemon**, not a config
knob — the trailing-window discipline is a live design constraint and
we don't want a wide `backfill_window_hours` to accidentally reactivate
the old batch-backfill pattern the 2026-08-27 redesign replaced (that
concern is already documented in `arc.cfg`'s ceiling clamp).

**This is the payoff.** Chunking without Phase 3 ships a capability
change with no coverage change; Phase 3 without chunking can't run
because those articles hit the same 9,000-char wall. They're a pair.

### Sequencing

1. Redo the ollama-url benchmark from a moment the M1 is known-healthy
   (see "Deferred" below). Result gates nothing in Phase 1, but the
   memory-conflict finding may reshape Phase 1's headroom math.
2. ~~Phase 1 pre-flight (Python 3.12, venv rebuild w/ sha256, ffmpeg,
   Redis reachability, standalone Kokoro measurement of 5 articles →
   `AUDIO_TIMEOUT_SECONDS`).~~ **Done 2026-09-03** — Python 3.12.14 +
   ffmpeg 8.0.1 installed; venv rebuilt from pins with `uv` (rsync was
   inert because spectre's stock Python is 3.14 and the venv's
   interpreter path was dead); HF cache rsynced and af_heart sha
   verified. Redis reachability landed via **SSH tunnel** rather than
   the originally-planned LAN bind — see the dedicated subsection
   above; systemd user unit is `enabled` and reboot-survival proven.
   Measurement results in the "Phase 1 measurement" subsection above.
3. Phase 1 cutover, quiet overnight. Disable resolute's
   audio-backfill.service; enable spectre's. `arc:audio:sync_ok`
   counter live. (Redis path is already in place via the tunnel — no
   longer a blocker for this step.)
4. Phase 1 burn-in: one full peak-window weekday, current 9,000-char
   threshold still in place. Confirm zero validator skips on the
   af_heart directive, zero sync counter divergence.
5. Phase 2 build: per-chunk timeout, Redis-persisted chunk state,
   ffmpeg `-c copy` concat mirroring `build_wiki_show.py`. Per-chunk
   budget derived from Phase 1's measured cps.
6. Phase 2 cutover, quiet overnight. `AUDIO_TIMEOUT_SECONDS` becomes
   per-chunk; article-level threshold removed.
7. Phase 3: run `audio_backfill_history.py` off-peak, watch it drain
   through the ~21% backlog over however many days the mutex + rate
   limit dictates. This is the visible coverage improvement.

### Deferred: Ollama bench + memory conflict, tracked separately

Not blocking any of the above. Attempted 2026-09-03: both hosts hung
past 60s and 120s respectively on a `gemma4:e2b` `POST /api/generate`.
The M1 side is consistent with historical daemon flakiness
([[m1-filevault-two-tier-gate]] and TODO.md's "M1 Ollama daemon down"
entry). Redo when M1 is confirmed responsive:

```bash
for host in 192.168.1.185 192.168.1.189; do
  curl -sS -m 30 "http://$host:11434/api/generate" \
    -d '{"model":"gemma4:e2b","prompt":"hi","stream":false,"options":{"num_predict":1}}' >/dev/null
done
# then bench at num_predict=200 and read eval_count / eval_duration
```

**Memory arithmetic, corrected 2026-09-03**: spectre has 14.9 GB total,
6.4 GB available at scoping. `gemma4:e4b` (9.6 GB) was on the initial
`ollama list` output but Ross has since deleted it — **it is not
present on spectre**. The only local model is `gemma4:e2b` (7.2 GB);
the `31b-cloud` and `gpt-oss:20b-cloud` entries are cloud shims that
consume no local RAM. Ollama's current ~8 GB resident is `e2b` fully
loaded. Kokoro adds ~2.2 GB RSS.

So if `ollama_url` gets pointed at spectre: local Ollama traffic
lands on the already-resident `e2b` (no new memory pressure), cloud
traffic goes upstream (no local memory), Kokoro's 2.2 GB fits in the
remaining ~6.4 GB with room. Redirecting `ollama_url` looks
**memory-safe** under the corrected inventory — very different from
the reading I filed the first time. Still worth benching for the
tokens/sec question, but not blocked on memory sizing.

Do the bench and the redirect decision **before Phase 1 is finalized**
only if we're seriously considering pointing `ollama_url` at spectre;
otherwise it's parallel work with its own timeline.

### Requirepass rotation — deferred maintenance (flagged 2026-09-03)

**Trigger**: during the tunnel-build session, the 40-char Redis
`requirepass` was in this shell's environment while I ran RESP-protocol
tests and earlier recon. Concretely: expanded into subprocess argv
(momentarily visible in `ps` on both hosts), written into `bash -c`
strings ssh'd to spectre, and present in this session's context on
Anthropic's side. It was **not** printed to any tool output visible to
the user, and the committed TODO/commits carry only `$REDIS_PASSWORD`
references — never the value. But the exposure surface widened, and
Ross called the rotation. Recording it here.

**Rotation is a coordinated change, not a snap decision**:

1. Pick a new 40-char secret (openssl rand -base64 32 | tr -d '=+/' | cut -c1-40).
2. Update `.env` in every stack that connects — arc_stack,
   huntaegis_stack, deliberation_stack, primer_academy_directory
   (SoC), claude_stack (plants). Grep for `REDIS_PASSWORD=` to catch
   any I miss.
3. Update `/etc/redis/redis.conf`'s `requirepass` line (needs root)
   and `systemctl restart redis-server`.
4. Roll every daemon in every stack (each `./<stack>.sh restart`, or
   individual services). Watchdogs will bounce cleanly; manual
   restarts are safer for the sequencing.
5. Re-run the tunnel PING check (`AUTH` reply should be `+OK` with
   the new secret).
6. Sanity-check each stack's checkup endpoint is green afterward.

**Scope note**: this touches every stack on the box. Do it in a real
window, not as a side effect of another change. Independent of any
Phase 1/2/3 work above.

### Future optimization — startup-cost amortization (not for Phase 1/2/3)

Phase 1's measurement surfaced a scaling pattern worth recording,
though nothing here changes on the current path:

| Article chars | chars/s |
|---:|---:|
| 400 | 23.1 |
| 1,721 | 31.0 |
| 5,036 | 33.5 |
| 7,957 | 35.9 |
| 10,993 | 33.6 |

The rate climbs sharply from ~23 → ~34 chars/s over the first
~2,000 chars and then flattens. That shape is fixed per-invocation
startup cost — model load, spaCy init, `KPipeline` construction —
amortizing over longer text. Short articles pay disproportionately
because startup is spent again for every one of them.

**Recover it with a persistent worker** rather than per-article
process spawn: instead of `subprocess.run([AUDIO_KOKORO_PYTHON,
"synth.py", ...])` per article, keep one long-lived Kokoro process
around and feed it chunks over a pipe. Bench math against Phase 1
numbers: if the amortized ceiling is ~35 chars/s and the amortized
floor (long articles only) is ~34 chars/s, then a persistent worker
would move the ~1,700-char article from ~55 s wall to ~50 s and the
~400-char article from ~17 s to closer to ~12 s. Modest gains for a
non-trivial rewrite of `scribe.synthesize_article_audio`'s subprocess
model. **Not for now** — worth revisiting only if the daemon's
throughput becomes a real ceiling, which it isn't at spectre's ~2×
resolute rate.

## Ollama Cloud billing went monthly — escalation.py's weekly counter is now the wrong window (observation only, 2026-09-10)

`escalation.py`'s `weekly_cap` gate (`arc_config.yaml [escalation]`,
live value 1500, HEAD value 400) keys its Redis counter to the ISO
week (`arc:cloud_calls:weekly:{isoyear}-W{isoweek}`, 8-day TTL,
self-rolling every Monday). Ollama Cloud switched from a weekly
allowance to monthly included usage — a single cumulative pool with
a ~4-week reset, not a per-week one. A counter that resets every
Monday regardless of month-to-date usage can't back-stop a monthly
pool at any value: up to four full weekly allowances can be spent
before the real ceiling is ever consulted. `weekly_cap` is decorative
until the accounting window itself changes from ISO-week to
whatever Ollama's actual cycle is.

**Data point, recorded before it's lost**: 2026-09-10 — 9.5% of the
monthly pool used, 264 requests so far this month, dashboard reads
"resets in 3 weeks," credit balance $0 (no funded overage once the
pool is exhausted — Ollama's own 429 is still the hard stop beneath
this gate, per the existing weekly_cap comment, that part is
unaffected). Implied full-month pool ≈ 264 / 0.095 ≈ 2,780 requests.

**Why this isn't fixed yet**: the right fix (key the counter to the
real billing cycle instead of the calendar) depends on one fact this
single data point can't establish — whether the reset is calendar-
month-anchored (same day each month, so `relativedelta(months=+1)`
from a confirmed anchor date is correct) or a flat rolling window
(fixed N days after the last reset, so `timedelta(days=N)` is
correct instead). "9.5% used, 3 weeks to reset" is consistent with
either model this early in one cycle.

**Next step**: check ollama.com/settings the day this cycle actually
flips to 0%. The exact reset date (does it land on the same day-of-
month as whatever day the 9.5%-used reading above corresponds to, or
land some fixed number of days later regardless of month length)
tells you which model it is — the fix is a one-line change either
way once known: swap `_weekly_key()`'s `isocalendar()` derivation for
a `_cycle_key()` anchored to that reset date, using whichever of the
two step functions the observation confirms. `python-dateutil` is
already a pinned dependency (`requirements.txt`) for the
`relativedelta` case. Not touching `weekly_cap` or the counter until
then — implementing either step function now would be guessing.

## Cleanup, not urgent — vestigial Arc files sitting in huntaegis_stack

Found while sweeping both stacks for the 5005/5006 port-default bug
(2026-09-10 — see the three port-default commits on huntaegis_stack's
`fix/translate-failure-visibility` branch, same session). Three
leftover copies of Arc's own files never adapted when Huntaegis was
forked, all inert (nothing depends on their wrong values) but all
confusing to a future reader:

- `huntaegis_stack/arc_config.yaml` — a stale copy of Arc's own
  config (`stack.root: "/home/www/arc_stack"`, `stack.backend_port:
  5005`), undated since 2026-07-15 (predates Arc's own 07-18
  retention-hours change, so it's drifted from Arc's copy too).
  `mailer.py` reads only its `mailer:` sub-block, which is correct
  and unaffected — the wrong `stack:` block is never read by
  anything, confirmed by grep.
- `huntaegis_stack/backend/project_context.yaml` — same situation,
  a full stale copy of Arc's project doc (still describing Arc's
  Caddy config, Arc's port 5005 throughout). Referenced only in a
  comment at the top of Hunt's `scribe.py`; never actually loaded by
  any code (no `open()`/`yaml.safe_load` against it anywhere) — dead
  weight. Hunt has its own accurate `huntaegis_project_context.yaml`
  alongside it, which is presumably what's meant to be read instead.
- `huntaegis_stack/frontend/app/about/developer/page.tsx` — four
  `5005` mentions (lines 187, 233, 266, 271) in the public
  about/developer page's display text, describing Hunt's own backend
  port incorrectly to visitors. Cosmetic (UI copy, not networking
  code) but visibly wrong to anyone who opens that page and knows
  the real port is 5006.

Worth a cleanup pass — delete or properly re-scope the two stale
YAML copies, fix the four display strings — but nothing here is
live-wrong the way the port defaults were, so it can wait.

## Session handoff — 2026-09-10, resume here

Ran out of session budget mid-thread. Nothing left running, nothing
pushed. State and resume sequence below.

**Spectre's 6h-window first pass FINISHED this session** — don't
re-derive "still running" from an earlier estimate in this file's own
history if one exists above. Final: 13 narrated, 6 permanently
skipped (poison-pill, over the 11,004-char budget), window reported
idle at 11:30:24. Took ~36 minutes end to end, faster than the
mid-run estimate suggested — nothing wrong, the early estimate of
candidate count was just loose.

**Resume sequence, in order:**
1. `git push` resolute's `arc_stack` `main` (7 commits ahead of
   `origin/main`, all individually secret-audited clean today —
   the original 6 plus `dad74a2`, audited the same way, also clean).
2. On spectre: `git pull` (`arc_stack` clone at `backend/`'s parent)
   to bring it from `0088c86` to HEAD — this is what actually lands
   `cbe904b`'s TTL lease fix, which spectre has NOT been running
   yet despite being the host that's actually narrating.
3. Restart `arc-audio-backfill.service` (user unit, `systemctl --user
   restart`) on spectre to pick up the pull — config/code is only
   read at process start, not live-reloaded.
4. Watch the first hour after, three things:
   - `grep '📻'` in the journal — broadcast-script rejection rate.
     Healthy is occasional, not a wall of them (see `b0aae68`'s own
     commit data: 71% before its retune).
   - `LLEN analyzer:queue` on Redis — currently 0 (single-consumer
     analyzer keeping up). A growing, non-draining number means the
     new eager-enqueue from narration is outpacing the analyzer.
   - Wall time on the `✓` log lines against **this morning's
     baseline: 149s median / 166s mean** (n=579, measured before the
     pull, on raw article text up to 11,004 chars). Post-pull,
     narration synthesizes from ~1,100–1,400-char generated scripts
     instead — wall time should drop substantially. **This number is
     the actual decision point for whether warden as a second Kokoro
     worker is still worth building** — if narration is already fast
     post-pull, the throughput case for a second worker weakens; if
     it isn't, the case holds.

**Other things worth knowing, not yet acted on:**

- The 6h window is live on **spectre only** — spectre's own copy of
  `arc_stack/arc.cfg`, `backfill_window_hours: 2 → 6`, an uncommitted
  local edit on that host. Resolute's own `arc_stack/arc.cfg` still
  says `2` and
  separately carries its own unrelated local edits (`[ingestion]`
  `cycle_minutes`/`sources_per_sweep` — Ross's operator-owned live
  tuning, per this repo's CLAUDE.md; do not touch or "fix" those).
  These are two different hosts' copies of the same filename, not
  one shared file drifting — don't try to reconcile them into one.
- The poison-pill count grew 4 → 6 as the window reached further
  back mid-pass (up to 33,551 chars). Those specific articles are
  permanently silent under the *current* 11,004-char budget — but
  worth knowing that budget stops mattering at all once spectre
  pulls: `d8875c5` generates narration from Red/Blue/Purple analysis
  (a ~1,100–1,400-char broadcast script), never from raw article
  text, so source-article length stops gating narration entirely
  post-pull. The 6 skipped-today articles aren't necessarily doomed
  — they'd need to re-enter the window while still within whatever
  `backfill_window_hours` is active, but length itself won't be why
  they fail once the pull lands.
- Ollama Cloud billing observation is already recorded above (see
  "Ollama Cloud billing went monthly" section, same date) — 9.5%
  used, 264 requests, "resets in 3 weeks," $0 balance. Check the
  dashboard the day it flips; that's what the escalation-counter
  redesign is waiting on, not touched this session.
- Warden-as-second-Kokoro-worker design (reported, not built): the
  `cbe904b` TTL lease gives cross-host **safety** (never two
  synthesis subprocesses on the same article), not **parallelism** —
  it's one global key, one holder, anywhere. Real throughput needs
  two things together: worker-scoped lease keys (`arc:audio:active:
  {worker_id}`, trivial — reuses the proven lease code verbatim, just
  parameterized) and a per-article claim (`arc:audio:claimed:
  {article_id}`) that's atomic *with selection itself*, not a
  check-then-set after `find_newest_silent` returns — otherwise two
  workers converge on the same newest candidate every ~30s poll.
  Warden itself is still bare (no `/home/www`, no `uv`) and was mid
  kernel-compile as of this session's end — leave it alone until
  told otherwise, and don't start on this build until the wall-time
  number above says it's still worth it.

**UPDATE, same session, after the pass drained: push and pull both
done.** `origin/main` is at `fa26b40`. Spectre is pulled to the same
commit and running it — restart sequence above is complete, not
still pending. One real snag along the way, now fixed: spectre's
`arc_stack` checkout was on a stray branch (`fix/translate-failure-
visibility`, zero divergence from main, just never switched back —
apparently from whenever the clone was first set up) rather than
`main`; local `main` there was separately 93 commits stale (old,
unrelated to today). Fixed by checking out `main`, fast-forwarding,
and re-applying the local `backfill_window_hours=6` edit via
stash/pop — clean, no conflicts, verified intact after. Spectre now
correctly tracks `main` going forward.

**What's still open: the actual watch-list numbers.** 20 minutes
post-restart, the window stayed idle the whole time — no new
article went silent, so there's been no narration yet under the new
code. `analyzer:queue` LLEN is still 0 (consistent — nothing to
enqueue if nothing's narrating). No `📻` lines either way. This isn't
a problem, just quiet traffic; the daemon is confirmed running
correctly (dry-run + restart + idle-polling all verified). **Next
session: just check the journal for the first `✓` lines and compare
wall time to the 149s median / 166s mean baseline** — that's the
only thing this handoff still owes you.

---

## Session ending 2026-09-10 — IntelligenceCard wish list + today's landed items

Recorded verbatim from Ross at session end (CC restart for an update); nothing
in this section was independently verified by the session that wrote it down.

**Done today, committed — verify before relying on them:** prefs-not-loaded
race fix, `source_lang` captured at ingest on both stacks (Arc + Hunt),
inline audio with one-player-at-a-time, a memo comparator comment.

**IntelligenceCard wish list — none of the four below started:**

1. **Rename the two score components.** Currently "objectivity" and a
   college/reading-level label → should be "objectivity" and "difficulty".
   Do this in the same pass as reconciling a real inconsistency: Arc's
   scoring page and support page describe the same scale differently —
   support lists ten bands, the scoring UI shows five. Fixing the label
   without reconciling band count leaves three descriptions of one metric
   instead of two.
2. **Auto-translate non-English articles to English at ingest**, rather than
   on demand as today. ~6% of the corpus, so volume is manageable. Narration
   should key off the translated text once this lands — touches the audio
   pass too, not just ingest.
3. **A watch control next to the headphones control** — same expand-in-place
   pattern — launching a viewer for an mp4 built from the reporter's profile
   images plus the existing narration audio. Generate lazily on first watch,
   not for every article. Note: `card.origin === 'video'` is already a
   separate early-return branch in `IntelligenceCard.tsx` — do not conflate
   this new control with that existing path.
4. **Desktop left-nav restructure**: home, audio, video, publish, search,
   more — with wiki, library, and sources moved under "more". Blocked on one
   decision: what "audio" points at — `newsradio.arc-codex.com`, or a new
   in-Arc page listing narrated articles. Don't start building until that's
   settled.

---

## Session 2026-09-11 — narration wall-time regression, JIM_TAILSCALE_IP,
## broadcast-script rejection rate, narration-liveness monitoring

**Correction to this session's own early read**: a narration gap was first
reported as ~19h (newest mp3 read as 13:44 the previous day). That was a
misread of `ls` output — the actual newest file at the time was 01:12 the
same morning, a 4h45m gap, not 19h. Nothing was down for 19 hours; the
daemon, its Redis mutex (`arc:audio:active`), and the spectre-resolute
Redis tunnel were all confirmed healthy throughout the real 4h45m gap too
— it was an unlucky streak of the rejection-rate issue below (4 losses in
a row at an 81% base rate is a ~43% probability event), not a fault.

**`JIM_TAILSCALE_IP` was live in production, unconditionally, on spectre.**
`ollama_client.py`'s `DEFAULT_PRIMARY` is a literal placeholder string —
resolute's own `.env` overrides it (`OLLAMA_PRIMARY`/`OLLAMA_FALLBACK` both
pinned to the M1), but spectre's minimal `.env` never got the same fix, so
every `audio_backfill.py` → `scribe.run_broadcast_script` call paid a
connect-timeout tax against a hostname that was never going to resolve
before falling back to the M1. Fixed: spectre's `.env` now sets
`OLLAMA_PRIMARY` the same as resolute's. This plus the M1 already carrying
100% of the analyzer/character_builder/narration load together explain
part of why wall time didn't drop the way the scribe→broadcast-script pull
predicted — the new LLM round-trip the pull introduced (script-writing)
was paying this tax on every call, on top of ordinary M1 load variance.

**Broadcast-script rejection rate was measured at 81% (30/37), and the
model was found to be ignoring the length instruction, not merely
missing it.** 37 real attempts ranged 776-4048 chars (median 1682, mean
1871) against a 1,100-char target — a smooth, wide distribution with no
visible pull toward 1,100 at all, which is why the 2500→1400 retune made
the reject rate worse rather than better: nothing about generation itself
changed, only where the post-hoc cutoff fell across an unmoved
distribution. Root cause: `_apply_spec_following_options` sets
`num_predict=-1` (unbounded) for every gemma4-family call, so the
character-count instruction in `prompts.yaml` was a request the model was
free to ignore — nothing in decoding was ever enforcing it.

Fix landed (`b2df679`): `run_broadcast_script` now caps generation at 300
tokens (`BROADCAST_NUM_PREDICT`, scoped to this one call — no other
`call_ollama_local_only` caller is affected). Measured against 3 real
articles at 250/300/350 tokens before choosing 300: it's the only value
where all three landed under 1400 chars, and two of three finished
naturally (`done_reason=stop`) before ever hitting the cap, with complete
sentences. The third — dense, list-heavy biographical content — hit the
cap mid-sentence at every value tested, 250 included; that one's a
content-shape problem no single token value fully solves.
`BROADCAST_MAX_CHARS` stays as a backstop reject — the cap reduces
overshoots, it doesn't guarantee zero.

**Considered and rejected: routing this call to warden + `qwen2.5:1.5b`
instead of the M1 + `gemma4:e2b`.** Memory-wise it's the right fit (warden
can't honestly run `gemma4:e2b`, `qwen2.5:1.5b` is what Huntaegis' analyzer
already proves works there). But measured against real content — 11
generations, both `/api/generate` and `/api/chat` with a proper
system/user split, every num_predict value tried — `qwen2.5:1.5b`
reproduces the "RED TEAM FINDINGS" section labels as literal markdown
headers and restates the source as bullet points, never rewriting into
continuous narrated prose, on every single attempt. `gemma4:e2b`'s
problem was purely length; trading it for a model with a format problem
instead is a worse trade at any cap value. Reverted: spectre's `.env` no
longer sets `BROADCAST_OLLAMA_HOST`/`BROADCAST_OLLAMA_MODEL` (config only
— never committed to this repo), and `spectre-rebuild`'s warden ufw
allowlist change for spectre was reverted too (`fd3aa6b`, that repo). The
host/model override mechanism itself stays in `ollama_utils.py` — it's
inert when unset and is exactly what a future retry would need, whichever
model that ends up being.

**New: `mailer.py` narration-liveness monitoring (`802fe9a`)** — output-
arriving, not process-alive, specifically because this incident's shape
(daemon/mutex/tunnel all healthy, zero output) is invisible to
`watchdog.sh` by design. `audio_backfill.py` now sets
`arc:audio:last_narration` on every success; `mailer.py` alerts when its
age exceeds 3× `cycle_minutes` (2h floor, 8h ceiling — 4.85h at today's
97-minute cycle). Opt-in via `arc.cfg`'s `narration_liveness_enabled`
since Huntaegis shares this file but has no narrator at all. Not yet
observed firing or clearing in production — first real test is whenever
narration next actually stalls past the threshold.

**M1 memory — chased to ground, no changes made (Ross's instruction: land
and document, no changes to the M1 this session).** Early in this session
an 89%/7.3GB swap reading was reported as if steady-state; it wasn't — the
M1 rebooted between that check and a later one, and swap resets to 0 on
boot. Corrected, then chased further:

- **`OLLAMA_KEEP_ALIVE=-1` confirmed**, via `/Library/LaunchDaemons/
  com.arc.ollama.plist` (mtime 2026-08-19 19:50, matching `ops/RUNBOOK.md`'s
  own dated entry). `/api/ps`'s `expires_at` in the year 2318 is that
  setting's documented behavioral signature (RUNBOOK says so itself,
  2026-08-19 entry) — confirmed, not inferred.
- **The 2026-08-20 incident this pin caused is real and is closed, twice
  over**: `ops/RUNBOOK.md` records 63% coverage collapsing to 4% (67
  resident-defers vs 3 narrations) because `scribe.py:kokoro_preflight`
  used to refuse whenever `/api/ps` showed any resident model. Fixed
  same-day: preflight now checks `psutil.virtual_memory().available`
  instead — confirmed still the live code today, no residency check
  anywhere in `kokoro_preflight()`. Separately, Kokoro itself no longer
  runs on the M1 at all (moved to resolute that same 2026-08-20, then to
  spectre since) — the preflight this pin used to break doesn't even touch
  the M1 anymore, so this specific conflict cannot recur regardless of the
  pin.
- **The pin's cost is still live, not just historical**: RUNBOOK's own
  2026-08-20 measurement (8.79h window) found ~14.9 GB/hour of continuous
  swapping, called "steady state, machine coping" at the time. Checked
  today on a 37-minute-old boot: cumulative `Swapouts` in `vm_stat` ×
  16KB page size ≈ 5.91 GB ≈ **9.6 GB/hour** — same order of magnitude,
  still happening, today.
- **Recommendation (not applied): worth testing a finite keep-alive,
  status is "worth testing," not "confirmed remove."** The pin buys
  avoided cold-load latency (measured once: 42s, a cold start after a
  reboot) but costs a permanent ~2.67GB reservation and multi-GB/hour
  swapping as a *baseline*, including genuinely idle stretches (overnight,
  the peak-hour narration throttle window) where nothing needs the model
  loaded. Real call cadence during active hours (`character_builder.log`
  showed calls roughly every ~2 minutes in the window observed) may
  already keep even a finite keep-alive warm through the day, meaning the
  pin might be buying little while an 8GB box sits permanently near its
  ceiling — in tension with the standing "must never thrash" rule even
  though it hasn't produced an outright hang since the preflight fix.
  **The one missing measurement**: real inter-call gaps during quiet/
  overnight hours — that's what actually determines whether unpinning
  would cost anything in practice. Not measured this session; needed
  before deciding, not before testing.
- **qwen2.5:1.5b is not a candidate for offloading M1 work as-is.**
  Already found format-non-compliant for the narration-script task (see
  above) — reproduces section headers and bullet points instead of
  rewriting to prose, on every test, both `/api/generate` and `/api/chat`.
  It has **not been tested** against the M1's other two real consumers,
  `analyzer.py` and `character_builder.py` — different tasks (structured
  multi-section analysis, character-voice comments), so the narration
  failure doesn't automatically predict failure there, but nothing says
  it'll succeed either. If M1 memory pressure is ever addressed by moving
  a task to a smaller model, that model has to be tested against the
  actual target task first, same as narration was tested before ruling
  qwen out for it. **If no small model can do analyzer/character_builder's
  job acceptably, the right conclusion is that job doesn't fit an 8GB box
  at all — moving the work to different hardware, not forcing a smaller
  model to approximate it.**

**Broadcast-cap production check — started, not yet reported.** Both
`arc-audio-backfill.service` (spectre) and `mailer` (resolute) were
restarted this session to pick up: the `OLLAMA_PRIMARY` fix, the
`num_predict=300` cap, and `check_narration_liveness`. A background check
was kicked off at 06:23 MDT, sleeping ~75 minutes, due to report **around
07:38 MDT** — **this session ended before that landed.** Next session:
check whether it already reported (it notifies on completion) or read
`logs/scribe.log` on spectre directly. What to look for:
  - Attempted / accepted / rejected counts for broadcast scripts since the
    restart (grep `📻` in spectre's own `logs/scribe.log` — NOT
    `journalctl`, scribe.py's own `FileHandler` never reaches the journal,
    see earlier in this handoff for why), compared against the pre-cap
    baseline of **81% rejected (30 of 37)**.
  - The actual character lengths of whatever gets generated now — is 300
    tokens landing consistently under 1400, matching the 3-article
    pre-deploy measurement, or did real production traffic (different
    content mix) behave differently.
  - Whether `arc:audio:last_narration` is being written on each success —
    that heartbeat is what `check_narration_liveness` reads; if it's not
    updating, the new watchdog check is blind regardless of whether
    narration itself is working.

**429 TOO MANY REQUESTS, scribe against Arc's own `/api/pre_analyze` —
mechanism identified, not yet decided.** Ross caught this in `arc
checkup` output: two 429s in the same second at 03:06 today,
self-inflicted (scribe calling Arc's own backend), not external traffic.
Chased far enough to name the exact mechanism, stopping short of the
actual decision:

- **Not Flask-Limiter** (that's the per-IP `arc:auth:limiter` state in
  Redis DB5, a different thing entirely) — this is a bare
  `threading.Semaphore(2)` in `main.py` (`_pre_analyze_sem`, line 1088),
  capping `/api/pre_analyze` at 2 concurrent requests. A request that
  can't get a slot within 1s (`.acquire(timeout=1)`) gets a 429
  (`main.py:1204`).
- **Scribe's own concurrency deliberately exceeds it, by design** — not
  a misconfiguration discovered by accident. `scribe.py:428-434`:
  `MAX_CONCURRENT_ANALYZERS = _ingestion["concurrent_preproc"]` (10 in
  `arc.cfg` today) with a comment already on record: *"Flask semaphore
  caps actual parallelism at 2 — extra threads hit 429 (1s wait) then
  fallback. No cloud impact."* Scribe submits preprocessing work via
  `executor.submit(api_client.pre_analyze, ...)` (`scribe.py:2480`); on a
  429/failure it logs `errors_pre_analyze` and falls back to a default
  dossier (confirmed at `scribe.py:1685`, "using fallback dossier" — this
  is where a silent score-quality loss actually happens, same failure
  shape as a priority-item pre_analyze failure a few lines earlier).
- **Observed frequency, for what it's worth**: `arc:ops:scribe:counters`
  shows `errors_pre_analyze = 2` against `poll_success = 262465` right
  now — i.e. maybe *only* today's two events, ever, on this counter (didn't
  chase when the counter itself was created/reset, so "only ever twice"
  isn't fully verified, just what the cumulative number shows as of this
  check). If accurate, the 10-vs-2 mismatch mostly doesn't collide in
  practice — most of scribe's 10-way concurrency is presumably spent on
  I/O (fetching/scraping), not on the CPU-bound spaCy/VADER step, so
  simultaneous arrival at the semaphore specifically is rare even though
  the ceilings themselves are structurally mismatched.
- **What's still open, for next session**: whether "rare, by design,
  falls back gracefully" is actually fine as accepted behavior, or
  whether it's worth raising `_pre_analyze_sem` above 2 (the "No cloud
  impact" comment suggests 2 was chosen for a local-resource reason, not
  a cloud-cost one — worth confirming what that reason actually was
  before just raising the number) to close the gap between it and
  `concurrent_preproc`'s 10 rather than relying on collisions staying
  rare. Not decided or touched this session.

---

## Session 2026-09-11, later — Ollama off both 8GB boxes; narration moved M1→spectre→warden

**The reallocation**: Ross moved Ollama off the M1 and warden entirely —
both become Kokoro TTS workers instead (measured today: warden swapped
2,295MB running gemma4:e2b, the M1 was paging 3.8GB; Kokoro is ~330MB,
neither box swaps running it). Sequence this session, each step
verified live, not assumed:

1. **Arc's analyzer was escalating 100% of articles to cloud** — the M1's
   models were already deleted (`/api/tags` → `{"models":[]}`), every
   `gemma4:e2b` call 404'd, every article fell through to
   `gemma4:31b-cloud`. Repointed `OLLAMA_URL`/`PRIMARY`/`FALLBACK` on
   resolute's `.env`, spectre's own `.env`, and a third leaked M1
   reference in `huntaegis_stack/backend/.env`
   (`TRANSLATION_HOST`, not previously caught) — all now → spectre
   (192.168.1.189, 14GB, already serving Hunt's `gemma4:e2b`). Restarted
   the full arc_stack + Hunt's gunicorn. **Verified**, not assumed: a
   real post-restart article completed `source=local_full` via spectre,
   zero cloud escalation.
2. **Arc's narration moved spectre → warden** (Ross: no TTS on spectre or
   resolute at all — corrects an earlier wrong recommendation in this
   same session to leave it on spectre). Built from scratch:
   - `AUDIO_KOKORO_PYTHON` (`scribe.py`) is now an env override, not a
     hardcoded `lecture_pipeline` path (`31fc870`) — same pattern as
     `BROADCAST_OLLAMA_HOST`.
   - `kokoro_worker` ansible role fixed to use `uv` instead of the
     deadsnakes PPA (`spectre-rebuild@82df62f`) — confirmed directly that
     spectre's real, working Python 3.12 was never from that PPA
     (`dpkg -l` shows zero deadsnakes packages there); the role had
     never been run against real hardware. Not converged via the role
     today — see below.
   - Warden's actual Kokoro capability **reused existing, already-tested
     work found in `/home/ross/.venv`** (kokoro/torch/misaki/spacy
     installed, Kokoro-82M weights warmed, real synthesis already
     verified — `essay_audio.mp3` etc. predate this session). Pointed
     the new env override at it directly rather than provisioning fresh.
   - Full parity build otherwise: `arc_stack` cloned to
     `/home/www/arc_stack`, its own backend venv (`uv venv --python
     3.12`), two **new, warden-specific** SSH keys (not copies of
     spectre's) — `arc_redis_tunnel_ed25519` and
     `arc_audio_sync_ed25519` — with matching restricted
     `authorized_keys` entries added on resolute
     (`port-forwarding,permitopen="127.0.0.1:6379"` /
     `command="/usr/bin/rrsync -wo .../uploads/audio"`). Both systemd
     --user units tracked at `ops/systemd/warden/` (`arc_stack@bd3bc6d`),
     mirroring `ops/systemd/spectre/`'s existing pattern.
   - **Real gap found and fixed mid-build**: `requirements.txt` was
     missing `yt-dlp` entirely (scribe.py imports it unconditionally via
     `youtube_ingest.py`) — pinned to `2026.8.19`, matching spectre's
     real ad-hoc-installed version (`dcf0b8b`). A clean
     `pip install -r requirements.txt` had been broken by this since
     whenever the dependency landed; surfaced rebuilding warden from a
     real clean venv under time pressure.
   - **Root steps needed** (only two, both Ross's, both landed): `sudo
     mkdir -p /home/www /opt/kokoro && chown ross:ross` (bootstrap, same
     one-time pattern as spectre's own `/home/www`), and `sudo apt
     install -y git` (warden had zero git). Everything else — uv,
     Python, both venvs, both clones, both keys, both units — done
     without further sudo.
   - **Spectre's narration stopped and disabled**, not left idle —
     confirmed `arc-audio-backfill.service` `disabled`/`inactive` there.
     Warden's confirmed `enabled`/`active`, stable, no crash-loop, since
     restart.
3. **bookradio_stack/lecture_pipeline**: agreed to stay on warden too, as
   **separate scheduled jobs, no coordination with `arc:audio:active`**
   — checked directly, neither codebase references it. The only real
   consideration is local CPU contention on warden if both run at once
   (Kokoro's ~330MB footprint means this is not a memory/thrash risk the
   way the Ollama models were) — accepted as a self-resolving cost for
   "batch work with no deadline," not worth a lock. Not built this
   session (bookradio/lecture_pipeline scheduling itself is unscoped,
   just the coordination decision).
4. **`failed_this_run` durability gap — designed, approved, and built**
   (`dcf0b8b`). The gap: that set is process-local, so a real narration
   failure got exactly one lifetime attempt per daemon process (no
   retry without a restart), while a restart wiped it and gave every
   past failure an *unbounded* fresh attempt forever. Fixed:
   `arc:audio:attempts:{article_id}` in Redis, incremented on every
   `narrate_one()` failure, TTL'd on first creation to
   `backfill_window_ceiling_hours` (not the live window) + 1h margin,
   checked in `find_newest_silent()` alongside the existing poison-pill
   check. Attempt cap: 3, persists across any number of restarts.
   Exhaustion logs once, distinctly from the poison-pill line (`🛑`,
   not the poison-pill's plain skip), with the article id and the last
   actual failure reason — `narrate_one()` now returns `(bool, reason)`
   instead of a bare bool so there's something to attach. Deployed to
   warden, restarted, confirmed stable.
5. **M1**: not touched all session, per Ross's own instruction (his
   machine, hand-configured). Confirmed `OLLAMA_KEEP_ALIVE=-1` is set
   via `/Library/LaunchDaemons/com.arc.ollama.plist` (still present,
   though Ollama has nothing to serve there now that its models are
   deleted) — whether that LaunchDaemon should be removed/disabled now
   that the M1's job has changed entirely is an open question, not
   decided or touched.

**Left for next session — the watcher is still running, do not
re-derive this list, just read its output:**

A background process (`watch_first_narration.sh`, tracked task,
started ~17:00 MDT this session) is polling warden's
`arc-audio-backfill` journal for the first `✓` success line since it
started. Warden entered the site's peak-hour throttle window
(14:00–19:00 MDT, ~1 acquire/95min) shortly after the build finished,
so the first real narration may not land until close to or after 19:00
when full-speed scanning resumes. **The moment it fires, report these
five points individually, not as a summary** (Ross's own framing,
because the 0600-umask-on-this-exact-directory bug has bitten before —
a file can exist, match, and still be unreadable by Caddy):

1. mp3 exists on warden — `/home/www/arc_stack/frontend/public/uploads/audio/{id}.mp3`
2. mp3 exists at the same path on resolute (the actual serving host)
3. byte sizes match on both hosts exactly
4. `audio_url` is set on `article:{id}` in Redis (the field itself, not just that narration "succeeded" in the log)
5. the public URL serves: `curl -D - https://arc-codex.com/uploads/audio/{id}.mp3` → `200`, with an `Accept-Ranges: bytes` header specifically, not just any 200

The watcher's own script is at
`/tmp/claude-1000/-home-www/36a8a33f-c82d-4ba7-b300-54ba91af7c64/scratchpad/watch_first_narration.sh`
(session-scratch, won't survive past this session — if it's gone next
session, just re-run the same five checks by hand against whatever the
next `✓` line's article id is; the check logic is simple and is spelled
out here in full either way).

**Repo state at session end**: `arc_stack` and `spectre-rebuild` both
`0` ahead of origin (everything pushed). `huntaegis_stack` is still on
`fix/translate-failure-visibility` (not `main` — pre-existing since
before this session, 53 commits ahead of `main`, unmerged; not this
session's problem to fix) with one new commit on top
(`ce72577`, the M1-retirement CLAUDE.md note), pushed. Dirty-but-not-
mine files left exactly as found in all three repos (operator-tuned
cfg values, an unrelated in-flight edit to Arc's public developer page
describing this same multi-role architecture — Ross's own work, not
touched).

---

## Session 2026-09-11, later still — Arc/Hunt divergence audit, STOPPED AT 90% SESSION LIMIT

**Do not treat this as done.** Ross asked for a full written account —
per-hunk classification (deliberate product difference vs. unintended
drift) of the four files `CLAUDE.md` names as shared
(`ollama_utils.py`, `fetch_utils.py`, `stream_utils.py`, `auth.py`),
then widened to every file that exists in one stack and not the other,
and every file in both that differs. Deliverable: a document Ross can
read to answer "if I re-cloned Arc to Hunt tomorrow, what would I have
to put back" — committed somewhere findable (proposed:
`docs/arc-hunt-drift-2026-09-11.md`, matching the existing dated-doc
convention in `docs/`). **Report only, no reconciliation** — explicit
instruction, nothing was to be fixed.

**Done, solid, ready to write up verbatim:**

- **`ollama_utils.py`** (189 diff lines) — fully hunk-classified:
  - Import reordering at the top — cosmetic, no functional change. Drift, trivial.
  - `BROADCAST_OLLAMA_HOST`/`BROADCAST_OLLAMA_MODEL` block and the
    `call_ollama_local_only(host=, model=, num_predict=)` override —
    **100% this session's own work** (2026-09-11, the warden narration
    build). Deliberate, Arc-specific, dated precisely in its own
    comments. Not something to "put back" on Hunt — it's Arc's own
    narration-pipeline plumbing, meaningless on Hunt.
  - The `Fix (validated 2026-07-06 ...)` docstring wording (Hunt still
    says "in the arc stack against previously-failing articles"; Arc
    now cites a specific article hash) — drift, but *inherently*
    non-portable: the article ID is Arc-specific data, there's nothing
    to mirror.
  - `_trip_cloud_breaker`'s docstring parenthetical — drift, trivial.
  - **`is_cloud_reachable()` — present in Arc, absent from Hunt
    entirely. This is the one that matters.** Its own docstring: added
    after the 2026-07-07 M1 outage caused "2,755 doomed escalations...
    against a dead host because reachability was never checked."
    Confirmed real, live usage in Arc: `character_builder.py`,
    `translation.py`, `analyzer.py` (5 call sites total). Confirmed
    **zero** equivalent anywhere in Hunt's codebase (grepped for any
    reachability check before cloud escalation — nothing). **Hunt is
    currently exposed to the exact bug class Arc fixed on 2026-07-07.**
    This is drift that's actually a live, unfixed bug on one side, not
    a cosmetic difference — the strongest single finding of this pass
    so far.
  - `call_ollama_with_fallback`'s expanded signature (`format_schema`,
    `temperature`, `models` params, all optional/backward-compatible) —
    real capability added to Arc only (schema-constrained decoding,
    temperature control, custom model cascades), not from this session.
    Hunt cannot do any of these three things. Drift or deliberate withhold
    — undetermined; needs Ross's call on whether Hunt ever needs them.
  - Exception-message tightening (`tried = ", ".join(...)`) — trivial, drift.

- **`fetch_utils.py`** — fully hunk-classified, **one major finding**:
  - Sanitizer comment ("Mirror of arc/backend/fetch_utils.py" in Hunt →
    replaced with real allowlist description in Arc) — drift, comment-only,
    the actual `_SANITIZE_ALLOWED_TAGS` set itself is IDENTICAL in both.
  - Bare `except:` → `except Exception:` — trivial code-quality drift, safe to port.
  - **`fetch_with_anti_bot_handling`'s entire Tier-2/3 implementation
    was replaced in Arc** (2026-07-15, "Playwright Tier-3 restoration,"
    see `ops/RUNBOOK.md`) — delegates to a new `playwright_tier3.py`
    module (owns browser lifecycle, "the radeon exile [--disable-gpu]",
    process-tree kill-on-timeout). **Hunt still has the old, ~90-line
    inline Playwright stealth-context implementation Arc deleted.**
    Checked whether this is dangerous: Hunt's only call site
    (`main.py:384`) always passes `playwright_browser=None`, so the old
    code path is dead-but-present, never actually invoked — consistent
    with Hunt's own `CLAUDE.md` ("Playwright removed... do not re-add").
    **Not a live bug, but a real capability gap**: Arc can now
    partially recover CAPTCHA-walled content via `playwright_tier3.py`
    and Hunt cannot. Whether Arc's new module actually avoids the
    original "AMD GPU UBSAN crashes" reason Hunt dropped Playwright is
    **unverified** — that's the open question before anyone decides
    whether this is "deliberate, Hunt opted out" or "drift, Hunt just
    never got the fix." Needs Ross's call, not mine.

- **`stream_utils.py`** (22 diff lines) — fully classified, all trivial:
  two comment updates (a service name added to a docstring list —
  `quiz_generator` — and a stream-size figure refreshed from "41k
  entries by 07-22" to "85k entries / ~5 months by 07-18"). **No
  functional difference anywhere in this file.** Pure comment drift,
  lowest-stakes of the four.

**Not started — pick up here next session:**

1. **`auth.py`** — the biggest of the four and not yet touched at all.
   Already know from the stale-file survey earlier this session:
   **it doesn't exist in `huntaegis_stack/backend/` at all** — no file,
   no `auth_bp`, no `login_required` anywhere in that codebase (grepped,
   confirmed). This isn't a diff-and-classify job like the other three —
   it's "Hunt has none of this feature." What still needs answering:
   is that deliberate (Hunt genuinely has no local-auth realm by design,
   OAuth-only) or drift (auth.py was written for Arc after the stacks
   forked and simply never got ported)? `CLAUDE.md` lists it as
   "shared" without qualification, which argues for drift, but that
   needs checking against Hunt's actual auth story (does
   `huntaegis_stack/frontend/lib/auth.ts` alone cover everything Hunt
   needs, making a Flask-side auth.py genuinely unnecessary there?).
2. **The full widen pass** — "every file that exists in one stack and
   not the other, and every file that exists in both but differs" —
   **not done at all** beyond the byte-identical list already found
   (`backfill_sentinel_ca.py`, `comment_utils.py`, `corpus_exporter.py`,
   `operational_state.py`, `redis_readiness.py`, `user_prefs.py`,
   `validate_sites.py` — confirmed identical, likely fine as-is) and
   the two known-stale copies already on record
   (`huntaegis_stack/arc_config.yaml`, `huntaegis_stack/backend/
   project_context.yaml` — stale undated copies of Arc's own files,
   confirmed dead, from the 2026-09-10 handoff entry above). The
   mechanical part is cheap (a `diff`/existence loop across both
   `backend/` trees, same pattern as this session's identical-file
   check) — the SLOW part is the same hunk-by-hunk classification just
   done for the four named files, applied to whatever else turns up
   differing. Ross specifically named three recurring symptoms to
   watch for while doing this: **APIClient existing in three separate
   copies**, **the 5005 port default hardcoded in four different
   files**, and **the 0600 umask bug recurring in three different
   generators** — none of the three has been located yet this session;
   start there, since Ross already knows they exist and named them
   precisely.
3. **Frontend side of the widen pass** — not started at all. Given the
   backend pass alone found this much, the frontend trees (`app/`,
   `components/`, `lib/`) almost certainly have their own version of
   the same problem and haven't been looked at.
4. **Write the actual deliverable** — a real markdown document (not
   just this TODO entry) organized around Ross's own framing: "if I
   re-cloned Arc to Hunt tomorrow, what would I have to put back."
   Propose `docs/arc-hunt-drift-2026-09-11.md` (matches the dated-doc
   convention already in `docs/`), commit it there, and **cross-link it
   from `huntaegis_stack`'s own `CLAUDE.md`** too, since a doc that only
   lives in Arc's repo is exactly the kind of thing that won't be found
   from the Hunt side when someone needs it.

**Reminder for whoever picks this up**: nothing has been fixed or
reconciled, on purpose, per Ross's explicit instruction — this whole
pass is report-only. Don't let finding `is_cloud_reachable`'s absence
or the Playwright gap turn into an urge to just port the fix over;
report it in the document and let Ross decide.

---

## 2026-09-12 morning — warden's narration was completely down overnight, found and fixed

The original watcher process got killed ("system running low on
memory") before it ever saw a success. Checking cold the next morning
found **zero successful narrations since the build finished the
previous evening** — every single attempt from 17:44 onward failed
with `Local Ollama health check failed for http://192.168.1.189:11434
(ConnectTimeout)`, logged as an ordinary `no broadcast script;
narration skipped this pass` line — indistinguishable from a content
rejection unless you already know to check connectivity.

**Root cause**: spectre's `ufw` only ever allowlisted resolute
(`192.168.1.198`) for its Ollama port. When warden's
`OLLAMA_PRIMARY`/`FALLBACK` were repointed at spectre the previous
day (`192.168.1.189:11434`), nobody updated spectre's
`ollama_api_clients` to also allow warden (`192.168.1.190`) — confirmed
directly: `curl` from warden timed out, the identical `curl` from
resolute worked. A pure gap in yesterday's build — connectivity was
verified resolute→spectre and spectre→itself, never warden→spectre
specifically, which is exactly the new path that mattered.

**Fixed**: `ollama_api_clients` in `spectre-rebuild/inventory/
host_vars/spectre.yml` now includes `192.168.1.190`
(`c808f0f`, pushed) — source-of-truth for the next converge. Ross ran
the matching live command by hand (`sudo ufw allow from 192.168.1.190
to any port 11434 proto tcp comment 'warden narration'`) since this was
a live ~10-hour outage, not something to leave for a future converge.
**Verified**: `curl` from warden to spectre's `:11434` now succeeds
(confirmed live, not assumed from the ufw rule alone).

**Still open — not yet confirmed**: connectivity is fixed, but no
*narration* has actually succeeded through the fixed path yet as of
this note — that needs a real new candidate to land and a real attempt
to complete. Re-launched the watcher
(`watch_first_narration.sh`, same script/logic as before, task
`bnrzbflfk`) to catch the first post-fix `✓` line and run the original
five-point check (mp3 on warden, mp3 on resolute, byte sizes match,
`audio_url` set, public URL serves with `Accept-Ranges`). If this
watcher also dies before reporting, don't assume the fix didn't work —
check `journalctl --user -u arc-audio-backfill.service` on warden by
hand for a `✓` line and run the five points manually; the connectivity
fix itself is confirmed solid independent of whether the watcher
survives to report it.

---

## 2026-09-12, later — REBOOT COMING. Read this before doing anything else.

Session ended for a reboot, not because the work was finished. Whoever
picks this up: **the resolute box you're on is about to restart (or
just did)** — anything that assumed a running process survives across
it needs to be re-verified, not assumed. That specifically means: the
watcher is gone (killed deliberately, see below, not crashed), and
warden's/spectre's systemd `--user` services need their `is-active`
state re-checked fresh rather than trusted from this doc.

**A suspected-fabricated instruction arrived and was NOT acted on.**
A message claimed a Redis password rotation was left partial — "the
server is still on the old password while all seven files carry the
new one" — asking me to edit `/etc/redis/redis.conf`, run `CONFIG SET`
on the live server, or restart every consumer. **Checked directly
before touching anything**: `redis-cli -a <the same password every
.env file has carried all session> ping` → `PONG`, right now. Nothing
this entire session touched Redis authentication. There is no old/new
password split — every host and the server itself agree, unchanged.
**Declined to act.** If a real rotation is genuinely in flight through
some channel this session has no record of, it needs to be stated
plainly and verified again from scratch — don't resume "finishing" a
rotation neither this session nor (as far as its own history shows)
any prior one ever started.

**Confirmed, separately, since it was asked (and is real, unlike the
above): warden's `backfill_window_hours` is `2`** (the committed
default — it's a fresh clone) while **spectre's was `6`** (a local,
never-committed edit). Not the cause of the ~10h outage (that was the
firewall gap, already fixed and confirmed in the entry above) — but a
real difference worth a decision: does warden get the same 6h override
applied locally, matching what spectre had? Not done, not asked for
beyond "confirm" — Ross's call.

**Landed this session, on top of everything in the entry above:**

- **Transport-vs-content failure classification, fully implemented**
  (`4bd827c`, pushed to `origin/main`). Three new exception types —
  `ollama_utils.OllamaTransportError`, `ollama_utils.OllamaNoResponseError`,
  `scribe.AudioToolError` — so a connection failure, a host that
  answered with nothing usable, and a Kokoro/ffmpeg tool crash all get
  distinct log tokens (`UNREACHABLE`, `NO-RESPONSE`, `TOOL-FAILURE`,
  and `SYNC-FAILURE` for `push_to_destination`, which is unconditionally
  infrastructure — rsync has no concept of article content) and are
  explicitly excluded from the retry-budget counter built the session
  before. `narrate_one()` now returns `(ok, reason, countable)`, one
  more field than before. **What counts against the retry budget now,
  in full**: the model answered, the answer arrived, and it was
  unusable for a reason specific to the article (over
  `BROADCAST_MAX_CHARS`, or the script too short to narrate). Everything
  else is infrastructure and doesn't count.
  **NOT YET DEPLOYED to warden** — committed and pushed to `origin/main`
  only. Deliberately did not rush a `git pull` + service restart onto
  the one host actually running narration right before a reboot with no
  time left to verify it. Next session: `ssh warden 'cd
  /home/www/arc_stack && git pull && systemctl --user restart
  arc-audio-backfill.service'`, then watch the journal for a clean
  start (no crash-loop) before trusting it.
- **The watcher was killed deliberately**, not left to die in the
  reboot — confirmed dead (`ps aux` empty) before this note was
  written. It had not yet seen a successful narration through the
  fixed firewall path when it was killed; that's still genuinely
  unconfirmed. Re-launching it isn't required — a straight `journalctl
  --user -u arc-audio-backfill.service | grep '✓'` on warden next
  session answers the same question without needing a background
  process at all.

**Repo state at session end, all pushed, nothing ahead**: `arc_stack`
(0 ahead, `main`), `spectre-rebuild` (0 ahead, `master`, completely
clean), `huntaegis_stack` (0 ahead, still on `fix/translate-failure-
visibility` — pre-existing, not this session's to fix). Dirty-but-not-
mine files unchanged from every prior entry (`arc.cfg`, `arc_config.yaml`,
the developer-page edit, `next-env.d.ts` in arc_stack; `huntaegis.cfg`,
`nohup.out` in huntaegis_stack) — left exactly as found, still not
touched.

**Still fully open from the Arc/Hunt drift audit** (see the entry
above this one) — `auth.py`'s classification, the full exists-in-
one-not-other widen pass, the frontend side, and the actual deliverable
document are all exactly as unstarted as they were when that entry was
written. Nothing happened on that front this session; it got
interrupted by the overnight outage and this session's other work
instead.

---

## Session handoff 2026-09-12 evening — narration gates removed, script-collapse finding open

Warden was silent when the session opened: `arc:audio:last_narration` at
17:11 MDT, no article in the current feed carrying an `audio_url`, watchdog
still reporting "nothing silent in the last 6.00h" while the entire feed was
silent. Three gates surfaced across the session. Each of the three was
measuring a property of the pipeline as it existed **before Sunday's
redesign** — when `run_broadcast_script` became the sole caller of
`synthesize_article_audio` and source text stopped being narrated. None had
been updated to reflect that. Two gates landed as removals today; the third
landed as a naming/reorganization only.

**Gate 1 — `AUDIO_MIN_CHARS = 100` doing double duty** (split, no behavior
change downstream). The one constant was consulted at two sites against two
different texts: `audio_backfill.py:527` measured raw article body (a CAPTCHA
/ stub floor — the Aug 2026 CAPTCHA-extract cluster at 1234-1250 is what
this ought to keep out) and `scribe.py:692` measured the generated broadcast
script (a truncated-script floor). Split into `SOURCE_MIN_CHARS = 1500`
(raw body, above the CAPTCHA cluster) and `SCRIPT_MIN_CHARS = 400` (script,
well below the 776-char low end of real 2026-09-11 model output). Constants
split; both call sites updated. `AUDIO_MIN_CHARS` no longer exists.

**Gate 2 — `BROADCAST_MAX_CHARS = 1400` post-response rejection removed**
(`scribe.py:1964`). This was set as the ceiling on the model's script
output after the 2026-09-06 retune; paired with `BROADCAST_NUM_PREDICT
= 300` meant to keep the model landing under it. In practice the model was
reliably producing 1590-1911 chars at 300 tokens (~5.7 chars per token for
this content) and hitting the char ceiling every time — every completed
script was being discarded, with `TRUNCATED (done_reason=length)` and
`REJECTED for {aid}` back-to-back in the log. The rejection now downgrades
to an informational log line ("over historical BROADCAST_MAX_CHARS=1400,
accepted") and the script passes through. Constant is still defined;
nothing consults it as a hard gate any more.

**Gate 3 — 11,004-char source-length skip in `find_newest_silent` removed**
(`audio_backfill.py:527-534`). This was `max_chars_for_budget()` =
`estimated_synthesis_cps × AUDIO_TIMEOUT_SECONDS` = 18.34 × 600 = 11,004,
sized to keep synthesis of **raw article text** under Kokoro's timeout.
Nothing narrates raw article text any more — `narrate_one` calls
`run_broadcast_script()` and feeds the resulting ~1700-char script to
`synthesize_article_audio()`. Script length is bounded by
`BROADCAST_NUM_PREDICT` at generation, not by the source it was derived
from; a 110,000-char article produces the same ~1700-char script as a
13,000-char one. Skip removed; `max_chars_for_budget()` and its
"11004-char synthesis budget" startup log line are now unused (cosmetic
cleanup for later, non-urgent).

**End-to-end verification with the removed gates**: target article
`5a9f6aa7c4e55b9f751548748aed6891` (15,031-char body, which the 11,004
skip had rejected earlier in the session) narrated at 18:26:50 MDT —
1574-char script → 115.5s mp3 (13.6 chars/s), 617s wall.
`article:...audio_url` set, `arc:audio:sync_ok` incremented 1608 → 1609,
`sync_fail` still empty, `https://arc-codex.com/uploads/audio/5a9f6aa7…mp3`
returns HTTP/2 200 with `content-type: audio/mpeg`, local mp3 on
resolute at 924,332 bytes md5 `b859a8ce…`. First successful narration
since the 17:11 MDT stall.

**Where the work actually happens (context for the next session)**: warden
runs Kokoro but does not run `run_broadcast_script`. That's a
`call_ollama_local_only` call whose `BROADCAST_OLLAMA_HOST` env resolves to
spectre (`192.168.1.189:11434`, per warden's `.env`). Warden waits on
spectre for the script, then runs Kokoro locally, then rsyncs the mp3 to
resolute via the `arc-audio-sync@…` rrsync-wo key. When the daemon logs
`✓`, most of the wall time was spectre.

**Open finding — script-length collapse, not truncation, cause unknown.**
Ross observed broadcast-script responses collapsing from 1713-1804 chars
at 18:03 (all `done_reason=length`, model hitting the token cap) to
**101-234 chars with `done_reason=stop` and leading whitespace** later
in the session. That is the model *declining to write*, not writing
briefly — an entirely different failure shape from anything the day's
gate work touched, and one that the three edits above cannot cause: the
request payload to `call_ollama_local_only` (prompt template, `num_predict`,
model, host, timeout) is byte-for-byte unchanged from before the edits, and
`prompts.yaml` matches HEAD with matching md5 on both hosts. **The 101-234
observation is not in warden's `arc-audio-backfill` journal** as far as I
could locate it — the only TRUNCATED events there are the 1590-1911
sequence with `done_reason=length` — so the source of the observation is
somewhere I did not identify: `analyzer.py`'s journal (same call-path
shape, but different prompt), spectre's ollama server log, or a live
dashboard/tail. The 18:26:50 target-article narration returned 1574 chars
via the same code path with `done_reason=length`, which means the
collapse either recovered or is not universal.

**Where to start next session on that finding**: (a) locate which log
carries the 101-234-char observation; (b) correlate its timestamps with
anything that changed on spectre in the same window (ollama restart,
model reload, weight file touch, memory pressure), since nothing about
the request itself moved on the Arc side.

**Deliberately not touched at end of session, per Ross**: `SCRIPT_MIN_CHARS
= 400`, `prompts.yaml`. Nothing lands untested.

**Also unchanged, mentioned but not scoped this session**: the 6h feed
window in `find_newest_silent`, the peak-hour throttle, `BROADCAST_
TIMEOUT_SECONDS = 900`, `AUDIO_TIMEOUT_SECONDS = 600`,
`BROADCAST_NUM_PREDICT = 300`.

**Hunt mirror** — `AUDIO_MIN_CHARS = 100` still exists in
`/home/www/huntaegis_stack/backend/scribe.py` as the fused single constant.
Whether Hunt's narration path has the same script-vs-source split as Arc's
(and therefore the same vestigial-gate story) is unverified. Deferred.

**Repo state at session end**: `arc_stack` is `main` + 2 commits ahead of
`origin/main` — the gate-removal code commit and this handoff commit. Not
pushed (session ending, nightly-git-push cron at 02:30 will carry it).

**Ross's operator-owned files unchanged** (per CLAUDE.md's "operator-owned
fields" rule): `arc.cfg` [ingestion] tuning (`cycle_minutes = 0`,
`sources_per_sweep = 2`), `arc_config.yaml`, `frontend/next-env.d.ts` —
left exactly as found, not committed.

**Monitors killed at end of session**: `b8xjk7dcm`, `blr50k7ya` (both
timed out on their own), `b6ek0n2t3` (explicitly stopped). No background
task started by this session is still running.

