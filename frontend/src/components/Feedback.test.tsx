import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ApiError } from "../api";
import { ComparisonFailure, Feedback, canReplay } from "./Feedback";
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
it("shows a safe privacy failure without exposing detection details or enabling replay", () => {
  render(<ComparisonFailure code="private_policy_disclosure" />);
  expect(screen.getByRole("alert")).toHaveTextContent("bảo vệ dữ liệu");
  expect(screen.getByRole("alert")).not.toHaveTextContent(
    "private_policy_disclosure",
  );
  expect(canReplay(new ApiError("operation_failed", 502))).toBe(false);
});

it("explains a stored snapshot validation failure without claiming the reason is missing", () => {
  render(<ComparisonFailure code="storage_integrity_error" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Dữ liệu phiên");
  expect(screen.getByRole("alert")).toHaveTextContent("phiên bản API/worker");
  expect(screen.getByRole("alert")).not.toHaveTextContent(
    "chưa có nguyên nhân lỗi chi tiết",
  );
  expect(screen.getByRole("alert")).not.toHaveTextContent(
    "storage_integrity_error",
  );
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
