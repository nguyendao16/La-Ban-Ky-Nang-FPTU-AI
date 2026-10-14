"""Load academic inputs, generate a structured review, and verify its references."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

if __package__:
    from .academic_review_prompt import ACADEMIC_REVIEW_INSTRUCTIONS
    from .course_metadata import validate_course_metadata
    from .openai_model_config import MODEL_CAPABILITIES
else:
    from academic_review_prompt import ACADEMIC_REVIEW_INSTRUCTIONS
    from course_metadata import validate_course_metadata
    from openai_model_config import MODEL_CAPABILITIES


ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT_TOKENS = 4096
KNOWN_CONTEXT_WINDOWS = {name: capability.context_window for name, capability in MODEL_CAPABILITIES.items()}
TEMPERATURE_SUPPORTED_MODELS = frozenset(name for name, cap in MODEL_CAPABILITIES.items() if cap.temperature_without_reasoning)
Achievement = Literal["below_expected", "basic", "good", "excellent", "not_evaluated"]
Coverage = Literal["covered", "related", "not_evidenced"]


class ReviewError(ValueError):
    """An actionable failure; no generated review should be published."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def nonblank_strings(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Chuỗi không được rỗng hoặc chỉ chứa khoảng trắng")
        return value


class AcademicCLO(StrictModel):
    clo: str
    description: str
    score: float | None = Field(ge=0, le=10, allow_inf_nan=False)
    achievement: Achievement

    @model_validator(mode="after")
    def validate_missing_performance(self) -> AcademicCLO:
        if (self.score is None) != (self.achievement == "not_evaluated"):
            raise ValueError("score=null phải đi cùng achievement=not_evaluated")
        return self


class AcademicCourse(StrictModel):
    course_code: str
    metadata: dict[str, Any] | None = None
    clos: list[AcademicCLO] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_clos(self) -> AcademicCourse:
        if self.metadata is not None:
            validate_course_metadata(self.metadata, self.course_code)
        identifiers = [item.clo for item in self.clos]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Mã CLO bị trùng trong cùng môn học")
        return self


class AcademicProfile(StrictModel):
    profile_type: Literal["academic"]
    courses: list[AcademicCourse] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_courses(self) -> AcademicProfile:
        identifiers = [item.course_code for item in self.courses]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Mã môn học bị trùng trong hồ sơ")
        return self


class EvidenceReference(StrictModel):
    course_code: str
    clo: str


class MetadataEvidenceReference(StrictModel):
    course_code: str
    metadata_field: Literal["description", "tools"]


AcademicEvidence = EvidenceReference | MetadataEvidenceReference


class RequirementReview(StrictModel):
    jd_requirement: str
    coverage: Coverage
    comment: str = Field(description="Vietnamese academic assessment. Explain exact cited CLOs with their supplied achievement bands, or explicitly attribute curriculum context to course metadata. Metadata-only claims have no assessed achievement. Do not infer mastery, personal tool use or work experience.")
    evidence: list[AcademicEvidence] = Field(description="Exact CLO references or course metadata description/tools references supporting each claim. Metadata describes curriculum context, not assessed performance or personal tool use. A tools list alone is at most related. For compound covered requirements support every part.")


class AcademicKnowledgeReview(StrictModel):
    review_type: Literal["academic_knowledge_review"]
    overview: str
    requirement_reviews: list[RequirementReview]
    conclusion: str = Field(description="Vietnamese summary of evidenced academic learning and limitations. No personal-deficit claims, advice, hiring suitability or suggestions to acquire experience.")


def validation_details(exc: ValidationError) -> str:
    """Report field locations without echoing potentially sensitive input values."""
    return "; ".join(
        f"{'.'.join(str(part) for part in issue['loc']) or 'root'}: {issue['msg']}"
        for issue in exc.errors(include_input=False, include_url=False)
    )


def validate_profile(profile: Any) -> AcademicProfile:
    try:
        return AcademicProfile.model_validate(profile)
    except ValidationError as exc:
        raise ReviewError(f"Hồ sơ học thuật không hợp lệ: {validation_details(exc)}") from exc


def unique_json_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError("JSON chứa field bị trùng")
        result[key] = value
    return result


def load_profile(path: Path | str) -> dict[str, Any]:
    profile_path = Path(path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"), object_pairs_hook=unique_json_fields)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"Không thể đọc hồ sơ JSON UTF-8: {profile_path}") from exc
    validate_profile(raw)
    # Send the original values, not a normalized/rounded model serialization.
    return raw


def validate_jd(jd: Any) -> str:
    if not isinstance(jd, str) or not jd.strip():
        raise ReviewError("JD phải là văn bản không rỗng")
    return jd


def load_jd(path: Path | str) -> str:
    jd_path = Path(path)
    if jd_path.suffix.lower() != ".txt":
        raise ReviewError("JD phải được cung cấp qua file .txt UTF-8")
    try:
        return validate_jd(jd_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ReviewError(f"Không thể đọc JD UTF-8: {jd_path}") from exc


@dataclass(frozen=True)
class ReviewSettings:
    api_key: str = field(repr=False)
    model: str = "gpt-4o-mini"
    context_window: int | None = None
    temperature: float | None = None
    stage: Literal["review", "chat"] = "review"
    reasoning_effort: str | None = None
    max_output_tokens: int | None = None
    request_timeout: float | None = None

    def __post_init__(self) -> None:
        if self.request_timeout is not None and (type(self.request_timeout) not in (int, float)
                or not math.isfinite(self.request_timeout) or self.request_timeout <= 0):
            raise ReviewError("Request timeout phải là số hữu hạn lớn hơn 0")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ReviewError("Thiếu OPENAI_API_KEY; cấu hình trong môi trường hoặc .env tại root")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ReviewError("Tên model không được rỗng")
        if not isinstance(self.stage, str) or self.stage not in {"review", "chat"}:
            raise ReviewError("Stage phải là review hoặc chat")
        capability = MODEL_CAPABILITIES.get(self.model)
        if capability is None:
            raise ReviewError("Model/snapshot chưa xác nhận capability; --context-window không thay thế kiểm tra model")
        effort = self.reasoning_effort
        if capability.reasoning_efforts:
            if effort is None:
                effort = "high" if self.stage == "review" else "medium"
            if not isinstance(effort, str) or effort not in capability.reasoning_efforts:
                raise ReviewError("Reasoning effort không được model hỗ trợ")
        elif effort is not None:
            raise ReviewError("Model không hỗ trợ reasoning effort; bỏ cấu hình reasoning")
        temperature_allowed = capability.temperature_without_reasoning and effort in {None, "none"}
        if self.temperature is not None and (type(self.temperature) not in (int, float) or not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2):
            raise ReviewError("Temperature phải là số hữu hạn trong khoảng 0–2")
        if self.temperature is not None and not temperature_allowed:
            raise ReviewError("Chưa xác nhận model/effort hỗ trợ temperature; bỏ --temperature")
        output = self.max_output_tokens
        if output is None:
            output = (16384 if self.stage == "review" else 8192) if capability.reasoning_efforts else MAX_OUTPUT_TOKENS
        if type(output) is not int or not 16 <= output <= capability.max_output_tokens:
            raise ReviewError("max-output-tokens phải là số nguyên trong giới hạn output của model")
        limit = capability.context_window if self.context_window is None else self.context_window
        if type(limit) is not int or limit <= output:
            raise ReviewError(f"--context-window phải là số nguyên lớn hơn {output}")
        if limit > capability.context_window:
            raise ReviewError("--context-window không được vượt giới hạn model đã xác nhận")
        object.__setattr__(self, "context_window", limit)
        object.__setattr__(self, "reasoning_effort", effort)
        object.__setattr__(self, "max_output_tokens", output)
        if self.temperature is None and temperature_allowed:
            object.__setattr__(self, "temperature", 0.0)

    @property
    def timeout(self) -> float:
        if self.request_timeout is not None:
            return float(self.request_timeout)
        return 180.0 if self.reasoning_effort not in {None, "none"} else 60.0

    @property
    def reasoning_options(self) -> dict[str, Any]:
        return {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort is not None else {}


def load_settings(context_window: int | None = None, *, temperature: float | None = None,
                  stage: Literal["review", "chat"] = "review", model: str | None = None,
                  reasoning_effort: str | None = None, max_output_tokens: int | None = None,
                  request_timeout: float | None = None, api_key: str | None = None) -> ReviewSettings:
    if not isinstance(stage, str) or stage not in {"review", "chat"}:
        raise ReviewError("Stage phải là review hoặc chat")
    load_dotenv(ROOT / ".env", override=False)
    prefix = f"OPENAI_{stage.upper()}_"
    raw_output = os.environ.get(prefix + "MAX_OUTPUT_TOKENS")
    if max_output_tokens is None and raw_output is not None:
        try:
            max_output_tokens = int(raw_output)
        except ValueError as exc:
            raise ReviewError(f"{prefix}MAX_OUTPUT_TOKENS phải là số nguyên") from exc
    return ReviewSettings(
        api_key=os.environ.get("OPENAI_API_KEY", "") if api_key is None else api_key,
        model=model if model is not None else os.environ.get(prefix + "MODEL", os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL") or "gpt-4o-mini"),
        context_window=context_window,
        temperature=temperature,
        stage=stage,
        reasoning_effort=reasoning_effort if reasoning_effort is not None else os.environ.get(prefix + "REASONING_EFFORT"),
        max_output_tokens=max_output_tokens,
        request_timeout=request_timeout,
    )


def validate_review(raw: Any, profile: dict[str, Any]) -> AcademicKnowledgeReview:
    validated_profile = validate_profile(profile)
    try:
        # Revalidate model instances as well as dictionaries supplied by mocks/callers.
        if isinstance(raw, AcademicKnowledgeReview):
            raw = raw.model_dump()
        review = AcademicKnowledgeReview.model_validate(raw)
    except ValidationError as exc:
        raise ReviewError(f"Review sai schema: {validation_details(exc)}") from exc

    for row_number, requirement in enumerate(review.requirement_reviews, start=1):
        validate_evidence_references(requirement.evidence, validated_profile, label=f"Requirement {row_number}")
        if requirement.coverage == "not_evidenced" and requirement.evidence:
            raise ReviewError(f"Requirement {row_number}: not_evidenced phải có evidence rỗng")
        if requirement.coverage != "not_evidenced" and not requirement.evidence:
            raise ReviewError(f"Requirement {row_number}: covered/related phải có evidence")
        if requirement.coverage == "covered" and not any(
            isinstance(ref, EvidenceReference) or ref.metadata_field == "description" for ref in requirement.evidence
        ):
            raise ReviewError(f"Requirement {row_number}: tools-only evidence tối đa related")
    return review


def validate_evidence_references(
    references: list[AcademicEvidence], profile: AcademicProfile, *, label: str = "Evidence"
) -> None:
    """Check already schema-validated references for both review and chat."""
    index = {course.course_code: course for course in profile.courses}
    seen: set[tuple[str, str, str]] = set()
    for reference in references:
        if reference.course_code not in index:
            raise ReviewError(f"{label}: môn không tồn tại: {reference.course_code}")
        course = index[reference.course_code]
        if isinstance(reference, EvidenceReference):
            pair = (reference.course_code, "clo", reference.clo)
            if reference.clo not in {clo.clo for clo in course.clos}:
                raise ReviewError(f"{label}: CLO không thuộc môn: {reference.course_code}/{reference.clo}")
        else:
            pair = (reference.course_code, "metadata", reference.metadata_field)
            if course.metadata is None or not course.metadata[reference.metadata_field].strip():
                raise ReviewError(f"{label}: metadata field không tồn tại hoặc rỗng: {'/'.join(pair)}")
        if pair in seen:
            raise ReviewError(f"{label}: evidence bị trùng: {'/'.join(pair)}")
        seen.add(pair)


def schema_format() -> dict[str, Any]:
    return structured_schema_format(AcademicKnowledgeReview)


def structured_schema_format(response_model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": response_model.__name__,
        "strict": True,
        "schema": response_model.model_json_schema(),
    }


def generate_review(
    profile: dict[str, Any], jd: str, settings: ReviewSettings, *, client: Any | None = None
) -> AcademicKnowledgeReview:
    validate_profile(profile)
    validate_jd(jd)
    input_messages = [
        {"role": "user", "content": json.dumps({"student_academic_profile": profile}, ensure_ascii=False, allow_nan=False, indent=2)},
        {"role": "user", "content": json.dumps({"job_description": jd}, ensure_ascii=False)},
    ]
    raw = request_structured_response(
        ACADEMIC_REVIEW_INSTRUCTIONS, input_messages, AcademicKnowledgeReview, settings, client=client
    )
    return validate_review(raw, profile)


def request_structured_response(
    instructions: str, input_messages: list[dict[str, Any]], response_model: type[BaseModel],
    settings: ReviewSettings, *, client: Any | None = None, context_budget: int | None = None,
    operation_label: str = "review",
) -> Any:
    """One preflight and one generation, with the existing SDK failure policy."""
    budget = settings.context_window if context_budget is None else context_budget
    if type(budget) is not int or not settings.max_output_tokens < budget <= settings.context_window:
        raise ReviewError("Context budget phải lớn hơn output budget và không vượt context model")
    owned_client = client is None
    if owned_client:
        client = openai.OpenAI(api_key=settings.api_key, timeout=settings.timeout, max_retries=2)
    try:
        count = client.responses.input_tokens.count(
            timeout=settings.timeout,
            model=settings.model,
            instructions=instructions,
            input=input_messages,
            text={"format": structured_schema_format(response_model)},
            **settings.reasoning_options,
        )
        if type(count.input_tokens) is not int or count.input_tokens < 0:
            raise ReviewError("API đếm token trả về dữ liệu không hợp lệ")
        if count.input_tokens + settings.max_output_tokens > budget:
            raise ReviewError(
                f"Input ({count.input_tokens} tokens) + dự phòng output ({settings.max_output_tokens}) "
                f"vượt context ({budget}); không cắt bớt profile, JD hoặc history"
            )
        generation_options = {"temperature": settings.temperature} if settings.temperature is not None else {}
        response = client.responses.parse(
            timeout=settings.timeout,
            model=settings.model,
            instructions=instructions,
            input=input_messages,
            text_format=response_model,
            max_output_tokens=settings.max_output_tokens,
            truncation="disabled",
            store=False,
            **generation_options,
            **settings.reasoning_options,
        )
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "refusal":
                        raise ReviewError(f"Model từ chối tạo {operation_label} (refusal)")
        if response.status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", "unknown")
            raise ReviewError(f"Model trả response chưa hoàn tất (incomplete: {reason}); không lưu {operation_label}")
        if response.status != "completed":
            raise ReviewError(f"API không trả response completed; không lưu {operation_label}")
        if response.output_parsed is None:
            raise ReviewError("Response không có structured output có thể phân tích")
        return response.output_parsed
    except openai.AuthenticationError as exc:
        raise ReviewError("OpenAI từ chối xác thực; kiểm tra OPENAI_API_KEY") from exc
    except openai.RateLimitError as exc:
        message = "OpenAI hết quota hoặc chưa có billing" if exc.code == "insufficient_quota" else "OpenAI vượt rate limit"
        raise ReviewError(message) from exc
    except openai.APITimeoutError as exc:
        raise ReviewError("OpenAI timeout") from exc
    except openai.APIConnectionError as exc:
        raise ReviewError("Không kết nối được OpenAI") from exc
    except openai.APIStatusError as exc:
        raise ReviewError(f"OpenAI API lỗi HTTP {exc.status_code}; kiểm tra model/quyền truy cập/cấu hình") from exc
    except openai.APIError as exc:
        raise ReviewError(f"OpenAI SDK trả lỗi API; không lưu {operation_label}") from exc
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ReviewError("Response không phân tích được thành JSON đúng schema; có thể chưa hoàn tất") from exc
    finally:
        if owned_client:
            client.close()


def protect_input_paths(output: Path | str, *inputs: Path | str) -> None:
    output_path = Path(output)
    for input_file in inputs:
        input_path = Path(input_file)
        same_path = output_path.resolve() == input_path.resolve()
        if not same_path and output_path.exists() and input_path.exists():
            same_path = output_path.samefile(input_path)
        if same_path:
            raise ReviewError("Output không được ghi đè file đầu vào")


def write_review(path: Path | str, review: AcademicKnowledgeReview) -> None:
    output_path = Path(path)
    temporary_path: Path | None = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(review.model_dump(), file, ensure_ascii=False, allow_nan=False, indent=2)
            file.write("\n")
        temporary_path.replace(output_path)
    except OSError as exc:
        raise ReviewError(f"Không thể ghi review: {output_path}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def review_files(
    profile_path: Path | str, jd_path: Path | str, output_path: Path | str,
    *, settings: ReviewSettings | None = None, context_window: int | None = None,
    client: Any | None = None,
) -> AcademicKnowledgeReview:
    protect_input_paths(output_path, profile_path, jd_path)
    profile = load_profile(profile_path)
    jd = load_jd(jd_path)
    if settings is None:
        settings = load_settings(context_window)
    review = generate_review(profile, jd, settings, client=client)
    write_review(output_path, review)
    return review
