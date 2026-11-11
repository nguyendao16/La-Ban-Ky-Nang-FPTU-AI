import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ComparisonView } from "./components/ComparisonView";
import { longJDComparison } from "./test/fixtures";

it("shows the full JD conclusion and all requirement titles before independent radar and expanded axes", () => {
  const { container } = render(
    <ComparisonView comparison={longJDComparison} courseCount={23} />,
  );
  const summary = container.querySelector(".career-summary") as HTMLElement;
  expect(
    screen.getByRole("heading", { name: "Kết quả đối chiếu với JD" }),
  ).toHaveFocus();
  expect(summary).toHaveTextContent("23 môn đã chọn");
  expect(
    within(summary).getByText(longJDComparison.conclusion, {
      normalizer: (text) => text,
    }).textContent,
  ).toBe(longJDComparison.conclusion);
  expect(within(summary).getAllByRole("button")).toHaveLength(12);
  expect(
    within(summary).queryByRole("button", { name: /Đọc đầy đủ|Xem thêm/ }),
  ).not.toBeInTheDocument();
  expect(summary).not.toHaveTextContent(longJDComparison.overview);
  expect(
    screen.getByRole("img", { name: /Radar 5 trục đối chiếu với JD/ }),
  ).toBeVisible();
  expect(container.querySelector(".radar-overall strong")).toHaveTextContent(
    "3,7",
  );
  const details = container.querySelector(".radar-details")!;
  expect(details).toHaveAttribute("open");
  expect(details.nextElementSibling).toHaveClass("career-analysis");
  expect(
    container.querySelectorAll(".career-analysis details[open]"),
  ).toHaveLength(0);
  expect(document.body.textContent).not.toMatch(/CWA|%|CLO|enriched/);
});

it("preserves requirement order, coverage, prose and evidence when opening all details", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ComparisonView comparison={longJDComparison} courseCount={12} />,
  );
  await user.click(screen.getByRole("button", { name: "Mở tất cả" }));
  const analysis = container.querySelector(".career-analysis") as HTMLElement;
  expect(
    [...analysis.querySelectorAll("h4")].map((el) => el.textContent),
  ).toEqual(longJDComparison.requirement_reviews.map((r) => r.jd_requirement));
  for (const requirement of longJDComparison.requirement_reviews) {
    const comment = within(analysis).getByText(requirement.comment);
    expect(comment).toBeVisible();
    expect(comment.textContent).toBe(requirement.comment);
    for (const evidence of requirement.evidence)
      expect(
        within(comment.closest("details")!).getByText(evidence.course_code),
      ).toBeVisible();
  }
  expect(analysis.querySelectorAll(".coverage-covered")).toHaveLength(4);
  expect(analysis.querySelectorAll(".coverage-related")).toHaveLength(4);
  expect(analysis.querySelectorAll(".coverage-not_evidenced")).toHaveLength(4);
  await user.click(screen.getByRole("button", { name: "Thu gọn tất cả" }));
  expect(analysis.querySelectorAll("details[open]")).toHaveLength(0);
  expect(container.querySelector(".radar-details")).toHaveAttribute("open");
  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
});

it("opens the exact JD requirement from either summary group, including repeated titles", async () => {
  const user = userEvent.setup();
  const repeated = {
    ...longJDComparison,
    requirement_reviews: longJDComparison.requirement_reviews.map((r) => ({
      ...r,
      jd_requirement: "Cùng yêu cầu",
    })),
  };
  const { container } = render(
    <ComparisonView comparison={repeated} courseCount={12} />,
  );
  const summary = container.querySelector(".career-summary") as HTMLElement;
  const gapLinks = within(
    summary.querySelector(".summary-gaps") as HTMLElement,
  ).getAllByRole("button");
  await user.click(gapLinks[1]);
  const detail = screen
    .getByText(longJDComparison.requirement_reviews[5].comment)
    .closest("details")!;
  expect(detail).toHaveAttribute("open");
  expect(detail.querySelector("summary")).toHaveFocus();
  expect(
    screen.getByText(longJDComparison.requirement_reviews[2].comment),
  ).not.toBeVisible();
});

it("keeps old JD results usable without inventing scores or regenerating", () => {
  const { radar: _radar, ...legacy } = longJDComparison;
  const { container } = render(
    <ComparisonView comparison={legacy} courseCount={12} />,
  );
  expect(
    screen.getByText(legacy.conclusion, { normalizer: (text) => text }),
  ).toBeVisible();
  expect(screen.getByText("Kết quả này chưa có dữ liệu radar.")).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Điểm tổng" }),
  ).not.toBeInTheDocument();
  expect(container.querySelector(".radar-details")).not.toBeInTheDocument();
  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
});

it("shows a neutral empty-JD result and accepts different model-defined JD axes", () => {
  const { rerender, container } = render(
    <ComparisonView
      comparison={{ ...longJDComparison, requirement_reviews: [], radar: null }}
      courseCount={1}
    />,
  );
  expect(
    screen.getByText("JD chưa có yêu cầu nội dung phù hợp để đối chiếu."),
  ).toBeVisible();
  const other = {
    ...longJDComparison,
    radar: {
      ...longJDComparison.radar!,
      axes: longJDComparison.radar!.axes.map((a, i) => ({
        ...a,
        name: `Hạ tầng triển khai ${i + 1}`,
      })),
    },
  };
  rerender(<ComparisonView comparison={other} courseCount={1} />);
  expect(container.querySelector(".radar-details")).toHaveTextContent(
    "Hạ tầng triển khai 5",
  );
  expect(screen.getByRole("img")).toHaveAccessibleName(/Hạ tầng triển khai/);
  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
});
