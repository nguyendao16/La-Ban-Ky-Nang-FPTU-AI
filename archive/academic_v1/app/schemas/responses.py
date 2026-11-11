from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from scripts.academic_review import AcademicEvidence, AcademicKnowledgeReview


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    database: Literal["ok", "unavailable"]
    curriculum: str | None = None
    review_worker: str | None = None
    queued_review_jobs: int | None = None


class CourseListResponse(BaseModel):
    curriculum_code: str
    courses: list[dict[str, Any]]
    selection_constraints: dict[str, Any]


class CourseDetailResponse(BaseModel):
    course_code: str
    curriculum_code: str
    catalog: dict[str, Any]
    metadata: dict[str, Any] | None
    assessments: list[dict[str, Any]] | None
    availability: dict[str, bool]
    diagnostics: list[dict[str, Any]]


class ProfileResponse(BaseModel):
    profile_id: str
    curriculum_code: str
    status: Literal["ready"] = "ready"
    summary: dict[str, int]
    profile: dict[str, Any]
    selected_courses: list[str]
    grades: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    fingerprint: str
    created_at: str


class CreatedProfileResponse(ProfileResponse):
    access_token: str


class CreatedSessionResponse(BaseModel):
    session_id: str
    status: Literal["queued"]
    review_job: dict[str, str]


class SessionResponse(BaseModel):
    session_id: str
    profile_id: str
    status: Literal["queued", "processing", "ready", "failed", "interrupted"]
    academic_state: Literal["pending_review", "ready"]
    initial_review: AcademicKnowledgeReview | None
    review_job: dict[str, Any]
    fingerprints: dict[str, str]
    revision: int
    turn_count: int
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    message_id: str
    reply: str
    evidence: list[AcademicEvidence]


class HistoryResponse(BaseModel):
    session_id: str
    turns: list[dict[str, Any]]
