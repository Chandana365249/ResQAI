import { CheckCircle2, CircleSlash, Loader2, TriangleAlert, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { useSystemStatus } from "../../state/SystemStatusContext";

interface PillView {
  label: string;
  Icon: LucideIcon;
  className: string;
  spin?: boolean;
}

/** Compact header indicator. Text + icon carry the meaning; colour only reinforces it. */
export function SystemStatusPill() {
  const { state } = useSystemStatus();

  let view: PillView;
  if (state.status === "loading") {
    view = { label: "Checking service…", Icon: Loader2, className: "bg-slate-100 text-slate-700 ring-slate-300", spin: true };
  } else if (state.status === "waking") {
    view = { label: "Waking up service… (idle hosting can take a minute)", Icon: Loader2, className: "bg-amber-50 text-amber-900 ring-amber-300", spin: true };
  } else if (state.status === "unreachable") {
    view = { label: "Service unreachable", Icon: CircleSlash, className: "bg-red-50 text-red-900 ring-red-300" };
  } else if (state.readiness.status === "NOT_READY" || state.health.status === "unavailable") {
    view = { label: "Service not ready", Icon: CircleSlash, className: "bg-red-50 text-red-900 ring-red-300" };
  } else if (state.health.status === "degraded") {
    view = { label: "Degraded: a model is unavailable", Icon: TriangleAlert, className: "bg-amber-50 text-amber-900 ring-amber-300" };
  } else {
    view = { label: "Service ready", Icon: CheckCircle2, className: "bg-emerald-50 text-emerald-900 ring-emerald-300" };
  }

  return (
    <Link
      to="/system"
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${view.className}`}
    >
      <view.Icon aria-hidden className={`size-3.5 ${view.spin ? "animate-spin motion-reduce:animate-none" : ""}`} />
      {view.label}
    </Link>
  );
}
