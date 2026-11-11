"""Service failures independent of CLI exit codes and HTTP status codes."""

from __future__ import annotations

import copy
from typing import Any

from scripts.academic_chat import ChatError


class ServiceError(ValueError):
    """An invalid service operation or unavailable source."""


class UnknownCurriculumError(ServiceError):
    pass


class UnknownCourseError(ServiceError):
    pass


class CourseDataError(ServiceError):
    pass


class InvalidMetadataError(CourseDataError):
    pass


class MissingAssessmentDataError(CourseDataError):
    pass


class InconsistentSourceDataError(CourseDataError):
    pass


class ScoreValidationError(ServiceError):
    """Submitted grades are invalid; details retain course/category locations."""

    def __init__(self, issues: list[dict[str, Any]], report: dict[str, Any] | None = None):
        self.issues = copy.deepcopy(issues)
        self.report = copy.deepcopy(report)
        super().__init__("Invalid academic input: " + ", ".join(issue["issue"] for issue in issues))


class SessionNotFoundError(ChatError):
    pass


class ResourceNotFoundError(ServiceError):
    code = "resource_not_found"


class AccessDeniedError(ServiceError):
    code = "access_denied"


class OperationConflictError(ServiceError):
    code = "session_busy"


class SessionNotReadyError(OperationConflictError):
    code = "session_not_ready"


class IdempotencyConflictError(OperationConflictError):
    code = "idempotency_conflict"


class OperationRunningError(OperationConflictError):
    code = "operation_running"


class OperationInterruptedError(OperationConflictError):
    code = "operation_interrupted"


class OwnershipLostError(OperationConflictError):
    code = "ownership_lost"


class StoredOperationFailedError(ServiceError):
    code = "operation_failed"


class StorageIntegrityError(ServiceError):
    code = "storage_integrity_error"


class BackendUnavailableError(ServiceError):
    code = "backend_unavailable"
