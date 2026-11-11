import { config } from "./config";
import type { SessionPayload } from "./types";

export interface TargetDraft {
  mode: "cwa" | "jd";
  careerProfileId: string;
  jd: string;
}
export function targetDraft(
  payload?: SessionPayload,
  mode: "cwa" | "jd" = "cwa",
): TargetDraft {
  return {
    mode: payload?.career_profile_id
      ? "cwa"
      : payload?.job_description !== undefined
        ? "jd"
        : mode,
    careerProfileId: payload?.career_profile_id ?? "",
    jd: payload?.job_description ?? "",
  };
}
export function targetError(target: TargetDraft): string | null {
  if (target.mode === "cwa")
    return target.careerProfileId ? null : "Chọn nhóm nghề bạn muốn hướng tới.";
  return target.jd.trim() && target.jd.length <= config.maxJD
    ? null
    : `Nhập JD từ 1 đến ${config.maxJD} ký tự.`;
}
export function targetPayload(
  selectionId: string,
  target: TargetDraft,
): SessionPayload {
  return target.mode === "cwa"
    ? { selection_id: selectionId, career_profile_id: target.careerProfileId }
    : { selection_id: selectionId, job_description: target.jd };
}
