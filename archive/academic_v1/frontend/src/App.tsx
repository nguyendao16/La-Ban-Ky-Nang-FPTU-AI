import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { config } from "./config";
import { readWorkspace, saveWorkspace, type Workspace } from "./workspace";
import type {
  Catalog,
  CourseDetail,
  CreatedProfile,
  Health,
  Profile,
} from "./types";
import { CourseSelection } from "./components/CourseSelection";
import { GradeForm } from "./components/GradeForm";
import { ProfileOverview } from "./components/ProfileOverview";
import { AdvisorFlow } from "./components/AdvisorFlow";
import { Feedback, Loading } from "./components/Feedback";
const steps = [
  "Chọn môn học",
  "Nhập điểm",
  "Hồ sơ CLO",
  "Job Description",
  "Tiến độ Review",
  "Academic Review",
  "Academic Chat",
];
export default function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(readWorkspace);
  const [profile, setProfile] = useState<Profile | null>(null),
    [details, setDetails] = useState<CourseDetail[]>([]),
    [catalog, setCatalog] = useState<Catalog | null>(null);
  const [screen, setScreen] = useState<
    "courses" | "grades" | "profile" | "advisor"
  >(workspace ? "advisor" : "courses");
  const [step, setStep] = useState(
    workspace?.sessionId ? 5 : workspace ? 4 : 1,
  );
  const [error, setError] = useState<unknown>(),
    [health, setHealth] = useState<Health | null>(null);
  const [profileEpoch, setProfileEpoch] = useState(0);
  const updateWorkspace = useCallback((w: Workspace) => {
    if (!saveWorkspace(w))
      throw "Không thể lưu phiên trong tab. Bỏ tùy chọn lưu trước khi gửi thao tác.";
    setWorkspace(w);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    api
      .getHealth(abort.signal)
      .then(setHealth)
      .catch(() => {});
    return () => abort.abort();
  }, []);
  useEffect(() => {
    if (!workspace || profile) return;
    const abort = new AbortController();
    api
      .getProfile(workspace.profileId, workspace.token, abort.signal)
      .then((p) => {
        setProfile(p);
        setError(null);
      })
      .catch(setError);
    return () => abort.abort();
  }, [workspace?.profileId, workspace?.token, profile, profileEpoch]);
  function created(p: CreatedProfile) {
    const { access_token, ...academic } = p;
    updateWorkspace({
      profileId: p.profile_id,
      token: access_token,
      keepInTab: false,
    });
    setProfile(academic);
    setScreen("profile");
    setStep(3);
  }
  function reset() {
    saveWorkspace(null);
    setWorkspace(null);
    setProfile(null);
    setDetails([]);
    setScreen("courses");
    setStep(1);
    setError(null);
  }
  return (
    <div className="app-shell">
      <header className="topbar">
        <a href="#" className="brand" onClick={(e) => e.preventDefault()}>
          <span className="brand-mark">S</span>SkillBridge{" "}
          <small>ACADEMIC ADVISOR</small>
        </a>
        <span className="local-label">
          {config.demo ? "DEMO OFFLINE" : "LOCAL MVP"}
        </span>
      </header>
      <div className="layout">
        <aside>
          <p className="eyebrow">HÀNH TRÌNH CỦA BẠN</p>
          <ol className="steps">
            {steps.map((label, i) => (
              <li
                key={label}
                className={
                  step === i + 1 ? "current" : step > i + 1 ? "done" : ""
                }
                aria-current={step === i + 1 ? "step" : undefined}
              >
                <span>{String(i + 1).padStart(2, "0")}</span>
                {label}
              </li>
            ))}
          </ol>
          <div className="sidebar-note">
            Từ kết quả học tập
            <br />
            đến bằng chứng rõ ràng.
            <p>Không suy năng lực nghề nghiệp từ điểm số.</p>
          </div>
        </aside>
        <main>
          {health && health.status !== "ready" && (
            <p className="notice">
              Backend báo {health.status}.{" "}
              {health.review_worker === "not_seen"
                ? "Review worker chưa được nhìn thấy; catalog và hồ sơ vẫn có thể dùng nếu dữ liệu sẵn sàng."
                : "Kiểm tra cấu hình local."}
            </p>
          )}
          {workspace && (
            <div className="workspace-bar">
              <span>
                {workspace.keepInTab
                  ? "Phiên được giữ trong tab này."
                  : "Phiên ở trong bộ nhớ; reload trang sẽ mất quyền truy cập."}
              </span>
              <label>
                <input
                  type="checkbox"
                  checked={workspace.keepInTab}
                  disabled={!!workspace.chat || !!workspace.creation}
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
              <small>
                Session storage có thể được JavaScript cùng origin đọc; chỉ dùng
                trên máy tin cậy.
              </small>
              <div className="workspace-actions">
                {screen === "advisor" && (
                  <button
                    onClick={() => {
                      setScreen("profile");
                      setStep(3);
                    }}
                  >
                    Xem hồ sơ
                  </button>
                )}
                <button
                  disabled={!!workspace.chat || !!workspace.creation}
                  onClick={reset}
                >
                  Bắt đầu hồ sơ mới
                </button>
              </div>
              <small>Hồ sơ mới không đổi snapshot của phiên cũ.</small>
            </div>
          )}
          <Feedback error={error} />
          {workspace && !profile ? (
            error ? (
              <button
                onClick={() => {
                  setError(null);
                  setProfileEpoch((n) => n + 1);
                }}
              >
                Tải lại hồ sơ
              </button>
            ) : (
              <Loading>Đang khôi phục hồ sơ đã lưu…</Loading>
            )
          ) : (
            <>
              {screen === "courses" && (
                <CourseSelection
                  onContinue={(c, d) => {
                    setCatalog(c);
                    setDetails(d);
                    setScreen("grades");
                    setStep(2);
                  }}
                />
              )}
              {screen === "grades" && catalog && (
                <GradeForm
                  details={details}
                  curriculum={catalog.curriculum_code}
                  onCreated={created}
                  onBack={() => {
                    setScreen("courses");
                    setStep(1);
                  }}
                />
              )}
              {screen === "profile" && profile && (
                <ProfileOverview
                  profile={profile}
                  onContinue={() => {
                    setScreen("advisor");
                    setStep(workspace?.sessionId ? 5 : 4);
                  }}
                />
              )}
              {screen === "advisor" && profile && workspace && (
                <AdvisorFlow
                  profile={profile}
                  workspace={workspace}
                  updateWorkspace={updateWorkspace}
                  onStep={setStep}
                />
              )}
            </>
          )}
        </main>
      </div>
      <footer>
        SkillBridge V1 · Hồ sơ học thuật dựa trên CLO · Curriculum lấy từ nguồn
        đã cấu hình
      </footer>
    </div>
  );
}
