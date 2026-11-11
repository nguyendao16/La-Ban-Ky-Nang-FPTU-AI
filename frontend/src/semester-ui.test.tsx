import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { expect, it, vi } from "vitest";
import App from "./App";
import { api, ApiError } from "./api";
import { catalog, selection, token } from "./test/fixtures";
import { saveWorkspace } from "./workspace";

it("shows mixed group selection, fills previous semesters and cascades deselection", async () => {
  vi.spyOn(api, "listCourses").mockResolvedValue(catalog);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("checkbox", { name: /TEST101/ }),
  );
  expect(
    screen.getByRole("checkbox", { name: "Chọn học kỳ 1" }),
  ).toBePartiallyChecked();
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Chọn học kỳ 3" }),
  );
  for (const semester of [1, 2, 3])
    expect(
      screen.getByRole("checkbox", { name: `Chọn học kỳ ${semester}` }),
    ).toBeChecked();
  await userEvent.click(screen.getByRole("checkbox", { name: /OTHER201/ }));
  expect(screen.getByRole("checkbox", { name: /TEST101/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /LATE301/ })).not.toBeChecked();
});
it("replaces track courses through all nine semesters, with no unavailable-course warnings", async () => {
  vi.spyOn(api, "listCourses").mockResolvedValue(catalog);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("radio", { name: "Applied Data Science" }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Chọn học kỳ 9" }),
  );
  await userEvent.click(screen.getByRole("radio", { name: "AI application" }));
  expect(
    screen.queryByRole("checkbox", { name: /COMBOA/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: /COMBOB/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /EXTRA/ })).toBeEnabled();
  for (let n = 1; n <= 9; n++)
    expect(
      screen.getByRole("checkbox", { name: `Chọn học kỳ ${n}` }),
    ).toBeChecked();
  expect(
    screen.queryByText(/chưa có dữ liệu|không tham gia|CLO|enriched/i),
  ).not.toBeInTheDocument();
});
it("submits once under StrictMode without fetching definitions or confirming sources", async () => {
  vi.spyOn(api, "listCourses").mockResolvedValue(catalog);
  const details = vi.spyOn(api, "getCourse");
  const create = vi
    .spyOn(api, "createSelection")
    .mockResolvedValue({ ...selection, access_token: token });
  const session = vi
    .spyOn(api, "createAdvisorSession")
    .mockRejectedValue(new ApiError("network_error"));
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  await userEvent.click(
    await screen.findByRole("checkbox", { name: /LATE301/ }),
  );
  await userEvent.click(
    screen.getByRole("tab", { name: "Mô tả công việc (JD)" }),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Job Description" }), {
    target: { value: "SQL" },
  });
  act(() => {
    fireEvent.submit(
      screen.getByRole("textbox", { name: "Job Description" }).closest("form")!,
    );
    fireEvent.submit(
      screen.getByRole("textbox", { name: "Job Description" }).closest("form")!,
    );
  });
  await waitFor(() => expect(session).toHaveBeenCalledOnce());
  expect(create).toHaveBeenCalledExactlyOnceWith({
    curriculum_code: "configured",
    selected_courses: ["TEST101", "OTHER201", "MID201", "LATE301"],
  });
  expect(details).not.toHaveBeenCalled();
  await screen.findByRole("alert");
  expect(session).toHaveBeenCalledOnce();
});
it("restores ambiguous creation without automatically posting again", async () => {
  saveWorkspace({
    selectionId: selection.selection_id,
    token,
    keepInTab: true,
    creation: {
      key: "stable-key",
      payload: {
        selection_id: selection.selection_id,
        job_description: "Frozen JD",
      },
    },
  });
  vi.spyOn(api, "getSelection").mockResolvedValue(selection);
  const post = vi
    .spyOn(api, "createAdvisorSession")
    .mockRejectedValue(new ApiError("network_error"));
  render(<App />);
  expect(
    await screen.findByRole("textbox", { name: "Job Description" }),
  ).toHaveValue("Frozen JD");
  expect(post).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "Thử lại cùng yêu cầu" }),
  );
  expect(post).toHaveBeenCalledOnce();
  expect(post.mock.calls[0][2]).toBe("stable-key");
});
