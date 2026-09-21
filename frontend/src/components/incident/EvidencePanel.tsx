import { Quote } from "lucide-react";
import type { EvidenceItem } from "../../api";
import { formatValue, humanize } from "../../lib/format";
import { CertaintyBadge } from "../common/Badges";
import { Card } from "../common/Card";
import { EmptyState } from "../common/Feedback";

/**
 * Provenance: for each extracted field, the report wording that supports it.
 * Only what the API returned is shown -- a field without a text snippet
 * simply has no quote line.
 */
export function EvidencePanel({ evidence }: { evidence: EvidenceItem[] }) {
  return (
    <Card id="evidence" title="Why was this information extracted?" origin="report">
      {evidence.length === 0 ? (
        <EmptyState title="No supporting evidence was recorded for this report." />
      ) : (
        <details>
          <summary className="cursor-pointer text-sm font-medium text-teal-800">
            Show the supporting evidence ({evidence.length} {evidence.length === 1 ? "field" : "fields"})
          </summary>
          <ul className="mt-3 space-y-3">
            {evidence.map((item, index) => (
              <li key={`${item.field}-${index}`} className="rounded-md border border-slate-200 p-3">
                <dl className="grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1 text-sm">
                  <dt className="text-slate-600">Field</dt>
                  <dd className="font-medium text-slate-900">{humanize(item.field)}</dd>
                  <dt className="text-slate-600">Value</dt>
                  <dd className="font-medium text-slate-900">{formatValue(item.value)}</dd>
                  <dt className="text-slate-600">Certainty</dt>
                  <dd><CertaintyBadge certainty={item.certainty} /></dd>
                  {item.evidence && (
                    <>
                      <dt className="text-slate-600">Evidence</dt>
                      <dd>
                        <blockquote className="flex gap-1.5 text-slate-800">
                          <Quote aria-hidden className="mt-0.5 size-3.5 shrink-0 text-slate-500" />
                          <span className="italic">“{item.evidence}”</span>
                        </blockquote>
                      </dd>
                    </>
                  )}
                </dl>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
