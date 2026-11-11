import type {
  Catalog,
  Course,
  Profile,
  Session,
  Review,
  CourseDetail,
} from "../types";
export const token = "test-capability-never-rendered";
export const course = (code: string, available = true): Course => ({
  course_code: code,
  name: { vi: `Môn ${code}` },
  semester: 3,
  credits: 3,
  record_type: "normal_subject",
  curriculum_code: "configured",
  availability: {
    metadata: available,
    clos: available,
    assessments: available,
  },
  diagnostics: [],
});
export const catalog: Catalog = {
  curriculum_code: "configured",
  courses: [
    course("TEST101"),
    course("OTHER201"),
    course("COMBOA"),
    course("COMBOB"),
    course("UNAVAILABLE", false),
  ],
  selection_constraints: {
    exclusive_slots: [
      {
        curriculum_code: "configured",
        family: "source-combo",
        slot_identifier: "slot-1",
        course_codes: ["COMBOA", "COMBOB"],
      },
    ],
    ambiguous_slots: [],
  },
};
export const detail = (code: string): CourseDetail => ({
  course_code: code,
  curriculum_code: "configured",
  catalog: course(code),
  metadata: null,
  assessments: [
    { category: "Quiz 1", part: "1", weight: "25%", clo: "CLO1" },
    { category: "Final exam", part: "1", weight: "75%", clo: "CLO1" },
  ],
  availability: course(code).availability,
  diagnostics: [],
});
export const profile: Profile = {
  profile_id: "profile-1",
  curriculum_code: "configured",
  status: "ready",
  summary: { course_count: 1, clo_count: 1 },
  profile: {
    profile_type: "academic",
    courses: [
      {
        course_code: "TEST101",
        clos: [
          {
            clo: "CLO1",
            description: "Use SQL",
            score: 0,
            achievement: "below_expected",
          },
        ],
      },
    ],
  },
  selected_courses: ["TEST101"],
  grades: [],
  diagnostics: {},
  fingerprint: "test",
  created_at: "2026-10-14",
};
export const review: Review = {
  review_type: "academic_knowledge_review",
  overview: "Tổng quan học thuật từ backend.",
  requirement_reviews: [
    {
      jd_requirement: "SQL",
      coverage: "not_evidenced",
      comment: "Không có bằng chứng cho yêu cầu này.",
      evidence: [{ course_code: "TEST101", clo: "CLO1" }],
    },
  ],
  conclusion: "Điểm không xác nhận kinh nghiệm.",
};
export const session = (status: Session["status"]): Session => ({
  session_id: "session-1",
  profile_id: "profile-1",
  status,
  academic_state: status === "ready" ? "ready" : "pending_review",
  initial_review: status === "ready" ? review : null,
  review_job: {
    job_id: "job-1",
    status: status === "ready" ? "succeeded" : status,
  },
  fingerprints: {},
  revision: status === "ready" ? 1 : 0,
  turn_count: 0,
  created_at: "2026-10-14",
  updated_at: "2026-10-14",
});
export const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
