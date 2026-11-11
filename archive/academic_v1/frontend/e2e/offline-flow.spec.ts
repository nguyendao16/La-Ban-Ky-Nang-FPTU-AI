import { test, expect } from "@playwright/test";

test("real catalog → zero grades → stored profile → fake worker → Review → two Chat turns → reload", async ({
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
  await expect(page.getByText("49 môn trong nguồn curriculum")).toBeVisible();
  await page.getByRole("textbox", { name: "Tìm môn học" }).fill("ADY201m");
  await page.getByRole("checkbox", { name: /ADY201m/ }).check();
  await page.getByRole("button", { name: /Tiếp tục nhập điểm/ }).click();
  await expect(
    page.getByText("Final Project Evaluation", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("spinbutton")).toHaveCount(8);
  await page.getByRole("button", { name: "Tạo hồ sơ học thuật" }).click();
  await expect(page.getByRole("alert")).toContainText("Nhập đủ điểm");
  for (const input of await page.getByRole("spinbutton").all())
    await input.fill("0");
  await page.getByRole("button", { name: "Tạo hồ sơ học thuật" }).click();
  await expect(
    page.getByText("CLO trong hồ sơ", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("below_expected", { exact: true })).toHaveCount(
    7,
  );
  await page.getByRole("checkbox", { name: /Giữ phiên trong tab/ }).check();
  await page.getByRole("button", { name: /Phân tích JD/ }).click();
  await page
    .getByRole("textbox", { name: "Job Description" })
    .fill("Data Analyst intern — Python và SQL.");
  await page.getByRole("button", { name: "Tạo phiên phân tích" }).click();
  await expect(
    page.getByRole("heading", {
      name: /Đang chờ Review worker|Đang phân tích học thuật/,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Kiến thức học thuật & JD" }),
  ).toBeVisible();
  expect(statuses).toContain("processing");
  expect(statuses).toContain("ready");
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
    .fill("Giải thích CLO được tham chiếu.");
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
      JSON.parse(sessionStorage.getItem("skillbridge.workspace.v1")!).workspace,
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
    return { turns: s.turn_count, attempts: s.review_job.attempt_count };
  }, workspace);
  expect(state).toEqual({ turns: 2, attempts: 1 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `/tmp/skillbridge-${testInfo.project.name}.png`,
    fullPage: true,
  });
});
