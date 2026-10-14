"""Isolated evidence-bound response experiment; offline unless explicitly approved.

Production never imports this module. --prepare freezes the study without HTTP;
--verify checks it; --live requires the separately approved prototype plan hash.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import fcntl
import json
import sys
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Literal

import httpx
import openai
from pydantic import Field, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_academic_benchmark as b
from academic_chat import AcademicChatResponse, validate_chat_response
from academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
from academic_model_comparison import estimate_cost
from academic_review import (EvidenceReference, MetadataEvidenceReference, ReviewError,
    ReviewSettings, StrictModel, load_settings, request_structured_response,
    structured_schema_format, validate_evidence_references, validate_profile)

MODEL = "gpt-5.4-mini-2026-03-17"
DIRECTORY = "data/academic_grounding_prototype"
LIMITS = {"max_generations": 32, "max_preflights": 32, "max_http_operations": 64, "max_cost_usd": "3.00"}


class QuotedCLO(EvidenceReference):
    source_excerpt: str = Field(min_length=1, description="Exact nonblank substring of this CLO's canonical description. Grades remain separate canonical fields.")


class QuotedMetadata(MetadataEvidenceReference):
    source_excerpt: str = Field(min_length=1, description="Exact nonblank substring of this course's description/tools field, preserving original spelling and line breaks.")


class EvidenceBoundSegment(StrictModel):
    kind: Literal["academic_claim", "jd_requirement", "not_evidenced", "general_explanation"] = Field(
        description="Classify the actual text: academic facts/performance require academic_claim and sources; connective text cannot hide academic facts.")
    text: str = Field(min_length=1, description="Natural Vietnamese public text, preserved verbatim as one ordered paragraph. May contain multiple assertions if all have appropriate sources. No fixed length.")
    academic_sources: list[QuotedCLO | QuotedMetadata] = Field(
        description="Sources for every academic assertion here. Repeated identities with legitimate excerpts are allowed. Required for academic_claim; related sources permitted for not_evidenced.")
    jd_excerpt: str | None = Field(description="Exact nonblank substring of the current JD when present; required for jd_requirement. Never substitutes for academic evidence.")


class EvidenceBoundResponse(StrictModel):
    segments: list[EvidenceBoundSegment] = Field(min_length=1, description="Ordered public answer paragraphs. Backend joins their text; do not generate a separate reply. Adapt detail naturally; no fixed segment count.")


SCHEMAS = {"A": AcademicChatResponse, "B": EvidenceBoundResponse}
SUMMARY_SCOPE = """EXPLICIT SUMMARY SCOPE (diagnostic S1):
A conversation summary summarizes the topics actually discussed in preceding
user/assistant messages. Do not expand into unrelated topics found only in the
profile or Initial Review. Recheck against canonical sources and correct earlier
errors; such a correction may retrieve additional details of the discussed topic.
A comprehensive JD academic summary may use the entire profile and Initial Review
and add relevant, correctly evidenced facts not previously discussed. Do not limit
that request to history. For an ambiguous 'tóm tắt lại', use the conversational
referent; do not expand automatically or ask unnecessarily when intent is clear.
Preserve essential distinctions and requested content. Fewer claims are not by
themselves better. These rules do not change source authority or Strict Option A.
"""


def settings(api_key="offline-prototype"):
    return ReviewSettings(api_key=api_key, stage="chat", model=MODEL, reasoning_effort="medium",
                          max_output_tokens=8192, request_timeout=180)


def bound_instructions():
    old = ('{"reply": "Natural Vietnamese response", "evidence": [{"course_code": "existing code", "clo": "existing CLO"}]}\n'
           'Use only these two fields. Evidence objects follow the CLO or metadata shapes above;\n'
           'never put score, achievement or description in them. Do not duplicate references.')
    if ACADEMIC_CHAT_INSTRUCTIONS.count(old) != 1:
        raise ReviewError("Production output contract changed; review prototype before freeze")
    new = """Return only {segments: [...]} as required by the supplied schema; no reply or
aggregate evidence field. Each segment has kind, text, academic_sources, jd_excerpt.
The backend publishes the ordered text verbatim, separated by blank lines, and
deduplicates source identities into external evidence. Write coherent Vietnamese
paragraphs, not a separate mapping followed by an independently generated answer.
academic_claim needs at least one academic source covering its academic assertions.
jd_requirement has no academic sources and needs an exact current-JD excerpt.
not_evidenced may have no academic sources or may cite related academic context.
general_explanation is connective text only, without academic sources/JD excerpts;
never hide a curriculum, performance, tool-use or JD fact in that category.
Sources retain CLO/metadata identity plus source_excerpt, a verbatim nonblank
substring of the exact CLO description or metadata field. Paraphrase public text
naturally. Scores/achievement come from the canonical CLO fields, not its quote.
Repeated source identities and multiple excerpts are permitted within/across
segments; the backend alone deduplicates final external evidence. Preserve all
source values; do not supply private reasoning. Use no fixed segment/word limit."""
    result = ACADEMIC_CHAT_INSTRUCTIONS.replace(old, new)
    result = result.replace("Each evidence item is EXACTLY one of these shapes:",
        "Each academic source uses one of these identity shapes plus source_excerpt:")
    result = result.replace("not_evidenced uses evidence: [] when neither",
        "not_evidenced may use academic_sources: [] when neither")
    return result


def instructions(arm, scope):
    base = ACADEMIC_CHAT_INSTRUCTIONS if arm == "A" else bound_instructions()
    return base if scope == "S0" else base + "\n" + SUMMARY_SCOPE


def source_value(profile, reference):
    course = next((c for c in profile["courses"] if c["course_code"] == reference["course_code"]), None)
    if course is None:
        raise ReviewError("Course is absent from actually provided profile")
    if "clo" in reference:
        outcome = next((c for c in course["clos"] if c["clo"] == reference["clo"]), None)
        if outcome is None:
            raise ReviewError("CLO is absent from actually provided course")
        return outcome["description"]
    value = (course.get("metadata") or {}).get(reference["metadata_field"])
    if not isinstance(value, str) or not value.strip():
        raise ReviewError("Metadata field is absent or blank in actually provided course")
    return value


def raw_render(parsed):
    """Lossless analysis view only; this function does not authorize publication."""
    evidence, seen = [], set()
    for segment in parsed.segments:
        for source in segment.academic_sources:
            ref = source.model_dump(exclude={"source_excerpt"})
            identity = tuple(sorted(ref.items()))
            if identity not in seen:
                seen.add(identity)
                evidence.append(ref)
    return {"reply": "\n\n".join(s.text for s in parsed.segments), "evidence": evidence}


def provenance_gate(parsed, profile, jd):
    """Structural/source provenance only; deliberately no semantic entailment check."""
    try:
        parsed = EvidenceBoundResponse.model_validate(parsed.model_dump() if hasattr(parsed, "model_dump") else parsed)
    except ValidationError as exc:
        return {"status": "rejected", "errors": [{"path": "/".join(str(v) for v in e["loc"]),
            "code": "schema", "message": e["msg"]} for e in exc.errors(include_input=False, include_url=False)],
            "checks": [], "semantic_support": "requires_manual_assessment"}
    index = validate_profile(profile)
    errors, checks = [], []
    for number, segment in enumerate(parsed.segments):
        path = f"segments/{number}"
        if not segment.text.strip():
            errors.append({"path": path + "/text", "code": "blank_text"})
        if segment.kind == "academic_claim" and not segment.academic_sources:
            errors.append({"path": path, "code": "missing_academic_source"})
        if segment.kind == "jd_requirement" and (segment.jd_excerpt is None or not segment.jd_excerpt.strip()):
            errors.append({"path": path, "code": "missing_jd_excerpt"})
        if segment.kind in {"jd_requirement", "general_explanation"} and segment.academic_sources:
            errors.append({"path": path, "code": "unexpected_academic_source_for_kind"})
        if segment.kind == "general_explanation" and segment.jd_excerpt is not None:
            errors.append({"path": path, "code": "unexpected_jd_excerpt_for_kind"})
        if segment.jd_excerpt is not None:
            valid = bool(segment.jd_excerpt.strip()) and segment.jd_excerpt in jd
            checks.append({"path": path + "/jd_excerpt", "literal_excerpt_passed": valid})
            if not valid:
                errors.append({"path": path + "/jd_excerpt", "code": "jd_quote_provenance"})
        for offset, source in enumerate(segment.academic_sources):
            ref = source.model_dump(exclude={"source_excerpt"})
            check = {"path": f"{path}/academic_sources/{offset}", "reference": ref,
                     "source_excerpt": source.source_excerpt, "source_present": False, "literal_excerpt_passed": False}
            try:
                identity = EvidenceReference.model_validate(ref) if "clo" in ref else MetadataEvidenceReference.model_validate(ref)
                # Validate individually: repeated legitimate identities are not an error.
                validate_evidence_references([identity], index, label="Prototype source")
                value = source_value(profile, ref)
                check["source_present"] = True
                check["literal_excerpt_passed"] = bool(source.source_excerpt.strip()) and source.source_excerpt in value
                if not check["literal_excerpt_passed"]:
                    errors.append({"path": check["path"], "code": "academic_quote_provenance"})
            except (ReviewError, ValueError) as exc:
                errors.append({"path": check["path"], "code": "source_identity", "message": str(exc)})
            checks.append(check)
    return {"status": "rejected" if errors else "passed", "errors": errors, "checks": checks,
            "semantic_support": "requires_manual_assessment"}


def adapt_response(raw, profile, jd):
    gate = provenance_gate(raw, profile, jd)
    if gate["status"] != "passed":
        raise ReviewError("Prototype provenance gate rejected the response: " + json.dumps(gate["errors"], ensure_ascii=False))
    parsed = EvidenceBoundResponse.model_validate(raw.model_dump() if hasattr(raw, "model_dump") else raw)
    return validate_chat_response(raw_render(parsed), validate_profile(profile))


def freeze_json(path, value):
    if path.exists():
        if b.read_json(path) != value:
            raise ReviewError(f"Refusing to overwrite frozen artifact: {path.name}")
    else:
        b.atomic_json(path, value)


def integrity(root, manifest):
    changed = [name for name, sha in manifest["files"].items()
               if not (root / name).is_file() or b.digest((root / name).read_bytes()) != sha]
    return {"protected_files": len(manifest["files"]), "changed": changed, "passed": not changed}


def prepare(root=ROOT, directory=None):
    from research.diagnostics.evidence_bound_fixtures import build_bundle
    root = Path(root).resolve()
    directory = Path(directory) if directory is not None else root / DIRECTORY
    if (directory / "plan.json").exists():
        return check_bundle(root, directory)
    bundle, source_paths = build_bundle(root)
    before_path = directory / "integrity_before.json"
    if not before_path.exists():
        excluded = {".venv", "__pycache__", ".pytest_cache", ".git", ".ruff_cache"}
        freeze_json(before_path, {"version": 1, "files": {str(p.relative_to(root)): b.digest(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file() and not excluded.intersection(p.relative_to(root).parts)
            and not p.is_relative_to(directory)}})
    if not integrity(root, b.read_json(before_path))["passed"]:
        raise ReviewError("Protected existing files changed before freeze")
    for name, value in bundle.items():
        freeze_json(directory / name, value)
    changes = "".join(difflib.unified_diff(ACADEMIC_CHAT_INSTRUCTIONS.splitlines(keepends=True),
        bound_instructions().splitlines(keepends=True), fromfile="production-A-S0", tofile="prototype-B-S0"))
    diff_path = directory / "prompt_contract.diff"
    if diff_path.exists() and diff_path.read_text() != changes:
        raise ReviewError("Frozen prompt diff differs")
    diff_path.write_text(changes)
    source_paths += ["scripts/academic_chat.py", "scripts/academic_chat_prompt.py", "scripts/academic_metadata_prompt.py",
        "scripts/academic_review.py", "scripts/academic_review_prompt.py", "scripts/openai_model_config.py",
        "scripts/evaluate_academic_benchmark.py", "scripts/academic_model_comparison.py",
        "research/diagnostics/evidence_bound_response.py", "research/diagnostics/evidence_bound_fixtures.py",
        "research/diagnostics/evidence_bound_results.py", "tests/test_evidence_bound_response.py"]
    conditions = bundle["conditions.json"]["conditions"]
    config = settings()
    plan = {"version": 1, "purpose": "isolated_evidence_bound_prototype_no_production_integration",
        "live_authorization": "new_user_approval_of_this_plan_required_after_offline_pass",
        "model": MODEL, "reasoning_effort": "medium", "max_output_tokens": 8192, "timeout_seconds": 180,
        "context_window": config.context_window, "temperature_sent": False, "store": False, "truncation": "disabled",
        "max_retries": 0, "budgets": LIMITS, "holdouts": ["S4", "S8"], "planning_input_tokens": 64000,
        "planning_input_is_not_a_truncation_cap": True,
        "planning_uncached_cost_ceiling_usd": str(32 * estimate_cost(MODEL, 64000, 8192)),
        "prices_per_million_usd": {"input": "0.75", "cached_input": "0.075", "output": "4.50"},
        "pricing_source": "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
        "pricing_checked_at": "2026-10-14", "reverify_official_pricing_before_authorized_live": True,
        "sources": {name: b.digest(b.checked_path(root, name).read_bytes()) for name in sorted(set(source_paths))},
        "artifacts": {name: b.digest((directory / name).read_bytes())
                      for name in [*bundle, "prompt_contract.diff", "integrity_before.json"]},
        "operations": [{key: row[key] for key in ["operation", "scenario_id", "arm", "scope", "phase", "holdout", "repeat_of", "input_sha256", "instructions_sha256", "schema_sha256"]} for row in conditions],
        "production_chat_prompt_sha256": b.digest(ACADEMIC_CHAT_INSTRUCTIONS.encode()),
        "production_chat_schema_sha256": b.fingerprint(structured_schema_format(AcademicChatResponse)),
        "assessment_status": "pending_live_and_manual_review"}
    freeze_json(directory / "plan.json", plan)
    return check_bundle(root, directory)


def check_bundle(root=ROOT, directory=None, *, deep=False, validate_matrix=True):
    root = Path(root).resolve()
    directory = Path(directory) if directory is not None else root / DIRECTORY
    plan = b.read_json(directory / "plan.json")
    if plan["budgets"] != LIMITS:
        raise ReviewError("Prototype budget policy differs from frozen plan")
    for name, sha in plan["sources"].items():
        if b.digest(b.checked_path(root, name).read_bytes()) != sha:
            raise ReviewError(f"Source fingerprint changed: {name}")
    for name, sha in plan["artifacts"].items():
        if b.digest((directory / name).read_bytes()) != sha:
            raise ReviewError(f"Frozen artifact changed: {name}")
    config = settings()
    for key, value in {"model": config.model, "reasoning_effort": config.reasoning_effort,
                       "max_output_tokens": config.max_output_tokens, "timeout_seconds": config.timeout,
                       "context_window": config.context_window}.items():
        if plan[key] != value:
            raise ReviewError(f"Frozen setting changed: {key}")
    schemas = b.read_json(directory / "schemas.json")
    if schemas != {name: structured_schema_format(model) for name, model in SCHEMAS.items()}:
        raise ReviewError("Frozen schema differs")
    if validate_matrix:
        from research.diagnostics.evidence_bound_fixtures import validate_conditions
        validate_conditions(b.read_json(directory / "conditions.json")["conditions"])
    if deep and not integrity(root, b.read_json(directory / "integrity_before.json"))["passed"]:
        raise ReviewError("Protected historical/production files changed")
    return plan


class PrototypeRun(b.EvaluationRun):
    def __init__(self, root, directory, plan, config):
        self.root, self.bundle_directory = Path(root).resolve(), Path(directory).resolve()
        self.directory = self.bundle_directory / "live"
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise ReviewError("Live directory may not be a symlink")
        if (config.model, config.reasoning_effort, config.max_output_tokens, config.timeout, config.temperature, config.context_window) != (MODEL, "medium", 8192, 180, None, 400000):
            raise ReviewError("Live settings differ from prototype matrix")
        if plan != check_bundle(self.root, self.bundle_directory):
            raise ReviewError("Supplied plan differs from frozen bundle")
        self.path = self.directory / "run.json"
        self.settings = self.active_settings = config
        self.active_input_tokens = None
        self.maximum_preflights, self.maximum_cost = 32, Decimal("3.00")
        self.cost_guard_enabled = self.continue_on_case_error = True
        self.plan, self.current_condition = plan, None
        self.lock = (self.directory / "run.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sha = b.digest((self.bundle_directory / "plan.json").read_bytes())
            self.data = b.read_json(self.path) if self.path.exists() else {"version": 1, "origin": "live",
                "plan_sha256": sha, "started_at": b.now(), "max_generations": 32, "generation_attempts": 0,
                "preflight_attempts": 0, "http_attempts": [], "conditions": {}, "semantic_status": "pending_manual_annotation"}
            if self.data["plan_sha256"] != sha or self.data["max_generations"] != 32:
                raise ReviewError("Cannot resume another plan or budget")
            for kind, field in [("generation", "generation_attempts"), ("preflight", "preflight_attempts")]:
                records = [r for r in self.data["http_attempts"] if r["kind"] == kind]
                if self.data[field] != len(records) or self.data[field] > 32:
                    raise ReviewError("Ledger physical counters are inconsistent")
            self.save()
        except BaseException:
            self.close()
            raise

    def verify_sources(self):
        # Matrix is validated at construction; verify its immutable bytes on every
        # dispatch without repeatedly rebuilding 32 Pydantic schema comparisons.
        check_bundle(self.root, self.bundle_directory, validate_matrix=False)

    def consume_http(self, kind, operation):
        if kind not in {"preflight", "generation"} or self.current_condition is None or operation != self.current_condition["operation"] or operation not in {c["operation"] for c in self.plan["operations"]}:
            raise ReviewError("HTTP operation is outside frozen matrix")
        self.verify_sources()
        if len(self.data["http_attempts"]) >= 64:
            raise ReviewError("Physical operations cap reached")
        return super().consume_http(kind, operation)

    def capture_metrics(self, current):
        # The comparison helper assumes production schema; use condition-aware metrics.
        usage = current.get("usage") or {}
        current["metrics"] = {"arm": self.current_condition["arm"], "scope": self.current_condition["scope"],
            "holdout": self.current_condition["holdout"], "requested_model": MODEL,
            "resolved_model": current.get("response_model"), "reasoning_effort": "medium",
            "max_output_tokens": 8192, "temperature_sent": False, "usage": usage,
            "completion": current.get("api_status", "unknown"),
            "schema_validation": "passed" if current.get("structured_output") is not None else "failed" if current.get("failure_kind") == "parsing" else "unavailable",
            "production_reference_validation": current.get("validation_status") if self.current_condition["arm"] == "A" else "adapter_only",
            "gate_status": current.get("gate", {}).get("status", "not_applicable" if self.current_condition["arm"] == "A" else "unavailable"),
            "semantic_support": "pending_manual_annotation", "latency": current.get("latency", {})}


class TimedInnerTransport(httpx.BaseTransport):
    """Time only physical HTTP/body reading; outer BudgetTransport owns accounting."""
    def __init__(self, run, inner):
        self.run, self.inner = run, inner

    def handle_request(self, request):
        record = self.run.data["http_attempts"][-1]
        start = perf_counter()
        try:
            response = self.inner.handle_request(request)
            response.read()
            return response
        finally:
            record["http_latency_seconds"] = perf_counter() - start

    def close(self):
        self.inner.close()


class PrototypeRecordingClient(b.RecordingClient):
    def parse(self, **kwargs):
        self.current["generation_calls"] += 1
        request = dict(kwargs)
        request["response_schema"] = structured_schema_format(request.pop("text_format"))
        self.current["request"] = copy.deepcopy(request)
        self.current["context_sha256"] = b.fingerprint(request)
        self.flush()
        raw = self.sdk.responses.with_raw_response.parse(**kwargs)
        self.current.update(raw_response=raw.text, sdk_retries_taken=raw.retries_taken)
        self.flush()
        start = perf_counter()
        try:
            response = raw.parse()
        finally:
            self.current.setdefault("latency", {})["parsing_seconds"] = perf_counter() - start
            self.flush()
        self.current.update(response_model=response.model, api_status=response.status,
            usage=response.usage.model_dump() if response.usage else None,
            structured_output=response.output_parsed.model_dump() if response.output_parsed is not None else None)
        if response.incomplete_details is not None:
            self.current["incomplete_details"] = response.incomplete_details.model_dump()
        self.flush()
        return response

    def finish(self, error=None):
        records = [r for r in self.run.data["http_attempts"] if r["operation"] == self.current["operation"]]
        latency = self.current.setdefault("latency", {})
        for kind, label in [("preflight", "preflight_seconds"), ("generation", "generation_http_seconds")]:
            row = next((r for r in records if r["kind"] == kind), {})
            latency[label] = row.get("http_latency_seconds")
        # An SDK parse failure must still preserve API status, usage and raw body.
        generation = next((r for r in records if r["kind"] == "generation"), {})
        if generation.get("raw_response"):
            self.current.setdefault("raw_response", generation["raw_response"])
            try:
                payload = json.loads(generation["raw_response"])
                if not isinstance(payload, dict):
                    payload = {}
            except (TypeError, ValueError):
                payload = {}
            for key, dest in [("status", "api_status"), ("model", "response_model"), ("usage", "usage"), ("incomplete_details", "incomplete_details")]:
                if payload.get(key) is not None:
                    self.current.setdefault(dest, payload[key])
        latency["total_seconds"] = perf_counter() - self.started_clock
        super().finish(error)
        if self.current.get("gate", {}).get("status") == "rejected":
            self.current["failure_kind"] = "provenance_gate"
        elif error and "refusal" in str(error):
            self.current["failure_kind"] = "refusal"
        if error and "vượt context" in str(error):
            self.current["failure_kind"] = "context"
            self.stop_requested = True
        if error and isinstance(error.__cause__, openai.APIStatusError):
            self.stop_requested = True
        if self.stop_requested:
            self.run.data["stop_reason"] = self.current.get("error", "global_failure")
            self.run.save()
        self.flush()


def evaluate_parsed(condition, parsed, directory):
    """Persist original parsed output before gate; never mutate the frozen input."""
    op, arm = condition["operation"], condition["arm"]
    freeze_json(directory / "parsed" / f"{op}.json", parsed.model_dump())
    profile = json.loads(condition["input"][0]["content"])["student_academic_profile"]
    jd = json.loads(condition["input"][1]["content"])["current_job_description"]
    if arm == "A":
        result = validate_chat_response(parsed.model_dump(), validate_profile(profile))
        assessment = {"status": "not_applicable", "reason": "Path A uses only unchanged production validation"}
    else:
        freeze_json(directory / "raw_views" / f"{op}.json", {"publication": "analysis_only", **raw_render(parsed)})
        assessment = provenance_gate(parsed, profile, jd)
        freeze_json(directory / "gates" / f"{op}.json", assessment)
        if assessment["status"] != "passed":
            return None, assessment
        result = validate_chat_response(raw_render(parsed), validate_profile(profile))
    freeze_json(directory / "outputs" / f"{op}.json", result.model_dump())
    return result, assessment


def recover_condition(run, condition):
    """Recover a durable completed HTTP response; never redispatch uncertain attempts."""
    op = condition["operation"]
    records = [r for r in run.data["http_attempts"] if r["operation"] == op]
    generation = next((r for r in records if r["kind"] == "generation"), None)
    trace_path = run.directory / "requests" / f"{op}.json"
    trace = b.read_json(trace_path) if trace_path.exists() else {}
    state = {"status": "attempted_not_regenerated", "artifact": f"requests/{op}.json", "reason": "attempt outcome uncertain"}
    request = trace.get("request")
    expected = {"timeout": 180.0, "model": MODEL, "instructions": condition["instructions"], "input": condition["input"],
        "max_output_tokens": 8192, "truncation": "disabled", "store": False, "reasoning": {"effort": "medium"},
        "response_schema": structured_schema_format(SCHEMAS[condition["arm"]])}
    if generation is None or not generation.get("raw_response") or request != expected:
        return state
    try:
        payload = json.loads(generation["raw_response"])
        if payload.get("status") != "completed" or payload.get("model") != MODEL:
            return {**state, "status": "failed", "reason": "response incomplete or incompatible model"}
        texts = [c["text"] for item in payload.get("output", []) if item.get("type") == "message"
                 for c in item.get("content", []) if c.get("type") == "output_text"]
        if len(texts) != 1:
            return {**state, "status": "failed", "reason": "refusal or missing structured text"}
        parsed = SCHEMAS[condition["arm"]].model_validate(json.loads(texts[0]))
        result, gate = evaluate_parsed(condition, parsed, run.directory)
        return {"status": "withheld" if result is None else "completed", "recovered_offline": True,
                "artifact": f"requests/{op}.json", "gate": gate, "metrics": trace.get("metrics"),
                "output": f"outputs/{op}.json" if result is not None else None}
    except (ValueError, ReviewError) as exc:
        return {**state, "status": "failed", "reason": str(exc)}


def execute_conditions(run, sdk, transport):
    conditions = b.read_json(run.bundle_directory / "conditions.json")["conditions"]
    client = PrototypeRecordingClient(sdk, run, transport)
    for condition in conditions:
        op = condition["operation"]
        run.current_condition = condition
        try:
            run.verify_sources()
        except (ReviewError, OSError, ValueError) as exc:
            run.data["stop_reason"] = str(exc)
            run.data["conditions"].setdefault(op, {"status": "not_attempted", "reason": "source_integrity"})
            client.stop_requested = True
            break
        if (run.directory / "requests" / f"{op}.json").exists() or any(r["operation"] == op for r in run.data["http_attempts"]):
            run.data["conditions"][op] = recover_condition(run, condition)
            run.save()
            continue
        if run.accounted_cost() + estimate_cost(MODEL, 0, 8192) > run.maximum_cost:
            run.data["stop_reason"] = "Remaining budget cannot reserve even the output ceiling"
            client.stop_requested = True
            break
        client.begin(op, run.settings)
        result, error = None, None
        try:
            parsed = request_structured_response(condition["instructions"], copy.deepcopy(condition["input"]),
                SCHEMAS[condition["arm"]], run.settings, client=client, operation_label="prototype")
            run.verify_sources()
            start = perf_counter()
            try:
                result, gate = evaluate_parsed(condition, parsed, run.directory)
                client.current["gate"] = gate
                if result is None:
                    raise ReviewError("Prototype provenance gate rejected output")
            finally:
                client.current.setdefault("latency", {})["validation_adapter_seconds"] = perf_counter() - start
        except (ReviewError, OSError, ValueError) as exc:
            error = exc
        try:
            client.finish(error)
        except (ReviewError, OSError, ValueError) as exc:
            # In-flight source changes stop publication and leave durable raw HTTP.
            client.current.update(validation_status="failed", failure_kind="source_integrity", error=str(exc))
            run.capture_metrics(client.current)
            client.flush()
            run.data["stop_reason"] = str(exc)
            client.stop_requested = True
        run.data["conditions"][op] = {"status": "completed" if result is not None else "withheld" if client.current.get("gate", {}).get("status") == "rejected" else "failed",
            "artifact": f"requests/{op}.json", "failure_kind": client.current.get("failure_kind"),
            "metrics": client.current["metrics"], "output": f"outputs/{op}.json" if result is not None else None}
        run.save()
        if client.stop_requested:
            break
    for condition in conditions:
        run.data["conditions"].setdefault(condition["operation"], {"status": "not_attempted"})
    run.data["run_status"] = "stopped" if client.stop_requested else "completed" if all(c["status"] == "completed" for c in run.data["conditions"].values()) else "completed_with_failures"
    run.data["updated_at"] = b.now()
    run.save()
    from research.diagnostics.evidence_bound_results import summarize
    try:
        summarize(run.bundle_directory)
    except (ReviewError, OSError, ValueError) as exc:
        run.data["analysis_error"] = str(exc)
        run.save()


def main(argv=None):
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--live", action="store_true")
    parser.add_argument("--directory", default=DIRECTORY)
    parser.add_argument("--approved-plan-sha256", help="Operator acknowledgment of this prototype plan; separate user paid approval is required.")
    args = parser.parse_args(argv)
    try:
        directory = b.checked_path(ROOT, args.directory)
        if not directory.is_relative_to((ROOT / DIRECTORY).resolve()):
            raise ReviewError("Prototype output must stay under data/academic_grounding_prototype; historical directories are protected")
        plan = prepare(ROOT, directory) if args.prepare else check_bundle(ROOT, directory, deep=True)
        sha = b.digest((directory / "plan.json").read_bytes())
        if not args.live:
            print(f"Offline verified: 32 generation / 32 preflight / <=3 USD; plan SHA256={sha}; no HTTP.")
            return 0
        if args.approved_plan_sha256 != sha:
            raise ReviewError("Live requires explicit approval of this prototype plan SHA256; prior RCA approval does not apply")
        config = load_settings(stage="chat", model=MODEL, reasoning_effort="medium", max_output_tokens=8192, request_timeout=180)
        run = PrototypeRun(ROOT, directory, plan, config)
        try:
            transport = b.BudgetTransport(run, TimedInnerTransport(run, httpx.HTTPTransport()))
            with openai.OpenAI(api_key=config.api_key, timeout=180, max_retries=0,
                    http_client=httpx.Client(transport=transport, timeout=180)) as sdk:
                execute_conditions(run, sdk, transport)
            print(f"Physical HTTP: {run.data['generation_attempts']} generation / {run.data['preflight_attempts']} preflight")
        finally:
            run.close()
        return 0
    except (ReviewError, OSError, ValueError) as exc:
        print(f"Prototype error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
