import { test, expect } from "@playwright/test";

test("semester/COMBO selection → JD → private-source comparison → replay → two turns → reload", async ({
  page,
}, testInfo) => {
  const sessionPosts: string[] = [],
    chatKeys: string[] = [],
    statuses: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      /\/advisor\/sessions$/.test(request.url())
    )
      sessionPosts.push(request.url());
  });
  page.on("response", async (response) => {
    if (
      response.request().method() === "GET" &&
      /\/advisor\/sessions\/[^/]+$/.test(response.url())
    ) {
      try {
        statuses.push((await response.json()).status);
      } catch {
        /* aborted polling */
      }
    }
  });
  const publicBodies: unknown[] = [];
  page.on("response", async (response) => {
    if (response.url().includes("/api/v1/")) {
      try {
        publicBodies.push(await response.json());
      } catch {
        /* cancelled request */
      }
    }
  });
  let loseFirstChatResponse = true;
  await page.route("**/advisor/sessions/*/messages", async (route) => {
    if (route.request().method() === "POST") {
      chatKeys.push(route.request().headers()["idempotency-key"]);
      if (loseFirstChatResponse) {
        loseFirstChatResponse = false;
        const committed = await route.fetch();
        expect(committed.status()).toBe(200);
        await route.abort("failed");
        return;
      }
    }
    await route.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Hành trình học tập của bạn" }),
  ).toBeVisible();
  await page.getByRole("radio", { name: "Applied Data Science" }).check();
  await page.getByRole("checkbox", { name: "Chọn học kỳ 9" }).check();
  for (let n = 1; n <= 9; n++)
    await expect(
      page.getByRole("checkbox", { name: `Chọn học kỳ ${n}` }),
    ).toBeChecked();
  await page.getByRole("radio", { name: "AI application" }).check();
  await expect(page.getByRole("checkbox", { name: /AIH301m/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /BDI302c/ })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: /HCM202/ })).toBeEnabled();
  await expect(page.getByRole("checkbox", { name: /HCM202/ })).toBeChecked();
  expect(await page.locator("body").textContent()).not.toMatch(
    /CLO|enriched|chưa có dữ liệu/i,
  );
  await page.getByRole("checkbox", { name: /Giữ phiên trong tab/ }).check();
  await page.getByRole("tab", { name: "Mô tả công việc (JD)" }).click();
  await page
    .getByRole("textbox", { name: "Job Description" })
    .fill("Data Analyst intern — Python và SQL.");
  await page.screenshot({
    path: `/tmp/skillbridge-semester-input-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "So sánh với JD", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Đang chờ worker so sánh|Đang đối chiếu nội dung môn học/,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Kết quả đối chiếu với JD",
      exact: true,
    }),
  ).toBeVisible();
  expect(statuses).toContain("processing");
  await expect.poll(() => statuses).toContain("ready");
  await expect(page.locator(".jd-results .radar-dot")).toHaveCount(5);
  await expect(page.locator(".jd-results .radar-details")).toHaveAttribute(
    "open",
    "",
  );
  await expect(
    page.locator(".jd-results .career-analysis details[open]"),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      "Chưa có lượt trao đổi. Bạn có thể hỏi về nội dung liên quan đến công việc mục tiêu.",
    ),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Câu hỏi của bạn" })
    .fill("Mình đã học nội dung nào liên quan?");
  await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
  await expect(page.getByRole("alert")).toContainText("Mất kết nối");
  await page.getByRole("button", { name: "Thử lại cùng câu hỏi" }).click();
  await expect(page.locator(".turn")).toHaveCount(1);
  expect(chatKeys).toHaveLength(2);
  expect(chatKeys[1]).toBe(chatKeys[0]);
  await page
    .getByRole("textbox", { name: "Câu hỏi của bạn" })
    .fill("Giải thích các môn được tham chiếu.");
  await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
  await expect(page.locator(".turn")).toHaveCount(2);
  expect(chatKeys[2]).not.toBe(chatKeys[1]);
  await page.getByRole("button", { name: "Tải lại lịch sử" }).click();
  await expect(page.locator(".turn")).toHaveCount(2);
  await page.reload();
  await expect(page.locator(".turn")).toHaveCount(2);
  expect(sessionPosts).toHaveLength(1);
  const workspace = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem("skillbridge.course-jd.workspace.v1")!)
        .workspace,
  );
  expect(await page.locator("body").textContent()).not.toContain(
    workspace.token,
  );
  const state = await page.evaluate(async (w) => {
    const r = await fetch(
      `http://127.0.0.1:8001/api/v1/advisor/sessions/${w.sessionId}`,
      { headers: { Authorization: `Bearer ${w.token}` } },
    );
    const s = await r.json();
    return { turns: s.turn_count, attempts: s.comparison_job.attempt_count };
  }, workspace);
  expect(state).toEqual({ turns: 2, attempts: 1 });
  const sourceProbe = await page.request.get(
    "/@fs/data/FPT/Learning_Materials/Semester_5/DPL302m/skillbridge/data/courses/ADY201m/clos.json",
  );
  expect(sourceProbe.status()).toBe(403);
  const network = JSON.stringify(publicBodies);
  expect(network).not.toMatch(
    /"clos"|"clo"|"clo_set"|"fingerprints"|CLO[0-9]|enriched/,
  );
  expect(await page.locator("body").textContent()).not.toMatch(/CLO|enriched/i);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `/tmp/skillbridge-semester-result-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "So sánh mục tiêu khác" }).click();
  await expect(
    page.getByRole("textbox", { name: "Job Description" }),
  ).toHaveValue("");
  expect(sessionPosts).toHaveLength(1);
  await page
    .getByRole("textbox", { name: "Job Description" })
    .fill("JD khác: Python và xử lý dữ liệu.");
  await page.getByRole("button", { name: "So sánh với JD" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Kết quả đối chiếu với JD",
      exact: true,
    }),
  ).toBeVisible();
  expect(sessionPosts).toHaveLength(2);
  const second = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem("skillbridge.course-jd.workspace.v1")!)
        .workspace,
  );
  expect(second.selectionId).toBe(workspace.selectionId);
  expect(second.sessionId).not.toBe(workspace.sessionId);
  const previous = await page.evaluate(async (w) => {
    const r = await fetch(
      `http://127.0.0.1:8001/api/v1/advisor/sessions/${w.sessionId}`,
      { headers: { Authorization: `Bearer ${w.token}` } },
    );
    const s = await r.json();
    return { turns: s.turn_count, attempts: s.comparison_job.attempt_count };
  }, workspace);
  expect(previous).toEqual({ turns: 2, attempts: 1 });
});
