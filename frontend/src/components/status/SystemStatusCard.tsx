import { CheckCircle2, CircleSlash, RefreshCw } from "lucide-react";
import { getApiBaseUrl, type ComponentHealth } from "../../api";
import { humanize } from "../../lib/format";
import { useSystemStatus } from "../../state/SystemStatusContext";
import { Card } from "../common/Card";
import { ErrorPanel, Spinner } from "../common/Feedback";

const COMPONENT_LABELS: Record<string, string> = {
  api: "API",
  report_parser: "Report intelligence (parser)",
  risk_engine: "Risk indicator engine",
  decision_engine: "Decision engine",
  resource_catalog: "Demo resource catalog",
  historical_model: "Historical severity model",
  report_compatible_model: "Report-compatible severity model",
};

function ComponentRow({ name, component }: { name: string; component: ComponentHealth }) {
  const up = component.status !== "unavailable";
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
      <div>
        <p className="text-sm font-medium text-slate-900">{COMPONENT_LABELS[name] ?? humanize(name)}</p>
        {component.detail && <p className="text-xs text-slate-600">{component.detail}</p>}
      </div>
      <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${up ? "bg-emerald-50 text-emerald-900 ring-emerald-300" : "bg-red-50 text-red-900 ring-red-300"}`}>
        {up ? <CheckCircle2 aria-hidden className="size-3.5" /> : <CircleSlash aria-hidden className="size-3.5" />}
        {up ? (component.status === "available" ? "Available" : "Operational") : "Unavailable"}
      </span>
    </li>
  );
}

const OVERALL_LABEL = {
  healthy: "Healthy",
  degraded: "Degraded — service works but a severity model is unavailable",
  unavailable: "Unavailable — a required component is down",
} as const;

export function SystemStatusCard() {
  const { state, refresh } = useSystemStatus();

  return (
    <Card
      id="system-status"
      title="ResQAI system status"
      origin="system"
      actions={
        <button
          type="button" onClick={() => void refresh()} disabled={state.status === "loading"}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw aria-hidden className="size-3.5" /> Refresh
        </button>
      }
    >
      {state.status === "loading" && <Spinner label="Checking the ResQAI service…" />}
      {state.status === "waking" && (
        <Spinner label={`The service has not answered yet (attempt ${state.attempt}); it may be waking up after being idle, which can take about a minute. Retrying…`} />
      )}
      {state.status === "unreachable" && <ErrorPanel error={state.error} onRetry={() => void refresh()} />}
      {state.status === "loaded" && (
        <div className="space-y-4">
          <dl className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Health</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">{OVERALL_LABEL[state.health.status]}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Readiness</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">
                {state.readiness.status === "READY" ? "Ready to analyze reports" : "Not ready"}
              </dd>
              {state.readiness.reasons.map((reason) => <dd key={reason} className="text-xs text-red-800">{reason}</dd>)}
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">Backend</dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">
                {state.health.service} v{state.health.version}
              </dd>
              <dd className="text-xs text-slate-600">Environment: {state.health.environment}</dd>
            </div>
          </dl>

          <ul className="divide-y divide-slate-100 rounded-md border border-slate-200" aria-label="Components">
            {Object.entries(state.health.components).map(([name, component]) => (
              <ComponentRow key={name} name={name} component={component} />
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-xs text-slate-600">
        Dashboard is connected to{" "}
        {getApiBaseUrl() ? <span className="font-mono">{getApiBaseUrl()}</span> : <strong>(no backend URL configured)</strong>}
      </p>
    </Card>
  );
}
