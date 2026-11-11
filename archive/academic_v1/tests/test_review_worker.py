import copy
import sqlite3

import pytest

from app.jobs.review_worker import ReviewWorker
from scripts.academic_review import ReviewError


@pytest.mark.parametrize("failure,expected", [("prepare", "failed"), ("inference", "interrupted"),
                                              ("incomplete", "failed"), ("evidence", "failed"), ("commit", "interrupted")])
def test_worker_failures_preserve_complete_snapshot_and_never_auto_retry(api_backend, queued_session, failure, expected, monkeypatch, caplog):
    if failure == "prepare":
        monkeypatch.setattr(api_backend.advisor, "prepare_review_settings", lambda: (_ for _ in ()).throw(ReviewError("sk-secret")))
    elif failure == "inference":
        api_backend.review_client.responses.parse.side_effect = RuntimeError("sk-secret")
    elif failure == "incomplete":
        api_backend.review_client.responses.parse.return_value.status = "incomplete"
    elif failure == "evidence":
        raw = copy.deepcopy(api_backend.review_client.responses.parse.return_value.output_parsed)
        raw["requirement_reviews"][0]["evidence"][0]["clo"] = "CLO999"
        api_backend.review_client.responses.parse.return_value.output_parsed = raw
    elif failure == "commit":
        with api_backend.database.transaction(write=True) as connection:
            connection.execute("""CREATE TRIGGER fail_commit BEFORE UPDATE OF status ON jobs
                WHEN NEW.status='succeeded' BEGIN SELECT RAISE(ABORT,'test commit failure'); END""")
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor, heartbeat_interval=5)
    assert worker.run_once() == queued_session["review_job"]["job_id"]
    job = api_backend.backend.jobs.get(queued_session["review_job"]["job_id"])
    assert job["status"] == expected and job["attempt_count"] == 1
    state = api_backend.backend.sessions.get(queued_session["session_id"], queued_session["access_token"])
    assert state["snapshot"]["review"] is None and state["snapshot"]["messages"] == [] and state["revision"] == 0
    assert worker.run_once() is None
    assert api_backend.review_client.responses.parse.call_count == (0 if failure == "prepare" else 1)
    assert "sk-secret" not in caplog.text and "sk-secret" not in str(job)
    assert (job["dispatched_at"] is None) == (failure == "prepare")
    worker.close()


def test_crash_after_successful_commit_keeps_success(api_backend, queued_session, monkeypatch):
    original = api_backend.backend.jobs.commit_review
    def after_commit(*args):
        original(*args)
        raise RuntimeError("Response observation lost")
    monkeypatch.setattr(api_backend.backend.jobs, "commit_review", after_commit)
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    worker.run_once()
    assert api_backend.backend.jobs.get(queued_session["review_job"]["job_id"])["status"] == "succeeded"
    assert worker.run_once() is None and api_backend.review_client.responses.parse.call_count == 1
    worker.close()


def test_worker_shutdown_marks_uncertain_and_releases_owner(api_backend, queued_session):
    api_backend.review_client.responses.parse.side_effect = KeyboardInterrupt()
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    with pytest.raises(KeyboardInterrupt): worker.run_once()
    assert api_backend.backend.jobs.get(queued_session["review_job"]["job_id"])["status"] == "interrupted"
    with api_backend.database.transaction() as connection:
        assert connection.execute("SELECT lease_token FROM sessions").fetchone()[0] is None
    worker.close()


def test_failed_heartbeat_prevents_publication_even_before_expiry(api_backend, queued_session, monkeypatch):
    from app.jobs.heartbeat import OperationHeartbeat
    heartbeats = []
    class CapturedHeartbeat(OperationHeartbeat):
        def __enter__(self):
            heartbeats.append(self)
            return super().__enter__()
    parsed = api_backend.review_client.responses.parse.return_value
    def generation(**kwargs):
        def fail(*args):
            raise sqlite3.OperationalError("Heartbeat failed")
        with monkeypatch.context() as patch:
            patch.setattr(api_backend.backend.sessions, "renew", fail)
            assert not heartbeats[0].pulse()
        return parsed
    api_backend.review_client.responses.parse.side_effect = generation
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor, heartbeat_factory=CapturedHeartbeat)
    worker.run_once()
    stored = api_backend.backend.sessions.get(queued_session["session_id"], queued_session["access_token"])
    assert stored["job"]["status"] == "interrupted" and stored["snapshot"]["review"] is None
    assert api_backend.review_client.responses.parse.call_count == 1
    worker.close()
