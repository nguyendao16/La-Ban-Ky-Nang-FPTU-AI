import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { api } from "./api";
import { ComparisonView } from "./components/ComparisonView";
import { TargetInput } from "./components/TargetInput";
import { targetDraft } from "./target";
import {
  careerComparison,
  careerProfiles,
  careerRadar,
  comparison,
} from "./test/fixtures";

const names = [
  "Image & Video Processing",
  "Vision Model Development",
  "Testing & Troubleshooting",
  "Vision Integration & Deployment",
  "Secure & Responsible Vision Engineering",
];
const fixedTarget = {
  title: "Computer Vision Engineer",
  scope: "Phạm vi thị giác máy tính; không bắt buộc chuyên môn NLP/LLM.",
  axes: names.map((name) => ({
    name,
    description: `Phạm vi tiếng Việt ổn định cho ${name}.`,
  })),
};
const fixedRadar = {
  ...careerRadar,
  axes: careerRadar.axes.map((axis, i) => ({
    ...axis,
    ...fixedTarget.axes[i],
  })),
};

it("uses the selected application title and scope while keeping the shared source intact", async () => {
  const profiles = careerProfiles.map((p) =>
    p.profile_id === "computer-vision-engineer"
      ? {
          ...p,
          title: "AI Engineer / Machine Learning Engineer",
          content: "Nguyên văn nguồn AI/ML gồm cả CV và NLP/LLM.",
          target: fixedTarget,
        }
      : p,
  );
  vi.spyOn(api, "listCareerProfiles").mockResolvedValue({ profiles });
  const create = vi.spyOn(api, "createAdvisorSession");
  function Form() {
    const [value, setValue] = useState(targetDraft());
    return <TargetInput value={value} onChange={setValue} />;
  }
  render(<Form />);
  const select = await screen.findByRole("combobox");
  expect(screen.getAllByRole("option")).toHaveLength(9);
  await userEvent.selectOptions(select, "computer-vision-engineer");
  expect(
    screen.getByRole("option", { name: fixedTarget.title }),
  ).toHaveProperty("selected", true);
  await userEvent.click(screen.getByText("Xem mô tả nhóm nghề"));
  expect(screen.getByText(fixedTarget.scope)).toBeVisible();
  expect(
    screen.getByText("Nguyên văn nguồn AI/ML gồm cả CV và NLP/LLM."),
  ).toBeVisible();
  expect(
    screen.getAllByRole("listitem").map((item) => item.textContent),
  ).toEqual(names);
  expect(create).not.toHaveBeenCalled();
});

it("renders full fixed English names and Vietnamese scopes without recomputing scores", () => {
  render(
    <ComparisonView
      comparison={{ ...careerComparison, radar: fixedRadar }}
      careerTitle={fixedTarget.title}
      fixedCareerAxes
      courseCount={15}
    />,
  );
  const details = document.querySelector(".radar-details") as HTMLElement;
  expect(
    [...details.querySelectorAll("dt > span")].map((node) => node.textContent),
  ).toEqual(names);
  for (const axis of fixedTarget.axes)
    expect(within(details).getByText(axis.description)).toBeVisible();
  expect(document.querySelector(".career-radar figcaption")).toBeNull();
  expect(
    [...document.querySelectorAll(".radar-axis-label")].map((label) =>
      [...label.querySelectorAll("tspan")]
        .map((line) => line.textContent)
        .join(" "),
    ),
  ).toEqual(names);
  expect(document.querySelector(".radar-overall strong")).toHaveTextContent(
    "3,7",
  );
  expect(screen.getByRole("img")).toHaveAccessibleName(
    expect.stringContaining(names[4]),
  );
});

it("retains saved dynamic CWA names rather than relabelling them from the new catalog", () => {
  const legacy = { ...careerComparison, radar: careerRadar };
  render(
    <ComparisonView
      comparison={legacy}
      careerTitle="AI / ML Engineer"
      courseCount={15}
    />,
  );
  expect(
    [...document.querySelectorAll(".radar-axis-detail dt > span")].map(
      (node) => node.textContent,
    ),
  ).toEqual(careerRadar.axes.map((a) => a.name));
  expect(screen.queryByText(/Năm trục cố định/)).not.toBeInTheDocument();
  expect(document.querySelector(".career-radar figcaption")).toBeNull();
});

it("keeps JD axes and its existing caption even when fixed CWA display is requested", () => {
  render(
    <ComparisonView
      comparison={{ ...comparison, radar: careerRadar }}
      fixedCareerAxes
      courseCount={15}
    />,
  );
  expect(
    [...document.querySelectorAll(".radar-axis-detail dt > span")].map(
      (node) => node.textContent,
    ),
  ).toEqual(careerRadar.axes.map((a) => a.name));
  expect(screen.queryByText(/Năm trục cố định/)).not.toBeInTheDocument();
  expect(screen.getByText(/Ước tính phù hợp với JD/)).toBeVisible();
  expect(screen.getByText(/cá nhân hoặc quyết định tuyển dụng/)).toBeVisible();
});
