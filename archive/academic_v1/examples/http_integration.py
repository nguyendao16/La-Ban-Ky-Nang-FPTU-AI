"""Complete HTTP flow with a temporary SQLite database and mocked inference.

No OpenAI client is constructed, no .env is loaded by model configuration, and
no global academic files are written. Capability tokens are never printed.
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
from examples.services_integration import mock_client
from scripts.academic_review import ReviewSettings
from scripts.clo_scoring import match_assessment, normalize_assessment_records


def run_demo(*, curriculum_code: str, curriculum_source_id: str):
    evidence = [{"course_code": "ADY201m", "clo": "CLO1"}]
    raw_review = {"review_type": "academic_knowledge_review", "overview": "MOCK: Academic Review.",
        "requirement_reviews": [{"jd_requirement": "SQL", "coverage": "related",
                                 "comment": "MOCK: kiểm thử orchestration, không đánh giá LLM.", "evidence": evidence}],
        "conclusion": "MOCK: kiến thức học thuật không xác nhận kinh nghiệm nghề nghiệp."}
    review_client = mock_client(raw_review)
    chat_client = mock_client({"reply": "MOCK: trả lời dựa trên academic context của phiên.", "evidence": evidence})
    advisor = AdvisorService(review_settings=ReviewSettings(api_key="offline-http", stage="review"),
        chat_settings=ReviewSettings(api_key="offline-http", stage="chat"),
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
            definitions = normalize_assessment_records(detail.json()["assessments"])
            source = json.loads((ROOT / "academic_report.json").read_text(encoding="utf-8"))["ADY201m"]
            grades = [{"course_code": "ADY201m", "category": match_assessment(name, definitions).assessment.category, "grade": grade}
                      for name, grade in source.items()]
            created_profile = client.post("/api/v1/profiles", json={"curriculum_code": curriculum_code,
                "selected_courses": ["ADY201m"], "grades": grades})
            assert created_profile.status_code == 201
            profile = created_profile.json()
            headers = {"Authorization": "Bearer " + profile["access_token"], "Idempotency-Key": "demo-create"}
            fetched = client.get("/api/v1/profiles/" + profile["profile_id"], headers=headers)
            assert fetched.status_code == 200 and fetched.json()["profile"] == profile["profile"]
            body = {"profile_id": profile["profile_id"], "job_description": (ROOT / "data/sample_jd.txt").read_text(encoding="utf-8")}
            created_session = client.post("/api/v1/advisor/sessions", headers=headers, json=body)
            assert created_session.status_code == 202
            session = created_session.json()
            session_path = "/api/v1/advisor/sessions/" + session["session_id"]
            assert client.get(session_path, headers=headers).json()["status"] == "queued"
            worker = ReviewWorker(application.state.backend.jobs, advisor)
            try:
                assert worker.run_once() == session["review_job"]["job_id"]
                assert client.get(session_path, headers=headers).json()["status"] == "ready"
                assert client.post("/api/v1/advisor/sessions", headers=headers, json=body).json() == session
                headers["Idempotency-Key"] = "demo-chat"
                message = {"message": "Mình đã học những kiến thức nào liên quan tới JD này?"}
                reply = client.post(session_path + "/messages", headers=headers, json=message)
                assert reply.status_code == 200
                assert client.post(session_path + "/messages", headers=headers, json=message).json() == reply.json()
                history = client.get(session_path + "/messages", headers=headers).json()["turns"]
                assert len(history) == 1 and history[0]["message_id"] == reply.json()["message_id"]
                return {"catalog_courses": len(catalog.json()["courses"]), "assessments": len(definitions),
                        "profile_summary": profile["summary"], "session_status": "ready", "committed_turns": len(history),
                        "profile_id": profile["profile_id"], "session_id": session["session_id"],
                        "mock_generations": {"review": review_client.responses.parse.call_count, "chat": chat_client.responses.parse.call_count},
                        "mock_preflights": {"review": review_client.responses.input_tokens.count.call_count,
                                            "chat": chat_client.responses.input_tokens.count.call_count}}
            finally:
                worker.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum-code", required=True)
    parser.add_argument("--curriculum-source-id", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_demo(curriculum_code=args.curriculum_code,
                             curriculum_source_id=args.curriculum_source_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
