import { requestJson } from "./http";
import type { ModelMetricsResponse, ModelsResponse } from "./types";

export function getModels(signal?: AbortSignal): Promise<ModelsResponse> {
  return requestJson<ModelsResponse>("/models", { signal });
}

export function getModelMetrics(signal?: AbortSignal): Promise<ModelMetricsResponse> {
  return requestJson<ModelMetricsResponse>("/models/metrics", { signal });
}
