import { useCallback, useEffect, useRef, useState } from "react";
import { searchPrices, type SearchResponse } from "@/lib/api";

export function usePriceSearch() {
  const [data, setData] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

    try {
      setData(await searchPrices(query, country, { refresh, signal: controller.signal }));
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
  }, []);

  return { data, isLoading, error, search, clear };
}
