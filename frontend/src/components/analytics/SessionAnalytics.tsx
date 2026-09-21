import { Trash2 } from "lucide-react";
import { summarizeSession } from "../../lib/analytics";
import { formatPercent, formatTimestamp, humanize, sourceLabel } from "../../lib/format";
import type { SessionRecord } from "../../lib/sessionHistory";
import { PriorityBadge } from "../common/Badges";
import { Card } from "../common/Card";
import { EmptyState } from "../common/Feedback";
import { CountBarChart } from "./CountBarChart";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">{label}</dt>
      <dd className="mt-1 text-2xl font-bold tabular-nums text-slate-900">{value}</dd>
      {hint && <dd className="text-xs text-slate-600">{hint}</dd>}
    </div>
  );
}

interface SessionAnalyticsProps {
  records: SessionRecord[];
  onClear: () => void;
}

/** Every number here is computed from the analyses stored in THIS browser -- nothing is sampled or invented. */
export function SessionAnalytics({ records, onClear }: SessionAnalyticsProps) {
  const summary = summarizeSession(records);

  return (
    <Card
      id="session-analytics"
      title="Session analytics"
      origin="system"
      description="Computed from the analyses run in this browser. Local demo data only; the backend keeps no history."
      actions={
        records.length > 0 ? (
          <button
            type="button" onClick={onClear}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50"
          >
            <Trash2 aria-hidden className="size-3.5" /> Clear session history
          </button>
        ) : undefined
      }
    >
      {records.length === 0 ? (
        <EmptyState title="No session analytics yet.">Run a few analyses to populate session analytics.</EmptyState>
      ) : (
        <div className="space-y-5">
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Reports analyzed" value={String(summary.total)} />
            <Stat
              label="Prediction available" value={String(summary.predictionAvailable)}
              hint={`${summary.predictionUnavailable} without a prediction`}
            />
            <Stat
              label="Model/rule disagreements" value={String(summary.disagreements)}
              hint={summary.disagreementRate === null ? undefined : `${formatPercent(summary.disagreementRate)} of analyses`}
            />
            <Stat
              label="Most frequent risk indicator"
              value={summary.mostFrequentRiskIndicator ? humanize(summary.mostFrequentRiskIndicator.key) : "None detected"}
              hint={summary.mostFrequentRiskIndicator ? `in ${summary.mostFrequentRiskIndicator.count} analyses` : undefined}
            />
          </dl>

          <div className="grid gap-4 lg:grid-cols-2">
            <CountBarChart
              title="Prediction source" unit="analyses" data={summary.predictionSources}
              labelFor={(k) => sourceLabel(k as never)} emptyMessage="No analyses yet."
            />
            <CountBarChart
              title="Priority assigned" unit="analyses" data={summary.priorities}
              emptyMessage="No analyses yet."
            />
            <CountBarChart
              title="Risk indicator frequency" unit="analyses" data={summary.riskIndicators}
              labelFor={humanize} emptyMessage="No risk indicators were detected in these analyses."
            />
            <CountBarChart
              title="Predicted severity" unit="analyses" data={summary.predictedSeverities}
              emptyMessage="No predictions were available in these analyses."
            />
          </div>

          <div>
            <h3 className="text-sm font-semibold text-slate-900">Recent analyses (local demo history)</h3>
            <ul className="mt-2 divide-y divide-slate-100 rounded-md border border-slate-200">
              {records.slice(0, 10).map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-sm">
                  <PriorityBadge priority={r.priority} />
                  <span className="font-medium text-slate-900">{humanize(r.incidentType)}</span>
                  <span className="text-slate-700">{sourceLabel(r.predictionSource)}</span>
                  <span className="text-xs text-slate-600">{formatTimestamp(r.analyzedAt)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-600">
              Only outcome metadata is stored (no report text, coordinates or personal details), up to 50 analyses, in this browser only.
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}
