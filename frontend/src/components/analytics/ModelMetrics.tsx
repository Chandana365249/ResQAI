import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getModelMetrics, type ModelEvaluation, type ModelMetricsEntry } from "../../api";
import { formatPercent } from "../../lib/format";
import { useCachedQuery } from "../../state/useCachedQuery";
import { Card } from "../common/Card";
import { EmptyState, ErrorPanel, Spinner } from "../common/Feedback";

const METRICS: { key: keyof Pick<ModelEvaluation, "accuracy" | "macro_f1" | "macro_precision" | "macro_recall" | "fatal_class_recall">; label: string }[] = [
  { key: "accuracy", label: "Accuracy" },
  { key: "macro_f1", label: "Macro F1" },
  { key: "macro_precision", label: "Macro precision" },
  { key: "macro_recall", label: "Macro recall" },
  { key: "fatal_class_recall", label: "Fatal-class recall" },
];
const COLORS = ["#0f766e", "#7c3aed"];

/**
 * Model performance, straight from GET /models/metrics (the backend's stored
 * training-time evaluation). Nothing is hard-coded in the frontend, and the
 * two models are shown side by side with their trade-offs -- neither is
 * called "best".
 */
export function ModelMetrics() {
  const query = useCachedQuery("models:metrics", () => getModelMetrics());

  let body;
  if (query.loading && !query.data) {
    body = <Spinner label="Loading model metrics…" />;
  } else if (query.error) {
    body = <ErrorPanel error={query.error} onRetry={query.reload} />;
  } else if (!query.data) {
    body = <EmptyState title="Model metrics are not available." />;
  } else {
    const available = query.data.models.filter((m): m is ModelMetricsEntry & { evaluation: ModelEvaluation } => m.evaluation !== null);
    if (available.length === 0) {
      body = (
        <EmptyState title="Model metrics are not exposed for this deployment.">
          The backend could not read its stored evaluation files, so no performance figures are shown.
        </EmptyState>
      );
    } else {
      const rows = METRICS.map(({ key, label }) => ({
        metric: label,
        ...Object.fromEntries(available.map((m) => [m.display_name, m.evaluation[key]])),
      }));
      body = (
        <div className="space-y-4">
          <figure>
            <figcaption className="text-sm font-semibold text-slate-900">
              Held-out test performance <span className="font-normal text-slate-600">(score from 0 to 1, higher is better)</span>
            </figcaption>
            <div role="img" aria-label={`Model metrics: ${rows.map((r) => r.metric).join(", ")} for ${available.map((m) => m.display_name).join(" and ")}. See the table below for values.`} className="mt-2 h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="metric" tick={{ fontSize: 12, fill: "#334155" }} interval={0} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 12, fill: "#334155" }} />
                  <Tooltip formatter={(value) => Number(value).toFixed(3)} />
                  <Legend />
                  {available.map((m, i) => (
                    <Bar key={m.source_id} dataKey={m.display_name} fill={COLORS[i % COLORS.length]} isAnimationActive={false} radius={[3, 3, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </figure>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left text-sm">
              <caption className="sr-only">Model evaluation metrics</caption>
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-600">
                  <th scope="col" className="py-2 pr-3 font-semibold">Metric</th>
                  {available.map((m) => <th key={m.source_id} scope="col" className="py-2 pr-3 font-semibold">{m.display_name}</th>)}
                </tr>
              </thead>
              <tbody>
                {METRICS.map(({ key, label }) => (
                  <tr key={key} className="border-b border-slate-100">
                    <th scope="row" className="py-2 pr-3 font-medium text-slate-800">{label}</th>
                    {available.map((m) => (
                      <td key={m.source_id} className="py-2 pr-3 tabular-nums text-slate-900">
                        {m.evaluation[key].toFixed(3)} <span className="text-xs text-slate-600">({formatPercent(m.evaluation[key])})</span>
                      </td>
                    ))}
                  </tr>
                ))}
                <tr>
                  <th scope="row" className="py-2 pr-3 font-medium text-slate-800">Test rows</th>
                  {available.map((m) => <td key={m.source_id} className="py-2 pr-3 tabular-nums text-slate-900">{m.evaluation.test_rows.toLocaleString()}</td>)}
                </tr>
              </tbody>
            </table>
          </div>

          <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-800">
            <p className="font-semibold text-slate-900">Reading the trade-offs</p>
            <p className="mt-1">
              No single metric decides which model is appropriate. Macro metrics weight all five severity classes equally,
              while fatal-class recall shows how often the rarest, most severe class is caught. The two models also use
              different inputs: the Report-Compatible Model exists because most real reports cannot supply what the
              Historical Model needs.
            </p>
            <p className="mt-2 text-xs text-slate-700">{query.data.evaluation_note}</p>
          </div>
        </div>
      );
    }
  }

  return (
    <Card
      id="model-metrics"
      title="Model performance"
      origin="model"
      description="Stored evaluation metrics from training, served by the backend. Not live performance."
    >
      {body}
    </Card>
  );
}
