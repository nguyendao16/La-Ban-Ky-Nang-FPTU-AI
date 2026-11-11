export interface Evidence {
  course_code: string;
}
export interface Course {
  course_code: string;
  name: { vi?: string; en?: string; full?: string };
  semester: number | string;
  credits?: number | string | null;
  curriculum_code: string;
}
export interface Semester {
  semester: number;
  course_codes: string[];
}
export interface Catalog {
  curriculum_code: string;
  courses: Course[];
  semester_map: {
    common: Semester[];
    combos: Array<{ name: string; semesters: Semester[] }>;
  };
}
export type CourseDetail = Course;
export interface SelectionPayload {
  curriculum_code: string;
  selected_courses: string[];
  combo?: string;
}
export interface Selection {
  selection_id: string;
  curriculum_code: string;
  status: "ready";
  selected_courses: string[];
  summary: { course_count: number };
  created_at: string;
}
export interface CreatedSelection extends Selection {
  access_token: string;
}
export interface JDComparison {
  comparison_type: "course_jd_comparison";
  radar?: CareerRadarData | null;
  overview: string;
  requirement_reviews: Array<{
    jd_requirement: string;
    coverage: "covered" | "related" | "not_evidenced";
    comment: string;
    evidence: Evidence[];
  }>;
  conclusion: string;
}
export interface CareerProfile {
  profile_id: string;
  title: string;
  standard: "CWA 18398:2026";
  role_codes: string[];
  content: string;
  fingerprint: string;
  target?: {
    title: string;
    scope: string;
    axes: Array<{ name: string; description: string }>;
  } | null;
}
export interface CareerRadarData {
  overall_score: number;
  overall_comment: string;
  axes: Array<{
    name: string;
    description: string;
    score: number;
    comment: string;
    evidence: Evidence[];
  }>;
}
export interface CareerComparison {
  comparison_type: "career_comparison";
  radar?: CareerRadarData | null;
  overview: string;
  related_content: Array<{
    title: string;
    comment: string;
    evidence: Evidence[];
  }>;
  gaps: Array<{ title: string; comment: string; evidence: Evidence[] }>;
  conclusion: string;
}
export type Comparison = JDComparison | CareerComparison;
export type SessionPayload = { selection_id: string } & (
  | { job_description: string; career_profile_id?: never }
  | { career_profile_id: string; job_description?: never }
);
export type SessionTarget =
  | { type: "cwa"; career_profile: CareerProfile }
  | { type: "jd"; job_description: string };
export interface CreatedSession {
  session_id: string;
  status: "queued";
  comparison_job: { job_id: string; status: string };
}
export type SessionStatus =
  | "queued"
  | "processing"
  | "ready"
  | "failed"
  | "interrupted";
export interface Session {
  session_id: string;
  selection_id: string;
  status: SessionStatus;
  comparison: Comparison | null;
  target: SessionTarget;
  comparison_job: {
    job_id: string;
    status: string;
    error_code?: string | null;
    error_message?: string | null;
  };
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
  error_code?: string;
  message?: string;
}

export interface CourseRecommendation {
  title: string;
  url: string;
  provider: string | null;
  program_type: "course" | "specialization" | "professional_certificate" | null;
  duration: string | null;
  price: string | null;
  reason: string;
  gap_ids: string[];
}
export interface RecommendationsView {
  session_id: string;
  status:
    | "not_requested"
    | "queued"
    | "processing"
    | "ready"
    | "failed"
    | "interrupted";
  job: { job_id: string; error_code?: string | null } | null;
  result: { summary: string; courses: CourseRecommendation[] } | null;
  gaps: Array<{ gap_id: string; description: string }>;
}
