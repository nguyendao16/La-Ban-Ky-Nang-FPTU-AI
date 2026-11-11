"""Immutable CLO sets and capability ownership, separate from engine payloads."""

import hmac
import secrets
from uuid import uuid4

from app.engines.models import validate_clo_set
from app.services.errors import AccessDeniedError, ResourceNotFoundError, StorageIntegrityError
from .database import digest, json_read, json_text, token_digest, utc_timestamp


def authorized(row, access_token):
    if row is None:
        raise ResourceNotFoundError("Resource not found")
    if not isinstance(access_token, str) or not hmac.compare_digest(row["owner_hash"], token_digest(access_token)):
        raise AccessDeniedError("The capability does not authorize this resource")
    return row


def clo_set_record(row):
    try:
        source = json_read(row["clo_set_json"])
        validate_clo_set(source)
        selected = json_read(row["selected_courses_json"])
        diagnostics = json_read(row["diagnostics_json"])
        if not isinstance(diagnostics, dict) or not isinstance(selected, list) or any(not isinstance(c, str) for c in selected):
            raise ValueError("Invalid selection metadata")
        omitted = diagnostics.get("excluded_courses", [])
        if not isinstance(omitted, list) or any(not isinstance(c, str) for c in omitted):
            raise ValueError("Invalid excluded courses")
        source_codes = [c["course_code"] for c in source["courses"]]
        if (digest(source) != row["fingerprint"] or len(selected) != len(set(selected))
                or set(omitted) & set(source_codes)
                or [c for c in selected if c not in omitted] != source_codes
                or set(selected) != set(source_codes) | set(omitted)
                or diagnostics.get("selection_fingerprint", digest(selected)) != digest(selected)):
            raise ValueError("CLO set fingerprint/selection mismatch")
        return {"clo_set_id": row["clo_set_id"], "curriculum_code": row["curriculum_code"],
                "selected_courses": selected, "clo_set": source, "fingerprint": row["fingerprint"],
                "diagnostics": json_read(row["diagnostics_json"]), "created_at": row["created_at"]}
    except (ValueError, TypeError, KeyError) as exc:
        raise StorageIntegrityError("Stored CLO set failed integrity validation") from exc


class CLOSetRepository:
    def __init__(self, database):
        self.database = database

    def create(self, curriculum_code, selected_courses, clo_set, diagnostics=None):
        source = validate_clo_set(clo_set).model_dump()
        diagnostics = dict(diagnostics or {})
        omitted = diagnostics.get("excluded_courses", [])
        if ([c for c in selected_courses if c not in omitted] != [c["course_code"] for c in source["courses"]]
                or len(selected_courses) != len(set(selected_courses))
                or set(omitted) - set(selected_courses)
                or set(omitted) & {c["course_code"] for c in source["courses"]}):
            raise StorageIntegrityError("Selection must match the CLO set")
        diagnostics["selection_fingerprint"] = digest(list(selected_courses))
        identifier, token = uuid4().hex, secrets.token_urlsafe(32)
        with self.database.transaction(write=True) as connection:
            connection.execute("""INSERT INTO clo_sets(clo_set_id,owner_hash,curriculum_code,selected_courses_json,
                clo_set_json,fingerprint,diagnostics_json,created_at) VALUES(?,?,?,?,?,?,?,?)""", (
                identifier, token_digest(token), curriculum_code, json_text(list(selected_courses)),
                json_text(source), digest(source), json_text(diagnostics or {}), utc_timestamp(self.database.clock())))
        result = self.get(identifier, token)
        result["access_token"] = token
        return result

    def get(self, clo_set_id, access_token):
        with self.database.transaction() as connection:
            row = authorized(connection.execute("SELECT * FROM clo_sets WHERE clo_set_id=?", (clo_set_id,)).fetchone(), access_token)
            return clo_set_record(row)
