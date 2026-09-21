import { useId, useState } from "react";
import { FlaskConical } from "lucide-react";
import { getResources } from "../api";
import { DemoBadge } from "../components/common/Badges";
import { Card } from "../components/common/Card";
import { EmptyState, ErrorPanel, Spinner } from "../components/common/Feedback";
import { humanize } from "../lib/format";
import { useCachedQuery } from "../state/useCachedQuery";

/**
 * The simulated resource catalogue. Filter choices are derived from the
 * catalogue itself (not hard-coded) and applied through the API's own
 * resource_type / availability_status query parameters.
 */
export function ResourcesPage() {
  const uid = useId();
  const [resourceType, setResourceType] = useState("");
  const [availability, setAvailability] = useState("");

  const all = useCachedQuery("resources:all", () => getResources());
  const filtered = useCachedQuery(`resources:${resourceType}:${availability}`, () =>
    getResources({ resource_type: resourceType || undefined, availability_status: availability || undefined }),
  );

  const types = Array.from(new Set((all.data?.resources ?? []).map((r) => r.resource_type))).sort();
  const statuses = Array.from(new Set((all.data?.resources ?? []).map((r) => r.availability_status))).sort();
  const selectClass = "mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Demo resource catalog</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-700">
          The synthetic catalog ResQAI matches against. None of these are real emergency units.
        </p>
      </div>

      <div className="flex items-start gap-2 rounded-md border border-dashed border-slate-400 bg-slate-100 p-3 text-sm text-slate-800">
        <FlaskConical aria-hidden className="mt-0.5 size-4 shrink-0" />
        <p>
          {filtered.data?.notice ?? all.data?.notice ?? "All resources shown are simulated demo entries, not real units, and carry no live availability."}
        </p>
      </div>

      <Card id="resource-filters" title="Filter">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={`${uid}-type`} className="block text-sm font-medium text-slate-800">Resource type</label>
            <select id={`${uid}-type`} value={resourceType} onChange={(e) => setResourceType(e.target.value)} className={selectClass}>
              <option value="">All types</option>
              {types.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor={`${uid}-status`} className="block text-sm font-medium text-slate-800">Availability (simulated)</label>
            <select id={`${uid}-status`} value={availability} onChange={(e) => setAvailability(e.target.value)} className={selectClass}>
              <option value="">Any</option>
              {statuses.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </select>
          </div>
        </div>
      </Card>

      {filtered.loading && <Spinner label="Loading demo resources…" />}
      {filtered.error && <ErrorPanel error={filtered.error} onRetry={filtered.reload} />}

      {filtered.data && (
        <section aria-labelledby="resource-list-heading">
          <h2 id="resource-list-heading" className="text-base font-semibold text-slate-900">
            {filtered.data.count} demo resource{filtered.data.count === 1 ? "" : "s"}
          </h2>
          {filtered.data.resources.length === 0 ? (
            <div className="mt-3"><EmptyState title="No demo resources match these filters." /></div>
          ) : (
            <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.data.resources.map((r) => (
                <li key={r.resource_id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-900">{r.resource_name}</p>
                      <p className="text-xs text-slate-600">
                        {humanize(r.resource_type)} · <span className="font-mono">{r.resource_id}</span>
                      </p>
                    </div>
                    <DemoBadge compact />
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-xs text-slate-600">Availability (simulated)</dt>
                      <dd className="font-medium text-slate-900">{humanize(r.availability_status)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-600">Capacity</dt>
                      <dd className="font-medium text-slate-900">{r.capacity ?? "Not recorded"}</dd>
                    </div>
                  </dl>
                  {r.capabilities.length > 0 && (
                    <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Capabilities">
                      {r.capabilities.map((c) => (
                        <li key={c} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">{humanize(c)}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
