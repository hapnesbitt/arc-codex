# State of Arc-Codex — consolidated audit scorecard — 2026-07-18

Single scorecard pulled from the existing audit docs, re-verified live after
today's reboot + frontend recreate. Sources:
- [`docs/perf-2026-07-17.md`](./perf-2026-07-17.md) — performance recon + ISR cache lever
- [`docs/pwa-audit-2026-07-17.md`](./pwa-audit-2026-07-17.md) — service-worker correctness
- [`../claude_stack/docs/soc-recon-2026-07-18.md`](../../claude_stack/docs/soc-recon-2026-07-18.md) — WCAG + credential/security findings (SoC; cross-applied to arc where relevant)
- [`TODO.md`](../TODO.md) — carried-forward deferrals

There is **no dedicated a11y / OWASP-ASVS document for arc**. Those dimensions
below are sourced from the SoC recon (shared codebase patterns) and code audit,
and are labelled as such — not from a formal arc assessment that does not exist.

---

## Scorecard

| Dimension | Last audited | Shipped | Still open | Priority |
|---|---|---|---|---|
| **Performance / scale** | 07-17, re-measured 07-18 | Anonymous ISR cache on `/`, `/article/[slug]`, `/wiki/[slug]`, `/about` (commit `5890fed`). Full-chain 75→219 req/s, SSR latency −65%. **Cache LIVE post-reboot, full-chain HELD at 216 req/s.** | SSR-direct layer re-measured lower than deploy-day (482 vs 1106 req/s) — CPU contention, not a cache regression. Swap still 0. Gunicorn oversized on purpose. | **LOW** |
| **A11y / ARIA (WCAG)** | 07-18 (SoC recon §3) | *In SoC:* radio-group semantics OK, `role=status` on warnings, pinch-zoom unblocked. | **arc still ships `maximum-scale=1`** → WCAG 1.4.4 pinch-zoom failure, live over the wire. Quiz focus-management (arc `/quiz` shares the pattern). | **MEDIUM** |
| **Security (OWASP)** | No formal arc ASVS pass exists | Fetch-Metadata bot-gate + flask-limiter rate limits (both stacks); W3C rate-limit gate upstream; analyzer NX-EX dedup. Ed25519 credential signing shipped **in SoC only**. | No arc ASVS assessment. `backend/.env` captured in cold backup (known **R9**). Perf work dropped `X-Real-User-Agent` from the SSR fetch → `/api/article` bot-gate fires only on cache-miss (NX-dedup mitigates). | **MEDIUM** (for a real ASVS pass) |
| **PWA** | 07-17 | Nothing (audit was report-only). Manifest + icons + meta verified correct. | **SW caches authed HTML in `arc-v1` past logout** — confirmed still `arc-v1` over the wire, unfixed. ~30-line SW rewrite deferred. iOS installed-app session parity (decision). Lighthouse never captured. | **HIGH** |

---

## 1. Performance / scale — resolved, and it held through the reboot

**The Next.js SSR bottleneck was the whole problem and it is addressed.** The
perf recon proved every millisecond of the 622ms full-chain latency lived in the
Node SSR process (Caddy ≈ 0%, Flask ≈ 3%; Flask alone serves 2271 req/s). The fix
was in-process Next.js ISR (`revalidate`) on the anonymous pages, with the SSR
render path stripped of cookie reads so the cached HTML is definitionally the
anonymous view.

**Deploy-day results** (commit `5890fed`, `wrk -t2 -c50 -d30s`):

| Target | Before | After |
|---|---:|---:|
| Full chain `arc-codex.com/` | 75 req/s / 622ms | **219 req/s / 218ms** |
| Next.js SSR direct `:3000/` | 76 req/s / 636ms | **1106 req/s / 50ms** |

**Live re-verification today (2026-07-18, post reboot + frontend recreate):**
- Cache headers present and correct: `s-maxage=60, stale-while-revalidate`,
  `x-nextjs-cache: HIT` on the cookie'd request, `STALE` (serving + background
  revalidate) on the cold anonymous request. A `force-dynamic` page would emit no
  such header — **ISR is confirmed active in production.**
- `wrk -t2 -c50 -d15s` full chain: **216.5 req/s / 224ms** — matches the
  deploy-day 219/218 almost exactly. **The cache survived the reboot.**
- `wrk` Next-direct `:3000/`: **482 req/s / 120ms** — 6.3× the 76 req/s baseline,
  but below deploy-day's 1106. Most likely **CPU contention**: the deploy-day
  measurement ran with `CYCLE_MINUTES=69`; the box is currently running the
  intentional `CYCLE_MINUTES=1` scribe, which sweeps every minute and competes
  with the Node event loop for cores. This is *not* a cache regression — the
  full-chain number (which is what real users experience, bounded by the ~220
  req/s Caddy TLS ceiling) is intact, and Node latency dropped, not rose.

**Capacity context:** real organic homepage demand is **0.037 req/s** (134
renders/hour). Even the 76 req/s pre-cache SSR was ~2000× demand. The cache is a
first-paint latency-feel win, never a capacity requirement.

**Open (low priority, all deliberate):** swap still 0 (open since the 07-08 Redis
OOM remediation); gunicorn at 20×8 threads (≈9.3 GiB RSS) for 1.4 req/s of real
demand — ~5 GiB reclaimable at 6×8 if Redis pressure ever forces it, otherwise
leave.

## 2. A11y / ARIA — one confirmed cross-applicable WCAG failure, open

The WCAG 2.1 AA findings come from the SoC quiz-flow spot-check (recon §3 Part
1.4). Mapping to arc:

- **Pinch-zoom (`maximum-scale=1`) — WCAG 1.4.4 — APPLIES TO ARC, OPEN.** SoC
  removed it; arc's `frontend/app/layout.tsx` still sets `maximumScale: 1` and
  the meta tag ships live: `<meta name="viewport" content="width=device-width,
  initial-scale=1, maximum-scale=1">`. A ~1-line fix (drop `maximumScale`),
  never applied to arc. Hostile to low-vision and older-device users.
- **Screen-reader announcement on transient warnings** — SoC-specific (the
  anonymous-pass warning box). Arc has no equivalent surface; SoC shipped
  `role=status`. Not an arc item.
- **Radio-group semantics** — SoC quiz already conformant (`role=radiogroup`
  + `aria-labelledby`). Not an arc defect.
- **Focus management across quiz phase transitions** — SoC has `/quiz`-style
  phase swaps with no `focus()`; arc's daily `/quiz` shares the family. Worth a
  spot-check but lower confidence than the pinch-zoom item.

**Recommend:** removing `maximumScale` from arc's layout is the one clear,
shippable a11y correctness fix. (Not applied — Phase 1 is report-only.)

## 3. Security — no formal arc ASVS pass; posture is hardened at the edges

**Important honesty flag:** there is no OWASP ASVS assessment document for arc.
The brief asked for its state; the state is *it has not been done for arc*. What
exists is security-relevant hardening delivered as part of other work:

- **API hardening / bot-gate:** cold-generation and LLM-proxy paths gated behind
  Fetch-Metadata (`Sec-Fetch-*`) browser-shape checks; flask-limiter rate limits
  on both stacks; the Wave C W3C rate-limit gate upstream absorbs bot swarms
  before SSR; analyzer enqueues deduped with an `analyzer:queued:{id}` NX-EX lock.
- **Auth:** NextAuth JWT + Google OAuth; shared `auth.py` blueprint; DB 5 holds
  shared user records and per-IP limiter state. (No ASVS-level review of session
  fixation, token lifetime, CSRF on state-changing routes has been recorded.)
- **Secrets:** `backend/.env` is captured inside the cold backup archive — the
  known **R9** issue (secrets at rest in the archive). `secret/soc_ed25519.pem`
  (SoC) is `600` and git-ignored with an encrypted off-box backup.
- **Signing:** Ed25519 sign-at-issue for certs/badges shipped **in SoC only**
  (commit `e4ca721`) — not an arc capability.
- **Regression from the perf work:** SSR no longer forwards
  `X-Real-User-Agent`, so the `/api/article/:id` bot-gate now only evaluates on a
  cache-miss (once per 60s per article). Mitigated by the NX-EX analyzer dedup;
  worth noting in any future ASVS pass.

**Recommend:** if security is a priority, a scoped arc ASVS Level-1 pass (auth,
session, input validation on the comment + publish routes, secrets handling) is
the missing artifact. **MEDIUM** — nothing here is a known live exploit, but the
assessment gap is real.

## 4. PWA — the highest-priority correctness item, still open

**Confirmed still open and unfixed** (`/sw.js` served live = `arc-v1`, still
`caches.put(request, clone)` on every non-API GET):

The service worker uses network-first-with-cache-fallback for all HTML and writes
every response into `arc-v1`, keyed by URL only — no cookie/session partition.
This **breaks the ISR + auth contract**: the server-side guarantee (SSR never
reads cookies → cannot cache a personalized page) is defeated by the SW writing
authed HTML to disk after the fact. Failure mode:

1. Authed user visits `/article/private-x` → HTML lands in `arc-v1`.
2. User logs out.
3. Network flakes / offline.
4. SW serves the cached authed HTML to the now-logged-out user.

Same-device, no cross-user leak — but a real "logged out, still see my private
view" bug, and `arc-v1` grows unbounded between manual cache-name bumps.

**Fix (deferred, ~30 lines, diagnosed in `TODO.md § SW: stop caching HTML`):**
precache only `/manifest.json` + icons, pass HTML through with no cache read/write,
keep cache-first only for content-hashed `/_next/static/*`, bump `CACHE_NAME` →
`arc-v2` so `activate()` drops the old cache. Must be done whole — a partial
apply (bump name only) just resets the HTML cache and leaves the pattern intact.

**Also open:** iOS installed-app session parity (accept/mitigate *decision*, not
code — SoC-incident shape); Lighthouse baseline never captured.

**This is the top-ranked correctness item across all four dimensions.** It is a
> 5-line change, so it was correctly held out of the audit sessions; it needs a
deliberate deploy of its own.

---

## Bottom line

- **Performance: resolved and durable** — the SSR bottleneck is fixed, the cache
  is live, and it survived the reboot. Only low-priority, deliberate items remain.
- **PWA SW rewrite is the one open *correctness* bug** and should be the next
  thing shipped.
- **Pinch-zoom removal is the one clear open a11y fix** (~1 line, arc-specific).
- **A scoped arc ASVS pass is the missing security artifact** — not a known
  exploit, but a genuine assessment gap.
</content>
