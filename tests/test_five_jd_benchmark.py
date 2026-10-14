"""Two-stage dispatch, durable budgets and recovery, with no paid API calls."""
import copy
import json
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import httpx
import openai
import pytest

from test_academic_benchmark import project, fake_sdk
import academic_review as review
import academic_chat as chat
import evaluate_academic_benchmark as benchmark
import academic_model_comparison as comparison


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("Real HTTP forbidden"))
    monkeypatch.setattr(review, "load_dotenv", lambda *a, **k: None)


@pytest.fixture
def five(project):
    root, manifest = project
    original = manifest["cases"][0]
    cases = []
    for identifier in ["JD01", "JD05", "JD07", "JD10", "JD11"]:
        case = copy.deepcopy(original)
        case.update(case_id=identifier, jd_path=f"data/academic_benchmark/jds/{identifier}.txt",
                    actual_source_url="https://example.com/intern", temperature_pair=False, deep_messages=[])
        path = root / case["jd_path"]
        path.write_text(f"Object detection {identifier}; YOLO preferred.")
        case["jd_sha256"] = benchmark.digest(path.read_bytes())
        case["messages"] = [{"user": f"{identifier} question {turn}", "expected": "Manual"} for turn in range(1, 5)]
        cases.append(case)
    manifest["cases"] = cases
    benchmark.atomic_json(root / "data/academic_benchmark/manifest.json", manifest)
    return root, manifest


def configs():
    return (review.ReviewSettings(api_key="offline", model="gpt-5.4", reasoning_effort="high",
                                 max_output_tokens=32768, request_timeout=360),
            review.ReviewSettings(api_key="offline", stage="chat", model="gpt-5.4-mini",
                                 reasoning_effort="medium", max_output_tokens=8192, request_timeout=180))


def new_run(five, identifier="five", **overrides):
    first, chat = configs()
    options = dict(maximum=25, chat_settings=chat, maximum_preflights=25, maximum_cost=6,
                   max_retries=0, continue_on_case_error=True)
    options.update(overrides)
    return benchmark.EvaluationRun(*five, identifier, first, **options)


def body(payload, *, invalid=False, incomplete=False):
    if payload["text"]["format"]["name"] == "AcademicKnowledgeReview":
        parsed = {"review_type": "academic_knowledge_review", "overview": "Mock", "conclusion": "Mock",
                  "requirement_reviews": [{"jd_requirement": "Object detection", "coverage": "covered", "comment": "Mock",
                      "evidence": [{"course_code": "CPV301", "clo": "CLO8"}]}]}
    else:
        parsed = {"reply": "Mock score 8.81/excellent.", "evidence": [{"course_code": "CPV301", "clo": "CLO999" if invalid else "CLO8"}]}
    return {"id": "resp_mock", "object": "response", "created_at": 1,
        "status": "incomplete" if incomplete else "completed", "model": payload["model"],
        "incomplete_details": {"reason": "max_output_tokens"} if incomplete else None,
        "output": [] if incomplete else [{"type": "message", "id": "msg_mock", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(parsed), "annotations": []}]}],
        "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 100}, "output_tokens_details": {"reasoning_tokens": 20}}}


def execute(run, handler):
    transport = benchmark.BudgetTransport(run, httpx.MockTransport(handler))
    with openai.OpenAI(api_key="offline", max_retries=0, http_client=httpx.Client(transport=transport)) as sdk:
        client = benchmark.RecordingClient(sdk, run, transport)
        benchmark.run_cases(run, client, run.manifest["cases"])
        benchmark.record_case_statuses(run, run.manifest["cases"])
    return client


def test_real_sdk_two_stages_full_history_and_physical_caps(five):
    dispatched = []
    def serve(request):
        payload = json.loads(request.content)
        dispatched.append((request.url.path, payload, request.extensions["timeout"]["read"]))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        return httpx.Response(200, json=body(payload))
    run = new_run(five)
    try:
        execute(run, serve)
        assert run.data["generation_attempts"] == run.data["preflight_attempts"] == 25
        for path, payload, timeout in dispatched:
            assert "temperature" not in payload
            is_review = payload["model"] == "gpt-5.4"
            assert timeout == (360 if is_review else 180)
            assert payload["reasoning"]["effort"] == ("high" if is_review else "medium")
            if path.endswith("/responses"):
                assert payload["store"] is False and payload["truncation"] == "disabled"
                assert payload["max_output_tokens"] == (32768 if is_review else 8192)
        chat_inputs = [p["input"] for path, p, _ in dispatched if path.endswith("/responses") and p["model"] == "gpt-5.4-mini"]
        assert [len(messages) for messages in chat_inputs] == [4, 6, 8, 10] * 5
        assert len({state["session_id"] for state in run.data["cases"].values()}) == 5
        assert all(state["successful_turns"] == 4 for state in run.data["cases"].values())
        for index, messages in enumerate(chat_inputs):
            identifier = run.manifest["cases"][index // 4]["case_id"]
            assert identifier in json.loads(messages[1]["content"])["current_job_description"]
            assert messages[-1]["content"] == f"{identifier} question {index % 4 + 1}"
        count = len(dispatched)
        execute(run, serve)
        assert len(dispatched) == count
        trace = benchmark.read_json(run.directory / "requests/chat-JD01-1.json")
        assert trace["metrics"]["requested_model"] == "gpt-5.4-mini"
        assert trace["metrics"]["stage"] == "chat"
        assert Decimal(trace["metrics"]["estimated_cost_usd"]) == comparison.estimate_cost("gpt-5.4-mini", 1000, 100, 100)
        assert run.accounted_cost() < Decimal(run.data["reserved_cost_usd"])
        with pytest.raises(review.ReviewError, match="preflight"):
            run.consume_http("preflight", "extra")
    finally:
        run.close()


@pytest.mark.parametrize("failure", ["timeout", "incomplete", "chat_reference"])
def test_case_failures_skip_remaining_turns_and_continue_without_retry(five, failure):
    run = new_run(five)
    generations = []
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        operation = next(reversed(run.data["http_attempts"]))["operation"]
        generations.append(operation)
        if operation == "review-JD01" and failure == "timeout":
            raise httpx.ReadTimeout("Mock timeout", request=request)
        return httpx.Response(200, json=body(payload,
            incomplete=operation == "review-JD01" and failure == "incomplete",
            invalid=operation == "chat-JD01-2" and failure == "chat_reference"))
    try:
        client = execute(run, serve)
        assert not client.stop_requested
        assert run.data["cases"]["JD05"]["successful_turns"] == 4
        first = run.data["cases"]["JD01"]
        assert first["failed"]
        if failure == "chat_reference":
            assert first["successful_turns"] == 1
            assert [t["status"] for t in first["chat_turns"]] == ["completed", "failed", "not_attempted", "not_attempted"]
        else:
            assert "session_id" not in first
            assert all(t["status"] == "not_attempted" for t in first["chat_turns"])
        before = list(generations)
        execute(run, serve)
        assert generations == before
        if failure == "timeout":
            record = next(r for r in run.data["http_attempts"] if r["operation"] == "review-JD01" and r["kind"] == "generation")
            assert "raw_response" not in record and Decimal(record["reserved_cost_usd"]) > 0
            trace = benchmark.read_json(run.directory / "requests/review-JD01.json")
            assert trace["failure_kind"] == "timeout"
    finally:
        run.close()


def test_cost_cap_and_unknown_reservation_survive_resume(five):
    run = new_run(five, maximum_cost=.5)
    run.accept_preflight_tokens(32000)
    with pytest.raises(review.ReviewError, match="chi phí"):
        run.consume_http("generation", "too-expensive")
    assert run.data["generation_attempts"] == 0
    run.accept_preflight_tokens(1000)
    run.consume_http("generation", "attempted")
    accounted = run.accounted_cost()
    run.close()
    resumed = new_run(five, maximum_cost=.5)
    try:
        assert resumed.accounted_cost() == accounted
        resumed.accept_preflight_tokens(1000)
        with pytest.raises(review.ReviewError, match="attempted"):
            resumed.consume_http("generation", "attempted")
        with pytest.raises(review.ReviewError, match="chi phí"):
            resumed.consume_http("generation", "next")
    finally:
        resumed.close()


def test_crash_after_success_recovers_review_without_generation(five, monkeypatch):
    run = new_run(five)
    sdk, calls = fake_sdk()
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    original = benchmark.write_review
    def crash(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(benchmark, "write_review", crash)
    try:
        with pytest.raises(KeyboardInterrupt):
            benchmark.run_cases(run, client, run.manifest["cases"])
        assert len(calls) == 1
    finally:
        run.close()
    monkeypatch.setattr(benchmark, "write_review", original)
    run = new_run(five)
    try:
        client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
        benchmark.run_cases(run, client, run.manifest["cases"])
        assert len(calls) == 25  # captured first review recovered without another call
        assert run.data["cases"]["JD01"]["successful_turns"] == 4
    finally:
        run.close()


def test_unknown_crash_attempt_is_skipped_not_regenerated(five):
    run = new_run(five)
    run.consume_http("preflight", "review-JD01")
    run.close()
    run = new_run(five)
    sdk, calls = fake_sdk()
    try:
        client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
        benchmark.run_cases(run, client, run.manifest["cases"])
        assert len(calls) == 20
        assert run.data["cases"]["JD01"]["failure_kind"] == "interrupted_attempt"
    finally:
        run.close()


def test_crash_after_chat_response_before_commit_recovers_without_call(five, monkeypatch):
    run = new_run(five)
    sdk, calls = fake_sdk()
    original = chat.write_session
    def crash(path, record):
        if len(record.messages) == 2:
            raise KeyboardInterrupt()
        return original(path, record)
    monkeypatch.setattr(chat, "write_session", crash)
    client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
    try:
        with pytest.raises(KeyboardInterrupt):
            benchmark.run_cases(run, client, run.manifest["cases"])
        assert len(calls) == 2
        trace = benchmark.read_json(run.directory / "requests/chat-JD01-1.json")
        assert trace["api_status"] == "completed" and "validation_status" not in trace
    finally:
        run.close()
    monkeypatch.setattr(chat, "write_session", original)
    run = new_run(five)
    try:
        client = benchmark.RecordingClient(sdk, run, SimpleNamespace(operation=None, budget_exhausted=False))
        benchmark.run_cases(run, client, run.manifest["cases"])
        assert len(calls) == 25
        assert run.data["cases"]["JD01"]["successful_turns"] == 4
        trace = benchmark.read_json(run.directory / "requests/chat-JD01-1.json")
        assert trace["recovered_offline"] and trace["validation_status"] == "passed"
    finally:
        run.close()


def test_auth_failure_stops_remaining_cases(five):
    run = new_run(five)
    dispatched = []
    def serve(request):
        dispatched.append(request)
        return httpx.Response(401, json={"error": {"code": "invalid_api_key", "type": "authentication_error", "message": "secret"}})
    try:
        client = execute(run, serve)
        assert client.stop_requested and len(dispatched) == 1
        assert run.data["generation_attempts"] == 0
        assert run.data["cases"]["JD05"]["review_status"] == "not_attempted"
        assert "secret" not in run.path.read_text()
    finally:
        run.close()


def test_offline_cli_plan_creates_no_sdk_and_freezes_configuration(five, monkeypatch):
    root, _ = five
    monkeypatch.setattr(benchmark, "ROOT", root)
    monkeypatch.setattr(benchmark.openai, "OpenAI", lambda **kw: pytest.fail("Offline must not create SDK"))
    args = ["--manifest", str(root / "data/academic_benchmark/manifest.json"), "--run-id", "five",
        "--plan-output", "data/plan.json", "--max-generations", "25", "--max-preflights", "25",
        "--max-cost-usd", "6", "--max-retries", "0", "--continue-on-case-error",
        "--review-model", "gpt-5.4", "--review-reasoning-effort", "high", "--review-max-output-tokens", "32768", "--review-timeout", "360",
        "--chat-model", "gpt-5.4-mini", "--chat-reasoning-effort", "medium", "--chat-max-output-tokens", "8192", "--chat-timeout", "180"]
    assert benchmark.main(args) == 0
    plan = benchmark.read_json(root / "data/plan.json")
    assert len(plan["operations"]) == 25
    assert plan["max_http_operations"] == 50
    assert Decimal(plan["planning_uncached_ceiling_usd"]) == Decimal("4.794880")
    assert not (root / "data/academic_benchmark/evaluations/five/run.json").exists()
    assert benchmark.main(args) == 0
    assert benchmark.main(args + ["--chat-timeout", "181"]) == 1


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeout_fails_before_http(timeout):
    with pytest.raises(review.ReviewError, match="timeout"):
        replace(configs()[0], request_timeout=timeout)


def test_general_benchmark_does_not_inherit_comparison_input_cap(five):
    run = new_run(five)
    try:
        run.active_settings = run.chat_settings
        run.accept_preflight_tokens(80000)
        record = run.consume_http("generation", "chat-JD01-1")
        assert Decimal(record["reserved_cost_usd"]) == Decimal("0.096864")
    finally:
        run.close()


def test_cost_guard_includes_flagship_long_context_price():
    ordinary = comparison.estimate_cost("gpt-5.4", 272000, 1000, 100000)
    longer = comparison.estimate_cost("gpt-5.4", 272001, 1000, 100000)
    assert ordinary == (Decimal(172000) * Decimal("2.5") + Decimal(100000) * Decimal(".25") + Decimal(1000) * 15) / 1000000
    assert longer == ((Decimal(172001) * Decimal("2.5") + Decimal(100000) * Decimal(".25")) * 2 + Decimal(1000) * Decimal("22.5")) / 1000000
