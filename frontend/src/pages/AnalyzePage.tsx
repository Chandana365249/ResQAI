import { Card } from "../components/common/Card";
import { ErrorPanel, Spinner } from "../components/common/Feedback";
import { AnalysisResult } from "../components/incident/AnalysisResult";
import { IncidentForm } from "../components/report/IncidentForm";
import { useAnalysis } from "../state/AnalysisContext";

export function AnalyzePage() {
  const { state, draft, setDraft, submit, retry } = useAnalysis();
  const loading = state.status === "loading";
  const serverFieldErrors = state.status === "error" ? state.error.fieldErrors : undefined;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">
          AI-assisted emergency response · decision support
        </p>
        <h1 className="mt-0.5 text-2xl font-bold tracking-tight text-slate-900">Analyze an emergency report</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-700">
          ResQAI analyzes the report and provides decision-support information for human review. It extracts what the
          report says, flags operational risks, estimates severity with a statistical model when the report supports it,
          and matches simulated demo resources. It does not dispatch anyone or make decisions.
        </p>
      </div>

      <Card id="analyze-form" title="Describe the incident" origin="report">
        <IncidentForm
          values={draft}
          onChange={setDraft}
          onSubmit={(request) => void submit(request)}
          loading={loading}
          serverFieldErrors={serverFieldErrors}
        />
      </Card>

      {state.status === "loading" && (
        <Card id="analysis-loading" title="Analysis in progress">
          <Spinner label="Analyzing incident…" />
        </Card>
      )}

      {state.status === "error" && <ErrorPanel error={state.error} onRetry={() => void retry()} />}

      {state.status === "success" && <AnalysisResult result={state.result} />}

      {state.status === "idle" && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center">
          <p className="font-medium text-slate-800">No incident analyzed yet.</p>
          <p className="mt-1 text-sm text-slate-600">
            Submit a report above or pick an example scenario to see the structured analysis here.
          </p>
        </div>
      )}
    </div>
  );
}
