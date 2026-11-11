"""Shared fixtures for offline service contracts."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.services import CourseService
from app import llm


@pytest.fixture
def service_offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Service verification may not make real HTTP requests")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)
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
def service_clo_set(service_catalog):
    from app.services import CLOSetService
    return CLOSetService(service_catalog).build_clo_set(["TEST101"])


@pytest.fixture
def service_review(career_radar):
    return {"radar": copy.deepcopy(career_radar), "comparison_type": "clo_jd_comparison", "overview": "Đối chiếu nội dung SQL.",
            "requirement_reviews": [{"jd_requirement": "SQL", "coverage": "covered",
                                     "comment": "TEST101/CLO1 có nội dung SQL.",
                                     "evidence": [{"course_code": "TEST101", "clo": "CLO1"}]}],
            "conclusion": "CLO hiện có chưa bao phủ kinh nghiệm nghề nghiệp."}


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
def target_domain(request):
    return getattr(request, 'param', 'jd')


@pytest.fixture
def career_radar():
    return {'overall_score': 3.7, 'overall_comment': 'Nhận định tổng thể về nội dung học tập.',
        'axes': [{'name': name, 'description': f'Phạm vi nội dung {name} của nhóm nghề.',
                  'score': score, 'comment': 'Nội dung có liên hệ nền tảng, chưa chứng minh thực hành.',
                  'evidence': [{'course_code': 'TEST101', 'clo': 'CLO1'}] if score else []}
                 for name, score in [('Dữ liệu', 4.0), ('Phân tích', 2.5), ('Mô hình', 1.0), ('Triển khai', 0.0), ('Giao tiếp', 1.5)]]}


@pytest.fixture
def career_review(career_radar):
    from app.services import CareerCatalog
    career_radar = copy.deepcopy(career_radar)
    for axis, definition in zip(career_radar['axes'], CareerCatalog().get('data-analyst')['target']['axes'], strict=True):
        axis.update(definition)
    return {'comparison_type': 'career_comparison', 'overview': 'Góc nhìn nghề nghiệp theo nội dung học tập.',
        'related_content': [{'title': 'Nền tảng dữ liệu', 'comment': 'Nội dung môn hỗ trợ làm việc với dữ liệu.',
                             'evidence': [{'course_code': 'TEST101', 'clo': 'CLO1'}]}],
        'gaps': [{'title': 'Vận hành hệ thống', 'comment': 'Nội dung hiện có chưa thể hiện khía cạnh vận hành.', 'evidence': []}],
        'conclusion': 'Các liên hệ này không chứng nhận năng lực cá nhân.', 'radar': career_radar}


@pytest.fixture
def career_review_for(career_review):
    from app.services import CareerCatalog
    def for_target(profile_id):
        raw = copy.deepcopy(career_review)
        for axis, definition in zip(raw['radar']['axes'], CareerCatalog().get(profile_id)['target']['axes'], strict=True):
            axis.update(definition)
        return raw
    return for_target


@pytest.fixture
def api_backend(tmp_path, service_catalog, sdk_client, service_review, service_reply, service_offline, target_domain, career_review):
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
    review_client, chat_client = sdk_client(career_review if target_domain == "cwa" else service_review), sdk_client(service_reply)
    advisor = AdvisorService(review_settings=llm.LLMSettings(api_key="offline-worker", stage="review"),
        chat_settings=llm.LLMSettings(api_key="offline-chat", stage="chat"),
        review_client=review_client, chat_client=chat_client,
        max_turns=settings.max_turns, max_message_chars=settings.max_message_chars)
    from app.services.semester_map import SemesterMap
    raw = {f'Semester {n}': (['TEST101', 'OTHER201'] if n == 1 else []) for n in range(1, 5)}
    raw.update({t: {f'Semester {n}': [] for n in range(5, 10)} for t in SemesterMap.TRACKS})
    app = create_app(settings, advisor_service=advisor, course_service=service_catalog, database=database, semester_map=SemesterMap(raw))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(app=app, client=client, backend=app.state.backend, settings=settings,
            database=database, clock=clock, advisor=advisor, catalog=service_catalog,
            review_client=review_client, chat_client=chat_client, domain=target_domain)


@pytest.fixture
def stored_clo_set(api_backend):
    body = {"curriculum_code": "configured", "selected_courses": ["TEST101"]}
    response = api_backend.client.post("/api/v1/selections", json=body)
    assert response.status_code == 201, response.text
    value = response.json()
    private = api_backend.backend.clo_sets.get(value['selection_id'], value['access_token'])
    return {**private, **value}


@pytest.fixture
def queued_session(api_backend, stored_clo_set):
    headers = {"Authorization": "Bearer " + stored_clo_set["access_token"], "Idempotency-Key": "create-session"}
    response = api_backend.client.post("/api/v1/advisor/sessions", headers=headers,
        json={"selection_id": stored_clo_set["clo_set_id"], **({"career_profile_id": "data-analyst"} if api_backend.domain == "cwa" else {"job_description": "SQL internship"})})
    assert response.status_code == 202, response.text
    return {**response.json(), "headers": headers, "access_token": stored_clo_set["access_token"]}


@pytest.fixture
def ready_session(api_backend, queued_session):
    from app.jobs.review_worker import ReviewWorker
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor, heartbeat_interval=5)
    assert worker.run_once() == queued_session["comparison_job"]["job_id"]
    worker.close()
    assert api_backend.backend.jobs.get(queued_session["comparison_job"]["job_id"])["status"] == "succeeded"
    return queued_session
