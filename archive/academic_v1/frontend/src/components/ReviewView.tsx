import type { AcademicProfile, Evidence, Review } from "../types";
export function EvidenceList({
  evidence,
  profile,
}: {
  evidence: Evidence[];
  profile: AcademicProfile;
}) {
  if (!evidence.length)
    return (
      <p className="muted">Không có tham chiếu học thuật trong nội dung này.</p>
    );
  return (
    <div className="evidence-list">
      {evidence.map((e, i) => {
        const course = profile.courses.find(
          (c) => c.course_code === e.course_code,
        );
        const clo = course?.clos.find((c) => c.clo === e.clo);
        const metadata =
          e.metadata_field && course?.metadata?.[e.metadata_field];
        return (
          <details key={`${e.course_code}-${e.clo || e.metadata_field}-${i}`}>
            <summary>
              {e.course_code} / {e.clo || `metadata.${e.metadata_field}`}
            </summary>
            {clo && (
              <p>
                {clo.description}
                <br />
                <small>
                  Điểm {clo.score ?? "chưa đánh giá"} · {clo.achievement}
                </small>
              </p>
            )}
            {typeof metadata === "string" && (
              <p className="verbatim">
                {metadata}
                <br />
                <small>
                  Ngữ cảnh curriculum; chưa xác nhận việc cá nhân đã sử dụng
                  công cụ.
                </small>
              </p>
            )}
          </details>
        );
      })}
    </div>
  );
}
export function ReviewView({
  review,
  profile,
}: {
  review: Review;
  profile: AcademicProfile;
}) {
  return (
    <section>
      <div className="eyebrow">06 / INITIAL ACADEMIC REVIEW</div>
      <h1>Kiến thức học thuật & JD</h1>
      <span className="pill">{review.review_type}</span>
      <p className="verbatim review-overview">{review.overview}</p>
      {review.requirement_reviews.length === 0 && (
        <p>Review không có requirement reviews.</p>
      )}
      {review.requirement_reviews.map((r, i) => (
        <article className="requirement" key={i}>
          <div className="requirement-heading">
            <h2>{r.jd_requirement}</h2>
            <span className={`pill coverage-${r.coverage}`}>{r.coverage}</span>
          </div>
          {r.coverage === "not_evidenced" && (
            <small>
              Chưa có bằng chứng học thuật trong hồ sơ; không kết luận bạn thiếu
              kỹ năng.
            </small>
          )}
          <p className="verbatim">{r.comment}</p>
          <EvidenceList evidence={r.evidence} profile={profile} />
        </article>
      ))}
      <div className="conclusion">
        <h2>Kết luận của Review</h2>
        <p className="verbatim">{review.conclusion}</p>
      </div>
    </section>
  );
}
