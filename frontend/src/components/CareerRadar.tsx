import { useId } from "react";
import type { CareerRadarData } from "../types";
import { EvidenceList } from "./EvidenceList";

const formatScore = (value: number) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(value);
const point = (axis: number, radius: number) => {
  const angle = -Math.PI / 2 + (axis * Math.PI * 2) / 5;
  return [200 + Math.cos(angle) * radius, 140 + Math.sin(angle) * radius];
};
const polygon = (scores: number[]) =>
  scores
    .map((score, axis) =>
      point(axis, (score / 5) * 92)
        .map((n) => n.toFixed(2))
        .join(","),
    )
    .join(" ");
function labelLines(name: string) {
  const words = name
    .split(/\s+/)
    .flatMap((word) => word.match(/.{1,11}/gu) ?? []);
  const lines: string[] = [];
  for (const word of words) {
    const last = lines.length - 1;
    if (last >= 0 && `${lines[last]} ${word}`.length <= 11)
      lines[last] += ` ${word}`;
    else lines.push(word);
  }
  return lines.length <= 3 ? lines : [...lines.slice(0, 2), `${lines[2]}…`];
}

function fixedLabelLines(name: string, axis: number) {
  const width = axis === 1 || axis === 4 ? 13 : 20;
  const lines: string[] = [];
  for (const word of name.split(/\s+/)) {
    const last = lines.length - 1;
    if (last >= 0 && `${lines[last]} ${word}`.length <= width)
      lines[last] += ` ${word}`;
    else lines.push(word);
  }
  return lines;
}

export function CareerRadar({
  radar,
  target = "career",
  fixedAxes = false,
}: {
  radar: CareerRadarData;
  target?: "career" | "jd";
  fixedAxes?: boolean;
}) {
  const id = useId();
  const labels = [
    { x: 200, y: 10, anchor: "middle" },
    { x: fixedAxes ? 306 : 314, y: 101, anchor: "start" },
    { x: 274, y: 252, anchor: "middle" },
    { x: 126, y: 252, anchor: "middle" },
    { x: fixedAxes ? 94 : 86, y: 101, anchor: "end" },
  ] as const;
  return (
    <aside
      className={`career-radar${fixedAxes ? " fixed-radar" : ""}`}
      aria-labelledby={`${id}-heading`}
    >
      <h2 id={`${id}-heading`}>Điểm tổng</h2>
      <p className="radar-overall">
        <strong>{formatScore(radar.overall_score)}</strong>
        <span>/5</span>
      </p>
      <p className="radar-score-label">
        {target === "jd"
          ? "Ước tính phù hợp với JD"
          : "Ước tính phù hợp với nhóm nghề"}
      </p>
      <figure>
        <svg
          viewBox="0 0 400 310"
          role="img"
          aria-labelledby={`${id}-title ${id}-description`}
          className="radar-svg"
        >
          <title id={`${id}-title`}>
            {target === "jd"
              ? "Radar 5 trục đối chiếu với JD"
              : "Radar 5 trục đối chiếu nghề nghiệp"}
          </title>
          <desc id={`${id}-description`}>
            Thang điểm 0 đến 5.{" "}
            {radar.axes
              .map((axis) => `${axis.name}: ${formatScore(axis.score)}/5`)
              .join(". ")}
          </desc>
          {[1, 2, 3, 4, 5].map((level) => (
            <polygon
              key={level}
              points={polygon(Array(5).fill(level))}
              className="radar-grid"
            />
          ))}
          {radar.axes.map((_, axis) => {
            const [x, y] = point(axis, 92);
            return (
              <line
                key={axis}
                x1={200}
                y1={140}
                x2={x}
                y2={y}
                className="radar-spoke"
              />
            );
          })}
          {[1, 2, 3, 4, 5].map((level) => (
            <text
              key={level}
              x={205}
              y={140 - (level / 5) * 92 + 4}
              className="radar-tick"
            >
              {level}
            </text>
          ))}
          <polygon
            points={polygon(radar.axes.map((axis) => axis.score))}
            className="radar-shape"
          />
          {radar.axes.map((axis, index) => {
            const [x, y] = point(index, (axis.score / 5) * 92);
            return (
              <circle
                key={index}
                cx={x}
                cy={y}
                r={3.5}
                className="radar-dot"
                data-score={axis.score}
              />
            );
          })}
          {radar.axes.map((axis, index) => (
            <text
              key={index}
              x={labels[index].x}
              y={labels[index].y}
              textAnchor={labels[index].anchor}
              className="radar-axis-label"
            >
              <title>
                {axis.name}: {formatScore(axis.score)}/5
              </title>
              {(fixedAxes
                ? fixedLabelLines(axis.name, index)
                : labelLines(axis.name)
              ).map((line, lineIndex) => (
                <tspan
                  key={lineIndex}
                  x={labels[index].x}
                  dy={lineIndex ? 17 : 0}
                >
                  {line}
                </tspan>
              ))}
            </text>
          ))}
        </svg>
        {target === "jd" && (
          <figcaption>
            5 trục và điểm số do LLM ước tính trên thang 0–5; không đo năng lực
            cá nhân hoặc quyết định tuyển dụng.
          </figcaption>
        )}
      </figure>
    </aside>
  );
}

export function CareerRadarDetails({ radar }: { radar: CareerRadarData }) {
  return (
    <details className="radar-details" open>
      <summary>Chi tiết 5 trục</summary>
      <p className="verbatim radar-rationale">{radar.overall_comment}</p>
      <dl>
        {radar.axes.map((axis, index) => (
          <div key={index} className="radar-axis-detail">
            <dt>
              <span>{axis.name}</span>
              <strong>{formatScore(axis.score)}/5</strong>
            </dt>
            <dd>
              <p className="verbatim">{axis.description}</p>
              <p className="verbatim">{axis.comment}</p>
              <EvidenceList evidence={axis.evidence} />
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
