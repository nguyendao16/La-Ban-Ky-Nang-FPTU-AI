from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def nonblank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Text must not be blank")
        return value


class SelectionRequest(RequestModel):
    curriculum_code: str = Field(min_length=1, max_length=128)
    selected_courses: list[str] = Field(min_length=1, max_length=256)
    combo: str | None = None


class SessionRequest(RequestModel):
    selection_id: str = Field(min_length=1, max_length=64)
    job_description: str | None = Field(default=None, min_length=1, max_length=100000)
    career_profile_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def exactly_one_target(self):
        if (self.job_description is None) == (self.career_profile_id is None):
            raise ValueError('Choose exactly one career profile or JD')
        return self


class MessageRequest(RequestModel):
    message: str = Field(min_length=1, max_length=100000)
