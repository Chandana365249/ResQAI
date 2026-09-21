import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { clearQueryCache } from "../state/useCachedQuery";

// jsdom has no ResizeObserver, which the charting library needs to size charts.
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

afterEach(() => {
  cleanup();
  localStorage.clear();
  clearQueryCache();
  vi.unstubAllGlobals();
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.useRealTimers();
});
