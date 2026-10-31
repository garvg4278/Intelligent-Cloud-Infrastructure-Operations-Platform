import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/errors";

export interface Resource<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  reload: () => void;
  /** Replace the data locally (optimistic updates, "load more"). */
  setData: (updater: (current: T | null) => T | null) => void;
}

/**
 * Loads data and exposes loading/error state.
 * - Aborts the in-flight request on unmount or when `deps` change, so a slow
 *   response for the previous filter can never overwrite the current one.
 * - Keeps showing the previous data while reloading (no flash of empty UI).
 */
export function useResource<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[]): Resource<T> {
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetcherRef
      .current(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setDataState(result);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason : new Error("Request failed"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  const setData = useCallback((updater: (current: T | null) => T | null) => setDataState(updater), []);
  return { data, error, loading, reload, setData };
}
