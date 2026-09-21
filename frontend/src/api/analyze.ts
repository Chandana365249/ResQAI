import { requestJson } from "./http";
import type { AnalyzeRequest, AnalyzeResponse } from "./types";

export function analyzeReport(request: AnalyzeRequest, signal?: AbortSignal): Promise<AnalyzeResponse> {
  return requestJson<AnalyzeResponse>("/analyze", { method: "POST", body: request, signal });
}
