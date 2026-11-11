import { useEffect, useRef } from "react";
import type { Catalog, Course } from "../types";
import {
  semestersFor,
  selectCourse,
  selectSemester,
  changeCombo,
} from "../selection";
export const courseName = (course: Course) =>
  course.name.vi || course.name.en || course.name.full || course.course_code;
function GroupCheckbox({
  checked,
  mixed,
  label,
  disabled,
  onChange,
}: {
  checked: boolean;
  mixed: boolean;
  label: string;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (input.current) input.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <input
      ref={input}
      type="checkbox"
      aria-label={label}
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
    />
  );
}
export function CourseSelection({
  catalog,
  selected,
  combo,
  onChange,
  onCombo,
  busy,
}: {
  catalog: Catalog;
  selected: string[];
  combo: string;
  onChange: (codes: string[]) => void;
  onCombo: (combo: string) => void;
  busy: boolean;
}) {
  const rows = semestersFor(catalog, combo);
  return (
    <section className="course-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">01 / MÔN HỌC</span>
          <h2>Hành trình học tập của bạn</h2>
        </div>
        <span className="pill selection-count" role="status">
          {selected.length} môn đã chọn
        </span>
      </div>
      <p className="muted">
        Chọn kỳ để tích nhanh các môn. Các kỳ trước sẽ được chọn cùng.
      </p>
      <fieldset className="combo-choice">
        <legend>COMBO chuyên ngành</legend>
        {catalog.semester_map.combos.map((c) => (
          <label className={combo === c.name ? "active" : ""} key={c.name}>
            <input
              type="radio"
              name="combo"
              value={c.name}
              checked={combo === c.name}
              disabled={busy}
              onChange={() => {
                onChange(changeCombo(selected, catalog, combo, c.name));
                onCombo(c.name);
              }}
            />
            {c.name}
          </label>
        ))}
      </fieldset>
      <div className="semester-list">
        {rows.map((row) => {
          const count = row.course_codes.filter((c) =>
            selected.includes(c),
          ).length;
          return (
            <section
              className={`semester-card ${count ? "has-selection" : ""}`}
              key={row.semester}
            >
              <div className="semester-heading">
                <label>
                  <GroupCheckbox
                    label={`Chọn học kỳ ${row.semester}`}
                    checked={count > 0 && count === row.course_codes.length}
                    mixed={count > 0 && count < row.course_codes.length}
                    disabled={busy}
                    onChange={(checked) =>
                      onChange(
                        selectSemester(selected, rows, row.semester, checked),
                      )
                    }
                  />
                  <strong>Học kỳ {row.semester}</strong>
                </label>
                <span>
                  {count}/{row.course_codes.length} môn
                </span>
              </div>
              <div className="semester-courses">
                {row.course_codes.map((code) => {
                  const course = catalog.courses.find(
                    (c) => c.course_code === code,
                  );
                  return (
                    <label
                      key={code}
                      className={`course-row ${selected.includes(code) ? "selected" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(code)}
                        disabled={busy}
                        aria-label={`${code}${course ? ` — ${courseName(course)}` : ""}`}
                        onChange={(e) =>
                          onChange(
                            selectCourse(
                              selected,
                              rows,
                              code,
                              e.target.checked,
                            ),
                          )
                        }
                      />
                      <span>
                        <strong>{code}</strong>
                        <span className="course-name">
                          {course && courseName(course) !== code
                            ? courseName(course)
                            : ""}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
      {!combo && (
        <p className="combo-hint">Chọn COMBO để xem các môn học kỳ 5–9.</p>
      )}
    </section>
  );
}
