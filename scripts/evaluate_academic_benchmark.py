"""Benchmark local có provenance; API có phí chỉ chạy với --live, không có LLM judge."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from decimal import Decimal
from datetime import datetime
from time import perf_counter
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import openai

if __package__:
    from .academic_chat import AcademicChatResponse, AcademicChatSession, AssistantMessage, UserMessage, validate_chat_response, write_session
    from .academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
    from .academic_review import (
        ROOT, MAX_OUTPUT_TOKENS, AcademicKnowledgeReview, ReviewError, generate_review,
        load_jd, load_profile, load_settings, request_structured_response,
        structured_schema_format, unique_json_fields, validate_profile, validate_review, write_review,
    )
    from .academic_review_prompt import ACADEMIC_REVIEW_INSTRUCTIONS
else:
    from academic_chat import AcademicChatResponse, AcademicChatSession, AssistantMessage, UserMessage, validate_chat_response, write_session
    from academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
    from academic_review import (
        ROOT, MAX_OUTPUT_TOKENS, AcademicKnowledgeReview, ReviewError, generate_review,
        load_jd, load_profile, load_settings, request_structured_response,
        structured_schema_format, unique_json_fields, validate_profile, validate_review, write_review,
    )
    from academic_review_prompt import ACADEMIC_REVIEW_INSTRUCTIONS


BENCHMARK = ROOT / "data/academic_benchmark"


def now():
    return datetime.now().astimezone().isoformat()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_json_fields)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"Không đọc được benchmark JSON: {path}") from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checked_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ReviewError("Benchmark path không được thoát khỏi repository")
    return path


def load_manifest(root=ROOT, path=None):
    root = Path(root)
    path = Path(path) if path else root / "data/academic_benchmark/manifest.json"
    manifest = read_json(path)
    if manifest.get("version") != 1 or not 1 <= len(manifest.get("cases", [])) <= 15:
        raise ReviewError("Manifest version/case count không hợp lệ")
    profile_path = checked_path(root, manifest["profile_path"])
    load_profile(profile_path)
    if digest(profile_path.read_bytes()) != manifest["profile_sha256"]:
        raise ReviewError("Profile khác fingerprint benchmark")
    identifiers = set()
    for case in manifest["cases"]:
        identifier = case["case_id"]
        if not re.fullmatch(r"JD(?:0[0-9]|1[0-4])", identifier) or identifier in identifiers:
            raise ReviewError("Case ID không hợp lệ hoặc bị trùng")
        identifiers.add(identifier)
        jd = checked_path(root, case["jd_path"])
        load_jd(jd)
        if digest(jd.read_bytes()) != case["jd_sha256"]:
            raise ReviewError(f"JD fingerprint thay đổi: {identifier}")
        required = ("company", "role", "category", "checked_at", "source_type", "retrieval_method", "snapshot_type", "source_limitations")
        if any(not case.get(name) for name in required) or len(case.get("messages", [])) < 3:
            raise ReviewError(f"Thiếu provenance/messages: {identifier}")
        if identifier != "JD00" and not case.get("actual_source_url"):
            raise ReviewError("JD nguồn thực phải có URL")
        if identifier == "JD00" and jd.read_bytes() != (root / "data/sample_jd.txt").read_bytes():
            raise ReviewError("JD00 phải giữ nguyên baseline")
    return manifest


class EvaluationRun:
    """One immutable run context and a durable budget; main holds its POSIX lock."""

    def __init__(self, root, manifest, run_id, settings, maximum=80, chat_settings=None,
                 *, maximum_preflights=None, maximum_cost=None, max_retries=2,
                 continue_on_case_error=False):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id):
            raise ReviewError("Run ID chỉ gồm chữ, số, _ hoặc -; không có path")
        if type(maximum) is not int or not 1 <= maximum <= 80:
            raise ReviewError("Budget generation phải là số nguyên 1–80")
        if maximum_preflights is not None and (type(maximum_preflights) is not int or not 1 <= maximum_preflights <= 80):
            raise ReviewError("Budget preflight phải là số nguyên 1–80")
        self.maximum_cost = Decimal(str(maximum_cost)) if maximum_cost is not None else None
        self.cost_guard_enabled = maximum_cost is not None
        if self.maximum_cost is not None and (not self.maximum_cost.is_finite() or self.maximum_cost <= 0):
            raise ReviewError("Cost budget phải hữu hạn và lớn hơn 0")
        if type(max_retries) is not int or not 0 <= max_retries <= 2:
            raise ReviewError("SDK retries phải trong khoảng 0–2")
        self.maximum_preflights = maximum_preflights
        self.continue_on_case_error = continue_on_case_error
        self.active_settings = settings
        self.active_input_tokens = None
        self.root = Path(root).resolve()
        self.base = self.root / "data/academic_benchmark"
        self.run_id, self.manifest, self.settings = run_id, manifest, settings
        self.chat_settings = settings if chat_settings is None else chat_settings
        self.directory = self.base / "evaluations" / run_id
        if self.directory.is_symlink() or self.directory.parent.is_symlink():
            raise ReviewError("Không dùng symlink làm thư mục run")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "run.json"
        context = {
            "manifest_sha256": fingerprint(manifest), "profile_sha256": manifest["profile_sha256"],
            "model": settings.model, "context_window": settings.context_window,
            "max_output_tokens": settings.max_output_tokens, "baseline_temperature": settings.temperature,
            "reasoning_effort": settings.reasoning_effort,
            "chat_settings": {"model": self.chat_settings.model, "reasoning_effort": self.chat_settings.reasoning_effort,
                              "max_output_tokens": self.chat_settings.max_output_tokens,
                              "temperature": self.chat_settings.temperature, "context_window": self.chat_settings.context_window},
            "review_prompt_sha256": digest(ACADEMIC_REVIEW_INSTRUCTIONS.encode()),
            "chat_prompt_sha256": digest(ACADEMIC_CHAT_INSTRUCTIONS.encode()),
            "review_schema_sha256": fingerprint(structured_schema_format(AcademicKnowledgeReview)),
            "chat_schema_sha256": fingerprint(structured_schema_format(AcademicChatResponse)),
        }
        # Do not change the frozen context of historical runs with default options.
        if settings.request_timeout is not None or self.chat_settings.request_timeout is not None:
            context["stage_timeouts"] = {"review": settings.timeout, "chat": self.chat_settings.timeout}
        if maximum_preflights is not None or maximum_cost is not None or max_retries != 2 or continue_on_case_error:
            context["execution_policy"] = {"max_preflights": maximum_preflights,
                "max_cost_usd": str(self.maximum_cost) if self.maximum_cost is not None else None,
                "max_retries": max_retries, "continue_on_case_error": continue_on_case_error}
        self.lock = (self.directory / "run.lock").open("a")
        import fcntl
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists():
                self.data = read_json(self.path)
                if self.data["context"] != context or self.data["max_generations"] != maximum:
                    raise ReviewError("Không resume run với sources/prompt/schema/model/budget khác")
            else:
                self.data = {
                    "version": 1, "run_id": run_id, "origin": "live", "started_at": now(),
                    "context": context, "max_generations": maximum,
                    "generation_attempts": 0, "preflight_attempts": 0,
                    "http_attempts": [], "cases": {}, "pilot": {}, "temperature_pairs": {},
                    "semantic_status": "not_automatically_assessed",
                }
                self.save()
        except BaseException:
            self.lock.close()
            raise

    def save(self):
        atomic_json(self.path, self.data)

    def close(self):
        self.lock.close()

    def verify_sources(self):
        if digest(checked_path(self.root, self.manifest["profile_path"]).read_bytes()) != self.manifest["profile_sha256"]:
            raise ReviewError("Profile thay đổi trong run")
        for case in self.manifest["cases"]:
            if digest(checked_path(self.root, case["jd_path"]).read_bytes()) != case["jd_sha256"]:
                raise ReviewError(f"JD thay đổi trong run: {case['case_id']}")

    def consume_http(self, kind, operation):
        # Persist before network dispatch: crashes may overcount, never overspend.
        if kind == "generation" and self.data["generation_attempts"] >= self.data["max_generations"]:
            raise ReviewError("Đã hết budget generation; không gửi thêm request")
        if kind == "preflight" and self.maximum_preflights is not None and self.data["preflight_attempts"] >= self.maximum_preflights:
            raise ReviewError("Đã hết budget preflight; không gửi thêm request")
        if self.cost_guard_enabled and any(r["kind"] == kind and r["operation"] == operation for r in self.data["http_attempts"]):
            raise ReviewError("Operation đã attempted; không gửi lại request")
        reservation = None
        if kind == "generation" and self.cost_guard_enabled:
            if self.active_input_tokens is None:
                raise ReviewError("Generation phải có preflight hợp lệ")
            reservation = comparison_helpers().estimate_cost(self.active_settings.model, self.active_input_tokens,
                                                             self.active_settings.max_output_tokens)
            if self.accounted_cost() + reservation > self.maximum_cost:
                raise ReviewError("Đã hết budget chi phí; không gửi generation")
        field = "generation_attempts" if kind == "generation" else "preflight_attempts"
        self.data[field] += 1
        record = {"kind": kind, "operation": operation, "started_at": now(), "number": self.data[field]}
        if reservation is not None:
            record.update(reserved_cost_usd=str(reservation), requested_model=self.active_settings.model)
            self.data["reserved_cost_usd"] = str(Decimal(self.data.get("reserved_cost_usd", "0")) + reservation)
        self.data["http_attempts"].append(record)
        self.save()
        return record

    def accept_preflight_tokens(self, tokens):
        if type(tokens) is not int or tokens < 0:
            raise ReviewError("Preflight token count không hợp lệ")
        self.active_input_tokens = tokens

    def accounted_cost(self):
        total = Decimal("0")
        for record in self.data["http_attempts"]:
            if record["kind"] != "generation":
                continue
            cost = None
            try:
                usage = json.loads(record.get("raw_response", "{}" )).get("usage") or {}
                if "input_tokens" in usage and "output_tokens" in usage:
                    cost = comparison_helpers().estimate_cost(record["requested_model"], usage["input_tokens"],
                        usage["output_tokens"], (usage.get("input_tokens_details") or {}).get("cached_tokens", 0))
            except (ValueError, TypeError, KeyError):
                pass
            total += cost if cost is not None else Decimal(record.get("reserved_cost_usd", "0"))
        return total

    def capture_metrics(self, current):
        comparison_helpers().capture_request_metrics(self, current, self.active_settings)


def comparison_helpers():
    if __package__:
        from . import academic_model_comparison
    else:
        import academic_model_comparison
    return academic_model_comparison


class BudgetTransport(httpx.BaseTransport):
    """Count actual HTTP dispatch attempts, including SDK retries, not just parse()."""

    def __init__(self, run, inner=None):
        self.run, self.inner = run, inner if inner is not None else httpx.HTTPTransport()
        self.operation = "unassigned"
        self.budget_exhausted = False

    def handle_request(self, request):
        path = request.url.path.rstrip("/")
        kind = "generation" if request.method == "POST" and path.endswith("/responses") else "preflight" if request.method == "POST" and path.endswith("/responses/input_tokens") else None
        if kind is None:
            raise ReviewError("Benchmark không gửi endpoint ngoài Responses/count")
        try:
            record = self.run.consume_http(kind, self.operation)
        except ReviewError:
            self.budget_exhausted = True
            raise
        try:
            response = self.inner.handle_request(request)
            # Preserve API bodies for failures, including SDK parse errors/refusals.
            response.read()
            record["status_code"] = response.status_code
            if response.status_code < 400:
                record["raw_response"] = response.text
            else:
                # Authentication error messages can echo key fragments. Preserve
                # error codes, never API error messages/headers or credentials.
                try:
                    error = response.json().get("error", {})
                    record["api_error"] = {key: error.get(key) for key in ("type", "code")}
                except (ValueError, AttributeError):
                    record["api_error"] = {"type": "non_json_error"}
            return response
        except Exception as exc:
            record["transport_error_type"] = type(exc).__name__
            raise
        finally:
            self.run.save()

    def close(self):
        self.inner.close()


class RecordingClient:
    """Injected observer of existing SDK calls, with raw bodies saved before parsing."""

    def __init__(self, sdk, run, transport):
        self.sdk, self.run, self.transport = sdk, run, transport
        self.responses = SimpleNamespace(parse=self.parse, input_tokens=SimpleNamespace(count=self.count))
        self.current = None
        self.stop_requested = False

    def begin(self, operation, settings=None):
        self.run.verify_sources()
        self.run.active_settings = self.run.settings if settings is None else settings
        self.run.active_input_tokens = None
        self.transport.operation = operation
        self.current = {"operation": operation, "origin": "live", "started_at": now(), "preflight_calls": 0, "generation_calls": 0}
        self.started_clock = perf_counter()
        self.trace_path = self.run.directory / "requests" / f"{operation}.json"
        if self.trace_path.exists():
            raise ReviewError("Không ghi đè request artifact đã có; chọn case/phase chưa chạy")

    def flush(self):
        atomic_json(self.trace_path, self.current)

    def count(self, **kwargs):
        self.current["preflight_calls"] += 1
        self.flush()
        result = self.sdk.responses.input_tokens.count(**kwargs)
        self.current["input_tokens"] = result.input_tokens
        self.current["preflight_request"] = copy.deepcopy(kwargs)
        self.flush()
        if hasattr(self.run, "accept_preflight_tokens"):
            self.run.accept_preflight_tokens(result.input_tokens)
        return result

    def parse(self, **kwargs):
        self.current["generation_calls"] += 1
        request = dict(kwargs)
        request["response_schema"] = structured_schema_format(request.pop("text_format"))
        self.current["request"] = copy.deepcopy(request)
        self.current["context_sha256"] = fingerprint({k: v for k, v in request.items() if k != "temperature"})
        self.flush()
        raw = self.sdk.responses.with_raw_response.parse(**kwargs)
        self.current["raw_response"] = raw.text
        self.current["sdk_retries_taken"] = raw.retries_taken
        self.flush()
        response = raw.parse()
        parsed = response.output_parsed
        self.current.update(
            response_model=response.model, api_status=response.status,
            usage=response.usage.model_dump() if response.usage else None,
            structured_output=parsed.model_dump() if hasattr(parsed, "model_dump") else parsed,
        )
        self.flush()
        return response

    def finish(self, error=None):
        self.run.verify_sources()
        self.current["validation_status"] = "failed" if error else "passed"
        self.current["completed_at"] = now()
        if error:
            self.current["error"] = "Đã hết budget generation" if self.transport.budget_exhausted else str(error)
            self.stop_requested = self.transport.budget_exhausted or isinstance(error, OSError) or isinstance(error.__cause__, openai.APIError)
            cause = error.__cause__
            if self.run.continue_on_case_error and not self.transport.budget_exhausted:
                # A timeout is local to this attempted case; connectivity/auth/quota
                # failures make subsequent requests unavailable without intervention.
                self.stop_requested = isinstance(error, OSError) or (isinstance(cause, openai.APIError)
                    and not isinstance(cause, (openai.APITimeoutError, openai.InternalServerError)))
            self.current["failure_kind"] = classify_failure(error, self.current, self.transport)
            if self.stop_requested:
                self.run.data["stop_reason"] = self.current["error"]
                self.run.save()
        self.current["latency_seconds"] = round(perf_counter() - self.started_clock, 3)
        if hasattr(self.run, "capture_metrics"):
            self.run.capture_metrics(self.current)
        self.flush()


def classify_failure(error, trace, transport):
    if transport.budget_exhausted:
        return "budget"
    if isinstance(error.__cause__, openai.APITimeoutError):
        return "timeout"
    if trace.get("api_status") == "incomplete" or "incomplete" in str(error):
        return "incomplete"
    if isinstance(error.__cause__, openai.APIError):
        return "api"
    if "schema" in str(error) or "phân tích" in str(error):
        return "parsing"
    if "evidence" in str(error).lower() or "Requirement" in str(error):
        return "reference_validation"
    return "validation_or_local_error"


def invoke(client, operation, function, *, settings=None):
    client.begin(operation, settings)
    try:
        result = function()
    except (ReviewError, OSError, ValueError) as exc:
        client.finish(exc)
        print(f"{operation}: failed ({type(exc).__name__})", flush=True)
        return None
    client.finish()
    print(f"{operation}: validated", flush=True)
    return result


def review_path(run, identifier):
    return checked_path(run.base, f"initial_reviews/{run.run_id}/{identifier}.json")


def verify_review_mapping(run, case, state):
    path = review_path(run, case["case_id"])
    if state.get("jd_sha256") != case["jd_sha256"] or state.get("review_sha256") != digest(path.read_bytes()):
        raise ReviewError("Review không khớp JD/hash đã ghi cho case")
    validate_review(read_json(path), load_profile(checked_path(run.root, run.manifest["profile_path"])))
    return path


def save_conversation(run, case, state, session):
    # Session's atomic stored history is authoritative after an interruption.
    turns = []
    history = session.history
    for index in range(0, len(history), 2):
        user, assistant = history[index:index + 2]
        operation = f"chat-{case['case_id']}-{index // 2 + 1}"
        trace = read_json(run.directory / "requests" / f"{operation}.json")
        result = {"reply": assistant["content"], "evidence": assistant["evidence"]}
        if trace.get("structured_output") != result:
            raise ReviewError("Stored history không khớp raw structured output")
        turns.append({"turn": index // 2 + 1, "user": user["content"], "response": result,
                      "request_artifact": str((run.directory / "requests" / f"{operation}.json").relative_to(run.root))})
    atomic_json(checked_path(run.base, f"conversations/{run.run_id}/{case['case_id']}.json"), {
        "origin": "live", "case_id": case["case_id"], "session_id": session.session_id,
        "profile_sha256": run.manifest["profile_sha256"], "jd_sha256": case["jd_sha256"],
        "review_sha256": state["review_sha256"], "turns": turns,
    })
    state["successful_turns"] = session.turn_count
    run.save()


def attempted(run, operation):
    return (run.directory / "requests" / f"{operation}.json").exists() or any(
        record["operation"] == operation for record in run.data["http_attempts"])


def recover_output(run, operation, settings, messages, response_model, profile):
    """Recover a captured success locally; an uncertain attempt is never retried."""
    path = run.directory / "requests" / f"{operation}.json"
    if not path.exists():
        return None
    trace = read_json(path)
    request = trace.get("request", {})
    instructions = ACADEMIC_REVIEW_INSTRUCTIONS if response_model is AcademicKnowledgeReview else ACADEMIC_CHAT_INSTRUCTIONS
    expected = {"input": messages, "instructions": instructions, "model": settings.model,
                "max_output_tokens": settings.max_output_tokens, "store": False, "truncation": "disabled",
                "response_schema": structured_schema_format(response_model), **settings.reasoning_options}
    if trace.get("api_status") != "completed" or trace.get("validation_status") == "failed":
        return None
    if any(request.get(key) != value for key, value in expected.items()):
        raise ReviewError("Captured output không khớp context/model/schema của run")
    if request.get("temperature") != settings.temperature or request.get("timeout", settings.timeout) != settings.timeout:
        raise ReviewError("Captured output không khớp temperature/timeout")
    raw = trace.get("structured_output")
    if raw is None:
        return None
    try:
        result = validate_review(raw, profile) if response_model is AcademicKnowledgeReview else validate_chat_response(raw, validate_profile(profile))
    except ReviewError:
        return None
    if trace.get("validation_status") != "passed":
        trace.update(validation_status="passed", recovered_offline=True, completed_at=now())
        trace.setdefault("latency_seconds", None)
        run.active_settings = settings
        run.capture_metrics(trace)
        atomic_json(path, trace)
    return result


def mark_failed_case(run, state, stage, turn=None, kind=None):
    state["failed"] = f"{stage}_generation_or_validation"
    state["failure_kind"] = kind or "interrupted_attempt"
    if turn is not None:
        state["failed_turn"] = turn
    run.save()


def run_cases(run, client, cases, *, deep=False):
    profile_path = checked_path(run.root, run.manifest["profile_path"])
    run.verify_sources()
    for case in cases:
        identifier = case["case_id"]
        state = run.data["cases"].setdefault(identifier, {"jd_sha256": case["jd_sha256"]})
        if state.get("failed"):
            continue
        path = review_path(run, identifier)
        if not state.get("review_sha256"):
            if deep:
                raise ReviewError("Chạy benchmark cơ bản trước deep phase")
            if path.exists():
                # Recover a completed atomic review only if it matches the captured generation.
                trace = read_json(run.directory / "requests" / f"review-{identifier}.json")
                review = validate_review(read_json(path), load_profile(profile_path))
                if trace.get("structured_output") != review.model_dump():
                    raise ReviewError("Review artifact không có provenance đúng")
            else:
                operation = f"review-{identifier}"
                profile = load_profile(profile_path)
                jd = load_jd(checked_path(run.root, case["jd_path"]))
                messages = [
                    {"role": "user", "content": json.dumps({"student_academic_profile": profile}, ensure_ascii=False, allow_nan=False, indent=2)},
                    {"role": "user", "content": json.dumps({"job_description": jd}, ensure_ascii=False)},
                ]
                if attempted(run, operation):
                    result = recover_output(run, operation, run.settings, messages, AcademicKnowledgeReview, profile)
                else:
                    result = invoke(client, operation, lambda: generate_review(profile, jd, run.settings, client=client))
                if result is None:
                    mark_failed_case(run, state, "review", kind=(client.current or {}).get("failure_kind"))
                    if client.stop_requested:
                        return
                    continue
                write_review(path, result)
            state["review_sha256"] = digest(path.read_bytes())
            run.save()
        path = verify_review_mapping(run, case, state)
        options = {"resume": state["session_id"]} if state.get("session_id") else {"persist": True}
        with AcademicChatSession.from_files(
            profile_path, checked_path(run.root, case["jd_path"]), path,
            settings=run.chat_settings, client=client,
            session_dir=run.base / "conversations" / run.run_id / "sessions", **options,
        ) as session:
            state["session_id"] = session.session_id
            run.save()
            messages = case["messages"] + (case["deep_messages"] if deep else [])
            for item in messages[session.turn_count:]:
                operation = f"chat-{identifier}-{session.turn_count + 1}"
                if attempted(run, operation):
                    input_messages = copy.deepcopy(session._context_messages)
                    for previous in session.history:
                        content = previous["content"] if previous["role"] == "user" else json.dumps(
                            {"reply": previous["content"], "evidence": previous["evidence"]}, ensure_ascii=False)
                        input_messages.append({"role": previous["role"], "content": content})
                    input_messages.append({"role": "user", "content": item["user"]})
                    result = recover_output(run, operation, run.chat_settings, input_messages,
                                            AcademicChatResponse, load_profile(profile_path))
                    if result is not None:
                        prospective = session._messages + [UserMessage(role="user", content=item["user"]),
                            AssistantMessage(role="assistant", content=result.reply, evidence=result.evidence)]
                        write_session(session._session_path, session._record(prospective))
                        session._messages = prospective
                else:
                    result = invoke(client, operation, lambda: session.send(item["user"]), settings=run.chat_settings)
                if result is None:
                    mark_failed_case(run, state, "chat", session.turn_count + 1,
                                     (client.current or {}).get("failure_kind"))
                    break
                save_conversation(run, case, state, session)
            save_conversation(run, case, state, session)
        if client.stop_requested:
            return


def run_temperature(run, client, cases):
    profile = validate_profile(load_profile(checked_path(run.root, run.manifest["profile_path"])))
    for case in cases:
        identifier = case["case_id"]
        if not case["temperature_pair"] or identifier in run.data["temperature_pairs"]:
            continue
        state = run.data["cases"].get(identifier, {})
        if state.get("successful_turns", 0) < 3:
            continue
        verify_review_mapping(run, case, state)
        baseline_path = run.directory / "requests" / f"chat-{identifier}-3.json"
        baseline = read_json(baseline_path)
        request = baseline["request"]
        if baseline["validation_status"] != "passed" or request["temperature"] != 0 or request["instructions"] != ACADEMIC_CHAT_INSTRUCTIONS:
            raise ReviewError("A/B baseline không phải context/prompt hợp lệ ở temperature 0")
        settings = replace(run.chat_settings, temperature=0.3)
        def generate():
            raw = request_structured_response(request["instructions"], copy.deepcopy(request["input"]), AcademicChatResponse, settings, client=client, operation_label="A/B chat")
            return validate_chat_response(raw, profile)
        operation = f"temperature-{identifier}-0_3"
        result = invoke(client, operation, generate)
        pair = {"baseline_artifact": str(baseline_path.relative_to(run.root)),
                "candidate_artifact": str((run.directory / "requests" / f"{operation}.json").relative_to(run.root)),
                "status": "generation_failed" if result is None else "comparable",
                "manual_evaluation": None}
        if result is not None:
            if client.current["context_sha256"] != baseline["context_sha256"] or client.current["response_model"] != baseline["response_model"]:
                pair["status"] = "incomparable_context_or_resolved_model"
        run.data["temperature_pairs"][identifier] = pair
        run.save()
        if client.stop_requested:
            return


def run_pilot(run, client):
    artifact = read_json(run.root / "data/academic_chat_evaluation/conversational_style.examples.live.json")
    cv, sql = artifact["cases"]
    pilots = [
        ("SQL_ATTRIBUTION", sql, 2, "Bạn kiểm tra lại lời giải thích trước: DAP391m/CLO7 có thực sự ghi SQL/database access không? Tóm tắt bằng chứng đúng giúp mình."),
        ("CV_METHODS", cv, 6, "Bạn tóm tắt phần toán đã nói, kiểm tra CLO nào thực sự hỗ trợ PCA, SVM và hồi quy tuyến tính nhé."),
        ("SQL_ACHIEVEMENT", sql, None, "DBI202/CLO6 đạt basic có nghĩa môn chỉ dạy SQL cơ bản và SQL của mình chỉ basic không?"),
        ("CV_FRAMEWORKS", cv, None, "Mình đã học Object Detection. Với JD này, kiến thức nào nên kiểm tra hoặc cân nhắc bổ sung nếu chưa tự học? Tách giúp mình phần kinh nghiệm production."),
    ]
    for name, source, seed_turn, question in pilots:
        if name in run.data["pilot"]:
            continue
        paths = {key: checked_path(run.root, value["path"]) for key, value in source["sources"].items()}
        for key, path in paths.items():
            if digest(path.read_bytes()) != source["sources"][key]["sha256"]:
                raise ReviewError("Pilot historical sources đã thay đổi")
        profile = load_profile(paths["profile"])
        review = validate_review(read_json(paths["review"]), profile)
        messages = [
            {"role": "user", "content": json.dumps({"student_academic_profile": profile}, ensure_ascii=False, indent=2)},
            {"role": "user", "content": json.dumps({"current_job_description": load_jd(paths["jd"])}, ensure_ascii=False)},
            {"role": "user", "content": json.dumps({"initial_academic_review": review.model_dump()}, ensure_ascii=False)},
        ]
        if seed_turn:
            turn = source["turns"][seed_turn - 1]
            validate_chat_response(turn["response"], validate_profile(profile))
            messages += [{"role": "user", "content": turn["user"]},
                         {"role": "assistant", "content": json.dumps(turn["response"], ensure_ascii=False)}]
        messages.append({"role": "user", "content": question})
        def generate():
            raw = request_structured_response(ACADEMIC_CHAT_INSTRUCTIONS, messages, AcademicChatResponse, run.chat_settings, client=client, operation_label="pilot chat")
            return validate_chat_response(raw, validate_profile(profile))
        result = invoke(client, f"pilot-{name}", generate)
        run.data["pilot"][name] = {"status": "validated" if result else "failed",
                                  "seed_origin": "historical_live" if seed_turn else None,
                                  "seed_artifact": "data/academic_chat_evaluation/conversational_style.examples.live.json",
                                  "seed_case": source["case"], "seed_turn": seed_turn}
        run.save()
        if client.stop_requested:
            return


def prepare_benchmark_plan(manifest, cases, settings, chat_settings, args, root=ROOT):
    operations = []
    for case in cases:
        operations.append({"operation": f"review-{case['case_id']}", "stage": "review", "case_id": case["case_id"]})
        operations.extend({"operation": f"chat-{case['case_id']}-{i}", "stage": "chat", "case_id": case["case_id"],
                           "question": item["user"]} for i, item in enumerate(case["messages"], 1))
    stage_settings = {}
    for stage, config, assumption in [("review", settings, 32000), ("chat", chat_settings, 80000)]:
        stage_settings[stage] = {"model": config.model, "reasoning_effort": config.reasoning_effort,
            "max_output_tokens": config.max_output_tokens, "timeout_seconds": config.timeout,
            "context_window": config.context_window, "temperature": config.temperature,
            "planning_input_tokens": assumption}
    ceiling = sum(comparison_helpers().estimate_cost(stage_settings[row["stage"]]["model"],
        stage_settings[row["stage"]]["planning_input_tokens"], stage_settings[row["stage"]]["max_output_tokens"]) for row in operations)
    if len(operations) > args.max_generations or (args.max_preflights is not None and len(operations) > args.max_preflights):
        raise ReviewError("Planned operations vượt generation/preflight cap")
    if args.max_cost_usd is not None and ceiling > Decimal(str(args.max_cost_usd)):
        raise ReviewError("Planning cost ceiling vượt budget chi phí")
    for directory in ["initial_reviews", "conversations"]:
        if args.run_id and (Path(root) / "data/academic_benchmark" / directory / args.run_id).exists():
            if not (Path(root) / "data/academic_benchmark/evaluations" / args.run_id / "run.json").exists():
                raise ReviewError("Run output đã tồn tại mà không có ledger; không ghi đè")
    return {"version": 1, "origin": "offline_plan", "run_id": args.run_id,
        "manifest_sha256": fingerprint(manifest), "profile_sha256": manifest["profile_sha256"],
        "case_ids": [c["case_id"] for c in cases], "stages": stage_settings, "operations": operations,
        "max_generations": args.max_generations, "max_preflights": args.max_preflights,
        "max_http_operations": args.max_generations + args.max_preflights if args.max_preflights is not None else None,
        "max_cost_usd": args.max_cost_usd, "max_retries": args.max_retries,
        "continue_on_case_error": args.continue_on_case_error,
        "planning_uncached_ceiling_usd": str(ceiling), "input_assumptions_are_not_truncation_limits": True,
        "jd_sources": [{"case_id": c["case_id"], "path": c["jd_path"], "sha256": c["jd_sha256"]} for c in cases],
        "review_prompt_sha256": digest(ACADEMIC_REVIEW_INSTRUCTIONS.encode()),
        "chat_prompt_sha256": digest(ACADEMIC_CHAT_INSTRUCTIONS.encode()),
        "review_schema_sha256": fingerprint(structured_schema_format(AcademicKnowledgeReview)),
        "chat_schema_sha256": fingerprint(structured_schema_format(AcademicChatResponse)),
        "pricing_sources": ["https://developers.openai.com/api/docs/models/gpt-5.4",
                            "https://developers.openai.com/api/docs/models/gpt-5.4-mini"]}


def record_case_statuses(run, cases):
    for case in cases:
        state = run.data["cases"].setdefault(case["case_id"], {"jd_sha256": case["jd_sha256"]})
        state["review_status"] = "completed" if state.get("review_sha256") else "failed" if state.get("failed") else "not_attempted"
        state["chat_turns"] = []
        for turn in range(1, len(case["messages"]) + 1):
            status = "completed" if turn <= state.get("successful_turns", 0) else "failed" if turn == state.get("failed_turn") else "not_attempted"
            state["chat_turns"].append({"turn": turn, "status": status})
    if run.cost_guard_enabled:
        run.data["accounted_cost_usd"] = str(run.accounted_cost())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Cho phép API có phí; thiếu cờ này chỉ kiểm tra manifest.")
    parser.add_argument("--phase", choices=["pilot", "benchmark", "deep", "temperature", "comparison"], default="benchmark")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-generations", type=int)
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--max-preflights", type=int)
    parser.add_argument("--max-retries", type=int, choices=[0, 1, 2], default=2)
    parser.add_argument("--continue-on-case-error", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--enriched-profile", default="data/student_academic_profile.enriched.json")
    parser.add_argument("--plan-output")
    parser.add_argument("--review-model")
    parser.add_argument("--chat-model")
    parser.add_argument("--review-reasoning-effort", choices=["none", "low", "medium", "high", "xhigh"])
    parser.add_argument("--chat-reasoning-effort", choices=["none", "low", "medium", "high", "xhigh"])
    parser.add_argument("--review-max-output-tokens", type=int)
    parser.add_argument("--chat-max-output-tokens", type=int)
    parser.add_argument("--review-timeout", type=float)
    parser.add_argument("--chat-timeout", type=float)
    args = parser.parse_args(argv)
    run = None
    try:
        manifest = load_manifest(ROOT, path=args.manifest)
        maximum = args.max_generations if args.max_generations is not None else (12 if args.phase == "comparison" else 80)
        if not 1 <= maximum <= 80:
            raise ReviewError("--max-generations phải trong khoảng 1–80")
        if args.phase == "comparison":
            args.max_cost_usd = 2.5 if args.max_cost_usd is None else args.max_cost_usd
            args.plan_output = args.plan_output or "data/academic_benchmark/metadata_models_plan.json"
            if args.case_ids or any(getattr(args, name) is not None for name in ["review_model", "chat_model", "review_reasoning_effort", "chat_reasoning_effort", "review_max_output_tokens", "chat_max_output_tokens"]):
                raise ReviewError("Comparison dùng ma trận cố định; không đổi case/model/effort giữa run")
            if __package__:
                from .academic_model_comparison import comparison_main
            else:
                from academic_model_comparison import comparison_main
            return comparison_main(ROOT, manifest, args, maximum)
        ids = {case["case_id"] for case in manifest["cases"]}
        if args.case_ids and not set(args.case_ids) <= ids:
            raise ReviewError("Case ID không có trong manifest")
        cases = [case for case in manifest["cases"] if not args.case_ids or case["case_id"] in args.case_ids]
        if not args.live and not args.plan_output:
            print(f"Offline: {len(cases)} fixtures hợp lệ; không gọi API. Live cần --live.")
            return 0
        settings = load_settings(stage="review", model=args.review_model,
                                 reasoning_effort=args.review_reasoning_effort, max_output_tokens=args.review_max_output_tokens,
                                 request_timeout=args.review_timeout, api_key=None if args.live else "offline-plan")
        chat_settings = load_settings(stage="chat", model=args.chat_model,
                                      reasoning_effort=args.chat_reasoning_effort, max_output_tokens=args.chat_max_output_tokens,
                                      request_timeout=args.chat_timeout, api_key=None if args.live else "offline-plan")
        if args.plan_output:
            if args.phase != "benchmark":
                raise ReviewError("--plan-output ngoài comparison chỉ dùng phase benchmark")
            args.max_generations = maximum
            plan = prepare_benchmark_plan(manifest, cases, settings, chat_settings, args, ROOT)
            plan_path = checked_path(ROOT, args.plan_output)
            if plan_path.exists() and read_json(plan_path) != plan:
                raise ReviewError("Không ghi đè plan khác; chọn run mới")
            if not plan_path.exists():
                atomic_json(plan_path, plan)
            if not args.live:
                print(f"Offline plan: {len(cases)} JD, {len(plan['operations'])} generations, uncached planning ceiling={plan['planning_uncached_ceiling_usd']} USD; không gọi API.")
                return 0
        run = EvaluationRun(ROOT, manifest, args.run_id or uuid4().hex, settings, maximum, chat_settings=chat_settings,
            maximum_preflights=args.max_preflights, maximum_cost=args.max_cost_usd,
            max_retries=args.max_retries, continue_on_case_error=args.continue_on_case_error)
        transport = BudgetTransport(run)
        print(f"run={run.run_id} phase={args.phase} review_model={settings.model} chat_model={chat_settings.model} budget={maximum}", flush=True)
        timeout = max(settings.timeout, chat_settings.timeout)
        with openai.OpenAI(api_key=settings.api_key, timeout=timeout, max_retries=args.max_retries,
                           http_client=httpx.Client(transport=transport, timeout=timeout)) as sdk:
            client = RecordingClient(sdk, run, transport)
            if args.phase == "pilot":
                run_pilot(run, client)
            elif args.phase == "temperature":
                run_temperature(run, client, cases)
            else:
                run_cases(run, client, cases, deep=args.phase == "deep")
        run.data["last_phase"] = args.phase
        record_case_statuses(run, cases)
        run.data["run_status"] = "stopped" if client.stop_requested else "completed_with_failures" if any(s.get("failed") for s in run.data["cases"].values()) else "completed"
        run.data["updated_at"] = now()
        run.save()
        print(f"HTTP generation attempts={run.data['generation_attempts']}; preflight attempts={run.data['preflight_attempts']}")
        failures = (
            any(state.get("failed") for state in run.data["cases"].values())
            or any(state.get("status") == "failed" for state in run.data["pilot"].values())
            or any(pair.get("status") != "comparable" for pair in run.data["temperature_pairs"].values())
        )
        return 1 if client.stop_requested or failures else 0
    except (ReviewError, OSError, KeyError, TypeError) as exc:
        print(f"Benchmark error: {exc}")
        return 1
    finally:
        if run:
            run.close()


if __name__ == "__main__":
    raise SystemExit(main())
