import { describe, expect, it, vi } from "vitest";
import { ApiError, analyzeReport, getModelMetrics, getReadiness, getResources } from "./index";
import { jsonResponse, stubFetch } from "../test/utils";
import { metricsFixture, serious, validationErrorFixture } from "../test/fixtures";

describe("API client", () => {
  it("returns typed data on success and posts JSON to /api/v1/analyze", async () => {
    const mock = stubFetch({ "/analyze": () => jsonResponse(serious) });
    const result = await analyzeReport({ raw_text: "A crash.", source: "dashboard" });

    expect(result.request_id).toBe(serious.request_id);
    const [url, init] = mock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/analyze$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ raw_text: "A crash.", source: "dashboard" });
  });

  it("converts a 422 validation error into an ApiError with field details", async () => {
    stubFetch({ "/analyze": () => jsonResponse(validationErrorFixture, 422) });
    const error = await analyzeReport({ raw_text: " " }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.kind).toBe("http");
    expect(apiError.status).toBe(422);
    expect(apiError.code).toBe("VALIDATION_ERROR");
    expect(apiError.details[0]?.field).toBe("raw_text");
    expect(apiError.requestId).toBeTruthy();
  });

  it("converts a 503 SERVICE_UNAVAILABLE into an ApiError", async () => {
    stubFetch({
      "/analyze": () => jsonResponse({ error: { code: "SERVICE_UNAVAILABLE", message: "down", request_id: "abc12345" } }, 503),
    });
    const error = (await analyzeReport({ raw_text: "x" }).catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(503);
    expect(error.code).toBe("SERVICE_UNAVAILABLE");
  });

  it("reports a network failure as kind=network without leaking the raw error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch: ECONNREFUSED 127.0.0.1")));
    const error = (await analyzeReport({ raw_text: "x" }).catch((e: unknown) => e)) as ApiError;
    expect(error.kind).toBe("network");
    expect(error.message).not.toMatch(/ECONNREFUSED|127\.0\.0\.1/);
  });

  it("reports a timeout as kind=timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit) => new Promise((_res, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      })),
    );
    const pending = getResources().catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(30_001);
    expect(((await pending) as ApiError).kind).toBe("timeout");
  });

  it("treats a non-JSON error body as a generic http error", async () => {
    stubFetch({ "/analyze": () => new Response("<html>Bad gateway</html>", { status: 502 }) });
    const error = (await analyzeReport({ raw_text: "x" }).catch((e: unknown) => e)) as ApiError;
    expect(error.kind).toBe("http");
    expect(error.status).toBe(502);
    expect(error.message).not.toContain("<html>");
  });

  it("reads /ready's NOT_READY body (HTTP 503) as data, not as a failure", async () => {
    const body = { status: "NOT_READY", service: "ResQAI", version: "0.1.0", reasons: ["x"], components: {} };
    stubFetch({ "/ready": () => jsonResponse(body, 503) });
    expect((await getReadiness()).status).toBe("NOT_READY");
  });

  it("sends resource filters as query parameters and omits empty ones", async () => {
    const mock = stubFetch({ "/resources": () => jsonResponse({}) });
    await getResources({ resource_type: "ambulance", availability_status: "" });
    const url = new URL((mock.mock.calls[0] as unknown as [string])[0]);
    expect(url.searchParams.get("resource_type")).toBe("ambulance");
    expect(url.searchParams.has("availability_status")).toBe(false);
  });

  it("fetches model metrics", async () => {
    stubFetch({ "/models/metrics": () => jsonResponse(metricsFixture) });
    const result = await getModelMetrics();
    expect(result.models).toHaveLength(2);
  });
});
