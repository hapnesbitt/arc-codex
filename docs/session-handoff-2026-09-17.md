# Session handoff — 2026-09-17

Restart-resumable notes from the 2026-09-17 session, which started with
the e2b/e4b bench and ended near the session limit with the essay-pass
verification still in flight.

---

## Commits landed this pass

- **Arc (this commit):** `docker-compose.yml` + `frontend/lib/site.ts`
  brand-env plumbing fix, `frontend/app/about/contact/page.tsx` LinkedIn
  row, this handoff doc.
- **Hunt (see hunt repo):** `.gitignore` + `docker-compose.yml` +
  `frontend/lib/site.ts` mirror of the same brand-env fix.

The .env files at each stack root (holding `NEXT_PUBLIC_SITE_*`
brand values) are gitignored and per-host — do not commit them.

---

## Fleet decision — e2b stays, e4b lives on warden

Bench on warden, same real 5,481-token prompt (13,731-char article +
full A.R.C. unified prompt), production call shape:

| Model | Wall | Prompt tps | Gen tps | Gen tokens | Response chars |
|---|---:|---:|---:|---:|---:|
| gemma4:e2b | 179 s | 55.5 | 9.6 | 764 | 3,796 |
| gemma4:e4b | 347 s | 29.5 | 5.2 | 715 | 3,974 |

**e4b is 1.9× slower on both prefill and decode.** Output length
near-identical (~5% longer chars, ~6% fewer tokens). At one slot e4b
would cap analysis at 10.4/hr, making the inference host the ceiling.

**DECISION:**
- **e2b stays on resolute and spectre.** No e4b pull on either.
  Resolute is at 90% disk (49 GB free) and can't spare it; spectre's
  14 GiB / no swap would leave only ~3 GB after e4b weights + 16k KV.
- **e4b lives on warden**, used only for the essay pass. Warden has
  the RAM (24 GB) and disk headroom; e4b already pulled.

Bench outputs sit in `scratchpad/bench_out_gemma4_{e2b,e4b}.txt` for
quality comparison.

---

## Essay pass — scope (approved), verification still running at handoff

### Structural guardrail (the important one)

Reuse `run_broadcast_script`'s pattern: signature is `(red, blue,
purple)` with **no `original_text` parameter**. The constraint is
enforced by the function shape and the prompt template (no
`--- ARTICLE TEXT ---` block), not by prompt language. A caller
cannot pass source prose because there is nowhere to put it.
`run_broadcast_script`'s docstring at `backend/scribe.py:1877-1898`
is the reference implementation.

### Scope

- **Input:** one article's `red_team_analysis` + `blue_team_analysis`
  + `purple_team_analysis`. Nothing else.
- **Output:** original Arc-voiced essay addressing what the source
  left unanswered. Not a summary, not a rewrite of Purple. Target
  ~500–1500 words. Wall time on e4b: ~5–8 min per essay.
- **Model:** gemma4:e4b on warden. Fine to swap the loaded model
  with Hunt's e2b for essay batches; ~1 s reload each direction.
- **Trigger:** on-demand from the UI. Per-user daily cap +
  per-article short-circuit (cached, not regenerated).
- **Storage:** `article:{id}.essay_analysis` + `.essay_generated_at`
  + `.essay_model`. New `essay:queue` Redis LIST, drained by
  `essay_writer.py` (single consumer). Same BRPOP + dedup-set as
  `analyzer.py`.
- **Surfacing:** IntelligenceCard is a stacked accordion (not tabs).
  Add a fourth accordion section, "Essay" / "Arc's Take", visible
  only when populated. Deep-link `#essay-{id}`. Wiki
  `/wiki/[slug]` pages include the essay in their `<details>` block
  when present.
- **Failure UX:** silent — missing essay renders as no accordion
  section, matching how missing analysis is handled.
- **Sentinel interaction:** suppress essays on SYNTHETIC-verdict
  articles.

### Chimera correction — trigger option B is dead

Automatic trigger by `chimera_score` threshold does not fit.
Arc's chimera_score is **readability difficulty (0–100)** per
`kasmir7.py:223-234` and `_chimera_color`, not essay-worthiness. A
dense financial disclosure and a deeply-reported investigation both
score high. Wrong signal — do not wire chimera to the essay
trigger.

### Verification run — completed, verdict: **RECONSIDER**

Ran 2026-09-17 05:31–05:44, 5 articles, gemma4:e4b on warden,
prompt built from R/B/P only (no `original_text` in the signature
or the template). Wall-per-essay: 82 s to 231 s (mean ~119 s —
faster than the 5–8 min estimate, because the model self-
terminated at 277–375 words instead of the 500–1500 word target).
Outputs preserved at `docs/essay-verification-2026-09-17/*.txt`.

**Failure-mode counts:**

| # | Article | Source leakage | Rewrite-of-Purple | Fabricated causal |
|---|---|---|---|---|
| 1 | MIRI: If Anyone Builds It | 0 | partial (mid-paragraph) | 0 |
| 2 | Producer/heiress fraud | 0 | **strong** (whole essay) | 0 |
| 3 | Betelgeuse / ALMA hotspots | 0 | partial (rewrote bridge Qs) | 0 |
| 4 | AI in Agriculture | 0 | **strong** (whole essay) | 0 |
| 5 | Aliencell / CHITUBOX E1 | 0 | **strong** (whole essay) | 0 |

- **Source leakage: 0/5** — structural (red, blue, purple)
  guardrail held perfectly. The no-`original_text` signature is
  the right architectural choice; keep that for any future essay
  work.
- **Rewrite-of-Purple: 5/5** — 3 strong, 2 partial. Every essay
  drew heavily from Purple's phrasing and structure. Essay 2
  lifts Purple's "the story's power derives not just from the
  alleged actions themselves, but from the multiplicity of
  external actors" nearly verbatim; Essay 4 rewrites Purple's
  "reliance on automated insights might lead to systemic blind
  spots… creating externalities across the supply chain" as its
  own prose; Essay 5 rewrites Purple's "reframing laser tools as
  extensions of creative thought rather than industrial
  apparatuses" as "rebranding laser tools away from looking like
  industrial gear and toward feeling more like extensions of an
  artist's own mind." Not a subtle issue — pervasive.
- **Fabricated causal chains: 0/5** — model was appropriately
  grounded. Speculation stayed within what R/B/P established.

**Verdict per the threshold set in the scope report** (>2/5 on any
mode = prompt problem the model won't fix): **do not build the
machinery yet.** The essay pass with a 5B-8B local model on R/B/P
alone produces longer Purple restatements, not essays. The problem
is not the trigger, not the storage, not the surfacing — the
essay-length prompt does not extract new material from a
description-length R/B/P summary. Purple already IS the analytical
take; asking the model to write a longer one from just Purple is
asking it to pad.

**Options to reconsider before building:**
1. **Feed more source-derived material** — pass the article's own
   headline, TL;DR, and Sentinel counter-analyst comment alongside
   R/B/P. Adds substrate without ceding the structural guardrail
   (no source prose). Risk: still likely to rewrite whatever we
   feed.
2. **Ask a genuinely different question** — the prompt currently
   asks for "what the source left unanswered," but at essay length
   the model reaches for Purple's bridge questions and paraphrases
   them. Try: *what does this article change about a related
   ongoing story that Arc has been tracking?* — forces the model
   to bring in structure R/B/P doesn't carry.
3. **Upgrade to cloud (gemma4:31b-cloud)** for the essay pass only
   — more capacity to synthesize rather than restate, at cloud-
   quota cost. Warden essay pass then becomes cloud escalation
   with e4b as the local fallback.
4. **Retire the essay pass idea.** If R/B/P + on-demand doesn't
   produce essays that read as new analysis, the concept doesn't
   pay for itself. The bench decision to reserve warden for e4b
   still stands — e4b just gets used differently (or not).

Recommend: try (2) as a one-hour prompt-only iteration before
committing to (1) or (3). If (2) also produces Purple restatements,
the concept needs the (3) upgrade or the (4) retirement.

Reproduction command (idempotent — rerun overwrites the numbered
output files in scratchpad, but the frozen 2026-09-17 copies in
`docs/essay-verification-2026-09-17/` stay put):
```
python3 /tmp/claude-1000/…/scratchpad/essay_verify.py
```
(The scratchpad path itself is session-scoped; if the session is
gone, the script sits next to the outputs at
`scratchpad/essay_verify.py` — copy it out first before the
scratchpad vanishes.)

---

## Regression fixed (both stacks): white-label brand env plumbing

Commit `8a4b8fb` (Sep 16, brand extraction) added three
`NEXT_PUBLIC_SITE_*` ARG/ENV declarations in Dockerfile.frontend but
did not wire them into `docker-compose.yml`'s build.args. `site.ts`
used `??` (nullish coalescing) which does not fall back on empty
strings — so Docker's empty ENV passed through unchanged, and
`layout.tsx:27`'s `metadataBase: new URL(site.baseUrl)` threw
`ERR_INVALID_URL` on `input: ''` during `/_not-found` collection.
Any `arc build --clean` since that commit has been failing this
way — the running container is from before the regression, which is
why prod is unaffected.

Fix, both stacks:
- `docker-compose.yml` — three `NEXT_PUBLIC_SITE_*` build.args, no
  default (per Ross's direction: no silent Arc default in Hunt).
- `frontend/lib/site.ts` — `requireBrandEnv()` throws with a
  message naming the variable and where to set it, instead of
  ERR_INVALID_URL three files away in layout.tsx.
- Compose-root `.env` — new file, gitignored, holds per-stack
  brand values. Hunt's `.gitignore` didn't cover a root `.env`;
  added the line.

Arc rebuilt + deployed + verified. Hunt fix source-only.

---

## LinkedIn: contact link back, poster/OAuth/share still retired

Memory `linkedin-retired-2026-07-15` updated to reflect the split:
`frontend/app/about/contact/page.tsx` now has a passive LinkedIn
row for the new profile `rossicusnesbitticus`. The 2026-07-15
retirement of the poster, OAuth provider, and share button
remains in force — only the contact-page mention came back.

---

## Still open / unfixed

- **Kokoro → M1 (fleet-doc item 4).** M1 unreachable via SSH — the
  FileVault two-tier gate is active (sshd up on port 22,
  `~/.ssh/authorized_keys` on the encrypted user volume until
  someone logs in). `curl http://192.168.1.185:11434/api/tags`
  returns `{"models":[]}` — Ollama up, no models. Resolute has no
  `~/.venvs/kokoro/`. `audio-backfill.service` inactive since
  2026-09-03. Cannot verify the target shape from here — needs
  someone to log into the M1 and either install launchd+Kokoro on
  M1, or reinstate the older daemon-on-resolute-shells-to-M1
  pattern.

- **Hunt frontend build never run against the fix.** Source
  changes landed on Hunt; next `huntaegis.sh build` will exercise
  them. Won't fail on the regression; may fail on the
  `/uploads/huntaegis-default.jpg` path if that file isn't in
  Hunt's `frontend/public/uploads/`. Verify before rebuilding
  Hunt.

- **Hunt `.gitignore:59` un-ignores** `arc-codex-default.jpg`
  inside Hunt's `frontend/public/uploads/` — a stale Arc asset
  tracked under Hunt's tree, exactly the same shape as the build
  regression white-label leak. Unfixed this session.

- **Resolute disk at 90%**, 49 GB free. Not urgent, but constrains
  the LightBox relocation below and blocks a resolute-side e4b
  pull (which the fleet decision above already rules out anyway).

- **`@tsparticles/react@3.0.0`** deprecated → 4.1.1 (surfaced in
  the `--clean` build stream). Minor; can be bumped whenever
  frontend deps get a pass.

- **Resolute's role.** Recommendation recorded as **nothing** —
  resolute stays a serving box (frontends, mailers,
  character_builder council on localhost:11434, redis, solr,
  cron). character_builder is already an inference client of
  resolute-local Ollama via `[inference].council_url`; that
  continues unchanged. Revisit if essay-length lands and wants
  its own lane.

- **LightBox relocation report.** Not started per Ross's queue.
  Scope stashed at
  `scratchpad/lightbox_relocation_scope.md` — the scratchpad is
  session-specific and will vanish, so the scope is also inlined
  here for durability:

  > **LightBox relocation — report scope (queued):** resolute is
  > at 90% disk / 49 GB free, and LightBox's uploads are the
  > largest single tenant. Report whether LightBox should move,
  > and where. Cover:
  >
  > 1. Current LightBox uploads size on resolute + what freeing
  >    it does to the 90% number.
  > 2. **Warden as destination.** Two working optical drives
  >    (spectre has none), and LightBox's two ripper daemons
  >    poll physical drives, so the services must live where the
  >    discs are. Say whether adding four systemd units +
  >    ripping to a box already running Hunt's analysis, Arc's
  >    broadcast scripts, and (slated) the essay pass makes
  >    warden the fleet's bottleneck.
  > 3. **Spectre as storage-only.** Services stay on resolute,
  >    uploads move to spectre. Network reads per video request;
  >    Caddy or app changes.
  > 4. **Redis constraint.** LightBox's Redis state is on
  >    resolute's loopback-bound instance. Say whether that
  >    still constrains the move (or whether the loopback
  >    binding can be relaxed cleanly).
  > 5. Recommend one, with the disk numbers attached.

---

## Files touched this session (all committed by end of session)

Arc:
- `frontend/app/about/contact/page.tsx` — LinkedIn row
- `frontend/lib/site.ts` — throw-on-missing brand env
- `docker-compose.yml` — three brand build.args
- `docs/session-handoff-2026-09-17.md` — this file
- `.env` — gitignored, per-stack Arc brand values (new file)

Hunt:
- `frontend/lib/site.ts` — throw-on-missing brand env
- `docker-compose.yml` — three brand build.args
- `.gitignore` — added `.env` line
- `.env` — gitignored, per-stack Hunt brand values (new file)
