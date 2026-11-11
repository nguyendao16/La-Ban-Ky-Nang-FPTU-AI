from __future__ import annotations

import multiprocessing
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.jobs.heartbeat import OperationHeartbeat
from app.jobs.review_worker import ReviewWorker


def process_worker(database_path, raw_review, barrier, output):
    """Spawned process uses a real independent connection and a fake engine."""
    from app.services import AdvisorService
    from app.storage.database import Database
    from app.storage.job_repository import JobRepository
    from app.storage.session_repository import SessionRepository
    from scripts.academic_review import ReviewSettings
    def generation(profile, jd, settings, *, client=None):
        output.put(("generation", 1))
        return raw_review
    db = Database(database_path, lease_seconds=60)
    db.initialize()
    advisor = AdvisorService(review_engine=generation, review_settings=ReviewSettings(api_key="offline-process", stage="review"))
    sessions = SessionRepository(db, advisor.validate_snapshot)
    worker = ReviewWorker(JobRepository(db, sessions), advisor)
    barrier.wait(timeout=20)
    result = worker.run_once()
    output.put(("claim", bool(result)))
    worker.close()


def test_two_worker_processes_claim_one_job_and_generate_once(api_backend, queued_session, service_review):
    context = multiprocessing.get_context("spawn")
    barrier, output = context.Barrier(2), context.Queue()
    processes = [context.Process(target=process_worker, args=(str(api_backend.settings.database_path), service_review, barrier, output)) for _ in range(2)]
    for process in processes: process.start()
    try:
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        events = [output.get(timeout=5) for _ in range(3)]
        assert sum(value for kind, value in events if kind == "generation") == 1
        assert sum(value for kind, value in events if kind == "claim") == 1
        assert api_backend.backend.jobs.get(queued_session["review_job"]["job_id"])["status"] == "succeeded"
        assert api_backend.backend.sessions.get(queued_session["session_id"], queued_session["access_token"])["revision"] == 1
    finally:
        for process in processes:
            if process.is_alive(): process.terminate()
            process.join(timeout=5)
        output.close()


def test_polling_does_not_wait_for_review_and_heartbeat_extends_lease(api_backend, queued_session):
    started, release = threading.Event(), threading.Event()
    heartbeats = []
    parsed = api_backend.review_client.responses.parse.return_value
    def generation(**kwargs):
        started.set()
        assert release.wait(10)
        return parsed
    class ControlledHeartbeat(OperationHeartbeat):
        def __enter__(self):
            heartbeats.append(self)
            return super().__enter__()
    api_backend.review_client.responses.parse.side_effect = generation
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor, heartbeat_interval=5, heartbeat_factory=ControlledHeartbeat)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(worker.run_once)
        try:
            assert started.wait(5)
            begin = time.monotonic()
            response = api_backend.client.get("/api/v1/advisor/sessions/" + queued_session["session_id"], headers=queued_session["headers"])
            assert time.monotonic() - begin < 1
            assert response.status_code == 200 and response.json()["status"] == "processing"
            assert response.json()["initial_review"] is None
            api_backend.clock.advance(20)
            assert heartbeats[0].pulse()
            api_backend.clock.advance(20)
            assert api_backend.backend.sessions.recover_expired() == 0
        finally:
            release.set()
        assert running.result(timeout=5) == queued_session["review_job"]["job_id"]
    assert api_backend.client.get("/api/v1/advisor/sessions/" + queued_session["session_id"], headers=queued_session["headers"]).json()["status"] == "ready"
    worker.close()


def test_same_session_concurrent_chat_is_busy_and_running_key_is_not_reexecuted(api_backend, ready_session):
    started, release = threading.Event(), threading.Event()
    parsed = api_backend.chat_client.responses.parse.return_value
    def generation(**kwargs):
        started.set()
        assert release.wait(10)
        return parsed
    api_backend.chat_client.responses.parse.side_effect = generation
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    headers = {**ready_session["headers"], "Idempotency-Key": "chat-A"}
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(api_backend.client.post, path, headers=headers, json={"message": "A"})
        try:
            assert started.wait(5)
            same = api_backend.client.post(path, headers=headers, json={"message": "A"})
            assert same.status_code == 409 and same.json()["error"]["code"] == "operation_running"
            other = api_backend.client.post(path, headers={**headers, "Idempotency-Key": "chat-B"}, json={"message": "B"})
            assert other.status_code == 409 and other.json()["error"]["code"] == "session_busy"
            assert api_backend.client.get(path, headers=headers).json()["turns"] == []
        finally:
            release.set()
        result = first.result(timeout=5)
    assert result.status_code == 200
    repeat = api_backend.client.post(path, headers=headers, json={"message": "A"})
    assert repeat.json() == result.json()
    assert api_backend.chat_client.responses.parse.call_count == 1
    assert len(api_backend.client.get(path, headers=headers).json()["turns"]) == 1


def test_different_sessions_can_chat_while_another_is_blocked(api_backend, ready_session, stored_profile):
    created = api_backend.client.post("/api/v1/advisor/sessions", headers={**ready_session["headers"], "Idempotency-Key": "second-session"},
        json={"profile_id": stored_profile["profile_id"], "job_description": "Independent SQL JD"}).json()
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    worker.run_once()
    worker.close()
    started, release = threading.Event(), threading.Event()
    parsed = api_backend.chat_client.responses.parse.return_value
    def generation(**kwargs):
        if kwargs["input"][-1]["content"] == "A":
            started.set()
            assert release.wait(10)
        return parsed
    api_backend.chat_client.responses.parse.side_effect = generation
    headers = {**ready_session["headers"], "Idempotency-Key": "same-key-independent-scopes"}
    a_path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    b_path = "/api/v1/advisor/sessions/" + created["session_id"] + "/messages"
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(api_backend.client.post, a_path, headers=headers, json={"message": "A"})
        try:
            assert started.wait(5)
            b = api_backend.client.post(b_path, headers=headers, json={"message": "B"})
            assert b.status_code == 200
        finally:
            release.set()
        assert running.result(timeout=5).status_code == 200
    assert api_backend.client.get(a_path, headers=headers).json()["turns"][0]["user_message"] == "A"
    assert api_backend.client.get(b_path, headers=headers).json()["turns"][0]["user_message"] == "B"


def test_lost_owner_cannot_publish_after_model_returns(api_backend, queued_session):
    started, release = threading.Event(), threading.Event()
    parsed = api_backend.review_client.responses.parse.return_value
    def generation(**kwargs):
        started.set()
        assert release.wait(10)
        return parsed
    api_backend.review_client.responses.parse.side_effect = generation
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor, heartbeat_interval=5)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(worker.run_once)
        try:
            assert started.wait(5)
            api_backend.clock.advance(31)
            assert api_backend.backend.sessions.recover_expired() == 1
        finally:
            release.set()
        running.result(timeout=5)
    record = api_backend.backend.sessions.get(queued_session["session_id"], queued_session["access_token"])
    assert record["snapshot"]["review"] is None and record["job"]["status"] == "interrupted"
    assert worker.run_once() is None
    worker.close()


def test_separate_api_instance_cannot_claim_an_owned_chat(api_backend, ready_session, sdk_client, service_reply):
    from app.main import create_app
    from app.services import AdvisorService
    from fastapi.testclient import TestClient
    from scripts.academic_review import ReviewSettings
    started, release = threading.Event(), threading.Event()
    parsed = api_backend.chat_client.responses.parse.return_value
    def generation(**kwargs):
        started.set()
        assert release.wait(10)
        return parsed
    api_backend.chat_client.responses.parse.side_effect = generation
    other_client = sdk_client(service_reply)
    other_advisor = AdvisorService(chat_settings=ReviewSettings(api_key="offline-other-api", stage="chat"), chat_client=other_client)
    other_app = create_app(api_backend.settings, advisor_service=other_advisor,
        course_service=api_backend.catalog, database=api_backend.database)
    headers = {**ready_session["headers"], "Idempotency-Key": "cross-app"}
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    with TestClient(other_app) as other, ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(api_backend.client.post, path, headers=headers, json={"message": "A"})
        try:
            assert started.wait(5)
            rejected = other.post(path, headers={**headers, "Idempotency-Key": "cross-app-B"}, json={"message": "B"})
            assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "session_busy"
            other_client.responses.parse.assert_not_called()
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
        assert other.post(path, headers=headers, json={"message": "A"}).status_code == 200
        other_client.responses.parse.assert_not_called()
