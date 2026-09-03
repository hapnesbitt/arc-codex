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
4. Verify Redis reachability from spectre to resolute:6379 with the
   real password. `arc:audio:active` mutex, `POLL_SECONDS = 30`,
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
   verified. Redis LAN reachability is **not** done — deferred to its
   own window before Phase 2 wiring (see below). Measurement results in
   the "Phase 1 measurement" subsection above.
3. Phase 1 cutover, quiet overnight. **Depends on Redis LAN binding.**
   Disable resolute's audio-backfill.service; enable spectre's.
   `arc:audio:sync_ok` counter live.
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

