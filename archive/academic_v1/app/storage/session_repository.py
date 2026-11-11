"""One snapshot history, fenced ownership and durable idempotency records."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import uuid4

from app.services.errors import (
    IdempotencyConflictError, OperationConflictError, OperationInterruptedError,
    OperationRunningError, OwnershipLostError, SessionNotReadyError,
    StorageIntegrityError, StoredOperationFailedError,
)

from .database import digest, json_read, json_text, token_digest, utc_timestamp
from .profile_repository import authorized, profile_record

SESSION_SELECT = """SELECT s.*, p.fingerprint AS profile_fingerprint,
    p.owner_hash AS profile_owner_hash FROM sessions s JOIN profiles p USING(profile_id)"""


@dataclass(frozen=True)
class Lease:
    session_id: str
    token: str
    generation: int
    revision: int
    operation_id: str


def replay_request(row, fingerprint):
    if row["request_fingerprint"] != fingerprint:
        raise IdempotencyConflictError("This key was used with a different request")
    if row["status"] == "succeeded":
        return json_read(row["response_json"])
    if row["status"] == "processing":
        raise OperationRunningError("The same request is still processing")
    if row["status"] == "interrupted":
        raise OperationInterruptedError("The previous operation is uncertain; it will not be rerun automatically")
    raise StoredOperationFailedError("The previous operation failed; it will not be rerun automatically")


class SessionRepository:
    def __init__(self, database, snapshot_validator):
        self.database = database
        self.snapshot_validator = snapshot_validator

    def _record(self, row):
        try:
            snapshot = self.snapshot_validator(json_read(row["snapshot_json"]))
            if (snapshot["session_id"] != row["session_id"]
                    or snapshot["fingerprints"]["profile"] != row["profile_fingerprint"]
                    or row["owner_hash"] != row["profile_owner_hash"]):
                raise ValueError("Immutable profile/session linkage mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise StorageIntegrityError("Stored session failed integrity validation") from exc
        return {"session_id": row["session_id"], "profile_id": row["profile_id"], "snapshot": snapshot,
                "revision": row["revision"], "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def get(self, session_id, access_token):
        with self.database.transaction() as connection:
            row = authorized(connection.execute(SESSION_SELECT + " WHERE s.session_id=?", (session_id,)).fetchone(), access_token)
            result = self._record(row)
            job = connection.execute("SELECT * FROM jobs WHERE session_id=?", (session_id,)).fetchone()
            if job is None or (job["status"] == "succeeded") != (result["snapshot"]["review"] is not None):
                raise StorageIntegrityError("Review job and academic state disagree")
            result["job"] = self.public_job(job)
            return result

    @staticmethod
    def public_job(row):
        return {key: row[key] for key in ["job_id", "job_type", "status", "created_at", "started_at", "finished_at",
                                        "attempt_count", "error_code", "error_message", "last_heartbeat", "dispatched_at"]}

    def create_with_job(self, profile_id, access_token, job_description, key, snapshot_factory):
        fingerprint = digest({"profile_id": profile_id, "job_description": job_description})
        with self.database.transaction(write=True) as connection:
            profile_row = authorized(connection.execute("SELECT * FROM profiles WHERE profile_id=?", (profile_id,)).fetchone(), access_token)
            existing = connection.execute("SELECT * FROM requests WHERE owner_hash=? AND scope='create-session' AND key_hash=?",
                                          (profile_row["owner_hash"], token_digest(key))).fetchone()
            if existing:
                return replay_request(existing, fingerprint)
            profile = profile_record(profile_row)["profile"]
            snapshot = self.snapshot_validator(snapshot_factory(profile, job_description))
            if (snapshot["profile"] != profile or snapshot["job_description"] != job_description
                    or snapshot["review"] is not None or snapshot["messages"]):
                raise StorageIntegrityError("New session must contain exactly the stored profile/JD and no Review/history")
            session_id, request_id, job_id = snapshot["session_id"], uuid4().hex, uuid4().hex
            now = utc_timestamp(self.database.clock())
            connection.execute("INSERT INTO sessions(session_id,profile_id,owner_hash,snapshot_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                               (session_id, profile_id, profile_row["owner_hash"], json_text(snapshot), now, now))
            response = {"session_id": session_id, "status": "queued", "review_job": {"job_id": job_id, "status": "queued"}}
            connection.execute("""INSERT INTO requests(request_id,owner_hash,scope,key_hash,request_fingerprint,
                session_id,status,response_json,created_at,finished_at) VALUES(?,?,?,?,?,?,'succeeded',?,?,?)""",
                (request_id, profile_row["owner_hash"], "create-session", token_digest(key), fingerprint,
                 session_id, json_text(response), now, now))
            connection.execute("INSERT INTO jobs(job_id,session_id,request_id,job_type,status,created_at) VALUES(?,?,?,'initial_review','queued',?)",
                               (job_id, session_id, request_id, now))
            return response

    def claim_locked(self, connection, row, operation_id, now):
        """Caller holds BEGIN IMMEDIATE; job/chat claims share this fence."""
        if row["lease_token"] is not None:
            raise OperationConflictError("Another operation owns this session")
        token, generation = secrets.token_hex(32), row["lease_generation"] + 1
        changed = connection.execute("""UPDATE sessions SET lease_token=?,lease_generation=?,lease_expires_at=?,
            last_heartbeat=?,lease_operation_id=? WHERE session_id=? AND lease_token IS NULL AND revision=?""",
            (token, generation, now + self.database.lease_seconds, utc_timestamp(now), operation_id,
             row["session_id"], row["revision"])).rowcount
        if changed != 1:
            raise OperationConflictError("Session ownership changed")
        return Lease(row["session_id"], token, generation, row["revision"], operation_id)

    def assert_owned(self, connection, lease, now):
        row = connection.execute(SESSION_SELECT + " WHERE s.session_id=?", (lease.session_id,)).fetchone()
        if (row is None or row["lease_token"] != lease.token or row["lease_generation"] != lease.generation
                or row["revision"] != lease.revision or row["lease_operation_id"] != lease.operation_id
                or row["lease_expires_at"] is None or row["lease_expires_at"] <= now):
            raise OwnershipLostError("Operation ownership expired or changed; output cannot be committed")
        return row

    def load_owned(self, lease):
        with self.database.transaction() as connection:
            return self._record(self.assert_owned(connection, lease, self.database.clock()))["snapshot"]

    def renew(self, lease):
        with self.database.transaction(write=True) as connection:
            now = self.database.clock()
            self.assert_owned(connection, lease, now)
            expires, stamp = now + self.database.lease_seconds, utc_timestamp(now)
            connection.execute("UPDATE sessions SET lease_expires_at=?,last_heartbeat=? WHERE session_id=?",
                               (expires, stamp, lease.session_id))
            connection.execute("""UPDATE jobs SET lease_expires_at=?,last_heartbeat=?
                WHERE job_id=? AND status='processing' AND lease_token=? AND lease_generation=?""",
                (expires, stamp, lease.operation_id, lease.token, lease.generation))

    def mark_dispatched(self, lease):
        with self.database.transaction(write=True) as connection:
            now = self.database.clock()
            self.assert_owned(connection, lease, now)
            stamp = utc_timestamp(now)
            connection.execute("UPDATE requests SET dispatched_at=? WHERE request_id=? AND status='processing'", (stamp, lease.operation_id))
            connection.execute("""UPDATE jobs SET dispatched_at=? WHERE job_id=? AND status='processing'
                AND lease_token=? AND lease_generation=?""", (stamp, lease.operation_id, lease.token, lease.generation))

    def _release(self, connection, lease):
        connection.execute("""UPDATE sessions SET lease_token=NULL,lease_expires_at=NULL,lease_operation_id=NULL
            WHERE session_id=? AND lease_token=? AND lease_generation=?""", (lease.session_id, lease.token, lease.generation))

    def recover_expired_locked(self, connection, now, session_id=None):
        sql = "SELECT * FROM sessions WHERE lease_token IS NOT NULL AND lease_expires_at<=?"
        parameters = [now]
        if session_id is not None:
            sql += " AND session_id=?"
            parameters.append(session_id)
        rows = connection.execute(sql, parameters).fetchall()
        for row in rows:
            stamp = utc_timestamp(now)
            connection.execute("""UPDATE jobs SET status='interrupted',finished_at=?,error_code='lease_expired',
                error_message='Ownership expired; remote outcome may be unknown',lease_token=NULL,lease_expires_at=NULL
                WHERE job_id=? AND status='processing' AND lease_token=? AND lease_generation=?""",
                (stamp, row["lease_operation_id"], row["lease_token"], row["lease_generation"]))
            connection.execute("""UPDATE requests SET status='interrupted',finished_at=?,error_code='lease_expired',
                error_message='Ownership expired; remote outcome may be unknown'
                WHERE request_id=? AND status='processing'""", (stamp, row["lease_operation_id"]))
            connection.execute("""UPDATE sessions SET lease_token=NULL,lease_expires_at=NULL,lease_operation_id=NULL,
                lease_generation=lease_generation+1 WHERE session_id=?""", (row["session_id"],))
        return len(rows)

    def recover_expired(self):
        with self.database.transaction(write=True) as connection:
            return self.recover_expired_locked(connection, self.database.clock())

    def claim_chat(self, session_id, access_token, message, key):
        fingerprint = digest({"message": message})
        scope = f"chat:{session_id}"
        # Recovery must commit even when replay below reports interrupted work.
        with self.database.transaction(write=True) as connection:
            authorized(connection.execute(SESSION_SELECT + " WHERE s.session_id=?", (session_id,)).fetchone(), access_token)
            self.recover_expired_locked(connection, self.database.clock(), session_id)
        with self.database.transaction(write=True) as connection:
            row = authorized(connection.execute(SESSION_SELECT + " WHERE s.session_id=?", (session_id,)).fetchone(), access_token)
            existing = connection.execute("SELECT * FROM requests WHERE owner_hash=? AND scope=? AND key_hash=?",
                                          (row["owner_hash"], scope, token_digest(key))).fetchone()
            if existing:
                snapshot = self._record(row)["snapshot"]
                cached = replay_request(existing, fingerprint)
                number = existing["turn_number"]
                if number is None or number < 1 or number * 2 > len(snapshot["messages"]):
                    raise StorageIntegrityError("Cached response has no committed turn")
                user, assistant = snapshot["messages"][(number - 1) * 2:number * 2]
                if (user["content"] != message or cached != {"message_id": existing["request_id"],
                        "reply": assistant["content"], "evidence": assistant["evidence"]}):
                    raise StorageIntegrityError("Response cache disagrees with authoritative history")
                return None, cached
            job = connection.execute("SELECT status FROM jobs WHERE session_id=?", (session_id,)).fetchone()
            if job is None or job["status"] != "succeeded":
                raise SessionNotReadyError("Initial Review is not ready")
            if self._record(row)["snapshot"]["review"] is None:
                raise StorageIntegrityError("Ready job has no committed Review")
            request_id = uuid4().hex
            now = self.database.clock()
            lease = self.claim_locked(connection, row, request_id, now)
            connection.execute("""INSERT INTO requests(request_id,owner_hash,scope,key_hash,request_fingerprint,
                session_id,status,created_at) VALUES(?,?,?,?,?,?,'processing',?)""",
                (request_id, row["owner_hash"], scope, token_digest(key), fingerprint, session_id, utc_timestamp(now)))
            return lease, None

    def commit_snapshot_locked(self, connection, lease, snapshot, *, kind):
        now = self.database.clock()
        row = self.assert_owned(connection, lease, now)
        old = self._record(row)["snapshot"]
        new = self.snapshot_validator(snapshot)
        if (new["session_id"] != old["session_id"] or new["profile"] != old["profile"]
                or new["job_description"] != old["job_description"]):
            raise StorageIntegrityError("Immutable academic context cannot change")
        if kind == "review":
            valid = old["review"] is None and new["review"] is not None and not old["messages"] and not new["messages"]
        else:
            valid = (new["review"] == old["review"] and new["messages"][:-2] == old["messages"]
                     and len(new["messages"]) == len(old["messages"]) + 2)
        if not valid:
            raise StorageIntegrityError("Snapshot is not one complete valid operation")
        changed = connection.execute("""UPDATE sessions SET snapshot_json=?,revision=revision+1,updated_at=?,
            lease_token=NULL,lease_expires_at=NULL,lease_operation_id=NULL
            WHERE session_id=? AND lease_token=? AND lease_generation=? AND revision=? AND lease_expires_at>?""",
            (json_text(new), utc_timestamp(now), lease.session_id, lease.token, lease.generation, lease.revision, now)).rowcount
        if changed != 1:
            raise OwnershipLostError("Stale session commit rejected")
        return new

    def commit_chat(self, lease, snapshot, response):
        with self.database.transaction(write=True) as connection:
            new = self.commit_snapshot_locked(connection, lease, snapshot, kind="chat")
            raw = response.model_dump()
            assistant = new["messages"][-1]
            if raw != {"reply": assistant["content"], "evidence": assistant["evidence"]}:
                raise StorageIntegrityError("Response cache disagrees with committed assistant turn")
            result = {"message_id": lease.operation_id, **raw}
            changed = connection.execute("""UPDATE requests SET status='succeeded',response_json=?,turn_number=?,finished_at=?
                WHERE request_id=? AND session_id=? AND status='processing'""",
                (json_text(result), len(new["messages"]) // 2, utc_timestamp(self.database.clock()),
                 lease.operation_id, lease.session_id)).rowcount
            if changed != 1:
                raise OwnershipLostError("Operation result could not be committed")
            return result

    def finish_failure(self, lease, *, status, code, message):
        """Release only our own fence; a stale caller cannot change new work."""
        with self.database.transaction(write=True) as connection:
            row = connection.execute("SELECT * FROM sessions WHERE session_id=?", (lease.session_id,)).fetchone()
            if (row is None or row["lease_token"] != lease.token or row["lease_generation"] != lease.generation
                    or row["revision"] != lease.revision or row["lease_operation_id"] != lease.operation_id):
                return False
            # An expired operation is uncertain even if a late owner reports failure.
            if row["lease_expires_at"] <= self.database.clock():
                status, code, message = "interrupted", "lease_expired", "Ownership expired; remote outcome may be unknown"
            stamp = utc_timestamp(self.database.clock())
            connection.execute("""UPDATE requests SET status=?,error_code=?,error_message=?,finished_at=?
                WHERE request_id=? AND status='processing'""", (status, code, message, stamp, lease.operation_id))
            connection.execute("""UPDATE jobs SET status=?,error_code=?,error_message=?,finished_at=?,
                lease_token=NULL,lease_expires_at=NULL WHERE job_id=? AND status='processing'
                AND lease_token=? AND lease_generation=?""", (status, code, message, stamp,
                lease.operation_id, lease.token, lease.generation))
            self._release(connection, lease)
            return True

    def history(self, session_id, access_token):
        with self.database.transaction() as connection:
            row = authorized(connection.execute(SESSION_SELECT + " WHERE s.session_id=?", (session_id,)).fetchone(), access_token)
            snapshot = self._record(row)["snapshot"]
            identifiers = {r["turn_number"]: r["request_id"] for r in connection.execute(
                "SELECT turn_number,request_id FROM requests WHERE session_id=? AND status='succeeded' AND turn_number IS NOT NULL ORDER BY turn_number", (session_id,))}
            if len(identifiers) != len(snapshot["messages"]) // 2:
                raise StorageIntegrityError("Turn identifiers disagree with authoritative history")
            turns = []
            for offset in range(0, len(snapshot["messages"]), 2):
                number = offset // 2 + 1
                if number not in identifiers:
                    raise StorageIntegrityError("Committed turn identifier is missing")
                user, assistant = snapshot["messages"][offset:offset + 2]
                turns.append({"message_id": identifiers[number], "sequence": number, "user_message": user["content"],
                              "reply": assistant["content"], "evidence": assistant["evidence"]})
            return turns
