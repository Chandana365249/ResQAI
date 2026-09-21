import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AnalyzeResponse } from "../api";
import { disagreement, hazmat, noPrediction, resourcesFixture, serious } from "../test/fixtures";
import { jsonResponse, stubFetch } from "../test/utils";
import { WarningPanel } from "./common/WarningPanel";
import { DecisionSummary } from "./decision/DecisionSummary";
import { AnalysisHeader } from "./incident/AnalysisHeader";
import { AnalysisResult } from "./incident/AnalysisResult";
import { EvidencePanel } from "./incident/EvidencePanel";
import { ExplanationCard } from "./incident/ExplanationCard";
import { ExtractedInformation } from "./incident/ExtractedInformation";
import { IncidentSummary } from "./incident/IncidentSummary";
import { DisagreementAlert } from "./ml/DisagreementAlert";
import { MlPredictionCard } from "./ml/MlPredictionCard";
import { ResourceResults } from "./resources/ResourceResults";
import { RiskIndicatorList } from "./risk/RiskIndicatorList";

const clone = (r: AnalyzeResponse): AnalyzeResponse => structuredClone(r);

describe("extracted information, certainty and evidence", () => {
  it("renders extracted fields grouped, with value and certainty", () => {
    render(<ExtractedInformation data={serious.extracted_information} />);
    expect(screen.getByRole("heading", { name: "People" })).toBeInTheDocument();
    const row = screen.getByText("Unconscious person").closest("li")!;
    expect(within(row).getByText("Yes")).toBeInTheDocument();
    expect(within(row).getByText("Possible")).toBeInTheDocument();
  });

  it("does not present 'possible' the same way as 'confirmed'", () => {
    render(<ExtractedInformation data={serious.extracted_information} />);
    const possible = screen.getAllByText("Possible")[0]!;
    const confirmed = screen.getAllByText("Confirmed")[0]!;
    expect(possible.className).not.toBe(confirmed.className);
    expect(possible.className).toContain("border-dashed"); // distinct border, not colour alone
    expect(confirmed.className).toContain("border-solid");
  });

  it("shows the supporting evidence text inside the expandable provenance panel", async () => {
    render(<EvidencePanel evidence={serious.evidence} />);
    expect(screen.getByText("Why was this information extracted?")).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Show the supporting evidence/));
    expect(screen.getAllByText("“one person may be unconscious.”").length).toBeGreaterThan(0);
  });

  it("does not invent evidence the API did not provide", async () => {
    render(<EvidencePanel evidence={[{ field: "rain", value: true, certainty: "confirmed", evidence: null }]} />);
    await userEvent.click(screen.getByText(/Show the supporting evidence/));
    expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
  });

  it("has an empty state when nothing was extracted", () => {
    render(<ExtractedInformation data={{}} />);
    expect(screen.getByText("No structured details were extracted from this report.")).toBeInTheDocument();
  });
});

describe("risk indicators", () => {
  it("renders name, level, certainty, explanation and evidence from the API", () => {
    render(<RiskIndicatorList indicators={serious.risk_indicators} />);
    const item = screen.getByText("Possible unconscious person").closest("li")!;
    expect(within(item).getByText("High")).toBeInTheDocument();
    expect(within(item).getByText("Possible")).toBeInTheDocument();
    expect(within(item).getByText("The report indicates a person may be unconscious.")).toBeInTheDocument();
    expect(within(item).getByText(/one person may be unconscious/)).toBeInTheDocument();
  });

  it("shows a clear empty state when no indicators were detected", () => {
    render(<RiskIndicatorList indicators={[]} />);
    expect(screen.getByText("No operational risk indicators were detected for this report.")).toBeInTheDocument();
  });
});

describe("machine-learning prediction", () => {
  it("shows the predicted label, source, model, features used and routing note", () => {
    render(<MlPredictionCard result={serious} />);
    expect(screen.getByText("Predicted severity").nextElementSibling).toHaveTextContent("Fatal Injury (K)");
    expect(screen.getAllByText("Report-Compatible Model").length).toBeGreaterThan(0);
    expect(screen.getByText("RandomForestClassifier")).toBeInTheDocument();
    for (const feature of serious.ml_prediction.features_used) {
      expect(screen.getByText(feature.charAt(0).toUpperCase() + feature.slice(1).replace(/_/g, " "))).toBeInTheDocument();
    }
    // the backend's own routing explanation, shown verbatim
    expect(screen.getByText(serious.ml_prediction.prediction_note!)).toBeInTheDocument();
  });

  it("renders every actual probability and none that the API did not provide", () => {
    render(<MlPredictionCard result={serious} />);
    const list = screen.getByRole("list", { name: "Model class probabilities" });
    const entries = Object.entries(serious.ml_prediction.probabilities!);
    expect(within(list).getAllByRole("listitem")).toHaveLength(entries.length);
    for (const [label, p] of entries) {
      const item = within(list).getByText(label, { exact: false }).closest("li")!;
      expect(item).toHaveTextContent(`${(p * 100).toFixed(1)}%`);
    }
    expect(within(list).getByText("(predicted)")).toBeInTheDocument();
  });

  it("shows an honest state when probabilities are missing", () => {
    const result = clone(serious);
    result.ml_prediction.probabilities = null;
    render(<MlPredictionCard result={result} />);
    expect(screen.getByText("Model probabilities are unavailable for this prediction.")).toBeInTheDocument();
  });

  it("shows 'prediction unavailable' with the API's reason, exactly once", () => {
    render(<MlPredictionCard result={noPrediction} />);
    expect(screen.getByText("Model prediction unavailable")).toBeInTheDocument();
    expect(screen.getAllByText(noPrediction.ml_prediction.prediction_note!)).toHaveLength(1);
    expect(screen.queryByText("Predicted severity")).not.toBeInTheDocument();
  });

  it("labels the statistical model as distinct from operational risk and priority", () => {
    render(<MlPredictionCard result={serious} />);
    expect(screen.getByText("Statistical model")).toBeInTheDocument();
    expect(screen.getByText(/not the same thing as the operational risk or priority/)).toBeInTheDocument();
  });
});

describe("model / rule disagreement", () => {
  it("is shown prominently, with both sides and the API's explanation", () => {
    render(<DisagreementAlert result={disagreement} />);
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("Model and operational-risk assessment differ")).toBeInTheDocument();
    expect(within(alert).getByText("Fatal Injury (K)")).toBeInTheDocument();
    expect(within(alert).getByText("Low")).toBeInTheDocument();
    expect(within(alert).getByText(disagreement.model_rule_disagreement!)).toBeInTheDocument();
    expect(within(alert).getByText(/Human review required/)).toBeInTheDocument();
    expect(alert).not.toHaveTextContent(/correct answer|is wrong|override/i);
  });

  it("is absent when the API reports no disagreement", () => {
    render(<DisagreementAlert result={serious} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("decision", () => {
  it("shows priority, risk level, reasons and response categories from the API", () => {
    render(<DecisionSummary decision={serious.decision} />);
    expect(screen.getByLabelText("Priority P0")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    for (const reason of serious.decision.reasons) expect(screen.getByText(reason)).toBeInTheDocument();
    for (const category of ["Ambulance", "Police response", "Traffic management"]) {
      expect(screen.getByText(category)).toBeInTheDocument();
    }
    expect(screen.getByText(/not a validated emergency dispatch standard or medical triage/)).toBeInTheDocument();
  });

  it("says so when no response category was recommended", () => {
    render(<DecisionSummary decision={disagreement.decision} />);
    expect(screen.getByText(/did not recommend any response category/)).toBeInTheDocument();
  });
});

describe("resources", () => {
  const routes = () => ({ "/resources": () => jsonResponse(resourcesFixture) });

  it("renders each matched resource with distance, capabilities, reason and a SIMULATED label", () => {
    stubFetch(routes());
    render(<ResourceResults section={serious.resources} />);
    const first = serious.resources.searches[0]!.recommendations[0]!;
    const card = screen.getByText(first.resource_name, { exact: false }).closest("li")!;
    expect(within(card).getByText(`${first.distance_km!.toFixed(1)} km`)).toBeInTheDocument();
    expect(within(card).getByText(first.reason)).toBeInTheDocument();
    expect(within(card).getByText("Simulated")).toBeInTheDocument();

    const total = serious.resources.searches.reduce((n, s) => n + s.recommendations.length, 0);
    expect(screen.getAllByText("Simulated")).toHaveLength(total); // every resource is labelled
    expect(screen.getByText(serious.resources.notice)).toBeInTheDocument();
  });

  it("draws the location plot from real coordinates once the catalog loads", async () => {
    stubFetch(routes());
    render(<ResourceResults section={serious.resources} />);
    expect(await screen.findByRole("img", { name: /Schematic plot of the incident/ })).toBeInTheDocument();
    expect(screen.getByText(/Schematic only — not a street map/)).toBeInTheDocument();
  });

  it("is honest when no location was provided: no plot, no invented coordinates, no distances", () => {
    stubFetch(routes());
    render(<ResourceResults section={noPrediction.resources} />);
    expect(screen.getByText(/Location not provided — proximity ranking and the location plot are unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Schematic plot/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("Not ranked (no incident location)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0); // still labelled without a location
  });

  it("shows an empty state when a category matched no resources", () => {
    stubFetch(routes());
    const section = clone(hazmat).resources;
    section.searches = [{ category: "ambulance", resource_available: false, reason: "No available demo resource matched the requested response category.", recommendations: [] }];
    render(<ResourceResults section={section} />);
    expect(screen.getByText("No compatible demo resources found.")).toBeInTheDocument();
    expect(screen.getByText("No available demo resource matched the requested response category.")).toBeInTheDocument();
  });

  it("shows an empty state when no categories were recommended", () => {
    stubFetch(routes());
    render(<ResourceResults section={disagreement.resources} />);
    expect(screen.getByText("No response categories were recommended, so no resources were searched.")).toBeInTheDocument();
  });
});

describe("header, summary, explanation, warnings", () => {
  it("keeps incident, priority, operational risk and model prediction as SEPARATE, labelled tiles", () => {
    render(<AnalysisHeader result={serious} />);
    for (const label of ["Incident", "Priority", "Operational risk", "Model prediction"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Human oversight required")).toBeInTheDocument();
    expect(screen.queryByText(/score/i)).not.toBeInTheDocument(); // no combined "AI score"
  });

  it("shows 'Unavailable' rather than a value when there is no prediction", () => {
    render(<AnalysisHeader result={noPrediction} />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("uses friendly 'Not provided' states, never null/undefined", () => {
    const result = clone(noPrediction);
    result.report.timestamp = null;
    result.report.source = null;
    const { container } = render(<IncidentSummary result={result} />);
    expect(screen.getAllByText("Not provided").length).toBeGreaterThanOrEqual(2);
    expect(container.textContent).not.toMatch(/\bnull\b|\bundefined\b|-1|999/);
  });

  it("lists what is uncertain and labels each explanation by origin", () => {
    render(<ExplanationCard result={serious} />);
    expect(screen.getByText("Unconscious person (possible)")).toBeInTheDocument();
    expect(screen.getByText(serious.explanation.report_facts[0]!)).toBeInTheDocument();
    expect(screen.getAllByText("From the report", { selector: "span" }).length).toBeGreaterThan(0);
  });

  it("de-duplicates warnings and hides ones already shown elsewhere", () => {
    render(<WarningPanel warnings={["a", "a", "b", "c"]} alreadyShown={["c"]} />);
    expect(screen.getAllByText("a")).toHaveLength(1);
    expect(screen.getByText("b")).toBeInTheDocument();
    expect(screen.queryByText("c")).not.toBeInTheDocument();
  });

  it("renders nothing when there are no warnings", () => {
    const { container } = render(<WarningPanel warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("full result", () => {
  it("renders the whole analysis with no 'undefined' or 'null' text", () => {
    stubFetch({ "/resources": () => jsonResponse(resourcesFixture) });
    const { container } = render(<AnalysisResult result={serious} />);
    expect(screen.getByRole("heading", { name: "Incident analysis" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\bnull\b|\bundefined\b|\bNaN\b/);
    expect(screen.getByText(serious.disclaimer)).toBeInTheDocument();
  });

  it("survives a sparse/degraded response without crashing", () => {
    stubFetch({ "/resources": () => jsonResponse(resourcesFixture) });
    const sparse = clone(noPrediction);
    sparse.extracted_information = {};
    sparse.evidence = [];
    sparse.risk_indicators = [];
    sparse.warnings = [];
    sparse.resources.searches = [];
    sparse.decision.reasons = [];
    expect(() => render(<AnalysisResult result={sparse} />)).not.toThrow();
    expect(screen.getByText("Model prediction unavailable")).toBeInTheDocument();
  });
});

describe("regressions found during real-browser verification", () => {
  it("shows a repeated resource reason once and produces no duplicate-key warnings", () => {
    const result = clone(noPrediction); // no location: the API repeats one reason per unranked resource
    const reason = result.explanation.resource_reasons[0]!;
    result.explanation.resource_reasons = [reason, reason, reason];
    const errors: string[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args) => { errors.push(args.map(String).join(" ")); });
    render(<ExplanationCard result={result} />);
    spy.mockRestore();
    expect(screen.getAllByText(reason)).toHaveLength(1);
    expect(errors.filter((e) => e.includes("same key"))).toEqual([]);
  });

  it("still says the location is not provided when no response category was recommended", () => {
    stubFetch({ "/resources": () => jsonResponse(resourcesFixture) });
    const section = clone(disagreement).resources;
    section.location = { available: false, latitude: null, longitude: null, reason: "Latitude/longitude were not provided for this report." };
    render(<ResourceResults section={section} />);
    expect(screen.getByText("No response categories were recommended, so no resources were searched.")).toBeInTheDocument();
    expect(screen.getByText(/Location not provided/)).toBeInTheDocument();
  });
});

describe("result hierarchy (Phase 6)", () => {
  it("orders the header tiles: Incident, Operational risk, Priority, Model prediction", () => {
    render(<AnalysisHeader result={serious} />);
    const labels = ["Incident", "Operational risk", "Priority", "Model prediction"].map(
      (l) => screen.getByText(l, { selector: "p" }),
    );
    for (let i = 1; i < labels.length; i++) {
      expect(labels[i - 1]!.compareDocumentPosition(labels[i]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });
});
