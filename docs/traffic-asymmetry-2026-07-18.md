# Traffic asymmetry: arc-codex ≫ huntaegis — investigation — 2026-07-18

**Report only** (no cadence changes — that decision is Ross's, per the brief).
Question: the Grafana "Arc Codex + Huntaegis Web Traffic" dashboard shows far
more traffic to arc than hnt. Hypothesis under test: arc publishes to social far
more often, and equalizing frequency won't fully close the gap.

**Verdict: the hypothesis is right that cadence won't close the gap — but the
data goes much further. Social referral is <1.5% of traffic on both sites, and
hnt already gets *more* of it than arc. Equalizing social cadence has a
near-zero ceiling. The gap is structural: arc exposes ~93× more indexable URLs
and a permanent reference corpus hnt lacks, which drives the crawler / scraper /
pseudo-direct volume that is the bulk of the difference.**

---

## 1. Publish cadence — arc does post more, but it's volume, not a timer

Success lines (`Posted article … to <Network>`) in the social poster logs, last
30 days (since 2026-06-18):

| Network | arc posts | hnt posts | arc/hnt | arc errors | hnt errors |
|---|---:|---:|---:|---:|---:|
| Bluesky | 7,480 | 5,057 | 1.48× | 924 | 596 |
| Mastodon | 7,465 | 5,065 | 1.47× | 906 | 673 |
| Facebook | 3,902 | 3,207 | 1.22× | 2,464 | 2,288 |
| Threads | — (dead code) | — | — | — | — |

- **arc posts ~22–48% more per network** than hnt. But the posters are **not on a
  tunable timer** — each scans Redis every 15s and posts *every newly-ingested
  article* (`for article_id in new_ids`). So the difference is **article-ingestion
  volume**, not a cadence knob. "Equalizing frequency" would mean throttling arc
  or growing hnt's article pipeline, not changing a schedule.
- **Threads is not a real network.** `arc_stack/backend/threads_poster.py` exists
  but no process runs it, `arc.sh` never starts it, and there is no threads log.
  Both stacks publish to the same 3 networks.
- **No silently-broken hnt network.** All three post. Facebook shows high error
  counts on *both* stacks (2,464 / 2,288) — these are `ReadTimeout` "will retry
  next cycle", i.e. transient FB API flakiness that retries, not permanent drops,
  and it is symmetric. Bluesky/Mastodon error rates are low on both. Nothing is
  silently dropping on hnt that isn't also happening on arc.

## 2. Source decomposition — where the gap actually is

All Caddy access logs per domain, classified by User-Agent (bot) then Referer,
normalized to per-day (arc logs span 1.3d, hnt 6.0d — normalization makes them
comparable):

| Source | arc/day | hnt/day | arc:hnt |
|---|---:|---:|---:|
| **social** | 321 | **384** | **0.84× (hnt leads)** |
| search (by referer) | 5 | 3 | ~0 both |
| direct | 83,143 | 4,736 | 17.6× |
| internal | 20,509 | 9,930 | 2.1× |
| bot (declared UA) | 56,392 | 15,681 | 3.6× |
| **total** | **160,398** | **30,740** | **5.2×** |

**The gap is ~5.2× total, and social referral is the one slice hnt already
wins.** Social is 0.2% of arc's traffic and 1.3% of hnt's. The gap lives in
`direct` (17.6×) and `bot` (3.6×).

**The "direct" bucket is overwhelmingly automated, not human.** Sampling arc's
no-referer / non-bot-UA requests: the top User-Agents are generic desktop
browser strings (Chrome-on-Windows, Chrome-on-Mac) and **Friendica ActivityPub
fetchers**, hitting a long tail of `/article/*` and `/uploads/scraped/*` URLs —
classic corpus-sweeping by scrapers and LLM crawlers that spoof browser UAs (so
they escape the UA bot filter) and by Fediverse servers fetching link previews.
On a site whose *real* organic homepage demand is 0.037 req/s (per
`perf-2026-07-17.md`), 83k "direct" requests/day is not an audience — it is crawl
volume. True human traffic on both sites is small.

## 3. The structural driver — indexable surface

| | arc-codex.com | huntaegis.com |
|---|---:|---:|
| `sitemap.xml` `<loc>` count | **25,949** | **280** |
| `news-sitemap.xml` `<loc>` count | 391 | 279 |

- arc exposes **~93× more indexable URLs**. Its main sitemap is the whole
  permanent corpus — library (books), plants, wiki directives, and all public
  articles. hnt's main sitemap (280) is essentially just its news-sitemap (279):
  **hnt has no permanent reference corpus indexed**, only the rolling news window.
- This is the mechanical explanation for §2: 93× the URLs = vastly more surface
  for crawlers, LLM scrapers, and federation preview-fetchers to sweep → the
  bot + pseudo-direct volume that *is* the traffic gap.

## 4. robots.txt / indexing symmetry — not a differentiator

Both robots.txt are structurally identical: `Allow: /`, `Disallow: /api/`,
`Crawl-delay: 10`, and both reference `sitemap.xml` **and** `news-sitemap.xml`.
The news/reference sitemap split (kasmir7 #14) **landed on both stacks**. There
is no robots.txt asymmetry causing the gap (the "huntaegis robots.txt lesson" is
not re-occurring). Both sitemaps return 200.

**Caveat on search referral:** the ~0 search-referer numbers do **not** prove
either site is well- or poorly-indexed. Google commonly strips `Referer` and
organic clicks frequently arrive in the `direct` bucket. Actual indexation
coverage can only be read from Search Console — which is exactly the Phase 3
work. What the sitemap counts *do* tell us: arc's indexation **ceiling** is ~93×
hnt's, because that's the surface each offers.

## 5. Ranked levers

1. **Do NOT equalize social cadence to close the traffic gap — ceiling ≈ 0.**
   Social is <1.5% of traffic on both, and hnt already leads it (384 vs 321/day).
   Ross's instinct ("won't fully close the gap") is correct, and stronger than
   stated: it would barely move it. Social cadence is worth tuning for *social
   engagement* reasons, but it is not a traffic-gap lever.
2. **Recognize most of the "gap" is automated crawl volume, not audience.** ~85%+
   of arc's lead is bot + scraper pseudo-direct traffic, mechanically tied to its
   93× larger URL surface. If the dashboard's purpose is real human reach, the
   headline gap is partly a measurement artifact — worth splitting bot vs human
   on the Grafana panel so the real signal isn't drowned.
3. **If growing real hnt reach is the goal, the lever is content surface +
   organic search, not social.** hnt has no reference corpus indexed (280 URLs).
   Options: build/expose an hnt reference corpus analogous to arc's library, and
   pursue genuine organic indexation (Phase 3 SEO + Search Console). Both sites
   show ~0 measurable search referral today — that is the real opportunity and
   the real ceiling, far above anything social can add.
4. **Internal linking:** arc's internal referral is 2× hnt's — a second-order
   effect of a bigger, more cross-linked site. More internal linking on hnt is a
   cheap organic assist, downstream of #3.

## Bottom line for Ross

Equalizing publish frequency will not close the gap — it will barely dent it,
because social is a rounding error in the traffic mix and hnt already wins that
slice. The gap is content-surface driven (93× indexable URLs, a permanent corpus
hnt lacks) and shows up as crawler/scraper volume. The realistic path to more
*real* hnt traffic is organic-search surface, not social cadence — which is what
Phase 3 sets up. No cadence changes made; awaiting your call.

---

*Method: poster logs (`{bluesky,facebook,mastodon}_poster.log`, 30-day window);
Caddy JSON access logs in `/var/log/caddy/` classified by UA→Referer, normalized
per-day; live robots.txt + sitemap `<loc>` counts. Read-only; nothing changed.*
