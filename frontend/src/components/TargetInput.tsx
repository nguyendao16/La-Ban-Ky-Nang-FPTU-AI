import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import { config } from "../config";
import type { CareerProfile } from "../types";
import type { TargetDraft } from "../target";
import { Feedback, Loading } from "./Feedback";

export function TargetInput({
  value,
  onChange,
  disabled = false,
}: {
  value: TargetDraft;
  onChange: (value: TargetDraft) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  const [profiles, setProfiles] = useState<CareerProfile[] | null>(null);
  const [error, setError] = useState<unknown>();
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    api
      .listCareerProfiles(abort.signal)
      .then((result) => {
        if (!abort.signal.aborted) {
          setProfiles(result.profiles);
          setError(null);
        }
      })
      .catch((err) => {
        if (!abort.signal.aborted) setError(err);
      });
    return () => abort.abort();
  }, [epoch]);
  const selected = profiles?.find(
    (p) => p.profile_id === value.careerProfileId,
  );
  return (
    <>
      <div
        className="target-tabs"
        role="tablist"
        aria-label="Cách chọn công việc mục tiêu"
      >
        {(["cwa", "jd"] as const).map((mode, index) => (
          <button
            key={mode}
            ref={(node) => {
              tabs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`${id}-${mode}-tab`}
            aria-controls={`${id}-${mode}-panel`}
            aria-selected={value.mode === mode}
            tabIndex={value.mode === mode ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange({ ...value, mode })}
            onKeyDown={(event) => {
              const next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? 1
                    : ["ArrowLeft", "ArrowRight"].includes(event.key)
                      ? 1 - index
                      : null;
              if (next !== null) {
                event.preventDefault();
                onChange({ ...value, mode: next ? "jd" : "cwa" });
                tabs.current[next]?.focus();
              }
            }}
          >
            {mode === "cwa" ? "Nhóm nghề CWA" : "Mô tả công việc (JD)"}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${id}-cwa-panel`}
        aria-labelledby={`${id}-cwa-tab`}
        hidden={value.mode !== "cwa"}
      >
        <>
          <p className="muted">
            Chọn một nhóm nghề để khám phá mối liên hệ với các môn đã học.
          </p>
          {!profiles ? (
            <>
              <Feedback error={error} />
              {error ? (
                <button type="button" onClick={() => setEpoch((n) => n + 1)}>
                  Tải lại nhóm nghề
                </button>
              ) : (
                <Loading>Đang tải nhóm nghề…</Loading>
              )}
            </>
          ) : (
            <>
              <label htmlFor={`${id}-career`}>Nhóm nghề mục tiêu</label>
              <select
                id={`${id}-career`}
                value={value.careerProfileId}
                disabled={disabled}
                onChange={(e) =>
                  onChange({ ...value, careerProfileId: e.target.value })
                }
              >
                <option value="">Chọn nghề bạn muốn hướng tới</option>
                {profiles.map((p) => (
                  <option key={p.profile_id} value={p.profile_id}>
                    {p.target?.title ?? p.title}
                  </option>
                ))}
              </select>
              {selected && (
                <details className="career-source">
                  <summary>Xem mô tả nhóm nghề</summary>
                  {selected.target && (
                    <>
                      <p>{selected.target.scope}</p>
                      <ol>
                        {selected.target.axes.map((axis) => (
                          <li key={axis.name}>{axis.name}</li>
                        ))}
                      </ol>
                    </>
                  )}
                  <p className="verbatim">{selected.content}</p>
                </details>
              )}
              <small className="target-note">
                Tham chiếu CWA 18398:2026 · Phân tích nội dung học tập, không
                đánh giá năng lực cá nhân.
              </small>
            </>
          )}
        </>
      </div>
      <div
        role="tabpanel"
        id={`${id}-jd-panel`}
        aria-labelledby={`${id}-jd-tab`}
        hidden={value.mode !== "jd"}
      >
        <>
          <p className="muted">Dán mô tả công việc để bắt đầu đối chiếu.</p>
          <label htmlFor={`${id}-jd`}>Job Description</label>
          <textarea
            id={`${id}-jd`}
            rows={13}
            value={value.jd}
            onChange={(e) => onChange({ ...value, jd: e.target.value })}
            maxLength={config.maxJD}
            disabled={disabled}
            placeholder="Ví dụ: Data Analyst Intern…"
          />
          <small className="character-count">
            {value.jd.length.toLocaleString()}/{config.maxJD.toLocaleString()}{" "}
            ký tự
          </small>
        </>
      </div>
    </>
  );
}
