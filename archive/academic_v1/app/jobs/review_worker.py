from __future__ import annotations

import logging
from uuid import uuid4

from .failures import classify_failure
from .heartbeat import OperationHeartbeat
from app.services.errors import StorageIntegrityError

LOGGER = logging.getLogger("skillbridge.review_worker")


class ReviewWorker:
    def __init__(self, jobs, advisor, *, heartbeat_interval=10, heartbeat_factory=OperationHeartbeat,
                 review_settings_overrides=None):
        self.jobs, self.sessions, self.advisor = jobs, jobs.sessions, advisor
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_factory = heartbeat_factory
        self.review_settings_overrides = dict(review_settings_overrides or {})
        self.worker_id = uuid4().hex

    def run_once(self):
        self.jobs.worker_heartbeat(self.worker_id)
        lease = self.jobs.claim_next()
        if lease is None:
            return None
        phase = "prepare"
        try:
            with self.heartbeat_factory(self.sessions, lease, self.heartbeat_interval) as heartbeat:
                snapshot = self.sessions.load_owned(lease)
                if snapshot["review"] is not None or snapshot["messages"]:
                    raise StorageIntegrityError("Initial Review job requires an unchanged pending session")
                settings = self.advisor.prepare_review_settings(**self.review_settings_overrides)
                heartbeat.check()
                self.sessions.mark_dispatched(lease)
                phase = "inference"
                updated, _ = self.advisor.review_snapshot(snapshot, settings=settings)
                phase = "commit"
                heartbeat.check()
                self.jobs.commit_review(lease, updated)
        except BaseException as error:
            status, code, message = classify_failure(error, phase)
            try:
                self.sessions.finish_failure(lease, status=status, code=code, message=message)
            except Exception:
                LOGGER.error("job=%s code=state_write_failed", lease.operation_id)
            LOGGER.warning("job=%s code=%s", lease.operation_id, code)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
        return lease.operation_id

    def close(self):
        self.jobs.worker_heartbeat(self.worker_id, state="stopped")
