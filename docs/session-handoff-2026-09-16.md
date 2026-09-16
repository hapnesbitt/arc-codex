# 2026-09-16 session handoff — parity audit, sales rewrite, local-only mode, brand extraction

Session goal: get Arc and Hunt ship-shape for cloning / selling / demoing.
Four things landed; three remain from earlier today; one strategic sweep
is deliberately deferred.

---

## Landed this session

### 1. Parity audit — `docs/stack-parity-audit-2026-09-16.md` (commit `f9b38bd`)

Read-only, file-by-file accounting of what legitimately differs between
`arc_stack` and `huntaegis_stack` vs. what differs only by drift.

Headline findings:

- **CLAUDE.md's "four shared utilities" claim is false.** `auth.py`
  doesn't exist on Hunt at all; `ollama_utils.py` / `fetch_utils.py` /
  `stream_utils.py` are all drifted (ollama_utils by 205 content
  lines — Arc-forward exception taxonomy, cloud-reachability probe,
  broadcast host). Fix: mirror or drop the claim. (Partially addressed
  this session by porting `is_cloud_reachable` to Hunt — see item 3.)
- **`site_config.py` exists on both stacks but only ~20% adopted.**
  Port default (`5005`/`5006`), brand strings, Redis env still
  copy-pasted across 12+ files per stack. This is the "sufficient
  version" cleanup — see the deferred section below.
- **Arc-only files split cleanly** into product surfaces Hunt doesn't
  want (Library/Quiz/Reporters/Plants/Syndromes) vs. missed-mirroring
  infrastructure Hunt would want (net_safety, playwright_tier3,
  escalation, docs/, ops/systemd/, provision.sh).

That doc is the input for everything below.

### 2. Module map + sales page rewrite (commit `0316059`)

`frontend/app/about/sales/page.tsx` — restructured around four tiers.
The chat report broke every Arc-only surface into "already deployable /
needs a day / needs real work / out of scope."

Tier structure now on the live page:

- **Base · What Ships On Day One** — Hunt-as-a-live-instance. Nine
  bullets, everything Hunt actually runs today.
- **First Week · Add-Ons In The Deployment Window** — Wiki, Sources
  page, YouTube ingest, prompt-to-article, grade endpoints, Playwright
  fallback. Lead-in sentence acknowledges "carrying across recent
  improvements from the shared codebase — a real cost, budgeted into
  the week."
- **Sprint Add-Ons · Discrete Engagements** — Quiz, Reporters, Library.
- **Sibling Products · Named Separately** — Newsradio, LightBox,
  School of Chat.

Also corrected on the page: source count 51→**284** for Huntaegis (was a
five-fold understatement); header stat "Docker-Ready" → "Self-Hosted";
"Zero cloud dependency" softened to a per-path posture; "in a single
session" replaced with "a live second instance, code-shared with Arc
Codex, run continuously."

Ground-truth facts settled before writing copy:
- **Inference (fact 1):** three of four paths (council, translation,
  broadcast script) are local-only unconditionally; the fourth
  (analyzer) is local-first with a gated cloud escalation. Not
  cloud-primary today.
- **Source count (fact 2):** Arc `sources.json` = 2,310. Hunt = 284.
- **"In a single session" (fact 3):** ~69 backend + ~126 in-scope
  frontend brand strings per stack — the real cost of every future
  white-label. Honest phrasing: "one week of setup by one engineer."

### 3. Local-only mode — `ARC_LOCAL_ONLY=1` (commits Arc `86592ff`, Hunt `ad47d46`)

Makes the sales page's "local-only mode disables cloud entirely" claim
true by construction, not by convention.

**Scope, honest:** ~35 Python lines + ~20 docs/tests across both
stacks. About one day of engineering. Landed in one session because
every existing cloud gate already routed through one of two functions.

**Three enforcement points:**

1. `ollama_utils.is_cloud_available()` returns False under the flag.
   `analyzer.py`'s escalation guard, `translation.py`'s user-facing
   cloud retry, and `call_ollama_with_fallback`'s tuple-stripping
   cascade all check this function — the flag propagates with no
   per-callsite work.
2. `ollama_utils.is_cloud_reachable()` short-circuits without touching
   the network. Prevents every escalation-decision cycle from logging
   a failed probe against a host disabled by policy.
3. `site_config.load_site_config()` refuses to start if
   `[inference].council_url` points off-host.

**The council_url guard is the load-bearing finding.**
`character_builder.py` (the council path) hits `site.council_url`
directly with `requests.post` and does NOT route through
`ollama_utils`. Without the loader check, a customer who set a cloud
council endpoint would silently bypass the mode. That ~5-line guard in
`site_config.py`'s loader is the difference between "supported" and
"provable." Worth naming explicitly because a buyer who requires
zero-cloud gets nothing from a convention.

**Hunt-side bonus:** `is_cloud_reachable()` didn't exist on Hunt (was
Arc-forward drift per the parity audit) — ported alongside the flag so
the mode's invariant holds on both stacks. Closes one line of the
parity audit's section C.

**Regression sweeps:** Arc 112 tests green, Hunt 87 tests green.

### 4. Brand extraction — backend, partial (commits Arc `b606d12`, Hunt `13de657`)

Scope from the report before starting: ~126 in-scope frontend + ~69
in-scope backend strings per stack, roughly 1.5-2 days across both
stacks. Backend went in this session; frontend deferred.

**New `site_config` accessors** (matched to the existing `[branding]`
cfg schema — both cfgs already carried the section with values, the
code just wasn't reading them):

- `SITE.email_from` → `[branding].mail_sender` (fallback `ross@<domain>`)
- `SITE.default_image_url` → `[branding].default_image` (relative or absolute)
- `SITE.article_url(id)` → `f"{base_url}/article/{id}"` — replaces 11+ hardcoded sites
- `SITE.rss_title`, `SITE.rss_generator`, `SITE.rss_guid_prefix`

**Callsites replaced (Arc):** `rss_feed.py`, `bluesky_poster.py`,
`facebook_poster.py`, `mastodon_poster.py`, `threads_poster.py`,
`manual_publisher.py`, `prompt_to_article.py`, `analyzer.py` (CA
prompt persona), `mailer.py` (digest subject/lines/HTML/footer),
`auth.py` (module defaults + Jinja templates now receive `site_name`
via `_render`/`render_template_string`).

**Callsites replaced (Hunt):** `rss_feed.py` only. **This is the
demonstrable payback moment** — Hunt's RSS feed was still emitting
"HapEnews" and "whirled-news.barrel-of-knowledge.info" even though
`huntaegis.cfg` had the correct Huntaegis branding. Reading from cfg
made the feed match the rest of the stack, no cfg change needed.

**What's left on Hunt** (~8 more backend files):
`bluesky_poster.py`, `facebook_poster.py`, `mastodon_poster.py`,
`mailer.py`, `manual_publisher.py`, `analyzer.py`, plus whatever
touching frontend requires. Total maybe 3-4 more hours of the same
mechanical pattern used on Arc.

**Payback math (from the earlier report):** ~1.5-2 engineer-days now
saves ~3-4 hours per future customer deploy. Break-even before you
finish the second customer. **Do it before the next customer, not
during.** Same argument stands with the backend half already landed.

---

## Deferred: `site_config` adoption sweep (parity audit E.5)

The sufficient version of the extraction. Beyond brand strings, ~15
modules per stack still re-derive `os.getenv("REDIS_URL")` /
`os.getenv("REDIS_HOST")` / `os.getenv("REDIS_PORT")` /
`os.getenv("REDIS_DB")` / `os.getenv("REDIS_PASSWORD")` directly
instead of reading from `SITE`. Also the port default (`5005`/`5006`)
appears in ~12 files per stack.

Estimated ~1 more day of engineering. Deliberately deferred this
session so brand extraction lands first and gets verified before the
broader sweep starts. Do it as the follow-up to finishing Hunt's
brand extraction.

---

## Still open from earlier today (carried forward from `TODO.md` §2026-09-13)

### The `-np 2` re-enable sequence — still not run

Full sequence lives in `TODO.md:36-64`. Committed code (`46f7a17` +
`44a99a4`) has capped `num_ctx=16384` and `analysis_max_chars=50000`
to fit a second parallel slot on spectre inside 14 GiB. Session left
the drop-in removed (safe reboot state). Re-enable after verifying
the analyzer processes started from the committed code, not the
pre-commit cache.

### `cycle_minutes = 3` against ~10 analyses/hour — queue-growth arithmetic

Arrival rate at `cycle_minutes = 3` is ~20 articles/hr; analyzer
drain measured at 10.3 completions/hr. Queue grew 149→156→153 across
the prior session. Ross's proposed fix: bump `[ingestion]
cycle_minutes` to 15 (arrival ~4/hr, well below drain). Zero code
change. **`arc.cfg` `[ingestion]` is operator-tuned per CLAUDE.md —
the edit is Ross's, not a normalization pass.** Still `cycle_minutes = 3`
in the working tree, dirty exactly as found.

### 65/day silent loss — no metric exists

Over the 24h ending at 2026-09-13 close, 65 articles aged out of the
6h audio window unanalyzed with zero log lines and zero retry
counters. Failure mode of `audio_backfill.find_newest_silent` when it
passes over an unanalyzed article. **No counter exists for this** —
`corpus_exporter.py` has no gauge for "candidate passed to next pass
because unanalyzed." Adding one to `find_newest_silent` (increment
`arc:stats:aged_out_unanalyzed` when `_is_analyzed` returns False AND
`feed_ts` is near the window cutoff) surfaces the loss without a two-
file grep. Not touched this session.

---

## Repo state at session close

### Arc (`/home/www/arc_stack`, branch `main`)

Committed this session (in order):
- `f9b38bd` — docs: parity audit
- `0316059` — sales page rewrite
- `86592ff` — local-only mode
- `b606d12` — brand extraction (backend, partial)
- (this handoff will be one more commit)

Dirty at session close, all pre-existing operator state:
- `arc.cfg` — `[ingestion] cycle_minutes = 3` and other operator-tuned
  fields. Do not normalize. CLAUDE.md's rule.
- `arc_config.yaml` — pre-existing operator changes.
- `frontend/next-env.d.ts` — regenerated by Next.js on every build.
- Untracked: `"Ghost in the Machine ... [dLQzVLtvdv8].webm"` (2 GB
  documentary in repo root, unrelated to code).

### Hunt (`/home/www/huntaegis_stack`, branch `fix/translate-failure-visibility`)

Committed this session (both landed on the pre-existing working
branch, not `main`):
- `ad47d46` — local-only mode (mirror)
- `13de657` — brand extraction (backend, partial — rss_feed only)

Dirty at session close:
- `huntaegis.cfg` — pre-existing operator changes.
- Untracked: `nohup.out` (Ross's own).

Both Hunt commits ride the `fix/translate-failure-visibility` branch.
If you want them on `main`, cherry-pick or rebase — but that branch is
also carrying Ross's prior 5005→5006 port-fix work (`17babdc`,
`f436821`, `b5871af`, `3f07b95`, plus `ce72577`) and looks like it's
being held for a single merge later.

### Nothing running that this session started

The 7 long-lived python processes (elapsed times 1h+ / 4h+ / 24h+)
are the production `arc.sh` / `huntaegis.sh` managed daemons —
scribe, analyzer, mailer for each stack — unrelated to this session.
Confirmed via `ps -o pid,etime,cmd`.

---

## Next-session natural order

1. Finish Hunt backend brand extraction (~3-4 hours, same pattern as
   Arc's `b606d12`).
2. Frontend brand extraction on both stacks (~4-5 hours per the
   earlier report): new `frontend/lib/site.ts` reading
   `NEXT_PUBLIC_SITE_*` env vars, update `cardConfig.ts` and ~60-90
   callsites per stack, wire the Dockerfile build args, verify with
   a browser check.
3. Update the sales page tier-2 lead-in from "budgeted into the week"
   to "one afternoon of brand-swap, four days of real customization"
   once the frontend extraction actually delivers on that claim.
4. `site_config` adoption sweep (parity audit E.5) — the ~15
   Redis-env holdouts and the ~12 port-default holdouts per stack.
5. Any of the three open items (§-np 2, cycle_minutes, 65/day silent
   loss) that Ross wants prioritized.
