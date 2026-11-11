import { expect, it, vi } from "vitest";
import { readWorkspace, saveWorkspace } from "./workspace";
it("ignores the retired tab namespace without deleting its data", () => {
  sessionStorage.setItem(
    "skillbridge.workspace.v1",
    JSON.stringify({
      workspace: { profileId: "old", token: "old-capability", keepInTab: true },
    }),
  );
  expect(readWorkspace()).toBeNull();
  expect(sessionStorage.getItem("skillbridge.workspace.v1")).toContain(
    "old-capability",
  );
});
it("keeps capabilities in memory by default and only persists with consent", () => {
  const w = { selectionId: "p", token: "secret-capability", keepInTab: false };
  saveWorkspace(w);
  expect(readWorkspace()).toBeNull();
  expect(sessionStorage.length).toBe(0);
  saveWorkspace({
    ...w,
    keepInTab: true,
    sessionId: "s",
    creation: {
      key: "stable",
      payload: { selection_id: "p", job_description: "JD" },
    },
    chat: { key: "chat-key", message: "question" },
  });
  expect(readWorkspace()).toMatchObject({
    token: "secret-capability",
    sessionId: "s",
    creation: { key: "stable" },
    chat: { key: "chat-key" },
  });
  saveWorkspace(null);
  expect(readWorkspace()).toBeNull();
});
it("rejects corrupt saved state and signals failure to persist before dispatch", () => {
  sessionStorage.setItem("skillbridge.course-jd.workspace.v1", "{bad");
  expect(readWorkspace()).toBeNull();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Storage disabled");
  });
  expect(saveWorkspace({ selectionId: "p", token: "t", keepInTab: true })).toBe(
    false,
  );
});
