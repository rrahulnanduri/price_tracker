import { useCallback, useEffect, useRef, useState } from "react";
import { searchPricesStream, type SearchEvent, type SearchResponse } from "@/lib/api";

export type SourceState = { name: string; status: "pending" | "done" | "failed"; offers: number; error: string | null };

export interface SearchProgress {
  /** null until the API says which sources it is asking */
  sources: SourceState[] | null;
  stage: "fetching" | "matching" | "ai_review";
}

const START: SearchProgress = { sources: null, stage: "fetching" };

/** Fold one progress event into the progress state. */
export function applyEvent(progress: SearchProgress, event: SearchEvent): SearchProgress {
  switch (event.type) {
    case "sources":
      return {
        ...progress,
        sources: event.names.map((name) => ({ name, status: "pending", offers: 0, error: null })),
      };
    case "source":
      return {
        ...progress,
        sources: (progress.sources ?? [{ name: event.name, status: "pending", offers: 0, error: null }]).map(
          (s) =>
            s.name === event.name
              ? { ...s, status: event.ok ? "done" : "failed", offers: event.offers, error: event.error }
              : s,
        ),
      };
    case "stage":
      return { ...progress, stage: event.stage };
    default:
      return progress;
  }
}

/** 0..1 for the progress bar: sources answering fill most of it, matching the rest. */
export function progressFraction(progress: SearchProgress): number {
  if (progress.stage === "matching") return 0.92;
  if (progress.stage === "ai_review") return 0.96;
  const sources = progress.sources;
  if (!sources || sources.length === 0) return 0.08;
  const finished = sources.filter((s) => s.status !== "pending").length;
  return 0.12 + (finished / sources.length) * 0.74;
}

export function usePriceSearch() {
  const [data, setData] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<SearchProgress>(START);
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => () => inFlight.current?.abort(), []);

  const search = useCallback(async (product: string, country: string, refresh = false) => {
    const query = product.trim();
    if (!query) return;

    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;

    setIsLoading(true);
    setError(null);
    setData(null);
    setProgress(START);

    try {
      const result = await searchPricesStream(query, country, {
        refresh,
        signal: controller.signal,
        onEvent: (event) => {
          if (!controller.signal.aborted) setProgress((current) => applyEvent(current, event));
        },
      });
      if (!controller.signal.aborted) setData(result);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (inFlight.current === controller) setIsLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    inFlight.current?.abort();
    setData(null);
    setError(null);
    setIsLoading(false);
    setProgress(START);
  }, []);

  return { data, isLoading, error, progress, search, clear };
}
