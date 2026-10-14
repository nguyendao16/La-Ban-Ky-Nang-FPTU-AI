"""Offline prototype tests use the real SDK with httpx.MockTransport only."""
import copy
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import openai
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.diagnostics import evidence_bound_response as p
from research.diagnostics import evidence_bound_fixtures as f
from research.diagnostics import evidence_bound_results as results


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    path = tmp_path_factory.mktemp("evidence-bound-frozen")
    p.prepare(ROOT, path)
    return path


@pytest.fixture
def bundle(tmp_path, frozen):
    path = tmp_path / "bundle"
    shutil.copytree(frozen, path)
    return path


@pytest.fixture(scope="module")
def profile():
    return p.b.read_json(ROOT / f.PROFILE)


def rows(bundle):
    return p.b.read_json(bundle / "conditions.json")["conditions"]


def segment(text="Nội dung học thuật", sources=None, kind="academic_claim", jd_excerpt=None):
    return {"kind": kind, "text": text, "academic_sources": [] if sources is None else sources, "jd_excerpt": jd_excerpt}


def quote(profile, course="MAS291", identifier="CLO7", excerpt=None):
    ref = f.clo(course, identifier)
    return {**ref, "source_excerpt": excerpt if excerpt is not None else p.source_value(profile, ref)}


def metadata_quote(profile, course, field="tools", excerpt=None):
    ref = f.metadata(course, field)
    return {**ref, "source_excerpt": excerpt if excerpt is not None else p.source_value(profile, ref)}


def body(payload, parsed, *, status="completed", usage=True):
    return {"id": "resp_mock", "object": "response", "created_at": 1, "status": status, "model": payload["model"],
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
        "output": [{"type": "message", "id": "msg_mock", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(parsed), "annotations": []}]}],
        "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 100}, "output_tokens_details": {"reasoning_tokens": 20}} if usage else None}


def good(payload):
    if payload["text"]["format"]["name"] == "EvidenceBoundResponse":
        return {"segments": [segment("Mock output", kind="general_explanation")]}
    return {"reply": "Mock output", "evidence": []}


def execute(run, serve):
    transport = p.b.BudgetTransport(run, p.TimedInnerTransport(run, httpx.MockTransport(serve)))
    with openai.OpenAI(api_key="offline", max_retries=0, timeout=180,
                      http_client=httpx.Client(transport=transport, timeout=180)) as sdk:
        p.execute_conditions(run, sdk, transport)


def run_for(bundle):
    return p.PrototypeRun(ROOT, bundle, p.check_bundle(ROOT, bundle), p.settings())


def test_adapter_preserves_text_paragraphs_source_order_and_repeated_excerpts(profile):
    first = quote(profile, excerpt="confidence intervals")
    second = quote(profile, excerpt="population parameters")
    tools = metadata_quote(profile, "MAD101")
    texts = ["Bạn học confidence intervals.  ", "- Ngữ cảnh công cụ\n- Cần giữ giới hạn.", "Một nguồn có thể dùng nhiều lần."]
    raw = {"segments": [segment(texts[0], [first, second]), segment(texts[1], [tools]), segment(texts[2], [first])]}
    before = copy.deepcopy(raw)
    result = p.adapt_response(raw, profile, "JD")
    assert result.reply == "\n\n".join(texts)
    assert [r.model_dump() for r in result.evidence] == [f.clo("MAS291", "CLO7"), f.metadata("MAD101", "tools")]
    assert raw == before
    assert set(result.model_dump()) == {"reply", "evidence"}


def test_metadata_only_short_quote_and_newlines_are_supported(profile):
    raw = {"segments": [segment("Ngữ cảnh công cụ, không xác nhận cá nhân", [metadata_quote(profile, "MAD101", excerpt="C")]),
                        segment("Các công cụ trong môn", [metadata_quote(profile, "ADY201m", excerpt="Jupyter Notebooks\n- JupyterLab")])]}
    assert p.adapt_response(raw, profile, "JD")


def test_gate_is_provenance_not_entailment_and_grade_validator(profile):
    raw = {"segments": [segment("CLO9 dạy confidence intervals; điểm 0, basic.", [quote(profile, identifier="CLO9")])]}
    assert p.provenance_gate(raw, profile, "JD")["status"] == "passed"
    assert p.adapt_response(raw, profile, "JD").reply == raw["segments"][0]["text"]
    hidden = {"segments": [segment("Bạn đã dùng FastAPI ở trường.", kind="general_explanation")]}
    assert p.provenance_gate(hidden, profile, "JD")["status"] == "passed"
    # Both are semantic errors to be manually assessed, not a regex 'fix'.


@pytest.mark.parametrize("mutation", ["wrong_clo_quote", "absent_course", "absent_clo", "other_course_quote", "blank_quote", "empty_tools", "wrong_metadata_quote", "missing_source", "wrong_jd", "missing_jd", "blank_text", "general_sources", "general_jd"])
def test_gate_rejections_preserve_original_output(profile, mutation):
    raw = {"segments": [segment(sources=[quote(profile)])]}
    s = raw["segments"][0]
    if mutation == "wrong_clo_quote": s["academic_sources"][0]["clo"] = "CLO9"
    if mutation == "absent_course": s["academic_sources"][0]["course_code"] = "ABSENT"
    if mutation == "absent_clo": s["academic_sources"][0]["clo"] = "CLO999"
    if mutation == "other_course_quote": s["academic_sources"][0]["source_excerpt"] = p.source_value(profile, f.clo("CSI106", "CLO3"))
    if mutation == "blank_quote": s["academic_sources"][0]["source_excerpt"] = " "
    if mutation == "empty_tools": s["academic_sources"] = [{"course_code": "MAE101", "metadata_field": "tools", "source_excerpt": "x"}]
    if mutation == "wrong_metadata_quote": s["academic_sources"] = [metadata_quote(profile, "MAD101", excerpt="JupyterLab")]
    if mutation == "missing_source": s["academic_sources"] = []
    if mutation in {"wrong_jd", "missing_jd"}:
        s.update(kind="jd_requirement", academic_sources=[], jd_excerpt="Another JD" if mutation == "wrong_jd" else None)
    if mutation == "blank_text": s["text"] = " \n "
    if mutation == "general_sources": s["kind"] = "general_explanation"
    if mutation == "general_jd": s.update(kind="general_explanation", academic_sources=[], jd_excerpt="JD")
    before = copy.deepcopy(raw)
    assert p.provenance_gate(raw, profile, "JD")["status"] == "rejected"
    with pytest.raises(p.ReviewError): p.adapt_response(raw, profile, "JD")
    assert raw == before


@pytest.mark.parametrize("mutation", ["mixed", "invalid_metadata", "extra_reply", "empty_segments", "empty_text", "bad_kind", "extra_source_field"])
def test_schema_rejects_malformed_contract(profile, mutation):
    raw = {"segments": [segment(sources=[quote(profile)])]}
    if mutation == "mixed": raw["segments"][0]["academic_sources"][0]["metadata_field"] = "tools"
    if mutation == "invalid_metadata": raw["segments"][0]["academic_sources"] = [{"course_code": "MAD101", "metadata_field": "subject_code", "source_excerpt": "MAD101"}]
    if mutation == "extra_reply": raw["reply"] = "independent text"
    if mutation == "empty_segments": raw["segments"] = []
    if mutation == "empty_text": raw["segments"][0]["text"] = ""
    if mutation == "bad_kind": raw["segments"][0]["kind"] = "anything"
    if mutation == "extra_source_field": raw["segments"][0]["academic_sources"][0]["score"] = 1
    with pytest.raises(ValueError): p.EvidenceBoundResponse.model_validate(raw)


def test_absence_related_and_jd_segments_and_production_duplicate_contract(profile):
    raw = {"segments": [segment("Chưa xác nhận tên công nghệ", kind="not_evidenced"),
        segment("Có bối cảnh công cụ liên quan", [metadata_quote(profile, "MAD101")], kind="not_evidenced"),
        segment("JD ưu tiên Python OR R", kind="jd_requirement", jd_excerpt="Preferred: Python OR R")]}
    assert p.adapt_response(raw, profile, "Preferred: Python OR R")
    with pytest.raises(p.ReviewError):
        p.validate_chat_response({"reply": "Mock", "evidence": [f.clo("MAS291", "CLO7"), f.clo("MAS291", "CLO7")]}, p.validate_profile(profile))


def test_gate_uses_only_actually_provided_profile(profile):
    restricted = {**copy.deepcopy(profile), "courses": [c for c in profile["courses"] if c["course_code"] == "CSI106"]}
    assert p.provenance_gate({"segments": [segment(sources=[quote(profile)])]}, restricted, "JD")["status"] == "rejected"


def test_frozen_matrix_controls_scopes_histories_repeats_and_new_holdouts(bundle, profile):
    conditions = rows(bundle)
    p.check_bundle(ROOT, bundle, deep=True)
    assert len(conditions) == len({r["operation"] for r in conditions}) == 32
    assert [sum(r["phase"] == phase for r in conditions) for phase in ["primary", "scope", "repeat"]] == [16, 8, 8]
    assert {r["scenario_id"] for r in conditions if r["holdout"]} == {"S4", "S8"}
    by_id = {r["operation"]: r for r in conditions}
    scenarios = {r["scenario_id"]: r for r in p.b.read_json(bundle / "scenarios.json")["scenarios"]}
    assert scenarios["S5"]["history"] == p.b.read_json(ROOT / f.RCA / "histories.json")["histories"]["E2-contaminated"]["history"]
    assert "AIL303m/CLO3" in scenarios["S8"]["history"][1]["content"]
    assert scenarios["S8"]["summary_scope"] == "comprehensive_jd"
    for row in conditions:
        assert json.loads(row["input"][0]["content"])["student_academic_profile"] == profile
        review = json.loads(row["input"][2]["content"])["initial_academic_review"]
        assert review == p.b.read_json(ROOT / f.REVIEWS / f"{row['jd']}.json")
        assert row["asked_atomic_denominator"] == len(row["asked_atomic_units"])
        assert "MAD101" not in row["instructions"]  # no holdout mappings in prompt
        if row["scope"] == "S1":
            original = by_id[f"primary-{row['scenario_id']}-{row['arm']}-S0"]
            assert row["input"] == original["input"]
            assert row["instructions"] == original["instructions"] + "\n" + p.SUMMARY_SCOPE
        if row["repeat_of"]:
            assert row["input"] == by_id[row["repeat_of"]]["input"]
    assert by_id["primary-S1-A-S0"]["instructions"] == p.ACADEMIC_CHAT_INSTRUCTIONS
    assert "Do not duplicate references." not in p.bound_instructions()


def test_real_sdk_32_pairs_accounting_before_http_settings_latency_and_resume(bundle):
    run = run_for(bundle)
    calls = []
    def serve(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload, request.extensions["timeout"]["read"]))
        saved = p.b.read_json(run.path)
        assert len(saved["http_attempts"]) == len(calls)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 80000})
        assert Decimal(saved["http_attempts"][-1]["reserved_cost_usd"]) == p.estimate_cost(p.MODEL, 80000, 8192)
        return httpx.Response(200, json=body(payload, good(payload)))
    try:
        execute(run, serve)
        assert run.data["generation_attempts"] == run.data["preflight_attempts"] == 32
        assert len(calls) == 64
        for first, second in zip(calls[::2], calls[1::2]):
            for key in ["model", "instructions", "input", "text", "reasoning"]: assert first[1][key] == second[1][key]
            assert second[1]["max_output_tokens"] == 8192
            assert second[1]["store"] is False and second[1]["truncation"] == "disabled"
        for _, payload, timeout in calls:
            assert payload["model"] == p.MODEL and payload["reasoning"] == {"effort": "medium"}
            assert timeout == 180 and "temperature" not in payload
        assert all(c["status"] == "completed" for c in run.data["conditions"].values())
        for row in rows(bundle):
            trace = p.b.read_json(run.directory / "requests" / f"{row['operation']}.json")
            assert trace["sdk_retries_taken"] == 0
            assert set(trace["latency"]) == {"preflight_seconds", "generation_http_seconds", "parsing_seconds", "validation_adapter_seconds", "total_seconds"}
            assert all(v >= 0 for v in trace["latency"].values())
            assert trace["request"]["input"] == row["input"]
            assert trace["metrics"]["semantic_support"] == "pending_manual_annotation"
        usage = p.b.read_json(run.directory / "usage.json")
        assert Decimal(usage["known_cost_usd"]) == 32 * p.estimate_cost(p.MODEL, 1000, 100, 100)
        assert usage["unknown_usage_reservation_usd"] == "0"
        execute(run, lambda req: pytest.fail("Resume dispatched attempted operation"))
        assert run.data["generation_attempts"] == 32
    finally: run.close()


@pytest.mark.parametrize("failure", ["timeout", "incomplete", "parse", "gate", "reference", "refusal", "nonjson"])
def test_failures_preserve_raw_and_do_not_feed_history_or_regenerate(bundle, failure):
    run = run_for(bundle)
    failing = rows(bundle)[1 if failure == "gate" else 0]["operation"]
    calls = []
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        op = run.data["http_attempts"][-1]["operation"]
        calls.append(op)
        parsed = good(payload)
        if op == failing:
            if failure == "timeout": raise httpx.ReadTimeout("mock", request=request)
            if failure == "nonjson": return httpx.Response(200, text="malformed body", headers={"Content-Type": "application/json"})
            if failure == "parse": parsed = {"extra": "malformed"}
            if failure == "gate": parsed = {"segments": [segment(sources=[{"course_code": "MAS291", "clo": "CLO9", "source_excerpt": "confidence intervals"}])]}
            if failure == "reference": parsed = {"reply": "Mock", "evidence": [{"course_code": "ABSENT", "clo": "CLO1"}]}
        response = body(payload, parsed, status="incomplete" if op == failing and failure == "incomplete" else "completed")
        if op == failing and failure == "refusal": response["output"][0]["content"] = [{"type": "refusal", "refusal": "mock refusal"}]
        return httpx.Response(200, json=response)
    try:
        execute(run, serve)
        assert len(calls) == 32
        assert run.data["conditions"][failing]["status"] == ("withheld" if failure == "gate" else "failed")
        assert not (run.directory / "outputs" / f"{failing}.json").exists()
        trace = p.b.read_json(run.directory / "requests" / f"{failing}.json")
        if failure != "timeout": assert trace["raw_response"]
        if failure == "gate":
            assert (run.directory / "parsed" / f"{failing}.json").exists()
            assert p.b.read_json(run.directory / "raw_views" / f"{failing}.json")["publication"] == "analysis_only"
            assert trace["failure_kind"] == "provenance_gate"
        if failure == "incomplete": assert trace["incomplete_details"] == {"reason": "max_output_tokens"}
        if failure == "refusal": assert trace["failure_kind"] == "refusal"
        usage = p.b.read_json(run.directory / "usage.json")
        assert (Decimal(usage["unknown_usage_reservation_usd"]) > 0) == (failure in {"timeout", "nonjson"})
        execute(run, lambda req: pytest.fail("Failed operation regenerated"))
    finally: run.close()


def test_path_a_has_no_added_provenance_gate(bundle):
    row = next(r for r in rows(bundle) if r["arm"] == "A")
    parsed = p.AcademicChatResponse(reply="CSI106/CLO4 xác nhận data types/bit patterns.", evidence=[f.clo("CSI106", "CLO4")])
    result, gate = p.evaluate_parsed(row, parsed, bundle / "analysis")
    assert result and gate["status"] == "not_applicable"
    assert not (bundle / "analysis/gates").exists()


@pytest.mark.parametrize("crash", ["preflight", "generation", "after_raw"])
def test_crash_resume_keeps_counters_reservations_and_recovers_durable_raw(bundle, crash):
    run = run_for(bundle)
    first = rows(bundle)[0]["operation"]
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            if crash == "preflight": raise KeyboardInterrupt()
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        if crash == "generation": raise KeyboardInterrupt()
        return httpx.Response(200, json=body(payload, good(payload)))
    original = p.evaluate_parsed
    if crash == "after_raw":
        def interrupted(*args): raise KeyboardInterrupt()
        p.evaluate_parsed = interrupted
    try:
        with pytest.raises(KeyboardInterrupt): execute(run, serve)
        counters = (run.data["preflight_attempts"], run.data["generation_attempts"])
    finally:
        p.evaluate_parsed = original
        run.close()
    resumed = run_for(bundle)
    seen = []
    def finish(request):
        payload = json.loads(request.content)
        assert resumed.data["http_attempts"][-1]["operation"] != first
        seen.append(request.url.path)
        if request.url.path.endswith("input_tokens"): return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        return httpx.Response(200, json=body(payload, good(payload)))
    try:
        execute(resumed, finish)
        assert counters[0] == 1 and len(seen) == 62
        assert resumed.data["generation_attempts"] == 31 + counters[1]
        assert resumed.data["conditions"][first]["status"] == ("completed" if crash == "after_raw" else "attempted_not_regenerated")
        if crash == "generation": assert Decimal(results.usage_summary(resumed.data)["unknown_usage_reservation_usd"]) > 0
    finally: resumed.close()


def test_cost_cap_unknown_usage_persists_across_resume(bundle):
    run = run_for(bundle)
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"): return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 200000})
        return httpx.Response(200, json=body(payload, good(payload), usage=False))
    try:
        execute(run, serve)
        assert run.data["generation_attempts"] == 16 and run.data["preflight_attempts"] == 16
        assert run.accounted_cost() == 16 * p.estimate_cost(p.MODEL, 200000, 8192) <= Decimal("3")
        assert sum(s["status"] == "not_attempted" for s in run.data["conditions"].values()) == 16
        before = run.accounted_cost()
    finally: run.close()
    resumed = run_for(bundle)
    try:
        execute(resumed, serve)
        assert resumed.data["generation_attempts"] == 16 and resumed.accounted_cost() == before
    finally: resumed.close()


def test_http_caps_and_duplicate_operation_guards(bundle):
    run = run_for(bundle)
    try:
        for row in rows(bundle):
            run.current_condition = row
            run.consume_http("preflight", row["operation"])
        assert run.data["preflight_attempts"] == 32
        with pytest.raises(p.ReviewError): run.consume_http("preflight", rows(bundle)[-1]["operation"])
        run.current_condition = rows(bundle)[0]
        run.active_input_tokens = 1000
        run.consume_http("generation", run.current_condition["operation"])
        with pytest.raises(p.ReviewError): run.consume_http("generation", run.current_condition["operation"])
        with pytest.raises(p.ReviewError): run.consume_http("generation", "unplanned")
        for row in rows(bundle)[1:]:
            run.current_condition = row
            run.consume_http("generation", row["operation"])
        assert run.data["generation_attempts"] == 32 and len(run.data["http_attempts"]) == 64
        with pytest.raises(p.ReviewError): run.consume_http("generation", rows(bundle)[-1]["operation"])
    finally: run.close()


@pytest.mark.parametrize("tokens, generations", [(400000 - 8192, 32), (400000 - 8192 + 1, 0)])
def test_context_boundary_keeps_full_input(bundle, tokens, generations):
    run = run_for(bundle)
    def serve(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("input_tokens"): return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": tokens})
        return httpx.Response(200, json=body(payload, good(payload)))
    try:
        execute(run, serve)
        assert run.data["generation_attempts"] == generations
        if not generations: assert run.data["preflight_attempts"] == 1 and run.data["run_status"] == "stopped"
    finally: run.close()


def test_auth_global_failure_stops_without_retry(bundle):
    run = run_for(bundle)
    calls = []
    def serve(request):
        calls.append(request.url.path)
        return httpx.Response(401, json={"error": {"type": "invalid_request_error", "code": "invalid_api_key", "message": "mock"}})
    try:
        execute(run, serve)
        assert len(calls) == 1 and run.data["run_status"] == "stopped"
        assert sum(s["status"] == "not_attempted" for s in run.data["conditions"].values()) == 31
    finally: run.close()


@pytest.mark.parametrize("phase", ["preflight", "generation"])
def test_inflight_fingerprint_failure_stops_publication_and_preserves_raw(bundle, phase):
    run = run_for(bundle)
    calls = []
    def serve(request):
        payload = json.loads(request.content)
        kind = "preflight" if request.url.path.endswith("input_tokens") else "generation"
        calls.append(kind)
        if kind == phase:
            target = bundle / "expected_evidence.json"
            target.write_text(target.read_text() + " ")
        if kind == "preflight": return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1000})
        return httpx.Response(200, json=body(payload, good(payload)))
    try:
        execute(run, serve)
        assert run.data["run_status"] == "stopped"
        assert len(calls) == (1 if phase == "preflight" else 2)
        assert not (run.directory / "outputs").exists()
        assert "fingerprint" in run.data["stop_reason"] or "artifact" in run.data["stop_reason"]
        assert sum(s["status"] == "not_attempted" for s in run.data["conditions"].values()) == 31
        if phase == "generation":
            assert run.data["http_attempts"][-1]["raw_response"]
    finally: run.close()


def test_fingerprint_guard_frozen_artifacts_and_unknown_resume_request(bundle):
    plan = p.check_bundle(ROOT, bundle)
    path = bundle / "histories.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(p.ReviewError, match="artifact changed"): p.check_bundle(ROOT, bundle)
    path.write_text(path.read_text()[:-1])
    run = run_for(bundle)
    try:
        row = rows(bundle)[0]
        run.current_condition = row
        run.consume_http("preflight", row["operation"])
        run.active_input_tokens = 1000
        record = run.consume_http("generation", row["operation"])
        record["raw_response"] = json.dumps(body({"model": p.MODEL}, {"reply": "Original", "evidence": []}))
        run.save()
        p.b.atomic_json(run.directory / "requests" / f"{row['operation']}.json", {"request": {"model": "other"}})
        assert p.recover_condition(run, row)["status"] == "attempted_not_regenerated"
        assert not (run.directory / "outputs").exists()
    finally: run.close()


def test_offline_summary_has_null_semantic_results_and_no_http(bundle, monkeypatch):
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("Offline constructed API client"))
    p.check_bundle(ROOT, bundle, deep=True)
    summary = results.summarize(bundle)
    assert summary["status"] == "awaiting_new_paid_approval"
    assert summary["usage"]["generation_http_attempts"] == summary["usage"]["preflight_http_attempts"] == 0
    assert all(r["raw_p0"] is None and r["answered_atomic_claims"] is None for r in summary["matrix"])
    assert not (bundle / "live").exists()
    assert p.prepare(ROOT, bundle)["operations"] == p.check_bundle(ROOT, bundle)["operations"]


def test_cli_offline_and_unapproved_live_cannot_construct_sdk(bundle, monkeypatch):
    monkeypatch.setattr(p, "ROOT", bundle.parent)
    monkeypatch.setattr(p, "DIRECTORY", "bundle")
    monkeypatch.setattr(p, "check_bundle", lambda *args, **kw: p.b.read_json(bundle / "plan.json"))
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("API client constructed"))
    assert p.main(["--verify", "--directory", "bundle"]) == 0
    assert p.main(["--live", "--directory", "bundle"]) == 2
    assert p.main(["--prepare", "--directory", "historical"]) == 2


def test_ledger_tamper_and_changed_settings_cannot_reset_budget(bundle):
    run = run_for(bundle)
    run.close()
    stored = p.b.read_json(bundle / "live/run.json")
    stored["generation_attempts"] = 1
    p.b.atomic_json(bundle / "live/run.json", stored)
    with pytest.raises(p.ReviewError, match="counters"): run_for(bundle)
    with pytest.raises(p.ReviewError, match="settings"):
        p.PrototypeRun(ROOT, bundle, p.check_bundle(ROOT, bundle), p.ReviewSettings(api_key="offline", stage="chat", model=p.MODEL, reasoning_effort="low", max_output_tokens=8192, request_timeout=180))
