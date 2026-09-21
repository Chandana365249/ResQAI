import { Cpu } from "lucide-react";
import type { AnalyzeResponse, Readiness } from "../../api";
import { humanize, sourceLabel, uniqueStrings } from "../../lib/format";
import { Card } from "../common/Card";
import { ProbabilityChart } from "./ProbabilityChart";

function ReadinessRow({ title, readiness }: { title: string; readiness: Readiness }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 text-sm">
      <p className="font-semibold text-slate-900">
        {title}: <span className="font-medium text-slate-700">{humanize(readiness.status)}</span>
      </p>
      <p className="mt-1 text-xs text-slate-700">
        {readiness.mapped_features.length} feature(s) supplied by the report ·{" "}
        {readiness.missing_features.length} missing · {readiness.unsupported_features.length} not obtainable from report text
      </p>
      {readiness.mapped_features.length > 0 && (
        <p className="mt-1 text-xs text-slate-600">Supplied: {readiness.mapped_features.map(humanize).join(", ")}</p>
      )}
    </div>
  );
}

/**
 * The statistical model's output, with its source and routing made visible.
 * All text about routing/readiness is the backend's own (prediction_note,
 * warnings); this component never reinterprets or rewrites it.
 */
export function MlPredictionCard({ result }: { result: AnalyzeResponse }) {
  const { ml_prediction: ml, prediction_readiness: readiness } = result;
  // The backend can repeat prediction_note verbatim as a warning; show it once.
  const warnings = uniqueStrings(ml.warnings).filter((w) => w !== ml.prediction_note);

  return (
    <Card
      id="ml-prediction"
      title="Machine-learning severity prediction"
      origin="model"
      description="A statistical estimate learned from historical U.S. crash records. It is not a diagnosis and not the same thing as the operational risk or priority above."
    >
      {ml.available && ml.predicted_label ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Predicted severity</p>
              <p className="mt-0.5 text-2xl font-bold text-slate-900">{ml.predicted_label}</p>
            </div>
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-slate-600">Prediction source</dt>
                <dd>
                  <span className="inline-flex items-center gap-1.5 rounded bg-violet-700 px-2 py-0.5 text-xs font-semibold text-white">
                    <Cpu aria-hidden className="size-3.5" />
                    {sourceLabel(ml.prediction_source)}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-slate-600">Model</dt>
                <dd className="font-medium text-slate-900">{ml.model_name || "Not reported"}</dd>
              </div>
              <div>
                <dt className="text-slate-600">Features used ({ml.features_used.length})</dt>
                <dd>
                  {ml.features_used.length === 0 ? (
                    <span className="text-slate-600">None reported</span>
                  ) : (
                    <ul className="mt-1 flex flex-wrap gap-1.5">
                      {ml.features_used.map((feature) => (
                        <li key={feature} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">{humanize(feature)}</li>
                      ))}
                    </ul>
                  )}
                </dd>
              </div>
            </dl>
          </div>
          <ProbabilityChart probabilities={ml.probabilities} predictedLabel={ml.predicted_label} />
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4">
          <p className="font-semibold text-slate-900">Model prediction unavailable</p>
          <p className="mt-1 text-sm text-slate-700">
            ResQAI did not guess: neither trained model had enough information that this report actually provides.
          </p>
        </div>
      )}

      {ml.prediction_note && (
        <div className="mt-4 rounded-md border border-violet-200 bg-violet-50 p-3 text-sm text-violet-950">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-800">Model routing</p>
          <p className="mt-1">{ml.prediction_note}</p>
        </div>
      )}

      {warnings.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-800">
          {warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}

      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-teal-800">Model input readiness</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <ReadinessRow title="Historical Model" readiness={readiness.historical_model} />
          {readiness.report_compatible_model ? (
            <ReadinessRow title="Report-Compatible Model" readiness={readiness.report_compatible_model} />
          ) : (
            <div className="rounded-md border border-slate-200 p-3 text-sm text-slate-700">
              Report-Compatible Model: not needed for this report.
            </div>
          )}
        </div>
      </details>
    </Card>
  );
}
