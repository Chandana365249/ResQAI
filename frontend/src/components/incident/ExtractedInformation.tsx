import type { ExtractedInformation as ExtractedInformationData } from "../../api";
import { formatValue, groupLabel, humanize } from "../../lib/format";
import { CertaintyBadge } from "../common/Badges";
import { Card } from "../common/Card";
import { EmptyState } from "../common/Feedback";

/** Only the fields the report actually mentioned (the API omits everything else). */
export function ExtractedInformation({ data }: { data: ExtractedInformationData }) {
  const groups = Object.entries(data).filter(([, fields]) => Object.keys(fields).length > 0);

  return (
    <Card
      id="extracted-information"
      title="What ResQAI extracted"
      origin="report"
      description="Structured details found in the report text, each with how certain the wording was."
    >
      {groups.length === 0 ? (
        <EmptyState title="No structured details were extracted from this report." />
      ) : (
        <div className="space-y-5">
          {groups.map(([group, fields]) => (
            <div key={group}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{groupLabel(group)}</h3>
              <ul className="mt-2 divide-y divide-slate-100 rounded-md border border-slate-200">
                {Object.entries(fields).map(([name, field]) => (
                  <li key={name} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2">
                    <span className="text-sm text-slate-800">{humanize(name)}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900">{formatValue(field.value)}</span>
                      <CertaintyBadge certainty={field.certainty} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
