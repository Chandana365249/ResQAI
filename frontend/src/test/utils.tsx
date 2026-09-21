import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { AnalyzeRequest, AnalyzeResponse, HealthResponse, ReadinessResponse } from "../api";
import { AnalysisProvider } from "../state/AnalysisContext";
import { SystemStatusProvider } from "../state/SystemStatusContext";
import { healthFixture, readyFixture } from "./fixtures";

interface RenderOptions {
  route?: string;
  analyze?: (request: AnalyzeRequest) => Promise<AnalyzeResponse>;
  fetchHealth?: () => Promise<HealthResponse>;
  fetchReadiness?: () => Promise<ReadinessResponse>;
}

/** Renders UI inside the same providers as the real app, with injectable API calls. */
export function renderWithProviders(ui: ReactElement, options: RenderOptions = {}) {
  const {
    route = "/",
    analyze = () => Promise.reject(new Error("analyze was not expected to be called")),
    fetchHealth = () => Promise.resolve(healthFixture),
    fetchReadiness = () => Promise.resolve(readyFixture),
  } = options;
  return render(
    <MemoryRouter initialEntries={[route]}>
      <SystemStatusProvider fetchHealth={fetchHealth} fetchReadiness={fetchReadiness}>
        <AnalysisProvider analyze={analyze}>{ui}</AnalysisProvider>
      </SystemStatusProvider>
    </MemoryRouter>,
  );
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * Stubs global fetch with a path->response table (paths relative to /api/v1).
 * Any unlisted path fails loudly so a test can never silently hit the network.
 */
export function stubFetch(routes: Record<string, () => Response | Promise<Response>>) {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    const key = url.pathname.replace(/^\/api\/v1/, "") + url.search;
    const handler = routes[key] ?? routes[url.pathname.replace(/^\/api\/v1/, "")];
    if (!handler) throw new TypeError(`Unexpected fetch in test: ${key}`);
    return handler();
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
