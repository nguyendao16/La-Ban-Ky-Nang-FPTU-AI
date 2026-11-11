"""Strict JSON serialization shared by snapshots, storage and engines."""

import hashlib
import json


def unique_json_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON contains duplicate fields")
        result[key] = value
    return result


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def json_read(value):
    def invalid_constant(raw):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(value, object_pairs_hook=unique_json_fields, parse_constant=invalid_constant)


def digest(value):
    canonical = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
