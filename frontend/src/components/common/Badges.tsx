import { AlertCircle, AlertOctagon, AlertTriangle, CheckCircle2, CircleDashed, FlaskConical, HelpCircle, Info, MinusCircle } from "lucide-react";
import type { Certainty, Level, Priority } from "../../api";
import { CERTAINTY_LABELS, LEVEL_LABELS } from "../../lib/format";

/**
 * Certainty is shown with an icon, a text label AND a distinct border style
 * (solid / dashed / dotted), so "possible" never looks like "confirmed" and
 * nothing depends on colour alone.
 */
const CERTAINTY_STYLE: Record<Certainty, { className: string; Icon: typeof CheckCircle2 }> = {
  confirmed: { className: "border border-solid border-emerald-600 bg-emerald-50 text-emerald-900", Icon: CheckCircle2 },
  possible: { className: "border border-dashed border-amber-600 bg-amber-50 text-amber-900", Icon: HelpCircle },
  uncertain: { className: "border border-dotted border-orange-700 bg-orange-50 text-orange-900", Icon: CircleDashed },
  not_mentioned: { className: "border border-solid border-slate-300 bg-slate-50 text-slate-600", Icon: MinusCircle },
};

export function CertaintyBadge({ certainty }: { certainty: Certainty }) {
  const { className, Icon } = CERTAINTY_STYLE[certainty];
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold ${className}`}>
      <Icon aria-hidden className="size-3.5" />
      {CERTAINTY_LABELS[certainty]}
    </span>
  );
}

const LEVEL_STYLE: Record<Level, { className: string; Icon: typeof Info }> = {
  critical: { className: "bg-red-700 text-white", Icon: AlertOctagon },
  high: { className: "bg-orange-100 text-orange-900 ring-1 ring-inset ring-orange-500", Icon: AlertTriangle },
  moderate: { className: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-400", Icon: AlertCircle },
  low: { className: "bg-slate-100 text-slate-800 ring-1 ring-inset ring-slate-300", Icon: Info },
};

export function LevelBadge({ level }: { level: Level }) {
  const { className, Icon } = LEVEL_STYLE[level];
  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold ${className}`}>
      <Icon aria-hidden className="size-3.5" />
      {LEVEL_LABELS[level]}
    </span>
  );
}

const PRIORITY_STYLE: Record<Priority, string> = {
  P0: "bg-red-700 text-white",
  P1: "bg-orange-600 text-white",
  P2: "bg-amber-500 text-slate-900",
  P3: "bg-slate-600 text-white",
};

export function PriorityBadge({ priority, large = false }: { priority: Priority; large?: boolean }) {
  return (
    <span
      aria-label={`Priority ${priority}`}
      className={`inline-flex items-center justify-center rounded font-bold tabular-nums ${PRIORITY_STYLE[priority]} ${
        large ? "px-3 py-1 text-2xl" : "px-2 py-0.5 text-xs"
      }`}
    >
      {priority}
    </span>
  );
}

/** Every resource, everywhere, is labelled as simulated. */
export function DemoBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-dashed border-slate-500 bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-slate-700">
      <FlaskConical aria-hidden className="size-3" />
      {compact ? "Simulated" : "Simulated demo resource"}
    </span>
  );
}
