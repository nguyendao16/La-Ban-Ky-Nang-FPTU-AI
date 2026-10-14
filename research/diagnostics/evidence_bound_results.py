"""Offline accounting and manual evaluation scaffolds; no inference or LLM judge."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from statistics import mean, median

from research.diagnostics import evidence_bound_response as p


def usage_summary(run):
    known, unknown = Decimal("0"), Decimal("0")
    totals = {k: 0 for k in ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"]}
    for record in run.get("http_attempts", []):
        if record["kind"] != "generation":
            continue
        try:
            payload = json.loads(record.get("raw_response", "{}"))
            usage = payload.get("usage") or {}
            input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
            reasoning = (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
            if any(type(x) is not int or x < 0 for x in [input_tokens, output_tokens, cached, reasoning]) or cached > input_tokens or reasoning > output_tokens:
                raise ValueError("Invalid usage")
            cost = p.estimate_cost(record["requested_model"], input_tokens, output_tokens, cached)
        except (ValueError, TypeError, KeyError, AttributeError):
            unknown += Decimal(record.get("reserved_cost_usd", "0"))
            continue
        known += cost
        for key, value in zip(totals, [input_tokens, cached, output_tokens, reasoning]):
            totals[key] += value
    return {"generation_http_attempts": run.get("generation_attempts", 0),
        "preflight_http_attempts": run.get("preflight_attempts", 0),
        "known_cost_usd": str(known), "unknown_usage_reservation_usd": str(unknown),
        "accounted_cost_usd": str(known + unknown), "tokens_with_known_usage": totals,
        "reasoning_tokens_included_in_output_tokens": True, "not_an_invoice": True}


def latency_stats(states, arm):
    result = {}
    for key in ["preflight_seconds", "generation_http_seconds", "parsing_seconds", "validation_adapter_seconds", "total_seconds"]:
        values = [(s.get("metrics") or {}).get("latency", {}).get(key) for s in states
                  if (s.get("metrics") or {}).get("arm") == arm]
        values = [v for v in values if isinstance(v, (float, int))]
        result[key] = {"n": len(values), "mean": mean(values) if values else None, "median": median(values) if values else None}
    return result


def annotation_template(conditions):
    return {"version": 1, "status": "pending_live_and_manual_review", "review_method": "human_manual_no_llm_judge",
        "outputs": [{"operation": c["operation"], "scenario_id": c["scenario_id"], "arm": c["arm"], "scope": c["scope"],
            "phase": c["phase"], "holdout": c["holdout"], "review_status": "pending", "claims": [],
            "asked_atomic_units": c["asked_atomic_units"], "answered_asked_units": None, "omissions": None,
            "raw_semantic_p0": None, "p1": None, "p2": None,
            "raw_semantically_correct": None, "source_provenance_correct": None,
            "naturalness": None, "completeness": None, "usable_response": None,
            "reviewer": None, "explanation": None} for c in conditions]}


def summarize(directory):
    directory = Path(directory)
    plan = p.b.read_json(directory / "plan.json")
    if p.b.digest((directory / "conditions.json").read_bytes()) != plan["artifacts"]["conditions.json"]:
        raise p.ReviewError("Cannot analyze changed frozen conditions")
    conditions = p.b.read_json(directory / "conditions.json")["conditions"]
    path = directory / "live/run.json"
    run = p.b.read_json(path) if path.exists() else {"generation_attempts": 0, "preflight_attempts": 0, "http_attempts": [], "conditions": {}}
    annotations_path = directory / "manual_annotations.json"
    if not annotations_path.exists():
        p.freeze_json(annotations_path, annotation_template(conditions))
    annotations = p.b.read_json(annotations_path)
    annotated = {r["operation"]: r for r in annotations["outputs"]}
    states = run["conditions"]
    rows, assessments = [], []
    for condition in conditions:
        op = condition["operation"]
        state = states.get(op, {"status": "not_attempted"})
        gate = p.b.read_json(directory / "live/gates" / f"{op}.json") if (directory / "live/gates" / f"{op}.json").exists() else None
        manual = annotated.get(op, {})
        completed_review = manual.get("review_status") == "completed"
        assessments.append({"operation": op, "arm": condition["arm"], "gate_status": gate["status"] if gate else "not_applicable" if condition["arm"] == "A" else "unavailable",
            "source_provenance_correct": manual.get("source_provenance_correct") if completed_review else None,
            "raw_semantically_correct": manual.get("raw_semantically_correct") if completed_review else None,
            "semantic_p0": manual.get("raw_semantic_p0") if completed_review else None,
            "publication_status": state["status"], "usable_response": manual.get("usable_response") if completed_review else None})
        rows.append({"operation": op, "scenario_id": condition["scenario_id"], "phase": condition["phase"],
            "arm": condition["arm"], "scope": condition["scope"], "holdout": condition["holdout"],
            "summary_scope": condition["summary_scope"], "completion": state["status"],
            "gate": assessments[-1]["gate_status"], "raw_p0": assessments[-1]["semantic_p0"],
            "p1": manual.get("p1") if completed_review else None, "p2": manual.get("p2") if completed_review else None,
            "asked_atoms": len(condition["asked_atomic_units"]),
            "answered_atomic_claims": len(manual["claims"]) if completed_review else None,
            "added_atomic_claims": sum(c["origin_asked_or_added"] == "added" for c in manual["claims"]) if completed_review else None,
            "review_status": manual.get("review_status", "pending")})
    usage = usage_summary(run)
    arm_stats = {}
    for arm in ["A", "B"]:
        selected = [r for r in rows if r["arm"] == arm]
        attempted = sum(r["completion"] != "not_attempted" for r in selected)
        accepted = sum(r["completion"] == "completed" for r in selected)
        withheld = sum(r["completion"] == "withheld" for r in selected)
        arm_stats[arm] = {"planned": len(selected), "attempted": attempted, "accepted": accepted, "withheld": withheld,
            "accepted_p0": sum(r["raw_p0"] > 0 for r in selected if r["completion"] == "completed" and r["raw_p0"] is not None) if all(r["raw_p0"] is not None for r in selected if r["completion"] == "completed") and accepted else None,
            "availability_before_semantic_review": accepted / attempted if attempted else None,
            "latency": latency_stats(list(states.values()), arm)}
        completed_reviews = [annotated[r["operation"]] for r in selected if r["review_status"] == "completed"]
        arm_stats[arm]["manually_reviewed"] = len(completed_reviews)
        arm_stats[arm]["usable_response_rate"] = sum(r["usable_response"] is True for r in completed_reviews) / attempted if attempted and len(completed_reviews) == attempted else None
        semantic_reviews = [r for r in completed_reviews if isinstance(r.get("raw_semantic_p0"), int)]
        arm_stats[arm]["raw_outputs_with_p0"] = sum(r["raw_semantic_p0"] > 0 for r in semantic_reviews) if semantic_reviews else None
        arm_stats[arm]["semantic_review_denominator"] = len(semantic_reviews)
    confusion = {}
    for truth in ["source_provenance_correct", "raw_semantically_correct"]:
        evaluated = [a for a in assessments if a["arm"] == "B" and a["gate_status"] in {"passed", "rejected"} and isinstance(a[truth], bool)]
        counts = {"true_acceptance": 0, "true_rejection": 0, "false_acceptance": 0, "false_rejection": 0}
        for a in evaluated:
            accepted = a["gate_status"] == "passed"
            key = "true_acceptance" if accepted and a[truth] else "false_acceptance" if accepted else "false_rejection" if a[truth] else "true_rejection"
            counts[key] += 1
        confusion[truth] = {"n": len(evaluated), **counts, "pending": sum(a["arm"] == "B" and a["gate_status"] in {"passed", "rejected"} and a[truth] is None for a in assessments)}
    failure_counts = {}
    for state in states.values():
        if state.get("failure_kind"):
            key = state["failure_kind"]
            failure_counts[key] = failure_counts.get(key, 0) + 1
    summary = {"status": "awaiting_new_paid_approval" if not run["http_attempts"] else "pending_manual_review" if any(r["review_status"] != "completed" for r in rows if r["completion"] != "not_attempted") else "manually_reviewed",
        "plan_sha256": p.b.digest((directory / "plan.json").read_bytes()), "matrix": rows,
        "arms": arm_stats, "usage": usage, "gate_confusion": confusion, "failure_counts": failure_counts,
        "semantic_status": "not_inferred_from_json_or_gate_pass", "recommendation": "inconclusive_until_live_and_manual_review",
        "gate_assessment_note": "Provenance confusion matrix and semantic confusion matrix are separate; pending manual correctness labels remain null."}
    p.b.atomic_json(directory / "gate_assessments.json", {"assessments": assessments, "confusion": confusion, "semantic_correctness": "manual_only"})
    p.b.atomic_json(directory / "comparison_summary.json", summary)
    if path.exists():
        p.b.atomic_json(directory / "live/usage.json", usage)
    return summary
