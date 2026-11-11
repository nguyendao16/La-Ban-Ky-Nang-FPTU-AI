import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "./api";
import { json } from "./test/fixtures";
describe("typed HTTP client", () => {
  it("uses Bearer and stable caller keys; sends only the new message", async () => {
    const fetcher = vi.fn(
      async (
        _url: string,
        _options: {
          headers: Record<string, string>;
          body: string;
          credentials: string;
        },
      ) => json({ message_id: "message-1", reply: "SQL", evidence: [] }),
    );
    vi.stubGlobal("fetch", fetcher);
    const client = new ApiClient("http://local.invalid");
    await client.sendChatMessage(
      "session/1",
      "Câu hỏi",
      "private-capability",
      "same-key",
    );
    await client.sendChatMessage(
      "session/1",
      "Câu hỏi",
      "private-capability",
      "same-key",
    );
    for (const [url, request] of fetcher.mock.calls) {
      expect(url).toBe(
        "http://local.invalid/api/v1/advisor/sessions/session%2F1/messages",
      );
      expect(url).not.toContain("private-capability");
      expect(request.headers.Authorization).toBe("Bearer private-capability");
      expect(request.headers["Idempotency-Key"]).toBe("same-key");
      expect(JSON.parse(request.body)).toEqual({ message: "Câu hỏi" });
      expect(request.credentials).toBe("omit");
    }
  });
  it("preserves structured errors without echoing arbitrary server text", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json(
            {
              error: {
                code: "invalid_scores",
                message: "unsafe server text",
                details: [{ category: "Quiz", issue: "missing_grade" }],
              },
            },
            422,
          ),
        ),
    );
    await expect(
      new ApiClient().createProfile({
        curriculum_code: "c",
        selected_courses: ["T"],
        grades: [],
      }),
    ).rejects.toMatchObject({
      code: "invalid_scores",
      status: 422,
      details: [{ category: "Quiz", issue: "missing_grade" }],
    });
  });
  it("times out long Chat without an automatic second request", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(
      (_url, opts) =>
        new Promise<Response>((_resolve, reject) =>
          opts.signal.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          ),
        ),
    );
    vi.stubGlobal("fetch", fetcher);
    const pending = new ApiClient(
      "http://local.invalid",
      10,
      240000,
    ).sendChatMessage("s", "q", "t", "k");
    const assertion = expect(pending).rejects.toMatchObject({
      code: "transport_timeout",
    });
    await vi.advanceTimersByTimeAsync(239999);
    expect(fetcher).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await assertion;
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it("supports cancellation and rejects malformed JSON", async () => {
    const controller = new AbortController();
    const fetcher = vi.fn(
      (_url, opts) =>
        new Promise<Response>((_resolve, reject) =>
          opts.signal.addEventListener("abort", () =>
            reject(new Error("aborted")),
          ),
        ),
    );
    vi.stubGlobal("fetch", fetcher);
    const pending = new ApiClient().listCourses(controller.signal);
    controller.abort();
    await expect(pending).rejects.toEqual(new ApiError("cancelled"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("bad JSON")));
    await expect(new ApiClient().listCourses()).rejects.toMatchObject({
      code: "invalid_response",
    });
  });
});
