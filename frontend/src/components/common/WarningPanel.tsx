import { TriangleAlert } from "lucide-react";
import { uniqueStrings } from "../../lib/format";
import { Card } from "./Card";

interface WarningPanelProps {
  warnings: string[];
  /** Warnings already shown elsewhere (e.g. inside the ML card) are not repeated here. */
  alreadyShown?: string[];
}

/** The backend's own warnings and limitations, de-duplicated. Hidden entirely when there are none. */
export function WarningPanel({ warnings, alreadyShown = [] }: WarningPanelProps) {
  const shown = new Set(alreadyShown);
  const items = uniqueStrings(warnings).filter((w) => !shown.has(w));
  if (items.length === 0) return null;

  return (
    <Card
      id="warnings"
      title="Warnings and limitations"
      origin="system"
      description="Things that are missing, approximate or unavailable for this analysis."
    >
      <ul className="space-y-2">
        {items.map((warning) => (
          <li key={warning} className="flex items-start gap-2 text-sm text-slate-800">
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-700" />
            <span>{warning}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
