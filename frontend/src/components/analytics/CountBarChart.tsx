import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Count } from "../../lib/analytics";
import { EmptyState } from "../common/Feedback";

interface CountBarChartProps {
  title: string;
  /** What is being counted, e.g. "analyses" -- shown as the unit. */
  unit: string;
  data: Count[];
  labelFor?: (key: string) => string;
  emptyMessage: string;
}

const ROW_HEIGHT = 34;

/**
 * Horizontal bar chart of REAL counts. Every chart has a title, a unit, an
 * empty state and a text table alternative, so it is readable without
 * sight or a pointer.
 */
export function CountBarChart({ title, unit, data, labelFor = (k) => k, emptyMessage }: CountBarChartProps) {
  const rows = data.map((d) => ({ name: labelFor(d.key), count: d.count }));
  return (
    <figure className="rounded-md border border-slate-200 p-3">
      <figcaption className="text-sm font-semibold text-slate-900">
        {title} <span className="font-normal text-slate-600">(number of {unit})</span>
      </figcaption>
      {rows.length === 0 ? (
        <div className="mt-2"><EmptyState title={emptyMessage} /></div>
      ) : (
        <>
          <div role="img" aria-label={`${title}: ${rows.map((r) => `${r.name} ${r.count}`).join(", ")}`} style={{ height: rows.length * ROW_HEIGHT + 36 }} className="mt-2 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                <CartesianGrid horizontal={false} stroke="#e2e8f0" />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "#334155" }} />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12, fill: "#334155" }} />
                <Tooltip cursor={{ fill: "#f1f5f9" }} formatter={(value) => [String(value), unit]} />
                <Bar dataKey="count" fill="#0f766e" radius={[0, 3, 3, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-1">
            <summary className="cursor-pointer text-xs font-medium text-teal-800">View as table</summary>
            <table className="mt-1 w-full text-left text-xs">
              <thead><tr><th scope="col" className="py-1 pr-2 font-semibold">Category</th><th scope="col" className="py-1 font-semibold">Count</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name} className="border-t border-slate-100"><td className="py-1 pr-2">{r.name}</td><td className="py-1 tabular-nums">{r.count}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </figure>
  );
}
