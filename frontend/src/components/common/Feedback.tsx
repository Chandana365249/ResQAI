import type { ReactNode } from "react";
import { AlertTriangle, Loader2, RotateCw } from "lucide-react";
import type { UserFacingError } from "../../lib/errors";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {children && <p className="mt-1 text-sm text-slate-600">{children}</p>}
    </div>
  );
}

/** Indeterminate spinner: no fake percentages or invented stages. */
export function Spinner({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-slate-700">
      <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
      <span>{label}</span>
    </div>
  );
}

interface ErrorPanelProps {
  error: UserFacingError;
  onRetry?: () => void;
}

/** Human-readable failure message; never a stack trace or raw JSON. */
export function ErrorPanel({ error, onRetry }: ErrorPanelProps) {
  return (
    <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0 text-red-700" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-red-900">{error.title}</p>
          <p className="mt-1 text-sm text-red-900">{error.message}</p>
          {error.requestId && (
            <p className="mt-2 text-xs text-red-800">
              Reference: <span className="font-mono">{error.requestId}</span>
            </p>
          )}
          {error.retryable && onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-red-400 bg-white px-3 py-1.5 text-sm font-medium text-red-900 hover:bg-red-100"
            >
              <RotateCw aria-hidden className="size-4" />
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
