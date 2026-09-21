import type { ReactNode } from "react";
import { Cpu, FileText, FlaskConical, ListChecks, Scale, type LucideIcon } from "lucide-react";

/**
 * Where a piece of information comes from. ResQAI's core promise is that the
 * reader can always tell facts from statistics from rules, so every major
 * section carries one of these labels (icon + text, never colour alone).
 */
export type Origin = "report" | "model" | "rules" | "demo" | "system";

const ORIGINS: Record<Origin, { label: string; Icon: LucideIcon; className: string }> = {
  report: { label: "From the report", Icon: FileText, className: "bg-sky-50 text-sky-800 ring-sky-200" },
  model: { label: "Statistical model", Icon: Cpu, className: "bg-violet-50 text-violet-800 ring-violet-200" },
  rules: { label: "Project decision rules", Icon: Scale, className: "bg-amber-50 text-amber-900 ring-amber-200" },
  demo: { label: "Simulated demo data", Icon: FlaskConical, className: "bg-slate-100 text-slate-700 ring-slate-300" },
  system: { label: "System", Icon: ListChecks, className: "bg-slate-100 text-slate-700 ring-slate-300" },
};

export function OriginTag({ origin }: { origin: Origin }) {
  const { label, Icon, className } = ORIGINS[origin];
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${className}`}>
      <Icon aria-hidden className="size-3" />
      {label}
    </span>
  );
}

interface CardProps {
  id?: string;
  title: string;
  origin?: Origin;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Card({ id, title, origin, description, actions, children, className = "" }: CardProps) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={`section-in rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 border-b border-slate-100 px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <h2 id={headingId} className="text-base font-semibold text-slate-900">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-slate-600">{description}</p>}
        </div>
        <div className="flex items-center gap-2">
          {origin && <OriginTag origin={origin} />}
          {actions}
        </div>
      </header>
      <div className="px-4 py-4 sm:px-5">{children}</div>
    </section>
  );
}
