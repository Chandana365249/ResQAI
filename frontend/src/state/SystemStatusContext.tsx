import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, getHealth, getReadiness, type HealthResponse, type ReadinessResponse } from "../api";
import { describeError, type UserFacingError } from "../lib/errors";

export type SystemStatusState =
  | { status: "loading" }
  /** The backend did not answer yet; retrying (free hosting sleeps when idle and takes about a minute to wake). */
  | { status: "waking"; attempt: number }
  | { status: "unreachable"; error: UserFacingError }
  | { status: "loaded"; health: HealthResponse; readiness: ReadinessResponse };

interface SystemStatusValue {
  state: SystemStatusState;
  refresh: () => Promise<void>;
}

const SystemStatusContext = createContext<SystemStatusValue | null>(null);

/** Retry budget for the FIRST load only: 6 retries, 10 s apart (plus each attempt's own timeout). */
export const WAKE_RETRIES = 6;
export const WAKE_DELAY_MS = 10_000;

/** An unreachable/slow backend may just be starting; a misconfigured or answering one will not fix itself. */
function mayBeWakingUp(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === "network" || error.kind === "timeout");
}

interface ProviderProps {
  children: ReactNode;
  fetchHealth?: () => Promise<HealthResponse>;
  fetchReadiness?: () => Promise<ReadinessResponse>;
  wakeRetries?: number;
  wakeDelayMs?: number;
}

/** Fetched on load (with patient retries while the backend wakes) and on demand (Refresh); never polled. */
export function SystemStatusProvider({
  children, fetchHealth = getHealth, fetchReadiness = getReadiness,
  wakeRetries = WAKE_RETRIES, wakeDelayMs = WAKE_DELAY_MS,
}: ProviderProps) {
  const [state, setState] = useState<SystemStatusState>({ status: "loading" });
  const cancelled = useRef(false);

  const fetchOnce = useCallback(async (): Promise<SystemStatusState> => {
    const [health, readiness] = await Promise.all([fetchHealth(), fetchReadiness()]);
    return { status: "loaded", health, readiness };
  }, [fetchHealth, fetchReadiness]);

  /** Manual refresh: a single attempt, so a click always gives a prompt answer. */
  const refresh = useCallback(async () => {
    setState({ status: "loading" });
    try {
      setState(await fetchOnce());
    } catch (err) {
      setState({ status: "unreachable", error: describeError(err) });
    }
  }, [fetchOnce]);

  useEffect(() => {
    cancelled.current = false;
    void (async () => {
      for (let attempt = 0; attempt <= wakeRetries; attempt++) {
        try {
          const next = await fetchOnce();
          if (!cancelled.current) setState(next);
          return;
        } catch (err) {
          if (cancelled.current) return;
          if (attempt === wakeRetries || !mayBeWakingUp(err)) {
            setState({ status: "unreachable", error: describeError(err) });
            return;
          }
          setState({ status: "waking", attempt: attempt + 1 });
          await new Promise((resolve) => setTimeout(resolve, wakeDelayMs));
        }
      }
    })();
    return () => {
      cancelled.current = true;
    };
  }, [fetchOnce, wakeRetries, wakeDelayMs]);

  const value = useMemo(() => ({ state, refresh }), [state, refresh]);
  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}

export function useSystemStatus(): SystemStatusValue {
  const ctx = useContext(SystemStatusContext);
  if (!ctx) throw new Error("useSystemStatus must be used inside <SystemStatusProvider>.");
  return ctx;
}
