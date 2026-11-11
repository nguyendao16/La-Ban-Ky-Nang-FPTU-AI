import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { api, ApiClient, ApiError } from "./api";
import { Recommendations } from "./components/Recommendations";
import { ComparisonView } from "./components/ComparisonView";
import { careerComparison, careerRadar, json, token } from "./test/fixtures";
import type { RecommendationsView } from "./types";
import { readWorkspace, saveWorkspace, type Workspace } from "./workspace";

const workspace: Workspace = {
  selectionId: "selection-1",
  sessionId: "session-1",
  token,
  keepInTab: true,
};
const idle: RecommendationsView = {
  session_id: "session-1",
  status: "not_requested",
  job: null,
  result: null,
  gaps: [],
};
const ready: RecommendationsView = {
  session_id: "session-1",
  status: "ready",
  job: { job_id: "rec-job" },
  result: {
    summary: "Các khóa có liên hệ với khoảng trống nội dung đã ghi nhận.",
    courses: [
      {
        title: "Data Practice",
        url: "https://www.coursera.org/learn/data-practice",
        provider: null,
        program_type: "course",
        duration: null,
        price: null,
        reason: "Mô tả sơ lược gợi ý nội dung thực hành xử lý dữ liệu.",
        gap_ids: ["gap-1"],
      },
    ],
  },
  gaps: [
    { gap_id: "gap-1", description: "Chưa thể hiện thực hành xử lý dữ liệu." },
  ],
};
function Harness({ initial = workspace }: { initial?: Workspace }) {
  const [current, setCurrent] = useState(initial);
  return (
    <Recommendations
      workspace={current}
      updateWorkspace={(next) => {
        saveWorkspace(next);
        setCurrent(next);
      }}
    />
  );
}

it("only reads on mount, then replays a lost response using the identical stored key", async () => {
  const read = vi
    .spyOn(api, "getRecommendations")
    .mockResolvedValueOnce(idle)
    .mockResolvedValue(ready);
  const create = vi
    .spyOn(api, "createRecommendations")
    .mockRejectedValueOnce(new ApiError("network_error"))
    .mockResolvedValue({ job_id: "rec-job", status: "queued" });
  render(<Harness />);
  const button = await screen.findByRole("button", {
    name: "Gợi ý khóa học",
  });
  expect(create).not.toHaveBeenCalled();
  await userEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Mất kết nối");
  const key = readWorkspace()!.recommendations!.key;
  expect(create).toHaveBeenCalledTimes(1);
  await userEvent.click(
    screen.getByRole("button", { name: "Thử lại cùng yêu cầu gợi ý" }),
  );
  await screen.findByRole("link", { name: "Data Practice" });
  expect(create.mock.calls[0].slice(0, 3)).toEqual(["session-1", token, key]);
  expect(create.mock.calls[1].slice(0, 3)).toEqual(
    create.mock.calls[0].slice(0, 3),
  );
  expect(readWorkspace()!.recommendations).toBeUndefined();
  expect(screen.getByText(/Thông tin từ kết quả tìm kiếm/)).toBeVisible();
  expect(
    screen.queryByText(/Giá:|Thời lượng:|Miễn phí|null/),
  ).not.toBeInTheDocument();
  expect(document.body.textContent).not.toContain(token);
  expect(read.mock.calls.length).toBeGreaterThanOrEqual(2);
});

it("reloads a committed set without POST, keeps nullable metadata, and opens gap details", async () => {
  vi.spyOn(api, "getRecommendations").mockResolvedValue(ready);
  const create = vi.spyOn(api, "createRecommendations");
  render(
    <Harness
      initial={{
        ...workspace,
        recommendations: { key: "unknown-response-key" },
      }}
    />,
  );
  const link = await screen.findByRole("link", { name: "Data Practice" });
  expect(link).toHaveAttribute("href", ready.result!.courses[0].url);
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  const summary = screen.getByText("Khoảng trống liên quan (1)");
  await userEvent.click(summary);
  expect(screen.getByText(ready.gaps[0].description)).toBeVisible();
  expect(create).not.toHaveBeenCalled();
  expect(readWorkspace()!.recommendations).toBeUndefined();
});

it("embeds saved Coursera citations and bare URLs as clickable links without searching again", async () => {
  const url = ready.result!.courses[0].url;
  vi.spyOn(api, "getRecommendations").mockResolvedValue({
    ...ready,
    result: {
      ...ready.result!,
      summary: `Nội dung liên quan ([coursera.org](${url}?utm_source=openai)).`,
      courses: [
        {
          ...ready.result!.courses[0],
          reason: `Xem [nội dung khóa học](${url}/#about) hoặc ${url}.`,
        },
      ],
    },
  });
  const create = vi.spyOn(api, "createRecommendations");
  render(<Harness />);
  await screen.findByRole("link", { name: "coursera.org" });
  for (const name of [
    "coursera.org",
    "nội dung khóa học",
    "Coursera",
    "Data Practice",
  ]) {
    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  }
  expect(document.body.textContent).toContain(
    "Nội dung liên quan (coursera.org).",
  );
  expect(document.body.textContent).toContain("hoặc Coursera.");
  expect(document.body.textContent).not.toContain("utm_source");
  expect(document.body.textContent).not.toContain("[coursera.org](");
  expect(create).not.toHaveBeenCalled();
});

it("keeps unapproved links and HTML as text instead of creating unsafe citations", async () => {
  vi.spyOn(api, "getRecommendations").mockResolvedValue({
    ...ready,
    result: {
      ...ready.result!,
      summary:
        "[Ngoài](https://coursera.org.evil.test/learn/data) [Khác](https://www.coursera.org/learn/not-saved)",
      courses: [
        {
          ...ready.result!.courses[0],
          reason:
            "[Mở](javascript:alert(1)) <img src=x onerror=alert(1)> [Giả](https://coursera.org@evil.test/learn/data)",
        },
      ],
    },
  });
  render(<Harness />);
  await screen.findByRole("link", { name: "Data Practice" });
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(document.querySelector("img")).toBeNull();
  expect(document.body.textContent).toContain("<img src=x onerror=alert(1)>");
});

it("pauses polling and resumes with GET without creating another operation", async () => {
  vi.useFakeTimers();
  const read = vi.spyOn(api, "getRecommendations").mockResolvedValue({
    ...idle,
    status: "processing",
    job: { job_id: "rec-job" },
  });
  const create = vi.spyOn(api, "createRecommendations");
  render(<Harness />);
  await act(async () => {});
  fireEvent.click(
    screen.getByRole("button", { name: "Tạm dừng theo dõi gợi ý" }),
  );
  const count = read.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15000);
  });
  expect(read).toHaveBeenCalledTimes(count);
  read.mockResolvedValue(ready);
  fireEvent.click(
    screen.getByRole("button", { name: "Tải lại trạng thái gợi ý" }),
  );
  await act(async () => {});
  expect(screen.getByRole("link", { name: "Data Practice" })).toBeVisible();
  expect(create).not.toHaveBeenCalled();
});

it("a terminal failure only refreshes status and does not offer a new inference", async () => {
  const read = vi.spyOn(api, "getRecommendations").mockResolvedValue({
    ...idle,
    status: "interrupted",
    job: { job_id: "rec-job", error_code: "remote_outcome_unknown" },
  });
  const create = vi.spyOn(api, "createRecommendations");
  render(<Harness />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "không tự tìm lại",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Tải lại trạng thái gợi ý" }),
  );
  await waitFor(() => expect(read.mock.calls.length).toBeGreaterThan(1));
  expect(create).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("button", { name: "Gợi ý khóa học" }),
  ).not.toBeInTheDocument();
});

it("accepts a saved empty set without filling the list or searching automatically", async () => {
  vi.spyOn(api, "getRecommendations").mockResolvedValue({
    ...ready,
    result: { summary: "Chưa tìm được khóa đủ phù hợp.", courses: [] },
  });
  const create = vi.spyOn(api, "createRecommendations");
  render(<Harness />);
  expect(
    await screen.findByText("Chưa có khóa học phù hợp để hiển thị."),
  ).toBeVisible();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(create).not.toHaveBeenCalled();
});

it("places recommendations immediately after summary/radar and before fixed axes and deeper analysis", async () => {
  render(
    <ComparisonView
      comparison={{ ...careerComparison, radar: careerRadar }}
      courseCount={15}
      recommendations={<Harness />}
    />,
  );
  await screen.findByRole("button", { name: "Gợi ý khóa học" });
  const summary = document.querySelector(".career-summary")!;
  const recommendations = document.querySelector(".recommendations-section")!;
  const axes = document.querySelector(".radar-details")!;
  const analysis = document.querySelector(".career-analysis")!;
  for (const [a, b] of [
    [summary, recommendations],
    [recommendations, axes],
    [axes, analysis],
  ])
    expect(
      a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
});

it("sends only the empty creation payload with capability and caller key; GET carries no write key", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(async () =>
      json({ job_id: "rec-job", status: "queued" }),
    );
  vi.stubGlobal("fetch", fetcher);
  const client = new ApiClient("http://offline.invalid");
  await client.createRecommendations("session/1", token, "stable-key");
  await client.getRecommendations("session/1", token);
  expect(fetcher.mock.calls[0][0]).toBe(
    "http://offline.invalid/api/v1/advisor/sessions/session%2F1/recommendations",
  );
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({});
  expect(fetcher.mock.calls[0][1].headers["Idempotency-Key"]).toBe(
    "stable-key",
  );
  expect(fetcher.mock.calls[1][1].headers["Idempotency-Key"]).toBeUndefined();
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
    `Bearer ${token}`,
  );
});

it("preserves a pending recommendation key in opt-in tab storage and rejects malformed keys", () => {
  saveWorkspace({ ...workspace, recommendations: { key: "stable-key" } });
  expect(readWorkspace()?.recommendations).toEqual({ key: "stable-key" });
  saveWorkspace({ ...workspace, recommendations: { key: "" } });
  expect(readWorkspace()).toBeNull();
});
