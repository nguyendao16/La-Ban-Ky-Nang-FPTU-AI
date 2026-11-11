from typing import Any, Literal
from pydantic import BaseModel, Field
from app.engines.career import CareerProfile
from app.engines.recommendations import RecommendationResult, RecommendationGap


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal['ready', 'degraded', 'unavailable']
    database: Literal['ok', 'unavailable']
    error_code: str | None = None
    message: str | None = None
    curriculum: str | None = None
    review_worker: str | None = None
    queued_review_jobs: int | None = None


class CourseListResponse(BaseModel):
    curriculum_code: str
    courses: list[dict[str, Any]]
    semester_map: dict[str, Any]


class CourseDetailResponse(BaseModel):
    course_code: str
    curriculum_code: str
    name: dict[str, str]
    semester: int | str
    credits: int | str | None = None


class SelectionResponse(BaseModel):
    selection_id: str
    curriculum_code: str
    status: Literal['ready'] = 'ready'
    selected_courses: list[str]
    summary: dict[str, int]
    created_at: str


class CreatedSelectionResponse(SelectionResponse):
    access_token: str


class PublicEvidence(BaseModel):
    course_code: str


class PublicRequirement(BaseModel):
    jd_requirement: str
    coverage: Literal['covered', 'related', 'not_evidenced']
    comment: str
    evidence: list[PublicEvidence]


class PublicCareerFinding(BaseModel):
    title: str
    comment: str
    evidence: list[PublicEvidence]


class PublicCareerRadarAxis(BaseModel):
    name: str
    description: str
    score: float = Field(ge=0, le=5, allow_inf_nan=False)
    comment: str
    evidence: list[PublicEvidence]


class PublicCareerRadar(BaseModel):
    overall_score: float = Field(ge=0, le=5, allow_inf_nan=False)
    overall_comment: str
    axes: list[PublicCareerRadarAxis] = Field(min_length=5, max_length=5)


class PublicComparison(BaseModel):
    comparison_type: Literal['course_jd_comparison']
    overview: str
    requirement_reviews: list[PublicRequirement]
    conclusion: str
    radar: PublicCareerRadar | None = None


class PublicCareerComparison(BaseModel):
    comparison_type: Literal['career_comparison']
    overview: str
    related_content: list[PublicCareerFinding]
    gaps: list[PublicCareerFinding]
    conclusion: str
    radar: PublicCareerRadar | None = None


class CareerCatalogResponse(BaseModel):
    profiles: list[CareerProfile]


class CareerTargetResponse(BaseModel):
    type: Literal['cwa']
    career_profile: CareerProfile


class JDTargetResponse(BaseModel):
    type: Literal['jd']
    job_description: str


class CreatedSessionResponse(BaseModel):
    session_id: str
    status: Literal['queued']
    comparison_job: dict[str, str]


class SessionResponse(BaseModel):
    session_id: str
    selection_id: str
    status: Literal['queued', 'processing', 'ready', 'failed', 'interrupted']
    comparison: PublicComparison | PublicCareerComparison | None
    target: CareerTargetResponse | JDTargetResponse
    comparison_job: dict[str, Any]
    revision: int
    turn_count: int
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    message_id: str
    reply: str
    evidence: list[PublicEvidence]


class PublicTurn(MessageResponse):
    sequence: int
    user_message: str


class HistoryResponse(BaseModel):
    session_id: str
    turns: list[PublicTurn]


class CreatedRecommendationsResponse(BaseModel):
    job_id: str
    status: Literal['queued']


class RecommendationsResponse(BaseModel):
    session_id: str
    status: Literal['not_requested', 'queued', 'processing', 'ready', 'failed', 'interrupted']
    job: dict[str, Any] | None
    result: RecommendationResult | None
    gaps: list[RecommendationGap]
