import { useEffect, useId, useRef, type ReactNode } from "react";
import type { Comparison, Evidence } from "../types";
import { CareerRadar, CareerRadarDetails } from "./CareerRadar";
import { EvidenceList } from "./EvidenceList";

const labels = {
  covered: "Được bao phủ",
  related: "Có liên quan",
  not_evidenced: "Chưa có bằng chứng đối chiếu",
};
type Finding = {
  id: string;
  title: string;
  comment: string;
  evidence: Evidence[];
  coverage?: keyof typeof labels;
};

function FindingLinks({
  title,
  findings,
  group,
  reveal,
}: {
  title: string;
  findings: Finding[];
  group: string;
  reveal: (id: string) => void;
}) {
  return (
    <div className={`summary-findings summary-${group}`}>
      <h3>{title}</h3>
      {!findings.length ? (
        <p className="muted">Kết quả chưa ghi nhận mục nào trong nhóm này.</p>
      ) : (
        <ul>
          {findings.map((finding) => (
            <li key={finding.id}>
              <button
                type="button"
                className="finding-link"
                onClick={() => reveal(finding.id)}
              >
                {finding.title}
                {finding.coverage && (
                  <span
                    className={`finding-status finding-${finding.coverage}`}
                  >
                    {labels[finding.coverage]}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ComparisonView({
  comparison,
  careerTitle,
  courseCount,
  fixedCareerAxes = false,
  recommendations,
}: {
  comparison: Comparison;
  careerTitle?: string;
  courseCount: number;
  fixedCareerAxes?: boolean;
  recommendations?: ReactNode;
}) {
  const career = comparison.comparison_type === "career_comparison";
  const radar = "radar" in comparison ? comparison.radar : undefined;
  const groups: { key: string; title: string; findings: Finding[] }[] = career
    ? [
        {
          key: "related",
          title: "Nội dung học tập liên quan",
          findings: comparison.related_content.map((f, i) => ({
            ...f,
            id: `related-${i}`,
          })),
        },
        {
          key: "gaps",
          title: "Khoảng trống nội dung",
          findings: comparison.gaps.map((f, i) => ({ ...f, id: `gaps-${i}` })),
        },
      ]
    : [
        {
          key: "requirements",
          title: "Yêu cầu trong JD",
          findings: comparison.requirement_reviews.map((r, i) => ({
            id: `requirements-${i}`,
            title: r.jd_requirement,
            comment: r.comment,
            evidence: r.evidence,
            coverage: r.coverage,
          })),
        },
      ];
  const highlights = [
    {
      key: "related",
      title: "Nội dung liên quan",
      findings: career
        ? groups[0].findings
        : groups[0].findings.filter((f) => f.coverage !== "not_evidenced"),
    },
    {
      key: "gaps",
      title: "Khoảng trống được ghi nhận",
      findings: career
        ? groups[1].findings
        : groups[0].findings.filter((f) => f.coverage === "not_evidenced"),
    },
  ];
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const details = useRef<Record<string, HTMLDetailsElement | null>>({});
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView?.({ block: "start" });
  }, []);
  function reveal(id: string) {
    const item = details.current[id];
    if (!item) return;
    item.open = true;
    item.querySelector("summary")?.focus();
    item.scrollIntoView?.({ block: "start" });
  }
  function toggleAll(open: boolean) {
    for (const detail of Object.values(details.current))
      if (detail) detail.open = open;
  }
  return (
    <section
      className={`comparison-section career-results${career ? "" : " jd-results"}`}
      aria-labelledby={`${id}-heading`}
    >
      <header className="career-summary">
        <span className="eyebrow">
          {career
            ? "02 / GÓC NHÌN NGHỀ NGHIỆP · CWA 18398:2026"
            : "02 / ĐỐI CHIẾU VỚI JD"}
        </span>
        <h1 id={`${id}-heading`} ref={heading} tabIndex={-1}>
          {career
            ? "Kết quả đối chiếu với nhóm nghề"
            : "Kết quả đối chiếu với JD"}
        </h1>
        <div className="result-context">
          <p className="target-heading">
            <span>{career ? "Nhóm nghề mục tiêu" : "Mục tiêu đối chiếu"}</span>
            <strong>
              {career
                ? (careerTitle ?? "Nhóm nghề đã chọn")
                : "Mô tả công việc đã nhập"}
            </strong>
          </p>
          <span className="result-course-count">{courseCount} môn đã chọn</span>
        </div>
        <div className={radar ? "executive-grid has-radar" : "executive-grid"}>
          <div className="executive-narrative">
            <div className="result-conclusion">
              <h2>Nhận định tổng quan</h2>
              <p className="verbatim conclusion-text">
                {comparison.conclusion}
              </p>
            </div>
            <div className="summary-highlights">
              {highlights.map((group) => (
                <FindingLinks
                  key={group.key}
                  title={group.title}
                  findings={group.findings}
                  group={group.key}
                  reveal={reveal}
                />
              ))}
            </div>
          </div>
          {radar ? (
            <CareerRadar
              radar={radar}
              target={career ? "career" : "jd"}
              fixedAxes={career && fixedCareerAxes}
            />
          ) : (
            <p className="radar-unavailable">
              Kết quả này chưa có dữ liệu radar.
            </p>
          )}
        </div>
        {!career && !comparison.requirement_reviews.length && (
          <p className="muted">
            JD chưa có yêu cầu nội dung phù hợp để đối chiếu.
          </p>
        )}
        <p className="summary-scope">
          Đối chiếu các môn đã chọn với mục tiêu nghề nghiệp. Thiếu bằng chứng
          trong dữ liệu không đồng nghĩa chương trình không giảng dạy nội dung
          đó.
        </p>
      </header>
      {recommendations}
      {radar && <CareerRadarDetails radar={radar} />}
      <section className="career-analysis" aria-labelledby={`${id}-analysis`}>
        <div className="result-section-heading">
          <div>
            <span className="eyebrow">ĐỌC SÂU HƠN</span>
            <h2 id={`${id}-analysis`}>Phân tích chi tiết</h2>
          </div>
          <div className="detail-controls">
            <button type="button" onClick={() => toggleAll(true)}>
              Mở tất cả
            </button>
            <button type="button" onClick={() => toggleAll(false)}>
              Thu gọn tất cả
            </button>
          </div>
        </div>
        <details
          className="analysis-item analysis-context"
          ref={(node) => {
            details.current.context = node;
          }}
        >
          <summary>Bối cảnh đối chiếu</summary>
          <div className="analysis-content">
            <p className="verbatim">{comparison.overview}</p>
          </div>
        </details>
        {groups.map((group) => (
          <div
            className={`analysis-group analysis-${group.key}`}
            key={group.key}
          >
            <h3>{group.title}</h3>
            {!group.findings.length && (
              <p className="muted">
                Kết quả chưa ghi nhận mục nào trong nhóm này.
              </p>
            )}
            {group.findings.map((finding) => (
              <details
                className="analysis-item"
                key={finding.id}
                ref={(node) => {
                  details.current[finding.id] = node;
                }}
              >
                <summary>
                  <h4>{finding.title}</h4>
                  {finding.coverage && (
                    <span className={`pill coverage-${finding.coverage}`}>
                      {labels[finding.coverage]}
                    </span>
                  )}
                </summary>
                <div className="analysis-content">
                  <p className="verbatim">{finding.comment}</p>
                  <EvidenceList evidence={finding.evidence} />
                </div>
              </details>
            ))}
          </div>
        ))}
      </section>
    </section>
  );
}
