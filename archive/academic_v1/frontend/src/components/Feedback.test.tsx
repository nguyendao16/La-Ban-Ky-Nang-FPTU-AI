import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ApiError } from "../api";
import { Feedback, canReplay } from "./Feedback";
it.each([
  "unauthorized",
  "access_denied",
  "session_not_ready",
  "backend_unavailable",
  "invalid_request",
])("renders safe actionable %s errors", (code) => {
  render(<Feedback error={new ApiError(code, 403)} />);
  expect(screen.getByRole("alert")).toBeVisible();
  expect(screen.getByRole("alert")).not.toHaveTextContent("stack");
});
it("only permits replay of retrievable/ambiguous requests and blocks interrupted operations", () => {
  expect(canReplay(new ApiError("session_busy", 409))).toBe(true);
  expect(canReplay(new ApiError("operation_running", 409))).toBe(true);
  expect(canReplay(new ApiError("operation_interrupted", 409))).toBe(false);
  expect(canReplay(new ApiError("access_denied", 403))).toBe(false);
});
