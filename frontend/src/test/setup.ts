import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { api } from "../api";
beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("Unexpected HTTP in offline test"))),
  );
  vi.spyOn(api, "getRecommendations").mockImplementation(async (id) => ({
    session_id: id,
    status: "not_requested",
    job: null,
    result: null,
    gaps: [],
  }));
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
