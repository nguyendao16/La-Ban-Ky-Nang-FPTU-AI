"""Frozen human-authored prototype scenarios; no new output becomes later input."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from research.diagnostics import evidence_bound_response as p
from academic_review import load_jd, load_profile, validate_review

PROFILE = "data/student_academic_profile.enriched.json"
RCA = "data/academic_grounding_rca"
REVIEWS = "data/academic_benchmark/initial_reviews/reasoning-five-jds-20261013"
FIVE = "data/academic_benchmark/evaluations/reasoning-five-jds-20261013"
RUBRIC = "data/academic_benchmark/evaluations/rubric.json"


def clo(course, identifier):
    return {"course_code": course, "clo": identifier}


def metadata(course, field):
    return {"course_code": course, "metadata_field": field}


def canonical(profile, reference):
    if "clo" not in reference:
        return p.source_value(profile, reference)
    course = next(c for c in profile["courses"] if c["course_code"] == reference["course_code"])
    return next(c for c in course["clos"] if c["clo"] == reference["clo"])


def target(identifier, statement, direct=(), related=(), *, note="", category="curriculum"):
    return {"target_id": identifier, "statement": statement, "category": category,
            "acceptable_direct_sources": list(direct), "acceptable_related_sources": list(related),
            "note": note, "semantic_assessment": "manual_only"}


def build_scenarios(root, profile):
    previous = {s["scenario_id"]: s for s in p.b.read_json(root / RCA / "scenarios.json")["scenarios"]}
    old = p.b.read_json(root / RCA / "histories.json")["histories"]
    history8 = [{"role": "user", "content": "AIL303m có nội dung phát hiện và xử lý outliers không?"},
        {"role": "assistant", "content": json.dumps({"reply": "AIL303m/CLO3 ghi: " +
            p.source_value(profile, clo("AIL303m", "CLO3")) + " Điểm 7.56, achievement good thuộc CLO này.",
            "evidence": [clo("AIL303m", "CLO3")]}, ensure_ascii=False)}]
    summary = "Bạn tóm tắt các nội dung học thuật đã trao đổi, kèm nguồn phù hợp và giữ đúng điểm/achievement nếu nhắc lại."
    rows = [
        {"scenario_id": "S1", "jd": "JD05", "question": previous["S1"]["question"], "history": [], "summary_scope": "not_summary", "holdout": False,
         "targets": [target("S1-CI", "Confidence intervals trong MAS291", [clo("MAS291", "CLO7")]),
            target("S1-LR", "Simple linear regression trong MAS291", [clo("MAS291", "CLO9")]),
            target("S1-CI-GRADE", "MAS291/CLO7=9.43/excellent", [clo("MAS291", "CLO7")], category="assessment"),
            target("S1-LR-GRADE", "MAS291/CLO9=9.43/excellent", [clo("MAS291", "CLO9")], category="assessment")]},
        {"scenario_id": "S2", "jd": "JD11", "question": "CSI106 cho mình những nền tảng gì về biểu diễn dữ liệu và mạng máy tính, và chúng liên quan thế nào tới Backend Engineering trong JD này?", "history": [], "summary_scope": "not_summary", "holdout": False,
         "targets": [target("S2-DATA", "Data types/bit patterns", [clo("CSI106", "CLO3"), metadata("CSI106", "description")], note="Metadata supports curriculum coverage, not the assessed Describe outcome/score."),
            target("S2-NET", "Networking layers", [clo("CSI106", "CLO4"), metadata("CSI106", "description")]),
            target("S2-LINK", "Liên hệ nền tảng với backend, không suy framework/kinh nghiệm", related=[clo("CSI106", "CLO3"), clo("CSI106", "CLO4")], category="boundary")]},
        {"scenario_id": "S3", "jd": "JD01", "question": previous["S3"]["question"], "history": [], "summary_scope": "not_summary", "holdout": False,
         "targets": [target("S3-OD", "Understand/Implement Object Detection", [clo("CPV301", "CLO8")]),
            target("S3-FACE", "Explain Face Recognition", [clo("CPV301", "CLO9")]),
            target("S3-TRACK", "Explain Object Tracking", [clo("CPV301", "CLO9")]),
            target("S3-LIMIT", "Explain Face Recognition/Tracking không xác nhận Implement cả ba", related=[clo("CPV301", "CLO8"), clo("CPV301", "CLO9")], category="boundary")]},
        {"scenario_id": "S4", "jd": "JD11", "question": "Trong MAD101, C programming tools và Maxima được nêu ở đâu? Hồ sơ có xác nhận mình đã sử dụng từng công cụ và được đánh giá riêng trên chúng không?", "history": [], "summary_scope": "not_summary", "holdout": True,
         "holdout_rationale": "New metadata/example-versus-personal-use question about MAD101; not the old ADY/DAP/PFP tool fixtures or their schema rerun.",
         "targets": [target("S4-C", "C programming tools trong MAD101 metadata.tools, for example", [metadata("MAD101", "tools")], category="metadata"),
            target("S4-MAXIMA", "Maxima trong MAD101 metadata.tools, for example", [metadata("MAD101", "tools")], category="metadata"),
            target("S4-USE-C", "Không xác nhận cá nhân đã dùng C programming tools", related=[metadata("MAD101", "tools")], category="boundary"),
            target("S4-USE-MAXIMA", "Không xác nhận cá nhân đã dùng Maxima", related=[metadata("MAD101", "tools")], category="boundary"),
            target("S4-GRADE", "Không suy điểm hoặc performance riêng của hai công cụ", related=[metadata("MAD101", "tools")], category="boundary")]},
        {"scenario_id": "S5", "jd": "JD05", "question": summary, "history": copy.deepcopy(old["E2-contaminated"]["history"]),
         "history_origin": "Exact isolated RCA E2-contaminated history; only historical CI attribution is seeded wrong", "summary_scope": "conversation", "holdout": False,
         "targets": [target("S5-CI", "Giữ CI và sửa nguồn thành MAS291/CLO7", [clo("MAS291", "CLO7")]),
            target("S5-HYP", "Hypothesis testing", [clo("MAS291", "CLO8")]),
            target("S5-LR", "Simple linear regression", [clo("MAS291", "CLO9")]),
            target("S5-PCA", "PCA", [clo("MAI391", "CLO6")])]},
        {"scenario_id": "S6", "jd": "JD05", "question": summary, "history": copy.deepcopy(old["E3-same-course"]["history"]), "summary_scope": "conversation", "holdout": False,
         "targets": [target("S6-DESCR", "Descriptive statistics", [clo("MAS291", "CLO5")]),
            target("S6-SAMPLING", "Sampling distributions", [clo("MAS291", "CLO6")]),
            target("S6-CLT", "Central Limit Theorem", [clo("MAS291", "CLO6")]),
            target("S6-CI", "Confidence intervals", [clo("MAS291", "CLO7")]),
            target("S6-HYP", "Hypothesis testing", [clo("MAS291", "CLO8")]),
            target("S6-LR", "Simple linear regression", [clo("MAS291", "CLO9")])]},
        {"scenario_id": "S7", "jd": "JD11", "question": "Tóm tắt ngắn đúng hai nội dung sorting và hashing mình vừa trao đổi.",
         "history": copy.deepcopy(old["E5-holdout"]["history"]), "summary_scope": "conversation", "holdout": False,
         "previous_holdout_now_development": True,
         "targets": [target("S7-SORT", "Sorting", [clo("CSD203", "CLO6")]), target("S7-HASH", "Hashing", [clo("CSD203", "CLO7")])]},
        {"scenario_id": "S8", "jd": "JD07", "question": "Tổng hợp tất cả kiến thức học thuật trong hồ sơ liên quan tới JD này, kể cả phần chưa bàn trong hội thoại; phân biệt nội dung có nguồn, công nghệ chưa được xác nhận và điều kiện JD mà CLO không chứng minh.",
         "history": history8, "summary_scope": "comprehensive_jd", "holdout": True,
         "holdout_rationale": "New JD07 comprehensive synthesis with a new AIL303m/outliers-only history; not an old PFP/CSD RCA holdout rerun. JD07 and its Review were historical inputs, not claimed entirely unseen.",
         "targets": [
            target("S8-WORKFLOW", "Methodology/business questions và phân tích dữ liệu", [clo("ADY201m", "CLO4"), clo("DAP391m", "CLO1"), clo("DAP391m", "CLO2"), clo("DAP391m", "CLO7")]),
            target("S8-COLLECTION", "Data collection/retrieval", [clo("ADY201m", "CLO5"), clo("ADY201m", "CLO4"), clo("DAP391m", "CLO7"), clo("AIL303m", "CLO1"), clo("AIL303m", "CLO10")], note="Do not bind collection to ADY201m/CLO7; preserve cognitive verbs."),
            target("S8-CLEAN", "Cleaning/wrangling/transform", [clo("DAP391m", "CLO1"), clo("DAP391m", "CLO2"), clo("DAP391m", "CLO7"), clo("ADY201m", "CLO5"), clo("ADY201m", "CLO7"), clo("AIL303m", "CLO1"), clo("AIL303m", "CLO2"), clo("AIL303m", "CLO10")]),
            target("S8-VIS", "Visualization/reports/dashboard", [clo("DAP391m", "CLO2"), clo("DAP391m", "CLO3"), clo("DAP391m", "CLO4"), clo("DAP391m", "CLO7"), metadata("DAP391m", "description"), clo("ADY201m", "CLO7")], note="Dashboard needs DAP391m/CLO7 or explicit course-description scope; other visualization sources do not individually prove dashboard."),
            target("S8-QUALITY", "Data quality/outliers", [clo("AIL303m", "CLO3"), clo("DAP391m", "CLO2"), clo("AIL303m", "CLO1")]),
            target("S8-SQL", "Foundational SQL", [clo("DBI202", "CLO5"), clo("DBI202", "CLO6"), clo("ADY201m", "CLO1"), clo("ADY201m", "CLO7")], note="Each CLO has its own assessment; no overall SQL proficiency tier."),
            target("S8-PYTHON", "Python trong lựa chọn preferred Python OR R", [clo("PFP191", "CLO3"), clo("PFP191", "CLO4"), clo("PFP191", "CLO5"), clo("PFP191", "CLO6"), clo("PFP191", "CLO7"), clo("ADY201m", "CLO5"), clo("DAP391m", "CLO1")]),
            target("S8-R", "R được nhắc nhưng use-at-least-one không xác định lựa chọn cá nhân; preferred/OR được giữ", related=[clo("ADY201m", "CLO3"), metadata("ADY201m", "tools")], category="boundary", note="ADY metadata.tools says RStudio, not standalone R use; CLO3 explicitly names R."),
            target("S8-TOOLS", "Excel/Power BI/Tableau chưa được xác nhận trực tiếp là personal use", related=[metadata("MAS291", "tools"), metadata("MAD101", "tools"), clo("DAP391m", "CLO7")], category="boundary", note="MAS metadata names Excel as example; MAD tools does not name Excel/Power BI/Tableau. Split named tool assertions manually."),
            target("S8-GPA", "Không suy GPA>=7.5 từ CLO", category="boundary"),
            target("S8-ENGLISH", "Không suy chứng chỉ English B1 từ CLO", category="boundary"),
            target("S8-STUDENT", "Không suy final-year/recent graduate eligibility hoặc projects nghề nghiệp", category="boundary")]}]
    return rows


def context(root, profile, jd):
    review_path = f"{REVIEWS}/{jd}.json"
    review = p.b.read_json(root / review_path)
    validate_review(review, profile)
    source_trace = p.b.read_json(root / FIVE / "requests" / f"review-{jd}.json")
    actual = json.loads(source_trace["request"]["input"][0]["content"])["student_academic_profile"]
    if actual != profile or source_trace["request"]["model"] != "gpt-5.4" or source_trace["request"].get("reasoning") != {"effort": "high"}:
        raise p.ReviewError("Existing Review is not the intended enriched/high baseline")
    if source_trace["structured_output"] != review:
        raise p.ReviewError("Existing Review differs from its captured response")
    jd_text = load_jd(root / f"data/academic_benchmark/jds/{jd}.txt")
    if json.loads(source_trace["request"]["input"][1]["content"])["job_description"] != jd_text:
        raise p.ReviewError("Existing Review was generated for another JD")
    return [{"role": "user", "content": json.dumps({"student_academic_profile": profile}, ensure_ascii=False, allow_nan=False, indent=2)},
        {"role": "user", "content": json.dumps({"current_job_description": jd_text}, ensure_ascii=False)},
        {"role": "user", "content": json.dumps({"initial_academic_review": review}, ensure_ascii=False)}]


def validate_conditions(rows):
    if len(rows) != 32 or len({r["operation"] for r in rows}) != 32:
        raise p.ReviewError("Prototype requires 32 unique operations")
    groups = {}
    expected_prompts = {(arm, scope): p.instructions(arm, scope) for arm in ["A", "B"] for scope in ["S0", "S1"]}
    expected_schemas = {arm: p.b.fingerprint(p.structured_schema_format(model)) for arm, model in p.SCHEMAS.items()}
    for row in rows:
        if row["input_sha256"] != p.b.fingerprint(row["input"]) or row["instructions"] != expected_prompts[row["arm"], row["scope"]]:
            raise p.ReviewError("Frozen input/prompt mismatch")
        if row["instructions_sha256"] != p.b.digest(row["instructions"].encode()) or row["schema_sha256"] != expected_schemas[row["arm"]]:
            raise p.ReviewError("Frozen schema/prompt hash mismatch")
        groups.setdefault((row["phase"], row["scenario_id"], row["scope"]), []).append(row)
    if len(groups) != 16:
        raise p.ReviewError("Prototype pair count changed")
    by_id = {r["operation"]: r for r in rows}
    for group in groups.values():
        if len(group) != 2 or {r["arm"] for r in group} != {"A", "B"} or group[0]["input"] != group[1]["input"]:
            raise p.ReviewError("A/B input pairing changed")
    for row in rows:
        if row["repeat_of"]:
            original = by_id[row["repeat_of"]]
            if any(row[k] != original[k] for k in ["input", "instructions", "schema_sha256", "scope", "arm"]):
                raise p.ReviewError("Repetition differs from original condition")
    if {r["scenario_id"] for r in rows if r["holdout"]} != {"S4", "S8"}:
        raise p.ReviewError("Holdout allocation changed")


def forensic(root, profile):
    paths = [f"{FIVE}/requests/chat-JD05-2.json", f"{FIVE}/requests/chat-JD10-4.json", f"{FIVE}/requests/chat-JD11-1.json"]
    paths += [f"{RCA}/live/requests/{op}.json" for op in ["AB-S2", "E2-contaminated-D2", "E3-same-course", "E5-holdout", "D-S7-D2"]]
    records = []
    for name in paths:
        trace = p.b.read_json(root / name)
        messages = trace["request"]["input"]
        actual_profile = json.loads(messages[0]["content"])["student_academic_profile"]
        raw = json.loads(trace["raw_response"])
        texts = [c["text"] for item in raw.get("output", []) if item.get("type") == "message" for c in item.get("content", []) if c.get("type") == "output_text"]
        parsed = json.loads(texts[0])
        canonical_courses = {c["course_code"]: c for c in profile["courses"]}
        if parsed != trace["structured_output"] or any(canonical_courses.get(c["course_code"]) != c for c in actual_profile["courses"]):
            raise p.ReviewError("Forensic raw/parsed/profile mismatch")
        records.append({"artifact": name, "sha256": p.b.digest((root / name).read_bytes()),
            "exact_question": messages[-1]["content"], "original_output": parsed,
            "initial_review": json.loads(messages[2]["content"])["initial_academic_review"] if len(messages)>3 else None,
            "history_before_question": messages[3:-1], "raw_equals_parsed": True,
            "actual_profile_sha256": p.b.fingerprint(actual_profile),
            "actually_provided_courses": [c["course_code"] for c in actual_profile["courses"]],
            "semantic_authority": "canonical profile, not prior report labels"})
    return {"records": records, "observations": [
        "CI belongs to MAS291/CLO7, regression to CLO9; equal grades do not detect wrong topic binding.",
        "CSI representation belongs to CLO3, networking to CLO4.",
        "AB-S2 repeated metadata description identity with two legitimate exact excerpts: allow repetition internally.",
        "D-S7-D2 mapping omitted additional data-structure/OOP reply claims; remove independent reply generation in B.",
        "E3/E5 summaries expanded beyond the actual history; separate semantic support from authorized summary scope."],
        "hypotheses": ["Evidence-bound representation may reduce mapping/reply divergence; not established before live.",
                       "A provenance gate may detect wrong quote/identity while allowing unsupported claims with real quotes.",
                       "Explicit summary scope may help either representation independently."],
        "source_paths": paths}


def build_bundle(root):
    root = Path(root)
    profile = load_profile(root / PROFILE)
    if len(profile["courses"]) != 15 or sum(len(c["clos"]) for c in profile["courses"]) != 122:
        raise p.ReviewError("Expected enriched 15-course/122-CLO profile")
    scenarios = build_scenarios(root, profile)
    by_id = {r["scenario_id"]: r for r in scenarios}
    conditions = []
    # Counterbalance which arm runs first. No output-dependent scheduling.
    for phase, scope, ids in [("primary", "S0", ["S1", "S2", "S3", "S5", "S6", "S7", "S4", "S8"]),
                             ("scope", "S1", ["S5", "S6", "S7", "S8"]),
                             ("repeat", "S0", ["S1", "S5", "S6", "S8"])]:
        for number, sid in enumerate(ids):
            scenario = by_id[sid]
            messages = context(root, profile, scenario["jd"]) + copy.deepcopy(scenario["history"]) + [{"role": "user", "content": scenario["question"]}]
            for arm in (["A", "B"] if number % 2 == 0 else ["B", "A"]):
                conditions.append({"operation": f"{phase}-{sid}-{arm}-{scope}", "scenario_id": sid,
                    "phase": phase, "arm": arm, "scope": scope, "holdout": scenario["holdout"], "jd": scenario["jd"],
                    "summary_scope": scenario["summary_scope"], "input": copy.deepcopy(messages),
                    "input_sha256": p.b.fingerprint(messages), "instructions": p.instructions(arm, scope),
                    "instructions_sha256": p.b.digest(p.instructions(arm, scope).encode()),
                    "schema_sha256": p.b.fingerprint(p.structured_schema_format(p.SCHEMAS[arm])),
                    "asked_target_ids": [t["target_id"] for t in scenario["targets"]],
                    "repeat_of": f"primary-{sid}-{arm}-S0" if phase == "repeat" else None})
    validate_conditions(conditions)
    expected = []
    for scenario in scenarios:
        for t in scenario["targets"]:
            supplied = []
            for relation in ["direct", "related"]:
                for ref in t[f"acceptable_{relation}_sources"]:
                    value = canonical(profile, ref)
                    supplied.append({"reference": ref, "relation": relation, "canonical_source": value})
            expected.append({"scenario_id": scenario["scenario_id"], **t, "canonical_evidence": supplied,
                "sources_are_alternatives_not_all_required": True,
                "available_in_operations": [r["operation"] for r in conditions if r["scenario_id"] == scenario["scenario_id"]]})
    reconstruction = forensic(root, profile)
    protocol = {"version": 1, "semantic_assessment": "manual_only_no_llm_judge", "rubric": p.b.read_json(root / RUBRIC),
        "atomicity": "Split independent topic assertions and independently attributed CLO/score/band tuples. Split combined named technologies and sampling/CLT. A segment need not be atomic. Do not double-count a parent plus its leaves.",
        "denominators": {"asked": "Before live, expand coarse frozen targets into listed atomic leaves once. Record asked IDs separately from optional volunteered grades.",
            "answered": "Every independently assessable academic/JD assertion in the final text, including added topics and each assessment tuple.",
            "added": "Answered assertions not required by asked atoms; errors and counts reported separately.",
            "omission": "Missing essential asked content; not missing one acceptable alternative, optional grade detail or a source absent from input."},
        "fields": ["operation", "claim_id", "original_claim_verbatim", "span", "segment_index", "kind", "asked_atom_id", "origin_asked_or_added", "model_sources", "acceptable_sources", "provided_sources", "provenance", "semantic_support", "reference_completeness", "history_or_review_origin", "summary_scope", "taxonomy", "severity", "explanation"],
        "taxonomy": ["wrong_attribution", "missing_reference", "unsupported_specificity", "wrong_score_band", "verb_upgrade", "personal_tool_use", "history_propagation", "summary_invention", "out_of_scope_summary", "source_compression", "kind_misclassification", "omission"],
        "gate_metrics": "Two separate truth tables: literal source provenance versus manual semantic correctness. Gate pass does not imply entailment. Always report accepted P0 with withheld denominator and valid responses rejected.",
        "presentation": {"naturalness": ["natural Vietnamese", "paragraph coherence", "segmentation", "CLO identifier intrusion", "repetition", "unnecessary offers"],
                         "completeness": "Essential asked content retained; no reward for fewer claims/shorter answers", "rating": ["no_issue", "mild_degradation", "severe_degradation"]},
        "recommendation_rule": "Meaningful observed grounding/detection or summary preservation benefit with no severe availability/completeness/naturalness loss; separate S1 effects. If little/no raw error or inconsistent repetitions, report inconclusive, no reliability guarantee.",
        "failures": "Timeout/incomplete/refusal/parser failure is a completion failure, not automatically academic P0; inspect any available text manually."}
    # Freeze leaf units before inference, including broad holdout obligations.
    leaves = {t["target_id"]: [t["target_id"]] for t in expected}
    leaves["S8-TOOLS"] = ["S8-TOOLS-EXCEL", "S8-TOOLS-POWERBI", "S8-TOOLS-TABLEAU"]
    leaves["S8-WORKFLOW"] = ["S8-METHODOLOGY", "S8-BUSINESS-QUESTIONS", "S8-DATA-ANALYSIS"]
    leaves["S8-VIS"] = ["S8-VISUALIZATION", "S8-REPORTING", "S8-DASHBOARD"]
    leaves["S8-CLEAN"] = ["S8-CLEANING", "S8-WRANGLING-TRANSFORM"]
    leaves["S8-STUDENT"] = ["S8-ELIGIBILITY", "S8-PROJECT-LIMIT"]
    protocol["asked_atomic_leaves"] = leaves
    for row in conditions:
        row["asked_atomic_units"] = [leaf for t in row["asked_target_ids"] for leaf in leaves[t]]
        row["asked_atomic_denominator"] = len(row["asked_atomic_units"])
    files = {"scenarios.json": {"version": 1, "profile_path": PROFILE, "profile_sha256": p.b.digest((root / PROFILE).read_bytes()), "holdouts": ["S4", "S8"], "scenarios": scenarios},
        "histories.json": {"histories": {r["scenario_id"]: {"messages": r["history"], "sha256": p.b.fingerprint(r["history"])} for r in scenarios}},
        "expected_evidence.json": {"origin": "human_authored_canonical_before_live", "targets": expected},
        "conditions.json": {"conditions": conditions, "pairing": "Same full profile/JD/Review/history/question; only representation/contract and shared S1 change", "no_new_outputs_in_context": True},
        "annotation_protocol.json": protocol, "forensic_findings.json": reconstruction,
        "schemas.json": {arm: p.structured_schema_format(model) for arm, model in p.SCHEMAS.items()},
        "prompts.json": {f"{arm}-{scope}": p.instructions(arm, scope) for arm in ["A", "B"] for scope in ["S0", "S1"]}}
    sources = [PROFILE, f"{RCA}/histories.json", f"{RCA}/scenarios.json", f"{RCA}/plan.json", RUBRIC,
        "docs/academic_grounding_rca.md", "docs/academic_reasoning_five_jds_evaluation.md", *reconstruction["source_paths"]]
    for jd in sorted({r["jd"] for r in scenarios}):
        sources += [f"data/academic_benchmark/jds/{jd}.txt", f"{REVIEWS}/{jd}.json", f"{FIVE}/requests/review-{jd}.json"]
    return files, sources
