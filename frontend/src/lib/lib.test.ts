import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import { summarizeSession } from "./analytics";
import { describeError } from "./errors";
import { formatValue, humanize, sourceLabel, uniqueStrings } from "./format";
import { EMPTY_FORM, toAnalyzeRequest, validateReportForm } from "./reportForm";
import {
  addRecord, clearStoredHistory, HISTORY_STORAGE_KEY, loadHistory, MAX_HISTORY_RECORDS, saveHistory,
  toSessionRecord, type SessionRecord,
} from "./sessionHistory";
import { projectRelativeTo } from "./geo";
import { disagreement, noPrediction, serious } from "../test/fixtures";

function record(overrides: Partial<SessionRecord> = {}): SessionRecord {
  return {
    id: "r1", analyzedAt: "2026-09-21T10:00:00.000Z", incidentType: "vehicle_collision", priority: "P1",
    riskLevel: "high", predictionAvailable: true, predictionSource: "report_compatible_model",
    predictedSeverity: "Fatal Injury (K)", modelRuleDisagreement: false, riskIndicators: ["road_blockage"],
    ...overrides,
  };
}

describe("format helpers", () => {
  it("humanizes identifiers and never prints null/undefined", () => {
    expect(humanize("unconscious_person")).toBe("Unconscious person");
    expect(formatValue(null)).toBe("—");
    expect(formatValue(undefined)).toBe("—");
    expect(formatValue(true)).toBe("Yes");
    expect(formatValue(["cars", "trucks"])).toBe("cars, trucks");
    expect(sourceLabel("report_compatible_model")).toBe("Report-Compatible Model");
    expect(uniqueStrings(["a", "b", "a"])).toEqual(["a", "b"]);
  });
});

describe("error translation", () => {
  it("maps backend codes to friendly messages with no internals", () => {
    const unavailable = describeError(new ApiError("http", "raw backend text", { status: 503, code: "SERVICE_UNAVAILABLE", requestId: "rid-1" }));
    expect(unavailable.message).toMatch(/currently unavailable/);
    expect(unavailable.retryable).toBe(true);
    expect(unavailable.requestId).toBe("rid-1");

    const internal = describeError(new ApiError("http", "Traceback C:\\secret\\path", { status: 500, code: "INTERNAL_ERROR" }));
    expect(internal.message).toBe("Something went wrong while analyzing the incident. Please try again.");
    expect(JSON.stringify(internal)).not.toMatch(/Traceback|secret/);

    expect(describeError(new ApiError("http", "x", { status: 400, code: "INVALID_REPORT" })).message).toBe("Please enter a valid emergency report.");
  });

  it("maps a 422 to field-specific guidance", () => {
    const result = describeError(new ApiError("http", "x", {
      status: 422, code: "VALIDATION_ERROR", details: [{ field: "latitude", message: "Input should be <= 90" }],
    }));
    expect(result.fieldErrors.latitude).toMatch(/between -90 and 90/);
    expect(result.retryable).toBe(false);
  });

  it("handles network, timeout and unknown failures", () => {
    expect(describeError(new ApiError("network", "x")).title).toMatch(/Cannot reach/);
    expect(describeError(new ApiError("timeout", "x")).title).toMatch(/timed out/);
    expect(describeError(new Error("boom")).message).not.toContain("boom");
  });
});

describe("report form", () => {
  it("rejects a blank report and bad coordinates, accepts a valid form", () => {
    expect(validateReportForm({ ...EMPTY_FORM, rawText: "   " }).rawText).toBeTruthy();
    expect(validateReportForm({ ...EMPTY_FORM, rawText: "ok", latitude: "95", longitude: "10" }).latitude).toMatch(/-90 and 90/);
    expect(validateReportForm({ ...EMPTY_FORM, rawText: "ok", latitude: "10", longitude: "" }).longitude).toMatch(/both/i);
    expect(validateReportForm({ ...EMPTY_FORM, rawText: "ok", latitude: "abc", longitude: "10" }).latitude).toMatch(/number/);
    expect(validateReportForm({ ...EMPTY_FORM, rawText: "ok", latitude: "39.1", longitude: "-94.5" })).toEqual({});
    expect(validateReportForm({ ...EMPTY_FORM, rawText: "x".repeat(5001) }).rawText).toMatch(/too long/);
  });

  it("builds a request that omits empty optional fields instead of inventing defaults", () => {
    expect(toAnalyzeRequest({ ...EMPTY_FORM, rawText: "  A crash.  " })).toEqual({ raw_text: "A crash.", source: "dashboard" });
    const full = toAnalyzeRequest({
      rawText: "A crash.", latitude: "39.1", longitude: "-94.5", timestamp: "2026-09-19T10:30", reportId: "r-1",
    });
    expect(full).toMatchObject({ latitude: 39.1, longitude: -94.5, timestamp: "2026-09-19T10:30", report_id: "r-1" });
  });
});

describe("session history", () => {
  it("stores outcome metadata only: no report text, coordinates or report id", () => {
    const stored = toSessionRecord(serious, new Date("2026-09-21T10:00:00Z"));
    const json = JSON.stringify(stored);
    expect(json).not.toContain(serious.explanation.report_facts[0]!);
    expect(json).not.toMatch(/latitude|longitude|39\.1|-94\.58|fx-serious/);
    expect(stored.priority).toBe(serious.decision.priority);
    expect(stored.riskIndicators).toEqual(serious.risk_indicators.map((r) => r.name));
  });

  it("marks disagreement only when the API reported one", () => {
    expect(toSessionRecord(disagreement).modelRuleDisagreement).toBe(true);
    expect(toSessionRecord(serious).modelRuleDisagreement).toBe(false);
    expect(toSessionRecord(noPrediction).predictionAvailable).toBe(false);
  });

  it("persists, reloads, caps and clears", () => {
    saveHistory([record({ id: "a" }), record({ id: "b" })]);
    expect(loadHistory().map((r) => r.id)).toEqual(["a", "b"]);
    clearStoredHistory();
    expect(loadHistory()).toEqual([]);

    let list: SessionRecord[] = [];
    for (let i = 0; i < MAX_HISTORY_RECORDS + 5; i++) list = addRecord(list, record({ id: `id-${i}` }));
    expect(list).toHaveLength(MAX_HISTORY_RECORDS);
    expect(list[0]!.id).toBe(`id-${MAX_HISTORY_RECORDS + 4}`); // newest first
  });

  it("ignores corrupt or malformed stored data instead of crashing", () => {
    localStorage.setItem(HISTORY_STORAGE_KEY, "{not json");
    expect(loadHistory()).toEqual([]);
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify([{ id: 1 }, record({ id: "ok" })]));
    expect(loadHistory().map((r) => r.id)).toEqual(["ok"]);
  });
});

describe("session analytics (computed from real records only)", () => {
  it("returns empty, non-misleading values with no records", () => {
    const s = summarizeSession([]);
    expect(s.total).toBe(0);
    expect(s.disagreementRate).toBeNull();
    expect(s.mostFrequentRiskIndicator).toBeNull();
  });

  it("counts analyses, predictions, sources, priorities and risk indicators", () => {
    const s = summarizeSession([
      record({ id: "1", riskIndicators: ["road_blockage", "severe_weather"] }),
      record({ id: "2", riskIndicators: ["road_blockage"], priority: "P0" }),
      record({ id: "3", predictionAvailable: false, predictionSource: "none", predictedSeverity: null, riskIndicators: [] }),
    ]);
    expect(s.total).toBe(3);
    expect(s.predictionAvailable).toBe(2);
    expect(s.predictionUnavailable).toBe(1);
    expect(s.predictionSources).toEqual([
      { key: "report_compatible_model", count: 2 }, { key: "none", count: 1 },
    ]);
    expect(s.priorities).toEqual([{ key: "P1", count: 2 }, { key: "P0", count: 1 }]);
    expect(s.mostFrequentRiskIndicator).toEqual({ key: "road_blockage", count: 2 });
    expect(s.predictedSeverities).toEqual([{ key: "Fatal Injury (K)", count: 2 }]); // unavailable ones excluded
  });

  it("computes the disagreement count and rate from the records", () => {
    const s = summarizeSession([
      record({ id: "1", modelRuleDisagreement: true }),
      record({ id: "2" }), record({ id: "3" }),
      record({ id: "4", modelRuleDisagreement: true }),
    ]);
    expect(s.disagreements).toBe(2);
    expect(s.disagreementRate).toBe(0.5);
  });
});

describe("location projection", () => {
  it("places the incident-relative points without inventing any", () => {
    const { points, extentKm } = projectRelativeTo({ latitude: 39.1, longitude: -94.58 }, [
      { id: "north", latitude: 39.2, longitude: -94.58 },
      { id: "east", latitude: 39.1, longitude: -94.48 },
    ]);
    expect(points).toHaveLength(2);
    expect(points[0]!.y).toBeGreaterThan(0.9); // north of the incident
    expect(Math.abs(points[0]!.x)).toBeLessThan(0.01);
    expect(points[1]!.x).toBeGreaterThan(0.5); // east of the incident
    expect(extentKm).toBeGreaterThan(5);
    expect(projectRelativeTo({ latitude: 0, longitude: 0 }, []).points).toEqual([]);
  });
});
