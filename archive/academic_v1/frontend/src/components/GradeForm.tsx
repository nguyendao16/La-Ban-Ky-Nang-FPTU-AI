import { useRef, useState } from "react";
import { api } from "../api";
import type { CourseDetail, CreatedProfile, GradeEntry } from "../types";
import { courseName } from "./CourseSelection";
import { Feedback } from "./Feedback";
const fieldKey = (code: string, category: string) =>
  JSON.stringify([code, category]);
export function GradeForm({
  details,
  curriculum,
  onCreated,
  onBack,
}: {
  details: CourseDetail[];
  curriculum: string;
  onCreated: (profile: CreatedProfile) => void;
  onBack: () => void;
}) {
  const [scores, setScores] = useState<Record<string, string>>({});
  const [invalid, setInvalid] = useState<string[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    const bad: string[] = [];
    const grades: GradeEntry[] = [];
    for (const course of details)
      for (const a of course.assessments || []) {
        const key = fieldKey(course.course_code, a.category),
          raw = scores[key] ?? "",
          grade = Number(raw);
        if (!raw.trim() || !Number.isFinite(grade) || grade < 0 || grade > 10)
          bad.push(key);
        else
          grades.push({
            course_code: course.course_code,
            category: a.category,
            grade,
          });
      }
    setInvalid(bad);
    if (bad.length) {
      setError(
        "Nhập đủ điểm từ 0 đến 10 cho mọi assessment. Điểm 0 hợp lệ; ô trống chưa có điểm.",
      );
      return;
    }
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await api.createProfile({
          curriculum_code: curriculum,
          selected_courses: details.map((c) => c.course_code),
          grades,
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  return (
    <section>
      <div className="eyebrow">02 / ĐIỂM ASSESSMENT</div>
      <h1>Ghi lại kết quả học tập</h1>
      <p className="intro">
        Thang điểm 0–10. Nhập đủ assessments; backend sẽ tính CLO theo mapping
        gốc.
      </p>
      <form onSubmit={submit} noValidate>
        {details.map((course) => (
          <fieldset key={course.course_code} disabled={busy}>
            <legend>
              {course.course_code} · {courseName(course.catalog)}
            </legend>
            <div className="assessment-list">
              {course.assessments?.map((a) => {
                const key = fieldKey(course.course_code, a.category);
                return (
                  <label key={a.category} className="assessment-row">
                    <span>
                      <strong>{a.category}</strong>
                      <small>
                        Trọng số {a.weight} · Part {a.part} · {a.clo}
                      </small>
                    </span>
                    <input
                      type="number"
                      inputMode="decimal"
                      min="0"
                      max="10"
                      step="any"
                      placeholder="0–10"
                      aria-label={`${course.course_code} · ${a.category}`}
                      aria-invalid={invalid.includes(key)}
                      value={scores[key] ?? ""}
                      onChange={(e) =>
                        setScores((s) => ({ ...s, [key]: e.target.value }))
                      }
                    />
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
        <Feedback error={error} />
        <div className="actions">
          <button type="button" disabled={busy} onClick={onBack}>
            ← Chọn lại môn
          </button>
          <button className="primary" disabled={busy}>
            {busy ? "Đang tạo hồ sơ…" : "Tạo hồ sơ học thuật"}
          </button>
        </div>
      </form>
    </section>
  );
}
