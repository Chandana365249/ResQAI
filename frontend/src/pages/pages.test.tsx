import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type AnalyzeRequest, type AnalyzeResponse } from "../api";
import { App } from "../App";
import { HISTORY_STORAGE_KEY, saveHistory, toSessionRecord } from "../lib/sessionHistory";
import {
  disagreement, healthFixture, metricsFixture, modelsFixture, noPrediction, readyFixture, resourcesFixture, serious,
  validationErrorFixture,
} from "../test/fixtures";
import { jsonResponse, renderWithProviders, stubFetch } from "../test/utils";

const REPORT = "Two cars collided at an intersection during heavy rain. One person may be unconscious.";

function apiRoutes() {
  return {
    "/resources": () => jsonResponse(resourcesFixture),
    "/models": () => jsonResponse(modelsFixture),
    "/models/metrics": () => jsonResponse(metricsFixture),
  };
}

async function typeReport(text = REPORT) {
  await userEvent.type(screen.getByLabelText("Emergency report"), text);
}
const submitButton = () => screen.getByRole("button", { name: /Analyze Incident|Analyzing/ });

/** A promise the test resolves/rejects by hand, to observe the loading state. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("Analyze page", () => {
  it("starts with a meaningful empty state", () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze" });
    expect(screen.getByText("No incident analyzed yet.")).toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
  });

  it("prevents blank submission with friendly validation and never calls the API", async () => {
    stubFetch(apiRoutes());
    const analyze = vi.fn();
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await userEvent.click(submitButton());
    expect(await screen.findByText("Please enter an emergency report.")).toBeInTheDocument();
    expect(analyze).not.toHaveBeenCalled();
  });

  it("shows a loading state, disables the form, and then renders the result", async () => {
    stubFetch(apiRoutes());
    const pending = deferred<AnalyzeResponse>();
    renderWithProviders(<App />, { route: "/analyze", analyze: () => pending.promise });
    await typeReport();
    await userEvent.click(submitButton());

    expect(await screen.findByText("Analysis in progress")).toBeInTheDocument();
    expect(screen.getAllByRole("status").some((el) => el.textContent?.includes("Analyzing incident…"))).toBe(true);
    expect(submitButton()).toBeDisabled();
    expect(screen.getByLabelText("Emergency report")).toBeDisabled();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument(); // no fake progress percentages

    pending.resolve(serious);
    expect(await screen.findByRole("heading", { name: "Incident analysis" })).toBeInTheDocument();
    expect(screen.queryByText("Analysis in progress")).not.toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
  });

  it("sends exactly what was entered (optional fields omitted) with the dashboard source", async () => {
    stubFetch(apiRoutes());
    const analyze = vi.fn<(r: AnalyzeRequest) => Promise<AnalyzeResponse>>().mockResolvedValue(serious);
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await typeReport("A crash on the highway.");
    await userEvent.click(submitButton());
    await screen.findByRole("heading", { name: "Incident analysis" });
    expect(analyze).toHaveBeenCalledWith({ raw_text: "A crash on the highway.", source: "dashboard" });
  });

  it("includes coordinates only when the user provided them", async () => {
    stubFetch(apiRoutes());
    const analyze = vi.fn<(r: AnalyzeRequest) => Promise<AnalyzeResponse>>().mockResolvedValue(serious);
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await typeReport("A crash.");
    await userEvent.type(screen.getByLabelText("Latitude"), "39.10");
    await userEvent.type(screen.getByLabelText("Longitude"), "-94.58");
    await userEvent.click(submitButton());
    await screen.findByRole("heading", { name: "Incident analysis" });
    expect(analyze).toHaveBeenCalledWith(expect.objectContaining({ latitude: 39.1, longitude: -94.58 }));
  });

  it("ignores a second submission while one is in flight", async () => {
    stubFetch(apiRoutes());
    const pending = deferred<AnalyzeResponse>();
    const analyze = vi.fn(() => pending.promise);
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await typeReport();
    await userEvent.click(submitButton());
    await userEvent.click(submitButton()); // disabled + guarded
    expect(analyze).toHaveBeenCalledTimes(1);
    pending.resolve(serious);
    await screen.findByRole("heading", { name: "Incident analysis" });
  });

  it("shows a human-readable error, keeps the text, and retries", async () => {
    stubFetch(apiRoutes());
    const analyze = vi.fn<(r: AnalyzeRequest) => Promise<AnalyzeResponse>>()
      .mockRejectedValueOnce(new ApiError("http", "raw internal text /srv/app.py", { status: 503, code: "SERVICE_UNAVAILABLE", requestId: "req-123456" }))
      .mockResolvedValueOnce(serious);
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await typeReport();
    await userEvent.click(submitButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("ResQAI could not analyze this report because the analysis service is currently unavailable.");
    expect(alert).not.toHaveTextContent(/srv|Traceback|app\.py/);
    expect(alert).toHaveTextContent("req-123456");
    expect(screen.getByLabelText("Emergency report")).toHaveValue(REPORT); // text preserved

    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Incident analysis" })).toBeInTheDocument();
    expect(analyze).toHaveBeenCalledTimes(2);
  });

  it("maps a backend 422 onto the matching form field", async () => {
    stubFetch(apiRoutes());
    const err = validationErrorFixture.error;
    const analyze = vi.fn().mockRejectedValue(new ApiError("http", err.message, {
      status: 422, code: err.code, requestId: err.request_id, details: err.details ?? [],
    }));
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await typeReport();
    await userEvent.click(submitButton());
    expect(await screen.findByText(/Please enter a valid emergency report \(between 1 and 5000 characters\)/)).toBeInTheDocument();
    expect(screen.getByLabelText("Emergency report")).toHaveAttribute("aria-invalid", "true");
  });

  it("explains a network failure without exposing internals", async () => {
    stubFetch(apiRoutes());
    const analyze = vi.fn().mockRejectedValue(new ApiError("network", "fetch failed ECONNREFUSED"));
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await typeReport();
    await userEvent.click(submitButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not be reached");
    expect(alert).not.toHaveTextContent("ECONNREFUSED");
  });

  it("fills the form from an example scenario without analyzing it", async () => {
    stubFetch(apiRoutes());
    const analyze = vi.fn();
    renderWithProviders(<App />, { route: "/analyze", analyze });
    await userEvent.click(screen.getByRole("button", { name: "Pedestrian collision" }));
    expect(screen.getByLabelText("Emergency report")).toHaveValue(
      "A pedestrian was struck by a speeding vehicle. The driver fled the scene.",
    );
    expect(screen.getByText(/Example scenarios \(demo text\)/)).toBeInTheDocument();
    expect(analyze).not.toHaveBeenCalled();
  });

  it("shows the disagreement panel for a flagged result", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze", analyze: () => Promise.resolve(disagreement) });
    await typeReport();
    await userEvent.click(submitButton());
    expect(await screen.findByText("Model and operational-risk assessment differ")).toBeInTheDocument();
  });

  it("records the analysis in local history WITHOUT the report text", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze", analyze: () => Promise.resolve(serious) });
    await typeReport();
    await userEvent.click(submitButton());
    await screen.findByRole("heading", { name: "Incident analysis" });
    const stored = localStorage.getItem(HISTORY_STORAGE_KEY)!;
    expect(stored).toContain(serious.request_id);
    expect(stored).not.toContain("collided");
    expect(stored).not.toContain("intersection");
  });
});

describe("Resources page", () => {
  it("lists the catalog with every resource labelled simulated", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/resources" });
    expect(await screen.findByText(`${resourcesFixture.count} demo resources`)).toBeInTheDocument();
    expect(screen.getAllByText("Simulated")).toHaveLength(resourcesFixture.count);
    expect(screen.getByText(/None of these are real emergency units/)).toBeInTheDocument();
  });

  it("applies filters through the API's own query parameters", async () => {
    const ambulances = { ...resourcesFixture, count: 1, resources: resourcesFixture.resources.filter((r) => r.resource_type === "ambulance").slice(0, 1) };
    const mock = stubFetch({
      ...apiRoutes(),
      "/resources?resource_type=ambulance": () => jsonResponse(ambulances),
    });
    renderWithProviders(<App />, { route: "/resources" });
    await screen.findByText(`${resourcesFixture.count} demo resources`);
    await userEvent.selectOptions(screen.getByLabelText("Resource type"), "ambulance");
    expect(await screen.findByText("1 demo resource")).toBeInTheDocument();
    const urls = mock.mock.calls.map((c) => String((c as unknown as [string])[0]));
    expect(urls.some((u) => u.includes("resource_type=ambulance"))).toBe(true);
  });

  it("shows an empty state when the filters match nothing", async () => {
    stubFetch({
      ...apiRoutes(),
      "/resources?resource_type=hazmat_response": () => jsonResponse({ ...resourcesFixture, count: 0, resources: [] }),
    });
    renderWithProviders(<App />, { route: "/resources" });
    await screen.findByText(`${resourcesFixture.count} demo resources`);
    await userEvent.selectOptions(screen.getByLabelText("Resource type"), "hazmat_response");
    expect(await screen.findByText("No demo resources match these filters.")).toBeInTheDocument();
  });

  it("shows a readable error if the catalog cannot be loaded", async () => {
    stubFetch({ "/resources": () => jsonResponse({ error: { code: "SERVICE_UNAVAILABLE", message: "x", request_id: "rid" } }, 503) });
    renderWithProviders(<App />, { route: "/resources" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/currently unavailable/);
  });
});

describe("Analytics page", () => {
  it("shows the empty session state and never invents counts", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analytics" });
    expect(await screen.findByText("No session analytics yet.")).toBeInTheDocument();
    expect(screen.getByText("Run a few analyses to populate session analytics.")).toBeInTheDocument();
    expect(screen.queryByText("Reports analyzed")).not.toBeInTheDocument();
  });

  it("computes session statistics from the stored analyses", async () => {
    stubFetch(apiRoutes());
    saveHistory([toSessionRecord(serious), toSessionRecord(disagreement), toSessionRecord(noPrediction)]);
    renderWithProviders(<App />, { route: "/analytics" });
    const stat = async (label: string) => (await screen.findByText(label)).closest("div")!;

    expect(await stat("Reports analyzed")).toHaveTextContent("3");
    expect(await stat("Prediction available")).toHaveTextContent("2");
    expect(await stat("Model/rule disagreements")).toHaveTextContent("1");
    expect(await stat("Model/rule disagreements")).toHaveTextContent("33.3% of analyses");
    expect(await stat("Most frequent risk indicator")).toHaveTextContent(/Moderate|Road blockage|Multiple|Severe|Possible|Hazardous/i);
  });

  it("clears the session history on request", async () => {
    stubFetch(apiRoutes());
    saveHistory([toSessionRecord(serious)]);
    renderWithProviders(<App />, { route: "/analytics" });
    await userEvent.click(await screen.findByRole("button", { name: /Clear session history/ }));
    expect(await screen.findByText("No session analytics yet.")).toBeInTheDocument();
    expect(localStorage.getItem(HISTORY_STORAGE_KEY)).toBeNull();
  });

  it("shows the backend's real model metrics for BOTH models, with no 'best' claim", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analytics" });
    const table = await screen.findByRole("table", { name: "Model evaluation metrics" });
    for (const m of metricsFixture.models) {
      expect(within(table).getByText(m.display_name)).toBeInTheDocument();
      expect(within(table).getAllByText(new RegExp(m.evaluation!.macro_f1.toFixed(3))).length).toBeGreaterThan(0);
      expect(within(table).getAllByText(new RegExp(m.evaluation!.fatal_class_recall.toFixed(3))).length).toBeGreaterThan(0);
    }
    expect(within(table).getByText("Fatal-class recall")).toBeInTheDocument();
    expect(screen.getByText("Reading the trade-offs")).toBeInTheDocument();
    // model role, feature count, prediction-source id and limitations come from GET /models
    const facts = await screen.findByRole("group", { name: "About these models" });
    for (const m of modelsFixture.models) {
      expect(within(facts).getByText(m.source_id)).toBeInTheDocument();
      expect(within(facts).getByText(m.limitations[0]!)).toBeInTheDocument();
    }
    expect(within(facts).getByText("32")).toBeInTheDocument();
    expect(within(facts).getByText("15")).toBeInTheDocument();
    expect(screen.queryByText(/\bbest\b/i)).not.toBeInTheDocument();
  });

  it("says metrics are not exposed when the backend has none, instead of showing numbers", async () => {
    stubFetch({
      ...apiRoutes(),
      "/models/metrics": () => jsonResponse({
        evaluation_note: "n",
        models: metricsFixture.models.map((m) => ({ ...m, available: false, evaluation: null })),
      }),
    });
    renderWithProviders(<App />, { route: "/analytics" });
    expect(await screen.findByText("Model metrics are not exposed for this deployment.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Model evaluation metrics" })).not.toBeInTheDocument();
  });
});

describe("System page", () => {
  it("renders health, readiness, components and model information from the API", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/system" });
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("Ready to analyze reports")).toBeInTheDocument();
    const components = screen.getByRole("list", { name: "Components" });
    for (const label of ["API", "Report intelligence (parser)", "Demo resource catalog", "Historical severity model", "Report-compatible severity model"]) {
      expect(within(components).getByText(label)).toBeInTheDocument();
    }
    expect(await screen.findByText("Historical Model (Phase 1)")).toBeInTheDocument();
    expect(screen.getByText("Report-Compatible Model (Phase 3.5)")).toBeInTheDocument();
    expect(screen.getByText(modelsFixture.routing)).toBeInTheDocument();
  });

  it("reports a degraded backend and an unavailable component honestly", async () => {
    stubFetch(apiRoutes());
    const degraded = structuredClone(healthFixture);
    degraded.status = "degraded";
    degraded.components.historical_model = { status: "unavailable", detail: "Model artifact is not loaded." };
    renderWithProviders(<App />, { route: "/system", fetchHealth: () => Promise.resolve(degraded) });
    expect(await screen.findByText(/Degraded — service works but a severity model is unavailable/)).toBeInTheDocument();
    const row = screen.getByText("Historical severity model").closest("li")!;
    expect(within(row).getByText("Unavailable")).toBeInTheDocument();
  });

  it("shows NOT_READY reasons", async () => {
    stubFetch(apiRoutes());
    const notReady = { ...readyFixture, status: "NOT_READY" as const, reasons: ["Required component 'resource_catalog' is unavailable."] };
    renderWithProviders(<App />, { route: "/system", fetchReadiness: () => Promise.resolve(notReady) });
    expect(await screen.findByText("Not ready")).toBeInTheDocument();
    expect(screen.getByText("Required component 'resource_catalog' is unavailable.")).toBeInTheDocument();
  });

  it("shows a clear message when the backend is unreachable", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, {
      route: "/system",
      fetchHealth: () => Promise.reject(new ApiError("network", "x")),
    });
    expect(await screen.findByText("Cannot reach the ResQAI service")).toBeInTheDocument();
    expect(screen.getAllByText("Service unreachable").length).toBeGreaterThan(0); // header pill too
  });
});

describe("Backend waking up (free hosting cold start)", () => {
  it("retries patiently, shows a waking state, then recovers without any user action", async () => {
    stubFetch(apiRoutes());
    const fetchHealth = vi.fn()
      .mockRejectedValueOnce(new ApiError("network", "x"))
      .mockRejectedValueOnce(new ApiError("timeout", "x"))
      .mockResolvedValue(healthFixture);
    renderWithProviders(<App />, { route: "/analyze", fetchHealth });
    expect(await screen.findByText("Service ready")).toBeInTheDocument();
    expect(fetchHealth).toHaveBeenCalledTimes(3);
  });

  it("shows the waking state while retrying", async () => {
    stubFetch(apiRoutes());
    let release!: (h: typeof healthFixture) => void;
    const fetchHealth = vi.fn()
      .mockRejectedValueOnce(new ApiError("network", "x"))
      .mockImplementationOnce(() => new Promise((res) => { release = res; }));
    renderWithProviders(<App />, { route: "/analyze", fetchHealth });
    expect(await screen.findByText(/Waking up service/)).toBeInTheDocument();
    release(healthFixture);
    expect(await screen.findByText("Service ready")).toBeInTheDocument();
  });

  it("gives up after the retry budget and reports the service as unreachable", async () => {
    stubFetch(apiRoutes());
    const fetchHealth = vi.fn().mockRejectedValue(new ApiError("network", "x"));
    renderWithProviders(<App />, { route: "/analyze", fetchHealth });
    expect((await screen.findAllByText("Service unreachable")).length).toBeGreaterThan(0);
    expect(fetchHealth.mock.calls.length).toBeGreaterThan(1);
  });

  it("does not retry a configuration error (it will not fix itself)", async () => {
    stubFetch(apiRoutes());
    const fetchHealth = vi.fn().mockRejectedValue(new ApiError("not_configured", "x"));
    renderWithProviders(<App />, { route: "/analyze", fetchHealth });
    expect((await screen.findAllByText("Service unreachable")).length).toBeGreaterThan(0);
    expect(fetchHealth).toHaveBeenCalledTimes(1);
  });
});

describe("Navigation and layout", () => {
  it("offers all four areas plus a persistent human-oversight notice and status pill", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const name of ["Analyze Incident", "Resources", "Analytics", "System"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Human oversight required")).toBeInTheDocument();
    expect(await screen.findByText("Service ready")).toBeInTheDocument();
  });

  it("shows the single release version from the VERSION file in the footer", () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze" });
    expect(screen.getByText(`ResQAI v${__APP_VERSION__}`)).toBeInTheDocument();
    expect(__APP_VERSION__).toMatch(/^[0-9]+[.][0-9]+[.][0-9]+/);
  });

  it("states the decision-support purpose and human review on the analyze page", () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze" });
    expect(screen.getByText(/provides decision-support information for human review/)).toBeInTheDocument();
  });

  it("redirects / to the analyze workflow", () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/" });
    expect(screen.getByRole("heading", { name: "Analyze an emergency report" })).toBeInTheDocument();
  });

  it("has a menu button that toggles the mobile navigation and exposes its state", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze" });
    const button = screen.getByRole("button", { name: /Menu/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "primary-nav");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "Primary" })).toHaveClass("block");
    await userEvent.click(screen.getByRole("link", { name: "Resources" }));
    await waitFor(() => expect(button).toHaveAttribute("aria-expanded", "false")); // closes after navigating
  });

  it("navigates between pages and keeps the analysis when returning", async () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/analyze", analyze: () => Promise.resolve(serious) });
    await typeReport();
    await userEvent.click(submitButton());
    await screen.findByRole("heading", { name: "Incident analysis" });
    await userEvent.click(screen.getByRole("link", { name: "System" }));
    await screen.findByRole("heading", { name: "System and models" });
    await userEvent.click(screen.getByRole("link", { name: "Analyze Incident" }));
    expect(await screen.findByRole("heading", { name: "Incident analysis" })).toBeInTheDocument();
    expect(screen.getByLabelText("Emergency report")).toHaveValue(REPORT);
  });

  it("has a skip link and an unknown-route page", () => {
    stubFetch(apiRoutes());
    renderWithProviders(<App />, { route: "/does-not-exist" });
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
