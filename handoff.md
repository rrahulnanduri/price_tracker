# Handoff

Branch `refactor/cleanup`, 2026-11-11. Nothing is committed or pushed yet.

## Read this first

**The live Google Shopping scrape has not been run.** On the machine this work
was done on, Chromium would not start (Windows refused to launch the
Playwright build) and google.com is blocked in the in-app browser by
organisation policy, so no real results page was ever fetched. Everything
around the fetch is tested; the fetch itself and the selectors that read
Google's markup are not. The SerpApi provider is also untested against the
real service (no API key); it was written against SerpApi's published field
list and is tested with a sample payload.

The first thing to do on a machine where the browser works:

```bash
python -m evals.run --live -v
```

If it reports few or no results, the scraper's card and store selectors in
`backend/providers/google_shopping.py` (`CARD_CLASSES`, `STORE_SELECTORS`) need
updating against the current page. If Google blocks the address, the API now
says so explicitly (HTTP 503) instead of returning "no results".

## What changed, in order

### 1. Cleanup refactor (first pass)

- Deleted stale compiled `.js` files that sat next to every `.tsx`. Vite
  resolves `.js` first, so the app had been running an old `App.js`. `tsc` now
  has `noEmit`.
- Untracked `node_modules` (24,462 files), `.idea`, `.DS_Store`.
- Deleted the legacy Flask prototype (`app.py`, `templates/`); it is in git history.
- Split the backend and the 334-line `App.tsx` into modules.

### 2. Fetching rebuilt for accuracy

- **Providers** (`backend/providers/`): one interface, three sources chosen by
  `PRICE_PROVIDER`: the Google Shopping scraper, SerpApi, and a demo source.
  `auto` uses SerpApi when `SERPAPI_KEY` is set.
- **Scraper** now returns every offer on the page instead of the first seven,
  finds an offer card by known class and otherwise by structure, skips prices
  in another currency, skips shipping fees and sentences that merely contain a
  price, and reads shipping cost and stock status from the card text.
- **Relevance matching** (`backend/matching.py`) is new. Previously the
  cheapest listing per store won, so a phone case outranked the phone. Each
  listing is now scored against the query and dropped below 0.7. It rejects
  accessories, other models (model numbers must match exactly), other variants
  (Pro, Max, Mini...), games and add-ons that only mention the product, used
  and refurbished units unless you searched for them, and prices under 30% of
  the median.
- **Ranking** is by total cost (price plus known shipping), in-stock first,
  one offer per store.
- **Price parsing** (`backend/pricing.py`) understands currency codes and
  region-specific symbols (AED, S$, A$, CHF, kr, zł, Rs) and has per-currency
  plausibility ranges, so INR and JPY prices above 100,000 are no longer dropped.

### 3. Tracking

- **SQLite** (`backend/storage.py`): every live search is stored as an
  observation; the watchlist lives in the same file (`PRICE_DB`).
- **Watchlist**: track a product per region, with an optional alert price.
- **Scheduled re-checks** (`backend/scheduler.py`): tracked products are
  re-checked every `REFRESH_HOURS` (default 6) while the API is running.
- **Alerts**: a tracked product at or below its alert price is flagged in the
  UI, and `ALERT_WEBHOOK_URL`, if set, is POSTed once per drop.
- The chart shows real stored history. The simulated trend line is gone.

### 4. Protection for the source

- Results are cached for 15 minutes per product and region.
- Live fetches are rate-limited per client (10 a minute; cache hits are free)
  and capped at two at a time. Identical simultaneous searches share one fetch.

### 5. Regions

- 19 regions (added NL, BE, IE, AT, CH, ES, IT, SE, PL), each with currency and
  locale. An unsupported region is now an error rather than silently US.
- The UI has a region picker, remembers the choice, and detects a default from
  timezone, then browser language.

### 6. Frontend

- Search with region picker, watchlist, ranked results with total price,
  shipping, stock, condition and match score, tracking controls, history chart
  with now / lowest seen / change.
- Responsive: three columns on desktop, one scrolling column on phones. No
  text under 10px.
- The chart library loads lazily; the main bundle went from 566 kB to 249 kB.

### 7. Tooling

- Backend: 50 tests, `ruff`. Frontend: 15 tests (`vitest`), `eslint`, `tsc`.
- GitHub Actions workflow runs all of it plus the offline evals.
- `graphify-out/` untracked and ignored; the Figma export moved to
  `docs/design-prototype/`.

## Evals

`python -m evals.run` scores the ranking pipeline on 30 hand-labelled cases
(199 listings, 12 regions). Cases are split:

- **dev** (24 cases): used while writing the rules. A regression gate.
- **holdout** (6 cases): written after the rules were frozen and never tuned
  against. This is the honest estimate.

| Metric | Dev | Holdout |
| --- | --- | --- |
| Precision (kept listings that are the product) | 93.5% | 93.8% |
| Recall (real listings kept) | 100% | 93.8% |
| Top result is the right product | 91.7% | 83.3% |
| Top result is the cheapest right one | 91.7% | 83.3% |

Wrong listings that got through, all cases: accessories 0 of 44, wrong model
0 of 50, used 0 of 11, other 1 of 6, **variants 4 of 14**.

These numbers measure the matching rules on listings I wrote to resemble real
ones. They say nothing about whether the scraper extracts real pages
correctly; `--live` is what measures that.

Known misses, left visible in the eval rather than special-cased:

- Variants named by a word the rules don't know: "Duo Crisp" vs "Duo",
  "Nappy Pants", "Kids", a "265S" when "265" was searched.
- A bundle that leads with a different product ("MX Keys combo with MX Master 3S").
- A real listing whose title spells the query differently ("Starterkit" vs
  "starter kit") is dropped.

When a real search returns something wrong, add it to `evals/cases.json` as a
dev case, fix the rule, and confirm the holdout numbers did not fall.

## Verified

- Backend tests, frontend tests, lint, typecheck, production build: all pass.
- Scraper extraction against a sample page parsed with Scrapling's own parser
  (class-based card, structural fallback, currency filter, shipping, stock).
- The app end to end in a browser against the demo provider, at 1280px and
  375px: search, region change, results, track with alert price, invalid alert
  price, watchlist open and remove, refresh, history chart with 14 seeded
  points, error messages. Layout was checked by measuring the page, because
  screenshots were unavailable.

## Not verified

- The live Google scrape and the SerpApi provider (see top).
- The alert webhook against a real endpoint (the trigger logic is tested).
- The scheduler over real hours (its due-date logic is tested).
- Visual appearance by eye.

## Limits and next steps

1. Run the live eval and fix the Google selectors if needed. Scraping Google
   is against its terms and breaks without notice; SerpApi or a retailer API
   is the durable choice.
2. Re-checks only run while the API process is up. For always-on tracking,
   deploy it or move `scheduler.refresh_due` to a cron job.
3. Alerts are in-app plus one webhook. No email or push.
4. Single user: no accounts, one shared watchlist. The rate limiter and cache
   are in memory and per process.
5. Shipping and stock are read from text when stated; often they are not.
6. The matcher is rule-based and English-centric, with some Dutch, German,
   French, Spanish, Italian, Swedish and Japanese vocabulary.
7. `npm audit` reports 10 moderate issues in dev tooling that need a breaking
   upgrade to clear; `npm audit fix` was applied for the rest.
8. No Docker or deployment config.
