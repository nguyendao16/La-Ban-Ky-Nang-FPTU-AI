import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api";
import { config } from "../config";
import type { RecommendationsView } from "../types";
import { operationKey, type Workspace } from "../workspace";
import { canReplay, Feedback, Loading } from "./Feedback";

const programTypes = {
  course: "Khóa học",
  specialization: "Specialization",
  professional_certificate: "Professional Certificate",
};

function CourseText({ text, urls }: { text: string; urls: string[] }) {
  const nodes: ReactNode[] = [];
  let end = 0;
  for (const match of text.matchAll(
    /\[([^\]\n]+)\]\((https:\/\/[^\s<>"()]+)\)|(https:\/\/[^\s<>"()\[\]]+)/g,
  )) {
    nodes.push(text.slice(end, match.index));
    const original = match[2] ?? match[3];
    const raw = match[2] ? original : original.replace(/[.,;:!?]+$/, "");
    let href: string | undefined;
    try {
      const url = new URL(raw);
      if (
        url.protocol === "https:" &&
        ["coursera.org", "www.coursera.org"].includes(url.hostname) &&
        !url.username &&
        !url.password &&
        !url.port
      ) {
        url.hostname = "www.coursera.org";
        url.pathname = url.pathname.replace(/\/+$/, "");
        url.search = "";
        url.hash = "";
        if (urls.includes(url.href)) href = url.href;
      }
    } catch {
      // Unrecognized citations remain escaped text.
    }
    nodes.push(
      href ? (
        <a
          key={match.index}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
        >
          {match[1] ?? "Coursera"}
        </a>
      ) : (
        match[0]
      ),
    );
    if (href && !match[2]) nodes.push(original.slice(raw.length));
    end = match.index + match[0].length;
  }
  return (
    <>
      {nodes}
      {text.slice(end)}
    </>
  );
}

export function Recommendations({
  workspace,
  updateWorkspace,
}: {
  workspace: Workspace;
  updateWorkspace: (value: Workspace) => void;
}) {
  const id = useId();
  const [view, setView] = useState<RecommendationsView | null>(null);
  const [readError, setReadError] = useState<unknown>();
  const [postError, setPostError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [tracking, setTracking] = useState(true);
  const [epoch, setEpoch] = useState(0);
  const latest = useRef(workspace),
    update = useRef(updateWorkspace),
    mounted = useRef(true),
    sending = useRef(false);
  const postRequest = useRef<AbortController | null>(null);
  latest.current = workspace;
  update.current = updateWorkspace;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      postRequest.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!tracking) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function read() {
      try {
        const next = await api.getRecommendations(
          workspace.sessionId!,
          workspace.token,
          abort.signal,
        );
        if (abort.signal.aborted) return;
        setView(next);
        setReadError(null);
        if (next.status !== "not_requested" && latest.current.recommendations) {
          update.current({ ...latest.current, recommendations: undefined });
          setPostError(null);
        }
        if (next.status === "queued" || next.status === "processing")
          timer = setTimeout(read, config.pollInterval);
      } catch (error) {
        if (!abort.signal.aborted) setReadError(error);
      }
    }
    void read();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [workspace.sessionId, workspace.token, tracking, epoch]);

  async function create() {
    if (sending.current) return;
    const operation = latest.current.recommendations ?? { key: operationKey() };
    sending.current = true;
    setBusy(true);
    setPostError(null);
    const abort = new AbortController();
    postRequest.current = abort;
    try {
      update.current({ ...latest.current, recommendations: operation });
      await api.createRecommendations(
        workspace.sessionId!,
        workspace.token,
        operation.key,
        abort.signal,
      );
      if (mounted.current) {
        setTracking(true);
        setEpoch((n) => n + 1);
      }
    } catch (error) {
      if (mounted.current) setPostError(error);
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const waiting = view?.status === "queued" || view?.status === "processing";
  const courseUrls = view?.result?.courses.map((course) => course.url) ?? [];
  const retry =
    !postError ||
    canReplay(postError) ||
    (postError instanceof ApiError && postError.code === "cancelled");
  return (
    <section
      className="recommendations-section"
      aria-labelledby={`${id}-title`}
    >
      <h2 id={`${id}-title`}>Khóa học gợi ý</h2>
      <p className="muted">
        Tìm khóa học Coursera liên quan đến khoảng trống trong kết quả đã lưu.
      </p>
      <Feedback error={readError} />
      <Feedback error={postError} />
      {!view && !readError && <Loading>Đang tải trạng thái gợi ý…</Loading>}
      {view?.status === "not_requested" && (
        <button
          type="button"
          className="primary"
          disabled={busy || !retry}
          onClick={create}
        >
          {latest.current.recommendations
            ? "Thử lại cùng yêu cầu gợi ý"
            : "Gợi ý khóa học"}
        </button>
      )}
      {busy && <Loading>Đang gửi yêu cầu gợi ý…</Loading>}
      {waiting && tracking && !readError && (
        <Loading>
          {view?.status === "queued"
            ? "Đang chờ worker tìm khóa học…"
            : "Đang tìm khóa học Coursera…"}
        </Loading>
      )}
      {waiting && tracking && !readError && (
        <button type="button" onClick={() => setTracking(false)}>
          Tạm dừng theo dõi gợi ý
        </button>
      )}
      {(readError ||
        !tracking ||
        view?.status === "failed" ||
        view?.status === "interrupted") && (
        <button
          type="button"
          onClick={() => {
            setTracking(true);
            setEpoch((n) => n + 1);
          }}
        >
          Tải lại trạng thái gợi ý
        </button>
      )}
      {(view?.status === "failed" || view?.status === "interrupted") && (
        <p className="notice error" role="alert">
          Chưa thể hoàn tất gợi ý khóa học. Kết quả đối chiếu vẫn được giữ; ứng
          dụng không tự tìm lại. Cần operator kiểm tra trước khi chạy lại.
        </p>
      )}
      {view?.status === "ready" && view.result && (
        <>
          <p className="verbatim">
            <CourseText text={view.result.summary} urls={courseUrls} />
          </p>
          {!view.result.courses.length && (
            <p className="empty-state">Chưa có khóa học phù hợp để hiển thị.</p>
          )}
          <ol className="recommendation-list">
            {view.result.courses.map((course) => (
              <li key={course.url}>
                <h3>
                  <a
                    href={course.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {course.title}
                  </a>
                </h3>
                <p className="muted recommendation-meta">
                  {[
                    course.provider,
                    course.program_type && programTypes[course.program_type],
                    course.duration && `Thời lượng: ${course.duration}`,
                    course.price && `Giá: ${course.price}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="verbatim">
                  <CourseText text={course.reason} urls={courseUrls} />
                </p>
                <details>
                  <summary>
                    Khoảng trống liên quan ({course.gap_ids.length})
                  </summary>
                  <ul>
                    {course.gap_ids.map((gap) => (
                      <li key={gap}>
                        {view.gaps.find((g) => g.gap_id === gap)?.description ??
                          gap}
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            ))}
          </ol>
          {!!view.result.courses.length && (
            <p className="muted recommendation-source-note">
              Thông tin từ kết quả tìm kiếm; cần xem chi tiết khóa học. Gợi ý hỗ
              trợ nội dung học tập, không xác nhận kinh nghiệm hoặc năng lực
              nghề nghiệp.
            </p>
          )}
        </>
      )}
    </section>
  );
}
