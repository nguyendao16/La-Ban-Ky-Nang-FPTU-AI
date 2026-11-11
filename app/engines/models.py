"""Domain contracts contain only course-scoped CLO text and comparisons."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator, model_serializer

from .errors import ComparisonError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def nonblank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Text must not be blank")
        return value


class CLO(StrictModel):
    clo: str
    description: str


class CourseCLOs(StrictModel):
    course_code: str
    clos: list[CLO] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_clos(self):
        if len({c.clo for c in self.clos}) != len(self.clos):
            raise ValueError("Duplicate CLO identifier within course")
        return self


class CLOSet(StrictModel):
    courses: list[CourseCLOs]

    @model_validator(mode="after")
    def unique_courses(self):
        if len({c.course_code for c in self.courses}) != len(self.courses):
            raise ValueError("Duplicate course identifier")
        return self


class EvidenceReference(StrictModel):
    course_code: str
    clo: str


class CareerRadarAxis(StrictModel):
    name: str = Field(max_length=64)
    description: str
    score: float = Field(ge=0, le=5, allow_inf_nan=False)
    comment: str
    evidence: list[EvidenceReference]


class CareerRadar(StrictModel):
    overall_score: float = Field(ge=0, le=5, allow_inf_nan=False)
    overall_comment: str
    axes: list[CareerRadarAxis] = Field(min_length=5, max_length=5)

    @model_validator(mode='after')
    def distinct_axes(self):
        names = [' '.join(axis.name.casefold().split()) for axis in self.axes]
        if len(set(names)) != 5:
            raise ValueError('Radar axes must have distinct names')
        return self


class RequirementComparison(StrictModel):
    jd_requirement: str = Field(description="A substantive required or preferred requirement grounded in the supplied JD.")
    coverage: Literal["covered", "related", "not_evidenced"]
    comment: str = Field(description="Vietnamese explanation comparing exact cited CLO descriptions with the requirement's topic and scope.")
    evidence: list[EvidenceReference]


class CLOJDComparison(StrictModel):
    comparison_type: Literal["clo_jd_comparison"]
    overview: str
    requirement_reviews: list[RequirementComparison]
    conclusion: str
    radar: CareerRadar | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_fingerprint(self, handler):
        result = handler(self)
        if self.radar is None and not type(self).model_fields['radar'].is_required():
            result.pop('radar', None)
        return result


class ScoredCLOJDComparison(CLOJDComparison):
    radar: CareerRadar | None


class ChatResponse(StrictModel):
    reply: str = Field(description="Natural Vietnamese explanation of the approved course-to-career or course-to-JD comparison and its content gaps. Use permitted structured evidence without exposing private course definitions, inventing personal abilities or adding learning roadmaps.")
    evidence: list[EvidenceReference]


def validation_details(exc: ValidationError):
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'root'}: {e['type']}"
                     for e in exc.errors(include_input=False, include_url=False))


def parse_model(model, raw):
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ComparisonError(f"Invalid {model.__name__}: {validation_details(exc)}", code="invalid_structured_output") from exc


def validate_clo_set(raw: Any) -> CLOSet:
    return parse_model(CLOSet, raw)


def validate_jd(raw):
    if not isinstance(raw, str) or not raw.strip():
        raise ComparisonError("JD must be nonempty text")
    return raw


def validate_evidence(references, clo_set):
    source = validate_clo_set(clo_set)
    allowed = {(course.course_code, clo.clo) for course in source.courses for clo in course.clos}
    seen = set()
    for reference in references:
        pair = (reference.course_code, reference.clo)
        if pair not in allowed or pair in seen:
            raise ComparisonError("Evidence must reference distinct CLOs in this snapshot", code="invalid_evidence")
        seen.add(pair)


def validate_radar(radar, source, *, enforce_score_consistency=False):
    texts = [radar.overall_comment]
    for axis in radar.axes:
        validate_evidence(axis.evidence, source)
        if axis.score > 0 and not axis.evidence:
            raise ComparisonError('A positive radar score needs supporting course evidence', code='invalid_evidence')
        texts.extend([axis.name, axis.description, axis.comment])
    if radar.overall_score > 0 and not any(axis.evidence for axis in radar.axes):
        raise ComparisonError('A positive overall score needs supporting course evidence', code='invalid_evidence')
    # New generations must be consistent; saved results keep their original policy.
    if enforce_score_consistency and radar.overall_score > max(axis.score for axis in radar.axes):
        raise ComparisonError('Overall score must not exceed the highest axis score', code='invalid_structured_output')
    return texts


def validate_comparison(raw, clo_set, *, require_radar=False):
    comparison = parse_model(ScoredCLOJDComparison if require_radar else CLOJDComparison, raw)
    if require_radar and comparison.requirement_reviews and comparison.radar is None:
        raise ComparisonError('A JD with comparable requirements needs radar data', code='invalid_structured_output')
    validate_clo_set(clo_set)
    for row in comparison.requirement_reviews:
        if (row.coverage == "not_evidenced") != (len(row.evidence) == 0):
            raise ComparisonError("Coverage and evidence disagree", code="invalid_coverage")
        validate_evidence(row.evidence, clo_set)
    from app.public_view import check_generated_text
    texts = [comparison.overview, comparison.conclusion, *[text for r in comparison.requirement_reviews for text in (r.jd_requirement, r.comment)]]
    if comparison.radar is not None:
        texts.extend(validate_radar(comparison.radar, clo_set, enforce_score_consistency=require_radar))
    check_generated_text(texts, validate_clo_set(clo_set).model_dump(), check_policy=require_radar)
    # Normalize explicit null from generation back to the legacy storage shape.
    return parse_model(CLOJDComparison, comparison) if require_radar else comparison


def validate_chat_response(raw, clo_set, *, check_policy=True):
    response = parse_model(ChatResponse, raw)
    validate_evidence(response.evidence, clo_set)
    from app.public_view import check_generated_text
    check_generated_text([response.reply], validate_clo_set(clo_set).model_dump(), check_policy=check_policy)
    return response
