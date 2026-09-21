import { FlaskConical } from "lucide-react";
import type { ResourcesSection } from "../../api";
import { humanize } from "../../lib/format";
import { Card } from "../common/Card";
import { EmptyState } from "../common/Feedback";
import { ResourceCard } from "./ResourceCard";
import { ResourceMap } from "./ResourceMap";

/** Matched demo resources per recommended response category. The simulated status is always visible. */
export function ResourceResults({ section }: { section: ResourcesSection }) {
  const { searches } = section;

  return (
    <Card id="resources" title="Compatible demo resources" origin="demo">
      <div className="mb-4 flex items-start gap-2 rounded-md border border-dashed border-slate-400 bg-slate-100 p-3 text-sm text-slate-800">
        <FlaskConical aria-hidden className="mt-0.5 size-4 shrink-0" />
        <p>{section.notice}</p>
      </div>

      {searches.length === 0 ? (
        <div className="space-y-3">
          <EmptyState title="No response categories were recommended, so no resources were searched." />
          <ResourceMap section={section} />
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div className="space-y-5">
            {searches.map((search) => (
              <div key={search.category}>
                <h3 className="text-sm font-semibold text-slate-900">{humanize(search.category)}</h3>
                {search.recommendations.length === 0 ? (
                  <div className="mt-2">
                    <EmptyState title="No compatible demo resources found.">{search.reason ?? undefined}</EmptyState>
                  </div>
                ) : (
                  <>
                    {search.reason && <p className="mt-1 text-xs text-slate-700">{search.reason}</p>}
                    <ul className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-1">
                      {search.recommendations.map((rec, index) => (
                        <ResourceCard key={rec.resource_id} resource={rec} rank={index + 1} />
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ))}
          </div>

          <div className="xl:sticky xl:top-4 xl:self-start">
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Location</h3>
            <ResourceMap section={section} />
          </div>
        </div>
      )}
    </Card>
  );
}
