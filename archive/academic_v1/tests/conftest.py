"""Shared fixtures for offline service contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.services import CourseService
from scripts import academic_review


@pytest.fixture
def service_offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Service verification may not make real HTTP requests")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(academic_review, "load_dotenv", lambda *a, **k: None)
    for key in list(os.environ):
        if key == "MODEL" or key.startswith("OPENAI_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def service_catalog(tmp_path):
    courses = tmp_path / "courses"
    subjects = tmp_path / "subjects"
    subjects.mkdir()
    for code, source in [("TEST101", "3173"), ("OTHER201", "3173"), ("FOREIGN301", "9999")]:
        folder = courses / code
        folder.mkdir(parents=True)
        metadata = {"subject_code": code, "course_name_english": "SQL Course",
                    "syllabus_name": "SQL", "description": "Relational databases and SQL", "tools": "",
                    "source_note": "Keep this extra raw field"}
        clos = [{"clo": "CLO2", "description": "Understand joins"}, {"clo": "CLO1", "description": "Use SQL"}]
        assessments = [{"category": "Quiz 1", "part": "1", "weight": "25%", "clo": "CLO1"},
                       {"category": "Final exam", "part": "1", "weight": "75%", "clo": "CLO1, CLO2"}]
        for filename, raw in [("metadata.json", metadata), ("clos.json", clos), ("assessments.json", assessments)]:
            (folder / filename).write_text(json.dumps(raw), encoding="utf-8")
        processed = {"record_type": "normal_subject", "subject": {"code": code,
                     "name": {"en": "SQL", "vi": "Cơ sở dữ liệu", "full": "SQL_Cơ sở dữ liệu"},
                     "semester": 3, "credits": 3, "prerequisite": ""},
                     "source": {"curriculum_url": f"https://example.test/CurriculumDetails?curid={source}"}}
        (subjects / f"{code}.json").write_text(json.dumps(processed), encoding="utf-8")
    combo_path = tmp_path / "combos.json"
    combo_path.write_text("[]", encoding="utf-8")
    return CourseService(curriculum_mapping={"configured": "3173", "other": "9999"},
                         default_curriculum_code="configured", courses_dir=courses,
                         subjects_dir=subjects, combo_map_path=combo_path)


@pytest.fixture
def service_profile(service_catalog):
    from app.services import ProfileService
    return ProfileService(service_catalog).build_profile(["TEST101"], {"TEST101": {"Quiz 1": 10, "Final exam": 8}})


@pytest.fixture
def service_review():
    return {"review_type": "academic_knowledge_review", "overview": "Nền tảng học thuật SQL.",
            "requirement_reviews": [{"jd_requirement": "SQL", "coverage": "covered",
                                     "comment": "TEST101/CLO1 có nội dung SQL.",
                                     "evidence": [{"course_code": "TEST101", "clo": "CLO1"}]}],
            "conclusion": "Hồ sơ chưa xác nhận kinh nghiệm nghề nghiệp."}


@pytest.fixture
def service_reply():
    return {"reply": "TEST101/CLO1 bao gồm SQL.", "evidence": [{"course_code": "TEST101", "clo": "CLO1"}]}


@pytest.fixture
def sdk_client():
    def factory(raw, *, status="completed"):
        client = Mock()
        client.responses.input_tokens.count.return_value = SimpleNamespace(input_tokens=100)
        client.responses.parse.return_value = SimpleNamespace(status=status, output=[], output_parsed=raw)
        return client
    return factory


@pytest.fixture
def actual_course_service():
    # Test-owned alias; this makes no claim about the human curriculum name.
    return CourseService(curriculum_mapping={"fixture-source-3173": "3173"},
                         default_curriculum_code="fixture-source-3173")


class ManualClock:
    def __init__(self):
        self.value = 1791936000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


@pytest.fixture
def api_backend(tmp_path, service_catalog, sdk_client, service_review, service_reply, service_offline):
    from app.config import BackendSettings
    from app.main import create_app
    from app.services import AdvisorService
    from app.storage.database import Database
    from fastapi.testclient import TestClient
    settings = BackendSettings(database_path=tmp_path / "api.sqlite3",
        curriculum_mapping={"configured": "3173", "other": "9999"}, default_curriculum="configured",
        lease_seconds=30, heartbeat_interval=5, max_body_bytes=4096,
        cors_origins=("http://localhost:5173",))
    clock = ManualClock()
    database = Database(settings.database_path, clock=clock, lease_seconds=settings.lease_seconds)
    review_client, chat_client = sdk_client(service_review), sdk_client(service_reply)
    advisor = AdvisorService(review_settings=academic_review.ReviewSettings(api_key="offline-worker", stage="review"),
        chat_settings=academic_review.ReviewSettings(api_key="offline-chat", stage="chat"),
        review_client=review_client, chat_client=chat_client,
        max_turns=settings.max_turns, max_message_chars=settings.max_message_chars)
    app = create_app(settings, advisor_service=advisor, course_service=service_catalog, database=database)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(app=app, client=client, backend=app.state.backend, settings=settings,
            database=database, clock=clock, advisor=advisor, catalog=service_catalog,
            review_client=review_client, chat_client=chat_client)


@pytest.fixture
def stored_profile(api_backend):
    body = {"curriculum_code": "configured", "selected_courses": ["TEST101"],
            "grades": [{"course_code": "TEST101", "category": "Quiz 1", "grade": 10},
                       {"course_code": "TEST101", "category": "Final exam", "grade": 8}]}
    response = api_backend.client.post("/api/v1/profiles", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def queued_session(api_backend, stored_profile):
    headers = {"Authorization": "Bearer " + stored_profile["access_token"], "Idempotency-Key": "create-session"}
    response = api_backend.client.post("/api/v1/advisor/sessions", headers=headers,
        json={"profile_id": stored_profile["profile_id"], "job_description": "SQL internship"})
    assert response.status_code == 202, response.text
    return {**response.json(), "headers": headers, "access_token": stored_profile["access_token"]}


@pytest.fixture
def ready_session(api_backend, queued_session):
    from app.jobs.review_worker import ReviewWorker
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor, heartbeat_interval=5)
    assert worker.run_once() == queued_session["review_job"]["job_id"]
    worker.close()
    assert api_backend.backend.jobs.get(queued_session["review_job"]["job_id"])["status"] == "succeeded"
    return queued_session
