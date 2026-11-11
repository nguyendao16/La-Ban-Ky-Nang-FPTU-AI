import { expect, it, vi } from "vitest";
import { readWorkspace, saveWorkspace } from "./workspace";
it("keeps capabilities in memory by default and only persists with consent", () => {
  const w = { profileId: "p", token: "secret-capability", keepInTab: false };
  saveWorkspace(w);
  expect(readWorkspace()).toBeNull();
  expect(sessionStorage.length).toBe(0);
  saveWorkspace({
    ...w,
    keepInTab: true,
    sessionId: "s",
    creation: {
      key: "stable",
      payload: { profile_id: "p", job_description: "JD" },
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
  sessionStorage.setItem("skillbridge.workspace.v1", "{bad");
  expect(readWorkspace()).toBeNull();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Storage disabled");
  });
  expect(saveWorkspace({ profileId: "p", token: "t", keepInTab: true })).toBe(
    false,
  );
});
