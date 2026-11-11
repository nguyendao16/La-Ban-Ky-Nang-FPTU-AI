import { describe, it, expect } from "vitest";
import {
  semestersFor,
  selectCourse,
  selectSemester,
  changeCombo,
} from "./selection";
import { catalog } from "./test/fixtures";
describe("semester prefix selection", () => {
  const rows = semestersFor(catalog, "Applied Data Science");
  it("selects every previous semester for an individual later course", () => {
    expect(selectCourse([], rows, "COMBOA", true)).toEqual([
      "TEST101",
      "OTHER201",
      "MID201",
      "LATE301",
      "FOUR401",
      "COMBOA",
    ]);
  });
  it("selects all rows through a semester, including unmapped courses", () => {
    const selected = selectSemester([], rows, 9, true);
    expect(selected).toEqual(rows.flatMap((r) => r.course_codes));
    expect(selected).toContain("EXTRA");
  });
  it("deselects every later semester after removing one previous course", () => {
    expect(
      selectCourse(selectSemester([], rows, 9, true), rows, "OTHER201", false),
    ).toEqual(["TEST101"]);
  });
  it("deselects this and all later semesters while retaining earlier ones", () => {
    expect(
      selectSemester(selectSemester([], rows, 9, true), rows, 3, false),
    ).toEqual(["TEST101", "OTHER201", "MID201"]);
  });
  it("replaces selected track-specific courses and preserves prefix/common courses", () => {
    const selected = selectSemester([], rows, 9, true);
    const next = changeCombo(
      selected,
      catalog,
      "Applied Data Science",
      "AI application",
    );
    expect(next).toEqual(
      semestersFor(catalog, "AI application").flatMap((r) => r.course_codes),
    );
    expect(next).not.toContain("COMBOA");
    expect(
      changeCombo(next, catalog, "AI application", "Applied Data Science"),
    ).toEqual(selected);
  });
  it("preserves partial selection in the last semester during a track change", () => {
    const selected = selectCourse([], rows, "COMBOA", true);
    expect(
      changeCombo(selected, catalog, "Applied Data Science", "AI application"),
    ).toEqual([
      "TEST101",
      "OTHER201",
      "MID201",
      "LATE301",
      "FOUR401",
      "COMBOB",
    ]);
  });
});
