import { config } from "./config";
import type { SessionPayload } from "./types";

export interface Workspace {
  profileId: string;
  token: string;
  sessionId?: string;
  keepInTab: boolean;
  creation?: { key: string; payload: SessionPayload };
  chat?: { key: string; message: string };
}
const storageKey = "skillbridge.workspace.v1";
export function readWorkspace(): Workspace | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    const w = raw?.workspace;
    if (
      raw?.baseUrl !== config.baseUrl ||
      !w?.keepInTab ||
      typeof w.profileId !== "string" ||
      typeof w.token !== "string" ||
      !w.profileId ||
      !w.token
    )
      return null;
    if (w.sessionId !== undefined && typeof w.sessionId !== "string")
      return null;
    if (
      w.creation &&
      (typeof w.creation.key !== "string" ||
        w.creation.payload?.profile_id !== w.profileId ||
        typeof w.creation.payload?.job_description !== "string")
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
