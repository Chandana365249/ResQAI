import { describe, expect, it, vi } from "vitest";
import { ApiError, analyzeReport, getModelMetrics, getReadiness, getResources } from "./index";
import { resolveApiBaseUrl } from "./http";
import { describeError } from "../lib/errors";
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

describe("production configuration", () => {
  it("never falls back to localhost in a production build without an API URL", () => {
    expect(resolveApiBaseUrl({ PROD: true, VITE_API_BASE_URL: undefined }, "http://127.0.0.1:8000")).toBeNull();
    expect(resolveApiBaseUrl({ PROD: true, VITE_API_BASE_URL: "   " }, "http://127.0.0.1:8000")).toBeNull();
  });

  it("falls back to the local backend only during development", () => {
    expect(resolveApiBaseUrl({ PROD: false, VITE_API_BASE_URL: undefined }, "http://127.0.0.1:8000")).toBe("http://127.0.0.1:8000");
  });

  it("uses the configured URL with any trailing slash removed", () => {
    expect(resolveApiBaseUrl({ PROD: true, VITE_API_BASE_URL: "https://api.example.test/" }, undefined)).toBe("https://api.example.test");
    expect(resolveApiBaseUrl({ PROD: false, VITE_API_BASE_URL: "https://api.example.test//" }, undefined)).toBe("https://api.example.test");
  });

  it("a production build with no API URL reports not_configured (not a network error) and sends nothing", async () => {
    // Regression: buildUrl used to run inside requestJson's try/catch, so this was mislabelled "network".
    vi.stubEnv("DEV", false);
    vi.stubEnv("PROD", true);
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.resetModules();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const { analyzeReport: freshAnalyze } = await import("./analyze");
    const { ApiError: FreshApiError } = await import("./http");
    const error = await freshAnalyze({ raw_text: "x" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(FreshApiError);
    expect((error as ApiError).kind).toBe("not_configured");
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("maps the not_configured error to an operator-facing message", () => {
    const result = describeError(new ApiError("not_configured", "x"));
    expect(result.title).toBe("Dashboard is not connected to a backend");
    expect(result.retryable).toBe(false);
  });
});
