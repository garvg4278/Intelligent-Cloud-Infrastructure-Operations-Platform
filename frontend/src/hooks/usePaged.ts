import { useCallback, useEffect, useRef, useState } from "react";
import { PAGE_SIZE } from "../config/constants";

/**
 * Accumulating "load more" pagination over an offset/limit API.
 * Starts again from page one whenever `deps` change (a filter) or `reload()`
 * is called (after a mutation); a response for a superseded request is dropped.
 */
export function usePaged<T>(fetchPage: (offset: number, signal: AbortSignal) => Promise<T[]>, deps: readonly unknown[]) {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [exhausted, setExhausted] = useState(false);
  const [tick, setTick] = useState(0);
  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;
  const rowCount = useRef(0);
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (reset: boolean) => {
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    setLoading(true);
    setError(null);
    try {
      const page = await fetchRef.current(reset ? 0 : rowCount.current, ctl.signal);
      if (ctl.signal.aborted) return;
      setRows((current) => {
        const next = reset ? page : [...current, ...page];
        rowCount.current = next.length;
        return next;
      });
      setExhausted(page.length < PAGE_SIZE);
    } catch (reason) {
      if (ctl.signal.aborted) return;
      setError(reason instanceof Error ? reason : new Error("Request failed"));
    } finally {
      if (!ctl.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void run(true);
    return () => controller.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, run]);

  return {
    rows,
    loading,
    error,
    exhausted,
    loadMore: () => void run(false),
    reload: useCallback(() => setTick((n) => n + 1), []),
    replaceRow: (match: (row: T) => boolean, next: T) => setRows((list) => list.map((r) => (match(r) ? next : r))),
  };
}
