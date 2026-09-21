/**
 * Local, client-side demo history. The backend is stateless (no database),
 * so this lives only in this browser's localStorage and is clearly labelled
 * as such in the UI.
 *
 * Privacy: a record keeps ONLY fields the API returned that describe the
 * analysis outcome. It deliberately does NOT store the report text,
 * coordinates, report id, or any free-text explanation.
 */

import type { AnalyzeResponse, Level, PredictionSource, Priority } from "../api";

export interface SessionRecord {
  /** The API's request_id (unique per analysis). */
  id: string;
  /** Client clock time at which the analysis completed. */
  analyzedAt: string;
  incidentType: string;
  priority: Priority;
  riskLevel: Level;
  predictionAvailable: boolean;
  predictionSource: PredictionSource;
  predictedSeverity: string | null;
  modelRuleDisagreement: boolean;
  riskIndicators: string[];
}

export const HISTORY_STORAGE_KEY = "resqai.sessionHistory.v1";
export const MAX_HISTORY_RECORDS = 50;

export function toSessionRecord(response: AnalyzeResponse, analyzedAt: Date = new Date()): SessionRecord {
  return {
    id: response.request_id,
    analyzedAt: analyzedAt.toISOString(),
    incidentType: response.incident.incident_type,
    priority: response.decision.priority,
    riskLevel: response.decision.risk_level,
    predictionAvailable: response.ml_prediction.available,
    predictionSource: response.ml_prediction.prediction_source,
    predictedSeverity: response.ml_prediction.predicted_label,
    modelRuleDisagreement: response.model_rule_disagreement !== null,
    riskIndicators: response.risk_indicators.map((r) => r.name),
  };
}

function isRecord(value: unknown): value is SessionRecord {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    typeof r.id === "string" && typeof r.analyzedAt === "string" && typeof r.incidentType === "string" &&
    typeof r.priority === "string" && typeof r.riskLevel === "string" &&
    typeof r.predictionAvailable === "boolean" && typeof r.predictionSource === "string" &&
    typeof r.modelRuleDisagreement === "boolean" && Array.isArray(r.riskIndicators)
  );
}

/** Never throws: storage can be disabled, full, or contain stale/corrupt data. */
export function loadHistory(): SessionRecord[] {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isRecord).slice(0, MAX_HISTORY_RECORDS) : [];
  } catch {
    return [];
  }
}

export function saveHistory(records: SessionRecord[]): void {
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(records.slice(0, MAX_HISTORY_RECORDS)));
  } catch {
    /* storage unavailable: history simply won't persist this session */
  }
}

export function clearStoredHistory(): void {
  try {
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
}

/** Newest first, capped. */
export function addRecord(records: SessionRecord[], record: SessionRecord): SessionRecord[] {
  return [record, ...records.filter((r) => r.id !== record.id)].slice(0, MAX_HISTORY_RECORDS);
}
