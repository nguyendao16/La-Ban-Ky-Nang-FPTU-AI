import type { Evidence } from "../types";

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return evidence.length ? (
    <div className="evidence-list">
      <span className="muted">Môn tham chiếu</span>
      {evidence.map((e) => (
        <span className="course-reference" key={e.course_code}>
          {e.course_code}
        </span>
      ))}
    </div>
  ) : null;
}
