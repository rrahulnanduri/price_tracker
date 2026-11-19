# Price Tracker

Search a product, compare current prices across stores in your region, and
track it: every check is stored, tracked products are re-checked on a
schedule, and you can set a price to be alerted at.

FastAPI + SQLite backend, React + Vite frontend. See [handoff.md](handoff.md)
for how it is built, what has and has not been verified, and what to do next.

## Run

Backend (Python 3.10+):

```bash
pip install -r requirements.txt
```

```bash
scrapling install
```

```bash
uvicorn backend.main:app --reload --port 8000
```

Frontend (Node 20+):

```bash
npm install
```

```bash
npm run dev
```

Open http://localhost:5173.

To try the app without touching a real price source, start the backend with
made-up data instead (the UI labels it DEMO DATA):

```bash
PRICE_PROVIDER=demo uvicorn backend.main:app --port 8000
```

## Price sources

| `PRICE_PROVIDER` | What it does | Needs |
| --- | --- | --- |
| `auto` (default) | `serpapi` if `SERPAPI_KEY` is set, otherwise `google` | |
| `google` | Scrapes Google Shopping with Scrapling | `scrapling install` |
| `serpapi` | SerpApi's Google Shopping API, plus every seller of the best matches | `SERPAPI_KEY` |
| `sites` | Only the regional comparison sites below; no Google | nothing |
| `demo` | Made-up prices, real store-search links | nothing |

Every mode except `demo` also queries regional price-comparison sites
(`COMPARISON_SITES=true`), all sources at once. Offers are pooled, one per shop
at its cheapest, and the results say which source found each one and which
sources were unavailable.

| Site | Regions | How |
| --- | --- | --- |
| Kieskeurig | NL, BE | opens the best-matching product pages and reads every seller from their schema.org data |
| StaticICE | AU | reads the results list, linking straight to each shop |

Sites were added only if they allow it in robots.txt and serve pages to a
client that honestly identifies itself; sites that block non-browser clients
(Beslist, idealo, Geizhals, PriceSpy, PriceRunner) are left out rather than
disguised as a browser.

With SerpApi, `SERPAPI_SELLER_LOOKUPS` (default 2) opens Google's product page
for the best-matching results to list every store selling that exact item.
Each lookup costs one SerpApi search.

All settings are environment variables, listed with defaults in
[.env.example](.env.example).

## Optional AI help

With [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai) installed
(`pip install -r requirements-llm.txt`) and `LLM_MODEL` set, an LLM helps in
two narrow places:

- **Extraction fallback:** if a results page loads but the scraper's selectors
  find no offers (usually a Google layout change), the LLM reads the page
  instead. Any offer whose price or title is not actually on the page is
  discarded, and prices are always parsed by the app, never by the model.
- **Second opinion on matching:** once per search, the LLM is asked whether
  the plausible listings are exactly the product searched for. It can drop a
  variant the rules kept or keep a listing they missed. It never overrides a
  mismatched model number or an accessory.

If the model fails or is unreachable, the search uses the rules-only result.
Results read or corrected by the AI are labelled in the UI. ScrapeGraphAI's
telemetry is switched off.

Compare rules alone with rules plus AI on the labelled cases and saved pages:

```bash
python -m evals.run --ai -v
```

## Checks

```bash
pip install -r requirements-dev.txt
```

```bash
ruff check backend evals tests && pytest -q
```

```bash
npm run check
```

## Evals: how good are the results?

```bash
python -m evals.run -v
```

Runs labelled listings ([evals/cases.json](evals/cases.json)) through the
ranking pipeline and reports precision, recall, whether the top result is the
right product, and which kinds of wrong listing leak through. It runs in CI and
fails if a metric drops.

```bash
python -m evals.run --live -v
```

Runs real searches ([evals/live_queries.json](evals/live_queries.json))
through whichever provider is configured and checks each result is priced in a
plausible band, titled like the query, and linked. Run this after changing the
scraper, and whenever results look off.

## Layout

- `backend/` — `app.py` (API), `search.py` (cache, rate limit, pipeline), `matching.py` (relevance), `llm.py` (optional AI help), `pricing.py` (price parsing), `providers/` (price sources), `storage.py` (SQLite), `scheduler.py` (re-checks)
- `src/` — `App.tsx`, `components/`, `hooks/`, `lib/` (API client, formatting, region detection, chart helpers)
- `tests/`, `src/lib/lib.test.ts` — backend and frontend tests
- `evals/` — search-quality evals
- `docs/design-prototype/` — original Figma Make export, not part of the build
