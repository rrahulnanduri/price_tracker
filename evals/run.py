"""Search-quality evals.

    python -m evals.run            offline: labelled cases through the ranking pipeline
    python -m evals.run --live     live: real searches through the configured provider
    python -m evals.run -v         also list every offer the pipeline got wrong

Offline evals are deterministic and run in CI; they fail (exit 1) when a
metric drops below its threshold. Live evals need network access and a working
provider (PRICE_PROVIDER / SERPAPI_KEY) and check that real results look like
the product: priced inside an expected band, titled like the query, linked.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_region, load_settings
from backend.matching import DEFAULT_MIN_RELEVANCE, Offer, rank_offers, tokenize
from backend.pricing import parse_price
from backend.providers import build_provider
from backend.providers.base import parse_shipping

HERE = Path(__file__).parent
THRESHOLDS = {            # dev-split metrics must stay at or above these (regression gate)
    "precision": 0.93,
    "recall": 0.95,
    "top_result_correct": 0.90,
    "cheapest_correct": 0.85,
    "price_parsing": 1.0,
    "shipping_parsing": 1.0,
}
HOLDOUT_FLOOR = 0.75      # unseen-product metrics below this mean the rules do not generalise
LIVE_THRESHOLDS = {
    "answered": 0.9,
    "in_price_range": 0.9,
    "title_matches": 0.9,
    "has_link": 0.95,
}


def _ratio(hits: int, total: int) -> float:
    return hits / total if total else 1.0


# -- offline -------------------------------------------------------------------

def run_case(case: dict, min_relevance: float) -> dict:
    region = get_region(case["country"])
    offers, labels = [], {}
    for store, title, price_text, label in case["offers"]:
        price = parse_price(price_text, region.currency)
        offer = Offer(store.upper(), title, price.value if price else 0.0, price_text)
        offers.append(offer)
        labels[id(offer)] = label

    ranked, rejected = rank_offers(case["query"], offers, min_relevance=min_relevance, limit=50)
    rejected_ids = {id(o) for o in rejected}
    kept = [o for o in offers if id(o) not in rejected_ids]
    matches = [o for o in offers if labels[id(o)] == "match"]

    wrongly_kept = [o for o in kept if labels[id(o)] != "match"]
    wrongly_dropped = [o for o in matches if id(o) in rejected_ids]
    cheapest_match = min(matches, key=lambda o: o.total) if matches else None
    top = ranked[0] if ranked else None

    return {
        "id": case["id"],
        "split": case.get("split", "dev"),
        "kept": len(kept),
        "matches": len(matches),
        "true_positives": len(kept) - len(wrongly_kept),
        "top_result_correct": bool(top and labels[id(top)] == "match"),
        "cheapest_correct": bool(top and cheapest_match and top is cheapest_match),
        "wrongly_kept": [(labels[id(o)], o.store, o.title, o.relevance) for o in wrongly_kept],
        "wrongly_dropped": [(o.store, o.title, o.relevance, o.flags) for o in wrongly_dropped],
        "leaks": {label: sum(1 for o in wrongly_kept if labels[id(o)] == label)
                  for label in {labels[id(o)] for o in offers} - {"match"}},
        "label_totals": {label: sum(1 for o in offers if labels[id(o)] == label)
                         for label in {labels[id(o)] for o in offers} - {"match"}},
    }


def run_offline(min_relevance: float, only: str | None = None) -> dict:
    data = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    cases = [c for c in data["cases"] if not only or c["id"] == only]
    results = [run_case(case, min_relevance) for case in cases]

    dev = [r for r in results if r["split"] == "dev"]
    holdout = [r for r in results if r["split"] == "holdout"]

    leaks: dict[str, list[int]] = {}
    for r in results:
        for label, total in r["label_totals"].items():
            entry = leaks.setdefault(label, [0, 0])
            entry[0] += r["leaks"].get(label, 0)
            entry[1] += total

    price_rows = data["price_parsing"]
    price_failures = []
    for text, currency, value, expected_currency in price_rows:
        got = parse_price(text, currency)
        actual = (got.value, got.currency) if got else (None, None)
        if actual != (value, expected_currency):
            price_failures.append((text, (value, expected_currency), actual))

    shipping_rows = data["shipping_parsing"]
    shipping_failures = []
    for text, currency, expected in shipping_rows:
        got = parse_shipping(text, currency)
        if got != expected:
            shipping_failures.append((text, expected, got))

    return {
        "mode": "offline",
        "min_relevance": min_relevance,
        "cases": results,
        "metrics": {
            **_ranking_metrics(dev),
            "price_parsing": _ratio(len(price_rows) - len(price_failures), len(price_rows)),
            "shipping_parsing": _ratio(len(shipping_rows) - len(shipping_failures), len(shipping_rows)),
        },
        "holdout_metrics": _ranking_metrics(holdout) if holdout else {},
        "leak_rates": {label: {"leaked": hit, "total": total} for label, (hit, total) in sorted(leaks.items())},
        "price_failures": price_failures,
        "shipping_failures": shipping_failures,
        "counts": {"cases": len(results), "dev": len(dev), "holdout": len(holdout),
                   "offers": sum(len(c["offers"]) for c in cases)},
    }


def _ranking_metrics(results: list[dict]) -> dict:
    kept = sum(r["kept"] for r in results)
    matches = sum(r["matches"] for r in results)
    true_positives = sum(r["true_positives"] for r in results)
    return {
        "precision": _ratio(true_positives, kept),
        "recall": _ratio(true_positives, matches),
        "top_result_correct": _ratio(sum(r["top_result_correct"] for r in results), len(results)),
        "cheapest_correct": _ratio(sum(r["cheapest_correct"] for r in results), len(results)),
    }


def print_offline(report: dict, verbose: bool) -> None:
    counts = report["counts"]
    print(f'Offline eval: {counts["cases"]} cases ({counts["dev"]} dev, {counts["holdout"]} holdout), '
          f'{counts["offers"]} labelled offers, min relevance {report["min_relevance"]}\n')
    print("  Dev split (cases the rules were tuned on; regression gate):")
    for name, value in report["metrics"].items():
        threshold = THRESHOLDS[name]
        mark = "ok  " if value >= threshold else "FAIL"
        print(f"    {mark} {name:<20} {value:6.1%}   (threshold {threshold:.0%})")
    if report["holdout_metrics"]:
        print("\n  Holdout split (products the rules have not seen; the honest estimate):")
        for name, value in report["holdout_metrics"].items():
            mark = "ok  " if value >= HOLDOUT_FLOOR else "FAIL"
            print(f"    {mark} {name:<20} {value:6.1%}   (floor {HOLDOUT_FLOOR:.0%})")

    print("\n  Wrong offers that got through, by kind:")
    for label, row in report["leak_rates"].items():
        print(f'    {label:<12} {row["leaked"]}/{row["total"]}')

    problems = [c for c in report["cases"] if c["wrongly_kept"] or c["wrongly_dropped"]
                or not c["top_result_correct"] or not c["cheapest_correct"]]
    if problems:
        print(f"\n  {len(problems)} case(s) with mistakes" + ("" if verbose else " (use -v for detail):"))
    for case in problems:
        notes = []
        if not case["top_result_correct"]:
            notes.append("top result is not the product")
        elif not case["cheapest_correct"]:
            notes.append("top result is not the cheapest match")
        print(f'    {case["id"]} [{case["split"]}]: {len(case["wrongly_kept"])} wrongly kept, '
              f'{len(case["wrongly_dropped"])} wrongly dropped' + (f' ({"; ".join(notes)})' if notes else ""))
        if verbose:
            for label, store, title, relevance in case["wrongly_kept"]:
                print(f"        kept    [{label}] {store}: {title}  (relevance {relevance})")
            for store, title, relevance, flags in case["wrongly_dropped"]:
                why = ", ".join(flags) or "low coverage"
                print(f"        dropped {store}: {title}  (relevance {relevance}, {why})")
    for text, expected, actual in report["price_failures"]:
        print(f"    price {text!r}: expected {expected}, got {actual}")
    for text, expected, actual in report["shipping_failures"]:
        print(f"    shipping {text!r}: expected {expected}, got {actual}")


# -- live ----------------------------------------------------------------------

async def run_live(min_relevance: float, limit: int | None) -> dict:
    settings = load_settings()
    provider = build_provider(settings)
    queries = json.loads((HERE / "live_queries.json").read_text(encoding="utf-8"))["queries"][:limit]
    rows = []

    for index, spec in enumerate(queries):
        region = get_region(spec["country"])
        started = time.monotonic()
        row = {"query": spec["query"], "country": spec["country"], "error": None, "results": []}
        try:
            raw = await provider.search(spec["query"], region)
            ranked, rejected = rank_offers(spec["query"], raw, min_relevance=min_relevance,
                                           limit=settings.max_results)
            low, high = spec["price_range"]
            wanted = [t for word in spec["must_include"] for t in tokenize(word)]
            for offer in ranked:
                title_tokens = set(tokenize(offer.title))
                row["results"].append({
                    **offer.to_dict(),
                    "in_price_range": low <= offer.price <= high,
                    "title_matches": all(t in title_tokens for t in wanted),
                    "has_link": offer.url.startswith(("http://", "https://")),
                })
            row["considered"] = len(raw)
            row["rejected"] = len(rejected)
        except Exception as exc:  # a failed query is a result, not a crash
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["seconds"] = round(time.monotonic() - started, 1)
        rows.append(row)
        if index < len(queries) - 1:
            await asyncio.sleep(5)   # be polite to the source

    results = [r for row in rows for r in row["results"]]
    return {
        "mode": "live",
        "provider": provider.name,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "queries": rows,
        "metrics": {
            "answered": _ratio(sum(1 for r in rows if r["results"]), len(rows)),
            "in_price_range": _ratio(sum(r["in_price_range"] for r in results), len(results)),
            "title_matches": _ratio(sum(r["title_matches"] for r in results), len(results)),
            "has_link": _ratio(sum(r["has_link"] for r in results), len(results)),
        },
        "counts": {"queries": len(rows), "results": len(results)},
    }


def print_live(report: dict, verbose: bool) -> None:
    counts = report["counts"]
    print(f'Live eval via "{report["provider"]}": {counts["queries"]} queries, {counts["results"]} results\n')
    for row in report["queries"]:
        if row["error"]:
            print(f'  FAIL {row["query"]} [{row["country"]}]: {row["error"]}')
            continue
        bad = [r for r in row["results"] if not (r["in_price_range"] and r["title_matches"] and r["has_link"])]
        status = "ok  " if row["results"] and not bad else "WARN"
        print(f'  {status} {row["query"]} [{row["country"]}]: {len(row["results"])} kept of '
              f'{row["considered"]} found, {len(bad)} suspect, {row["seconds"]}s')
        for r in (row["results"] if verbose else bad):
            issues = [name for name in ("in_price_range", "title_matches", "has_link") if not r[name]]
            print(f'         {r["store"]}: {r["price_text"]}  {r["title"][:70]}'
                  + (f'  <- fails {", ".join(issues)}' if issues else ""))
    print()
    for name, value in report["metrics"].items():
        threshold = LIVE_THRESHOLDS[name]
        mark = "ok  " if value >= threshold else "FAIL"
        print(f"  {mark} {name:<16} {value:6.1%}   (threshold {threshold:.0%})")


# -- entry point ---------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="run real searches through the configured provider")
    parser.add_argument("--case", help="offline: run a single case id")
    parser.add_argument("--limit", type=int, help="live: only the first N queries")
    parser.add_argument("--min-relevance", type=float, default=DEFAULT_MIN_RELEVANCE)
    parser.add_argument("--json", metavar="PATH", help="also write the full report as JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.live:
        report = asyncio.run(run_live(args.min_relevance, args.limit))
        print_live(report, args.verbose)
        thresholds = LIVE_THRESHOLDS
    else:
        report = run_offline(args.min_relevance, args.case)
        print_offline(report, args.verbose)
        thresholds = THRESHOLDS

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written to {args.json}")

    failed = [name for name, value in report["metrics"].items() if value < thresholds[name]]
    failed += [f"holdout {name}" for name, value in report.get("holdout_metrics", {}).items()
               if value < HOLDOUT_FLOOR]
    print("\nPASS" if not failed else f"\nFAIL: {', '.join(failed)} below threshold")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
