from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def nonblank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Text must not be blank")
        return value


class GradeRequest(RequestModel):
    course_code: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=256)
    grade: Annotated[StrictFloat, Field(allow_inf_nan=False)] | StrictInt | StrictStr | None


class ProfileRequest(RequestModel):
    curriculum_code: str = Field(min_length=1, max_length=128)
    selected_courses: list[str] = Field(min_length=1, max_length=256)
    grades: list[GradeRequest] = Field(max_length=4096)


class SessionRequest(RequestModel):
    profile_id: str = Field(min_length=1, max_length=64)
    job_description: str = Field(min_length=1, max_length=100000)


class MessageRequest(RequestModel):
    message: str = Field(min_length=1, max_length=100000)
