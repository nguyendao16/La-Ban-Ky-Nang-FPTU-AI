import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { config } from "../config";
import { operationKey, type Workspace } from "../workspace";
import type { Profile, Session } from "../types";
import { Feedback, Loading, canReplay } from "./Feedback";
import { ReviewView } from "./ReviewView";
import { Chat } from "./Chat";
const statusText = {
  queued: "Đang chờ Review worker",
  processing: "Đang phân tích học thuật",
  ready: "Initial Review sẵn sàng",
  failed: "Phân tích không hoàn tất",
  interrupted: "Phân tích bị gián đoạn",
};
export function AdvisorFlow({
  profile,
  workspace,
  updateWorkspace,
  onStep,
}: {
  profile: Profile;
  workspace: Workspace;
  updateWorkspace: (w: Workspace) => void;
  onStep: (n: number) => void;
}) {
  const [jd, setJD] = useState(
    workspace.creation?.payload.job_description || "",
  );
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<unknown>(),
    [pollError, setPollError] = useState<unknown>();
  const [busy, setBusy] = useState(false),
    [pollEpoch, setPollEpoch] = useState(0);
  const sending = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!workspace.sessionId) {
      onStep(4);
      return;
    }
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    async function poll() {
      try {
        const result = await api.getAdvisorSession(
          workspace.sessionId!,
          workspace.token,
          abort.signal,
        );
        if (cancelled) return;
        setSession(result);
        setPollError(null);
        onStep(result.status === "ready" ? 7 : 5);
        if (["queued", "processing"].includes(result.status))
          timer = setTimeout(poll, config.pollInterval);
      } catch (e) {
        if (cancelled) return;
        setPollError(e);
        if (!(e instanceof ApiError) || ![401, 403, 404].includes(e.status))
          timer = setTimeout(poll, config.pollInterval);
      }
    }
    onStep(5);
    poll();
    return () => {
      cancelled = true;
      abort.abort();
      clearTimeout(timer);
    };
  }, [workspace.sessionId, workspace.token, pollEpoch, onStep]);
  async function create(event?: React.SubmitEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (sending.current) return;
    const operation = workspace.creation || {
      key: operationKey(),
      payload: { profile_id: profile.profile_id, job_description: jd },
    };
    if (
      !operation.payload.job_description.trim() ||
      operation.payload.job_description.length > config.maxJD
    ) {
      setError(`Nhập JD từ 1 đến ${config.maxJD} ký tự.`);
      return;
    }
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      updateWorkspace({ ...workspace, creation: operation });
      const result = await api.createAdvisorSession(
        operation.payload,
        workspace.token,
        operation.key,
      );
      if (!mounted.current) return;
      updateWorkspace({
        ...workspace,
        sessionId: result.session_id,
        creation: undefined,
      });
    } catch (e) {
      if (mounted.current) {
        setError(e);
        // Rejected input/authentication does not enqueue an operation. Editing is
        // a new logical submission; ambiguous transport/server outcomes stay frozen.
        if (e instanceof ApiError && [401, 403, 422].includes(e.status))
          updateWorkspace({ ...workspace, creation: undefined });
      }
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <>
      {!workspace.sessionId ? (
        <section>
          <div className="eyebrow">04 / JOB DESCRIPTION</div>
          <h1>Đặt hồ sơ trong ngữ cảnh JD</h1>
          <p className="intro">
            Dán JD để xem bằng chứng học thuật liên quan. Việc tạo phiên chỉ đưa
            Review vào queue.
          </p>
          <p className="notice">
            {config.demo
              ? "DEMO OFFLINE: Review và Chat được giả lập; không gọi OpenAI."
              : "Worker riêng sẽ gọi OpenAI khi xử lý phiên. Một phiên mới có thể phát sinh phí inference."}
          </p>
          <form onSubmit={create}>
            <label>
              Job Description
              <textarea
                aria-label="Job Description"
                rows={12}
                maxLength={config.maxJD}
                value={workspace.creation?.payload.job_description ?? jd}
                disabled={busy || !!workspace.creation}
                onChange={(e) => setJD(e.target.value)}
                placeholder="Dán mô tả công việc ở đây…"
              />
            </label>
            <small>
              {jd.length}/{config.maxJD} ký tự
            </small>
            <Feedback error={error} />
            <div className="actions">
              <span>Review gắn với snapshot hồ sơ này.</span>
              <button
                className="primary"
                disabled={
                  busy || (!!workspace.creation && !!error && !canReplay(error))
                }
              >
                {busy
                  ? "Đang tạo phiên…"
                  : workspace.creation
                    ? "Thử lại cùng JD"
                    : "Tạo phiên phân tích"}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <>
          <section>
            <div className="eyebrow">05 / INITIAL REVIEW</div>
            <h1>
              {session
                ? statusText[session.status]
                : "Đang lấy trạng thái phiên"}
            </h1>
            <p className="id-label">Session ID: {workspace.sessionId}</p>
            <Feedback error={pollError} />
            {!session && !pollError && (
              <Loading>Đang đọc trạng thái từ backend…</Loading>
            )}
            {session?.status === "queued" && (
              <p>
                Phiên đang chờ một Review worker. Bạn có thể để tab này mở; chưa
                có Review được công bố.
              </p>
            )}
            {session?.status === "processing" && (
              <Loading>
                Phân tích có thể mất vài phút. Trạng thái được kiểm tra định kỳ.
              </Loading>
            )}
            {session?.status === "failed" && (
              <p className="notice error" role="alert">
                Review không hoàn tất. Cần operator kiểm tra cấu hình hoặc lỗi
                job; ứng dụng không tự chạy lại.
              </p>
            )}
            {session?.status === "interrupted" && (
              <p className="notice error" role="alert">
                Phân tích bị gián đoạn và kết quả inference có thể chưa xác
                định. Cần operator kiểm tra để recovery; ứng dụng không tự tạo
                lại Review.
              </p>
            )}
            {(pollError ||
              session?.status === "failed" ||
              session?.status === "interrupted") && (
              <button onClick={() => setPollEpoch((n) => n + 1)}>
                Tải lại trạng thái
              </button>
            )}
          </section>
          {session?.status === "ready" && session.initial_review && (
            <>
              <ReviewView
                review={session.initial_review}
                profile={profile.profile}
              />
              <Chat
                workspace={workspace}
                updateWorkspace={updateWorkspace}
                profile={profile.profile}
              />
            </>
          )}
        </>
      )}
    </>
  );
}
