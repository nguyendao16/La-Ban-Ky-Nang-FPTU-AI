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
import { GradeForm } from "./components/GradeForm";
import { CourseSelection } from "./components/CourseSelection";
import {
  catalog,
  detail,
  json,
  profile,
  session,
  token,
} from "./test/fixtures";
import type { Turn } from "./types";
import { saveWorkspace } from "./workspace";

it("loads the catalog, allows normal courses, enforces single-choice COMBO and fetches actual categories", async () => {
  const user = userEvent.setup(),
    proceed = vi.fn();
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      const path = new URL(url).pathname;
      return path.endsWith("/courses")
        ? json(catalog)
        : json(detail(path.split("/").pop()!));
    }),
  );
  render(<CourseSelection onContinue={proceed} />);
  expect(screen.getByText("Đang tải catalog…")).toBeInTheDocument();
  await user.click(await screen.findByRole("checkbox", { name: /TEST101/ }));
  await user.click(screen.getByRole("checkbox", { name: /OTHER201/ }));
  expect(screen.getByRole("checkbox", { name: /UNAVAILABLE/ })).toBeDisabled();
  await user.selectOptions(screen.getByRole("combobox"), "COMBOA");
  await user.selectOptions(screen.getByRole("combobox"), "COMBOB");
  await user.click(screen.getByRole("button", { name: /Tiếp tục nhập điểm/ }));
  await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
  expect(
    proceed.mock.calls[0][1].map((c: { course_code: string }) => c.course_code),
  ).toEqual(["TEST101", "OTHER201", "COMBOB"]);
  expect(calls.filter((c) => c.includes("/courses/"))).toHaveLength(3);
});

it("rejects empty grades, accepts zero and presents server validation issues", async () => {
  const user = userEvent.setup(),
    created = vi.fn();
  const payloads: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url, options) => {
      payloads.push(JSON.parse(options.body));
      return payloads.length === 1
        ? json(
            {
              error: {
                code: "invalid_scores",
                details: [
                  {
                    course_code: "TEST101",
                    category: "Quiz 1",
                    issue: "duplicate_assessment_entry",
                  },
                ],
              },
            },
            422,
          )
        : json({ ...profile, access_token: token }, 201);
    }),
  );
  render(
    <GradeForm
      details={[detail("TEST101")]}
      curriculum="configured"
      onCreated={created}
      onBack={() => {}}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Tạo hồ sơ học thuật" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Nhập đủ điểm");
  expect(payloads).toHaveLength(0);
  await user.type(
    screen.getByRole("spinbutton", { name: "TEST101 · Quiz 1" }),
    "0",
  );
  await user.type(
    screen.getByRole("spinbutton", { name: "TEST101 · Final exam" }),
    "8",
  );
  await user.click(screen.getByRole("button", { name: "Tạo hồ sơ học thuật" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "duplicate_assessment_entry",
  );
  await user.click(screen.getByRole("button", { name: "Tạo hồ sơ học thuật" }));
  await waitFor(() => expect(created).toHaveBeenCalledOnce());
  expect(payloads[0]).toMatchObject({
    grades: [
      { category: "Quiz 1", grade: 0 },
      { category: "Final exam", grade: 8 },
    ],
  });
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
      if (path.endsWith("/profiles"))
        return json({ ...profile, access_token: token }, 201);
      if (path.includes("/profiles/")) return json(profile);
      if (path.endsWith("/advisor/sessions"))
        return json(
          {
            session_id: "session-1",
            status: "queued",
            review_job: { job_id: "job-1", status: "queued" },
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
            evidence: [{ course_code: "TEST101", clo: "CLO1" }],
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
  await user.click(screen.getByRole("button", { name: /Tiếp tục nhập điểm/ }));
  for (const input of await screen.findAllByRole("spinbutton"))
    await user.type(input, "0");
  await user.click(screen.getByRole("button", { name: "Tạo hồ sơ học thuật" }));
  expect(await screen.findByText(/Profile ID: profile-1/)).toBeInTheDocument();
  expect(screen.getByText("below_expected")).toBeInTheDocument();
  expect(sessionStorage.length).toBe(0);
  expect(document.body.textContent).not.toContain(token);
  await user.click(
    screen.getByRole("checkbox", { name: /Giữ phiên trong tab/ }),
  );
  await user.click(screen.getByRole("button", { name: /Phân tích JD/ }));
  await user.type(
    screen.getByRole("textbox", { name: "Job Description" }),
    "SQL",
  );
  await user.click(screen.getByRole("button", { name: "Tạo phiên phân tích" }));
  expect(
    await screen.findByText("Tổng quan học thuật từ backend."),
  ).toBeInTheDocument();
  expect(screen.getByText("not_evidenced")).toBeInTheDocument();
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
    (r) => r.path.includes("/advisor/") || r.path.includes("/profiles/"),
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
  expect(screen.getByText(/Session ID: session-1/)).toBeInTheDocument();
});

it("keeps the same JD payload/key on transport retry and blocks double submission", async () => {
  const user = userEvent.setup(),
    update = vi.fn();
  const creation = vi
    .spyOn(api, "createAdvisorSession")
    .mockRejectedValue(new ApiError("network_error"));
  const w = { profileId: profile.profile_id, token, keepInTab: false };
  const { rerender } = render(
    <AdvisorFlow
      profile={profile}
      workspace={w}
      updateWorkspace={update}
      onStep={() => {}}
    />,
  );
  await user.type(
    screen.getByRole("textbox", { name: "Job Description" }),
    "SQL JD",
  );
  await user.click(screen.getByRole("button", { name: "Tạo phiên phân tích" }));
  await screen.findByRole("alert");
  const pending = update.mock.calls[0][0];
  rerender(
    <AdvisorFlow
      profile={profile}
      workspace={pending}
      updateWorkspace={update}
      onStep={() => {}}
    />,
  );
  expect(screen.getByRole("textbox")).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Thử lại cùng JD" }));
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
      profile={profile}
      workspace={{
        profileId: "profile-1",
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
    screen.getByRole("heading", { name: "Đang chờ Review worker" }),
  ).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(config.pollInterval);
  });
  expect(
    screen.getByRole("heading", { name: "Đang phân tích học thuật" }),
  ).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(config.pollInterval);
  });
  expect(
    screen.getByText("Tổng quan học thuật từ backend."),
  ).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(config.pollInterval * 3);
  });
  expect(poll).toHaveBeenCalledTimes(3);
  view.unmount();
  await vi.advanceTimersByTimeAsync(config.pollInterval);
  expect(poll).toHaveBeenCalledTimes(3);
});

it.each(["failed", "interrupted"] as const)(
  "shows %s without automatically creating another Review",
  async (status) => {
    vi.spyOn(api, "getAdvisorSession").mockResolvedValue(session(status));
    const create = vi.spyOn(api, "createAdvisorSession");
    render(
      <AdvisorFlow
        profile={profile}
        workspace={{
          profileId: "profile-1",
          token,
          sessionId: "session-1",
          keepInTab: false,
        }}
        updateWorkspace={() => {}}
        onStep={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("operator");
    expect(create).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("textbox", { name: "Câu hỏi của bạn" }),
    ).not.toBeInTheDocument();
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
      profileId: "profile-1",
      token,
      sessionId: "session-1",
      keepInTab: false,
    };
    const view = render(
      <Chat profile={profile.profile} workspace={w} updateWorkspace={update} />,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Gửi câu hỏi" })).toBeEnabled(),
    );
    await user.type(screen.getByRole("textbox"), "SQL?");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    await screen.findByRole("alert");
    view.rerender(
      <Chat
        profile={profile.profile}
        workspace={update.mock.calls[0][0]}
        updateWorkspace={update}
      />,
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
      profile={profile.profile}
      workspace={{
        profileId: "profile-1",
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
      profile={profile}
      workspace={{
        profileId: "profile-1",
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

it("retries a restored profile read without creating another session or generation", async () => {
  saveWorkspace({
    profileId: "profile-1",
    token,
    sessionId: "session-1",
    keepInTab: true,
  });
  const get = vi
    .spyOn(api, "getProfile")
    .mockRejectedValueOnce(new ApiError("backend_unavailable", 503))
    .mockResolvedValue(profile);
  vi.spyOn(api, "getAdvisorSession").mockResolvedValue(session("ready"));
  vi.spyOn(api, "getChatHistory").mockResolvedValue({
    session_id: "session-1",
    turns: [],
  });
  const create = vi.spyOn(api, "createAdvisorSession"),
    chat = vi.spyOn(api, "sendChatMessage");
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Tải lại hồ sơ" }),
  );
  await screen.findByText("Tổng quan học thuật từ backend.");
  expect(get).toHaveBeenCalledTimes(2);
  expect(create).not.toHaveBeenCalled();
  expect(chat).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain(token);
});
