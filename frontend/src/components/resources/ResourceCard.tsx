import type { ResourceRecommendation } from "../../api";
import { formatDistanceKm, humanize } from "../../lib/format";
import { DemoBadge } from "../common/Badges";

/** One matched demo resource. Always labelled simulated; never presented as a real unit. */
export function ResourceCard({ resource, rank }: { resource: ResourceRecommendation; rank: number }) {
  const distance = formatDistanceKm(resource.distance_km);
  return (
    <li className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900">
            <span className="mr-1.5 text-slate-500 tabular-nums">#{rank}</span>
            {resource.resource_name}
          </p>
          <p className="text-xs text-slate-600">
            {humanize(resource.resource_type)} · <span className="font-mono">{resource.resource_id}</span>
          </p>
        </div>
        <DemoBadge compact />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-xs text-slate-600">Distance</dt>
          <dd className="font-medium text-slate-900">{distance ?? "Not ranked (no incident location)"}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-600">Availability (simulated)</dt>
          <dd className="font-medium text-slate-900">{humanize(resource.availability)}</dd>
        </div>
      </dl>
      {resource.capabilities.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Capabilities">
          {resource.capabilities.map((c) => (
            <li key={c} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">{humanize(c)}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-700">{resource.reason}</p>
    </li>
  );
}
