import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ComparisonView } from "./components/ComparisonView";
import {
  careerComparison,
  careerRadar,
  longJDComparison,
} from "./test/fixtures";

const cases = [
  { name: "CWA", comparison: careerComparison, careerTitle: "Data Analyst" },
  { name: "JD", comparison: longJDComparison, careerTitle: undefined },
];

it.each(cases)(
  "shows saved public explanations and scores for $name",
  ({ comparison, careerTitle }) => {
    const explanation =
      "Nội dung ở mức hiểu; mục tiêu yêu cầu vận hành độc lập; còn thiếu độ sâu thực hành.";
    const radar = {
      ...careerRadar,
      overall_score: 1,
      overall_comment: explanation,
      axes: careerRadar.axes.map((axis) => ({
        ...axis,
        score: 1,
        comment: explanation,
      })),
    };
    const result = { ...comparison, radar, conclusion: explanation };
    const before = JSON.stringify(result);
    const { container } = render(
      <ComparisonView
        comparison={result}
        careerTitle={careerTitle}
        courseCount={3}
      />,
    );
    expect(container.querySelector(".career-summary")).toHaveTextContent(
      explanation,
    );
    expect(container.querySelector(".radar-rationale")).toHaveTextContent(
      explanation,
    );
    expect(container.querySelector(".radar-overall strong")).toHaveTextContent(
      /^1$/,
    );
    expect(container.querySelector(".radar-score-label")).toHaveTextContent(
      "Ước tính phù hợp",
    );
    expect(screen.getByText("Chi tiết 5 trục")).toBeVisible();
    expect(document.body.textContent).not.toMatch(/giả định|cách chấm/iu);
    expect(screen.getByRole("img", { name: /Radar 5 trục/ })).toBeVisible();
    expect(container.querySelectorAll(".radar-axis-detail")).toHaveLength(5);
    expect(JSON.stringify(result)).toBe(before);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  },
);

it.each(cases)(
  "keeps legacy $name scores and public prose",
  ({ comparison, careerTitle }) => {
    const before = JSON.stringify(comparison);
    const { container } = render(
      <ComparisonView
        comparison={comparison}
        careerTitle={careerTitle}
        courseCount={3}
      />,
    );
    expect(container.querySelector(".radar-overall strong")).toHaveTextContent(
      "3,7",
    );
    expect(container.querySelector(".radar-rationale")).toHaveTextContent(
      comparison.radar!.overall_comment,
    );
    expect(document.body.textContent).not.toMatch(/giả định|cách chấm/iu);
    expect(JSON.stringify(comparison)).toBe(before);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  },
);

it("marks only JD related statuses in the summary and details", () => {
  const { container } = render(
    <ComparisonView comparison={longJDComparison} courseCount={12} />,
  );
  const related = longJDComparison.requirement_reviews.filter(
    (r) => r.coverage === "related",
  );
  expect(
    container.querySelectorAll(".finding-status.finding-related"),
  ).toHaveLength(related.length);
  expect(container.querySelectorAll(".pill.coverage-related")).toHaveLength(
    related.length,
  );
  expect(container.querySelector(".finding-covered")).not.toHaveClass(
    "finding-related",
  );
});

it("marks the CWA related group without inventing coverage statuses", () => {
  const { container } = render(
    <ComparisonView
      comparison={careerComparison}
      careerTitle="Data Analyst"
      courseCount={3}
    />,
  );
  expect(container.querySelector(".summary-related h3")).toHaveTextContent(
    "Nội dung liên quan",
  );
  expect(
    container.querySelectorAll(".analysis-related .analysis-item"),
  ).toHaveLength(careerComparison.related_content.length);
  expect(container.querySelectorAll('[class*="coverage-"]')).toHaveLength(0);
});
