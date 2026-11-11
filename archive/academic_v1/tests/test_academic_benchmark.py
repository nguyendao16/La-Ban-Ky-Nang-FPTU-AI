"""Offline infrastructure checks; scripted replies are not semantic eval results."""
from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import academic_review as review
import academic_chat as chat
import evaluate_academic_benchmark as benchmark
import chat_academic_profile as chat_cli
import review_academic_profile as review_cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Offline benchmark tests cannot access HTTP")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


@pytest.fixture
def settings():
    return review.ReviewSettings(api_key="offline-benchmark-key", model="gpt-4.1")


@pytest.mark.parametrize("value", [-0.01, 2.01, float("nan"), float("inf"), -float("inf"), True, False, "0.3"])
def test_temperature_invalid_before_api(value):
    with pytest.raises(review.ReviewError, match="Temperature"):
        review.ReviewSettings(api_key="offline", temperature=value)


@pytest.mark.parametrize("value", [0, 0.3, 0.5, 2])
def test_temperature_propagates_to_single_generation(value):
    settings = review.ReviewSettings(api_key="offline", model="gpt-4.1", temperature=value)
    client = Mock()
    client.responses.input_tokens.count.return_value = SimpleNamespace(input_tokens=10)
    client.responses.parse.return_value = SimpleNamespace(status="completed", output=[], output_parsed={"reply": "Mock", "evidence": []})
    review.request_structured_response("instructions", [{"role": "user", "content": "question"}], chat.AcademicChatResponse, settings, client=client)
    client.responses.parse.assert_called_once()
    assert client.responses.parse.call_args.kwargs["temperature"] == value
    assert "temperature" not in client.responses.input_tokens.count.call_args.kwargs


def test_unknown_model_is_rejected_even_with_context_override():
    with pytest.raises(review.ReviewError, match="capability"):
        review.ReviewSettings(api_key="offline", model="unknown-model", context_window=64000)


def test_temperature_load_and_cli_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    assert review.load_settings(temperature=0.3).temperature == 0.3
    for cli in [chat_cli, review_cli]:
        assert cli.parse_args(["--jd", "jd.txt"]).temperature is None
        assert cli.parse_args(["--jd", "jd.txt", "--temperature", "0.3"]).temperature == 0.3


def test_manifest_all_sources_hashes_and_run_plan():
    manifest = benchmark.load_manifest()
    assert {c["case_id"] for c in manifest["cases"]} == {f"JD{i:02d}" for i in range(15)}
    assert sum(len(c["messages"]) for c in manifest["cases"]) == 45
    assert sum(len(c["deep_messages"]) for c in manifest["cases"]) == 8
    assert sum(c["temperature_pair"] for c in manifest["cases"]) == 6
    indexed = [c for c in manifest["cases"] if c["retrieval_method"] == "search_index"]
    assert indexed and all(c["snapshot_type"] == "sourced_paraphrase" and c["source_limitations"] for c in indexed)


@pytest.fixture
def project(tmp_path):
    profile = {"profile_type": "academic", "courses": [{"course_code": "CPV301", "clos": [
        {"clo": "CLO8", "description": "Understand and implement object detection.", "score": 8.81, "achievement": "excellent"},
    ]}]}
    baseline = tmp_path / "data/sample_jd.txt"
    baseline.parent.mkdir()
    baseline.write_text("Object detection; YOLO preferred. Production work is an internship responsibility.\n", encoding="utf-8")
    profile_path = tmp_path / "data/profile.json"
    benchmark.atomic_json(profile_path, profile)
    jd = tmp_path / "data/academic_benchmark/jds/JD00.txt"
    jd.parent.mkdir(parents=True)
    jd.write_bytes(baseline.read_bytes())
    case = {"case_id": "JD00", "company": "Local", "role": "CV", "category": "computer_vision",
            "checked_at": "2026-10-13", "source_type": "local", "retrieval_method": "local_file",
            "snapshot_type": "local_synthetic_baseline", "source_limitations": "Local fixture",
            "jd_path": str(jd.relative_to(tmp_path)), "jd_sha256": benchmark.digest(jd.read_bytes()),
            "messages": [{"user": s, "expected": "Transport only"} for s in ["Kiến thức liên quan?", "Phần chưa xác nhận?", "CLO đó bao nhiêu điểm?"]],
            "deep_messages": [{"user": "Chi tiết hơn", "expected": "Transport only"}, {"user": "Tóm tắt", "expected": "Transport only"}],
            "temperature_pair": True}
    manifest = {"version": 1, "profile_path": "data/profile.json", "profile_sha256": benchmark.digest(profile_path.read_bytes()), "cases": [case]}
    benchmark.atomic_json(tmp_path / "data/academic_benchmark/manifest.json", manifest)
    return tmp_path, manifest


@pytest.mark.parametrize("kind", ["jd_hash", "profile_hash", "duplicate", "unsafe_id", "unsafe_path", "missing_source"])
def test_manifest_rejects_wrong_provenance(project, kind):
    root, manifest = project
    case = manifest["cases"][0]
    if kind == "jd_hash": case["jd_sha256"] = "bad"
    elif kind == "profile_hash": manifest["profile_sha256"] = "bad"
    elif kind == "duplicate": manifest["cases"].append(copy.deepcopy(case))
    elif kind == "unsafe_id": case["case_id"] = "../JD00"
    elif kind == "unsafe_path": case["jd_path"] = "../../outside.txt"
    else: case["source_limitations"] = ""
    benchmark.atomic_json(root / "data/academic_benchmark/manifest.json", manifest)
    with pytest.raises(review.ReviewError): benchmark.load_manifest(root)


@pytest.mark.parametrize("run_id", ["../escape", "with/slash", "", ".hidden"])
def test_unsafe_run_ids(project, settings, run_id):
    root, manifest = project
    with pytest.raises(review.ReviewError): benchmark.EvaluationRun(root, manifest, run_id, settings)


def fake_sdk():
    calls = []
    def parse(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        if kwargs["text_format"] is review.AcademicKnowledgeReview:
            raw = {"review_type": "academic_knowledge_review", "overview": "Mock review",
                   "requirement_reviews": [{"jd_requirement": "Object detection", "coverage": "covered", "comment": "Mock comment", "evidence": [{"course_code": "CPV301", "clo": "CLO8"}]}], "conclusion": "Mock conclusion"}
        else:
            raw = {"reply": "Mock CLO8: 8.81, excellent.", "evidence": [{"course_code": "CPV301", "clo": "CLO8"}]}
        response = SimpleNamespace(status="completed", output=[], output_parsed=kwargs["text_format"].model_validate(raw),
                                   model="gpt-4.1-2025-04-14", usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 100, "output_tokens": 20}))
        return SimpleNamespace(text=json.dumps({"mock": True, "output": raw}), retries_taken=0, parse=lambda: response)
    sdk = SimpleNamespace(responses=SimpleNamespace(
        input_tokens=SimpleNamespace(count=lambda **kwargs: SimpleNamespace(input_tokens=100)),
        with_raw_response=SimpleNamespace(parse=parse)))
    return sdk, calls


def test_whole_case_resume_deep_and_frozen_temperature(project, settings):
    root, manifest = project
    before = (root / manifest["profile_path"]).read_bytes()
    run = benchmark.EvaluationRun(root, manifest, "offline", settings)
    sdk, calls = fake_sdk()
    transport = SimpleNamespace(operation=None, budget_exhausted=False)
    client = benchmark.RecordingClient(sdk, run, transport)
    try:
        benchmark.run_cases(run, client, manifest["cases"])
        assert len(calls) == 4  # one review + three real session sends, all mocked
        benchmark.run_cases(run, client, manifest["cases"])
        assert len(calls) == 4  # no duplicate paid generation on phase resume
        benchmark.run_cases(run, client, manifest["cases"], deep=True)
        assert len(calls) == 6
        assert [len(call["input"]) for call in calls[1:6]] == [4, 6, 8, 10, 12]
        baseline = calls[3]
        assert all("Transport only" not in json.dumps(call["input"]) for call in calls)
        benchmark.run_temperature(run, client, manifest["cases"])
        assert len(calls) == 7 and calls[-1]["temperature"] == 0.3
        for key in ["input", "instructions", "model", "max_output_tokens", "text_format", "store", "truncation"]:
            assert calls[-1][key] == baseline[key]
        benchmark.run_temperature(run, client, manifest["cases"])
        assert len(calls) == 7
        conversation = benchmark.read_json(root / "data/academic_benchmark/conversations/offline/JD00.json")
        assert len(conversation["turns"]) == 5
        assert run.data["temperature_pairs"]["JD00"]["status"] == "comparable"
        assert (root / manifest["profile_path"]).read_bytes() == before
    finally:
        run.close()


def test_swapped_review_and_changed_context_are_rejected(project, settings):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "offline", settings)
    sdk, _ = fake_sdk()
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    try:
        benchmark.run_cases(run, client, manifest["cases"])
        path = benchmark.review_path(run, "JD00")
        modified = benchmark.read_json(path)
        modified["overview"] = "Different JD review"
        benchmark.atomic_json(path, modified)
        with pytest.raises(review.ReviewError, match="không khớp"):
            benchmark.run_cases(run, client, manifest["cases"])
    finally: run.close()
    with pytest.raises(review.ReviewError, match="Không resume"):
        benchmark.EvaluationRun(root, manifest, "offline", replace(settings, model="gpt-4.1-2025-04-14"))


def test_failure_preserves_raw_response_and_no_replacement(project, settings):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "offline", settings)
    sdk, _ = fake_sdk()
    def bad_parse(**kwargs):
        response = SimpleNamespace(status="incomplete", output=[], output_parsed=None, model=settings.model, usage=None)
        return SimpleNamespace(text='{"status":"incomplete","output":[]}', retries_taken=0, parse=lambda: response)
    sdk.responses.with_raw_response.parse = bad_parse
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    try:
        benchmark.run_cases(run, client, manifest["cases"])
        trace = benchmark.read_json(run.directory / "requests/review-JD00.json")
        assert trace["raw_response"] == '{"status":"incomplete","output":[]}'
        assert trace["validation_status"] == "failed"
        assert not benchmark.review_path(run, "JD00").exists()
        assert "session_id" not in run.data["cases"]["JD00"]
    finally: run.close()


def test_sdk_retry_counts_http_and_blocks_before_dispatch(project, settings):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "retry", settings, maximum=1)
    requests = []
    def serve(request):
        requests.append(request)
        return httpx.Response(500, json={"error": {"type": "server_error", "code": "server_error"}})
    transport = benchmark.BudgetTransport(run, httpx.MockTransport(serve))
    try:
        with openai.OpenAI(api_key="offline-secret", max_retries=2, http_client=httpx.Client(transport=transport)) as sdk:
            with pytest.raises(openai.APIConnectionError): sdk.responses.create(model=settings.model, input="mock")
        assert len(requests) == run.data["generation_attempts"] == 1
        assert transport.budget_exhausted
        run.consume_http("preflight", "count")
        assert run.data["preflight_attempts"] == 1
    finally: run.close()


def test_api_failure_stops_remaining_cases_without_fabricating_review(project, settings):
    root, manifest = project
    other = copy.deepcopy(manifest["cases"][0])
    other["case_id"] = "JD01"
    manifest["cases"].append(other)
    run = benchmark.EvaluationRun(root, manifest, "failure", settings)
    sdk, calls = fake_sdk()
    def fail(**kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses/input_tokens"))
    sdk.responses.input_tokens.count = fail
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    try:
        benchmark.run_cases(run, client, manifest["cases"])
        assert client.stop_requested and not calls
        assert "JD01" not in run.data["cases"]
        assert not benchmark.review_path(run, "JD00").exists()
        assert "stop_reason" in run.data
    finally: run.close()


def test_authentication_error_does_not_store_key(project, settings):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "auth", settings)
    transport = benchmark.BudgetTransport(run, httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "Incorrect API key: offline-secret", "type": "authentication_error", "code": "invalid_api_key"}})))
    try:
        with openai.OpenAI(api_key="offline-secret", http_client=httpx.Client(transport=transport)) as sdk:
            with pytest.raises(openai.AuthenticationError): sdk.responses.create(model=settings.model, input="mock")
        assert "offline-secret" not in run.path.read_text()
        assert run.data["generation_attempts"] == 1
    finally: run.close()


def test_offline_runner_never_initializes_sdk(monkeypatch):
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: pytest.fail("Offline CLI initialized SDK"))
    assert benchmark.main([]) == 0
    assert benchmark.main(["--case", "JD02", "--phase", "temperature"]) == 0
    assert benchmark.main(["--max-generations", "81"]) == 1


def test_budget_survives_resume_and_run_lock_is_exclusive(project, settings):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "durable", settings, maximum=1)
    try:
        with pytest.raises(BlockingIOError):
            benchmark.EvaluationRun(root, manifest, "durable", settings, maximum=1)
        run.consume_http("generation", "first")
    finally:
        run.close()
    resumed = benchmark.EvaluationRun(root, manifest, "durable", settings, maximum=1)
    try:
        assert resumed.data["generation_attempts"] == 1
        with pytest.raises(review.ReviewError, match="budget"):
            resumed.consume_http("generation", "retry")
        assert len(resumed.data["http_attempts"]) == 1
    finally:
        resumed.close()


@pytest.mark.parametrize("failure", ["unparseable", "invalid_evidence"])
def test_failed_chat_keeps_raw_and_committed_history_without_overwrite(project, settings, failure):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "failed-chat", settings)
    sdk, calls = fake_sdk()
    original_parse = sdk.responses.with_raw_response.parse
    raw_text = '{"reply":"Raw failed reply","evidence":[{"course_code":"CPV301","clo":"CLO999"}]}'
    def parse(**kwargs):
        if len(calls) < 2:
            return original_parse(**kwargs)  # valid review and first chat turn
        def malformed():
            raise ValueError("Invalid structured JSON")
        response = SimpleNamespace(
            status="completed", output=[], model=settings.model, usage=None,
            output_parsed=chat.AcademicChatResponse.model_validate(json.loads(raw_text)),
        )
        return SimpleNamespace(text=raw_text, retries_taken=0,
                               parse=malformed if failure == "unparseable" else lambda: response)
    sdk.responses.with_raw_response.parse = parse
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    try:
        benchmark.run_cases(run, client, manifest["cases"])
        trace_path = run.directory / "requests/chat-JD00-2.json"
        trace = benchmark.read_json(trace_path)
        assert trace["validation_status"] == "failed" and trace["raw_response"] == raw_text
        conversation = benchmark.read_json(root / "data/academic_benchmark/conversations/failed-chat/JD00.json")
        assert len(conversation["turns"]) == 1
        assert conversation["turns"][0]["response"]["evidence"][0]["clo"] == "CLO8"
        before = trace_path.read_bytes()
        with pytest.raises(review.ReviewError, match="Không ghi đè"):
            client.begin("chat-JD00-2")
        assert trace_path.read_bytes() == before
        benchmark.run_cases(run, client, manifest["cases"])
        assert len(calls) == 2  # failed case is never silently replaced/retried
    finally:
        run.close()


def test_source_change_is_detected_before_any_request(project, settings):
    root, manifest = project
    run = benchmark.EvaluationRun(root, manifest, "changed", settings)
    sdk, calls = fake_sdk()
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    try:
        (root / manifest["cases"][0]["jd_path"]).write_text("Changed JD", encoding="utf-8")
        with pytest.raises(review.ReviewError, match="JD thay đổi"):
            benchmark.run_cases(run, client, manifest["cases"])
        assert not calls and run.data["generation_attempts"] == 0
    finally:
        run.close()
