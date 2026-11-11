"""SQLite application adapter around the existing snapshot-based service."""

from app.jobs.failures import classify_failure
from app.jobs.heartbeat import OperationHeartbeat
from app.services.errors import BackendUnavailableError, ServiceError, StoredOperationFailedError


class PersistentAdvisor:
    def __init__(self, advisor, sessions, *, settings, heartbeat_factory=OperationHeartbeat, career_catalog=None, jobs=None):
        self.advisor, self.sessions, self.settings = advisor, sessions, settings
        self.heartbeat_factory = heartbeat_factory
        from .career_catalog import CareerCatalog
        self.careers = career_catalog or CareerCatalog()
        self.jobs = jobs

    def create_session(self, clo_set_id, access_token, job_description, idempotency_key):
        if not isinstance(job_description, str) or not job_description.strip() or len(job_description) > self.settings.max_jd_chars:
            raise ServiceError("Invalid or oversized job description")
        return self.sessions.create_with_job(clo_set_id, access_token, job_description, idempotency_key, self.advisor.create_snapshot)

    def create_career_session(self, selection_id, access_token, profile_id, idempotency_key):
        def snapshot_factory(source, target):
            return self.advisor.create_career_snapshot(source, self.careers.get(target['career_profile_id']))
        return self.sessions.create_with_job(selection_id, access_token, {'career_profile_id': profile_id},
                                             idempotency_key, snapshot_factory)

    def get_session(self, session_id, access_token):
        stored = self.sessions.get(session_id, access_token)
        job, snapshot = stored["job"], stored["snapshot"]
        target = ({'type': 'cwa', 'career_profile': snapshot['career_profile']} if 'career_profile' in snapshot
                  else {'type': 'jd', 'job_description': snapshot['job_description']})
        return {"session_id": session_id, "clo_set_id": stored["clo_set_id"], 'target': target,
                "status": "ready" if job["status"] == "succeeded" else job["status"],
                "comparison": snapshot["comparison"], "comparison_job": job, "fingerprints": snapshot["fingerprints"],
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
                recommendations = None
                if self.jobs is not None:
                    saved = self.jobs.get_recommendations(session_id, access_token)
                    if saved['result'] is not None:
                        recommendations = {**saved['result'], 'gaps': saved['gaps']}
                # Stage settings are resolved before dispatch, retaining existing precedence.
                chat_settings = self.advisor.prepare_chat_settings()
                heartbeat.check()
                self.sessions.mark_dispatched(lease)
                phase = "inference"
                if recommendations is None:
                    updated, response = self.advisor.chat_snapshot(snapshot, message, settings=chat_settings)
                else:
                    updated, response = self.advisor.chat_snapshot(snapshot, message, settings=chat_settings, recommendations=recommendations)
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
