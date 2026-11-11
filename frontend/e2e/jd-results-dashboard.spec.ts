import { test, expect } from "@playwright/test";
import { longJDComparison, selection, session } from "../src/test/fixtures";
import type { JDComparison } from "../src/types";

test("JD has full summary, model radar and accessible details; legacy reload never regenerates", async ({
  page,
}, testInfo) => {
  let comparison: JDComparison = longJDComparison;
  const writes: string[] = [];
  const token = "offline-jd-results-capability";
  await page.addInitScript(
    ({ token, selectionId }) => {
      sessionStorage.setItem(
        "skillbridge.course-jd.workspace.v1",
        JSON.stringify({
          baseUrl: "http://127.0.0.1:8001",
          workspace: {
            selectionId,
            token,
            keepInTab: true,
            sessionId: "session-1",
            mode: "jd",
          },
        }),
      );
    },
    { token, selectionId: selection.selection_id },
  );
  await page.route("**/api/v1/**", async (route) => {
    if (route.request().method() !== "GET") {
      writes.push(route.request().url());
      await route.abort();
      return;
    }
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/recommendations"))
      await route.fulfill({
        json: {
          session_id: "session-1",
          status: "not_requested",
          job: null,
          result: null,
          gaps: [],
        },
      });
    else if (path.endsWith("/messages"))
      await route.fulfill({ json: { session_id: "session-1", turns: [] } });
    else if (path.includes("/advisor/sessions/"))
      await route.fulfill({ json: { ...session("ready"), comparison } });
    else if (path.includes("/selections/"))
      await route.fulfill({
        json: { ...selection, summary: { course_count: 12 } },
      });
    else throw new Error(`Unexpected request ${path}`);
  });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  const result = page.locator(".jd-results");
  const summary = result.locator(".career-summary");
  await expect(summary.locator(".finding-related").first()).toHaveCSS(
    "color",
    "rgb(122, 75, 0)",
  );
  await expect(summary.locator(".finding-related").first()).toHaveCSS(
    "background-color",
    "rgb(255, 248, 225)",
  );
  await expect(result.locator(".pill.coverage-related").first()).toHaveCSS(
    "background-color",
    "rgb(255, 248, 225)",
  );
  const heading = result.getByRole("heading", {
    name: "Kết quả đối chiếu với JD",
    exact: true,
  });
  await expect(heading).toBeFocused();
  await expect(summary).toContainText("12 môn đã chọn");
  await expect(summary.locator(".conclusion-text")).toHaveText(
    longJDComparison.conclusion,
  );
  await expect(summary.locator(".finding-link")).toHaveCount(12);
  await expect(
    summary.getByRole("button", { name: /Xem thêm|Đọc đầy đủ/ }),
  ).toHaveCount(0);
  const prose = await summary
    .locator(".conclusion-text")
    .evaluate((el) => ({ h: el.clientHeight, s: el.scrollHeight }));
  expect(prose.s).toBeLessThanOrEqual(prose.h + 1);
  const radar = summary.locator(".career-radar");
  await expect(radar.locator(".radar-dot")).toHaveCount(5);
  await expect(radar.locator(".radar-overall strong")).toHaveText("3,7");
  const narrativeBox = (await summary
    .locator(".executive-narrative")
    .boundingBox())!;
  const radarBox = (await radar.boundingBox())!;
  if (testInfo.project.name === "desktop")
    expect(radarBox.x).toBeGreaterThan(narrativeBox.x + narrativeBox.width);
  else
    expect(radarBox.y).toBeGreaterThanOrEqual(
      narrativeBox.y + narrativeBox.height,
    );
  const axes = result.locator(".radar-details");
  const analysis = result.locator(".career-analysis");
  await expect(axes).toHaveAttribute("open", "");
  await expect(axes.locator(".radar-axis-detail")).toHaveCount(5);
  expect((await axes.boundingBox())!.y).toBeLessThan(
    (await analysis.boundingBox())!.y,
  );
  await expect(analysis.locator("details[open]")).toHaveCount(0);
  const target = longJDComparison.requirement_reviews[10];
  await summary
    .getByRole("button", {
      name: `${target.jd_requirement} Có liên quan`,
      exact: true,
    })
    .focus();
  await page.keyboard.press("Enter");
  const detail = analysis.locator("details").filter({
    has: page.getByRole("heading", {
      name: target.jd_requirement,
      exact: true,
      includeHidden: true,
    }),
  });
  await expect(detail.locator("summary")).toBeFocused();
  await expect(detail).toHaveAttribute("open", "");
  await expect(detail.locator(".verbatim")).toHaveText(target.comment);
  await expect(detail.locator(".course-reference")).toHaveText("COURSE11");
  await page.keyboard.press("Space");
  await expect(detail).not.toHaveAttribute("open");
  await result.getByRole("button", { name: "Mở tất cả", exact: true }).click();
  await expect(analysis.locator("details[open]")).toHaveCount(13);
  expect(
    await analysis.locator(".analysis-content > .verbatim").allTextContents(),
  ).toEqual([
    longJDComparison.overview,
    ...longJDComparison.requirement_reviews.map((r) => r.comment),
  ]);
  await expect(analysis.locator("h4")).toHaveText(
    longJDComparison.requirement_reviews.map((r) => r.jd_requirement),
  );
  await result
    .getByRole("button", { name: "Thu gọn tất cả", exact: true })
    .click();
  await expect(axes).toHaveAttribute("open", "");
  await axes.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(axes).not.toHaveAttribute("open");
  await page.keyboard.press("Space");
  await expect(axes).toHaveAttribute("open", "");
  expect(await result.innerText()).not.toMatch(/CWA|CLO|enriched|%/);
  expect(await page.locator("body").innerText()).not.toContain(token);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  const order = await page
    .locator(".comparison-section,.chat-section")
    .evaluateAll((nodes) => nodes.map((n) => n.className));
  expect(order).toEqual([
    "comparison-section career-results jd-results",
    "chat-section",
  ]);
  await heading.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `/tmp/skillbridge-jd-results-${testInfo.project.name}.png`,
    fullPage: true,
  });
  const { radar: _radar, ...legacy } = longJDComparison;
  comparison = legacy;
  await page.reload();
  await expect(result.locator(".radar-unavailable")).toBeVisible();
  await expect(result.getByRole("img")).toHaveCount(0);
  await expect(result.locator(".conclusion-text")).toHaveText(
    legacy.conclusion,
  );
  expect(writes).toHaveLength(0);
});
