import { requestJson } from "./http";
import type { HealthResponse, ReadinessResponse } from "./types";

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/health", { signal });
}

/** /ready answers 503 with a valid NOT_READY body; that body is data, not a failure. */
export function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return requestJson<ReadinessResponse>("/ready", { signal, acceptStatuses: [503] });
}
