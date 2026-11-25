# Handoff

First pass merged to `master` on 2026-11-19 (PR #1). AI help (section 8) is on branch `feat/llm-fallback`.

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

### 8. Optional AI help via ScrapeGraphAI (branch `feat/llm-fallback`)

Added after a comparison with ScrapeGraphAI. Conclusion of that comparison:
ScrapeGraphAI does not help with getting past Google's bot checks (its
open-source version leaves that to you, and Scrapling is built for it), and an
LLM is slower, costs money per search and can misread a number. So it was not
used to replace the pipeline, only to cover its two weak spots:

- **Extraction fallback** (`backend/llm.py`, hooked in
  `providers/google_shopping.py`): runs only when a page loaded, was not a
  block page, and the selectors found zero offers. The page is turned into
  text with links, sent to ScrapeGraphAI's `SmartScraperGraph` as content (not
  a URL, so ScrapeGraphAI does not fetch anything itself), and every returned
  offer is verified: the price must be in the region's currency and appear as
  a number on the page, and most of the title's words must be on the page.
  Offers that fail are dropped and logged.
- **Second opinion on matching** (`backend/llm.py`, `matching.judge_candidates`
  / `apply_verdicts`, called from `search.py`): after the rules score each
  listing, those scoring at least 0.35 without a hard flag (`wrong_model`,
  `accessory`) go to the LLM in one batch, at most 30. A "no" drops a listing
  the rules kept; a "yes" keeps one they would have dropped.
- `rank_offers` is now `score_offers` + `select_offers`; `rank_offers` remains
  as the rules-only path used by the default evals.
- API: `/api/meta` reports `ai`; search results carry `ai_extracted`,
  `ai_changed`, and per-offer `extracted_by` and `ai_checked`. The UI labels
  AI-read offers and AI-checked searches.
- Off by default. Settings: `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`,
  `LLM_MODEL_TOKENS`, `LLM_FALLBACK`, `LLM_JUDGE`. Dependency in
  `requirements-llm.txt`, not in the core requirements or CI.
- `python -m evals.run --ai` runs the offline cases with and without the
  second opinion, and runs both extraction methods on saved pages in
  `evals/pages/` (scored against `evals/pages.json`). It fails if rules plus AI
  scores more than 2 points below rules alone on precision, recall or top
  result.

**Not verified:** no LLM was available on this machine (no API key, no
Ollama), so neither feature has been run against a real model and there are no
rules-vs-AI numbers yet. What was verified: 16 tests with a scripted stand-in
for the model (including invented prices and titles being rejected, failures
falling back, hard flags never overridden, and the eval gate catching a model
that says yes to everything), and the real ScrapeGraphAI pipeline accepting
the config and page text and failing only at the model connection, after which
the search fell back cleanly. The two saved pages are hand-written, not real
Google captures.

To get real numbers, with a model configured:

```bash
python -m evals.run --ai -v
```

### 9. Wider coverage: more sources, every seller, every store

Asked for after "the whole point is to find any and all local shops". Literal
"every website" is not achievable (nothing indexes every shop); the practical
route is to pool several aggregators.

- **Multi-source search** (`providers/multi.py`): the main source and every
  comparison site for the region run at once. A failing source is reported,
  not fatal; the search fails only if all fail. Offers are pooled and
  `matching.store_key` merges the same shop across sources ("Nedgame.nl" =
  "NEDGAME"), keeping its cheapest offer.
- **Comparison sites** (`providers/comparison.py`): Kieskeurig (NL, BE) and
  StaticICE (AU). Kieskeurig: the results page names products, the best three
  matches are opened, and every seller is read from the schema.org `Offer`
  data on each product page (`schema_offers`, generic, works for any site that
  publishes it). StaticICE lists offers directly with the shop's own URL.
  Requests identify as `PriceTracker/1.0` and wait 1 s between pages on a site.
- **Sites considered and left out:** Beslist (NL) and others block non-browser
  clients (405/403) and were not disguised as a browser; idealo, Geizhals,
  PriceSpy/Prisjakt, PriceRunner, Trovaprezzi likewise. Tweakers redirects to
  a cookie-consent wall, which the app does not accept on anyone's behalf.
  Toppreise (CH) and Ceneo (PL) build prices in the browser; Kakaku (JP)
  needs Shift_JIS handling. These are the next candidates, most needing
  Scrapling's browser on a machine where it runs.
- **Every seller via SerpApi** (`providers/serpapi.py`): for the best-matching
  results (score ≥ 0.7, up to `SERPAPI_SELLER_LOOKUPS`, default 2), the
  `google_immersive_product` engine with `more_stores=true` returns every
  store for that exact product. Not run against SerpApi (no key); tested with
  payloads shaped like SerpApi's documentation.
- **No cap of 8:** `MAX_RESULTS` defaults to 50; the UI shows 8 and a "show
  all N stores" button. Each offer says which source found it, and the
  results list every source with ✓/✗.
- `PRICE_PROVIDER=sites` uses only the comparison sites (works with no key or
  browser, but only for NL, BE and AU).
- Demo mode now links to real retailers' own search pages per region (prices
  remain made up and labelled).

**Verified live from this machine** (real network, real sites, 2026-11-19):
Switch OLED NL: 8 shops (€313.87 to €411.22); Sony WH-1000XM5 NL: 12 shops;
AirPods Pro 2 BE: 3 shops; Switch OLED AU: 3 shops with direct shop links,
cases filtered out. Also checked in the running app: 12 stores, "show all",
per-offer source, sources line with Google shown unavailable. Test fixtures in
`tests/fixtures/` are trimmed excerpts of those real pages (links, seller data
and result rows only; no reviews).

### 10. Live loading progress and site-wide animation

- **Progress stream:** `POST /api/search/stream` runs the same search as
  `/api/search` but sends newline-delimited JSON as it goes: `sources` (which
  sources are being asked), one `source` event per source as it finishes (ok,
  listing count, error), `stage` (`matching`, `ai_review`), then a single
  `result` or `error`. If the browser disconnects, the search is cancelled. The
  frontend (`searchPricesStream`) falls back to `/api/search` on an API
  without the route.
- **Loader** (`SearchProgress.tsx`): replaces the old timer-driven fake bar
  with real progress per source (spinner → ✓ count or ✗), a bar driven by
  sources answered, and placeholder cards shaped like results.
- **Motion** (`motion` package): results stagger in, re-rank with layout
  animation, expand smoothly on "show all", prices and chart stats count up,
  the chart fades in and marks the lowest price, watchlist items animate in
  and out, a hit target pulses, errors shake in, buttons give press feedback.
  `MotionConfig reducedMotion="user"` plus the existing CSS rule switch motion
  off for visitors who ask for reduced motion.
- **Removed:** the old loader and its shadcn parts (`ui/field`, `ui/progress`,
  `lib/utils`, `components.json`), and the now-unused `@base-ui/react`,
  `clsx`, `tailwind-merge`, `tw-animate-css` packages.
- **Windows fix:** with `uvicorn --reload` on Windows the event loop cannot
  start subprocesses, so the scraper's browser failed with
  `NotImplementedError`. `google_shopping.fetch_page` now runs the browser on
  its own Proactor loop in a worker thread in that case. Browser-start
  failures blocked by Windows now say so plainly.

**Verified:** the stream against the real sites (events arrive as each source
finishes: Google's failure at about 1.5 s, Kieskeurig's listings at about
5.4 s), the loader's live content in the running app, and the final results,
sources line, stats and lowest-price marker. **Not verified:** the motion
itself, because the in-app browser pane was hidden for the whole check, which
stops animation frames entirely; it needs a look in a visible browser.

### 11. First real Google Shopping fetches (via Edge) and the new layout

- **Edge fallback:** on the work laptop Windows refuses to run the downloaded
  Chromium (`spawn UNKNOWN`) but runs the system Microsoft Edge. Scrapling's
  stealth browser accepts an `executable_path`, so when the bundled browser
  cannot start the scraper retries with `SCRAPER_BROWSER_PATH` or, on Windows,
  Edge. Through Edge, real Google Shopping pages loaded for NL and US.
- **Google's current layout** (redirects to `udm=28`) has no stable class
  names and no links on offer cards. `extract_offers` now reads each card's
  text pieces (`parse_card_text`): title first, then the shop as the first
  short piece that is not a price, label, delivery note or rating, in either
  order. Condition labels on the card ("Pre-owned", "Refurbished",
  "Tweedehands") are appended to the title so matching drops used units.
  Price-filter chips ("Under $200", "Meer dan € 200") are skipped. Cards with
  no link fall back to a Google Shopping search for the item's title.
- On those real pages: NL 57 offers read, 8 shops ranked; US 39 offers, 8
  shops ranked. Known limit: a listing Google does not label as used (e.g.
  "... - Boxed" at a retro shop) is treated as new.
- **Rate limiting observed:** after about ten Google searches in a few minutes
  from the office network, Google served its "unusual traffic" page for every
  query; the app reports it as `ProviderBlocked`. Normal use (cached for 15
  minutes, rate-limited, scheduled re-checks spaced 20 s apart) sends far
  fewer, but a shared office connection makes blocks more likely.
- Live eval now prints each query as it finishes and handles Ctrl+C by
  reporting what has finished. `scrapling install` must be run as
  `.venv\Scripts\scrapling install`.

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

### 11a. Block detection false positives (2026-11-25)

Live runs showed "rate-limited" on pages that were really full results pages:
- Google's own scripts on every results page mention `/sorry/index` and `consent.google`, so those are now
  checked against the page address only. Page text counts only for "unusual traffic" or the captcha form.
- English-language pages often lay a "Before you continue to Google" dialog over full results. That dialog
  now only explains a page with **no** offers (`check_consent_wall`); otherwise the results are read.
- Struck-out ("Was ₹1,354") and converted ("(AED 1,323)") prices, and the French "Et plus de prix" label,
  are no longer read as shop names.
Real blocks (HTTP 429 to `/sorry/`) still happen on the office network after a burst of searches.
Matching fixes from the same live runs: second-hand wording in titles ("Zo goed als nieuw", "Nette staat",
"Erneuert", "Comme neuf", "Wie neu", "Like new") now marks an offer used/refurbished, and Hindi accessory
titles on Amazon.in ("… के साथ इस्तेमाल होने वाला … केस", "for use with … case") are accessories.
**Bundles are now filtered (owner's decision, 2026-11-25).** Someone asking for "playstation 5 console" wants
the console, so `_is_bundle` flags titles with bundle words (bundle, combo, voucher, accessories, AppleCare) or
extras after "with" / "w/" (controller, DualSense, game, headset), unless the query asks for them. The four eval
offers labelled `match` under the old rule were relabelled `bundle` in `evals/cases.json` (PS5 Spider-Man 2
bundle, AirPods + AppleCare+, MacBook Air + AppleCare, DJI Fly More Combo).
That exposed an accessory bug: "<accessory> für DJI Mini 4 Pro" was let through because the product name sat
within the first three words. `_is_accessory_for` now looks for a "for" word *before* the first mention of the
product. Note this fix was prompted by a holdout case (dji-mini-4-pro-de), so that case is no longer unseen.
Known gaps: second-hand marketplaces with no condition wording (Leboncoin, some eBay listings) and
"Tableau pour LEGO…" (a display frame for the set) still rank as matches.
