import type { Catalog, Semester } from "./types";
export const semestersFor = (catalog: Catalog, combo: string): Semester[] => [
  ...catalog.semester_map.common,
  ...(catalog.semester_map.combos.find((c) => c.name === combo)?.semesters ||
    []),
];
const ordered = (selected: Set<string>, rows: Semester[]) =>
  rows.flatMap((r) => r.course_codes.filter((c) => selected.has(c)));
export function selectCourse(
  selected: string[],
  rows: Semester[],
  code: string,
  checked: boolean,
): string[] {
  const row = rows.find((r) => r.course_codes.includes(code));
  if (!row) return selected;
  const next = new Set(selected);
  if (checked) {
    rows
      .filter((r) => r.semester < row.semester)
      .forEach((r) => r.course_codes.forEach((c) => next.add(c)));
    next.add(code);
  } else {
    next.delete(code);
    rows
      .filter((r) => r.semester > row.semester)
      .forEach((r) => r.course_codes.forEach((c) => next.delete(c)));
  }
  return ordered(next, rows);
}
export function selectSemester(
  selected: string[],
  rows: Semester[],
  semester: number,
  checked: boolean,
): string[] {
  const next = new Set(selected);
  rows
    .filter((r) => (checked ? r.semester <= semester : r.semester >= semester))
    .forEach((r) =>
      r.course_codes.forEach((c) => (checked ? next.add(c) : next.delete(c))),
    );
  return ordered(next, rows);
}
export function changeCombo(
  selected: string[],
  catalog: Catalog,
  previous: string,
  next: string,
): string[] {
  const oldRows = semestersFor(catalog, previous),
    newRows = semestersFor(catalog, next);
  const nextCodes = new Set(newRows.flatMap((r) => r.course_codes));
  const replaced = selected
    .map((code) => {
      if (nextCodes.has(code)) return code;
      const old = oldRows.find((r) => r.course_codes.includes(code));
      return old
        ? newRows.find((r) => r.semester === old.semester)?.course_codes[
            old.course_codes.indexOf(code)
          ]
        : undefined;
    })
    .filter((c): c is string => !!c);
  return ordered(new Set(replaced), newRows);
}
