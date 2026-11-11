import sqlite3

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import (
    AccessDeniedError, BackendUnavailableError, CourseDataError, OperationConflictError,
    ResourceNotFoundError, ScoreValidationError, ServiceError, StorageIntegrityError,
    StoredOperationFailedError, UnknownCourseError, UnknownCurriculumError,
)
from scripts.academic_review import ReviewError


def error_response(status, code, message, *, details=None, headers=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status, content={"error": error}, headers=headers)


def register_handlers(app):
    @app.exception_handler(RequestValidationError)
    async def malformed(request, error):
        details = [{"location": list(i["loc"]), "type": i["type"], "message": i["msg"]} for i in error.errors()]
        return error_response(422, "invalid_request", "Request validation failed", details=details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        code = "unauthorized" if error.status_code == 401 else ("resource_not_found" if error.status_code == 404 else "invalid_request")
        return error_response(error.status_code, code,
                              str(error.detail), headers=error.headers)

    @app.exception_handler(ServiceError)
    async def domain(request, error):
        if isinstance(error, ScoreValidationError):
            return error_response(422, "invalid_scores", "Academic input is invalid", details=error.issues)
        for kind, status, code, message in [
            (AccessDeniedError, 403, "access_denied", "Capability does not authorize this resource"),
            (ResourceNotFoundError, 404, "resource_not_found", "Resource not found"),
            (UnknownCourseError, 404, "unknown_course", "Course is absent from the requested curriculum"),
            (UnknownCurriculumError, 404, "unknown_curriculum", "Curriculum is not configured or has no processed records"),
            (BackendUnavailableError, 503, "backend_unavailable", "Backend configuration or storage is unavailable"),
            (CourseDataError, 503, "course_data_unavailable", "Canonical course data is unavailable or inconsistent"),
            (StorageIntegrityError, 500, "storage_integrity_error", "Stored academic data failed validation"),
            (StoredOperationFailedError, 502, "operation_failed", "Model operation failed; academic state was not changed"),
        ]:
            if isinstance(error, kind):
                return error_response(status, code, message)
        if isinstance(error, OperationConflictError):
            return error_response(409, error.code, str(error))
        return error_response(422, "invalid_input", "Service input is invalid")

    @app.exception_handler(ReviewError)
    async def engine_error(request, error):
        return error_response(422, "invalid_academic_data", "Academic data failed existing engine validation")

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, error):
        return error_response(503, "storage_unavailable", "Database operation is unavailable")

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return error_response(500, "internal_error", "Unexpected backend failure")
