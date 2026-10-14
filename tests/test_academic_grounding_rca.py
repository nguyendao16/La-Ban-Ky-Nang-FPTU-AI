"""Isolated RCA contracts and durable physical accounting; all HTTP is mocked."""
import copy
import json
import shutil
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import openai
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.diagnostics import academic_grounding_rca as rca
from research.diagnostics import rca_fixtures as fixtures

b = rca.benchmark


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("Real HTTP forbidden"))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", lambda *a, **k: pytest.fail("Real HTTP forbidden"))


@pytest.fixture(scope="session")
def frozen(tmp_path_factory):
    directory = tmp_path_factory.mktemp("frozen-rca")
    rca.prepare(ROOT, directory)
    return directory


@pytest.fixture
def bundle(frozen, tmp_path):
    directory = tmp_path / "rca"
    shutil.copytree(frozen, directory)
    return directory


def conditions(bundle):
    return b.read_json(bundle / "conditions.json")["conditions"]


def new_run(bundle):
    return rca.DiagnosticRun(ROOT, bundle, rca.check_bundle(ROOT, bundle), rca.settings())


def response_body(payload, parsed, *, incomplete=False):
    return {"id": "resp_mock", "object": "response", "created_at": 1,
        "status": "incomplete" if incomplete else "completed", "model": payload["model"],
        "incomplete_details": {"reason": "max_output_tokens"} if incomplete else None,
        "output": [] if incomplete else [{"type": "message", "id": "msg_mock", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(parsed), "annotations": []}]}],
        "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 100}, "output_tokens_details": {"reasoning_tokens": 20}}}


def execute(run, serve):
    transport = b.BudgetTransport(run, httpx.MockTransport(serve))
    with openai.OpenAI(api_key="offline", max_retries=0, timeout=180,
                      http_client=httpx.Client(transport=transport, timeout=180)) as sdk:
        rca.execute_conditions(run, sdk, transport)


def good_response(payload):
    name = payload["text"]["format"]["name"]
    if name == "EvidenceIdentification":
        # Empty observable selection is schema-valid, not a semantic success.
        return {"selections": []}
    if name == "ClaimLevelResponse":
        return {"claims": [], "reply": "Mock output", "evidence": []}
    return {"reply": "Mock output", "evidence": []}


def test_frozen_matrix_controls_holdouts_and_expected_source_availability(bundle):
    rows = conditions(bundle)
    assert len(rows) == len({r["operation"] for r in rows}) == 32
    assert {r["schema"] for r in rows} == set(rca.SCHEMAS)
    assert {r["operation"] for r in rows if r["family"] == "repeat"} == {"C1-repeat", "C4-repeat", "E2-contaminated-repeat"}
    by_id = {r["operation"]: r for r in rows}
    for sid in ["S1", "S6", "S7", "S8"]:
        first, second = by_id[f"D-{sid}-D1"], by_id[f"D-{sid}-D2"]
        assert first["input"] == second["input"] and first["instructions"] == second["instructions"]
    for name in ["E1-clean", "E2-contaminated"]:
        assert by_id[name]["input"] == by_id[name + "-D2"]["input"]
    assert by_id["C1"]["instructions"] == rca.ACADEMIC_CHAT_INSTRUCTIONS
    assert len({by_id[c]["input"][-1]["content"] for c in ["C1", "C2", "C3", "C4"]}) == 1
    assert by_id["E5-holdout"]["target_claim_ids"] == ["S8-SORT", "S8-HASH"]
    assert by_id["E1-clean"]["target_claim_ids"] == ["S1-CI", "S1-LR", "S5-PCA", "H-HYP"]
    expected = b.read_json(bundle / "expected_evidence.json")["claims"]
    fastapi = next(c for c in expected if c["claim_id"] == "S7-FASTAPI")
    assert fixtures.clo("ADY201m", "CLO5") in fastapi["acceptable_related_sources"]
    assert fixtures.clo("ADY201m", "CLO5") not in fastapi["available_acceptable_sources_by_condition"]["AB-S7"]
    holdout_start = next(i for i, row in enumerate(rows) if row["holdout"])
    assert all(r["holdout"] for r in rows[holdout_start:])
    for row in rows:
        assert "PFP191" not in row["instructions"] and "CSD203" not in row["instructions"]
        assert row["input_sha256"] == b.fingerprint(row["input"])


def test_reorder_repetitions_and_history_intervention_change_only_intended_values(bundle):
    rows = {c["operation"]: c for c in conditions(bundle)}
    baseline = json.loads(rows["C2"]["input"][0]["content"])["student_academic_profile"]
    reordered = json.loads(rows["C2-reversed"]["input"][0]["content"])["student_academic_profile"]
    for course in reordered["courses"]:
        course["clos"].reverse()
    assert reordered == baseline
    assert len(baseline["courses"]) == 15 and sum(len(c["clos"]) for c in baseline["courses"]) == 122
    for op in ["C1", "C4", "E2-contaminated"]:
        assert rows[op]["input"] == rows[op + "-repeat"]["input"]
        assert rows[op]["instructions"] == rows[op + "-repeat"]["instructions"]
        assert rows[op]["schema"] == rows[op + "-repeat"]["schema"]
    histories = b.read_json(bundle / "histories.json")["histories"]
    clean = histories["E1-clean"]["history"]
    dirty = copy.deepcopy(histories["E2-contaminated"]["history"])
    reply = json.loads(dirty[1]["content"])
    reply["reply"] = reply["reply"].replace("MAS291/CLO9:", "MAS291/CLO7:", 1)
    reply["evidence"][0]["clo"] = "CLO7"
    dirty[1]["content"] = json.dumps(reply, ensure_ascii=False)
    assert dirty == clean
    before = copy.deepcopy(rows["D-S1-verified-mapping"]["input"])
    assert json.loads(before.pop(-2)["content"])["externally_verified_mapping"]
    assert before == rows["D-S1-D1"]["input"]


def test_forensic_raw_reconstruction_keeps_historical_input_and_counterexamples(bundle):
    forensic = b.read_json(bundle / "forensic_findings.json")
    assert len(forensic["historical_output_index"]) == 115
    assert len(forensic["primary_cases"]) == len(forensic["successful_controls"]) == 3
    for case in forensic["primary_cases"]:
        assert case["raw_equals_parsed"] and case["canonical_evidence_present_in_actual_input"]
        assert not case["earlier_incorrect_attribution_found_by_manual_review"]
        trace = b.read_json(ROOT / case["artifact"])
        assert case["exact_user_message"] == trace["request"]["input"][-1]["content"]
        assert case["exact_reply"] == trace["structured_output"]["reply"]
    legacy = next(c for c in forensic["representative_cases"] if c["operation"] == "review-JD01-legacy-gpt41")
    assert legacy["actual_input_has_metadata"] is False
    assert any(c["history_before_failed_turn"] == [] for c in forensic["primary_cases"])


def test_quote_sources_two_shapes_and_provenance_not_semantic_support(bundle):
    profile = json.loads(conditions(bundle)[0]["input"][0]["content"])["student_academic_profile"]
    full = b.read_json(ROOT / fixtures.PROFILE)
    ref = fixtures.clo("MAS291", "CLO7")
    quoted = {**ref, "source_excerpt": rca.source_value(profile, ref)}
    raw = {"selections": [{"claim_id": "irrelevant", "claim": "The student built a production system",
                            "relation": "direct", "source_matches": [quoted]}]}
    assert rca.validate_provenance(raw, "identification", profile)
    # Valid quote does not establish this unrelated semantic claim.
    tools = fixtures.metadata("PFP191", "tools")
    second = {"claims": [{"statement": "Course tools list", "sources": [{**tools, "source_excerpt": rca.source_value(full, tools)}]}],
              "reply": "Mock", "evidence": [tools, ref]}
    assert rca.validate_provenance(second, "claim_level", full)


@pytest.mark.parametrize("change", ["empty", "whitespace", "wrong_quote", "wrong_clo", "absent_course", "mixed", "invalid_field", "duplicate"])
def test_invalid_quotes_and_reference_shapes_are_rejected(bundle, change):
    profile = b.read_json(ROOT / fixtures.PROFILE)
    ref = fixtures.clo("MAS291", "CLO7")
    quoted = {**ref, "source_excerpt": rca.source_value(profile, ref)}
    sources = [quoted]
    if change == "empty": quoted["source_excerpt"] = ""
    if change == "whitespace": quoted["source_excerpt"] = " "
    if change == "wrong_quote": quoted["source_excerpt"] = rca.source_value(profile, fixtures.clo("MAS291", "CLO9"))
    if change == "wrong_clo": quoted["clo"] = "CLO999"
    if change == "absent_course": quoted["course_code"] = "ABSENT"
    if change == "mixed": quoted["metadata_field"] = "tools"
    if change == "invalid_field": quoted = {"course_code": "MAS291", "metadata_field": "subject_name", "source_excerpt": "x"}; sources = [quoted]
    if change == "duplicate": sources.append(copy.deepcopy(quoted))
    with pytest.raises((rca.ReviewError, ValueError)):
        rca.validate_provenance({"claims": [{"statement": "Mock", "sources": sources}], "reply": "Mock", "evidence": []}, "claim_level", profile)


def test_empty_metadata_and_duplicate_aggregate_sources_rejected(bundle):
    profile = b.read_json(ROOT / fixtures.PROFILE)
    empty = next(c for c in profile["courses"] if c.get("metadata", {}).get("tools") == "")
    with pytest.raises(rca.ReviewError):
        rca.validate_provenance({"reply": "Mock", "evidence": [fixtures.metadata(empty["course_code"], "tools")]}, "chat", profile)
    ref = fixtures.clo("MAS291", "CLO7")
    with pytest.raises(rca.ReviewError):
        rca.validate_provenance({"reply": "Mock", "evidence": [ref, ref]}, "chat", profile)


def test_real_sdk_frozen_32_requests_schema_timeout_and_no_regeneration(bundle):
    run = new_run(bundle)
    calls = []
    def serve(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload, request.extensions["timeout"]["read"]))
        # Accounting is durable before every dispatch.
        saved = b.read_json(run.path)
        assert len(saved["http_attempts"]) == len(calls)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        assert Decimal(saved["http_attempts"][-1]["reserved_cost_usd"]) > 0
        return httpx.Response(200, json=response_body(payload, good_response(payload)))
    try:
        execute(run, serve)
        assert run.data["generation_attempts"] == run.data["preflight_attempts"] == 32
        assert len(calls) == 64
        for index in range(0, 64, 2):
            preflight, generation = calls[index][1], calls[index + 1][1]
            for key in ["model", "instructions", "input", "text", "reasoning"]:
                assert preflight[key] == generation[key]
            assert generation["max_output_tokens"] == 8192
            assert generation["store"] is False and generation["truncation"] == "disabled"
        for _, payload, timeout in calls:
            assert payload["model"] == rca.MODEL and payload["reasoning"] == {"effort": "medium"}
            assert timeout == 180 and "temperature" not in payload
        assert all(c["status"] == "completed" for c in run.data["conditions"].values())
        for row in conditions(bundle):
            trace = b.read_json(run.directory / "requests" / (row["operation"] + ".json"))
            assert trace["sdk_retries_taken"] == 0
            assert trace["metrics"]["schema_validation"] == "passed"
            assert trace["metrics"]["semantic_grounding"] == "pending_manual_annotation"
            assert trace["metrics"]["quote_provenance_validation"] == ("not_applicable" if row["schema"] == "chat" else "passed")
            assert trace["request"]["input"] == row["input"]  # No output becomes later input.
        usage = b.read_json(run.directory / "usage.json")
        assert usage["unknown_usage_reservation_usd"] == "0"
        assert Decimal(usage["known_cost_usd"]) == 32 * rca.estimate_cost(rca.MODEL, 1000, 100, 100)
        execute(run, lambda req: pytest.fail("Attempted operation regenerated"))
        assert len(calls) == 64
    finally:
        run.close()


@pytest.mark.parametrize("failure", ["timeout", "incomplete", "quote", "parse"])
def test_failures_preserve_raw_bodies_and_continue_independent_conditions(bundle, failure):
    run = new_run(bundle)
    first = conditions(bundle)[0]["operation"]
    attempted = []
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        op = run.data["http_attempts"][-1]["operation"]
        attempted.append(op)
        parsed = good_response(payload)
        if op == first:
            if failure == "timeout": raise httpx.ReadTimeout("mock", request=request)
            if failure == "quote":
                parsed = {"selections": [{"claim_id": "x", "claim": "x", "relation": "direct", "source_matches": [
                    {"course_code": "MAS291", "clo": "CLO7", "source_excerpt": "invented quote"}]}]}
            if failure == "parse": parsed = {"unknown": "invalid contract"}
        return httpx.Response(200, json=response_body(payload, parsed, incomplete=op == first and failure == "incomplete"))
    try:
        execute(run, serve)
        assert len(attempted) == 32 and run.data["conditions"][first]["status"] == "failed"
        assert not (run.directory / "outputs" / (first + ".json")).exists()
        trace = b.read_json(run.directory / "requests" / (first + ".json"))
        assert trace["failure_kind"] == {"timeout": "timeout", "incomplete": "incomplete", "quote": "quote_provenance", "parse": "parsing"}[failure]
        assert trace["metrics"]["semantic_grounding"] == "pending_manual_annotation"
        if failure == "incomplete": assert trace["incomplete_details"] == {"reason": "max_output_tokens"}
        usage = b.read_json(run.directory / "usage.json")
        assert Decimal(usage["unknown_usage_reservation_usd"]) > 0 if failure == "timeout" else Decimal(usage["unknown_usage_reservation_usd"]) == 0
        execute(run, lambda req: pytest.fail("Failed operation retried"))
    finally:
        run.close()


@pytest.mark.parametrize("failure", ["context", "cost", "auth"])
def test_global_context_cost_and_service_errors_stop_run(bundle, failure):
    run = new_run(bundle)
    calls = []
    def serve(request):
        calls.append(request.url.path)
        if failure == "auth": return httpx.Response(401, json={"error": {"type": "invalid_request_error", "code": "invalid_api_key", "message": "mock"}})
        return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 400000 if failure == "context" else 1000})
    if failure == "cost": run.maximum_cost = Decimal(".001")
    try:
        execute(run, serve)
        assert run.data["run_status"] == "stopped"
        assert len(calls) == 1 and run.data["generation_attempts"] == 0
        assert sum(c["status"] == "not_attempted" for c in run.data["conditions"].values()) == 31
    finally:
        run.close()


def test_unknown_attempt_reservation_and_caps_survive_resume(bundle):
    run = new_run(bundle)
    rows = conditions(bundle)
    run.current_condition = rows[0]
    run.consume_http("preflight", rows[0]["operation"])
    run.accept_preflight_tokens(64000)
    run.consume_http("generation", rows[0]["operation"])
    reserved = run.accounted_cost()
    run.close()
    run = new_run(bundle)
    try:
        assert run.accounted_cost() == reserved == rca.estimate_cost(rca.MODEL, 64000, 8192)
        run.current_condition = rows[0]
        with pytest.raises(rca.ReviewError, match="attempted"):
            run.consume_http("preflight", rows[0]["operation"])
        # Crash had no trace: the physical attempt is still never dispatched again.
        seen = []
        def serve(request):
            seen.append(run.data["http_attempts"][-1]["operation"])
            payload = json.loads(request.content)
            if request.url.path.endswith("input_tokens"):
                return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
            return httpx.Response(200, json=response_body(payload, good_response(payload)))
        execute(run, serve)
        assert rows[0]["operation"] not in seen
        assert run.data["conditions"][rows[0]["operation"]]["status"] == "attempted_not_regenerated"
        assert run.data["generation_attempts"] == run.data["preflight_attempts"] == 32
        with pytest.raises(rca.ReviewError, match="preflight"):
            run.consume_http("preflight", run.current_condition["operation"])
        with pytest.raises(rca.ReviewError, match="generation"):
            run.consume_http("generation", run.current_condition["operation"])
    finally:
        run.close()


def test_crash_after_successful_trace_recovers_parsed_output_without_http(bundle, monkeypatch):
    run = new_run(bundle)
    original = rca.freeze_json
    def crash(path, value):
        if path.parent.name == "outputs": raise KeyboardInterrupt()
        return original(path, value)
    monkeypatch.setattr(rca, "freeze_json", crash)
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        return httpx.Response(200, json=response_body(payload, good_response(payload)))
    try:
        with pytest.raises(KeyboardInterrupt): execute(run, serve)
    finally:
        run.close()
    monkeypatch.setattr(rca, "freeze_json", original)
    run = new_run(bundle)
    first = conditions(bundle)[0]["operation"]
    def resume(request):
        assert run.data["http_attempts"][-1]["operation"] != first
        return serve(request)
    try:
        execute(run, resume)
        assert run.data["generation_attempts"] == 32
        assert (run.directory / "outputs" / (first + ".json")).exists()
    finally:
        run.close()


def test_budget_over_three_dollars_and_unknown_operation_are_blocked(bundle):
    run = new_run(bundle)
    try:
        run.current_condition = {"operation": "invented"}
        with pytest.raises(rca.ReviewError, match="matrix"): run.consume_http("preflight", "invented")
        run.current_condition = conditions(bundle)[0]
        run.accept_preflight_tokens(4000000)
        with pytest.raises(rca.ReviewError, match="chi phí"):
            run.consume_http("generation", run.current_condition["operation"])
        assert run.data["generation_attempts"] == 0
        run.accept_preflight_tokens(80000)  # 32k comparison limit must not leak into RCA.
        run.consume_http("generation", run.current_condition["operation"])
    finally:
        run.close()


def test_fingerprint_guards_frozen_artifacts_and_source_copies(bundle, tmp_path):
    copied_root = tmp_path / "source-copy"
    plan = rca.check_bundle(ROOT, bundle)
    for name in plan["sources"]:
        path = copied_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    rca.check_bundle(copied_root, bundle)
    source = copied_root / fixtures.PROFILE
    source.write_text("changed source")
    with pytest.raises(rca.ReviewError, match="source fingerprint"):
        rca.check_bundle(copied_root, bundle)
    (bundle / "histories.json").write_text("{}")
    with pytest.raises(rca.ReviewError, match="artifact changed"):
        rca.check_bundle(ROOT, bundle)


def test_offline_idempotence_and_live_approval_guard_create_no_sdk(bundle, monkeypatch):
    monkeypatch.setattr(openai, "OpenAI", lambda *a, **k: pytest.fail("Offline/unauthorized SDK constructed"))
    old = (bundle / "plan.json").read_bytes()
    assert rca.prepare(ROOT, bundle) == rca.check_bundle(ROOT, bundle)
    assert (bundle / "plan.json").read_bytes() == old
    checked_path = b.checked_path
    monkeypatch.setattr(b, "checked_path", lambda root, value: bundle if value == "test-bundle" else checked_path(root, value))
    assert rca.main(["--directory", "test-bundle", "--check"]) == 0
    assert rca.main(["--directory", "test-bundle", "--live"]) == 1
    assert rca.main(["--directory", "test-bundle", "--live", "--approved-plan-sha256", "wrong"]) == 1


def test_live_settings_must_match_frozen_plan(bundle):
    with pytest.raises(rca.ReviewError, match="settings differ"):
        rca.DiagnosticRun(ROOT, bundle, rca.check_bundle(ROOT, bundle), replace(rca.settings(), reasoning_effort="low"))
