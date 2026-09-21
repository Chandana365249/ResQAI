import type { Decision } from "../../api";
import { humanize } from "../../lib/format";
import { LevelBadge, PriorityBadge } from "../common/Badges";
import { Card } from "../common/Card";

/**
 * Rule-based priority and recommended response CATEGORIES. Kept apart from
 * the ML prediction on purpose, and labelled as project-defined rather than
 * a validated dispatch or triage standard.
 */
export function DecisionSummary({ decision }: { decision: Decision }) {
  return (
    <Card id="decision" title="Priority and recommended response" origin="rules">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Priority</p>
          <div className="mt-1"><PriorityBadge priority={decision.priority} large /></div>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Operational risk level</p>
          <div className="mt-1.5"><LevelBadge level={decision.risk_level} /></div>
        </div>
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-semibold text-slate-900">Why this priority</h3>
        {decision.reasons.length === 0 ? (
          <p className="mt-1 text-sm text-slate-700">The rules recorded no specific reasons.</p>
        ) : (
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-slate-800">
            {decision.reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}
          </ul>
        )}
      </div>

      <div className="mt-4">
        <h3 className="text-sm font-semibold text-slate-900">Recommended response categories</h3>
        {decision.recommended_response_categories.length === 0 ? (
          <p className="mt-1 text-sm text-slate-700">The rules did not recommend any response category for this report.</p>
        ) : (
          <ul className="mt-2 flex flex-wrap gap-2">
            {decision.recommended_response_categories.map((category) => (
              <li key={category} className="rounded-md border border-slate-300 bg-slate-50 px-2.5 py-1 text-sm font-medium text-slate-900">
                {humanize(category)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="mt-4 rounded-md bg-slate-50 p-2.5 text-xs text-slate-700">
        Priority and categories come from the project's own prototype rules. They are not a validated emergency
        dispatch standard or medical triage, and are suggestions for a human, not commands.
      </p>
    </Card>
  );
}
