/**
 * LIVE INTEGRATION TESTS: no mocks, no fixtures. These run the frontend's
 * real API client and UI against a real, running ResQAI FastAPI backend.
 *
 *   1. start the backend from the project root:
 *        .venv\Scripts\python.exe -m uvicorn src.api.main:app
 *   2. npm test          (VITE_API_BASE_URL defaults to http://127.0.0.1:8000)
 *
 * If the backend is not reachable these tests are SKIPPED (so `npm test`
 * still works offline). Set RESQAI_LIVE_TESTS=1 to make an unreachable
 * backend a hard failure instead -- use that in any environment where the
 * live check must not be silently skipped.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { analyzeReport, getApiBaseUrl, getHealth, getModelMetrics, getModels, getReadiness, getResources } from "../api";
import { App } from "../App";
import { AnalysisResult } from "../components/incident/AnalysisResult";
import { AnalysisProvider } from "../state/AnalysisContext";
import { SystemStatusProvider } from "../state/SystemStatusContext";

const REPORT =
  "Two vehicles collided at an intersection during heavy rain. Four people appear injured. " +
  "One person may be unconscious. Traffic is completely blocked.";

const reachable = await fetch(`${getApiBaseUrl()}/api/v1/ready`).then((r) => r.ok).catch(() => false);
if (!reachable && process.env.RESQAI_LIVE_TESTS === "1") {
  throw new Error(`RESQAI_LIVE_TESTS=1 but no ResQAI backend is reachable at ${getApiBaseUrl()}.`);
}

describe.skipIf(!reachable)(`live backend at ${getApiBaseUrl()}`, () => {
  it("serves health and readiness in the shape the dashboard expects", async () => {
    const health = await getHealth();
    const ready = await getReadiness();
    expect(["healthy", "degraded", "unavailable"]).toContain(health.status);
    expect(Object.keys(health.components)).toEqual(
      expect.arrayContaining(["api", "report_parser", "risk_engine", "decision_engine", "resource_catalog"]),
    );
    expect(ready.status).toBe("READY");
  });

  it("returns exactly the analyze contract the TypeScript types describe", async () => {
    const result = await analyzeReport({ raw_text: REPORT, latitude: 39.1, longitude: -94.58, source: "dashboard" });
    expect(Object.keys(result).sort()).toEqual([
      "decision", "disclaimer", "evidence", "explanation", "extracted_information", "human_oversight_required",
      "incident", "ml_prediction", "model_rule_disagreement", "prediction_readiness", "processing_time_ms",
      "report", "request_id", "resources", "risk_indicators", "warnings",
    ]);
    expect(Object.keys(result.ml_prediction).sort()).toEqual([
      "available", "features_used", "model_name", "model_version", "predicted_class", "predicted_label",
      "prediction_note", "prediction_source", "probabilities", "warnings",
    ]);
    expect(result.human_oversight_required).toBe(true);
    expect(result.resources.demo_only).toBe(true);
  });

  it("serves resources (with real filters), models and metrics", async () => {
    const all = await getResources();
    const ambulances = await getResources({ resource_type: "ambulance" });
    expect(all.demo_only).toBe(true);
    expect(ambulances.count).toBeGreaterThan(0);
    expect(ambulances.count).toBeLessThan(all.count);
    expect((await getModels()).models).toHaveLength(2);
    const metrics = await getModelMetrics();
    expect(metrics.models.every((m) => m.available && m.evaluation !== null)).toBe(true);
  });

  it("renders a REAL analysis: incident, risks, ML prediction, decision, resources", async () => {
    const result = await analyzeReport({ raw_text: REPORT, latitude: 39.1, longitude: -94.58, source: "dashboard" });
    render(<MemoryRouter><AnalysisResult result={result} /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "Incident analysis" })).toBeInTheDocument();
    expect(screen.getAllByText("Vehicle collision").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Risk indicators" })).toBeInTheDocument();
    for (const risk of result.risk_indicators) {
      expect(screen.getAllByText(risk.explanation).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByLabelText(`Priority ${result.decision.priority}`).length).toBeGreaterThan(0);

    const ml = result.ml_prediction;
    if (ml.available) {
      expect(screen.getAllByText(ml.predicted_label!).length).toBeGreaterThan(0);
      expect(screen.getByRole("list", { name: "Model class probabilities" })).toBeInTheDocument();
    } else {
      expect(screen.getByText("Model prediction unavailable")).toBeInTheDocument();
    }

    const resources = screen.getByRole("region", { name: "Compatible demo resources" });
    const offered = result.resources.searches.flatMap((s) => s.recommendations);
    expect(within(resources).getAllByText("Simulated")).toHaveLength(offered.length);
    expect(screen.getByText("Human oversight required")).toBeInTheDocument();
  });

  it("drives the whole app: type a report, submit, and see the backend's analysis", async () => {
    render(
      <MemoryRouter initialEntries={["/analyze"]}>
        <SystemStatusProvider>
          <AnalysisProvider>
            <App />
          </AnalysisProvider>
        </SystemStatusProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Service ready")).toBeInTheDocument(); // real /ready via the header pill
    await userEvent.type(screen.getByLabelText("Emergency report"), REPORT);
    await userEvent.click(screen.getByRole("button", { name: "Analyze Incident" }));

    expect(await screen.findByRole("heading", { name: "Incident analysis" }, { timeout: 15_000 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Priority and recommended response" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Machine-learning severity prediction" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Compatible demo resources" })).toBeInTheDocument();
    expect(screen.getByText(/Location not provided — proximity ranking and the location plot are unavailable/)).toBeInTheDocument();
  });

  it("shows the backend's real validation error for a bad request", async () => {
    const error = await analyzeReport({ raw_text: "   " }).catch((e: unknown) => e);
    expect(error).toMatchObject({ kind: "http", status: 422, code: "VALIDATION_ERROR" });
  });
});
