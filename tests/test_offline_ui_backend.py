from fastapi.testclient import TestClient
from app.jobs.review_worker import ReviewWorker
from app.main import create_app
from examples.offline_demo import demo_advisor, demo_settings, marked_directory
import pytest


@pytest.mark.parametrize("target", ["cwa", "jd"])
@pytest.mark.parametrize("course_code", ["ADY201m", "MLN111"])
def test_demo_uses_real_catalog_and_disposable_storage_without_sdk(tmp_path, service_offline, monkeypatch, target, course_code):
    from app.llm import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("Offline demo constructed SDK"))
    advisor = demo_advisor(review_delay=0)
    settings = demo_settings(tmp_path)
    with TestClient(create_app(settings, advisor_service=advisor)) as client:
        catalog = client.get("/api/v1/courses").json()
        assert len(catalog["courses"]) == 41
        detail = client.get("/api/v1/courses/ADY201m").json()
        clo_set = client.post("/api/v1/selections", json={"curriculum_code": "source-3173", "selected_courses": [course_code]}).json()
        headers = {"Authorization": "Bearer " + clo_set["access_token"], "Idempotency-Key": "offline-session"}
        session = client.post("/api/v1/advisor/sessions", headers=headers,
            json={"selection_id": clo_set["selection_id"], **({"career_profile_id": "data-analyst"} if target == "cwa" else {"job_description": "Python"})}).json()
        path = "/api/v1/advisor/sessions/" + session["session_id"]
        worker = ReviewWorker(client.app.state.backend.jobs, advisor)
        try:
            worker.run_once()
        finally:
            worker.close()
        result = client.get(path, headers=headers).json()
        assert result["status"] == "ready" and "DEMO OFFLINE" in result["comparison"]["overview"]
        for i in range(2):
            headers["Idempotency-Key"] = f"offline-chat-{i}"
            body = {"message": f"Câu hỏi {i}"}
            first = client.post(path + "/messages", headers=headers, json=body)
            assert first.status_code == 200
            assert client.post(path + "/messages", headers=headers, json=body).json() == first.json()
        assert len(client.get(path + "/messages", headers=headers).json()["turns"]) == 2


def test_internal_demo_roles_refuse_unmarked_database_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLBRIDGE_OFFLINE_DEMO_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        marked_directory()
