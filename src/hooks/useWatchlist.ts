import { useCallback, useEffect, useState } from "react";
import { addWatch, deleteWatch, listWatches, updateWatch, type Watch } from "@/lib/api";

export function useWatchlist() {
  const [items, setItems] = useState<Watch[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setItems(await listWatches());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the watchlist");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  /** Run a change, then refresh the list; report failure instead of throwing. */
  const mutate = useCallback(
    async (change: () => Promise<unknown>) => {
      try {
        await change();
        await reload();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Watchlist update failed");
        return false;
      }
    },
    [reload],
  );

  const track = useCallback(
    (product: string, country: string, target: number | null) =>
      mutate(() => addWatch(product, country, target)),
    [mutate],
  );
  const setTarget = useCallback(
    (id: number, target: number | null) => mutate(() => updateWatch(id, target)),
    [mutate],
  );
  const untrack = useCallback((id: number) => mutate(() => deleteWatch(id)), [mutate]);

  return { items, error, reload, track, setTarget, untrack };
}

/** The watchlist entry for a product in a region, ignoring case and spacing. */
export function findWatch(items: Watch[], product: string, country: string): Watch | undefined {
  const key = product.toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  return items.find(
    (w) => w.country === country && w.product.toLowerCase().split(/\s+/).join(" ") === key,
  );
}
