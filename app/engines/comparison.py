"""One comparison generation over a text-only CLO set and a JD."""

from app.json_utils import json_text
from app.llm import request_structured_response
from .models import ScoredCLOJDComparison, validate_clo_set, validate_comparison, validate_jd
from .prompts import COMPARISON_INSTRUCTIONS


def context_messages(clo_set, jd):
    source = validate_clo_set(clo_set).model_dump()
    return [{"role": "user", "content": json_text({"clo_set": source})},
            {"role": "user", "content": json_text({"job_description": validate_jd(jd)})}]


def generate_comparison(clo_set, jd, settings, *, client=None):
    raw = request_structured_response(COMPARISON_INSTRUCTIONS, context_messages(clo_set, jd),
                                      ScoredCLOJDComparison, settings, client=client, operation_label="comparison")
    return validate_comparison(raw, clo_set, require_radar=True)
