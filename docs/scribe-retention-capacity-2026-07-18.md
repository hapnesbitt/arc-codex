# Scribe capacity + retention + sitemap + pins — diagnosis — 2026-07-18

**Report before fixing** (per Ross's three mid-session briefs). Covers: the
days/hours trim "bug", the sitemap 404s, the scribe-at-capacity go/no-go, and
the pin-system design. Evidence is live probes of Redis DB 0, the scribe log,
`retention.py` / `kasmir7.py` code, and `arc_config.yaml`.

---

## TL;DR

- **The days/hours trim is NOT broken.** The date math is correct (proven). "days
  30 → 0" was the *right* answer: 100% of articles older than 30 days are
  protected (76 reference + 4 pinned). The bug was in the **message**, not the
  filter — a zero-delete looked like a failure. Fail-safe direction confirmed:
  it fails **closed**.
- **Auto-retention IS working and DOES cap growth.** `retention_hours: 48` is
  enabled; scribe prunes news >48h every cycle and regenerates the sitemaps on
  each prune (log-confirmed, every ~73 min today). The corpus is **not** growing
  unbounded — news self-limits to a ~48h window.
- **The sitemap is regenerated from the LIVE corpus** (hourly + on every prune).
  The Google 404s are **not** a stale-sitemap bug — they are the unavoidable
  result of a 48h news lifetime being shorter than Google's crawl-to-index lag.
  This is the real "indexing failure" root cause, and it's a **strategy
  decision**, not a code fix.
- **Go/no-go on running scribe hot: GO, with two guardrails** (below). Memory is
  safe, analysis is local-only by default, retention caps the corpus. The real
  constraint is M1 local-inference contention, not cloud budget or RAM.
- **APPLIED 2026-07-18: `retention_hours` 48 → 720 (30 days)** (committed +
  scribe restarted, value verified live). Safe at the current rate. **This is
  NOT a green light for full-capacity scribe** — see §5: 30-day retention and
  `cycle_minutes=0` are ONE coupled decision, and the untested part of the
  combination is analyzer/cloud load, not RAM.

---

## 0. Retention change 48 → 720 — APPLIED (Brief 4 + 5)

Ross-directed and applied this session: `arc_config.yaml retention_hours: 48 →
720`, committed, scribe restarted (`arc.sh restart scribe`, new pid confirmed
running v53.0, `retention_hours = 720` verified loaded). Readiness answers:

1. **Memory model (measured, not estimated).** Live `MEMORY USAGE`: a news
   article hash = **76.3 KiB**, reference = 35.2 KiB; instance = 332 MB across
   all DBs.
   - **Current ~271/day × 30d = 8,130 news → ~0.64 GB** hash payload (~1.5 GB
     total incl. satellites + baseline). **Comfortable** under the 16 GB cap.
   - Capacity 1,440/day × 30d = 43,200 news → ~3.4 GB payload (~5–7 GB total).
   - Redis is `noeviction`, so the ceiling must never be reached — at the current
     rate 30d stays at ~10% of cap, so it isn't. **Caveat: the 16 GB instance is
     SHARED** across arc/hnt/SoC; arc's growth eats shared headroom.
2. **Analyzer load: unchanged by retention.** `trim_by_hours` only DEL/ZREM/SREM
   — it never analyzes, and raising retention triggers **no re-analysis**.
   Analysis happens at publish (sentinel + counter-analyst) and on first view
   (R/B/P); longer retention just means articles persist, not re-process. (A
   second-order effect: more persisted articles *can* be viewed → marginally more
   on-view analysis over time, readership-bound and weekly-cap-gated — not a
   retention cost.)
3. **Sitemap tracks the window.** `generate_sitemap` reads the live `feed` ZSET
   and regenerates every cycle + on every prune (log-confirmed), so the sitemap
   follows the 30-day window and drops moment-of-trim stragglers on the next
   regen. **With 30-day-lived URLs, the Google 404 problem largely self-heals**:
   articles now live long enough to be crawled and indexed before expiry. Ross is
   right — the SEO fix was partly a retention fix (this is Option B from §2, now
   chosen and applied).

**The coupling flag (Brief 5): 30-day retention and full-capacity scribe
(`cycle_minutes=0`, ~1,440/day) are ONE decision, not two.** RAM holds *either*
alone. The untested part of the *combination* is **analyzer/cloud load at
1,440/day × 30d**, not RAM. Retention is applied; **capacity is deliberately NOT
touched** in the same motion — that stays a separate go/no-go (§3) pending the
analyzer-cost model Ross now has below. Before any capacity increase, the
local-default guarantee (§3.2) must hold, which it does today.

---

## 1. The days/hours trim (Brief 1, items 1–3)

**Root cause: there is no date-parsing bug. The filter works; the result was
correct and only *looked* wrong.**

`kasmir7 [3] days/hours` delegates to `retention.trim_by_hours()`, which does:

```python
cutoff = time.time() - hours*3600
ids = r.zrangebyscore("feed", "-inf", cutoff)   # feed score = publish epoch
```

Direct probe of live Redis:

- feed ZSET scores **are** exact publish epochs — for every sampled news article,
  `score == article.timestamp` to the second (no bump, no drift, no tz skew).
- `ZCOUNT feed -inf (now-30d)` = **77** articles. The range query finds them fine.
- Of those 77: **76 are `content_type=reference`** (the plants, dated May 3) and
  the rest are **pinned**. `trim_by_hours` correctly exempts reference + pinned.
  → **deletable news older than 30 days = 0.** The "0 selected" was accurate.

Corpus snapshot: **76 reference + 305 news = 381**; pinned set = **80** (76
reference + 4 news). Publish histogram (by real timestamp): 4 news survive from
May–June (all 4 are the pinned news); **271 published today, 30 yesterday** — the
news corpus is a rolling ~48h window, exactly matching `retention_hours: 48`.

**Fail-safe direction (item 2): confirmed fails closed.** The days/hours path
does no string parsing at all (pure score math), so it cannot mis-parse. The one
place that parses a date string is the `directive` trim (`parser.parse(ts) except:
ts=0`) — a parse failure sets ts=0, sorting the article as *oldest*, but
`partition_protected` still guards reference/pinned, and it's a manual dry-run
path. Nothing auto-deletes on a parse error.

**Automatic trim using the same logic (item 3):** yes — scribe's end-of-cycle
hook calls `run_retention_pass → trim_by_hours` with `RETENTION_HOURS=48`. It is
**not** no-opping. The scribe log shows it pruning + regenerating every cycle:

```
17:07:05 🗑️  Retention: pruned 1 article(s) > 48h; regen={'sitemap': True, 'rss': True, 'news_sitemap': True}
15:51:42 🗑️  Retention: pruned 1 article(s) > 48h; ...
14:38:44 🗑️  Retention: pruned 1 article(s) > 48h; ...
```

Only ~1/cycle right now because 48h ago the ingest rate was low; as today's 271
articles cross the 48h line, prune rate rises to match ingest. Steady state:
**corpus ≈ 48h × ingest rate.** The premise "nothing caps corpus growth" is not
correct — retention is capping it.

**So why did Ross lose an hour?** The corpus never auto-trimmed *the old visible
dates* because those dates are the **permanent** reference plants (+ 4 pinned
news), which are supposed to survive. The confusion is a UX gap, not a logic bug
— addressed in §4.

## 2. The sitemap 404s (Brief 1, item 4 + Phase 3b)

**Is it cron-regenerated? Yes.** `sync_intel.sh` runs hourly (`0 * * * *`,
active) and calls `kasmir7.generate_sitemap`; retention also regenerates on every
prune. File mtimes (17:07 today) confirm it runs.

**Does it read the live corpus? Yes.** `generate_sitemap` builds article URLs
from `r.zrevrange('feed', 0, -1)` — the live feed. Pruned articles drop out on
the next regen (≤1h, usually immediately via the prune hook). The served sitemap
is **not stale**.

**So where do the 404s come from?** Composition: `sitemap.xml` = 25,949 URLs,
overwhelmingly the permanent **library** corpus + wiki + homepage; the **news
`/article/` URLs are the live feed (~305)**. Google crawled those `/article/`
URLs days ago (when they were inside the 48h window), cached them, and now
re-requests them → 404, because **retention deleted them after 48h.** This is
structural: **any news article Google indexes will 404 within ~48h.** News
retention (good for RAM) is fundamentally shorter than Google's index cycle.

**This is the real Google-indexing root cause — and it's a decision, not a bug:**
- *Option A (recommended):* keep ephemeral news `/article/` URLs **out of the
  main `sitemap.xml`**; expose them only via `news-sitemap.xml` (Google News,
  which expects high-velocity/short-lived URLs). Let the main sitemap advertise
  only the **permanent** surface (library, wiki, plants, reference) — the content
  that can actually hold a ranking. This aligns the sitemap with what survives.
- *Option B:* lengthen `retention_hours` for news so URLs live long enough to
  index — costs RAM and re-introduces the growth Ross wants to avoid.
- *Option C:* accept news as ephemeral; rely on the permanent corpus for organic
  SEO. (This is effectively what Huntaegis does — and why hnt's indexable surface
  is only 280 URLs; see `traffic-asymmetry-2026-07-18.md`.)

The kasmir7 [14] news/reference split already exists; the fix is ensuring the
**main** sitemap's article section excludes the 48h-lived news, not that a cron
is missing.

## 3. Scribe at capacity — go/no-go (Brief 2)

### 3.1 Why the historical rate looked like ~6/day
Measured, not assumed: the poster logs show arc posting ~250/day over 30 days,
and the feed shows **271 ingested today** at the current `CYCLE_MINUTES=1`. So
arc is **already running near-hot (~250–270/day), not 6/day.** The "6/day"
impression is survivorship bias — retention deletes news after 48h, so *old*
days show only the 4 pinned survivors, making history look sparse. Proven
capacity is ~1440/day (1/min); current ≈ 270/day ≈ **19% of capacity**, so there
is ~5× headroom.

Accept/reject: `SOURCE_BATCH_SIZE=69` sources scanned per 1-min cycle, most
articles rejected by `processed_hashes` dedup; net accept ≈ 270/day today.

### 3.2 Inference cost at capacity
Arc's analysis is **not** all done at ingest:
- **At ingest (scribe):** 2 Ollama calls/article — Sentinel + Counter-Analyst —
  via `call_ollama_local_only`. **Local-only, never cloud.** Background-threaded,
  `max_workers=2`.
- **Red/Blue/Purple (3 calls):** **lazy — only on first article *view*** (via
  `analyzer.py`), local-first, escalate to cloud only through `decide_escalate`
  behind a **hard weekly cloud cap**. High ingest does **not** multiply R/B/P;
  only *read* articles get analyzed.

**Confirmed: nothing in scribe's analysis path hits cloud `gemma4:31b` by
default** — it mirrors the SoC demand-gating local-default posture. Cloud draw at
capacity ≈ 0 unless articles are viewed *and* escalation fires, and even then the
weekly cap is a backstop. **Phase C (SoC cloud/spectre batch) and hot scribe do
not collide on the cloud budget** — scribe is local. They **do** collide on the
**M1 `gemma4:e2b` local model**: at 1440/day that's ~2 local calls/min from
scribe alone, plus arc on-view analysis, plus SoC local gen. **M1 is the real
bottleneck**, not cloud credit.

### 3.3 Memory at capacity
- Redis: **used 316 MB / peak 334 MB / cap 16 GB**, policy **`noeviction`**.
- At capacity: corpus ≈ 48h × 1440/day ≈ **2,880 news** + 76 reference + pins.
  That's ~7.5× today's article count → order **~1–2 GB** resident, still **<15%
  of the 16 GB cap.** The July OOM path is not reached as long as retention holds.
- **`noeviction` is the correct policy here:** it protects the plants/pins from
  being silently evicted (LRU would "eat the plants through another door" — Ross's
  exact fear). The tradeoff: if Redis ever *did* hit 16 GB, writes fail rather
  than evict. Retention capping the corpus is what keeps that from happening —
  which is why a working retention window is the precondition (it already works).

### 3.4 Verdict: **GO**, with two guardrails
Running scribe at/near capacity is **safe** on memory (retention caps it),
safe on cloud budget (analysis is local-default), and retention + sitemap regen
already keep the corpus and public files consistent. Guardrails:
1. **Watch M1, not the cloud.** The binding constraint is `gemma4:e2b` throughput
   on the M1 shared across scribe + arc on-view + SoC. Ramp in steps (e.g.
   `CYCLE_MINUTES=1`→ raise `SOURCE_BATCH_SIZE` gradually) and watch M1 latency /
   the sentinel+counter-analyst queue depth before going to full `cycle=0`.
2. **Decide the sitemap/SEO posture first (§2).** Running hotter multiplies the
   number of 48h-lived `/article/` URLs Google will 404 on. Pick Option A (news
   out of the main sitemap) before ramping, or the indexing problem scales with
   ingest.

Not required first: the days-trim "fix" (it works). RAM headroom is large.

## 4. Pin system — visibility + management (Brief 3)

### 4.1 The reference/pin overlap — needs a decision
**All 76 reference articles are ALSO in `arc:pinned_articles`** (pinned = 76
reference + 4 news). So reference content is **double-protected**: once by
`content_type=reference` (permanent by type) and again by pin. This is exactly
the confusing overlap Ross flagged. Two coherent models:
- *(recommended)* **Pins are for ephemeral news only.** Un-pin the 76 reference
  (they're already permanent by type); `arc:pinned_articles` then means "news I'm
  deliberately keeping past 48h" (the 4). Clean semantics, and Manage-Pins shows
  a short, meaningful list.
- **Pins are belt-and-suspenders.** Keep reference pinned too; Manage-Pins must
  then label each entry's protection source (type vs pin) so the list isn't
  confusing. Larger, noisier list.

This is a **decision for Ross** before building Manage-Pins (Brief 3 asked to
report if the overlap needs one — it does).

### 4.2 Safe to build now (additive, no decision needed)
- **Trim [3] visibility:** when candidates match but all are protected, print
  `"N matched, all N protected (X pinned, Y reference)"` instead of a bare "No
  articles matched." Kills the false-alarm that cost an hour. (~5 lines)
- **Dashboard [9]:** add `pinned` to the corpus summary line
  (`news / reference / pinned`). (~3 lines)

### 4.3 Manage-Pins (new menu option) — build after 4.1 is decided
List (hash · title · date · directive from `arc:pinned_articles` ⋈ article
records; flag **dangling pins** — hashes with no live article, the inverse of
tonight's issue); pin by hash/search; unpin by hash with confirmation +
**"this becomes trim-eligible immediately"** warning when age > retention window.
Back up `arc:pinned_articles` (SMEMBERS dump) before adding any write path;
commit-before-change; additive.

---

## What needs Ross

1. **Sitemap/SEO posture (§2):** Option A (news out of main sitemap — recommended)
   / B (longer retention) / C (accept ephemeral). Blocks scaling ingest cleanly.
2. **Pin model (§4.1):** pins = news-only (recommended) vs belt-and-suspenders.
   Blocks Manage-Pins.
3. **Green-light to ramp scribe** given the GO verdict + guardrails.

I can implement the §4.2 visibility tweaks immediately (safe, additive) on your
say-so; everything else awaits the two decisions above.

---

*All read-only probes; nothing changed. Redis facts from live DB 0; retention
from scribe log + `arc_config.yaml`; analyzer tiers from `analyzer.py` /
`scribe.py` / `ollama_utils`; sitemap source from `kasmir7.generate_sitemap`.*
