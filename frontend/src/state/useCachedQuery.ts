import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, type UserFacingError } from "../lib/errors";

/**
 * Tiny session cache for STABLE reads (demo resource catalog, model info,
 * model metrics): fetched once per browser session and shared by every
 * component that asks for the same key. `reload()` bypasses the cache.
 */
const cache = new Map<string, unknown>();
const inFlight = new Map<string, Promise<unknown>>();

export function clearQueryCache(): void {
  cache.clear();
  inFlight.clear();
}

export interface QueryState<T> {
  data: T | null;
  error: UserFacingError | null;
  loading: boolean;
  reload: () => void;
}

export function useCachedQuery<T>(key: string, fetcher: () => Promise<T>): QueryState<T> {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [data, setData] = useState<T | null>(() => (cache.has(key) ? (cache.get(key) as T) : null));
  const [error, setError] = useState<UserFacingError | null>(null);
  const [loading, setLoading] = useState<boolean>(!cache.has(key));

  const load = useCallback(
    async (force: boolean) => {
      if (!force && cache.has(key)) {
        setData(cache.get(key) as T);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        let pending = inFlight.get(key) as Promise<T> | undefined;
        if (!pending || force) {
          pending = fetcherRef.current();
          inFlight.set(key, pending);
        }
        const result = await pending;
        cache.set(key, result);
        setData(result);
      } catch (err) {
        setError(describeError(err));
      } finally {
        inFlight.delete(key);
        setLoading(false);
      }
    },
    [key],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const reload = useCallback(() => void load(true), [load]);
  return { data, error, loading, reload };
}
