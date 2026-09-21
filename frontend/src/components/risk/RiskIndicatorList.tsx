import type { RiskIndicator } from "../../api";
import { humanize } from "../../lib/format";
import { CertaintyBadge, LevelBadge } from "../common/Badges";
import { Card } from "../common/Card";
import { EmptyState } from "../common/Feedback";

/** Rule-based OPERATIONAL signals for a dispatcher's attention -- explicitly not medical triage. */
export function RiskIndicatorList({ indicators }: { indicators: RiskIndicator[] }) {
  return (
    <Card
      id="risk-indicators"
      title="Risk indicators"
      origin="rules"
      description="Operational signals detected by transparent rules. Not medical triage."
    >
      {indicators.length === 0 ? (
        <EmptyState title="No operational risk indicators were detected for this report." />
      ) : (
        <ul className="space-y-3">
          {indicators.map((indicator) => (
            <li key={indicator.name} className="rounded-md border border-slate-200 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold text-slate-900">{humanize(indicator.name)}</p>
                <span className="flex items-center gap-1.5">
                  <LevelBadge level={indicator.level} />
                  <CertaintyBadge certainty={indicator.certainty} />
                </span>
              </div>
              <p className="mt-1.5 text-sm text-slate-800">{indicator.explanation}</p>
              {indicator.evidence && (
                <p className="mt-1 text-xs text-slate-600">
                  Evidence: <span className="italic">“{indicator.evidence}”</span>
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
