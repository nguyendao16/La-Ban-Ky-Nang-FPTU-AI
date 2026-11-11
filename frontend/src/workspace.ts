import { config } from "./config";
import type { SessionPayload } from "./types";

export interface Workspace {
  selectionId: string;
  token: string;
  sessionId?: string;
  keepInTab: boolean;
  mode?: "cwa" | "jd";
  creation?: { key: string; payload: SessionPayload };
  chat?: { key: string; message: string };
  recommendations?: { key: string };
}
const storageKey = "skillbridge.course-jd.workspace.v1";
export function readWorkspace(): Workspace | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    const w = raw?.workspace;
    if (
      raw?.baseUrl !== config.baseUrl ||
      !w?.keepInTab ||
      typeof w.selectionId !== "string" ||
      typeof w.token !== "string" ||
      !w.selectionId ||
      !w.token
    )
      return null;
    if (w.sessionId !== undefined && typeof w.sessionId !== "string")
      return null;
    if (
      w.creation &&
      (typeof w.creation.key !== "string" ||
        w.creation.payload?.selection_id !== w.selectionId ||
        !(
          (typeof w.creation.payload?.job_description === "string" &&
            w.creation.payload.career_profile_id === undefined) ||
          (typeof w.creation.payload?.career_profile_id === "string" &&
            !!w.creation.payload.career_profile_id &&
            w.creation.payload.job_description === undefined)
        ))
    )
      return null;
    if (w.mode !== undefined && !["cwa", "jd"].includes(w.mode)) return null;
    if (
      w.recommendations &&
      (typeof w.recommendations.key !== "string" ||
        !w.recommendations.key.trim())
    )
      return null;
    if (
      w.chat &&
      (typeof w.chat.key !== "string" || typeof w.chat.message !== "string")
    )
      return null;
    return w as Workspace;
  } catch {
    return null;
  }
}
export function saveWorkspace(workspace: Workspace | null): boolean {
  try {
    if (workspace?.keepInTab)
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ baseUrl: config.baseUrl, workspace }),
      );
    else sessionStorage.removeItem(storageKey);
    return true;
  } catch {
    return !workspace?.keepInTab;
  }
}
export const operationKey = () => crypto.randomUUID();
