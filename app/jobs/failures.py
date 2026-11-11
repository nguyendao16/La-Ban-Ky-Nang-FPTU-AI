"""Safe operational errors; never persist exception payloads or credentials."""

import openai

from app.services.errors import OwnershipLostError, StorageIntegrityError
from app.engines.errors import ComparisonError


MODEL_FAILURE_MESSAGES = {
    "invalid_recommendations": "Model response referenced invalid course sources; no result was saved",
    "model_output_limit": "Model reached the output token limit; no comparison was saved",
    "model_response_incomplete": "Model response was incomplete; no comparison was saved",
    "model_refusal": "Model declined the request; no comparison was saved",
    "missing_structured_output": "Model returned no structured output; no comparison was saved",
    "invalid_response_status": "Model response did not complete; no comparison was saved",
    "invalid_structured_output": "Model output did not match the required schema; no comparison was saved",
    "invalid_evidence": "Model evidence was invalid or duplicated; no comparison was saved",
    "invalid_coverage": "Model coverage and evidence did not agree; no comparison was saved",
    "private_source_disclosure": "Model response failed the source privacy check; no comparison was saved",
    "private_policy_disclosure": "Model response failed privacy validation; no result was saved",
    "context_limit": "Input and output budgets exceeded the model context limit",
    "authentication_failed": "AI provider authentication failed; check worker credentials",
    "quota_exhausted": "AI provider quota was exhausted; check billing",
    "rate_limited": "AI provider rate limit was reached",
    "upstream_api_error": "AI provider rejected the request; check worker configuration and model access",
}


def classify_failure(error, phase):
    if isinstance(error, (KeyboardInterrupt, SystemExit, OwnershipLostError)):
        return "interrupted", "operation_interrupted", "Operation interrupted; remote outcome may be unknown"
    if isinstance(error, StorageIntegrityError):
        return "failed", "storage_integrity_error", "Stored comparison data failed validation"
    if phase == "prepare":
        return "failed", "configuration_or_input_error", "Operation could not start; check local configuration and stored input"
    cause = error
    while cause is not None:
        if isinstance(cause, (openai.APIConnectionError, openai.APITimeoutError)):
            return "interrupted", "remote_outcome_unknown", "Remote operation outcome is unknown; no automatic retry"
        cause = cause.__cause__
    if phase == "commit" or not isinstance(error, ComparisonError):
        return "interrupted", "result_not_committed", "Operation result was not committed; no automatic regeneration"
    # Only fixed messages may reach persistence, API responses, and worker logs.
    if isinstance(error.code, str) and error.code in MODEL_FAILURE_MESSAGES:
        return "failed", error.code, MODEL_FAILURE_MESSAGES[error.code]
    return "failed", "generation_failed", "Model operation failed validation or execution; comparison state was not changed"
