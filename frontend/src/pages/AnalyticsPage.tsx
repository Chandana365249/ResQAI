import { ModelMetrics } from "../components/analytics/ModelMetrics";
import { SessionAnalytics } from "../components/analytics/SessionAnalytics";
import { useAnalysis } from "../state/AnalysisContext";

export default function AnalyticsPage() {
  const { history, clearHistory } = useAnalysis();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Analytics</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-700">
          Model performance comes from the backend's stored evaluation. Session analytics are computed only from the
          analyses you have run in this browser.
        </p>
      </div>
      <SessionAnalytics records={history} onClear={clearHistory} />
      <ModelMetrics />
    </div>
  );
}
