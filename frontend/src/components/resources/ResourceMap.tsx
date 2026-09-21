import { getResources, type DemoResource, type ResourcesSection } from "../../api";
import { formatDistanceKm } from "../../lib/format";
import { projectRelativeTo, type GeoPoint } from "../../lib/geo";
import { useCachedQuery } from "../../state/useCachedQuery";

const SIZE = 320; // SVG viewBox is SIZE x SIZE
const PADDING = 28;
const RADIUS = SIZE / 2 - PADDING;

/**
 * A schematic position plot (NOT a street map): the incident at the centre
 * and the matched demo resources placed by their real catalogue
 * coordinates. No tiles, no external service, no API key. Distances in the
 * legend come from the API; the plot only draws positions.
 */
export function ResourceMap({ section }: { section: ResourcesSection }) {
  const { location, searches } = section;
  const catalog = useCachedQuery("resources:all", () => getResources());

  if (!location.available || location.latitude === null || location.longitude === null) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-700">
        Location not provided — proximity ranking and the location plot are unavailable.
      </div>
    );
  }

  const byId = new Map<string, DemoResource>((catalog.data?.resources ?? []).map((r) => [r.resource_id, r]));
  const seen = new Set<string>();
  const matched = searches
    .flatMap((s) => s.recommendations)
    .filter((rec) => (seen.has(rec.resource_id) ? false : (seen.add(rec.resource_id), true)));

  const geoPoints: GeoPoint[] = matched.flatMap((rec) => {
    const r = byId.get(rec.resource_id);
    return r && r.latitude !== null && r.longitude !== null
      ? [{ id: rec.resource_id, latitude: r.latitude, longitude: r.longitude }]
      : [];
  });

  if (matched.length === 0) {
    return (
      <p className="text-sm text-slate-700">No compatible demo resources were matched, so there is nothing to plot.</p>
    );
  }
  if (geoPoints.length === 0) {
    return (
      <p className="text-sm text-slate-700">
        {catalog.loading ? "Loading resource positions…" : "Resource positions are unavailable, so the plot is not shown."}
      </p>
    );
  }

  const { points, extentKm } = projectRelativeTo({ latitude: location.latitude, longitude: location.longitude }, geoPoints);
  const cx = SIZE / 2;
  const toX = (x: number) => cx + x * RADIUS;
  const toY = (y: number) => cx - y * RADIUS; // north is up

  return (
    <figure>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={`Schematic plot of the incident and ${geoPoints.length} matched simulated resources within about ${extentKm.toFixed(0)} km`}
        className="mx-auto h-auto w-full max-w-sm rounded-md border border-slate-200 bg-slate-50"
      >
        <circle cx={cx} cy={cx} r={RADIUS} fill="none" stroke="#cbd5e1" strokeDasharray="4 4" />
        <circle cx={cx} cy={cx} r={RADIUS / 2} fill="none" stroke="#e2e8f0" strokeDasharray="4 4" />
        <text x={cx} y={PADDING - 10} textAnchor="middle" fontSize="11" fill="#475569">N</text>

        {points.map((p, index) => {
          const rec = matched.find((m) => m.resource_id === p.id);
          const label = rec ? `${index + 1}` : "";
          return (
            <g key={p.id}>
              <title>{rec ? `${rec.resource_name} (simulated) — ${formatDistanceKm(rec.distance_km) ?? "distance not ranked"}` : p.id}</title>
              <rect x={toX(p.x) - 7} y={toY(p.y) - 7} width="14" height="14" rx="2" fill="#475569" stroke="#fff" strokeWidth="1.5" />
              <text x={toX(p.x)} y={toY(p.y) + 3.5} textAnchor="middle" fontSize="9" fontWeight="700" fill="#fff">{label}</text>
            </g>
          );
        })}

        <g>
          <title>Incident location</title>
          <circle cx={cx} cy={cx} r="9" fill="#b91c1c" stroke="#fff" strokeWidth="2" />
          <path d={`M${cx - 4} ${cx}h8M${cx} ${cx - 4}v8`} stroke="#fff" strokeWidth="2" strokeLinecap="round" />
        </g>
      </svg>
      <figcaption className="mt-2 space-y-1 text-xs text-slate-700">
        <p>
          <span className="font-semibold text-red-800">● Incident</span> at centre · <span className="font-semibold">■ numbered</span> simulated
          resources · outer ring ≈ {extentKm.toFixed(1)} km. Schematic only — not a street map or route.
        </p>
        <ol className="list-decimal pl-5">
          {points.map((p) => {
            const rec = matched.find((m) => m.resource_id === p.id);
            return rec ? (
              <li key={p.id}>
                {rec.resource_name} — {formatDistanceKm(rec.distance_km) ?? "not ranked"}
              </li>
            ) : null;
          })}
        </ol>
      </figcaption>
    </figure>
  );
}
