/**
 * REAL responses captured from the running FastAPI backend (see
 * docs/FRONTEND.md, "Test fixtures"). They are JSON files exactly as the API
 * returned them, cast to the API types; nothing here was written by hand.
 */

import type {
  AnalyzeResponse, ErrorResponse, HealthResponse, ModelMetricsResponse, ModelsResponse,
  ReadinessResponse, ResourceCatalogResponse,
} from "../../api";
import analyzeSerious from "./analyze-serious.json";
import analyzeDisagreement from "./analyze-disagreement.json";
import analyzeNoPrediction from "./analyze-no-prediction.json";
import analyzeHazmat from "./analyze-hazmat.json";
import health from "./health.json";
import ready from "./ready.json";
import resources from "./resources.json";
import models from "./models.json";
import modelsMetrics from "./models-metrics.json";
import errorValidation from "./error-validation.json";

export const serious = analyzeSerious as unknown as AnalyzeResponse;
export const disagreement = analyzeDisagreement as unknown as AnalyzeResponse;
export const noPrediction = analyzeNoPrediction as unknown as AnalyzeResponse;
export const hazmat = analyzeHazmat as unknown as AnalyzeResponse;
export const healthFixture = health as unknown as HealthResponse;
export const readyFixture = ready as unknown as ReadinessResponse;
export const resourcesFixture = resources as unknown as ResourceCatalogResponse;
export const modelsFixture = models as unknown as ModelsResponse;
export const metricsFixture = modelsMetrics as unknown as ModelMetricsResponse;
export const validationErrorFixture = errorValidation as unknown as ErrorResponse;
