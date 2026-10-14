"""The approved 12-generation experiment, reusing benchmark tracing and budgets."""
from __future__ import annotations

import copy
import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import openai
from dotenv import load_dotenv

if __package__:
    from . import evaluate_academic_benchmark as benchmark
    from .academic_review import (AcademicKnowledgeReview, ReviewError, ReviewSettings, generate_review,
                                  load_jd, load_profile, request_structured_response, validate_profile, validate_review)
    from .academic_chat import AcademicChatResponse, validate_chat_response
    from .academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
    from .openai_model_config import MODEL_CAPABILITIES
else:
    import evaluate_academic_benchmark as benchmark
    from academic_review import (AcademicKnowledgeReview, ReviewError, ReviewSettings, generate_review,
                                load_jd, load_profile, request_structured_response, validate_profile, validate_review)
    from academic_chat import AcademicChatResponse, validate_chat_response
    from academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
    from openai_model_config import MODEL_CAPABILITIES


MAX_INPUT_TOKENS = 32000
MAX_PREFLIGHTS = 12
CHAT_SEED = "data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-5.json"
CHAT_PROBE = """Bạn kiểm tra và sửa phần nhận xét SQL/API trong lịch sử, rồi tóm tắt bằng chứng đúng giúp mình: CLO nào hỗ trợ từng nội dung, điểm và achievement riêng của chúng ra sao? Đừng suy Python/SQL thành đã dùng FastAPI, SQLAlchemy hoặc PostgreSQL.
Mình cũng muốn hiểu bằng chứng từ danh sách công cụ: Jupyter/JupyterLab, Git/GitHub, RStudio và Watson Studio ở ADY201m, Microsoft SQL Server ở DBI202, Visual Studio Code/Google Colab ở PFP191, và 'PyCharm or Matlab' ở CPV301. Những mục này xác nhận nội dung của môn hay xác nhận mình đã sử dụng thành thạo từng công cụ? Giải thích cả giới hạn của yêu cầu 'use at least one', các lựa chọn 'or', và việc danh sách có textbook/Internet. Giữ phân biệt kết quả học thuật với kinh nghiệm nghề nghiệp."""


def estimate_cost(model, input_tokens, output_tokens, cached_tokens=0):
    cap = MODEL_CAPABILITIES[model]
    if not 0 <= cached_tokens <= input_tokens:
        raise ReviewError("Cached token usage không hợp lệ")
    long_context = model in {"gpt-5.4", "gpt-5.4-2026-03-05"} and input_tokens > 272000
    input_multiplier = Decimal(2 if long_context else 1)
    output_multiplier = Decimal("1.5" if long_context else "1")
    return ((Decimal(input_tokens - cached_tokens) * Decimal(str(cap.input_price))
             + Decimal(cached_tokens) * Decimal(str(cap.cached_input_price))) * input_multiplier
            + Decimal(output_tokens) * Decimal(str(cap.output_price)) * output_multiplier) / Decimal(1000000)


def comparison_rows():
    rows = []
    for case in ["JD01", "JD05"]:
        for name, profile, model, effort in [
            ("legacy-gpt41", "legacy", "gpt-4.1", None),
            ("enriched-gpt41", "enriched", "gpt-4.1", None),
            ("enriched-mini-high", "enriched", "gpt-5.4-mini", "high"),
            ("enriched-gpt54-high", "enriched", "gpt-5.4", "high"),
        ]:
            rows.append({"operation": f"review-{case}-{name}", "case_id": case, "stage": "review",
                         "profile": profile, "model": model, "reasoning_effort": effort, "max_output_tokens": 16384})
    for name, model, effort in [("gpt41", "gpt-4.1", None), ("mini-low", "gpt-5.4-mini", "low"),
                                ("mini-medium", "gpt-5.4-mini", "medium"), ("gpt54-medium", "gpt-5.4", "medium")]:
        rows.append({"operation": f"chat-JD11-{name}", "case_id": "JD11", "stage": "chat",
                     "profile": "enriched", "model": model, "reasoning_effort": effort, "max_output_tokens": 8192})
    return rows


def prepare_comparison(root, manifest, enriched_path):
    root = Path(root).resolve()
    paths = {"legacy": benchmark.checked_path(root, manifest["profile_path"]),
             "enriched": benchmark.checked_path(root, enriched_path),
             "chat_seed": benchmark.checked_path(root, CHAT_SEED)}
    profiles = {name: load_profile(path) for name, path in paths.items() if name != "chat_seed"}
    projected = copy.deepcopy(profiles["enriched"])
    for course in projected["courses"]:
        course.pop("metadata", None)
    if projected != profiles["legacy"]:
        raise ReviewError("Enriched profile thay đổi môn/CLO/description/score/achievement legacy")
    seed = benchmark.read_json(paths["chat_seed"])
    messages = copy.deepcopy(seed["request"]["input"])
    cases = {case["case_id"]: case for case in manifest["cases"]}
    if json.loads(messages[0]["content"])["student_academic_profile"] != profiles["legacy"]:
        raise ReviewError("Frozen chat seed không khớp legacy profile")
    if json.loads(messages[1]["content"])["current_job_description"] != load_jd(benchmark.checked_path(root, cases["JD11"]["jd_path"])):
        raise ReviewError("Frozen chat JD không khớp manifest")
    validate_review(json.loads(messages[2]["content"])["initial_academic_review"], profiles["legacy"])
    for message in messages[3:-1]:
        if message["role"] == "assistant":
            validate_chat_response(json.loads(message["content"]), validate_profile(profiles["legacy"]))
    messages[0]["content"] = json.dumps({"student_academic_profile": profiles["enriched"]}, ensure_ascii=False, allow_nan=False, indent=2)
    messages[-1] = {"role": "user", "content": CHAT_PROBE}
    rows = comparison_rows()
    # Validate all model combinations offline before any network dispatch.
    for row in rows:
        ReviewSettings(api_key="offline-plan", model=row["model"], stage=row["stage"],
                       reasoning_effort=row["reasoning_effort"], max_output_tokens=row["max_output_tokens"])
    plan = {"version": 1, "origin": "offline_plan", "rows": rows,
            "max_generation_http_attempts": 12, "max_preflight_http_attempts": MAX_PREFLIGHTS,
            "max_input_tokens_per_request": MAX_INPUT_TOKENS, "max_cost_usd": 2.5,
            "uncached_cost_ceiling_usd": str(sum(estimate_cost(r["model"], MAX_INPUT_TOKENS, r["max_output_tokens"]) for r in rows)),
            "sources": {name: {"path": str(path.relative_to(root)), "sha256": benchmark.digest(path.read_bytes())} for name, path in paths.items()},
            "chat_context_sha256": benchmark.fingerprint(messages), "chat_probe": CHAT_PROBE,
            "pricing_checked_at": "2026-10-13", "pricing_sources": [f"https://developers.openai.com/api/docs/models/{m}" for m in ["gpt-4.1", "gpt-5.4-mini", "gpt-5.4"]]}
    return plan, profiles, messages


class ComparisonRun(benchmark.EvaluationRun):
    def __init__(self, root, manifest, run_id, settings, plan, maximum=12, maximum_cost=2.5):
        if type(maximum) is not int or not 1 <= maximum <= 12:
            raise ReviewError("Comparison generation budget phải trong khoảng 1–12")
        try:
            cap = Decimal(str(maximum_cost))
        except Exception as exc:
            raise ReviewError("Comparison cost budget không hợp lệ") from exc
        if not cap.is_finite() or not 0 < cap <= Decimal("2.5"):
            raise ReviewError("Comparison cost budget phải lớn hơn 0 và không vượt 2.50 USD")
        super().__init__(root, manifest, run_id, settings, maximum)
        self.maximum_cost = cap
        self.plan = plan
        self.active_input_tokens = None
        frozen = {"plan": plan, "maximum_cost_usd": str(cap)}
        try:
            if "comparison" in self.data and self.data["comparison"] != frozen:
                raise ReviewError("Không resume comparison với ma trận/nguồn/budget khác")
            self.data["comparison"] = frozen
            self.data.setdefault("reserved_cost_usd", "0")
            self.data.setdefault("comparison_results", {})
            self.save()
        except BaseException:
            self.close()
            raise

    def verify_sources(self):
        super().verify_sources()
        for source in self.plan["sources"].values():
            if benchmark.digest(benchmark.checked_path(self.root, source["path"]).read_bytes()) != source["sha256"]:
                raise ReviewError("Comparison source fingerprint thay đổi; tạo run mới")

    def accept_preflight_tokens(self, tokens):
        if type(tokens) is not int or not 0 <= tokens <= MAX_INPUT_TOKENS:
            raise ReviewError("Comparison input vượt 32000 tokens hoặc count không hợp lệ; không cắt context")
        self.active_input_tokens = tokens

    def consume_http(self, kind, operation):
        reservation = None
        if kind == "preflight" and self.data["preflight_attempts"] >= MAX_PREFLIGHTS:
            raise ReviewError("Đã hết budget 12 preflight HTTP")
        if kind == "generation":
            if self.active_input_tokens is None:
                raise ReviewError("Generation phải có preflight hợp lệ")
            reservation = estimate_cost(self.settings.model, self.active_input_tokens, self.settings.max_output_tokens)
            if Decimal(self.data["reserved_cost_usd"]) + reservation > self.maximum_cost:
                raise ReviewError("Đã hết budget chi phí comparison; không gửi generation")
        record = super().consume_http(kind, operation)
        if reservation is not None:
            self.data["reserved_cost_usd"] = str(Decimal(self.data["reserved_cost_usd"]) + reservation)
            record["reserved_cost_usd"] = str(reservation)
            self.save()
        return record

    def capture_metrics(self, current):
        capture_request_metrics(self, current, self.settings)


def capture_request_metrics(run, current, settings):
    raw = current.get("raw_response")
    if raw is None:
        raw = next((r.get("raw_response") for r in reversed(run.data["http_attempts"])
                    if r["operation"] == current["operation"] and r["kind"] == "generation"), None)
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except (ValueError, TypeError):
        payload = {}
        current["raw_body_json_validation"] = "failed"
    if raw:
        current["raw_response"] = raw
    usage = payload.get("usage") or current.get("usage") or {}
    current.update(response_model=payload.get("model", current.get("response_model")), api_status=payload.get("status", current.get("api_status")),
                   incomplete_details=payload.get("incomplete_details"), usage=usage or None)
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    cost = estimate_cost(settings.model, input_tokens, output_tokens, cached) if input_tokens is not None and output_tokens is not None else None
    schema = "not_available"
    if current.get("structured_output") is not None:
        response_model = AcademicKnowledgeReview if settings.stage == "review" else AcademicChatResponse
        try:
            response_model.model_validate(current["structured_output"])
            schema = "passed"
        except ValueError:
            schema = "failed"
    current["metrics"] = {
        "requested_model": settings.model, "resolved_model": payload.get("model"),
        "stage": settings.stage, "reasoning_effort": settings.reasoning_effort,
        "temperature_sent": settings.temperature is not None, "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens, "preflight_input_tokens": current.get("input_tokens"),
        "input_tokens": input_tokens, "cached_input_tokens": cached, "output_tokens": output_tokens,
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
        "total_tokens": usage.get("total_tokens"), "estimated_cost_usd": str(cost) if cost is not None else None,
        "latency_seconds": current["latency_seconds"], "schema_validation": schema,
        "evidence_validation": current["validation_status"] if schema == "passed" else "not_available",
        "semantic_grounding": "pending_manual_review", "naturalness": None, "completeness": None,
    }


def comparison_main(root, manifest, args, maximum):
    plan, profiles, chat_messages = prepare_comparison(root, manifest, args.enriched_profile)
    plan_path = benchmark.checked_path(root, args.plan_output)
    if plan_path.exists() and benchmark.read_json(plan_path) != plan:
        raise ReviewError("Không ghi đè comparison plan khác; chọn --plan-output mới")
    if not plan_path.exists():
        benchmark.atomic_json(plan_path, plan)
    print(f"Comparison: 12 generations, 12 preflights, <=2.50 USD; uncached ceiling={plan['uncached_cost_ceiling_usd']} USD", flush=True)
    if not args.live:
        print(f"Offline comparison plan: {plan_path}; không gọi API.")
        return 0
    load_dotenv(Path(root) / ".env", override=False)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    baseline = ReviewSettings(api_key=api_key, model="gpt-4.1", max_output_tokens=16384)
    run = ComparisonRun(root, manifest, args.run_id or uuid4().hex, baseline, plan, maximum, args.max_cost_usd)
    try:
        transport = benchmark.BudgetTransport(run)
        with openai.OpenAI(api_key=api_key, timeout=180.0, max_retries=0,
                           http_client=httpx.Client(transport=transport, timeout=180.0)) as sdk:
            client = benchmark.RecordingClient(sdk, run, transport)
            cases = {case["case_id"]: case for case in manifest["cases"]}
            for row in plan["rows"]:
                operation = row["operation"]
                if (run.directory / "requests" / f"{operation}.json").exists():
                    continue  # An attempted condition is never regenerated, including after crashes.
                run.settings = ReviewSettings(api_key=api_key, model=row["model"], stage=row["stage"],
                                              reasoning_effort=row["reasoning_effort"], max_output_tokens=row["max_output_tokens"])
                run.active_input_tokens = None
                if row["stage"] == "review":
                    profile = profiles[row["profile"]]
                    jd = load_jd(benchmark.checked_path(root, cases[row["case_id"]]["jd_path"]))
                    result = benchmark.invoke(client, operation, lambda: generate_review(profile, jd, run.settings, client=client))
                else:
                    def reply():
                        raw = request_structured_response(ACADEMIC_CHAT_INSTRUCTIONS, copy.deepcopy(chat_messages),
                                                          AcademicChatResponse, run.settings, client=client, operation_label="comparison chat")
                        return validate_chat_response(raw, validate_profile(profiles["enriched"]))
                    result = benchmark.invoke(client, operation, reply)
                run.data["comparison_results"][operation] = {"status": "passed" if result is not None else "failed",
                    "metrics": client.current["metrics"], "artifact": f"requests/{operation}.json"}
                run.save()
                if client.stop_requested:
                    break
        run.data["completed_at"] = benchmark.now()
        complete = len(run.data["comparison_results"]) == len(plan["rows"])
        passed = complete and all(r["status"] == "passed" for r in run.data["comparison_results"].values())
        run.data["comparison_status"] = "completed" if passed else "completed_with_failures" if complete else "interrupted"
        run.save()
        print(f"Generation HTTP={run.data['generation_attempts']}; preflight HTTP={run.data['preflight_attempts']}; reserved USD={run.data['reserved_cost_usd']}")
        return 0 if passed else 1
    finally:
        run.close()
