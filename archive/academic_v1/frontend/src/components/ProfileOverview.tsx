import type { Profile } from "../types";
export function ProfileOverview({
  profile,
  onContinue,
}: {
  profile: Profile;
  onContinue?: () => void;
}) {
  return (
    <section>
      <div className="eyebrow">03 / STUDENT ACADEMIC PROFILE</div>
      <h1>Hồ sơ từ bằng chứng học thuật</h1>
      <div className="stats">
        <div>
          <strong>{profile.summary.course_count}</strong>
          <span>Môn đã chọn</span>
        </div>
        <div>
          <strong>{profile.summary.clo_count}</strong>
          <span>CLO trong hồ sơ</span>
        </div>
      </div>
      <p className="notice">
        Điểm và achievement phản ánh kết quả học thuật. Nội dung curriculum mô
        tả phạm vi được học; kinh nghiệm nghề nghiệp chưa được xác minh bằng
        điểm.
      </p>
      <p className="id-label">Profile ID: {profile.profile_id}</p>
      {profile.profile.courses.map((course) => (
        <details key={course.course_code} open>
          <summary>
            {course.course_code} ·{" "}
            {String(course.metadata?.course_name_english || "")}
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>CLO</th>
                  <th>Mô tả</th>
                  <th>Điểm</th>
                  <th>Achievement</th>
                </tr>
              </thead>
              <tbody>
                {course.clos.map((c) => (
                  <tr key={c.clo}>
                    <td>
                      <strong>{c.clo}</strong>
                    </td>
                    <td>{c.description}</td>
                    <td>{c.score === null ? "Chưa đánh giá" : c.score}</td>
                    <td>
                      <span className={`pill achievement-${c.achievement}`}>
                        {c.achievement}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
      <details>
        <summary>Diagnostics từ backend</summary>
        <p>
          Giữ nguyên diagnostics về assessment matching, CLO mapping và weight
          totals.
        </p>
        <pre>{JSON.stringify(profile.diagnostics, null, 2)}</pre>
      </details>
      {onContinue && (
        <div className="actions">
          <span>Hồ sơ được lưu như một snapshot riêng.</span>
          <button className="primary" onClick={onContinue}>
            Phân tích JD →
          </button>
        </div>
      )}
    </section>
  );
}
