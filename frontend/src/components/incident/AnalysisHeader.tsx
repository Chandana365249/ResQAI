import type { ReactNode } from "react";
import { Download } from "lucide-react";
import type { AnalyzeResponse } from "../../api";
import { humanize, sourceLabel } from "../../lib/format";
import { HumanOversightNotice } from "../layout/AppShell";
import { LevelBadge, PriorityBadge } from "../common/Badges";
import { OriginTag, type Origin } from "../common/Card";

function Tile({ label, origin, children }: { label: string; origin: Origin; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{label}</p>
        <OriginTag origin={origin} />
      </div>
      <div className="min-h-9">{children}</div>
    </div>
  );
}

function downloadJson(result: AnalyzeResponse): void {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `resqai-analysis-${result.request_id}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * The first thing a dispatcher sees. Four SEPARATE tiles -- there is
 * deliberately no combined "AI score": incident type (from the report),
 * priority and operational risk (project rules), and the statistical model's
 * prediction each keep their own label and origin.
 */
export function AnalysisHeader({ result }: { result: AnalyzeResponse }) {
  const { incident, decision, ml_prediction: ml } = result;
  return (
    <section aria-labelledby="result-heading" className="section-in rounded-lg border border-slate-300 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
        <div>
          <h2 id="result-heading" className="text-lg font-bold text-slate-900">Incident analysis</h2>
          <p className="text-xs text-slate-600">
            Request <span className="font-mono">{result.request_id}</span> · analysed in {Math.round(result.processing_time_ms)} ms
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <HumanOversightNotice />
          <button
            type="button" onClick={() => downloadJson(result)}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
          >
            <Download aria-hidden className="size-3.5" /> Download JSON
          </button>
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-4">
        <Tile label="Incident" origin="report">
          <p className="text-lg font-semibold leading-tight text-slate-900">{humanize(incident.incident_type)}</p>
          {incident.incident_subtype && <p className="text-sm text-slate-700">{incident.incident_subtype}</p>}
        </Tile>

        <Tile label="Priority" origin="rules">
          <div className="flex items-center gap-2">
            <PriorityBadge priority={decision.priority} large />
            <span className="text-xs text-slate-600">P0 highest → P3 lowest</span>
          </div>
        </Tile>

        <Tile label="Operational risk" origin="rules">
          <div className="flex items-center gap-2">
            <LevelBadge level={decision.risk_level} />
            <span className="text-xs text-slate-600">
              {result.risk_indicators.length} indicator{result.risk_indicators.length === 1 ? "" : "s"}
            </span>
          </div>
        </Tile>

        <Tile label="Model prediction" origin="model">
          {ml.available && ml.predicted_label ? (
            <>
              <p className="text-base font-semibold leading-tight text-slate-900">{ml.predicted_label}</p>
              <p className="text-xs text-slate-600">via {sourceLabel(ml.prediction_source)}</p>
            </>
          ) : (
            <>
              <p className="text-base font-semibold leading-tight text-slate-700">Unavailable</p>
              <p className="text-xs text-slate-600">No legitimate model input</p>
            </>
          )}
        </Tile>
      </div>
    </section>
  );
}
