import json
import sqlite3

import pytest

from app.services.errors import OwnershipLostError, StorageIntegrityError
from app.storage.database import Database, json_text
from app.storage.session_repository import SessionRepository


def test_initialization_idempotency_wal_foreign_keys_and_reopen(api_backend, stored_profile, queued_session):
    api_backend.database.initialize()
    api_backend.database.initialize()
    with api_backend.database.transaction() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    fresh_db = Database(api_backend.settings.database_path)
    fresh = SessionRepository(fresh_db, api_backend.advisor.validate_snapshot)
    restored = fresh.get(queued_session["session_id"], queued_session["access_token"])
    assert restored["snapshot"]["profile"] == stored_profile["profile"] and restored["snapshot"]["review"] is None
    assert restored["created_at"].endswith("+00:00")
    with pytest.raises(sqlite3.IntegrityError), fresh_db.transaction(write=True) as connection:
        connection.execute("UPDATE profiles SET curriculum_code='changed'")
    with pytest.raises(sqlite3.IntegrityError), fresh_db.transaction(write=True) as connection:
        connection.execute("""INSERT INTO sessions(session_id,profile_id,owner_hash,snapshot_json,created_at,updated_at)
            VALUES('bad','missing','hash','{}','now','now')""")


def test_session_and_job_creation_rollback_together(api_backend, stored_profile):
    with api_backend.database.transaction(write=True) as connection:
        connection.execute("CREATE TRIGGER no_jobs BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT,'test'); END")
    response = api_backend.client.post("/api/v1/advisor/sessions", headers={
        "Authorization": "Bearer " + stored_profile["access_token"], "Idempotency-Key": "rollback"},
        json={"profile_id": stored_profile["profile_id"], "job_description": "SQL"})
    assert response.status_code == 503
    with api_backend.database.transaction() as connection:
        for table in ["sessions", "jobs", "requests"]:
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("field", ["job_description", "profile", "fingerprints", "messages"])
def test_corrupted_snapshot_is_rejected_before_generation(api_backend, queued_session, field):
    with api_backend.database.transaction(write=True) as connection:
        snapshot = json.loads(connection.execute("SELECT snapshot_json FROM sessions").fetchone()[0])
        if field == "job_description": snapshot[field] += " changed"
        elif field == "profile": snapshot[field]["courses"][0]["clos"][0]["score"] = 2
        elif field == "fingerprints": snapshot[field]["jd"] = "0" * 64
        else: snapshot[field] = [{"role": "user", "content": "unfinished"}]
        connection.execute("UPDATE sessions SET snapshot_json=?", (json_text(snapshot),))
    response = api_backend.client.get("/api/v1/advisor/sessions/" + queued_session["session_id"], headers=queued_session["headers"])
    assert response.status_code == 500 and response.json()["error"]["code"] == "storage_integrity_error"
    api_backend.review_client.responses.parse.assert_not_called()


def test_revision_fences_and_single_review_commit(api_backend, queued_session):
    jobs = api_backend.backend.jobs
    lease = jobs.claim_next()
    assert jobs.claim_next() is None
    snapshot = api_backend.backend.sessions.load_owned(lease)
    updated, _ = api_backend.advisor.review_snapshot(snapshot)
    jobs.commit_review(lease, updated)
    with pytest.raises(OwnershipLostError): jobs.commit_review(lease, updated)
    record = api_backend.backend.sessions.get(lease.session_id, queued_session["access_token"])
    assert record["revision"] == 1 and record["snapshot"]["review"] is not None


def test_profile_changes_create_new_versions_without_changing_session(api_backend, queued_session, stored_profile):
    updated = api_backend.backend.profiles.create("configured", ["TEST101"], [], stored_profile["profile"], stored_profile["diagnostics"])
    assert updated["profile_id"] != stored_profile["profile_id"]
    record = api_backend.backend.sessions.get(queued_session["session_id"], queued_session["access_token"])
    assert record["profile_id"] == stored_profile["profile_id"] and record["snapshot"]["profile"] == stored_profile["profile"]
