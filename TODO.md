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

## Carried out of session 2026-08-01 — image derivation + translate rate-limit sweep

Landed this session (branches off main, not merged): `fix/retention-orig-purge`
(retention.py + test), `feat/image-derive-stage2-scaffold` (Stage 2 module,
unwired). Rate limiter B.3 landed on `fix/translate-failure-visibility` after
bd07573 — moves independently only when that branch does.

**T1 — Replace the graphic detector's primary signal.** Palette concentration
over 542 originals is not bimodal (photograph mass 0.30–0.65, transition
0.65–0.90, graphic spike 0.95+). Threshold is set to 0.95 so it fires only where
the signal is real; the middle 40% — magazine covers, text-on-photo,
screenshots — is unaddressed. Planned replacement: test the band a center-crop
would *discard* against the retained strip (per-row gradient profile,
discontinuity at the crop line, text-like runs). Measures the actual harm rather
than inferring image type; no population split required; checkable ground truth.
Keep palette ≥0.95 as a high-confidence override.

**T2 — Wire `derive_card()` into `rehost_article_image`** (`scribe.py:665–675`).
Blocked on T1. Audit says the swap is contained; WebP variants derive from the
returned card image so they need no change.

**T3 — `retention.py` glob covers `SCRAPED_IMAGE_DIR` only.** Manual-upload
heroes are content-addressed (`sha256[:16].jpg`) in
`frontend/public/uploads/`, not `scraped/`, so `purge_article_satellites`
never sweeps them. Unverified — possible unbounded leak since the manual
publish path shipped. Enumerate what references them and either extend the
sweep or accept the divergence explicitly.

**T6 — Unit D, language pills.** Data already served as `cached_langs` on the
article payload; frontend surface not yet built. IntelligenceCard territory.

**T7 — Translation TTL mismatch.** `translation:{id}:{lang}` runs 24h/7d
depending on model tier; `translation:langs:{id}` is 7d. A pill can outlive
its underlying translation, so clicking a ghost costs a fresh ~3-minute
inference. Decision on record: translations should prune with their article,
not carry their own TTL — remove the per-key expiries and rely on
kasmir7/retention to clear both keys together.

**T10 — Codex full-state survey is running.** Fold its findings in when it
lands; may collapse into or supersede items above.

---

## Landed / closed 2026-08-01 (removed from active list)

- **T4** — Unit B.2 Flask errorhandler wired (Aug 1 survey).
- **T8** — `og:image:height=675` aligned (Aug 1 survey; `fix/og-image-height-675`).
- **T9** — systemd units installed (Aug 1 survey).

### Session-scope notes worth catching next time

- Retention fix (E1) and translate B.3 (E3) landed within the same session.
  The retention branch was extracted to its own branch off main via
  detached worktree so it can ship independently. B.3 was NOT extracted —
  it depends on bd07573 (HTTPException passthrough) which is only on the
  translate branch; a full extract needs cherry-picking the translate
  chain first. Left in place for the next session to decide.
- Image derivation scaffold committed on its own branch but the running
  scribe still writes the pre-Stage-2 card unchanged. This is by design;
  see T2.

---

## Carried out of session 2026-08-01 (later) — quick-win sweep

Landed: `perf/scribe-cadence-30` (cfg 1→30), `fix/og-image-height-675`
(1200×630 → 1200×675), plus follow-up `824ed8d` on
`fix/translate-failure-visibility` completing B.3's main.py wiring —
B.3's `apply_rate_limits` call had been left in the working tree, so
production /api/translate/ ran uncapped from the B.3 commit until
this fix. Tests didn't catch it because the test file self-wires.

**T11 — Cap /api/grade/ and /api/library/ (Arc only, Hunt has neither
route).** Parked, not landed. The audit path is clear:
  - `backend/grade.py:137` — `grade_article` view. Suggested cap 20/hour
    per IP: grade responses cache 7 days (GRADE_TTL), so real reader
    traffic hits cache; a fresh grade is a ~300s inference call to
    `call_ollama_with_fallback`. 20/hour caps single-IP model spend at
    ~100 min/hour worst case, cache hits fine.
  - `backend/main.py:2279` — `get_library_work` view. Two buckets like
    translate: `?lang=en` or absent → 120/hour (SQLite read only),
    anything else → 10/hour (translates and caches the entire book —
    heavy).
  - Blocker: reusing B.3's `apply_rate_limits` helper cleanly requires
    it to be on main, and B.3 is still on `fix/translate-failure-visibility`.
    The right shape is to first extract the wrapping pattern
    (`view_functions[endpoint]` replacement, idempotency marker, loud
    missing-endpoint failure) into a shared `backend/rate_limit_utils.py`,
    then have translate/grade/library all use it. Doing that on a branch
    off main means either (a) refactoring translate's helper on the
    translate branch first and merging, or (b) shipping the shared util
    on its own branch off main and refactoring translate later. Option
    (b) is smaller. Either way, more than a "quick win" commit.

**T12 — Hunt gunicorn access log format lacks the duration field.**
Arc's has `%(D)s` (or equivalent) appended and produces
`… 200 9420 "…" "…" 7.365836`; Hunt's stops after the user-agent.
Blocks any p95 measurement of Hunt's /api/translate/ from access
logs. One-line change to `backend/gunicorn_arc.sh` (or wherever the
access_log_format is defined on Hunt); gunicorn restart to pick up.

**W1 AFTER measurement pending.** Scribe restarted at 13:38 UTC-6
with `cycle_minutes = 30` (was 1 on Arc, 60 on Hunt). Ross's plan
called for capturing Arc `/api/translate/` p50 and p95 ~60 min after
the change. BEFORE numbers were: n=55 successful, p50=0.01s (cached),
p95=451.93s, max=517.41s. Re-run:
  `python3 -c "import re; ..."` against
  `/home/www/arc_stack/logs/gunicorn_access.log` at ~14:38 UTC-6 or
  later. The regex used for the BEFORE capture is at
  `/tmp/w1-before.txt` alongside the numbers.

---

## Added 2026-08-02 — fleet-wide (mirrored in huntaegis_stack TODO)

**F1 — Spectre NVIDIA driver DEAD post Ubuntu 26.04 upgrade.** `nvidia-smi`
cannot reach the driver; Ollama reports `size_vram=0` on both `gemma4:e2b`
and `gemma4:e4b`. **Spectre is currently a CPU box at 10.7 tok/s against
the M1's 27.2.** Spectre was reduced to a dedicated inference agent BECAUSE
of the GPU. This changes the cluster plan — no Spectre-as-analysis-host
assumption is safe until the driver is back. DKMS module likely unbuilt
against kernel 7.0.0-28. Recon-only, do not attempt fix now. Direct impact
on Arc: none today (Arc analysis is on M1), but any future decision to
offload Arc onto Spectre needs this resolved first.

**F2 — Spectre HAS swap (correct earlier "no swap configured" claim).**
`free -h` on Spectre: 4.0 Gi configured, ~494 MiB already in use before any
bench work. Every doc/plan that repeats "Spectre has no swap" needs
updating. Relevant to co-tenant sizing: swap growth during inference
presents as slowness, not error.

**F3 — Spectre sshd may have reverted `PasswordAuthentication no` after
upgrade.** Spectre accepted a password from M1 today (was previously
disabled via `/etc/ssh/sshd_config.d/99-hardening.conf` on 2026-07-24).
Ubuntu 26.04 upgrade may have dropped it. `ufw` still limits port 22 to
LAN so not urgent. Verify with `sshd -T | grep -i passwordauthentication`
and audit what else the upgrade reset.

**F4 — Resolute has NO ssh key to M1 (blocks unattended M1-side diagnostics).**
Blocked Step 3.d in the Hunt translate work: could not fetch M1 `vm_stat`
during a live Hunt translate. M1 is the offsite backup destination
(LaunchAgent com.rossnesbitt.m1-pull-backups pulls FROM Resolute), so
checks are strictly one-directional today. `ssh-copy-id ross@192.168.1.185`
is a one-command fix; quick win, unblocks a whole class of unattended
health check.

**F5 — Single M1 Ollama process restart during 2026-08-02 benchmarking.**
One occurrence, not reproducible after Ollama came back. A `/api/chat`
request against `translategemma:latest` with `think=false` timed out at
300 s; Ollama process then died. Every subsequent identical request
succeeded in seconds. Worth watching if M1 continues to carry Arc analysis
plus co-tenants; Arc analysis health depends on it.

### Arc-side notes worth catching next time

- Arc's `translation.py` payload construction was the reference implementation
  for Hunt's Unit C work. Hunt now sends `think=false` and `num_ctx=32768`
  matching Arc's local path. Hunt still bypasses `ollama_client` and hits
  `/api/chat` instead of `/api/generate` — those diffs are logged as
  Hunt-side T13/T14 in huntaegis_stack TODO, not Arc's problem to fix.

