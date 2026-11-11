import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { StrictMode, useState } from "react";
import App from "./App";
import { api, ApiError } from "./api";
import { TargetInput } from "./components/TargetInput";
import { config } from "./config";
import { targetDraft } from "./target";
import { readWorkspace, saveWorkspace } from "./workspace";
import {
  catalog,
  careerProfiles,
  careerComparison,
  selection,
  session,
  token,
} from "./test/fixtures";

function prepare() {
  vi.spyOn(api, "listCourses").mockResolvedValue(catalog);
  vi.spyOn(api, "listCareerProfiles").mockResolvedValue({
    profiles: careerProfiles,
  });
}

it("offers eight career targets, accepts one explicit target and renders analysis without coverage labels", async () => {
  prepare();
  const user = userEvent.setup();
  const createSelection = vi
    .spyOn(api, "createSelection")
    .mockResolvedValue({ ...selection, access_token: token });
  const create = vi.spyOn(api, "createAdvisorSession").mockResolvedValue({
    session_id: "session-1",
    status: "queued",
    comparison_job: { job_id: "job-1", status: "queued" },
  });
  vi.spyOn(api, "getAdvisorSession").mockResolvedValue({
    ...session("ready"),
    target: { type: "cwa", career_profile: careerProfiles[0] },
    comparison: careerComparison,
  });
  vi.spyOn(api, "getChatHistory").mockResolvedValue({
    session_id: "session-1",
    turns: [],
  });
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  expect(
    await screen.findByRole("tab", { name: "Nhóm nghề CWA" }),
  ).toHaveAttribute("aria-selected", "true");
  expect(
    screen.queryByRole("textbox", { name: "Job Description" }),
  ).not.toBeInTheDocument();
  const select = await screen.findByRole("combobox", {
    name: "Nhóm nghề mục tiêu",
  });
  expect(screen.getAllByRole("option")).toHaveLength(9);
  expect(
    screen.getByRole("option", {
      name: "Computer Vision Engineer",
    }),
  ).toHaveValue("computer-vision-engineer");
  expect(
    screen.getByRole("option", { name: "NLP / LLM Engineer" }),
  ).toHaveValue("nlp-llm-engineer");
  await user.click(screen.getByRole("checkbox", { name: /TEST101/ }));
  await user.click(screen.getByRole("button", { name: "Khám phá nhóm nghề" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Chọn nhóm nghề");
  expect(createSelection).not.toHaveBeenCalled();
  await user.selectOptions(select, "data-scientist");
  await user.click(screen.getByText("Xem mô tả nhóm nghề"));
  expect(screen.getByText("Mô tả Data Scientist")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Khám phá nhóm nghề" }));
  await screen.findByText(careerComparison.overview);
  expect(create).toHaveBeenCalledOnce();
  expect(create.mock.calls[0].slice(0, 2)).toEqual([
    {
      selection_id: selection.selection_id,
      career_profile_id: "data-scientist",
    },
    token,
  ]);
  expect(
    screen.getByRole("heading", { name: "Khoảng trống nội dung" }),
  ).toBeVisible();
  expect(
    screen.queryByText(
      /Được bao phủ|Chưa có bằng chứng đối chiếu|CLO|enriched|%/,
    ),
  ).not.toBeInTheDocument();
  expect(document.body.textContent).not.toContain(token);
  expect(sessionStorage.length).toBe(0);
});

it("restores a frozen career operation and manually replays the exact payload/key after transport loss", async () => {
  prepare();
  const payload = {
    selection_id: selection.selection_id,
    career_profile_id: "data-analyst",
  };
  saveWorkspace({
    selectionId: selection.selection_id,
    token,
    keepInTab: true,
    mode: "cwa",
    creation: { key: "career-stable-key", payload },
  });
  vi.spyOn(api, "getSelection").mockResolvedValue(selection);
  const create = vi
    .spyOn(api, "createAdvisorSession")
    .mockRejectedValue(new ApiError("network_error"));
  render(<App />);
  const select = await screen.findByRole("combobox", {
    name: "Nhóm nghề mục tiêu",
  });
  expect(select).toHaveValue("data-analyst");
  expect(select).toBeDisabled();
  expect(
    screen.getByRole("tab", { name: "Mô tả công việc (JD)" }),
  ).toBeDisabled();
  expect(create).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "Thử lại cùng yêu cầu" }),
  );
  await screen.findByRole("alert");
  await userEvent.click(
    screen.getByRole("button", { name: "Thử lại cùng yêu cầu" }),
  );
  expect(create).toHaveBeenCalledTimes(2);
  expect(create.mock.calls[0]).toEqual([payload, token, "career-stable-key"]);
  expect(create.mock.calls[1]).toEqual(create.mock.calls[0]);
  expect(readWorkspace()?.creation).toEqual({
    key: "career-stable-key",
    payload,
  });
});

it("supports keyboard tabs, preserves drafts, and retries catalog reads without creating an operation", async () => {
  const list = vi
    .spyOn(api, "listCareerProfiles")
    .mockRejectedValueOnce(new ApiError("backend_unavailable", 503))
    .mockResolvedValue({ profiles: careerProfiles });
  const create = vi.spyOn(api, "createAdvisorSession");
  function Form() {
    const [value, setValue] = useState(targetDraft());
    return <TargetInput value={value} onChange={setValue} />;
  }
  render(<Form />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Tải lại nhóm nghề" }),
  );
  await screen.findByRole("combobox");
  expect(list).toHaveBeenCalledTimes(2);
  const cwa = screen.getByRole("tab", { name: "Nhóm nghề CWA" });
  cwa.focus();
  fireEvent.keyDown(cwa, { key: "ArrowRight" });
  const jd = screen.getByRole("tab", { name: "Mô tả công việc (JD)" });
  expect(jd).toHaveFocus();
  await userEvent.type(screen.getByRole("textbox"), "JD draft");
  fireEvent.keyDown(jd, { key: "Home" });
  expect(cwa).toHaveFocus();
  await userEvent.selectOptions(screen.getByRole("combobox"), "mlops-engineer");
  fireEvent.keyDown(cwa, { key: "End" });
  expect(screen.getByRole("textbox")).toHaveValue("JD draft");
  fireEvent.keyDown(jd, { key: "ArrowLeft" });
  expect(screen.getByRole("combobox")).toHaveValue("mlops-engineer");
  expect(create).not.toHaveBeenCalled();
});

it("rejects restored ambiguous mixed-target payloads", () => {
  sessionStorage.setItem(
    "skillbridge.course-jd.workspace.v1",
    JSON.stringify({
      baseUrl: config.baseUrl,
      workspace: {
        selectionId: "s",
        token,
        keepInTab: true,
        creation: {
          key: "x",
          payload: {
            selection_id: "s",
            job_description: "SQL",
            career_profile_id: "data-analyst",
          },
        },
      },
    }),
  );
  expect(readWorkspace()).toBeNull();
});
