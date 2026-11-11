import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { config } from "../config";
import { operationKey, type Workspace } from "../workspace";
import type { AcademicProfile, Turn } from "../types";
import { Feedback, Loading, canReplay } from "./Feedback";
import { EvidenceList } from "./ReviewView";
export function Chat({
  workspace,
  updateWorkspace,
  profile,
}: {
  workspace: Workspace;
  updateWorkspace: (w: Workspace) => void;
  profile: AcademicProfile;
}) {
  const [turns, setTurns] = useState<Turn[]>([]),
    [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>(),
    [historyError, setHistoryError] = useState<unknown>();
  const [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const sending = useRef(false),
    mounted = useRef(true),
    request = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    api
      .getChatHistory(workspace.sessionId!, workspace.token, abort.signal)
      .then((h) => {
        if (mounted.current) setTurns(h.turns);
      })
      .catch((e) => {
        if (mounted.current) setHistoryError(e);
      })
      .finally(() => {
        if (mounted.current) setLoading(false);
      });
    return () => {
      mounted.current = false;
      abort.abort();
      request.current?.abort();
    };
  }, [workspace.sessionId, workspace.token]);
  async function refresh() {
    setLoading(true);
    setHistoryError(null);
    try {
      const h = await api.getChatHistory(workspace.sessionId!, workspace.token);
      if (mounted.current) setTurns(h.turns);
    } catch (e) {
      if (mounted.current) setHistoryError(e);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }
  async function send(event?: React.SubmitEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (sending.current) return;
    const operation = workspace.chat || { key: operationKey(), message };
    if (
      !operation.message.trim() ||
      operation.message.length > config.maxMessage
    ) {
      setError(`Nhập câu hỏi từ 1 đến ${config.maxMessage} ký tự.`);
      return;
    }
    sending.current = true;
    setBusy(true);
    setError(null);
    request.current = new AbortController();
    try {
      updateWorkspace({ ...workspace, chat: operation });
      await api.sendChatMessage(
        workspace.sessionId!,
        operation.message,
        workspace.token,
        operation.key,
        request.current.signal,
      );
      const history = await api.getChatHistory(
        workspace.sessionId!,
        workspace.token,
        request.current.signal,
      );
      if (!mounted.current) return;
      setTurns(history.turns);
      setHistoryError(null);
      updateWorkspace({ ...workspace, chat: undefined });
      setMessage("");
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const pending = workspace.chat;
  const retry =
    !error ||
    canReplay(error) ||
    (error instanceof ApiError && error.code === "cancelled");
  return (
    <section className="chat-section">
      <div className="eyebrow">07 / ACADEMIC CHAT</div>
      <div className="section-heading">
        <h1>Trao đổi về hồ sơ của bạn</h1>
        <button disabled={loading || busy} onClick={refresh}>
          Tải lại lịch sử
        </button>
      </div>
      <p className="muted">
        Mỗi câu hỏi dùng cùng hồ sơ, JD và Initial Review của phiên. Câu trả lời
        có tham chiếu học thuật.
      </p>
      <Feedback error={historyError} />
      {loading && <Loading>Đang tải lịch sử…</Loading>}
      {!loading && !historyError && !turns.length && (
        <p className="empty-state">
          Chưa có lượt trao đổi. Bạn có thể hỏi về một CLO hoặc yêu cầu trong
          JD.
        </p>
      )}
      <div className="conversation" aria-live="polite">
        {turns.map((t) => (
          <article key={t.message_id} className="turn">
            <div className="user-message">
              <small>BẠN</small>
              <p className="verbatim">{t.user_message}</p>
            </div>
            <div className="assistant-message">
              <small>SKILLBRIDGE</small>
              <p className="verbatim">{t.reply}</p>
              <EvidenceList evidence={t.evidence} profile={profile} />
            </div>
          </article>
        ))}
      </div>
      {pending && (
        <div className="notice">
          <p>Câu hỏi đang chờ xác nhận kết quả:</p>
          <p className="verbatim">{pending.message}</p>
          <small>Nội dung và mã thao tác được giữ nguyên khi thử lại.</small>
        </div>
      )}
      <Feedback error={error} />
      {busy && (
        <Loading>Đang chờ phản hồi; thao tác có thể mất vài phút…</Loading>
      )}
      {pending ? (
        <button
          className="primary"
          disabled={busy || !retry}
          onClick={() => send()}
        >
          Thử lại cùng câu hỏi
        </button>
      ) : (
        <form onSubmit={send}>
          <label>
            Câu hỏi của bạn
            <textarea
              aria-label="Câu hỏi của bạn"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              maxLength={config.maxMessage}
              disabled={busy}
              placeholder="CLO nào trong hồ sơ liên quan đến yêu cầu của JD?"
            />
          </label>
          <div className="actions">
            <small>
              {message.length}/{config.maxMessage} ký tự
            </small>
            <button className="primary" disabled={busy || loading}>
              Gửi câu hỏi
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
