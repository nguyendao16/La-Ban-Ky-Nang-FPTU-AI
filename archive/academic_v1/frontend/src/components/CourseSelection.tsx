import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Catalog, Course, CourseDetail } from "../types";
import { Feedback, Loading } from "./Feedback";
export const courseName = (course: Course) =>
  course.name.vi || course.name.en || course.name.full || course.course_code;
export const usable = (course: Course) =>
  course.availability.metadata &&
  course.availability.assessments &&
  course.availability.clos;
export function CourseSelection({
  onContinue,
}: {
  onContinue: (catalog: Catalog, details: CourseDetail[]) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    api.listCourses(abort.signal).then(setCatalog).catch(setError);
    return () => {
      abort.abort();
      controller.current?.abort();
    };
  }, []);
  const toggle = (code: string) =>
    setSelected((s) =>
      s.includes(code) ? s.filter((c) => c !== code) : [...s, code],
    );
  async function proceed() {
    if (!catalog || busy) return;
    if (!selected.length) {
      setError("Chọn ít nhất một môn có đủ dữ liệu.");
      return;
    }
    if (
      catalog.selection_constraints.exclusive_slots.some(
        (s) => s.course_codes.filter((c) => selected.includes(c)).length > 1,
      )
    ) {
      setError("Chỉ chọn một môn trong mỗi COMBO slot.");
      return;
    }
    setBusy(true);
    setError(null);
    controller.current = new AbortController();
    try {
      const details = await Promise.all(
        selected.map((c) =>
          api.getCourse(c, catalog.curriculum_code, controller.current!.signal),
        ),
      );
      if (details.some((d) => !d.assessments?.length))
        throw "Môn đã chọn chưa có assessments dùng được.";
      onContinue(catalog, details);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }
  if (!catalog)
    return (
      <section>
        <h1>Chọn môn đã học</h1>
        {error ? (
          <>
            <Feedback error={error} />
            <button
              onClick={() => {
                setError(null);
                api.listCourses().then(setCatalog).catch(setError);
              }}
            >
              Tải lại catalog
            </button>
          </>
        ) : (
          <Loading>Đang tải catalog…</Loading>
        )}
      </section>
    );
  const comboCodes = new Set(
    catalog.selection_constraints.exclusive_slots.flatMap(
      (s) => s.course_codes,
    ),
  );
  const normal = catalog.courses.filter(
    (c) =>
      !comboCodes.has(c.course_code) &&
      `${c.course_code} ${courseName(c)}`
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
  );
  return (
    <section>
      <div className="eyebrow">01 / HỒ SƠ HỌC THUẬT</div>
      <h1>Những môn bạn đã học</h1>
      <p className="intro">
        Chọn các môn có điểm assessment để tạo hồ sơ CLO của riêng bạn.
      </p>
      <div className="catalog-meta">
        <span className="pill">{catalog.curriculum_code}</span>
        <span>{catalog.courses.length} môn trong nguồn curriculum</span>
      </div>
      <label className="search">
        Tìm môn học
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Mã môn hoặc tên môn"
        />
      </label>
      {catalog.courses.length === 0 && <p>Catalog chưa có môn học.</p>}
      <div className="course-grid">
        {normal.map((c) => (
          <label
            key={c.course_code}
            className={`course-card ${selected.includes(c.course_code) ? "selected" : ""} ${!usable(c) ? "unavailable" : ""}`}
          >
            <input
              type="checkbox"
              disabled={!usable(c) || busy}
              checked={selected.includes(c.course_code)}
              onChange={() => toggle(c.course_code)}
              aria-label={`${c.course_code} — ${courseName(c)}`}
            />
            <div>
              <strong>{c.course_code}</strong>
              <span className="course-name">{courseName(c)}</span>
              <small>
                Học kỳ {c.semester} · {c.credits ?? "—"} tín chỉ
              </small>
              {c.combo && (
                <small>{c.combo.title || c.combo.name || c.combo.code}</small>
              )}
              <small>
                {usable(c)
                  ? "Có assessments"
                  : "Chưa đủ metadata / CLO / assessments"}
              </small>
            </div>
          </label>
        ))}
      </div>
      {normal.length === 0 && catalog.courses.length > 0 && (
        <p>Không có môn phù hợp với tìm kiếm.</p>
      )}
      {catalog.selection_constraints.exclusive_slots.length > 0 && (
        <div className="combo-panel">
          <h2>Các học phần COMBO</h2>
          <p>
            Mỗi slot chọn tối đa một môn. Các lựa chọn lấy từ curriculum source.
          </p>
          {catalog.selection_constraints.exclusive_slots.map((slot) => (
            <label key={slot.slot_identifier}>
              COMBO {slot.slot_identifier}
              <select
                aria-label={`COMBO ${slot.slot_identifier}`}
                disabled={busy}
                value={
                  selected.find((c) => slot.course_codes.includes(c)) || ""
                }
                onChange={(e) => {
                  const code = e.target.value;
                  setSelected((s) => [
                    ...s.filter((c) => !slot.course_codes.includes(c)),
                    ...(code ? [code] : []),
                  ]);
                }}
              >
                <option value="">Chưa chọn</option>
                {slot.course_codes.map((code) => {
                  const c = catalog.courses.find((c) => c.course_code === code);
                  return (
                    c && (
                      <option key={code} value={code} disabled={!usable(c)}>
                        {code} — {courseName(c)} · {c.combo?.name || ""}
                        {!usable(c) ? " (chưa đủ dữ liệu)" : ""}
                      </option>
                    )
                  );
                })}
              </select>
            </label>
          ))}
        </div>
      )}
      {catalog.selection_constraints.ambiguous_slots.length > 0 && (
        <p className="notice">
          Một số COMBO slots chưa có ràng buộc xác thực. Backend sẽ kiểm tra
          selection khi tạo hồ sơ.
        </p>
      )}
      <Feedback error={error} />
      <div className="actions">
        <span>
          Đã chọn <strong>{selected.length}</strong> môn
        </span>
        <button className="primary" disabled={busy} onClick={proceed}>
          {busy ? "Đang tải assessments…" : "Tiếp tục nhập điểm →"}
        </button>
      </div>
    </section>
  );
}
