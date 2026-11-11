"""Data integrity and request compatibility; mocks do not grade model semantics."""
import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import academic_review as review
import academic_chat as chat
import clo_scoring as scoring
import evaluate_academic_benchmark as benchmark
import academic_model_comparison as comparison
import review_academic_profile as review_cli
import chat_academic_profile as chat_cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline test attempted real HTTP")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(review, "load_dotenv", lambda *a, **k: None)
    for key in list(os.environ):
        if key == "MODEL" or key.startswith("OPENAI_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")


def metadata(code="TEST101", tools=""):
    return {"syllabus_name": "Môn học", "course_name_english": "Course", "subject_code": code,
            "description": "Foundations of SQL", "tools": tools}


@pytest.fixture
def course(tmp_path):
    path = tmp_path / "TEST101"
    path.mkdir()
    (path / "clos.json").write_text(json.dumps([{"clo": "CLO1", "description": "Use SQL"}]))
    (path / "assessments.json").write_text(json.dumps([{"category": "Quiz", "part": "1", "weight": "100%", "clo": "CLO1"}]))
    return path


def test_builder_preserves_raw_metadata_and_ignores_unselected(course):
    raw = metadata(tools="PyCharm or MATLAB\nTextbook\n- Internet")
    raw["source_note"] = "Preserve extra source fields"
    (course / "metadata.json").write_text(json.dumps(raw))
    other = course.parent / "OTHER101"
    other.mkdir()
    (other / "metadata.json").write_text("malformed unrelated source")
    before, _ = scoring.build_profile_from_report({"TEST101": {"Quiz": 8.2}}, course.parent)
    after, report = scoring.build_profile_from_report({"TEST101": {"Quiz": 8.2}}, course.parent)
    assert after == before
    assert after["courses"][0]["metadata"] == raw
    assert after["courses"][0]["clos"] == [{"clo": "CLO1", "description": "Use SQL", "score": 8.2, "achievement": "good"}]
    assert report["courses_with_metadata"] == 1 and not report["metadata_validation_errors"]
    review.validate_profile(after)


@pytest.mark.parametrize("source", [None, "{broken", "[]", '{"subject_code":"WRONG"}',
                                     json.dumps(metadata("WRONG")), json.dumps({**metadata(), "tools": []}),
                                     '{"subject_code":"TEST101","subject_code":"TEST101"}',
                                     json.dumps({**metadata(), "extra": float("nan")})])
def test_metadata_failure_retains_all_clos(course, source):
    if source is not None:
        (course / "metadata.json").write_text(source)
    profile, report = scoring.build_profile_from_report({"TEST101": {"Quiz": 0}}, course.parent)
    assert profile["courses"][0]["clos"][0]["score"] == 0
    assert "metadata" not in profile["courses"][0]
    assert report["processed_courses"] == 1 and report["courses_without_metadata"] == 1
    assert report["metadata_validation_errors"][0]["course_code"] == "TEST101"
    review.validate_profile(profile)


def test_empty_tools_and_atomic_deterministic_writer(course, monkeypatch):
    (course / "metadata.json").write_text(json.dumps(metadata()))
    profile, _ = scoring.build_profile_from_report({"TEST101": {"Quiz": 7}}, course.parent)
    assert profile["courses"][0]["metadata"]["tools"] == ""
    output = course.parent / "profile.json"
    scoring.write_json(output, profile)
    first = output.read_bytes()
    scoring.write_json(output, profile)
    assert output.read_bytes() == first
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        scoring.write_json(output, {"changed": True})
    assert output.read_bytes() == first
    assert not list(course.parent.glob(".*.tmp"))


def test_actual_profile_metadata_and_every_original_value():
    legacy = review.load_profile(ROOT / "data/student_academic_profile.json")
    enriched, report = scoring.build_profile_from_report(scoring.load_json(ROOT / "academic_report.json"), ROOT / "data/courses")
    projected = copy.deepcopy(enriched)
    for course in projected["courses"]:
        raw = scoring.load_json(ROOT / "data/courses" / course["course_code"] / "metadata.json")
        assert course.pop("metadata") == raw
    assert projected == legacy
    assert report["courses_with_metadata"] == 15 and report["total_clos_evaluated"] == 122
    assert sum(c["metadata"]["tools"] == "" for c in enriched["courses"]) == 4
    review.validate_profile(enriched)


@pytest.fixture
def inputs():
    legacy = review.load_profile(ROOT / "data/student_academic_profile.json")
    enriched = copy.deepcopy(legacy)
    for course in enriched["courses"]:
        course["metadata"] = scoring.load_json(ROOT / "data/courses" / course["course_code"] / "metadata.json")
    return legacy, enriched


def review_object(evidence, coverage="related"):
    return {"review_type": "academic_knowledge_review", "overview": "Context", "conclusion": "Academic",
            "requirement_reviews": [{"jd_requirement": "SQL", "coverage": coverage, "comment": "Course context", "evidence": evidence}]}


def test_metadata_evidence_coverage_and_strict_references(inputs):
    legacy, enriched = inputs
    tools = {"course_code": "ADY201m", "metadata_field": "tools"}
    description = {"course_code": "ADY201m", "metadata_field": "description"}
    review.validate_review(review_object([tools]), enriched)
    review.validate_review(review_object([description], "covered"), enriched)
    with pytest.raises(review.ReviewError, match="tools-only"):
        review.validate_review(review_object([tools], "covered"), enriched)
    with pytest.raises(review.ReviewError):
        review.validate_review(review_object([tools]), legacy)
    for bad in [[tools, tools], [{**tools, "clo": "CLO3"}], [{**tools, "metadata_field": "subject_code"}],
                [{"course_code": "MAE101", "metadata_field": "tools"}], [{**tools, "course_code": "WRONG"}],
                [{"course_code": "ADY201m", "clo": "WRONG"}]]:
        with pytest.raises(review.ReviewError):
            review.validate_review(review_object(bad), enriched)
    with pytest.raises(review.ReviewError):
        review.validate_review(review_object([tools], "not_evidenced"), enriched)
    chat.validate_chat_response({"reply": "Course tools", "evidence": [tools]}, review.validate_profile(enriched))


def make_client(parsed, tokens=100):
    client = Mock()
    client.responses.input_tokens.count.return_value = SimpleNamespace(input_tokens=tokens)
    client.responses.parse.return_value = SimpleNamespace(status="completed", output=[], output_parsed=parsed)
    return client


def test_both_engines_send_metadata_and_persist_references(inputs, tmp_path):
    _, profile = inputs
    paths = [tmp_path / "profile.json", tmp_path / "jd.txt", tmp_path / "review.json"]
    initial = review_object([{"course_code": "ADY201m", "metadata_field": "description"}], "covered")
    benchmark.atomic_json(paths[0], profile)
    paths[1].write_text("SQL")
    benchmark.atomic_json(paths[2], initial)
    settings = review.ReviewSettings(api_key="offline", model="gpt-4.1")
    client = make_client(initial)
    review.generate_review(profile, "SQL", settings, client=client)
    assert json.loads(client.responses.parse.call_args.kwargs["input"][0]["content"])["student_academic_profile"] == profile
    reply = {"reply": "GitHub is listed as course context", "evidence": [{"course_code": "ADY201m", "metadata_field": "tools"}]}
    client = make_client(reply)
    with chat.AcademicChatSession.from_files(*paths, settings=settings, client=client, persist=True, session_dir=tmp_path / "sessions") as session:
        session.send("GitHub?")
        identifier = session.session_id
        assert json.loads(client.responses.parse.call_args.kwargs["input"][0]["content"])["student_academic_profile"] == profile
    with chat.AcademicChatSession.from_files(*paths, settings=settings, client=client, resume=identifier, session_dir=tmp_path / "sessions") as session:
        assert session.history[-1]["evidence"] == reply["evidence"]
        changed = copy.deepcopy(profile)
        changed["courses"][0]["metadata"]["tools"] = "Changed"
        benchmark.atomic_json(paths[0], changed)
        with pytest.raises(review.ReviewError, match="thay đổi"):
            session.send("Question")
    assert client.responses.parse.call_count == 1


@pytest.mark.parametrize("model,stage,effort,budget,temperature", [
    ("gpt-4.1", "review", None, 4096, 0), ("gpt-4o-mini", "chat", None, 4096, 0),
    ("gpt-5.4", "review", "high", 16384, None), ("gpt-5.4-mini", "chat", "medium", 8192, None),
    ("gpt-5.4-2026-03-05", "chat", "medium", 8192, None), ("gpt-5.4-mini-2026-03-17", "review", "high", 16384, None),
])
def test_stage_defaults_and_request_options(model, stage, effort, budget, temperature):
    settings = review.ReviewSettings(api_key="offline", model=model, stage=stage)
    assert (settings.reasoning_effort, settings.max_output_tokens, settings.temperature) == (effort, budget, temperature)
    client = make_client({"reply": "Answer", "evidence": []})
    review.request_structured_response("instructions", [], chat.AcademicChatResponse, settings, client=client)
    generation = client.responses.parse.call_args.kwargs
    count = client.responses.input_tokens.count.call_args.kwargs
    assert generation["max_output_tokens"] == budget and generation["store"] is False
    assert generation["truncation"] == "disabled"
    assert count["text"]["format"] == review.structured_schema_format(chat.AcademicChatResponse)
    assert ("reasoning" in generation) == (effort is not None)
    assert count.get("reasoning") == generation.get("reasoning")
    assert ("temperature" in generation) == (temperature is not None)
    client.responses.parse.assert_called_once()


@pytest.mark.parametrize("kwargs", [
    {"model": "gpt-5.4-pro"}, {"model": "gpt-5.4-mini-2099-01-01", "context_window": 400000},
    {"model": "gpt-4.1", "reasoning_effort": "high"}, {"model": "gpt-5.4", "reasoning_effort": "minimal"},
    {"model": "gpt-5.4", "temperature": 0}, {"model": "gpt-5.4-mini", "reasoning_effort": "none", "temperature": 0},
    {"model": "gpt-5.4-mini", "context_window": 400001}, {"model": "gpt-4.1", "max_output_tokens": 32769},
    {"max_output_tokens": True}, {"max_output_tokens": 0}, {"stage": "wrong"},
])
def test_incompatible_settings_never_create_client(kwargs, monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(review.openai, "OpenAI", constructor)
    with pytest.raises(review.ReviewError):
        review.ReviewSettings(api_key="offline", **kwargs)
    constructor.assert_not_called()


def test_stage_environment_cli_precedence_and_validation(monkeypatch):
    monkeypatch.setenv("MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("OPENAI_REVIEW_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_REVIEW_REASONING_EFFORT", "high")
    monkeypatch.setenv("OPENAI_REVIEW_MAX_OUTPUT_TOKENS", "16000")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_CHAT_REASONING_EFFORT", "low")
    monkeypatch.setenv("OPENAI_CHAT_MAX_OUTPUT_TOKENS", "6000")
    initial = review.load_settings()
    followup = review.load_settings(stage="chat")
    assert (initial.model, initial.reasoning_effort, initial.max_output_tokens) == ("gpt-5.4", "high", 16000)
    assert (followup.model, followup.reasoning_effort, followup.max_output_tokens) == ("gpt-5.4-mini", "low", 6000)
    override = review.load_settings(stage="chat", model="gpt-5.4", reasoning_effort="medium", max_output_tokens=7000)
    assert (override.model, override.reasoning_effort, override.max_output_tokens) == ("gpt-5.4", "medium", 7000)
    monkeypatch.setenv("OPENAI_CHAT_MAX_OUTPUT_TOKENS", "bad")
    with pytest.raises(review.ReviewError, match="số nguyên"):
        review.load_settings(stage="chat")
    assert review.load_settings(stage="chat", max_output_tokens=5000).max_output_tokens == 5000
    for cli in [review_cli, chat_cli]:
        args = cli.parse_args(["--jd", "jd.txt", "--model", "gpt-5.4-mini", "--reasoning-effort", "low", "--max-output-tokens", "5000"])
        assert (args.model, args.reasoning_effort, args.max_output_tokens, args.temperature) == ("gpt-5.4-mini", "low", 5000, None)


def test_reasoning_output_budget_boundary_and_incomplete_reason():
    settings = review.ReviewSettings(api_key="offline", model="gpt-5.4", context_window=17000)
    client = make_client({}, tokens=617)
    with pytest.raises(review.ReviewError, match="vượt context"):
        review.request_structured_response("", [], chat.AcademicChatResponse, settings, client=client)
    client.responses.parse.assert_not_called()
    client.responses.input_tokens.count.return_value.input_tokens = 616
    client.responses.parse.return_value = SimpleNamespace(status="incomplete", output=[], incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    with pytest.raises(review.ReviewError, match="incomplete: max_output_tokens"):
        review.request_structured_response("", [], chat.AcademicChatResponse, settings, client=client)
    client.responses.parse.assert_called_once()


def test_chat_uses_chat_stage_when_settings_not_injected(inputs, tmp_path, monkeypatch):
    _, profile = inputs
    paths = [tmp_path / "profile.json", tmp_path / "jd.txt", tmp_path / "review.json"]
    benchmark.atomic_json(paths[0], profile)
    paths[1].write_text("SQL")
    benchmark.atomic_json(paths[2], review_object([], "not_evidenced"))
    settings = review.ReviewSettings(api_key="offline", stage="chat", model="gpt-5.4-mini")
    loader = Mock(return_value=settings)
    monkeypatch.setattr(chat, "load_settings", loader)
    with chat.AcademicChatSession.from_files(*paths) as session:
        assert session.model == "gpt-5.4-mini"
    loader.assert_called_once_with(None, stage="chat")
