"""Physical HTTP caps, immutable comparison context and complete mocked matrix."""
import copy
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import academic_model_comparison as comparison
import academic_review as review
import evaluate_academic_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Comparison tests cannot reach real HTTP")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(comparison, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-comparison-key")


@pytest.fixture
def project(tmp_path):
    manifest = benchmark.read_json(ROOT / "data/academic_benchmark/manifest.json")
    for relative in [manifest["profile_path"], "data/sample_jd.txt", comparison.CHAT_SEED,
                     *[case["jd_path"] for case in manifest["cases"]]]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    enriched = benchmark.read_json(ROOT / manifest["profile_path"])
    for course in enriched["courses"]:
        course["metadata"] = benchmark.read_json(ROOT / "data/courses" / course["course_code"] / "metadata.json")
    benchmark.atomic_json(tmp_path / "data/enriched.json", enriched)
    return tmp_path, manifest


def arguments(live=False):
    return SimpleNamespace(enriched_profile="data/enriched.json", plan_output="data/plan.json",
                           live=live, run_id="mock-matrix", max_cost_usd=2.5)


def test_prepared_matrix_freezes_history_and_is_offline(project, monkeypatch):
    root, manifest = project
    plan, profiles, messages = comparison.prepare_comparison(root, manifest, "data/enriched.json")
    seed = benchmark.read_json(root / comparison.CHAT_SEED)["request"]["input"]
    assert messages[1:-1] == seed[1:-1]
    assert messages[-1]["content"] == comparison.CHAT_PROBE
    assert len(plan["rows"]) == 12
    assert sum(r["stage"] == "review" for r in plan["rows"]) == 8
    assert Decimal(plan["uncached_cost_ceiling_usd"]) == Decimal("2.081408")
    def blocked(*a, **k):
        raise AssertionError("Offline mode must not create SDK")
    monkeypatch.setattr(comparison.openai, "OpenAI", blocked)
    assert comparison.comparison_main(root, manifest, arguments(), 12) == 0
    assert (root / "data/plan.json").exists()


def test_changed_clo_is_not_a_data_effect_experiment(project):
    root, manifest = project
    enriched = benchmark.read_json(root / "data/enriched.json")
    enriched["courses"][0]["clos"][0]["score"] = 1
    benchmark.atomic_json(root / "data/enriched.json", enriched)
    with pytest.raises(review.ReviewError, match="thay đổi"):
        comparison.prepare_comparison(root, manifest, "data/enriched.json")


def make_run(project, cap=2.5, maximum=12):
    root, manifest = project
    plan, _, _ = comparison.prepare_comparison(root, manifest, "data/enriched.json")
    settings = review.ReviewSettings(api_key="offline", model="gpt-4.1", max_output_tokens=16384)
    return comparison.ComparisonRun(root, manifest, "budget-run", settings, plan, maximum, cap)


def test_physical_request_cost_caps_resume_and_sources(project):
    run = make_run(project, cap=.1)
    try:
        with pytest.raises(review.ReviewError, match="preflight"):
            run.consume_http("generation", "no-preflight")
        with pytest.raises(review.ReviewError, match="32000"):
            run.accept_preflight_tokens(32001)
        run.accept_preflight_tokens(32000)
        with pytest.raises(review.ReviewError, match="chi phí"):
            run.consume_http("generation", "too-expensive")
        assert run.data["generation_attempts"] == 0
        for i in range(12):
            run.consume_http("preflight", str(i))
        with pytest.raises(review.ReviewError, match="12 preflight"):
            run.consume_http("preflight", "extra")
    finally:
        run.close()
    resumed = make_run(project, cap=.1)
    try:
        assert resumed.data["preflight_attempts"] == 12
        path = project[0] / "data/enriched.json"
        path.write_text(path.read_text() + "\n")
        with pytest.raises(review.ReviewError, match="fingerprint"):
            resumed.verify_sources()
    finally:
        resumed.close()


@pytest.mark.parametrize("maximum,cap", [(13, 2.5), (0, 2.5), (12, 2.51), (12, 0), (12, float("nan")), (12, float("inf"))])
def test_unapproved_budget_is_rejected(project, maximum, cap):
    with pytest.raises(review.ReviewError):
        make_run(project, maximum=maximum, cap=cap)


def test_generation_budget_survives_resume(project):
    run = make_run(project, maximum=1)
    run.accept_preflight_tokens(100)
    run.consume_http("generation", "first")
    reserved = run.data["reserved_cost_usd"]
    run.close()
    run = make_run(project, maximum=1)
    try:
        run.accept_preflight_tokens(100)
        assert run.data["reserved_cost_usd"] == reserved
        with pytest.raises(review.ReviewError, match="generation"):
            run.consume_http("generation", "second")
        assert run.data["generation_attempts"] == 1
    finally:
        run.close()


def test_incomplete_keeps_raw_usage_without_semantic_grade(project):
    run = make_run(project)
    try:
        run.settings = review.ReviewSettings(api_key="offline", model="gpt-5.4-mini")
        body = {"model": "gpt-5.4-mini-2026-03-17", "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"}, "output": [],
                "usage": {"input_tokens": 16000, "output_tokens": 16384, "total_tokens": 32384,
                          "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 16384}}}
        trace = {"operation": "review-JD01-enriched-mini-high", "input_tokens": 16000,
                 "raw_response": json.dumps(body), "validation_status": "failed", "latency_seconds": 77}
        run.capture_metrics(trace)
        assert trace["incomplete_details"] == {"reason": "max_output_tokens"}
        assert trace["metrics"]["reasoning_tokens"] == 16384
        assert trace["metrics"]["schema_validation"] == "not_available"
        assert trace["metrics"]["evidence_validation"] == "not_available"
        assert Decimal(trace["metrics"]["estimated_cost_usd"]) > 0
        assert trace["metrics"]["naturalness"] is None
    finally:
        run.close()


def test_non_json_failure_body_is_preserved(project):
    run = make_run(project)
    try:
        trace = {"operation": "failed", "raw_response": "not-json", "validation_status": "failed", "latency_seconds": 1}
        run.capture_metrics(trace)
        assert trace["raw_response"] == "not-json"
        assert trace["raw_body_json_validation"] == "failed"
        assert trace["metrics"]["schema_validation"] == "not_available"
    finally:
        run.close()


def test_full_matrix_with_sdk_and_raw_traces(project, monkeypatch):
    root, manifest = project
    dispatched = []
    def handle(request):
        payload = json.loads(request.content)
        dispatched.append((request.url.path, payload))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        if payload["text"]["format"]["name"] == "AcademicKnowledgeReview":
            parsed = {"review_type": "academic_knowledge_review", "overview": "Mock curriculum", "conclusion": "Mock",
                      "requirement_reviews": [{"jd_requirement": "SQL", "coverage": "covered", "comment": "Mock",
                                               "evidence": [{"course_code": "ADY201m", "clo": "CLO1"}]}]}
        else:
            parsed = {"reply": "Mock course tools", "evidence": [{"course_code": "ADY201m", "metadata_field": "tools"}]}
        return httpx.Response(200, json={"id": "resp_mock", "object": "response", "created_at": 1,
            "status": "completed", "model": payload["model"], "output": [{"type": "message", "id": "msg_mock",
                "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": json.dumps(parsed), "annotations": []}]}],
            "usage": {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200,
                      "input_tokens_details": {"cached_tokens": 500}, "output_tokens_details": {"reasoning_tokens": 10}}})
    constructor = benchmark.BudgetTransport.__init__
    monkeypatch.setattr(benchmark.BudgetTransport, "__init__", lambda self, run: constructor(self, run, httpx.MockTransport(handle)))
    assert comparison.comparison_main(root, manifest, arguments(live=True), 12) == 0
    ledger = benchmark.read_json(root / "data/academic_benchmark/evaluations/mock-matrix/run.json")
    assert ledger["generation_attempts"] == ledger["preflight_attempts"] == 12
    assert len(dispatched) == 24
    assert Decimal(ledger["reserved_cost_usd"]) < Decimal("2.5")
    generations = [body for path, body in dispatched if not path.endswith("input_tokens")]
    for body in generations:
        assert body["store"] is False
        assert ("temperature" in body) == (body["model"] == "gpt-4.1")
    chats = generations[-4:]
    assert all(body["input"] == chats[0]["input"] for body in chats)
    assert all(r["metrics"]["schema_validation"] == "passed" and r["metrics"]["evidence_validation"] == "passed"
               for r in ledger["comparison_results"].values())
    assert all(r["metrics"]["cached_input_tokens"] == 500 for r in ledger["comparison_results"].values())
    before = copy.deepcopy(dispatched)
    assert comparison.comparison_main(root, manifest, arguments(live=True), 12) == 0
    assert dispatched == before  # Resume never regenerates any attempted condition.
