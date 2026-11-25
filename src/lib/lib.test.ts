import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, deleteWatch, getHistory, searchPrices, type HistoryPoint } from "./api";
import { assignColors, historyStats, seriesStores, toChartRows } from "./chart";
import { formatAge, formatMoney, formatPercent, parseTarget, percentChange } from "./format";
import { countryForLanguage, countryForTimezone, pickSupported } from "./region";

describe("region detection", () => {
  it("maps timezones to countries, exact zones before continent fallbacks", () => {
    expect(countryForTimezone("America/Toronto")).toBe("CA");
    expect(countryForTimezone("America/New_York")).toBe("US");
    expect(countryForTimezone("Europe/Amsterdam")).toBe("NL");
    expect(countryForTimezone("Australia/Sydney")).toBe("AU");
    expect(countryForTimezone("Africa/Lagos")).toBeNull();
    expect(countryForTimezone("")).toBeNull();
  });

  it("reads the region from a language tag", () => {
    expect(countryForLanguage("nl-NL")).toBe("NL");
    expect(countryForLanguage("en-gb")).toBe("GB");
    expect(countryForLanguage("en")).toBeNull();
    expect(countryForLanguage("")).toBeNull();
  });

  it("falls back when the detected country is not supported", () => {
    expect(pickSupported(["NL"], ["US", "NL"], "US")).toBe("NL");
    expect(pickSupported(["BR"], ["US", "NL"], "US")).toBe("US");
    expect(pickSupported([null, "NL"], ["US", "NL"], "US")).toBe("NL");
  });
});

describe("formatting", () => {
  it("formats money in the region's own style", () => {
    expect(formatMoney(1299.5, "USD", "en-US")).toBe("$1,299.50");
    expect(formatMoney(1299.5, "EUR", "de-DE")).toMatch(/1\.299,50\s€/);
    expect(formatMoney(150000, "JPY", "ja-JP")).toMatch(/150,000/);
    expect(formatMoney(5, "NOPE", "en-US")).toBe("5.00 NOPE");
  });

  it("describes how old a check is", () => {
    const now = Date.parse("2026-11-11T12:00:00Z");
    expect(formatAge("2026-11-11T11:59:30Z", now)).toBe("JUST NOW");
    expect(formatAge("2026-11-11T11:15:00Z", now)).toBe("45 MIN AGO");
    expect(formatAge("2026-11-11T09:00:00Z", now)).toBe("3 H AGO");
    expect(formatAge("2026-11-08T12:00:00Z", now)).toBe("3 D AGO");
    expect(formatAge("2026-11-11T12:05:00Z", now)).toBe("JUST NOW"); // clock skew
    expect(formatAge("not a date", now)).toBe("");
  });

  it("computes and formats price changes", () => {
    expect(percentChange(100, 95)).toBeCloseTo(-5);
    expect(percentChange(0, 95)).toBe(0);
    expect(formatPercent(-5)).toBe("-5.0%");
    expect(formatPercent(2.34)).toBe("+2.3%");
    expect(formatPercent(0.01)).toBe("0.0%");
  });

  it("parses a typed target price", () => {
    expect(parseTarget("299")).toBe(299);
    expect(parseTarget(" 299,50 ")).toBe(299.5);
    expect(parseTarget("")).toBeNull();
    expect(parseTarget("abc")).toBeNull();
    expect(parseTarget("-5")).toBeNull();
    expect(parseTarget("0")).toBeNull();
  });
});

describe("chart helpers", () => {
  const points: HistoryPoint[] = [
    { fetched_at: "2026-11-01T10:00:00Z", lowest: 500, lowest_store: "A", stores: { A: 500, B: 520 } },
    { fetched_at: "2026-11-02T10:00:00Z", lowest: 480, lowest_store: "B", stores: { A: 510, B: 480, C: 530 } },
  ];

  it("gives each store a stable, distinct colour", () => {
    const first = assignColors(["AMAZON", "BEST BUY", "WALMART", "TARGET", "NEWEGG"]);
    expect(assignColors(["AMAZON"]).AMAZON).toBe(first.AMAZON);
    expect(new Set(Object.values(first)).size).toBe(5);
  });

  it("charts the stores in the latest check, cheapest first", () => {
    expect(seriesStores(points)).toEqual(["B", "A", "C"]);
    expect(seriesStores([])).toEqual([]);
  });

  it("leaves a gap where a store had no offer", () => {
    const rows = toChartRows(points, ["A", "C"], (iso) => iso.slice(8, 10));
    expect(rows).toEqual([
      { label: "01", fetched_at: points[0].fetched_at, A: 500 },
      { label: "02", fetched_at: points[1].fetched_at, A: 510, C: 530 },
    ]);
  });

  it("summarises the lowest price over time", () => {
    expect(historyStats(points)).toEqual({ lowest: 480, highest: 500, first: 500, latest: 480 });
    expect(historyStats([])).toBeNull();
  });
});

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  const respond = (status: number, body?: unknown) =>
    vi.fn().mockResolvedValue(
      new Response(body === undefined ? null : JSON.stringify(body), { status }),
    );

  it("posts a search and returns the body", async () => {
    const fetchMock = respond(200, { results: [] });
    vi.stubGlobal("fetch", fetchMock);
    await searchPrices("ps5", "NL", { refresh: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/search");
    expect(JSON.parse(init.body)).toEqual({ product: "ps5", country: "NL", refresh: true });
  });

  it("surfaces the server's error detail and status", async () => {
    vi.stubGlobal("fetch", respond(429, { detail: "Too many searches. Try again in 30s." }));
    await expect(searchPrices("ps5", "US")).rejects.toMatchObject({
      message: "Too many searches. Try again in 30s.",
      status: 429,
    });
  });

  it("copes with non-JSON errors and an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 500 })));
    await expect(searchPrices("ps5", "US")).rejects.toThrow("Request failed (500)");

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(searchPrices("ps5", "US")).rejects.toBeInstanceOf(ApiError);
  });

  it("encodes query parameters and handles empty responses", async () => {
    const fetchMock = respond(200, { points: [] });
    vi.stubGlobal("fetch", fetchMock);
    expect(await getHistory("ps5 & more", "US")).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toContain("product=ps5+%26+more&country=US");

    vi.stubGlobal("fetch", respond(204));
    await expect(deleteWatch(1)).resolves.toBeUndefined();
  });
});

describe("progress stream", () => {
  it("splits chunks into lines, holding back partial lines", async () => {
    const { createLineParser } = await import("./stream");
    const lines: string[] = [];
    const parser = createLineParser((line) => lines.push(line));
    parser.push('{"a":1}\n{"b"');
    expect(lines).toEqual(['{"a":1}']);
    parser.push(':2}\n\n{"c":3}');
    parser.end();
    expect(lines).toEqual(['{"a":1}', '{"b":2}', '{"c":3}']);
  });

  it("folds events into progress", async () => {
    const { applyEvent, progressFraction } = await import("../hooks/usePriceSearch");
    let p = { sources: null, stage: "fetching" as const } as Parameters<typeof applyEvent>[0];
    expect(progressFraction(p)).toBeCloseTo(0.08);
    p = applyEvent(p, { type: "sources", names: ["google", "kieskeurig"] });
    expect(p.sources?.map((s) => s.status)).toEqual(["pending", "pending"]);
    p = applyEvent(p, { type: "source", name: "google", ok: false, offers: 0, error: "blocked" });
    p = applyEvent(p, { type: "source", name: "kieskeurig", ok: true, offers: 18, error: null });
    expect(p.sources).toEqual([
      { name: "google", status: "failed", offers: 0, error: "blocked" },
      { name: "kieskeurig", status: "done", offers: 18, error: null },
    ]);
    expect(progressFraction(p)).toBeCloseTo(0.86);
    p = applyEvent(p, { type: "stage", stage: "matching" });
    expect(progressFraction(p)).toBeCloseTo(0.92);
  });

  const ndjson = (events: unknown[], status = 200) =>
    new Response(events.map((e) => JSON.stringify(e)).join("\n") + "\n", {
      status,
      headers: { "Content-Type": "application/x-ndjson" },
    });

  it("streams progress, then returns the result", async () => {
    const { searchPricesStream } = await import("./api");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ndjson([
      { type: "sources", names: ["kieskeurig"] },
      { type: "source", name: "kieskeurig", ok: true, offers: 3, error: null },
      { type: "stage", stage: "matching" },
      { type: "result", data: { product: "ps5", results: [] } },
    ])));
    const seen: string[] = [];
    const result = await searchPricesStream("ps5", "NL", { onEvent: (e) => seen.push(e.type) });
    expect(seen).toEqual(["sources", "source", "stage"]);
    expect(result).toMatchObject({ product: "ps5" });
  });

  it("turns an error event into an ApiError", async () => {
    const { searchPricesStream } = await import("./api");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ndjson([
      { type: "sources", names: ["google"] },
      { type: "error", status: 503, detail: "Google is rate-limiting this address." },
    ])));
    await expect(searchPricesStream("ps5", "US")).rejects.toMatchObject({
      status: 503,
      message: "Google is rate-limiting this address.",
    });
  });

  it("falls back to the plain endpoint on an older API", async () => {
    const { searchPricesStream } = await import("./api");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 404 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ product: "ps5", results: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(searchPricesStream("ps5", "US")).resolves.toMatchObject({ product: "ps5" });
    expect(fetchMock.mock.calls[1][0]).toBe("http://localhost:8000/api/search");
  });

  it("reports a stream that ends without an answer", async () => {
    const { searchPricesStream } = await import("./api");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ndjson([{ type: "sources", names: ["google"] }])));
    await expect(searchPricesStream("ps5", "US")).rejects.toThrow("ended without an answer");
  });
});
