"""Offline accounting and literal provenance audit of a finished frozen RCA run.

No inference, semantic classifier, judge or production imports of this module.
Semantic annotations are separately authored after reading the original outputs.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from research.diagnostics import academic_grounding_rca as rca

b = rca.benchmark


def reference(item):
    return {key: value for key, value in item.items() if key != "source_excerpt"}


def audit_sources(condition, trace):
    profile = json.loads(condition["input"][0]["content"])["student_academic_profile"]
    output = trace["structured_output"]
    schema = condition["schema"]
    rca.SCHEMAS[schema].model_validate(output)
    groups = []
    if schema == "identification":
        groups = [(f"selections/{i}/source_matches", s["source_matches"]) for i, s in enumerate(output["selections"])]
    elif schema == "claim_level":
        groups = [(f"claims/{i}/sources", s["sources"]) for i, s in enumerate(output["claims"])]
    checks, duplicates = [], []
    for path, group in groups:
        seen = set()
        for index, source in enumerate(group):
            ref = reference(source)
            key = b.fingerprint(ref)
            if key in seen:
                duplicates.append({"path": f"{path}/{index}", "reference": ref})
            seen.add(key)
            try:
                value = rca.source_value(profile, ref)
                present = True
                literal = bool(source["source_excerpt"].strip()) and source["source_excerpt"] in value
            except rca.ReviewError:
                present = literal = False
                value = None
            checks.append({"path": f"{path}/{index}", "reference": ref, "source_present": present,
                "literal_excerpt_passed": literal, "returned_excerpt": source["source_excerpt"],
                "actual_source_value": value if not literal else None})
    aggregate = "not_applicable"
    if "evidence" in output:
        try:
            parsed = rca.SCHEMAS[schema].model_validate(output)
            rca.validate_evidence_references(parsed.evidence, rca.validate_profile(profile), label="Offline audit")
            aggregate = "passed"
        except (rca.ReviewError, ValueError):
            aggregate = "failed"
    return {"operation": condition["operation"], "schema": schema, "source_checks": checks,
        "duplicate_quoted_references": duplicates, "source_membership": "passed" if all(c["source_present"] for c in checks) else "failed",
        "literal_quote_provenance": ("passed" if all(c["literal_excerpt_passed"] for c in checks) else "failed") if groups else "not_applicable",
        "aggregate_reference_validation": aggregate, "semantic_support": "requires_manual_assessment"}


def summarize(directory):
    directory = Path(directory)
    plan = rca.check_bundle(rca.ROOT, directory)
    live = directory / "live"
    run = b.read_json(live / "run.json")
    conditions = b.read_json(directory / "conditions.json")["conditions"]
    physical = Counter(record["kind"] for record in run["http_attempts"])
    assert physical["generation"] == run["generation_attempts"] <= 32
    assert physical["preflight"] == run["preflight_attempts"] <= 32
    assert len(run["http_attempts"]) <= 64
    assert len({(r["kind"], r["operation"]) for r in run["http_attempts"]}) == len(run["http_attempts"])
    assert {r["operation"] for r in run["http_attempts"]} <= {c["operation"] for c in conditions}
    usage = b.read_json(live / "usage.json")
    assert float(usage["accounted_cost_usd"]) <= 3
    audits, records = [], []
    group_latencies = defaultdict(list)
    totals = Counter()
    for c in conditions:
        path = live / "requests" / (c["operation"] + ".json")
        if not path.exists():
            continue
        trace = b.read_json(path)
        raw = json.loads(trace["raw_response"])
        original = json.loads("".join(part["text"] for item in raw["output"] if item["type"] == "message"
                           for part in item["content"] if part["type"] == "output_text"))
        assert original == trace["structured_output"]
        assert trace["request"]["input"] == c["input"]
        assert trace["request"]["instructions"] == c["instructions"]
        assert trace["request"]["model"] == raw["model"] == plan["model"]
        assert trace["sdk_retries_taken"] == 0
        assert "temperature" not in trace["request"]
        assert trace["request"]["store"] is False and trace["request"]["truncation"] == "disabled"
        assert trace["request"]["max_output_tokens"] == 8192 and trace["request"]["reasoning"] == {"effort": "medium"}
        assert trace["request"]["timeout"] == trace["preflight_request"]["timeout"] == 180
        assert trace["preflight_request"]["text"]["format"] == trace["request"]["response_schema"]
        audits.append(audit_sources(c, trace))
        metrics = trace["metrics"]
        for name in ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"]:
            totals[name] += metrics[name] or 0
        group_latencies[c["schema"]].append(trace["latency_seconds"])
        records.append({"operation": c["operation"], "family": c["family"], "holdout": c["holdout"],
            "schema": c["schema"], "api_status": trace["api_status"], "validation_status": trace["validation_status"],
            "failure_kind": trace.get("failure_kind"), "error": trace.get("error"), "metrics": metrics})
    latencies = [r["metrics"]["latency_seconds"] for r in records]
    summary = {"plan_sha256": b.digest((directory / "plan.json").read_bytes()), "date": "2026-10-14",
        "physical_counters": dict(physical), "usage": usage, "tokens": dict(totals),
        "api_completion": dict(Counter(r["api_status"] for r in records)),
        "schema_validation": dict(Counter(r["metrics"]["schema_validation"] for r in records)),
        "combined_validation": dict(Counter(r["validation_status"] for r in records)),
        "latency_seconds": {"measurement": "preflight plus generation, parsing and validation per condition",
            "mean": statistics.mean(latencies), "median": statistics.median(latencies),
            "by_schema": {name: {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values)}
                          for name, values in group_latencies.items()}},
        "rows": records, "semantic_metrics": "manual_annotations.json, separately adjudicated"}
    b.atomic_json(directory / "postrun_checks.json", {"checks": audits,
        "note": "Literal quote checks are independent of duplicate-reference rejection. No semantic support is inferred from a passed quote."})
    b.atomic_json(directory / "execution_summary.json", summary)
    b.atomic_json(live / "execution_fingerprints.json", {str(p.relative_to(live)): b.digest(p.read_bytes())
        for folder in ["requests", "outputs"] for p in sorted((live / folder).glob("*.json"))})
    return summary


if __name__ == "__main__":
    print(json.dumps(summarize(rca.ROOT / rca.DIRECTORY), ensure_ascii=False, indent=2))
