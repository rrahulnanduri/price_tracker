import { useEffect, useState } from "react";

/**
 * Load a value whenever `key` changes; `null` key means "nothing to load".
 * Returns null while loading or after a failure: callers treat both as "no data yet".
 */
export function useRemote<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): T | null {
  const [state, setState] = useState<{ key: string; value: T } | null>(null);

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    load(controller.signal)
      .then((value) => setState({ key, value }))
      .catch(() => {
        if (!controller.signal.aborted) setState(null);
      });
    return () => controller.abort();
    // `load` is recreated every render; `key` is what identifies the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // A value loaded for a previous key is stale, not current.
  return state && state.key === key ? state.value : null;
}
