import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { analyzeReport, type AnalyzeRequest, type AnalyzeResponse } from "../api";
import { describeError, type UserFacingError } from "../lib/errors";
import { EMPTY_FORM, type ReportFormValues } from "../lib/reportForm";
import {
  addRecord, clearStoredHistory, loadHistory, saveHistory, toSessionRecord, type SessionRecord,
} from "../lib/sessionHistory";

export type AnalysisState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: AnalyzeResponse }
  | { status: "error"; error: UserFacingError };

interface AnalysisContextValue {
  state: AnalysisState;
  /** The form contents live here so navigating between pages does not lose the draft. */
  draft: ReportFormValues;
  setDraft: (values: ReportFormValues) => void;
  submit: (request: AnalyzeRequest) => Promise<void>;
  retry: () => Promise<void>;
  history: SessionRecord[];
  clearHistory: () => void;
}

const AnalysisContext = createContext<AnalysisContextValue | null>(null);

interface ProviderProps {
  children: ReactNode;
  /** Injection point for tests; production uses the real API client. */
  analyze?: (request: AnalyzeRequest) => Promise<AnalyzeResponse>;
}

export function AnalysisProvider({ children, analyze = analyzeReport }: ProviderProps) {
  const [state, setState] = useState<AnalysisState>({ status: "idle" });
  const [draft, setDraft] = useState<ReportFormValues>(EMPTY_FORM);
  const [history, setHistory] = useState<SessionRecord[]>(() => loadHistory());
  const lastRequest = useRef<AnalyzeRequest | null>(null);
  const inFlight = useRef(false);

  const submit = useCallback(
    async (request: AnalyzeRequest) => {
      if (inFlight.current) return; // prevents accidental duplicate submissions
      inFlight.current = true;
      lastRequest.current = request;
      setState({ status: "loading" });
      try {
        const result = await analyze(request);
        setState({ status: "success", result });
        setHistory((prev) => {
          const next = addRecord(prev, toSessionRecord(result));
          saveHistory(next);
          return next;
        });
      } catch (err) {
        setState({ status: "error", error: describeError(err) });
      } finally {
        inFlight.current = false;
      }
    },
    [analyze],
  );

  const retry = useCallback(async () => {
    if (lastRequest.current) await submit(lastRequest.current);
  }, [submit]);

  const clearHistory = useCallback(() => {
    clearStoredHistory();
    setHistory([]);
  }, []);

  const value = useMemo(
    () => ({ state, draft, setDraft, submit, retry, history, clearHistory }),
    [state, draft, submit, retry, history, clearHistory],
  );
  return <AnalysisContext.Provider value={value}>{children}</AnalysisContext.Provider>;
}

export function useAnalysis(): AnalysisContextValue {
  const ctx = useContext(AnalysisContext);
  if (!ctx) throw new Error("useAnalysis must be used inside <AnalysisProvider>.");
  return ctx;
}
