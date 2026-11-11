import { test, expect } from "@playwright/test";

test("chosen CWA career → lost creation response/replay → comparison → Chat replay → reload", async ({
  page,
}, testInfo) => {
  const creation: Array<{ key: string; body: unknown }> = [];
  const chatKeys: string[] = [];
  const bodies: unknown[] = [];
  let loseCreation = true,
    loseChat = true;
  page.on("response", async (response) => {
    if (response.url().includes("/api/v1/")) {
      try {
        bodies.push(await response.json());
      } catch {
        /* cancelled response */
      }
    }
  });
  await page.route("**/advisor/sessions", async (route) => {
    if (route.request().method() === "POST") {
      creation.push({
        key: route.request().headers()["idempotency-key"],
        body: route.request().postDataJSON(),
      });
      if (loseCreation) {
        loseCreation = false;
        expect((await route.fetch()).status()).toBe(202);
        await route.abort("failed");
        return;
      }
    }
    await route.continue();
  });
  await page.route("**/advisor/sessions/*/messages", async (route) => {
    if (route.request().method() === "POST") {
      chatKeys.push(route.request().headers()["idempotency-key"]);
      if (loseChat) {
        loseChat = false;
        expect((await route.fetch()).status()).toBe(200);
        await route.abort("failed");
        return;
      }
    }
    await route.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("tab", { name: "Nhóm nghề CWA" }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByRole("checkbox", { name: "Chọn học kỳ 4" }).check();
  await expect(page.getByRole("combobox").locator("option")).toHaveCount(9);
  await page
    .getByRole("combobox", { name: "Nhóm nghề mục tiêu" })
    .selectOption("data-analyst");
  await page.getByText("Xem mô tả nhóm nghề").click();
  await expect(page.locator(".career-source")).toContainText("CWA 18398:2026");
  await page.getByRole("checkbox", { name: /Giữ phiên trong tab/ }).check();
  await page.screenshot({
    path: `/tmp/skillbridge-cwa-input-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Khám phá nhóm nghề" }).click();
  await expect(page.getByRole("alert")).toContainText("Mất kết nối");
  await expect(
    page.getByRole("combobox", { name: "Nhóm nghề mục tiêu" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("tab", { name: "Mô tả công việc (JD)" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Thử lại cùng yêu cầu" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Kết quả đối chiếu với nhóm nghề",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".career-radar .radar-dot")).toHaveCount(5);
  await expect(page.locator(".radar-axis-detail dt > span")).toHaveText([
    "Data Collection & Modelling",
    "Data Quality & Transformation",
    "Data Analysis & Interpretation",
    "Visualization & Business Insights",
    "Data Governance & Protection",
  ]);
  const firstAxes = await page.locator(".radar-axis-label").allTextContents();
  expect(creation).toHaveLength(2);
  expect(creation[1]).toEqual(creation[0]);
  expect(creation[0].body).toMatchObject({ career_profile_id: "data-analyst" });
  expect(creation[0].body).not.toHaveProperty("job_description");
  await expect(page.locator(".target-heading")).toContainText("Data Analyst");
  await expect(
    page.getByRole("heading", { name: "Nội dung học tập liên quan" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Khoảng trống nội dung" }),
  ).toBeVisible();
  await expect(page.locator('[class*="coverage-"]')).toHaveCount(0);
  await page
    .getByRole("textbox", { name: "Câu hỏi của bạn" })
    .fill("Các môn này liên quan đến nghề phân tích dữ liệu thế nào?");
  await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
  await expect(page.getByRole("alert")).toContainText("Mất kết nối");
  await page.getByRole("button", { name: "Thử lại cùng câu hỏi" }).click();
  await expect(page.locator(".turn")).toHaveCount(1);
  expect(chatKeys[0]).toBe(chatKeys[1]);
  await page
    .getByRole("textbox", { name: "Câu hỏi của bạn" })
    .fill("Giải thích khoảng trống nội dung.");
  await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
  await expect(page.locator(".turn")).toHaveCount(2);
  await page.reload();
  await expect(page.locator(".turn")).toHaveCount(2);
  expect(creation).toHaveLength(2);
  const workspace = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem("skillbridge.course-jd.workspace.v1")!)
        .workspace,
  );
  const state = await page.evaluate(async (w) => {
    const response = await fetch(
      `http://127.0.0.1:8001/api/v1/advisor/sessions/${w.sessionId}`,
      { headers: { Authorization: `Bearer ${w.token}` } },
    );
    const session = await response.json();
    return {
      turns: session.turn_count,
      attempts: session.comparison_job.attempt_count,
      target: session.target.career_profile.profile_id,
    };
  }, workspace);
  expect(state).toEqual({ turns: 2, attempts: 1, target: "data-analyst" });
  expect(JSON.stringify(bodies)).not.toMatch(
    /"clos"|"clo"|"clo_set"|"fingerprints"|CLO[0-9]|enriched/,
  );
  expect(await page.locator("body").textContent()).not.toMatch(/CLO|enriched/i);
  expect(await page.locator("body").textContent()).not.toContain(
    workspace.token,
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `/tmp/skillbridge-cwa-result-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "So sánh mục tiêu khác" }).click();
  await page
    .getByRole("combobox", { name: "Nhóm nghề mục tiêu" })
    .selectOption("mlops-engineer");
  expect(creation).toHaveLength(2);
  await page.getByRole("button", { name: "Khám phá nhóm nghề" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Kết quả đối chiếu với nhóm nghề",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".target-heading")).toContainText("MLOps Engineer");
  await expect(page.locator(".career-radar .radar-dot")).toHaveCount(5);
  expect(await page.locator(".radar-axis-label").allTextContents()).not.toEqual(
    firstAxes,
  );
  expect(creation).toHaveLength(3);
  expect(creation[2].body).toMatchObject({
    selection_id: workspace.selectionId,
    career_profile_id: "mlops-engineer",
  });
  expect(creation[2].key).not.toBe(creation[0].key);
  for (const [id, title, names] of [
    [
      "computer-vision-engineer",
      "Computer Vision Engineer",
      [
        "Image & Video Processing",
        "Vision Model Development",
        "Testing & Troubleshooting",
        "Vision Integration & Deployment",
        "Secure & Responsible Vision Engineering",
      ],
    ],
    [
      "nlp-llm-engineer",
      "NLP / LLM Engineer",
      [
        "Text Processing",
        "Model Adaptation & Prompting",
        "NLP/LLM Testing & Troubleshooting",
        "Application Integration & Deployment",
        "Secure & Responsible AI Engineering",
      ],
    ],
  ] as const) {
    await page.getByRole("button", { name: "So sánh mục tiêu khác" }).click();
    await page.getByRole("combobox").selectOption(id);
    await page.getByRole("button", { name: "Khám phá nhóm nghề" }).click();
    await expect(page.locator(".target-heading")).toContainText(title);
    await expect(page.locator(".radar-axis-detail dt > span")).toHaveText([
      ...names,
    ]);
    expect(
      await page
        .locator(".radar-axis-label")
        .evaluateAll((labels) =>
          labels.map((label) =>
            [...label.querySelectorAll("tspan")]
              .map((line) => line.textContent)
              .join(" "),
          ),
        ),
    ).toEqual([...names]);
    const boxes = await page
      .locator(".radar-axis-label")
      .evaluateAll((labels) =>
        labels.map((label) => {
          const box = (label as SVGGraphicsElement).getBBox();
          return {
            x: box.x,
            right: box.x + box.width,
            y: box.y,
            bottom: box.y + box.height,
          };
        }),
      );
    for (const box of boxes) {
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.right).toBeLessThanOrEqual(400);
      expect(box.y).toBeGreaterThanOrEqual(-5);
      expect(box.bottom).toBeLessThanOrEqual(310);
    }
    await page.reload();
    await expect(page.locator(".radar-axis-detail dt > span")).toHaveText([
      ...names,
    ]);
    expect(await page.locator(".turn").count()).toBe(0);
  }
  expect(creation).toHaveLength(5);
  await page.screenshot({
    path: `/tmp/skillbridge-fixed-cwa-${testInfo.project.name}.png`,
    fullPage: true,
  });
});
