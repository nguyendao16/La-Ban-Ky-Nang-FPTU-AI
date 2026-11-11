from __future__ import annotations

import hmac
import secrets
from uuid import uuid4

from app.services.errors import AccessDeniedError, ResourceNotFoundError, StorageIntegrityError
from scripts.academic_review import validate_profile

from .database import digest, json_read, json_text, token_digest, utc_timestamp


def authorized(row, access_token):
    if row is None:
        raise ResourceNotFoundError("Resource not found")
    if not isinstance(access_token, str) or not hmac.compare_digest(row["owner_hash"], token_digest(access_token)):
        raise AccessDeniedError("The capability does not authorize this resource")
    return row


def profile_record(row):
    try:
        profile = json_read(row["profile_json"])
        validate_profile(profile)
        if digest(profile) != row["fingerprint"]:
            raise ValueError("Profile fingerprint mismatch")
        return {"profile_id": row["profile_id"], "curriculum_code": row["curriculum_code"],
                "selected_courses": json_read(row["selected_courses_json"]), "grades": json_read(row["grades_json"]),
                "profile": profile, "fingerprint": row["fingerprint"],
                "diagnostics": json_read(row["diagnostics_json"]), "created_at": row["created_at"]}
    except (ValueError, TypeError, KeyError) as exc:
        raise StorageIntegrityError("Stored profile failed integrity validation") from exc


class ProfileRepository:
    def __init__(self, database):
        self.database = database

    def create(self, curriculum_code, selected_courses, grades, profile, diagnostics):
        validate_profile(profile)
        profile_id, token = uuid4().hex, secrets.token_urlsafe(32)
        with self.database.transaction(write=True) as connection:
            connection.execute("INSERT INTO profiles VALUES (?,?,?,?,?,?,?,?,?)", (
                profile_id, token_digest(token), curriculum_code, json_text(selected_courses),
                json_text(grades), json_text(profile), digest(profile), json_text(diagnostics),
                utc_timestamp(self.database.clock()),
            ))
        result = self.get(profile_id, token)
        result["access_token"] = token
        return result

    def get(self, profile_id, access_token):
        with self.database.transaction() as connection:
            row = authorized(connection.execute("SELECT * FROM profiles WHERE profile_id=?", (profile_id,)).fetchone(), access_token)
            return profile_record(row)
