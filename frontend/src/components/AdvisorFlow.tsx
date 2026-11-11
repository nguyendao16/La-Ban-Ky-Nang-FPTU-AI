import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { config } from "../config";
import { operationKey, type Workspace } from "../workspace";
import type { Selection, Session } from "../types";
import { ComparisonFailure, Feedback, Loading, canReplay } from "./Feedback";
import { TargetInput } from "./TargetInput";
import { targetDraft, targetError, targetPayload } from "../target";
import { ComparisonView } from "./ComparisonView";
import { Recommendations } from "./Recommendations";
import { Chat } from "./Chat";
const statusText = {
  queued: "Đang chờ worker so sánh",
  processing: "Đang đối chiếu nội dung môn học",
  ready: "So sánh sẵn sàng",
  failed: "Phân tích không hoàn tất",
  interrupted: "Phân tích bị gián đoạn",
};
export function AdvisorFlow({
  selection,
  workspace,
  updateWorkspace,
  onStep,
  autoStart = false,
}: {
  selection: Selection;
  workspace: Workspace;
  updateWorkspace: (w: Workspace) => void;
  onStep: (n: number) => void;
  autoStart?: boolean;
}) {
  const started = useRef(false);
  const [target, setTarget] = useState(() =>
    targetDraft(workspace.creation?.payload, workspace.mode),
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
      onStep(1);
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
        onStep(result.status === "ready" ? 3 : 2);
        if (["queued", "processing"].includes(result.status))
          timer = setTimeout(poll, config.pollInterval);
      } catch (e) {
        if (cancelled) return;
        setPollError(e);
        if (!(e instanceof ApiError) || ![401, 403, 404].includes(e.status))
          timer = setTimeout(poll, config.pollInterval);
      }
    }
    onStep(2);
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
      payload: targetPayload(selection.selection_id, target),
    };
    const validation = targetError(targetDraft(operation.payload));
    if (validation) {
      setError(validation);
      return;
    }
    started.current = true;
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      updateWorkspace({ ...workspace, mode: target.mode, creation: operation });
      const result = await api.createAdvisorSession(
        operation.payload,
        workspace.token,
        operation.key,
      );
      if (!mounted.current) return;
      updateWorkspace({
        ...workspace,
        mode: target.mode,
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
  useEffect(() => {
    if (
      autoStart &&
      workspace.creation &&
      !workspace.sessionId &&
      !started.current
    ) {
      started.current = true;
      void create();
    }
  }, [workspace.creation?.key, autoStart]);
  return (
    <>
      {!workspace.sessionId ? (
        <section>
          <div className="eyebrow">01 / CÔNG VIỆC MỤC TIÊU</div>
          <h1>Đối chiếu với mục tiêu mới</h1>
          <p className="intro">
            Chọn nhóm nghề hoặc nhập JD. Các môn đã chọn được giữ nguyên.
          </p>
          <p className="notice">
            {config.demo
              ? "DEMO OFFLINE: Comparison và Chat được giả lập; không gọi OpenAI."
              : "Kết quả giải thích mối liên hệ giữa nội dung học tập và công việc mục tiêu."}
          </p>
          <form onSubmit={create}>
            <TargetInput
              value={target}
              onChange={setTarget}
              disabled={busy || !!workspace.creation}
            />
            <Feedback error={error} />
            <div className="actions">
              <span>
                Các môn đã chọn được giữ nguyên cho lần đối chiếu này.
              </span>
              <button
                className="primary"
                disabled={
                  busy || (!!workspace.creation && !!error && !canReplay(error))
                }
              >
                {busy
                  ? "Đang tạo phiên…"
                  : workspace.creation
                    ? "Thử lại cùng yêu cầu"
                    : target.mode === "cwa"
                      ? "Khám phá nhóm nghề"
                      : "So sánh với JD"}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <>
          {session?.status !== "ready" && (
            <section>
              <div className="eyebrow">02 / ĐANG ĐỐI CHIẾU</div>
              <h1>
                {session
                  ? statusText[session.status]
                  : "Đang lấy trạng thái phiên"}
              </h1>
              <Feedback error={pollError} />
              {!session && !pollError && (
                <Loading>Đang lấy trạng thái…</Loading>
              )}
              {session?.status === "queued" && (
                <p>
                  Yêu cầu đã được tiếp nhận. Kết quả sẽ tự hiển thị khi hoàn
                  tất.
                </p>
              )}
              {session?.status === "processing" && (
                <Loading>
                  Phân tích có thể mất vài phút. Trạng thái được kiểm tra định
                  kỳ.
                </Loading>
              )}
              {session?.status === "failed" && (
                <ComparisonFailure code={session.comparison_job.error_code} />
              )}
              {session?.status === "interrupted" && (
                <p className="notice error" role="alert">
                  Phân tích bị gián đoạn và kết quả inference có thể chưa xác
                  định. Cần operator kiểm tra để recovery; ứng dụng không tự tạo
                  lại Comparison.
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
          )}
          {session?.status === "ready" && session.comparison && (
            <>
              <ComparisonView
                comparison={session.comparison}
                courseCount={selection.summary.course_count}
                careerTitle={
                  session.target?.type === "cwa"
                    ? (session.target.career_profile.target?.title ??
                      session.target.career_profile.title)
                    : undefined
                }
                fixedCareerAxes={
                  session.target?.type === "cwa" &&
                  !!session.target.career_profile.target
                }
                recommendations={
                  <Recommendations
                    key={workspace.sessionId}
                    workspace={workspace}
                    updateWorkspace={updateWorkspace}
                  />
                }
              />
              <Chat workspace={workspace} updateWorkspace={updateWorkspace} />
            </>
          )}
        </>
      )}
    </>
  );
}
