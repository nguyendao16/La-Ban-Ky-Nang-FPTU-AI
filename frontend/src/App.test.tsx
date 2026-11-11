import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "./App";
import { api, ApiError } from "./api";
import { config } from "./config";
import { AdvisorFlow } from "./components/AdvisorFlow";
import { Chat } from "./components/Chat";
import {
  catalog,
  detail,
  json,
  selection,
  session,
  token,
} from "./test/fixtures";
import type { Turn } from "./types";
import { saveWorkspace } from "./workspace";
it("reuses the saved CLO set for another JD without dispatching until submit", async () => {
  saveWorkspace({
    selectionId: selection.selection_id,
    token,
    sessionId: "session-1",
    keepInTab: true,
  });
  vi.spyOn(api, "getSelection").mockResolvedValue(selection);
  vi.spyOn(api, "getAdvisorSession").mockResolvedValue(session("ready"));
  vi.spyOn(api, "getChatHistory").mockResolvedValue({
    session_id: "session-1",
    turns: [],
  });
  const create = vi
    .spyOn(api, "createAdvisorSession")
    .mockRejectedValue(new ApiError("network_error"));
  render(<App />);
  await screen.findByText("Tổng quan so sánh từ backend.");
  await userEvent.click(
    screen.getByRole("button", { name: "So sánh mục tiêu khác" }),
  );
  await userEvent.click(
    screen.getByRole("tab", { name: "Mô tả công việc (JD)" }),
  );
  const jd = await screen.findByRole("textbox", { name: "Job Description" });
  expect(jd).toHaveValue("");
  expect(create).not.toHaveBeenCalled();
  await userEvent.type(jd, "Một JD khác");
  await userEvent.click(screen.getByRole("button", { name: "So sánh với JD" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0][0]).toEqual({
    selection_id: selection.selection_id,
    job_description: "Một JD khác",
  });
  expect(create.mock.calls[0][1]).toBe(token);
});
it("completes the HTTP UI journey, uses capabilities, shows persisted multi-turn history and restores the tab", async () => {
  const user = userEvent.setup(),
    turns: Turn[] = [],
    requests: Array<{ path: string; options: RequestInit }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      const path = new URL(url).pathname;
      requests.push({ path, options });
      if (path.endsWith("/health"))
        return json({ status: "ready", database: "ok" });
      if (path.endsWith("/courses")) return json(catalog);
      if (path.includes("/courses/")) return json(detail("TEST101"));
      if (path.endsWith("/selections"))
        return json({ ...selection, access_token: token }, 201);
      if (path.includes("/selections/")) return json(selection);
      if (path.endsWith("/advisor/sessions"))
        return json(
          {
            session_id: "session-1",
            status: "queued",
            comparison_job: { job_id: "job-1", status: "queued" },
          },
          202,
        );
      if (path.endsWith("/messages")) {
        if (options.method === "POST") {
          const message = JSON.parse(String(options.body)).message;
          const t = {
            message_id: `m-${turns.length}`,
            sequence: turns.length + 1,
            user_message: message,
            reply: `Phản hồi backend ${turns.length + 1}`,
            evidence: [{ course_code: "TEST101" }],
          };
          turns.push(t);
          return json(t);
        }
        return json({ session_id: "session-1", turns });
      }
      return json(session("ready"));
    }),
  );
  const view = render(<App />);
  await user.click(await screen.findByRole("checkbox", { name: /TEST101/ }));
  expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  expect(screen.queryByText(/CLO|enriched/i)).not.toBeInTheDocument();
  expect(sessionStorage.length).toBe(0);
  expect(document.body.textContent).not.toContain(token);
  await user.click(
    screen.getByRole("checkbox", { name: /Giữ phiên trong tab/ }),
  );
  await user.click(screen.getByRole("tab", { name: "Mô tả công việc (JD)" }));
  await user.type(
    screen.getByRole("textbox", { name: "Job Description" }),
    "SQL",
  );
  await user.click(screen.getByRole("button", { name: "So sánh với JD" }));
  expect(
    await screen.findByText("Tổng quan so sánh từ backend."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /SQL.*Chưa có bằng chứng đối chiếu/ }),
  ).toBeInTheDocument();
  for (const message of ["Câu hỏi một", "Câu hỏi hai"]) {
    await user.type(
      await screen.findByRole("textbox", { name: "Câu hỏi của bạn" }),
      message,
    );
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    await screen.findByText(`Phản hồi backend ${turns.length || 1}`);
  }
  await user.click(screen.getByRole("button", { name: "Tải lại lịch sử" }));
  expect(await screen.findByText("Câu hỏi hai")).toBeInTheDocument();
  const privateRequests = requests.filter(
    (r) => r.path.includes("/advisor/") || r.path.includes("/selections/"),
  );
  expect(
    privateRequests.every(
      (r) =>
        (r.options.headers as Record<string, string>).Authorization ===
        `Bearer ${token}`,
    ),
  ).toBe(true);
  const chatRequests = requests.filter(
    (r) => r.path.endsWith("/messages") && r.options.method === "POST",
  );
  expect(chatRequests).toHaveLength(2);
  expect(chatRequests[0].options.body).toBe(
    JSON.stringify({ message: "Câu hỏi một" }),
  );
  view.unmount();
  render(<App />);
  expect(await screen.findByText("Câu hỏi hai")).toBeInTheDocument();
  expect(screen.queryByText(/Session ID/)).not.toBeInTheDocument();
});

it("keeps the same JD payload/key on transport retry and blocks double submission", async () => {
  const user = userEvent.setup(),
    update = vi.fn();
  const creation = vi
    .spyOn(api, "createAdvisorSession")
    .mockRejectedValue(new ApiError("network_error"));
  const w = { selectionId: selection.selection_id, token, keepInTab: false };
  const { rerender } = render(
    <AdvisorFlow
      selection={selection}
      workspace={w}
      updateWorkspace={update}
      onStep={() => {}}
    />,
  );
  await user.click(screen.getByRole("tab", { name: "Mô tả công việc (JD)" }));
  await user.type(
    screen.getByRole("textbox", { name: "Job Description" }),
    "SQL JD",
  );
  await user.click(screen.getByRole("button", { name: "So sánh với JD" }));
  await screen.findByRole("alert");
  const pending = update.mock.calls[0][0];
  rerender(
    <AdvisorFlow
      selection={selection}
      workspace={pending}
      updateWorkspace={update}
      onStep={() => {}}
    />,
  );
  expect(screen.getByRole("textbox")).toBeDisabled();
  await user.click(
    screen.getByRole("button", { name: "Thử lại cùng yêu cầu" }),
  );
  expect(creation.mock.calls[1]).toEqual(creation.mock.calls[0]);
  expect(creation).toHaveBeenCalledTimes(2);
});

it("polls queued and processing then stops at ready; unmount cancels polling", async () => {
  vi.useFakeTimers();
  const poll = vi
    .spyOn(api, "getAdvisorSession")
    .mockResolvedValueOnce(session("queued"))
    .mockResolvedValueOnce(session("processing"))
    .mockResolvedValue(session("ready"));
  vi.spyOn(api, "getChatHistory").mockResolvedValue({
    session_id: "session-1",
    turns: [],
  });
  const view = render(
    <AdvisorFlow
      selection={selection}
      workspace={{
        selectionId: "selection-1",
        token,
        sessionId: "session-1",
        keepInTab: false,
      }}
      updateWorkspace={() => {}}
      onStep={vi.fn()}
    />,
  );
  await act(async () => {});
  expect(
    screen.getByRole("heading", { name: "Đang chờ worker so sánh" }),
  ).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(config.pollInterval);
  });
  expect(
    screen.getByRole("heading", { name: "Đang đối chiếu nội dung môn học" }),
  ).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(config.pollInterval);
  });
  expect(screen.getByText("Tổng quan so sánh từ backend.")).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(config.pollInterval * 3);
  });
  expect(poll).toHaveBeenCalledTimes(3);
  view.unmount();
  await vi.advanceTimersByTimeAsync(config.pollInterval);
  expect(poll).toHaveBeenCalledTimes(3);
});

it.each(["failed", "interrupted"] as const)(
  "shows %s without automatically creating another Comparison",
  async (status) => {
    const poll = vi
      .spyOn(api, "getAdvisorSession")
      .mockResolvedValue(session(status));
    const create = vi.spyOn(api, "createAdvisorSession");
    render(
      <AdvisorFlow
        selection={selection}
        workspace={{
          selectionId: "selection-1",
          token,
          sessionId: "session-1",
          keepInTab: false,
        }}
        updateWorkspace={() => {}}
        onStep={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("operator");
    await userEvent.click(
      screen.getByRole("button", { name: "Tải lại trạng thái" }),
    );
    await waitFor(() => expect(poll).toHaveBeenCalledTimes(2));
    expect(create).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("textbox", { name: "Câu hỏi của bạn" }),
    ).not.toBeInTheDocument();
  },
);

it.each([
  ["model_output_limit", "giới hạn độ dài phản hồi"],
  ["invalid_evidence", "Dẫn chứng trong kết quả phân tích chưa hợp lệ"],
  ["quota_exhausted", "hết hạn mức sử dụng"],
  ["untrusted-provider-text", "chưa có nguyên nhân lỗi chi tiết"],
])(
  "explains a failed JD with safe reason %s and keeps reload read-only",
  async (code, message) => {
    const failed = session("failed");
    vi.spyOn(api, "getAdvisorSession").mockResolvedValue({
      ...failed,
      comparison_job: {
        ...failed.comparison_job,
        error_code: code,
        error_message: "sk-untrusted-server-payload",
      },
    });
    const create = vi.spyOn(api, "createAdvisorSession");
    render(
      <AdvisorFlow
        selection={selection}
        workspace={{
          selectionId: selection.selection_id,
          token,
          sessionId: "session-1",
          keepInTab: false,
        }}
        updateWorkspace={() => {}}
        onStep={vi.fn()}
      />,
    );
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveTextContent(
      "Tải lại trạng thái chỉ kiểm tra phiên hiện tại",
    );
    expect(document.body.textContent).not.toContain(
      "sk-untrusted-server-payload",
    );
    expect(document.body.textContent).not.toContain("untrusted-provider-text");
    expect(create).not.toHaveBeenCalled();
  },
);

it.each(["transport_timeout", "operation_running", "session_busy"])(
  "retains Chat payload/key after %s and disables ambiguous interrupted operations",
  async (code) => {
    const user = userEvent.setup(),
      update = vi.fn();
    vi.spyOn(api, "getChatHistory").mockResolvedValue({
      session_id: "session-1",
      turns: [],
    });
    const send = vi
      .spyOn(api, "sendChatMessage")
      .mockRejectedValueOnce(new ApiError(code))
      .mockRejectedValue(new ApiError("operation_interrupted", 409));
    const w = {
      selectionId: "selection-1",
      token,
      sessionId: "session-1",
      keepInTab: false,
    };
    const view = render(<Chat workspace={w} updateWorkspace={update} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Gửi câu hỏi" })).toBeEnabled(),
    );
    await user.type(screen.getByRole("textbox"), "SQL?");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    await screen.findByRole("alert");
    view.rerender(
      <Chat workspace={update.mock.calls[0][0]} updateWorkspace={update} />,
    );
    await user.click(
      screen.getByRole("button", { name: "Thử lại cùng câu hỏi" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Thử lại cùng câu hỏi" }),
      ).toBeDisabled(),
    );
    expect(send.mock.calls[1].slice(0, 4)).toEqual(
      send.mock.calls[0].slice(0, 4),
    );
    expect(screen.queryByText("Phản hồi backend")).not.toBeInTheDocument();
  },
);

it("prevents rapid duplicate Chat while the first request is unresolved", async () => {
  vi.spyOn(api, "getChatHistory").mockResolvedValue({
    session_id: "session-1",
    turns: [],
  });
  const send = vi
    .spyOn(api, "sendChatMessage")
    .mockImplementation(() => new Promise(() => {}));
  render(
    <Chat
      workspace={{
        selectionId: "selection-1",
        token,
        sessionId: "session-1",
        keepInTab: false,
      }}
      updateWorkspace={() => {}}
    />,
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Gửi câu hỏi" })).toBeEnabled(),
  );
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "SQL?" } });
  fireEvent.submit(screen.getByRole("textbox").closest("form")!);
  fireEvent.submit(screen.getByRole("textbox").closest("form")!);
  expect(send).toHaveBeenCalledOnce();
});

it("cancels an active queued polling loop when leaving the screen", async () => {
  vi.useFakeTimers();
  const poll = vi
    .spyOn(api, "getAdvisorSession")
    .mockResolvedValue(session("queued"));
  const view = render(
    <AdvisorFlow
      selection={selection}
      workspace={{
        selectionId: "selection-1",
        token,
        sessionId: "session-1",
        keepInTab: false,
      }}
      updateWorkspace={() => {}}
      onStep={vi.fn()}
    />,
  );
  await act(async () => {});
  expect(poll).toHaveBeenCalledOnce();
  const signal = poll.mock.calls[0][2];
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await vi.advanceTimersByTimeAsync(config.pollInterval * 3);
  expect(poll).toHaveBeenCalledOnce();
});

it("retries a restored selection read without creating another session or generation", async () => {
  saveWorkspace({
    selectionId: "selection-1",
    token,
    sessionId: "session-1",
    keepInTab: true,
  });
  const get = vi
    .spyOn(api, "getSelection")
    .mockRejectedValueOnce(new ApiError("backend_unavailable", 503))
    .mockResolvedValue(selection);
  vi.spyOn(api, "getAdvisorSession").mockResolvedValue(session("ready"));
  vi.spyOn(api, "getChatHistory").mockResolvedValue({
    session_id: "session-1",
    turns: [],
  });
  const create = vi.spyOn(api, "createAdvisorSession"),
    chat = vi.spyOn(api, "sendChatMessage");
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Khôi phục phiên" }),
  );
  await screen.findByText("Tổng quan so sánh từ backend.");
  expect(get).toHaveBeenCalledTimes(2);
  expect(create).not.toHaveBeenCalled();
  expect(chat).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain(token);
});
