from __future__ import annotations

from app.services.errors import OperationConflictError, OwnershipLostError, ResourceNotFoundError

from .database import json_read, json_text, utc_timestamp


class JobRepository:
    def __init__(self, database, sessions):
        self.database = database
        self.sessions = sessions

    def claim_next(self):
        self.sessions.recover_expired()
        with self.database.transaction(write=True) as connection:
            row = connection.execute("""SELECT j.job_id,s.* FROM jobs j JOIN sessions s USING(session_id)
                WHERE j.status='queued' AND s.lease_token IS NULL ORDER BY j.created_at,j.job_id LIMIT 1""").fetchone()
            if row is None:
                return None
            now = self.database.clock()
            lease = self.sessions.claim_locked(connection, row, row["job_id"], now)
            changed = connection.execute("""UPDATE jobs SET status='processing',started_at=?,finished_at=NULL,
                attempt_count=attempt_count+1,lease_token=?,lease_generation=?,lease_expires_at=?,last_heartbeat=?
                WHERE job_id=? AND status='queued'""", (utc_timestamp(now), lease.token, lease.generation,
                now + self.database.lease_seconds, utc_timestamp(now), row["job_id"])).rowcount
            if changed != 1:
                raise OwnershipLostError("Review claim lost")
            return lease

    def commit_review(self, lease, snapshot):
        with self.database.transaction(write=True) as connection:
            self.sessions.commit_snapshot_locked(connection, lease, snapshot, kind="review")
            now = self.database.clock()
            changed = connection.execute("""UPDATE jobs SET status='succeeded',finished_at=?,error_code=NULL,
                error_message=NULL,lease_token=NULL,lease_expires_at=NULL WHERE job_id=? AND status='processing'
                AND lease_token=? AND lease_generation=? AND lease_expires_at>?""",
                (utc_timestamp(now), lease.operation_id, lease.token, lease.generation, now)).rowcount
            if changed != 1:
                raise OwnershipLostError("Review result lost its ownership fence")

    def get(self, job_id):
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ResourceNotFoundError("Job not found")
            return self.sessions.public_job(row)

    def retry(self, job_id, *, acknowledge_possible_duplicate=False):
        """Explicit operator action only; never called by polling/claiming."""
        self.sessions.recover_expired()
        with self.database.transaction(write=True) as connection:
            job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise ResourceNotFoundError("Job not found")
            session = connection.execute("SELECT * FROM sessions WHERE session_id=?", (job["session_id"],)).fetchone()
            if job["status"] not in {"failed", "interrupted"} or session["lease_token"] is not None:
                raise OperationConflictError("Only an unowned failed/interrupted job can be explicitly retried")
            if job["dispatched_at"] is not None and not acknowledge_possible_duplicate:
                raise OperationConflictError("A remote request may have run; acknowledge possible duplicate generation before retry")
            history = json_read(job["recovery_log_json"])
            history.append({"retried_at": utc_timestamp(self.database.clock()), "previous_status": job["status"],
                            "attempt_count": job["attempt_count"], "dispatched_at": job["dispatched_at"],
                            "error_code": job["error_code"], "error_message": job["error_message"],
                            "acknowledged_possible_duplicate": acknowledge_possible_duplicate})
            connection.execute("""UPDATE jobs SET status='queued',started_at=NULL,finished_at=NULL,error_code=NULL,
                error_message=NULL,lease_token=NULL,lease_expires_at=NULL,last_heartbeat=NULL,dispatched_at=NULL,
                recovery_log_json=? WHERE job_id=?""", (json_text(history), job_id))
            return {"job_id": job_id, "status": "queued"}

    def worker_heartbeat(self, worker_id, *, state="running"):
        with self.database.transaction(write=True) as connection:
            now, stamp = self.database.clock(), utc_timestamp(self.database.clock())
            connection.execute("""INSERT INTO workers VALUES(?,?,?,?,?) ON CONFLICT(worker_id)
                DO UPDATE SET last_heartbeat=excluded.last_heartbeat,last_seen_epoch=excluded.last_seen_epoch,state=excluded.state""",
                (worker_id, stamp, stamp, now, state))
