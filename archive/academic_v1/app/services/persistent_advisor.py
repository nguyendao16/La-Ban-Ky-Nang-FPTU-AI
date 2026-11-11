"""SQLite application adapter around the existing snapshot-based service."""

from app.jobs.failures import classify_failure
from app.jobs.heartbeat import OperationHeartbeat
from app.services.errors import BackendUnavailableError, ServiceError, StoredOperationFailedError


class PersistentAdvisor:
    def __init__(self, advisor, sessions, *, settings, heartbeat_factory=OperationHeartbeat):
        self.advisor, self.sessions, self.settings = advisor, sessions, settings
        self.heartbeat_factory = heartbeat_factory

    def create_session(self, profile_id, access_token, job_description, idempotency_key):
        if not isinstance(job_description, str) or not job_description.strip() or len(job_description) > self.settings.max_jd_chars:
            raise ServiceError("Invalid or oversized job description")
        return self.sessions.create_with_job(profile_id, access_token, job_description, idempotency_key, self.advisor.create_snapshot)

    def get_session(self, session_id, access_token):
        stored = self.sessions.get(session_id, access_token)
        job, snapshot = stored["job"], stored["snapshot"]
        return {"session_id": session_id, "profile_id": stored["profile_id"],
                "status": "ready" if job["status"] == "succeeded" else job["status"],
                "academic_state": "ready" if snapshot["review"] is not None else "pending_review",
                "initial_review": snapshot["review"], "review_job": job, "fingerprints": snapshot["fingerprints"],
                "revision": stored["revision"], "turn_count": len(snapshot["messages"]) // 2,
                "created_at": stored["created_at"], "updated_at": stored["updated_at"]}

    def send_message(self, session_id, access_token, message, idempotency_key):
        if not isinstance(message, str) or not message.strip() or len(message) > self.settings.max_message_chars:
            raise ServiceError("Invalid or oversized chat message")
        lease, cached = self.sessions.claim_chat(session_id, access_token, message, idempotency_key)
        if lease is None:
            return cached
        phase = "prepare"
        try:
            with self.heartbeat_factory(self.sessions, lease, self.settings.heartbeat_interval) as heartbeat:
                snapshot = self.sessions.load_owned(lease)
                # Stage settings are resolved before dispatch, retaining existing precedence.
                chat_settings = self.advisor.prepare_chat_settings()
                heartbeat.check()
                self.sessions.mark_dispatched(lease)
                phase = "inference"
                updated, response = self.advisor.chat_snapshot(snapshot, message, settings=chat_settings)
                phase = "commit"
                heartbeat.check()
                return self.sessions.commit_chat(lease, updated, response)
        except BaseException as error:
            status, code, safe_message = classify_failure(error, phase)
            try:
                self.sessions.finish_failure(lease, status=status, code=code, message=safe_message)
            except Exception:
                pass  # Expired-lease recovery remains authoritative if the DB is unavailable.
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            if phase == "prepare" and isinstance(error, ServiceError):
                raise
            if phase == "prepare" and not isinstance(error, ServiceError):
                raise BackendUnavailableError("Chat settings or credentials are unavailable") from error
            if status == "interrupted":
                from .errors import OperationInterruptedError
                raise OperationInterruptedError(safe_message) from error
            raise StoredOperationFailedError(safe_message) from error

    def get_history(self, session_id, access_token):
        return {"session_id": session_id, "turns": self.sessions.history(session_id, access_token)}
