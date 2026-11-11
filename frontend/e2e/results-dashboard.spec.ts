import { test, expect } from "@playwright/test";
import {
  careerProfiles,
  longCareerComparison,
  selection,
  session,
} from "../src/test/fixtures";

test("full CWA summary, independent radar, expanded axes and local typography work on desktop and mobile", async ({
  page,
}, testInfo) => {
  const token = "offline-results-capability";
  const posts: string[] = [];
  const reads: string[] = [];
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
            mode: "cwa",
          },
        }),
      );
    },
    { token, selectionId: selection.selection_id },
  );
  await page.route("**/api/v1/**", async (route) => {
    if (route.request().method() !== "GET") {
      posts.push(route.request().url());
      await route.abort();
      return;
    }
    const path = new URL(route.request().url()).pathname;
    reads.push(path);
    let body: unknown;
    if (path.endsWith("/recommendations"))
      body = {
        session_id: "session-1",
        status: "not_requested",
        job: null,
        result: null,
        gaps: [],
      };
    else if (path.endsWith("/messages"))
      body = { session_id: "session-1", turns: [] };
    else if (path.includes("/advisor/sessions/"))
      body = {
        ...session("ready"),
        comparison: longCareerComparison,
        target: {
          type: "cwa",
          career_profile: careerProfiles.find(
            (p) => p.profile_id === "ai-data-platform-engineer",
          )!,
        },
      };
    else if (path.includes("/selections/"))
      body = {
        ...selection,
        summary: { course_count: 17 },
        selected_courses: [
          "COMMON101",
          ...Array.from(
            { length: 12 },
            (_, i) => `COURSE${String(i + 1).padStart(2, "0")}`,
          ),
          "GAP999",
          "A",
          "B",
          "C",
        ],
      };
    else throw new Error(`Unexpected offline request ${path}`);
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  const fontLoaded = await page.evaluate(async () => {
    const fonts = await document.fonts.load(
      '16px "Noto Sans"',
      "Nhận định tổng quan Đối chiếu",
    );
    return fonts.length > 0 && fonts.every((font) => font.status === "loaded");
  });
  expect(fontLoaded).toBe(true);
  const result = page.locator(".career-results");
  const summary = result.locator(".career-summary");
  await expect(summary.locator(".summary-related h3")).toHaveCSS(
    "color",
    "rgb(122, 75, 0)",
  );
  await expect(
    summary.locator(".summary-related .finding-link").first(),
  ).toHaveCSS("background-color", "rgb(255, 248, 225)");
  await expect(result.locator(".analysis-related summary").first()).toHaveCSS(
    "background-color",
    "rgb(255, 248, 225)",
  );
  const heading = result.getByRole("heading", {
    name: "Kết quả đối chiếu với nhóm nghề",
    exact: true,
  });
  await expect(heading).toBeFocused();
  const radar = summary.locator(".career-radar");
  await expect(radar).toBeVisible();
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
  const overallSize = await radar
    .locator(".radar-overall strong")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  const headingSize = await heading.evaluate((el) =>
    parseFloat(getComputedStyle(el).fontSize),
  );
  expect(overallSize).toBeGreaterThan(headingSize);
  await page.screenshot({
    path: `/tmp/skillbridge-results-viewport-${testInfo.project.name}.png`,
  });
  await expect(summary).toContainText("AI & Data Platform Engineer");
  await expect(summary).toContainText("17 môn đã chọn");
  const conclusion = summary.locator(".conclusion-text");
  await expect(conclusion).toHaveText(longCareerComparison.conclusion);
  const lineHeight = await conclusion.evaluate((el) =>
    parseFloat(getComputedStyle(el).lineHeight),
  );
  expect((await conclusion.boundingBox())!.height).toBeGreaterThan(
    lineHeight * 4,
  );
  const textStyle = await conclusion.evaluate((el) => ({
    overflow: getComputedStyle(el).overflow,
    lineClamp: getComputedStyle(el).webkitLineClamp,
    font: getComputedStyle(el).fontFamily,
    height: el.clientHeight,
    scrollHeight: el.scrollHeight,
  }));
  expect(textStyle.overflow).toBe("visible");
  expect(textStyle.lineClamp).toBe("none");
  expect(textStyle.font).toContain("Noto Sans");
  expect(textStyle.scrollHeight).toBeLessThanOrEqual(textStyle.height + 1);
  await expect(
    summary.getByRole("button", { name: /Đọc đầy đủ|Xem thêm|Thu gọn/ }),
  ).toHaveCount(0);
  const conclusionBox = (await summary
    .locator(".result-conclusion")
    .boundingBox())!;
  const highlightsBox = (await summary
    .locator(".summary-highlights")
    .boundingBox())!;
  expect(
    highlightsBox.y - conclusionBox.y - conclusionBox.height,
  ).toBeLessThanOrEqual(21);
  await expect(radar.locator("details")).toHaveCount(0);
  const axisDetails = result.locator(".radar-details");
  await expect(axisDetails).toHaveAttribute("open", "");
  await expect(axisDetails.locator(".radar-axis-detail")).toHaveCount(5);
  await expect(
    axisDetails.getByText(longCareerComparison.radar!.overall_comment),
  ).toBeVisible();
  for (const axis of longCareerComparison.radar!.axes) {
    await expect(
      axisDetails.getByText(axis.description, { exact: true }),
    ).toBeVisible();
    await expect(
      axisDetails.getByText(axis.comment, { exact: true }),
    ).toBeVisible();
  }
  await axisDetails.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(axisDetails).not.toHaveAttribute("open");
  await page.keyboard.press("Space");
  await expect(axisDetails).toHaveAttribute("open", "");
  const analysis = result.locator(".career-analysis");
  await expect(analysis.locator("details[open]")).toHaveCount(0);
  await expect(
    analysis.getByText(longCareerComparison.overview),
  ).not.toBeVisible();
  await expect(
    summary.getByRole("button", { name: /^Nhóm nội dung/ }),
  ).toHaveCount(12);
  await expect(
    summary.getByRole("button", { name: /^Khoảng trống \d/ }),
  ).toHaveCount(7);
  expect((await axisDetails.boundingBox())!.y).toBeLessThan(
    (await analysis.boundingBox())!.y,
  );
  const target = longCareerComparison.related_content[10];
  const jump = summary.getByRole("button", {
    name: target.title,
    exact: true,
    includeHidden: true,
  });
  await jump.focus();
  await page.keyboard.press("Enter");
  const detail = analysis.locator("details").filter({
    has: page.getByRole("heading", {
      name: target.title,
      exact: true,
      includeHidden: true,
    }),
  });
  await expect(detail).toHaveAttribute("open", "");
  await expect(detail.locator("summary")).toBeFocused();
  expect(await detail.locator(".verbatim").textContent()).toBe(target.comment);
  await expect(detail.locator(".course-reference")).toHaveText([
    "COURSE11",
    "COMMON101",
  ]);
  await page.keyboard.press("Space");
  await expect(detail).not.toHaveAttribute("open");
  await page.keyboard.press("Enter");
  await expect(detail).toHaveAttribute("open", "");
  await result.getByRole("button", { name: "Mở tất cả", exact: true }).click();
  await expect(analysis.locator("details[open]")).toHaveCount(20);
  const texts = await analysis
    .locator(".analysis-content > .verbatim")
    .allTextContents();
  expect(texts).toEqual([
    longCareerComparison.overview,
    ...longCareerComparison.related_content.map((f) => f.comment),
    ...longCareerComparison.gaps.map((f) => f.comment),
  ]);
  await result
    .getByRole("button", { name: "Thu gọn tất cả", exact: true })
    .click();
  await expect(analysis.locator("details[open]")).toHaveCount(0);
  await expect(axisDetails).toHaveAttribute("open", "");
  await expect(result.getByRole("table")).toHaveCount(0);
  await expect(result.getByText("GÓC NHÌN TỪ DẪN CHỨNG")).toHaveCount(0);
  expect(await result.innerText()).not.toMatch(/%|CLO|enriched|covered/);
  expect(await page.locator("body").innerText()).not.toContain(token);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  const order = await page
    .locator(".comparison-section, .chat-section")
    .evaluateAll((nodes) => nodes.map((n) => n.className));
  expect(order).toEqual(["comparison-section career-results", "chat-section"]);
  const preservedReads = reads.length;
  await result.getByRole("button", { name: "Mở tất cả", exact: true }).click();
  await result
    .getByRole("button", { name: "Thu gọn tất cả", exact: true })
    .click();
  expect(reads.length).toBe(preservedReads);
  expect(posts).toHaveLength(0);
  await heading.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `/tmp/skillbridge-results-ui-${testInfo.project.name}.png`,
    fullPage: true,
  });
});
