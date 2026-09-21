import { getModels } from "../../api";
import { humanize } from "../../lib/format";
import { useCachedQuery } from "../../state/useCachedQuery";
import { Card } from "../common/Card";
import { ErrorPanel, Spinner } from "../common/Feedback";

/** Model metadata exactly as the backend describes it (GET /models). */
export function ModelInfoCards() {
  const query = useCachedQuery("models:info", () => getModels());

  return (
    <Card id="model-info" title="Severity models" origin="model" description="Both models predict the same target: crash injury severity (MAX_SEV).">
      {query.loading && !query.data && <Spinner label="Loading model information…" />}
      {query.error && <ErrorPanel error={query.error} onRetry={query.reload} />}
      {query.data && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            {query.data.models.map((m) => (
              <article key={m.source_id} className="rounded-md border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="font-semibold text-slate-900">{m.display_name}</h3>
                  <span className={`rounded px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${m.available ? "bg-emerald-50 text-emerald-900 ring-emerald-300" : "bg-red-50 text-red-900 ring-red-300"}`}>
                    {m.available ? "Available" : "Unavailable"}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-800">{m.description}</p>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <div><dt className="text-xs text-slate-600">Role</dt><dd className="font-medium text-slate-900">{humanize(m.role)}</dd></div>
                  <div><dt className="text-xs text-slate-600">Estimator</dt><dd className="font-medium text-slate-900">{m.model_type ?? "Not loaded"}</dd></div>
                  <div><dt className="text-xs text-slate-600">Input features</dt><dd className="font-medium text-slate-900">{m.feature_count || "—"}</dd></div>
                  <div><dt className="text-xs text-slate-600">Training data</dt><dd className="font-medium text-slate-900">{m.training_dataset}</dd></div>
                </dl>
                <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-600">Limitations</h4>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-800">
                  {m.limitations.map((l) => <li key={l}>{l}</li>)}
                </ul>
              </article>
            ))}
          </div>
          <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-800">
            <p className="font-semibold text-slate-900">How the analysis chooses a model</p>
            <p className="mt-1">{query.data.routing}</p>
          </div>
        </div>
      )}
    </Card>
  );
}
