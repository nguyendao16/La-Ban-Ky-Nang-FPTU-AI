"""Service failures independent of CLI exit codes and HTTP status codes."""

from __future__ import annotations

import copy
from typing import Any

from app.engines.errors import ChatError


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


class InconsistentSourceDataError(CourseDataError):
    pass


class CLOSetValidationError(ServiceError):
    def __init__(self, issues):
        self.issues = copy.deepcopy(issues)
        super().__init__("Invalid course selection")


class IncompatibleDatabaseError(ServiceError):
    """Foreign/academic databases must never be migrated or reset."""


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
