import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ComparisonView } from "./components/ComparisonView";
import {
  careerComparison,
  comparison,
  longCareerComparison,
} from "./test/fixtures";

it("puts the existing conclusion first, uses the selection count and retains overview only in details", () => {
  const { container } = render(
    <ComparisonView
      comparison={careerComparison}
      careerTitle="Data Analyst"
      courseCount={37}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Kết quả đối chiếu với nhóm nghề" }),
  ).toHaveFocus();
  const summary = container.querySelector(".career-summary")!;
  expect(summary).toHaveTextContent("Data Analyst");
  expect(summary).toHaveTextContent("37 môn đã chọn");
  expect(
    within(summary as HTMLElement).getByText(careerComparison.conclusion),
  ).toBeVisible();
  expect(screen.getAllByText(careerComparison.conclusion)).toHaveLength(1);
  expect(summary).not.toHaveTextContent(careerComparison.overview);
  expect(screen.getByText(careerComparison.overview)).not.toBeVisible();
  expect(
    [...container.querySelector(".career-results")!.children].map(
      (n) => n.className,
    ),
  ).toEqual(["career-summary", "radar-details", "career-analysis"]);
  expect(
    container.querySelectorAll(".career-analysis details[open]"),
  ).toHaveLength(0);
  expect(
    screen.queryByRole("button", { name: "Đọc đầy đủ" }),
  ).not.toBeInTheDocument();
});

it("shows every summary title and the full conclusion immediately, and opens/focuses the matching detail", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ComparisonView
      comparison={longCareerComparison}
      careerTitle="Data Scientist"
      courseCount={17}
    />,
  );
  const summary = container.querySelector(".career-summary") as HTMLElement;
  expect(
    within(summary).getAllByRole("button", { name: /^Nhóm nội dung/ }),
  ).toHaveLength(12);
  expect(
    within(summary).getAllByRole("button", { name: /^Khoảng trống/ }),
  ).toHaveLength(7);
  expect(
    within(summary).queryByRole("button", {
      name: /Xem thêm|Đọc đầy đủ|Thu gọn/,
    }),
  ).not.toBeInTheDocument();
  expect(
    within(summary).getByText(longCareerComparison.conclusion).textContent,
  ).toBe(longCareerComparison.conclusion);
  const target = longCareerComparison.related_content[10];
  await user.click(within(summary).getByRole("button", { name: target.title }));
  const detail = screen
    .getByText(target.comment, { normalizer: (text) => text })
    .closest("details")!;
  expect(detail).toHaveAttribute("open");
  expect(detail.querySelector("summary")).toHaveFocus();
  expect(
    screen.getByText(target.comment, { normalizer: (text) => text }),
  ).toBeVisible();
  expect(within(detail).getAllByText("COMMON101").length).toBeGreaterThan(0);
});

it("opens and closes all analysis including context without changing the prose or making requests", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ComparisonView
      comparison={longCareerComparison}
      careerTitle="Data Scientist"
      courseCount={17}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Mở tất cả" }));
  expect(
    container.querySelectorAll(".career-analysis details[open]"),
  ).toHaveLength(20);
  for (const finding of [
    ...longCareerComparison.related_content,
    ...longCareerComparison.gaps,
  ]) {
    expect(
      screen.getByText(finding.comment, { normalizer: (text) => text }),
    ).toBeVisible();
    expect(
      screen.getByText(finding.comment, { normalizer: (text) => text })
        .textContent,
    ).toBe(finding.comment);
  }
  expect(screen.getByText(longCareerComparison.overview)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Thu gọn tất cả" }));
  expect(
    container.querySelectorAll(".career-analysis details[open]"),
  ).toHaveLength(0);
  expect(screen.getByText(longCareerComparison.conclusion).textContent).toBe(
    longCareerComparison.conclusion,
  );
  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
});

it("removes the reference chart while preserving every course reference in the analysis", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ComparisonView
      comparison={longCareerComparison}
      careerTitle="Data Scientist"
      courseCount={17}
    />,
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByText("GÓC NHÌN TỪ DẪN CHỨNG")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Môn học được tham chiếu" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Mở tất cả" }));
  const analysis = container.querySelector(".career-analysis") as HTMLElement;
  expect(within(analysis).getAllByText("COMMON101")).toHaveLength(12);
  expect(within(analysis).getByText("COURSE12")).toBeVisible();
  expect(within(analysis).getAllByText("GAP999")).toHaveLength(7);
  expect(document.body.textContent).not.toMatch(
    /%|covered|Career Task Coverage/,
  );
});

it("does not interpret empty findings or gap-only evidence as good coverage or a score", () => {
  render(
    <ComparisonView
      comparison={{
        ...careerComparison,
        related_content: [],
        gaps: [
          {
            title: "Giới hạn",
            comment: "Chưa đủ thông tin.",
            evidence: [{ course_code: "GAP999" }],
          },
        ],
      }}
      careerTitle="AI Researcher"
      courseCount={1}
    />,
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(
    screen.getAllByText("Kết quả chưa ghi nhận mục nào trong nhóm này.")[0],
  ).toBeVisible();
  expect(document.body.textContent).not.toMatch(
    /0%|100%|không có khoảng trống|đào tạo tốt/i,
  );
});

it("preserves separate details when the model repeats a title", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ComparisonView
      comparison={{
        ...careerComparison,
        related_content: [
          {
            ...careerComparison.related_content[0],
            title: "Cùng tiêu đề",
            comment: "Phân tích thứ nhất.",
          },
          {
            ...careerComparison.related_content[0],
            title: "Cùng tiêu đề",
            comment: "Phân tích thứ hai.",
          },
        ],
      }}
      careerTitle="Data Analyst"
      courseCount={2}
    />,
  );
  await user.click(
    within(
      container.querySelector(".career-summary") as HTMLElement,
    ).getAllByRole("button", { name: "Cùng tiêu đề" })[1],
  );
  expect(screen.getByText("Phân tích thứ hai.")).toBeVisible();
  expect(screen.getByText("Phân tích thứ nhất.")).not.toBeVisible();
});

it("uses the shared summary-first layout for legacy JD results", async () => {
  render(<ComparisonView comparison={comparison} courseCount={1} />);
  expect(
    screen.getByRole("heading", { name: "Kết quả đối chiếu với JD" }),
  ).toBeVisible();
  expect(screen.getByText(comparison.conclusion)).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Nhận định tổng quan" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Kết luận" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(comparison.overview)).not.toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Mở tất cả" }));
  expect(screen.getByText(comparison.overview)).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
