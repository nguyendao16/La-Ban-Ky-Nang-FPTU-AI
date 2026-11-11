from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import academic_review as engine  # noqa: E402
import review_academic_profile as cli  # noqa: E402
from academic_review_prompt import ACADEMIC_REVIEW_INSTRUCTIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every offline test must fail if it accidentally reaches an HTTP transport."""
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline tests may not make network/API requests")
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)


@pytest.fixture
def profile():
    return {
        "profile_type": "academic",
        "courses": [
            {"course_code": "CPV301", "clos": [
                {"clo": "CLO8", "description": "Understand and implement object detection techniques.",
                 "score": 8.81, "achievement": "excellent"},
            ]},
            {"course_code": "DBI202", "clos": [
                {"clo": "CLO5", "description": "Use SQL for queries.", "score": 5.96, "achievement": "basic"},
            ]},
        ],
    }


@pytest.fixture
def review():
    return {
        "review_type": "academic_knowledge_review",
        "overview": "Hồ sơ cung cấp bằng chứng học thuật về object detection.",
        "requirement_reviews": [{
            "jd_requirement": "Object detection",
            "coverage": "covered",
            "comment": "CLO bao gồm hiểu và triển khai kỹ thuật object detection; achievement excellent phản ánh học thuật.",
            "evidence": [{"course_code": "CPV301", "clo": "CLO8"}],
        }],
        "conclusion": "Bằng chứng học thuật chưa xác nhận kinh nghiệm nghề nghiệp.",
    }


@pytest.fixture
def settings():
    return engine.ReviewSettings(api_key="offline-test-key")


def mock_client(review, *, status="completed", tokens=1000, output=None):
    client = Mock()
    client.responses.input_tokens.count.return_value = SimpleNamespace(input_tokens=tokens)
    client.responses.parse.return_value = SimpleNamespace(
        status=status, output=[] if output is None else output, output_parsed=review,
    )
    return client


def input_files(tmp_path, profile, jd="Object detection"):
    profile_path = tmp_path / "profile.json"
    jd_path = tmp_path / "jd.txt"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    jd_path.write_text(jd, encoding="utf-8")
    return profile_path, jd_path


def test_valid_files_and_atomic_utf8_output(tmp_path, profile, review, settings):
    profile_path, jd_path = input_files(tmp_path, profile)
    original = profile_path.read_bytes()
    destination = tmp_path / "new" / "review.json"
    result = engine.review_files(profile_path, jd_path, destination, settings=settings, client=mock_client(review))
    assert json.loads(destination.read_text(encoding="utf-8")) == result.model_dump() == review
    assert "học thuật" in destination.read_text(encoding="utf-8")
    assert profile_path.read_bytes() == original
    assert list(destination.parent.glob("*.tmp")) == []


def test_entire_actual_profile_sent_without_mutation(review, settings):
    profile = engine.load_profile(ROOT / "data/student_academic_profile.json")
    before = copy.deepcopy(profile)
    client = mock_client(review)
    engine.generate_review(profile, "Object detection", settings, client=client)
    kwargs = client.responses.parse.call_args.kwargs
    sent = json.loads(kwargs["input"][0]["content"])["student_academic_profile"]
    assert sent == before == profile
    assert len(sent["courses"]) == 15
    assert sum(len(course["clos"]) for course in sent["courses"]) == 122
    assert kwargs["text_format"] is engine.AcademicKnowledgeReview
    assert kwargs["instructions"] == ACADEMIC_REVIEW_INSTRUCTIONS
    assert kwargs["truncation"] == "disabled"
    assert kwargs["store"] is False
    assert kwargs["max_output_tokens"] == 4096
    assert "tools" not in kwargs
    client.responses.parse.assert_called_once()
    count_kwargs = client.responses.input_tokens.count.call_args.kwargs
    assert count_kwargs["input"] == kwargs["input"]
    assert count_kwargs["instructions"] == kwargs["instructions"]
    assert count_kwargs["text"]["format"] == engine.schema_format()


@pytest.mark.parametrize("contents", ["{", "[]", "{}", '{"profile_type":"academic","profile_type":"other","courses":[]}'])
def test_malformed_profile(tmp_path, contents):
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(engine.ReviewError):
        engine.load_profile(path)


def test_missing_profile(tmp_path):
    with pytest.raises(engine.ReviewError, match="Không thể đọc"):
        engine.load_profile(tmp_path / "missing.json")


@pytest.mark.parametrize("value", [-1, 11, float("nan"), float("inf"), True, "8.81"])
def test_invalid_profile_scores(profile, value):
    profile["courses"][0]["clos"][0]["score"] = value
    with pytest.raises(engine.ReviewError):
        engine.validate_profile(profile)


@pytest.mark.parametrize("field,value", [("description", "  "), ("achievement", "expert"), ("clo", ""), ("score", None)])
def test_invalid_clo_fields(profile, field, value):
    profile["courses"][0]["clos"][0][field] = value
    with pytest.raises(engine.ReviewError):
        engine.validate_profile(profile)


def test_not_evaluated_preserved(profile, review, settings):
    profile["courses"][0]["clos"][0].update(score=None, achievement="not_evaluated")
    client = mock_client(review)
    engine.generate_review(profile, "Object detection", settings, client=client)
    sent = json.loads(client.responses.parse.call_args.kwargs["input"][0]["content"])
    assert sent["student_academic_profile"] == profile


@pytest.mark.parametrize("kind", ["course", "clo"])
def test_duplicate_profile_identifiers(profile, kind):
    if kind == "course":
        profile["courses"].append(copy.deepcopy(profile["courses"][0]))
    else:
        profile["courses"][0]["clos"].append(copy.deepcopy(profile["courses"][0]["clos"][0]))
    with pytest.raises(engine.ReviewError, match="trùng"):
        engine.validate_profile(profile)


@pytest.mark.parametrize("jd", ["", " \n\t "])
def test_empty_jd(tmp_path, jd):
    path = tmp_path / "empty.txt"
    path.write_text(jd, encoding="utf-8")
    with pytest.raises(engine.ReviewError, match="không rỗng"):
        engine.load_jd(path)


@pytest.mark.parametrize("kind", ["missing", "encoding", "suffix"])
def test_bad_jd_files(tmp_path, kind):
    path = tmp_path / ("jd.json" if kind == "suffix" else "jd.txt")
    if kind != "missing":
        path.write_bytes(b"\xff" if kind == "encoding" else b"Object detection")
    with pytest.raises(engine.ReviewError):
        engine.load_jd(path)


@pytest.mark.parametrize("change", ["enum", "course", "clo", "wrong_course", "duplicate", "extra_score", "extra_achievement", "empty", "unsupported_with_evidence", "blank_comment", "missing_field", "extra_verdict"])
def test_reject_invalid_reviews(profile, review, change):
    row = review["requirement_reviews"][0]
    if change == "enum":
        row["coverage"] = "matched"
    elif change == "course":
        row["evidence"][0]["course_code"] = "FAKE999"
    elif change == "clo":
        row["evidence"][0]["clo"] = "CLO999"
    elif change == "wrong_course":
        row["evidence"][0]["course_code"] = "DBI202"
    elif change == "duplicate":
        row["evidence"].append(copy.deepcopy(row["evidence"][0]))
    elif change in {"extra_score", "extra_achievement"}:
        row["evidence"][0][change.removeprefix("extra_")] = 10 if change == "extra_score" else "excellent"
    elif change == "empty":
        row["evidence"] = []
    elif change == "unsupported_with_evidence":
        row["coverage"] = "not_evidenced"
    elif change == "blank_comment":
        row["comment"] = "   "
    elif change == "missing_field":
        del review["overview"]
    else:
        review["readiness_score"] = 100
    with pytest.raises(engine.ReviewError):
        engine.validate_review(review, profile)


def test_same_reference_across_requirements_allowed(profile, review):
    second = copy.deepcopy(review["requirement_reviews"][0])
    second.update(jd_requirement="General detection concepts", coverage="related")
    review["requirement_reviews"].append(second)
    assert len(engine.validate_review(review, profile).requirement_reviews) == 2


def test_not_evidenced_and_no_knowledge_requirements(profile, review):
    review["requirement_reviews"][0].update(coverage="not_evidenced", evidence=[])
    assert engine.validate_review(review, profile).requirement_reviews[0].coverage == "not_evidenced"
    review["requirement_reviews"] = []
    assert engine.validate_review(review, profile).requirement_reviews == []


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled", "in_progress"])
def test_noncompleted_responses(profile, review, settings, status):
    with pytest.raises(engine.ReviewError):
        engine.generate_review(profile, "Object detection", settings, client=mock_client(review, status=status))


def test_refusal(profile, review, settings):
    output = [SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal", refusal="No")])]
    with pytest.raises(engine.ReviewError, match="refusal"):
        engine.generate_review(profile, "Object detection", settings, client=mock_client(review, output=output))


def test_missing_parsed_output(profile, settings):
    with pytest.raises(engine.ReviewError, match="structured output"):
        engine.generate_review(profile, "Object detection", settings, client=mock_client(None))


def test_unparseable_json(profile, review, settings):
    client = mock_client(review)
    client.responses.parse.side_effect = json.JSONDecodeError("invalid", "{", 1)
    with pytest.raises(engine.ReviewError, match="không phân tích"):
        engine.generate_review(profile, "Object detection", settings, client=client)


@pytest.mark.parametrize("stage", ["count", "parse"])
@pytest.mark.parametrize("failure", ["auth", "quota", "rate", "timeout", "connection", "server", "bad_request"])
def test_api_errors_are_explicit_and_do_not_leak_credentials(profile, review, settings, failure, stage):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401 if failure == "auth" else 429 if failure in {"quota", "rate"} else 500 if failure == "server" else 400, request=request)
    secret_message = "offline-test-key must never be printed"
    if failure == "timeout":
        exc = openai.APITimeoutError(request=request)
    elif failure == "connection":
        exc = openai.APIConnectionError(message=secret_message, request=request)
    else:
        error_type = {"auth": openai.AuthenticationError, "quota": openai.RateLimitError,
                      "rate": openai.RateLimitError, "server": openai.InternalServerError,
                      "bad_request": openai.BadRequestError}[failure]
        exc = error_type(secret_message, response=response, body={"code": "insufficient_quota" if failure == "quota" else "other"})
    client = mock_client(review)
    target = client.responses.input_tokens.count if stage == "count" else client.responses.parse
    target.side_effect = exc
    with pytest.raises(engine.ReviewError) as caught:
        engine.generate_review(profile, "Object detection", settings, client=client)
    assert settings.api_key not in str(caught.value)
    if failure == "quota":
        assert "quota" in str(caught.value)
    if stage == "count":
        client.responses.parse.assert_not_called()


def test_context_preflight_stops_before_generation(profile, review, settings):
    client = mock_client(review, tokens=128000 - 4096 + 1)
    with pytest.raises(engine.ReviewError, match="vượt context"):
        engine.generate_review(profile, "Object detection", settings, client=client)
    client.responses.parse.assert_not_called()


def test_context_boundary_allowed(profile, review, settings):
    engine.generate_review(profile, "Object detection", settings, client=mock_client(review, tokens=128000 - 4096))


@pytest.mark.parametrize("tokens", [-1, True, "100"])
def test_invalid_token_count(profile, review, settings, tokens):
    client = mock_client(review, tokens=tokens)
    with pytest.raises(engine.ReviewError, match="đếm token"):
        engine.generate_review(profile, "Object detection", settings, client=client)
    client.responses.parse.assert_not_called()


def test_unknown_model_requires_confirmed_context():
    with pytest.raises(engine.ReviewError, match="context-window"):
        engine.ReviewSettings(api_key="offline", model="another-structured-model")
    with pytest.raises(engine.ReviewError, match="capability"):
        engine.ReviewSettings(api_key="offline", model="another-structured-model", context_window=64000)


@pytest.mark.parametrize("limit", [4096, 0, -1, True, 999999])
def test_invalid_context_limits(limit):
    with pytest.raises(engine.ReviewError):
        engine.ReviewSettings(api_key="offline", context_window=limit)


def test_configuration_precedence_and_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dotenv-test-key\nMODEL=gpt-4o-mini\n", encoding="utf-8")
    monkeypatch.setattr(engine, "ROOT", tmp_path)
    for key in ["OPENAI_API_KEY", "OPENAI_MODEL", "MODEL"]:
        monkeypatch.delenv(key, raising=False)
    # Restore the environment even though dotenv writes it directly.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    settings = engine.load_settings()
    assert settings.model == "gpt-4o-mini"
    assert settings.api_key == "dotenv-test-key"
    assert settings.api_key not in repr(settings)
    monkeypatch.setenv("OPENAI_API_KEY", "process-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
    assert engine.load_settings().model == "gpt-4o-mini-2024-07-18"
    assert engine.load_settings().api_key == "process-test-key"


def test_missing_key_is_clear():
    with pytest.raises(engine.ReviewError, match="OPENAI_API_KEY"):
        engine.ReviewSettings(api_key="")


def test_prompt_injection_is_only_data(review, settings):
    profile = engine.load_profile(ROOT / "data/student_academic_profile.json")
    jd = engine.load_jd(ROOT / "data/academic_review_evaluation/prompt_injection.txt")
    client = mock_client(review)
    engine.generate_review(profile, jd, settings, client=client)
    kwargs = client.responses.parse.call_args.kwargs
    assert json.loads(kwargs["input"][1]["content"])["job_description"] == jd
    assert "MALICIOUS" not in kwargs["instructions"]
    assert "untrusted DATA" in kwargs["instructions"]
    # This verifies request separation only; live semantic resistance is evaluated separately.


@pytest.mark.parametrize("existing", [False, True])
def test_invalid_generation_never_writes_output(tmp_path, profile, review, settings, existing):
    profile_path, jd_path = input_files(tmp_path, profile)
    destination = tmp_path / "review.json"
    if existing:
        destination.write_text("previous output", encoding="utf-8")
    review["requirement_reviews"][0]["evidence"][0]["clo"] = "CLO999"
    with pytest.raises(engine.ReviewError):
        engine.review_files(profile_path, jd_path, destination, settings=settings, client=mock_client(review))
    assert destination.read_text(encoding="utf-8") == "previous output" if existing else not destination.exists()


@pytest.mark.parametrize("target", ["profile", "jd", "symlink", "hardlink"])
def test_output_cannot_replace_inputs(tmp_path, profile, review, settings, target):
    profile_path, jd_path = input_files(tmp_path, profile)
    destination = profile_path if target == "profile" else jd_path
    if target in {"symlink", "hardlink"}:
        destination = tmp_path / "alias.json"
        if target == "symlink":
            destination.symlink_to(profile_path)
        else:
            os.link(profile_path, destination)
    client = mock_client(review)
    with pytest.raises(engine.ReviewError, match="ghi đè"):
        engine.review_files(profile_path, jd_path, destination, settings=settings, client=client)
    client.responses.input_tokens.count.assert_not_called()


def test_atomic_write_failure_preserves_existing_output(tmp_path, profile, review, monkeypatch):
    destination = tmp_path / "review.json"
    destination.write_text("previous output", encoding="utf-8")
    def fail_replace(*args, **kwargs):
        raise OSError("simulated failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(engine.ReviewError, match="Không thể ghi"):
        engine.write_review(destination, engine.validate_review(review, profile))
    assert destination.read_text(encoding="utf-8") == "previous output"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_cli_failure_exit_code_and_help(tmp_path, capsys):
    assert cli.main(["--profile", str(tmp_path / "absent.json"), "--jd", str(tmp_path / "jd.txt")]) == 1
    assert "Lỗi:" in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        cli.parse_args(["--help"])
    assert caught.value.code == 0


def test_sdk_timeout_retries_and_client_cleanup(profile, review, settings, monkeypatch):
    client = mock_client(review)
    constructor = Mock(return_value=client)
    monkeypatch.setattr(engine.openai, "OpenAI", constructor)
    engine.generate_review(profile, "Object detection", settings)
    constructor.assert_called_once_with(api_key="offline-test-key", timeout=60.0, max_retries=2)
    client.close.assert_called_once()


def test_cli_success_writes_validated_review(tmp_path, profile, review, settings, monkeypatch, capsys):
    profile_path, jd_path = input_files(tmp_path, profile)
    destination = tmp_path / "result.json"
    monkeypatch.setattr(cli, "load_settings", Mock(return_value=settings))
    client = mock_client(review)
    monkeypatch.setattr(engine.openai, "OpenAI", Mock(return_value=client))
    assert cli.main(["--profile", str(profile_path), "--jd", str(jd_path), "--output", str(destination)]) == 0
    assert json.loads(destination.read_text(encoding="utf-8")) == review
    assert "Đã lưu review" in capsys.readouterr().out


def test_owned_sdk_client_closed_on_failure(profile, review, settings, monkeypatch):
    client = mock_client(review, status="incomplete")
    monkeypatch.setattr(engine.openai, "OpenAI", Mock(return_value=client))
    with pytest.raises(engine.ReviewError):
        engine.generate_review(profile, "Object detection", settings)
    client.close.assert_called_once()


def test_response_schema_forbids_extra_fields_at_all_levels():
    schema = engine.schema_format()["schema"]
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
