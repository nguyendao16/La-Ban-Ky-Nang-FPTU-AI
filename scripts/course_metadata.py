"""Read source course context without rewriting or interpreting its values."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIELDS = ("syllabus_name", "course_name_english", "subject_code", "description", "tools")


def validate_course_metadata(metadata: Any, course_code: str) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    for name in FIELDS:
        if name not in metadata or not isinstance(metadata[name], str):
            raise ValueError(f"metadata.{name} must be a string")
    if metadata["subject_code"] != course_code:
        raise ValueError(f"metadata.subject_code does not match course_code {course_code}")
    # Empty source strings are legitimate. Additional source fields are retained.
    json.dumps(metadata, ensure_ascii=False, allow_nan=False)
    return metadata


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate metadata field: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def read_course_metadata(courses_dir: Path, course_code: str) -> dict[str, Any]:
    path = courses_dir / course_code / "metadata.json"
    raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields,
                     parse_constant=_invalid_constant)
    return validate_course_metadata(raw, course_code)
