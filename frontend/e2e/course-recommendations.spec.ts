import { test, expect } from "@playwright/test";

for (const mode of ["cwa", "jd"] as const) {
  test(`${mode}: manual Coursera search, lost response replay, saved result and Chat reload`, async ({
    page,
  }, testInfo) => {
    const calls: Array<{ key: string; body: unknown }> = [];
    let loseResponse = true;
    await page.route("**/advisor/sessions/*/recommendations", async (route) => {
      if (route.request().method() === "POST") {
        calls.push({
          key: route.request().headers()["idempotency-key"],
          body: route.request().postDataJSON(),
        });
        if (loseResponse) {
          loseResponse = false;
          expect((await route.fetch()).status()).toBe(202);
          await route.abort("failed");
          return;
        }
      } else if (route.request().method() === "GET") {
        const response = await route.fetch();
        const body = await response.json();
        if (body.status === "ready" && body.result.courses.length) {
          const url = body.result.courses[0].url;
          body.result.summary += ` ([coursera.org](${url}?utm_source=openai))`;
          body.result.courses[0].reason += ` [Xem khóa học](${url})`;
        }
        await route.fulfill({ response, json: body });
        return;
      }
      await route.continue();
    });
    await page.goto("/");
    await page.getByRole("checkbox", { name: "Chọn học kỳ 1" }).check();
    await page.getByRole("checkbox", { name: /Giữ phiên trong tab/ }).check();
    if (mode === "cwa") {
      await page.getByRole("combobox").selectOption("data-analyst");
      await page
        .getByRole("button", { name: "Khám phá nhóm nghề", exact: true })
        .click();
    } else {
      await page.getByRole("tab", { name: "Mô tả công việc (JD)" }).click();
      await page
        .getByRole("textbox", { name: "Job Description" })
        .fill("Phân tích dữ liệu SQL và triển khai pipeline.");
      await page
        .getByRole("button", { name: "So sánh với JD", exact: true })
        .click();
    }
    const section = page.locator(".recommendations-section");
    await expect(
      section.getByRole("button", { name: "Gợi ý khóa học", exact: true }),
    ).toBeVisible();
    expect(calls).toHaveLength(0);
    const beforeRadar = await page
      .locator(".radar-axis-detail dt")
      .allTextContents();
    const beforeConclusion = await page
      .locator(".conclusion-text")
      .textContent();
    await section
      .getByRole("button", { name: "Gợi ý khóa học", exact: true })
      .click();
    await expect(section.getByRole("alert")).toContainText("Mất kết nối");
    await section
      .getByRole("button", { name: "Thử lại cùng yêu cầu gợi ý" })
      .click();
    await expect(
      section.getByRole("link", { name: "DEMO OFFLINE: Thực hành dữ liệu" }),
    ).toBeVisible();
    expect(calls).toHaveLength(2);
    expect(calls[0]).toEqual(calls[1]);
    expect(calls[0].body).toEqual({});
    await expect(section).toContainText("Thông tin từ kết quả tìm kiếm");
    await expect(page.locator(".career-radar figcaption")).toHaveCount(
      mode === "cwa" ? 0 : 1,
    );
    const citation = section.getByRole("link", {
      name: "coursera.org",
      exact: true,
    });
    const courseUrl = await section
      .getByRole("link", { name: "DEMO OFFLINE: Thực hành dữ liệu" })
      .getAttribute("href");
    await expect(citation).toHaveAttribute("href", courseUrl!);
    await expect(section).not.toContainText("[coursera.org](");
    await page.context().route("https://www.coursera.org/**", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "<title>Offline course link</title>",
      }),
    );
    const newTab = page.context().waitForEvent("page");
    await citation.focus();
    await page.keyboard.press("Enter");
    const coursePage = await newTab;
    await expect(coursePage).toHaveURL(courseUrl!);
    await coursePage.close();
    expect(
      await page.locator(".radar-axis-detail dt").allTextContents(),
    ).toEqual(beforeRadar);
    expect(await page.locator(".conclusion-text").textContent()).toBe(
      beforeConclusion,
    );
    const order = await page
      .locator(
        ".career-summary,.recommendations-section,.radar-details,.career-analysis,.chat-section",
      )
      .evaluateAll((nodes) => nodes.map((node) => node.className));
    expect(order).toEqual([
      "career-summary",
      "recommendations-section",
      "radar-details",
      "career-analysis",
      "chat-section",
    ]);
    const detail = section.getByText("Khoảng trống liên quan (1)");
    await detail.focus();
    await page.keyboard.press("Enter");
    await expect(section.locator("details")).toHaveAttribute("open", "");
    await page
      .getByRole("textbox", { name: "Câu hỏi của bạn" })
      .fill("Khóa gợi ý liên quan đến khoảng trống nào?");
    await page
      .getByRole("button", { name: "Gửi câu hỏi", exact: true })
      .click();
    await expect(page.locator(".turn")).toHaveCount(1);
    await expect(page.locator(".turn")).toContainText(
      "DEMO OFFLINE: Thực hành dữ liệu",
    );
    await page.reload();
    await expect(page.locator(".turn")).toHaveCount(1);
    await expect(
      section.getByRole("link", { name: "DEMO OFFLINE: Thực hành dữ liệu" }),
    ).toBeVisible();
    expect(calls).toHaveLength(2);
    const workspace = await page.evaluate(
      () =>
        JSON.parse(
          sessionStorage.getItem("skillbridge.course-jd.workspace.v1")!,
        ).workspace,
    );
    expect(workspace.recommendations).toBeUndefined();
    expect(await page.locator("body").textContent()).not.toContain(
      workspace.token,
    );
    const record = await page.evaluate(async (w) => {
      const response = await fetch(
        `http://127.0.0.1:8001/api/v1/advisor/sessions/${w.sessionId}/recommendations`,
        { headers: { Authorization: `Bearer ${w.token}` } },
      );
      return response.json();
    }, workspace);
    expect(record.job.attempt_count).toBe(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await section.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `/tmp/skillbridge-coursera-${mode}-${testInfo.project.name}.png`,
      fullPage: true,
    });
  });
}
