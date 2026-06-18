# Keyword Intelligence & Rank Tracking System — Build Plan

Scope: personalized keychains first, then name magnets and TankCrafter. The whole point is **bounded scope** — we are not indexing Amazon, just owning two or three niches. That constraint is what makes DIY beat a Helium 10 subscription here.

---

## The core idea

A "reverse ASIN" tool is an **inverted index**, nothing more. You build a table of `keyword → [asin @ position]`, then flip it on demand to `asin → [keywords]`. Helium 10 does this at marketplace scale by crawling millions of SERPs and inverting; we do it for keychains only.

Two jobs that people (me, last few turns) wrongly lump together:

1. **Keyword discovery** — *what terms exist and matter* in the niche. Free. No proxies.
2. **Rank measurement** — *where a specific ASIN actually sits* for a keyword, organic vs sponsored. Needs the live SERP, which needs proxies (or a SERP API) to do continuously.

The proxy is the *enabler* of job 2, not a source of precision. Precision comes from reading the real SERP under fixed conditions.

---

## The two components

### Component 1 — Keyword Discovery Engine (free, runs today)

**A. Recursive autocomplete harvester.**
Amazon's search-bar suggestion endpoint returns terms **already ordered by real search popularity** — that ordering is the demand signal, straight from Amazon. Grab the exact request params from your browser's network tab while typing in the search bar (more reliable than any endpoint I'd hardcode; they tweak it).
- Seeds: `keychain`, `personalized keychain`, `custom keychain`, `name keychain`, `name magnet`, etc.
- Recurse: append a–z, append modifier stems (`personalized keychain for ___`, `custom keychain with ___`).
- Capture each suggestion **and its rank position** (order = demand proxy).
- Throttle: randomized 0.5–2s delay, rotating user-agent. Runs clean from your home IP. Do not overbuild this.

**B. Competitor listing miner.**
Top sellers already did this research; their titles and bullets *are* the validated keyword set.
- Pull the top ~20 listings per seed term.
- **Clean path:** SP-API Catalog Items v2022-04-01 "search by keywords" — returns titles, bullets, ranked ASINs, no CAPTCHA, no proxy. Use this, not HTML scraping, for the listing text.
- Tokenize title + bullets, count term frequency across the winners. High cross-listing frequency = validated.

**C. Scoring.**
Each keyword gets: autocomplete rank (demand) + cross-listing frequency (validation) + competing-products count (competition, from the results-count number when you search it). Output = a prioritized target list. This is **ordinal** (which keyword beats which), not absolute search volume — and ordinal is enough to decide what to target.

### Component 2 — Rank Tracker (proxies / SERP API)

For the prioritized keywords, fetch the real SERP and record each ASIN's organic position and sponsored-vs-organic split. Timestamp every observation so rank-over-time falls out for free.

**Normalization is mandatory** or your clean proxies still give you drifting garbage. Amazon's SERP is personalized and geo-weighted, so pin every request:
- logged-out
- fixed US delivery ZIP (one consistent metro)
- consistent headers
- **sticky session per keyword** (hold one IP for one keyword's measurement, then rotate for the next — rotating mid-measurement shifts the SERP under you)

**Asset-light fetching** is the single biggest cost lever:
- Use `requests`/`httpx` + `Accept-Encoding: gzip`. **Never** a headless browser, never load images/CSS/JS.
- Asset-light: ~3,000–5,000 SERPs per GB. Headless w/ assets: ~200–350 per GB. Same data, 10x+ the cost.

**Swappable transport:** write the fetch layer so it takes either a raw Decodo proxy *or* a SERP API endpoint by swapping one function. Keeps the proxy-vs-API decision open.

---

## Data model (the inverted index)

```
keywords(
  id, phrase, source,
  autocomplete_rank, competing_count, est_volume,
  first_seen, updated
)

asins(
  asin, brand, title, is_mine, captured
)

observations(
  id, keyword_id, asin,
  position, slot_type,        -- organic vs sponsored
  page, observed_at,
  conditions_hash             -- the normalization params, so you know rows are comparable
)
```

Reverse ASIN = one query:
```sql
SELECT k.phrase, o.position, o.observed_at
FROM observations o JOIN keywords k ON k.id = o.keyword_id
WHERE o.asin = ?  ORDER BY o.position;
```
`conditions_hash` is what keeps "precise" honest — two observations are only comparable if their conditions match.

---

## Stack

- **Python 3** — `httpx` (or `requests`) + `selectolax`/`lxml` for parsing (fast; skip BeautifulSoup for speed).
- **SQLite** to start (zero-config, handles this scale easily) → Postgres on your Vultr box if/when it grows.
- **cron** for the daily tracker run.
- **Flask** UI — reverse-ASIN lookup, rank-over-time chart, keyword prioritization view. You've built this shape before.
- **SP-API client** for Catalog Items now, SQP later.
- **Decodo** residential proxy (PAYG) *or* a SERP API (Decodo / Bright Data). Datacenter proxies: **never** — Amazon blocks those ASN ranges on sight.

---

## Provider & cost

- **Decodo (ex-Smartproxy)** — best mid-market value, ~$2.20–3/GB, ~99.7% success against e-commerce targets in independent benchmarks, free trial + pay-as-you-go. US pool, geo-pinned, sticky per keyword.
- At ~300 keychain keywords/day asset-light, 1 GB lasts ~8–13 days → **~$5–8/month** in traffic. Proxy cost is not your constraint; getting blocked or measuring noise is.
- **SERP API alternative** bills per *request*, not per GB — so the per-GB math doesn't apply. Higher per-unit cost, but it bundles rotation + CAPTCHA + parsing and kills the maintenance treadmill. Given you're solo across 29 printers and three brands, price this before defaulting to raw proxies.

Before any spend: trial the pool by running a few hundred keychain SERPs through it and watching your CAPTCHA/Robot-Check rate. Let Amazon be the judge, not the marketing page.

---

## Parallel track — SQP for your *own* products (optional, independent)

The crawl above is the only path for *competitor* ASINs. For **your own** listings, Amazon will hand you ground truth it never gives Helium 10: the **Search Query Performance report** (SP-API, ASIN-level — the actual queries driving your impressions/clicks/purchases).

Gate: Brand Registry, which needs a trademark on the *name* (e.g. "KJ Keychains") — your products being generic/handmade is irrelevant. The "wait a year" problem is only the DIY-USPTO route. **IP Accelerator gets provisional Brand Registry access in ~2–3 weeks** while the mark is pending (~$600–1,500). That also unlocks Sponsored Brands, A+ Content, Stores, and Brand Analytics — the exact ad/keyword stack you're building. Start it whenever; it doesn't block the crawl build.

---

## Build order

1. **Discovery engine** (free, this week) — autocomplete harvester + listing miner + scoring. **Validate it produces a useful keyword list before spending a dollar on proxies.** You may find discovery alone covers what you need for keychains.
2. **Storage + inverted index** — stand up the schema, populate from discovery.
3. **Rank tracker** — swappable transport, normalization, daily cron. Proxy spend starts here, justified by results from step 1.
4. **Flask UI** — reverse-ASIN lookup, rank-over-time, prioritization.
5. **Ongoing** — maintain the parser, expand to name magnets + TankCrafter, optional one-month Helium 10 to bootstrap absolute-volume numbers once, optional SQP track.

---

## Honest caveats

- **No absolute volume.** You get ordinal ranking, not "8,100 searches/mo." Helium 10 *models* those from data you can't see. If you want the numbers, buy one month of H10, export keychains + personalized keychains, cancel — bootstrap the volume curve once, maintain the rest yourself.
- **Personalization/geo noise** is real — normalization isn't optional or your rank numbers drift run to run.
- **Parser maintenance** — raw scraping breaks when Amazon nudges their markup. A SERP API removes this tax.
- **Coverage = what you harvest.** A long-tail term you never test won't appear. Same limitation H10 has; smaller for you because your scope is tight.
- **ToS:** crawling SERPs is against Amazon's terms. Bounded, low-volume, well-throttled keeps the risk low, but it's real and it's your call. The SP-API paths (Catalog Items, SQP) are fully compliant; the SERP crawl is the one adversarial piece.
