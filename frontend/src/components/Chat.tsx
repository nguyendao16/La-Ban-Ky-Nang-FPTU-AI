import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { config } from "../config";
import { operationKey, type Workspace } from "../workspace";
import type { Turn } from "../types";
import { Feedback, Loading, canReplay } from "./Feedback";
import { EvidenceList } from "./EvidenceList";
export function Chat({
  workspace,
  updateWorkspace,
}: {
  workspace: Workspace;
  updateWorkspace: (w: Workspace) => void;
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
  const latestWorkspace = useRef(workspace);
  latestWorkspace.current = workspace;
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    api
      .getChatHistory(workspace.sessionId!, workspace.token, abort.signal)
      .then((h) => {
        if (mounted.current && !abort.signal.aborted) setTurns(h.turns);
      })
      .catch((e) => {
        if (mounted.current && !abort.signal.aborted) setHistoryError(e);
      })
      .finally(() => {
        if (mounted.current && !abort.signal.aborted) setLoading(false);
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
      updateWorkspace({ ...latestWorkspace.current, chat: operation });
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
      updateWorkspace({ ...latestWorkspace.current, chat: undefined });
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
      <div className="eyebrow">03 / TRAO ĐỔI</div>
      <div className="section-heading">
        <h1>Hiểu rõ hơn về kết quả</h1>
        <button disabled={loading || busy} onClick={refresh}>
          Tải lại lịch sử
        </button>
      </div>
      <p className="muted">
        Hỏi về yêu cầu công việc, nội dung liên quan và những khoảng trống trong
        kết quả.
      </p>
      <Feedback error={historyError} />
      {loading && <Loading>Đang tải lịch sử…</Loading>}
      {!loading && !historyError && !turns.length && (
        <p className="empty-state">
          Chưa có lượt trao đổi. Bạn có thể hỏi về nội dung liên quan đến công
          việc mục tiêu.
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
              <small>LA BÀN KỸ NĂNG</small>
              <p className="verbatim">{t.reply}</p>
              <EvidenceList evidence={t.evidence} />
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
              placeholder="Những môn nào liên quan đến yêu cầu này?"
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
