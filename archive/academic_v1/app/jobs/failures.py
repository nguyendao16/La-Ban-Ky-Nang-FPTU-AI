"""Safe operational errors; never persist exception payloads or credentials."""

import openai

from app.services.errors import OwnershipLostError, StorageIntegrityError
from scripts.academic_review import ReviewError


def classify_failure(error, phase):
    if isinstance(error, (KeyboardInterrupt, SystemExit, OwnershipLostError)):
        return "interrupted", "operation_interrupted", "Operation interrupted; remote outcome may be unknown"
    if isinstance(error, StorageIntegrityError):
        return "failed", "storage_integrity_error", "Stored academic data failed validation"
    if phase == "prepare":
        return "failed", "configuration_or_input_error", "Operation could not start; check local configuration and stored input"
    cause = error
    while cause is not None:
        if isinstance(cause, (openai.APIConnectionError, openai.APITimeoutError)):
            return "interrupted", "remote_outcome_unknown", "Remote operation outcome is unknown; no automatic retry"
        cause = cause.__cause__
    if phase == "commit" or not isinstance(error, ReviewError):
        return "interrupted", "result_not_committed", "Operation result was not committed; no automatic regeneration"
    return "failed", "generation_failed", "Model operation failed validation or execution; academic state was not changed"
