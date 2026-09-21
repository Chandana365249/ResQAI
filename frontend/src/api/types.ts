/**
 * TypeScript mirror of the ResQAI backend's public contract
 * (src/api/schemas/requests.py and src/api/schemas/responses.py).
 * The backend is the source of truth: if a field changes there, change it
 * here. Nothing in this file is computed or invented by the frontend.
 */

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type Certainty = "confirmed" | "possible" | "uncertain" | "not_mentioned";
export type Level = "critical" | "high" | "moderate" | "low";
export type Priority = "P0" | "P1" | "P2" | "P3";
export type PredictionSource = "phase1_historical_model" | "report_compatible_model" | "none";
export type ModelSourceId = Exclude<PredictionSource, "none">;

// ---------------------------------------------------------------- requests

export interface AnalyzeRequest {
  report_id?: string;
  raw_text: string;
  latitude?: number;
  longitude?: number;
  timestamp?: string;
  source?: string;
}

// ---------------------------------------------------------------- errors

export interface ErrorDetail {
  field?: string | null;
  message: string;
}
export interface ErrorBody {
  code: string;
  message: string;
  request_id: string;
  details?: ErrorDetail[] | null;
}
export interface ErrorResponse {
  error: ErrorBody;
}

// ---------------------------------------------------------------- analysis

export interface ReportMeta {
  report_id: string;
  source: string | null;
  timestamp: string | null;
}

export interface IncidentSummary {
  incident_type: string;
  incident_subtype: string | null;
  overall_extraction_confidence: "high" | "medium" | "low";
}

export interface ExtractedField {
  value: JsonValue;
  certainty: Certainty;
}
export type ExtractedInformation = Record<string, Record<string, ExtractedField>>;

export interface EvidenceItem {
  field: string;
  value: JsonValue;
  certainty: Certainty;
  evidence: string | null;
}

export interface RiskIndicator {
  name: string;
  level: Level;
  certainty: Certainty;
  evidence: string | null;
  explanation: string;
}

export interface MlPrediction {
  available: boolean;
  prediction_source: PredictionSource;
  predicted_class: number | null;
  predicted_label: string | null;
  probabilities: Record<string, number> | null;
  features_used: string[];
  model_name: string;
  model_version: string;
  prediction_note: string | null;
  warnings: string[];
}

export interface Readiness {
  status: "ready" | "partial" | "unavailable";
  mapped_features: string[];
  missing_features: string[];
  unsupported_features: string[];
  warnings: string[];
}
export interface PredictionReadiness {
  historical_model: Readiness;
  report_compatible_model: Readiness | null;
}

export interface Decision {
  priority: Priority;
  risk_level: Level;
  recommended_response_categories: string[];
  reasons: string[];
}

export interface Location {
  available: boolean;
  latitude: number | null;
  longitude: number | null;
  reason: string | null;
}

export interface ResourceRecommendation {
  resource_id: string;
  resource_type: string;
  resource_name: string;
  distance_km: number | null;
  availability: string;
  capabilities: string[];
  reason: string;
  demo_only: boolean;
}
export interface ResourceSearch {
  category: string;
  resource_available: boolean;
  reason: string | null;
  recommendations: ResourceRecommendation[];
}
export interface ResourcesSection {
  demo_only: true;
  notice: string;
  location: Location;
  searches: ResourceSearch[];
}

export interface Explanation {
  report_facts: string[];
  risk_reasons: string[];
  ml_reasons: string[];
  resource_reasons: string[];
}

export interface AnalyzeResponse {
  request_id: string;
  processing_time_ms: number;
  report: ReportMeta;
  incident: IncidentSummary;
  extracted_information: ExtractedInformation;
  evidence: EvidenceItem[];
  risk_indicators: RiskIndicator[];
  ml_prediction: MlPrediction;
  prediction_readiness: PredictionReadiness;
  decision: Decision;
  resources: ResourcesSection;
  explanation: Explanation;
  model_rule_disagreement: string | null;
  warnings: string[];
  human_oversight_required: true;
  disclaimer: string;
}

// ---------------------------------------------------------------- health / readiness

export interface ComponentHealth {
  status: "ok" | "available" | "unavailable";
  detail?: string | null;
}
export interface HealthResponse {
  status: "healthy" | "degraded" | "unavailable";
  service: string;
  version: string;
  environment: string;
  components: Record<string, ComponentHealth>;
}
export interface ReadinessResponse {
  status: "READY" | "NOT_READY";
  service: string;
  version: string;
  reasons: string[];
  components: Record<string, ComponentHealth>;
}

// ---------------------------------------------------------------- resources / models

export interface DemoResource {
  resource_id: string;
  resource_type: string;
  resource_name: string;
  latitude: number | null;
  longitude: number | null;
  availability_status: string;
  capacity: number | null;
  capabilities: string[];
  demo_only: boolean;
}
export interface ResourceCatalogResponse {
  demo_only: true;
  notice: string;
  count: number;
  resources: DemoResource[];
}
export interface ResourceFilters {
  resource_type?: string;
  availability_status?: string;
}

export interface ModelInfo {
  source_id: ModelSourceId;
  display_name: string;
  role: string;
  description: string;
  target: string;
  target_labels: Record<string, string>;
  available: boolean;
  model_type: string | null;
  feature_count: number;
  training_dataset: string;
  limitations: string[];
}
export interface ModelsResponse {
  models: ModelInfo[];
  routing: string;
}

export interface ClassMetrics {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}
export interface ModelEvaluation {
  estimator: string;
  accuracy: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  fatal_class_recall: number;
  test_rows: number;
  per_class: ClassMetrics[];
}
export interface ModelMetricsEntry {
  source_id: ModelSourceId;
  display_name: string;
  available: boolean;
  evaluation: ModelEvaluation | null;
}
export interface ModelMetricsResponse {
  models: ModelMetricsEntry[];
  evaluation_note: string;
}
