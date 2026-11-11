"""Catalog -> grades -> profile -> Review -> Chat, using mocked LLM responses.

Run with an explicitly supplied curriculum alias/source-ID mapping. This demo
never loads .env, creates an OpenAI client, or persists academic/session files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

from app.services import AdvisorService, CourseService, ProfileService
from scripts.academic_review import ReviewSettings


def mock_client(payload):
    client = Mock()
    client.responses.input_tokens.count.return_value = SimpleNamespace(input_tokens=100)
    client.responses.parse.return_value = SimpleNamespace(status="completed", output=[], output_parsed=payload)
    return client


def run_demo(*, curriculum_code: str, curriculum_source_id: str) -> dict:
    course_service = CourseService(curriculum_mapping={curriculum_code: curriculum_source_id},
                                   default_curriculum_code=curriculum_code)
    profile_service = ProfileService(course_service)
    courses = course_service.list_courses()
    assessments = course_service.get_course_assessments("ADY201m")
    report = json.loads((ROOT / "academic_report.json").read_text(encoding="utf-8"))
    profile = profile_service.build_profile(
        selected_courses=["ADY201m"], assessment_scores={"ADY201m": report["ADY201m"]},
    )
    reference = {"course_code": "ADY201m", "clo": profile["courses"][0]["clos"][0]["clo"]}
    review_payload = {
        "review_type": "academic_knowledge_review", "overview": "MOCK: ví dụ điều phối Academic Review.",
        "requirement_reviews": [{"jd_requirement": "Kiến thức Python/SQL", "coverage": "related",
                                 "comment": "MOCK: tham chiếu học thuật hợp lệ, không đánh giá chất lượng LLM.",
                                 "evidence": [reference]}],
        "conclusion": "MOCK: dữ liệu học thuật không xác nhận kinh nghiệm nghề nghiệp.",
    }
    review_client = mock_client(review_payload)
    chat_client = mock_client({"reply": "MOCK: câu trả lời có evidence từ profile của phiên.", "evidence": [reference]})
    # Explicit offline settings prevent .env loading. The existing defaults are
    # exercised; stage-specific production settings remain caller-configurable.
    with AdvisorService(
        review_settings=ReviewSettings(api_key="offline-demo", stage="review"),
        chat_settings=ReviewSettings(api_key="offline-demo", stage="chat"),
        review_client=review_client, chat_client=chat_client,
    ) as advisor_service:
        session = advisor_service.create_session(
            profile=profile, job_description=(ROOT / "data/sample_jd.txt").read_text(encoding="utf-8"),
        )
        initial_review = advisor_service.run_initial_review(session.session_id)
        reply = advisor_service.send_message(session.session_id, "Mình đã học những kiến thức nào liên quan tới JD?")
        result = {"courses": courses, "assessments": assessments, "profile": profile,
                  "session": advisor_service.get_session(session.session_id).model_dump(),
                  "review": initial_review.model_dump(), "reply": reply.model_dump(),
                  "history": advisor_service.get_history(session.session_id)}
    result["mock_calls"] = {
        stage: {"preflight": client.responses.input_tokens.count.call_count,
                "generation": client.responses.parse.call_count}
        for stage, client in [("review", review_client), ("chat", chat_client)]
    }
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum-code", required=True, help="Explicit caller-supplied alias, not inferred from source ID.")
    parser.add_argument("--curriculum-source-id", required=True, help="Source curriculum ID in processed records.")
    args = parser.parse_args(argv)
    result = run_demo(curriculum_code=args.curriculum_code, curriculum_source_id=args.curriculum_source_id)
    print(json.dumps({"catalog_courses": len(result["courses"]),
                      "assessment_components": len(result["assessments"]["assessments"]),
                      "profile_courses": len(result["profile"]["courses"]),
                      "session_id": result["session"]["session_id"], "status": result["session"]["status"],
                      "reply": result["reply"], "mock_calls": result["mock_calls"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
