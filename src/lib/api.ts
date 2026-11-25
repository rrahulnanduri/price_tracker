import { readNdjson } from "./stream";

export interface Offer {
  store: string;
  title: string;
  price: number;
  price_text: string;
  url: string;
  /** null = not stated, 0 = free */
  shipping_cost: number | null;
  /** price + known shipping */
  total: number;
  in_stock: boolean | null;
  condition: string;
  /** 0..1: how confident the matcher is that this is the searched product */
  relevance: number;
  /** "ai" when the page was read by the LLM fallback instead of the scraper's selectors */
  extracted_by: "rules" | "ai";
  /** whether the LLM gave a second opinion on this listing */
  ai_checked: boolean;
  /** which price source found this offer, e.g. "google", "kieskeurig" */
  source: string;
}

export interface Watch {
  id: number;
  product: string;
  country: string;
  target_price: number | null;
  currency: string | null;
  latest_price: number | null;
  latest_store: string | null;
  latest_at: string | null;
  previous_price: number | null;
  lowest_ever: number | null;
  target_hit: boolean;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface SourceReport {
  name: string;
  ok: boolean;
  offers: number;
  error: string | null;
}

export interface SearchResponse {
  /** every source asked for this search, and whether it answered */
  sources: SourceReport[];
  product: string;
  country: string;
  region: string;
  currency: string;
  locale: string;
  provider: string;
  fetched_at: string;
  cached: boolean;
  results: Offer[];
  /** listings the source returned before relevance filtering */
  considered: number;
  rejected: number;
  /** true if any listing was read by the LLM fallback */
  ai_extracted: boolean;
  /** null if the LLM was not asked; otherwise how many listings it moved in or out */
  ai_changed: number | null;
  watch: Watch | null;
}

export interface HistoryPoint {
  fetched_at: string;
  lowest: number;
  lowest_store: string;
  stores: Record<string, number>;
}

export interface Region {
  code: string;
  label: string;
  currency: string;
  locale: string;
}

export interface Meta {
  provider: string;
  default_region: string;
  refresh_hours: number;
  cache_ttl_seconds: number;
  regions: Region[];
  ai: { model: string | null; fallback: boolean; judge: boolean };
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE = (import.meta.env?.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
/** Matches the backend's API_TOKEN, when one is set. */
const API_TOKEN: string | undefined = import.meta.env?.VITE_API_TOKEN;

function headers(withBody: boolean): Record<string, string> {
  return {
    ...(withBody ? { "Content-Type": "application/json" } : {}),
    ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
  };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: headers(Boolean(init.body)),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Backend unreachable. Is the API running?", 0);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new ApiError(detail ?? `Request failed (${res.status})`, res.status);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const getMeta = (signal?: AbortSignal) => request<Meta>("/api/meta", { signal });

export const searchPrices = (
  product: string,
  country: string,
  options: { refresh?: boolean; signal?: AbortSignal } = {},
) =>
  request<SearchResponse>("/api/search", {
    ...json("POST", { product, country, refresh: options.refresh ?? false }),
    signal: options.signal,
  });

/** Progress events streamed while a search runs (see /api/search/stream). */
export type SearchEvent =
  | { type: "sources"; names: string[] }
  | ({ type: "source" } & SourceReport)
  | { type: "stage"; stage: "matching" | "ai_review" }
  | { type: "result"; data: SearchResponse }
  | { type: "error"; status: number; detail: string };

/**
 * The same search as `searchPrices`, but reporting progress through `onEvent` as each
 * source answers. Falls back to the plain endpoint if the API has no streaming route.
 */
export async function searchPricesStream(
  product: string,
  country: string,
  options: { refresh?: boolean; signal?: AbortSignal; onEvent?: (event: SearchEvent) => void } = {},
): Promise<SearchResponse> {
  const body = { product, country, refresh: options.refresh ?? false };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/search/stream`, {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Backend unreachable. Is the API running?", 0);
  }

  if (res.status === 404 || res.status === 405 || !res.body) {
    return searchPrices(product, country, options);   // older API without streaming
  }
  if (!res.ok) {
    const detail = await res.json().then((b) => (typeof b?.detail === "string" ? b.detail : null), () => null);
    throw new ApiError(detail ?? `Request failed (${res.status})`, res.status);
  }

  let outcome: { data: SearchResponse } | { error: ApiError } | null = null;
  await readNdjson(res.body, (raw) => {
    const event = raw as SearchEvent;
    if (event.type === "result") outcome = { data: event.data };
    else if (event.type === "error") outcome = { error: new ApiError(event.detail, event.status) };
    else options.onEvent?.(event);
  });
  const final = outcome as { data: SearchResponse } | { error: ApiError } | null;
  if (!final) throw new ApiError("The search ended without an answer. Try again.", 0);
  if ("error" in final) throw final.error;
  return final.data;
}

export const getHistory = (product: string, country: string, signal?: AbortSignal) =>
  request<{ points: HistoryPoint[] }>(
    `/api/history?${new URLSearchParams({ product, country })}`,
    { signal },
  ).then((body) => body.points);

export const listWatches = (signal?: AbortSignal) =>
  request<{ items: Watch[] }>("/api/watchlist", { signal }).then((body) => body.items);

export const addWatch = (product: string, country: string, targetPrice: number | null) =>
  request<Watch>("/api/watchlist", json("POST", { product, country, target_price: targetPrice }));

export const updateWatch = (id: number, targetPrice: number | null) =>
  request<Watch>(`/api/watchlist/${id}`, json("PATCH", { target_price: targetPrice }));

export const deleteWatch = (id: number) =>
  request<void>(`/api/watchlist/${id}`, { method: "DELETE" });
