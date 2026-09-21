import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup, configure } from "@testing-library/react";
import { clearQueryCache } from "../state/useCachedQuery";

// findBy*/waitFor default to 1 s; lazy chunks and real network calls need more headroom.
configure({ asyncUtilTimeout: 5000 });

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
