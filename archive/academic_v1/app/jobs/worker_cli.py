"""Independent local worker. Only a claimed generation requires OpenAI settings."""

from __future__ import annotations

import argparse
import json
import signal
import sqlite3
import threading

from app.config import BackendSettings
from app.services.advisor_service import AdvisorService
from app.services.errors import ServiceError
from app.storage.database import Database
from app.storage.job_repository import JobRepository
from app.storage.session_repository import SessionRepository

from .review_worker import ReviewWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Claim at most one queued job; requires credentials only if one is claimed.")
    parser.add_argument("--recover-only", action="store_true", help="Mark expired operations interrupted, without any inference.")
    parser.add_argument("--retry-job", help="Explicitly requeue one failed/interrupted Review; does not run inference.")
    parser.add_argument("--acknowledge-possible-duplicate", action="store_true", help="Required to retry a previously dispatched operation.")
    parser.add_argument("--review-timeout", type=float, help="Explicit existing ReviewSettings request_timeout override, e.g. 360.")
    args = parser.parse_args(argv)
    if sum([args.once, args.recover_only, args.retry_job is not None]) > 1:
        parser.error("Choose --once, --recover-only, or --retry-job")
    settings = BackendSettings.from_env()
    database = Database(settings.database_path, lease_seconds=settings.lease_seconds)
    database.initialize()
    advisor = AdvisorService(max_turns=settings.max_turns, max_message_chars=settings.max_message_chars)
    sessions = SessionRepository(database, advisor.validate_snapshot)
    jobs = JobRepository(database, sessions)
    if args.recover_only:
        print(json.dumps({"interrupted_operations": sessions.recover_expired()}))
        return 0
    if args.retry_job:
        print(json.dumps(jobs.retry(args.retry_job, acknowledge_possible_duplicate=args.acknowledge_possible_duplicate)))
        return 0
    overrides = {} if args.review_timeout is None else {"request_timeout": args.review_timeout}
    worker = ReviewWorker(jobs, advisor, heartbeat_interval=settings.heartbeat_interval, review_settings_overrides=overrides)
    stop = threading.Event()
    def interrupted(signum, frame):
        stop.set()
        raise KeyboardInterrupt
    old_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        while not stop.is_set():
            job_id = worker.run_once()
            if args.once:
                result = {"job_id": job_id, "status": jobs.get(job_id)["status"] if job_id else "no_queued_job"}
                print(json.dumps(result))
                return 0 if job_id is None or result["status"] == "succeeded" else 1
            stop.wait(settings.worker_poll_interval)
    except KeyboardInterrupt:
        return 0
    finally:
        signal.signal(signal.SIGTERM, old_term)
        worker.close()
        advisor.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, sqlite3.Error) as error:
        print(json.dumps({"error": {"code": getattr(error, "code", "configuration_or_storage_error"),
                                   "message": "Worker operation was not performed; check local configuration and options"}}))
        raise SystemExit(1)
