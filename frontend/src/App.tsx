import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { config } from "./config";
import {
  readWorkspace,
  saveWorkspace,
  operationKey,
  type Workspace,
} from "./workspace";
import type {
  Catalog,
  CreatedSelection,
  Selection,
  SessionPayload,
} from "./types";
import { CourseSelection } from "./components/CourseSelection";
import { TargetInput } from "./components/TargetInput";
import { targetDraft, targetError, targetPayload } from "./target";
import { AdvisorFlow } from "./components/AdvisorFlow";
import { Feedback, Loading } from "./components/Feedback";

function SelectionForm({
  onCreated,
}: {
  onCreated: (
    value: CreatedSelection,
    target: SessionPayload,
    keep: boolean,
  ) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<string[]>([]),
    [combo, setCombo] = useState("");
  const [target, setTarget] = useState(() => targetDraft()),
    [keep, setKeep] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    api
      .listCourses(abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) {
          setCatalog(value);
          setError(null);
        }
      })
      .catch((err) => {
        if (!abort.signal.aborted) setError(err);
      });
    return () => abort.abort();
  }, [epoch]);
  const sending = useRef(false);
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current || !catalog) return;
    if (!selected.length || targetError(target)) {
      setError(
        !selected.length
          ? "Chọn ít nhất một môn để tiếp tục."
          : targetError(target),
      );
      return;
    }
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.createSelection({
        curriculum_code: catalog.curriculum_code,
        selected_courses: selected,
        ...(combo ? { combo } : {}),
      });
      onCreated(result, targetPayload(result.selection_id, target), keep);
    } catch (err) {
      setError(err);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">TỪ GIẢNG ĐƯỜNG ĐẾN CÔNG VIỆC</span>
        <h1>
          Kết nối điều đã học
          <br />
          <span>với công việc bạn muốn.</span>
        </h1>
        <p>
          Chọn các môn học và nhóm nghề bạn hướng tới. La Bàn Kỹ Năng giúp bạn
          hiểu nội dung liên quan và những khoảng trống cần chú ý.
        </p>
      </div>
      {!catalog ? (
        <section>
          <Feedback error={error} />
          {error ? (
            <button onClick={() => setEpoch((n) => n + 1)}>
              Tải lại danh sách môn
            </button>
          ) : (
            <Loading>Đang tải danh sách môn học…</Loading>
          )}
        </section>
      ) : (
        <form className="input-layout" onSubmit={submit}>
          <CourseSelection
            catalog={catalog}
            selected={selected}
            combo={combo}
            onChange={setSelected}
            onCombo={setCombo}
            busy={busy}
          />
          <section className="jd-panel">
            <span className="eyebrow">02 / CÔNG VIỆC MỤC TIÊU</span>
            <h2>
              Bạn đang hướng đến
              <br />
              công việc nào?
            </h2>
            <TargetInput value={target} onChange={setTarget} disabled={busy} />
            <div className="selection-summary">
              <strong>{selected.length}</strong>
              <span>môn học đã chọn</span>
            </div>
            <label className="keep-option">
              <input
                type="checkbox"
                checked={keep}
                onChange={(e) => setKeep(e.target.checked)}
                disabled={busy}
              />
              Giữ phiên trong tab (tùy chọn)
            </label>
            <Feedback error={error} />
            <button className="primary submit-comparison" disabled={busy}>
              {busy
                ? "Đang chuẩn bị…"
                : target.mode === "cwa"
                  ? "Khám phá nhóm nghề"
                  : "So sánh với JD"}
              <span aria-hidden="true">↗</span>
            </button>
            <p className="form-note">
              {config.demo
                ? "DEMO OFFLINE · Kết quả và Chat được giả lập."
                : "Đối chiếu nội dung môn học với nhóm nghề hoặc JD bạn chọn."}
            </p>
          </section>
        </form>
      )}
    </>
  );
}
export default function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(readWorkspace);
  const [selection, setSelection] = useState<Selection | null>(null),
    [step, setStep] = useState(workspace?.sessionId ? 2 : 1);
  const [autoStart, setAutoStart] = useState(false);
  const [error, setError] = useState<unknown>(),
    [epoch, setEpoch] = useState(0);
  const updateWorkspace = useCallback((value: Workspace) => {
    if (!saveWorkspace(value))
      throw "Không thể lưu phiên trong tab. Bỏ tùy chọn lưu trước khi gửi thao tác.";
    setWorkspace(value);
  }, []);
  useEffect(() => {
    if (!workspace || selection) return;
    const abort = new AbortController();
    api
      .getSelection(workspace.selectionId, workspace.token, abort.signal)
      .then((value) => {
        if (!abort.signal.aborted) {
          setSelection(value);
          setError(null);
        }
      })
      .catch((err) => {
        if (!abort.signal.aborted) setError(err);
      });
    return () => abort.abort();
  }, [workspace?.selectionId, workspace?.token, selection, epoch]);
  function created(
    value: CreatedSelection,
    target: SessionPayload,
    keep: boolean,
  ) {
    const { access_token, ...stored } = value;
    const next: Workspace = {
      selectionId: value.selection_id,
      token: access_token,
      keepInTab: keep,
      mode: target.career_profile_id ? "cwa" : "jd",
      creation: {
        key: operationKey(),
        payload: target,
      },
    };
    updateWorkspace(next);
    setSelection(stored);
    setAutoStart(true);
    setStep(2);
  }
  function reset() {
    saveWorkspace(null);
    setWorkspace(null);
    setSelection(null);
    setStep(1);
    setError(null);
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Đến nội dung chính
      </a>
      <header className="topbar">
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <span className="brand-mark" aria-hidden="true">
            L<span>↗</span>
          </span>
          <span>
            La Bàn <span className="brand-accent">Kỹ Năng</span>
            <small>LEARNING MEETS OPPORTUNITY</small>
          </span>
        </a>
        <span className="local-label">
          <i aria-hidden="true" />
          {config.demo ? "DEMO OFFLINE" : "KHÁM PHÁ CƠ HỘI"}
        </span>
      </header>
      <main id="main-content" className="main-content">
        <ol className="journey">
          {["Môn học & mục tiêu", "Đối chiếu", "Kết quả & Chat"].map(
            (label, i) => (
              <li
                key={label}
                className={
                  step === i + 1 ? "current" : step > i + 1 ? "done" : ""
                }
                aria-current={step === i + 1 ? "step" : undefined}
              >
                <span>{`0${i + 1}`}</span>
                {label}
              </li>
            ),
          )}
        </ol>
        {workspace && (
          <div className="workspace-bar">
            <div>
              <span className="pill">
                {selection?.summary.course_count ?? "…"} môn đã chọn
              </span>
              <label className="keep-option">
                <input
                  type="checkbox"
                  checked={workspace.keepInTab}
                  disabled={
                    !!workspace.chat ||
                    !!workspace.creation ||
                    !!workspace.recommendations
                  }
                  onChange={(e) => {
                    try {
                      updateWorkspace({
                        ...workspace,
                        keepInTab: e.target.checked,
                      });
                    } catch (err) {
                      setError(err);
                    }
                  }}
                />
                Giữ phiên trong tab (tùy chọn)
              </label>
            </div>
            <div className="workspace-actions">
              {workspace.sessionId && (
                <button
                  disabled={
                    !!workspace.chat ||
                    !!workspace.creation ||
                    !!workspace.recommendations
                  }
                  onClick={() => {
                    try {
                      updateWorkspace({
                        ...workspace,
                        sessionId: undefined,
                        recommendations: undefined,
                      });
                      setStep(1);
                    } catch (err) {
                      setError(err);
                    }
                  }}
                >
                  So sánh mục tiêu khác
                </button>
              )}
              <button
                disabled={
                  !!workspace.chat ||
                  !!workspace.creation ||
                  !!workspace.recommendations
                }
                onClick={reset}
              >
                Chọn môn mới
              </button>
            </div>
          </div>
        )}
        <Feedback error={error} />
        {!workspace ? (
          <SelectionForm onCreated={created} />
        ) : !selection ? (
          error ? (
            <button
              onClick={() => {
                setError(null);
                setEpoch((n) => n + 1);
              }}
            >
              Khôi phục phiên
            </button>
          ) : (
            <Loading>Đang khôi phục phiên…</Loading>
          )
        ) : (
          <AdvisorFlow
            key={workspace.sessionId || "draft"}
            selection={selection}
            workspace={workspace}
            updateWorkspace={updateWorkspace}
            onStep={setStep}
            autoStart={autoStart}
          />
        )}
      </main>
      <footer>
        <span className="footer-brand">
          La Bàn Kỹ Năng<span>↗</span>
        </span>
        <span>Nội dung học tập. Góc nhìn nghề nghiệp mới.</span>
        <span className="brand-stripes" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </footer>
    </div>
  );
}
