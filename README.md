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
| `serpapi` | SerpApi's Google Shopping API: structured, more reliable | `SERPAPI_KEY` |
| `demo` | Deterministic made-up offers | nothing |

All settings are environment variables, listed with defaults in
[.env.example](.env.example).

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

- `backend/` — `app.py` (API), `search.py` (cache, rate limit, pipeline), `matching.py` (relevance), `pricing.py` (price parsing), `providers/` (price sources), `storage.py` (SQLite), `scheduler.py` (re-checks)
- `src/` — `App.tsx`, `components/`, `hooks/`, `lib/` (API client, formatting, region detection, chart helpers)
- `tests/`, `src/lib/lib.test.ts` — backend and frontend tests
- `evals/` — search-quality evals
- `docs/design-prototype/` — original Figma Make export, not part of the build
