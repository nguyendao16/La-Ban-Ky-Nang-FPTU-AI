import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CareerRadar, CareerRadarDetails } from "./components/CareerRadar";
import { ComparisonView } from "./components/ComparisonView";
import { careerComparison, careerRadar } from "./test/fixtures";

it("uses the LLM overall score directly and draws five axes on the shared five-point scale", () => {
  const { container } = render(<CareerRadar radar={careerRadar} />);
  expect(container.querySelector(".radar-overall strong")).toHaveTextContent(
    "3,7",
  );
  expect(careerRadar.overall_score).not.toBe(
    careerRadar.axes.reduce((sum, a) => sum + a.score, 0) / 5,
  );
  expect(screen.getByRole("img", { name: /Radar 5 trục/ })).toBeVisible();
  expect(container.querySelectorAll(".radar-grid")).toHaveLength(5);
  expect(container.querySelectorAll(".radar-axis-label")).toHaveLength(5);
  const dots = [...container.querySelectorAll(".radar-dot")];
  expect(dots).toHaveLength(5);
  for (let i = 0; i < dots.length; i++) {
    const x = Number(dots[i].getAttribute("cx")) - 200;
    const y = Number(dots[i].getAttribute("cy")) - 140;
    expect(Math.hypot(x, y)).toBeCloseTo((careerRadar.axes[i].score / 5) * 92);
  }
});

it("moves all five expanded axes before analysis, preserves evidence, and allows independent collapse", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ComparisonView
      comparison={careerComparison}
      careerTitle="Data Analyst"
      courseCount={3}
    />,
  );
  const detail = container.querySelector(".radar-details")!;
  expect(detail).toHaveAttribute("open");
  expect(
    container.querySelector(".career-radar details"),
  ).not.toBeInTheDocument();
  expect(detail.previousElementSibling).toHaveClass("career-summary");
  expect(detail.nextElementSibling).toHaveClass("career-analysis");
  expect(screen.getByText(careerRadar.overall_comment)).toBeVisible();
  for (const axis of careerRadar.axes) {
    expect(within(detail as HTMLElement).getByText(axis.name)).toBeVisible();
    expect(screen.getByText(axis.description)).toBeVisible();
    expect(screen.getByText(axis.comment)).toBeVisible();
  }
  expect(detail.querySelectorAll(".course-reference")).toHaveLength(5);
  await user.click(screen.getByRole("button", { name: "Thu gọn tất cả" }));
  expect(detail).toHaveAttribute("open");
  const summary = screen.getByText("Chi tiết 5 trục");
  await user.click(summary);
  expect(detail).not.toHaveAttribute("open");
  expect(screen.getByText(careerRadar.overall_comment)).not.toBeVisible();
  await user.click(summary);
  expect(detail).toHaveAttribute("open");
  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
});

it("renders different model-defined axes when the career changes, including long names", () => {
  const { rerender, container } = render(
    <>
      <CareerRadar radar={careerRadar} />
      <CareerRadarDetails radar={careerRadar} />
    </>,
  );
  const other = {
    ...careerRadar,
    axes: careerRadar.axes.map((axis, i) => ({
      ...axis,
      name: `Nghiên cứu thuật toán và kiến trúc mô hình chuyên sâu ${i + 1}`,
    })),
  };
  rerender(
    <>
      <CareerRadar radar={other} />
      <CareerRadarDetails radar={other} />
    </>,
  );
  const image = screen.getByRole("img");
  expect(image).toHaveAccessibleName(/Nghiên cứu thuật toán/);
  expect(image).not.toHaveAccessibleName(/Dữ liệu và thống kê/);
  expect(container.querySelector("dl")).toHaveTextContent(other.axes[4].name);
});

it("supports genuine zero ratings without inventing positive evidence", () => {
  const zero = {
    ...careerRadar,
    overall_score: 0,
    axes: careerRadar.axes.map((axis) => ({ ...axis, score: 0, evidence: [] })),
  };
  const { container } = render(<CareerRadar radar={zero} />);
  expect(container.querySelector(".radar-overall strong")).toHaveTextContent(
    /^0$/,
  );
  for (const dot of container.querySelectorAll(".radar-dot")) {
    expect(dot).toHaveAttribute("cx", "200");
    expect(dot).toHaveAttribute("cy", "140");
  }
  expect(container.querySelectorAll(".course-reference")).toHaveLength(0);
});

it("keeps old results readable without a fake score or automatic re-analysis", () => {
  const { radar: _radar, ...legacy } = careerComparison;
  render(
    <ComparisonView
      comparison={legacy}
      careerTitle="Data Analyst"
      courseCount={3}
    />,
  );
  expect(screen.getByText("Kết quả này chưa có dữ liệu radar.")).toBeVisible();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Điểm tổng" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(legacy.conclusion)).toBeVisible();
  expect(vi.mocked(fetch)).not.toHaveBeenCalled();
});
