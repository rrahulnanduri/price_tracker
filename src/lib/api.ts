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

export interface SearchResponse {
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
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE = (import.meta.env?.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init.body ? { "Content-Type": "application/json" } : undefined,
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
