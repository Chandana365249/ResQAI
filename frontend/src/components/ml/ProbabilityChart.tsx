import { formatPercent } from "../../lib/format";

interface ProbabilityChartProps {
  probabilities: Record<string, number> | null;
  predictedLabel: string | null;
}

/**
 * Horizontal bars for the model's ACTUAL class probabilities, in the order
 * the API returned them (mild-to-severe class order). Plain HTML so every
 * value is also readable text; the bar is decoration on top of the number.
 */
export function ProbabilityChart({ probabilities, predictedLabel }: ProbabilityChartProps) {
  if (!probabilities || Object.keys(probabilities).length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
        Model probabilities are unavailable for this prediction.
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Model class probabilities</p>
      <ul className="mt-2 space-y-2" aria-label="Model class probabilities">
        {Object.entries(probabilities).map(([label, probability]) => {
          const isPredicted = label === predictedLabel;
          return (
            <li key={label}>
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className={isPredicted ? "font-semibold text-slate-900" : "text-slate-800"}>
                  {label}
                  {isPredicted && <span className="ml-1.5 text-xs font-medium text-violet-800">(predicted)</span>}
                </span>
                <span className="tabular-nums font-medium text-slate-900">{formatPercent(probability)}</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded bg-slate-200" aria-hidden>
                <div
                  className={`h-full rounded ${isPredicted ? "bg-violet-700" : "bg-slate-500"}`}
                  style={{ width: `${Math.max(0, Math.min(1, probability)) * 100}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-slate-600">
        Probabilities are the model's own output for the details provided. They are not certainty about this incident.
      </p>
    </div>
  );
}
