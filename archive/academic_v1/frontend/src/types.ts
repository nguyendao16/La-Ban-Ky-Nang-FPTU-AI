// HTTP envelopes mirror app/schemas; academic values come from the backend.
export interface Evidence {
  course_code: string;
  clo?: string;
  metadata_field?: "description" | "tools";
}
export interface Course {
  course_code: string;
  name: { vi?: string; en?: string; full?: string };
  semester: number | string;
  credits?: number | string;
  record_type: string;
  curriculum_code: string;
  availability: Record<"metadata" | "clos" | "assessments", boolean>;
  diagnostics: Array<{ field: string; issue: string; message: string }>;
  combo?: { code: string; title?: string; name?: string };
}
export interface ExclusiveSlot {
  curriculum_code: string;
  family: string;
  slot_identifier: string;
  course_codes: string[];
}
export interface Catalog {
  curriculum_code: string;
  courses: Course[];
  selection_constraints: {
    exclusive_slots: ExclusiveSlot[];
    ambiguous_slots: unknown[];
  };
}
export interface Assessment {
  category: string;
  part: string;
  weight: string | number;
  clo: string;
}
export interface CourseDetail {
  course_code: string;
  curriculum_code: string;
  catalog: Course;
  metadata: Record<string, unknown> | null;
  assessments: Assessment[] | null;
  availability: Course["availability"];
  diagnostics: Course["diagnostics"];
}
export interface GradeEntry {
  course_code: string;
  category: string;
  grade: number;
}
export interface ProfilePayload {
  curriculum_code: string;
  selected_courses: string[];
  grades: GradeEntry[];
}
export interface CLO {
  clo: string;
  description: string;
  score: number | null;
  achievement:
    | "below_expected"
    | "basic"
    | "good"
    | "excellent"
    | "not_evaluated";
}
export interface AcademicProfile {
  profile_type: "academic";
  courses: Array<{
    course_code: string;
    metadata?: Record<string, unknown> | null;
    clos: CLO[];
  }>;
}
export interface Profile {
  profile_id: string;
  curriculum_code: string;
  status: "ready";
  summary: { course_count: number; clo_count: number };
  profile: AcademicProfile;
  selected_courses: string[];
  grades: GradeEntry[];
  diagnostics: Record<string, unknown>;
  fingerprint: string;
  created_at: string;
}
export interface CreatedProfile extends Profile {
  access_token: string;
}
export interface Review {
  review_type: "academic_knowledge_review";
  overview: string;
  requirement_reviews: Array<{
    jd_requirement: string;
    coverage: "covered" | "related" | "not_evidenced";
    comment: string;
    evidence: Evidence[];
  }>;
  conclusion: string;
}
export interface SessionPayload {
  profile_id: string;
  job_description: string;
}
export interface CreatedSession {
  session_id: string;
  status: "queued";
  review_job: { job_id: string; status: string };
}
export type SessionStatus =
  | "queued"
  | "processing"
  | "ready"
  | "failed"
  | "interrupted";
export interface Session {
  session_id: string;
  profile_id: string;
  status: SessionStatus;
  academic_state: "pending_review" | "ready";
  initial_review: Review | null;
  review_job: {
    job_id: string;
    status: string;
    error_code?: string | null;
    error_message?: string | null;
  };
  fingerprints: Record<string, string>;
  revision: number;
  turn_count: number;
  created_at: string;
  updated_at: string;
}
export interface ChatReply {
  message_id: string;
  reply: string;
  evidence: Evidence[];
}
export interface Turn extends ChatReply {
  sequence: number;
  user_message: string;
}
export interface History {
  session_id: string;
  turns: Turn[];
}
export interface Health {
  status: "ready" | "degraded" | "unavailable";
  database: string;
  curriculum?: string;
  review_worker?: string;
  queued_review_jobs?: number;
}
