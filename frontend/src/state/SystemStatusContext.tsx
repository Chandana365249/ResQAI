import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getHealth, getReadiness, type HealthResponse, type ReadinessResponse } from "../api";
import { describeError, type UserFacingError } from "../lib/errors";

export type SystemStatusState =
  | { status: "loading" }
  | { status: "unreachable"; error: UserFacingError }
  | { status: "loaded"; health: HealthResponse; readiness: ReadinessResponse };

interface SystemStatusValue {
  state: SystemStatusState;
  refresh: () => Promise<void>;
}

const SystemStatusContext = createContext<SystemStatusValue | null>(null);

interface ProviderProps {
  children: ReactNode;
  fetchHealth?: () => Promise<HealthResponse>;
  fetchReadiness?: () => Promise<ReadinessResponse>;
}

/** Fetched once on load and on demand (Refresh) -- not polled. */
export function SystemStatusProvider({ children, fetchHealth = getHealth, fetchReadiness = getReadiness }: ProviderProps) {
  const [state, setState] = useState<SystemStatusState>({ status: "loading" });

  const refresh = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const [health, readiness] = await Promise.all([fetchHealth(), fetchReadiness()]);
      setState({ status: "loaded", health, readiness });
    } catch (err) {
      setState({ status: "unreachable", error: describeError(err) });
    }
  }, [fetchHealth, fetchReadiness]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(() => ({ state, refresh }), [state, refresh]);
  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}

export function useSystemStatus(): SystemStatusValue {
  const ctx = useContext(SystemStatusContext);
  if (!ctx) throw new Error("useSystemStatus must be used inside <SystemStatusProvider>.");
  return ctx;
}
