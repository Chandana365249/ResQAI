import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Spinner } from "./components/common/Feedback";
import { AppShell } from "./components/layout/AppShell";
import { AnalyzePage } from "./pages/AnalyzePage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { SystemPage } from "./pages/SystemPage";

// The analytics page pulls in the charting library, so it loads on demand.
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));

function NotFound() {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <h1 className="text-lg font-semibold text-slate-900">Page not found</h1>
      <p className="mt-1 text-sm text-slate-700">Use the navigation above to return to the dashboard.</p>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/analyze" replace />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route
          path="/analytics"
          element={
            <Suspense fallback={<Spinner label="Loading analytics…" />}>
              <AnalyticsPage />
            </Suspense>
          }
        />
        <Route path="/system" element={<SystemPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
