import { Scale } from "lucide-react";
import type { AnalyzeResponse } from "../../api";
import { LEVEL_LABELS, sourceLabel } from "../../lib/format";

/**
 * Shown whenever the backend flags that the statistical model and the
 * rule-based operational risk disagree. Calm and factual by design: it
 * presents BOTH sides and the backend's own explanation, and does not pick
 * a winner -- a human decides.
 */
export function DisagreementAlert({ result }: { result: AnalyzeResponse }) {
  if (!result.model_rule_disagreement) return null;
  const { ml_prediction: ml, decision } = result;

  return (
    <section
      role="alert"
      aria-labelledby="disagreement-heading"
      className="section-in rounded-lg border-2 border-amber-500 bg-amber-50 p-4 sm:p-5"
    >
      <div className="flex items-start gap-3">
        <Scale aria-hidden className="mt-0.5 size-5 shrink-0 text-amber-900" />
        <div className="min-w-0 flex-1">
          <h2 id="disagreement-heading" className="text-base font-semibold text-amber-950">
            Model and operational-risk assessment differ
          </h2>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-md bg-white/70 p-3 ring-1 ring-amber-200">
              <dt className="text-xs font-semibold uppercase tracking-wide text-amber-900">Model prediction</dt>
              <dd className="mt-0.5 font-semibold text-slate-900">{ml.predicted_label ?? "Unavailable"}</dd>
              <dd className="text-xs text-slate-700">{sourceLabel(ml.prediction_source)}</dd>
            </div>
            <div className="rounded-md bg-white/70 p-3 ring-1 ring-amber-200">
              <dt className="text-xs font-semibold uppercase tracking-wide text-amber-900">Operational risk (rules)</dt>
              <dd className="mt-0.5 font-semibold text-slate-900">{LEVEL_LABELS[decision.risk_level]}</dd>
              <dd className="text-xs text-slate-700">Priority {decision.priority}</dd>
            </div>
          </dl>
          <p className="mt-3 text-sm text-amber-950">{result.model_rule_disagreement}</p>
          <p className="mt-2 text-sm font-semibold text-amber-950">
            Human review required. ResQAI does not decide which assessment is correct.
          </p>
        </div>
      </div>
    </section>
  );
}
