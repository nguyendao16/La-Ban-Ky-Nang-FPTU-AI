"""Reusable service contracts; importing never loads settings or creates clients."""

from scripts.academic_chat import ReviewAlreadyReadyError, ReviewNotReadyError

from .advisor_service import AdvisorService, AdvisorSessionView
from .course_service import CourseService
from .errors import (
    CourseDataError, InconsistentSourceDataError, InvalidMetadataError,
    MissingAssessmentDataError, ScoreValidationError, ServiceError,
    SessionNotFoundError, UnknownCourseError, UnknownCurriculumError,
)
from .profile_service import GradeEntry, ProfileService

__all__ = [
    "CourseService", "ProfileService", "GradeEntry", "AdvisorService", "AdvisorSessionView",
    "ServiceError", "CourseDataError", "InconsistentSourceDataError", "InvalidMetadataError",
    "MissingAssessmentDataError", "ScoreValidationError", "SessionNotFoundError",
    "UnknownCourseError", "UnknownCurriculumError", "ReviewNotReadyError", "ReviewAlreadyReadyError",
]
