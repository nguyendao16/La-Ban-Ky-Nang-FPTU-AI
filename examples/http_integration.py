"""Complete HTTP flow with a temporary SQLite database and mocked inference.

No OpenAI client is constructed, no .env is loaded by model configuration, and
no global source files are written. Capability tokens are never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.config import BackendSettings
from app.jobs.review_worker import ReviewWorker
from app.main import create_app
from app.services import AdvisorService
from examples.services_integration import mock_client, mock_career_radar, mock_jd_radar
from app.llm import LLMSettings


def run_demo(*, curriculum_code: str, curriculum_source_id: str, career_profile_id: str | None = None):
    evidence = [{"course_code": "ADY201m", "clo": "CLO1"}]
    raw_review = {"radar": mock_jd_radar(evidence), "comparison_type": "clo_jd_comparison", "overview": "MOCK: CLO–JD comparison.",
        "requirement_reviews": [{"jd_requirement": "SQL", "coverage": "related",
                                 "comment": "MOCK: kiểm thử orchestration, không đánh giá LLM.", "evidence": evidence}],
        "conclusion": "MOCK: so sánh nội dung CLO và JD."}
    if career_profile_id is not None:
        from app.services.career_catalog import CareerCatalog
        profile = CareerCatalog().get(career_profile_id)
        raw_review = {"comparison_type": "career_comparison", "overview": f"MOCK: đối chiếu với {profile['title']}.",
            "related_content": [{"title": "Nền tảng học tập", "comment": "MOCK: phân tích liên hệ nội dung học phần với nhóm nghề.", "evidence": evidence}],
            "gaps": [{"title": "Nội dung cần tìm hiểu", "comment": "MOCK: một số khía cạnh công việc chưa thể hiện trong nội dung học tập.", "evidence": []}],
            "conclusion": "MOCK: không đánh giá năng lực cá nhân.", "radar": mock_career_radar(profile, evidence)}
    review_client = mock_client(raw_review)
    chat_client = mock_client({"reply": "MOCK: giải thích kết quả đối chiếu của phiên.", "evidence": evidence})
    advisor = AdvisorService(review_settings=LLMSettings(api_key="offline-http", stage="review"),
        chat_settings=LLMSettings(api_key="offline-http", stage="chat"),
        review_client=review_client, chat_client=chat_client)
    with tempfile.TemporaryDirectory(prefix="skillbridge-http-demo-") as directory:
        settings = BackendSettings(database_path=Path(directory) / "demo.sqlite3",
            curriculum_mapping={curriculum_code: curriculum_source_id}, default_curriculum=curriculum_code)
        application = create_app(settings, advisor_service=advisor)
        with TestClient(application) as client:
            catalog = client.get("/api/v1/courses")
            assert catalog.status_code == 200
            detail = client.get("/api/v1/courses/ADY201m")
            assert detail.status_code == 200
            assert "clos" not in detail.json()
            created_clo_set = client.post("/api/v1/selections", json={"curriculum_code": curriculum_code,
                "selected_courses": ["ADY201m"]})
            assert created_clo_set.status_code == 201
            clo_set = created_clo_set.json()
            headers = {"Authorization": "Bearer " + clo_set["access_token"], "Idempotency-Key": "demo-create"}
            fetched = client.get("/api/v1/selections/" + clo_set["selection_id"], headers=headers)
            assert fetched.status_code == 200 and fetched.json()["selected_courses"] == clo_set["selected_courses"]
            target = {"career_profile_id": career_profile_id} if career_profile_id is not None else {"job_description": (ROOT / "data/sample_jd.txt").read_text(encoding="utf-8")}
            body = {"selection_id": clo_set["selection_id"], **target}
            created_session = client.post("/api/v1/advisor/sessions", headers=headers, json=body)
            assert created_session.status_code == 202
            session = created_session.json()
            session_path = "/api/v1/advisor/sessions/" + session["session_id"]
            assert client.get(session_path, headers=headers).json()["status"] == "queued"
            worker = ReviewWorker(application.state.backend.jobs, advisor)
            try:
                assert worker.run_once() == session["comparison_job"]["job_id"]
                assert client.get(session_path, headers=headers).json()["status"] == "ready"
                assert client.post("/api/v1/advisor/sessions", headers=headers, json=body).json() == session
                headers["Idempotency-Key"] = "demo-chat"
                message = {"message": "Môn học liên quan thế nào đến công việc mục tiêu?"}
                reply = client.post(session_path + "/messages", headers=headers, json=message)
                assert reply.status_code == 200
                assert client.post(session_path + "/messages", headers=headers, json=message).json() == reply.json()
                history = client.get(session_path + "/messages", headers=headers).json()["turns"]
                assert len(history) == 1 and history[0]["message_id"] == reply.json()["message_id"]
                return {"catalog_courses": len(catalog.json()["courses"]),
                        "selection_summary": clo_set["summary"], "session_status": "ready", "committed_turns": len(history),
                        "selection_id": clo_set["selection_id"], "session_id": session["session_id"],
                        "mock_generations": {"review": review_client.responses.parse.call_count, "chat": chat_client.responses.parse.call_count},
                        "mock_preflights": {"review": review_client.responses.input_tokens.count.call_count,
                                            "chat": chat_client.responses.input_tokens.count.call_count}}
            finally:
                worker.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum-code", required=True)
    parser.add_argument("--curriculum-source-id", required=True)
    parser.add_argument("--career-profile-id", help="Use one catalog CWA group instead of the sample JD")
    args = parser.parse_args(argv)
    print(json.dumps(run_demo(curriculum_code=args.curriculum_code,
                             curriculum_source_id=args.curriculum_source_id, career_profile_id=args.career_profile_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
