"""Human-authored targets and expected evidence, derived from canonical values.

No live output is used to construct another condition. Holdouts never appear in
prompt examples. These expected annotations are diagnostics, not production rules.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_academic_benchmark as b
from academic_review import load_profile, load_jd, validate_review
from academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS

PROFILE = "data/student_academic_profile.enriched.json"
PREVIOUS = "data/academic_benchmark/evaluations/reasoning-five-jds-20261013"
REVIEW_DIRECTORY = "data/academic_benchmark/initial_reviews/reasoning-five-jds-20261013"
RUBRIC = "data/academic_benchmark/evaluations/rubric.json"


def clo(course, identifier):
    return {"course_code": course, "clo": identifier}


def metadata(course, field):
    return {"course_code": course, "metadata_field": field}


def target(identifier, text, direct=(), related=(), relations=("direct",), atoms=(), note=""):
    return {"claim_id": identifier, "claim": text, "acceptable_direct_sources": list(direct),
        "acceptable_related_sources": list(related), "acceptable_relations": list(relations),
        "atomic_targets": list(atoms) or [text], "annotation_note": note}


def scenarios():
    return [
        {"scenario_id": "S1", "courses": ["MAS291"], "holdout": False, "jd": "JD05",
         "question": "Trong MAS291, CLO nào nói về confidence intervals, CLO nào nói về simple linear regression? Phân biệt hai nội dung và nêu điểm/achievement riêng.",
         "targets": [
             target("S1-CI", "MAS291 có nội dung confidence intervals", [clo("MAS291", "CLO7")]),
             target("S1-LR", "MAS291 có nội dung simple linear regression", [clo("MAS291", "CLO9")]),
             target("S1-BOTH", "MAS291 có cả confidence intervals và simple linear regression", [clo("MAS291", "CLO7"), clo("MAS291", "CLO9")],
                    atoms=["MAS291 confidence intervals", "MAS291 simple linear regression"], note="Compound requires support for both atoms; one reference does not cover both.")]},
        {"scenario_id": "S2", "courses": ["CSI106"], "holdout": False, "jd": "JD11",
         "question": "Trong CSI106, data types/bit patterns và networking nằm ở CLO nào? Hai mô tả có khác nhau không?",
         "targets": [target("S2-DATA", "CSI106 học data types and bit patterns", [clo("CSI106", "CLO3")]),
             target("S2-NET", "CSI106 học networking layers", [clo("CSI106", "CLO4")]),
             target("S2-BOTH", "CSI106 có data representation và networking", [clo("CSI106", "CLO3"), clo("CSI106", "CLO4")],
                    atoms=["CSI106 data representation", "CSI106 networking layers"])]},
        {"scenario_id": "S3", "courses": ["CPV301"], "holdout": False, "jd": "JD01",
         "question": "Object Detection, Face Recognition và Object Tracking trong CPV301 nằm ở đâu? Động từ học tập có xác nhận triển khai cả ba không?",
         "targets": [target("S3-OD", "CPV301 yêu cầu understand and implement object detection", [clo("CPV301", "CLO8")]),
             target("S3-FR", "CPV301 yêu cầu explain face recognition and object tracking", [clo("CPV301", "CLO9")],
                    atoms=["Explain face recognition", "Explain object tracking"]),
             target("S3-IMPLEMENT", "CPV301 xác nhận implement face recognition và object tracking", [], [clo("CPV301", "CLO9")],
                    relations=["related", "insufficient"], note="Explain is not Implement; contextual metadata also does not confirm personal implementation.")]},
        {"scenario_id": "S4", "courses": ["DBI202", "ADY201m", "DAP391m", "AIL303m"], "holdout": False, "jd": "JD05",
         "question": "SQL/T-SQL trong DBI202 và SQL/database access trong ADY201m nằm ở CLO nào, với điểm/achievement nào? DAP391m/CLO7 có nêu SQL không?",
         "targets": [target("S4-SQL", "DBI202 có SQL queries trên Microsoft SQL Server", [clo("DBI202", "CLO5")], [metadata("DBI202", "tools")]),
             target("S4-TSQL", "DBI202 có T-SQL programming", [clo("DBI202", "CLO6")]),
             target("S4-ADY", "ADY201m có SQL/database access trong guided project", [clo("ADY201m", "CLO7")], [clo("ADY201m", "CLO1")]),
             target("S4-DAP", "DAP391m/CLO7 nêu SQL/database access", [], [clo("DAP391m", "CLO7")], relations=["related", "insufficient"],
                    note="DAP7 is adjacent data-analysis workflow, not direct SQL evidence. ADY7 cannot establish what DAP7 says."),
             target("S4-BANDS", "DBI202/CLO5 và CLO6 có achievement basic", [clo("DBI202", "CLO5"), clo("DBI202", "CLO6")],
                    atoms=["DBI202/CLO5=5.96/basic", "DBI202/CLO6=5.96/basic"], note="Performance values are source fields, not quote substrings or a global SQL level.")]},
        {"scenario_id": "S5", "courses": ["MAI391", "MAE101", "MAS291", "ADY201m", "AIL303m"], "holdout": False, "jd": "JD05",
         "question": "Hồ sơ có gradient descent/continuous optimization, linear regression, PCA và SVM ở những nguồn nào? Nêu nguồn riêng và giữ achievement của từng CLO.",
         "targets": [target("S5-OPT", "Continuous optimization bằng gradient descent", [clo("MAI391", "CLO4")], [clo("MAE101", "CLO3")]),
             target("S5-LR", "Linear regression", [clo("MAI391", "CLO5"), clo("MAS291", "CLO9"), clo("AIL303m", "CLO4"), clo("ADY201m", "CLO6"), clo("ADY201m", "CLO7")],
                    note="These are alternative/complementary direct sources, not all mandatory citations. Cognitive scope differs by source."),
             target("S5-PCA", "PCA", [clo("MAI391", "CLO6"), metadata("MAI391", "description")], [clo("AIL303m", "CLO9")],
                    note="Metadata supports curriculum context; assessed Apply/score must use CLO6."),
             target("S5-SVM", "Support vector machine classification", [clo("MAI391", "CLO7"), metadata("MAI391", "description")],
                    note="Metadata cannot establish assessed performance or the Apply verb.")]},
        {"scenario_id": "S6", "courses": ["ADY201m", "DAP391m"], "holdout": False, "jd": "JD05",
         "question": "Git/GitHub, Jupyter/JupyterLab và RStudio xuất hiện ở đâu trong ADY201m/DAP391m? Danh sách đó và 'use at least one' có xác nhận mình đã sử dụng từng công cụ không?",
         "targets": [target("S6-CONTEXT", "ADY201m và DAP391m liệt kê Git và JupyterLab trong tools", [metadata("ADY201m", "tools"), metadata("DAP391m", "tools")],
                    atoms=["ADY201m tools names Git/JupyterLab", "DAP391m tools names Git/JupyterLab"], note="Direct for the listing fact only; Git/JupyterLab are not explicitly named by ADY CLO3."),
             target("S6-CHOICE", "ADY201m yêu cầu dùng ít nhất một data-science tool", [clo("ADY201m", "CLO3")]),
             target("S6-USE", "Profile xác nhận cá nhân đã dùng GitHub, JupyterLab và RStudio từng công cụ", [], [clo("ADY201m", "CLO3"), metadata("ADY201m", "tools"), metadata("DAP391m", "tools")],
                    relations=["related", "insufficient"], atoms=["Personal GitHub use", "Personal JupyterLab use", "Personal RStudio use"], note="Tool list and choice do not identify the selected tool or artifacts.")]},
        {"scenario_id": "S7", "courses": ["PFP191"], "holdout": True, "jd": "JD11",
         "question": "Trong PFP191, xử lý strings và đọc/ghi files nằm ở CLO nào? Python có xác nhận FastAPI không, và VS Code/Google Colab là evidence cá nhân hay metadata của môn?",
         "targets": [target("S7-STR", "PFP191 học Python strings", [clo("PFP191", "CLO4")]),
             target("S7-FILE", "PFP191 học Python file handling", [clo("PFP191", "CLO5")]),
             target("S7-FASTAPI", "Profile xác nhận FastAPI", [], [clo("PFP191", "CLO7"), clo("ADY201m", "CLO5"), clo("DAP391m", "CLO6")], relations=["related", "insufficient"]),
             target("S7-IDE", "Visual Studio Code và Google Colab được liệt kê ở PFP191 tools", [metadata("PFP191", "tools")],
                    note="The listing is direct contextual evidence; personal use is not confirmed.")]},
        {"scenario_id": "S8", "courses": ["CSD203"], "holdout": True, "jd": "JD11",
         "question": "CSD203 có graphs, sorting và hashing ở CLO nào? Điểm/achievement của từng CLO đó là gì, và có thể gọi cả môn excellent từ một CLO khác không?",
         "targets": [target("S8-GRAPH", "CSD203 graphs và graph algorithms", [clo("CSD203", "CLO5")]),
             target("S8-SORT", "CSD203 sorting algorithms", [clo("CSD203", "CLO6")]),
             target("S8-HASH", "CSD203 hashing", [clo("CSD203", "CLO7")]),
             target("S8-BANDS", "CSD203/CLO5–7 có achievement basic", [clo("CSD203", "CLO5"), clo("CSD203", "CLO6"), clo("CSD203", "CLO7")],
                    atoms=["CSD203/CLO5=6.06/basic", "CSD203/CLO6=6.06/basic", "CSD203/CLO7=6.06/basic"], note="Do not aggregate into a course-level performance label.")]},
    ]


def provided_profile(profile, codes):
    return {**copy.deepcopy(profile), "courses": [copy.deepcopy(c) for c in profile["courses"] if c["course_code"] in codes]}


def profile_message(profile):
    return {"role": "user", "content": json.dumps({"student_academic_profile": profile}, ensure_ascii=False, allow_nan=False, indent=2)}


def context(root, profile, jd):
    review_path = f"{REVIEW_DIRECTORY}/{jd}.json"
    review = b.read_json(root / review_path)
    validate_review(review, profile)
    return [profile_message(profile),
        {"role": "user", "content": json.dumps({"current_job_description": load_jd(root / f"data/academic_benchmark/jds/{jd}.txt")}, ensure_ascii=False)},
        {"role": "user", "content": json.dumps({"initial_academic_review": review}, ensure_ascii=False)}]


def synthetic_pair(profile, question, references):
    parts = []
    for ref in references:
        course = next(c for c in profile["courses"] if c["course_code"] == ref["course_code"])
        outcome = next(c for c in course["clos"] if c["clo"] == ref["clo"])
        parts.append(f"{ref['course_code']}/{ref['clo']}: CLO ghi {outcome['description']} Điểm {outcome['score']}, achievement {outcome['achievement']} thuộc outcome này.")
    return [{"role": "user", "content": question}, {"role": "assistant", "content": json.dumps({"reply": "\n".join(parts), "evidence": references}, ensure_ascii=False)}]


def build_fixtures(root, common_instructions, identification_instructions):
    profile = load_profile(root / PROFILE)
    rows = scenarios()
    source_paths = [PROFILE, "data/academic_benchmark/manifest.json", RUBRIC]
    source_paths += [f"data/academic_benchmark/jds/{jd}.txt" for jd in ["JD01", "JD05", "JD11"]]
    source_paths += [f"{REVIEW_DIRECTORY}/{jd}.json" for jd in ["JD01", "JD05", "JD11"]]
    historical_path = f"{PREVIOUS}/requests/chat-JD05-2.json"
    source_paths.append(historical_path)
    frozen_input = b.read_json(root / historical_path)["request"]["input"]
    if json.loads(frozen_input[0]["content"])["student_academic_profile"] != profile:
        raise ValueError("Historical source profile does not match canonical enriched profile")
    conditions = []

    def add(operation, family, ids, schema, label, instructions, messages, changes, repeat_of=None):
        selected = [s for s in rows if s["scenario_id"] in ids]
        item = {"operation": operation, "family": family, "scenario_ids": ids, "schema": schema,
            "context_condition": label, "holdout": any(s["holdout"] for s in selected), "instructions": instructions,
            "input": copy.deepcopy(messages), "input_sha256": b.fingerprint(messages),
            "prompt_sha256": b.digest(instructions.encode()), "changed_variables": changes,
            "target_claim_ids": [t["claim_id"] for s in selected for t in s["targets"]], "repeat_of": repeat_of}
        conditions.append(item)
        return item

    for scenario in rows:
        candidate = provided_profile(profile, scenario["courses"])
        targets = [{"claim_id": t["claim_id"], "claim": t["claim"]} for t in scenario["targets"]]
        add(f"AB-{scenario['scenario_id']}", "A/B", [scenario["scenario_id"]], "identification", "candidate_courses_only",
            identification_instructions, [profile_message(candidate), {"role": "user", "content": json.dumps({"targets": targets}, ensure_ascii=False)}],
            ["task restricted to source identification", "no natural Chat synthesis", "course candidate pool"])

    atomic_question = "Trong hồ sơ học thuật này, CLO nào xác nhận nội dung confidence intervals?"
    c_inputs = {
        "C1": [profile_message(provided_profile(profile, ["MAS291"]))],
        "C2": [profile_message(profile)],
        "C3": copy.deepcopy(frozen_input[:3]),
        "C4": copy.deepcopy(frozen_input[:-1]),
    }
    for name, messages in c_inputs.items():
        messages += [{"role": "user", "content": atomic_question}]
        item = add(name, "C", ["S1"], "chat", name, ACADEMIC_CHAT_INSTRUCTIONS, messages,
            ["context additions only relative to preceding C condition", "historical final question replaced with the same atomic question"])
        item["target_claim_ids"] = ["S1-CI"]

    for scenario_id in ["S1", "S6", "S7", "S8"]:
        scenario = next(s for s in rows if s["scenario_id"] == scenario_id)
        messages = context(root, profile, scenario["jd"]) + [{"role": "user", "content": scenario["question"]}]
        for name, schema in [("D1", "chat"), ("D2", "claim_level")]:
            add(f"D-{scenario_id}-{name}", "D", [scenario_id], schema, "full_profile_jd_review_no_history", common_instructions,
                messages, ["output representation/schema and field order; prompt/input identical within pair"])

    clean = synthetic_pair(profile, "Mình có học confidence intervals và hypothesis testing không?", [clo("MAS291", "CLO7"), clo("MAS291", "CLO8")])
    clean += synthetic_pair(profile, "Còn simple linear regression và PCA thì sao?", [clo("MAS291", "CLO9"), clo("MAI391", "CLO6")])
    contaminated = copy.deepcopy(clean)
    assistant = json.loads(contaminated[1]["content"])
    assistant["reply"] = assistant["reply"].replace("MAS291/CLO7:", "MAS291/CLO9:", 1)
    assistant["evidence"][0]["clo"] = "CLO9"
    contaminated[1]["content"] = json.dumps(assistant, ensure_ascii=False)
    histories = {
        "E1-clean": ("JD05", ["S1", "S5"], clean),
        "E2-contaminated": ("JD05", ["S1", "S5"], contaminated),
        "E3-same-course": ("JD05", ["S1"], synthetic_pair(profile, "Tóm các nội dung statistics mình đã học.", [clo("MAS291", c) for c in ["CLO5", "CLO6", "CLO7", "CLO8", "CLO9"]])),
        "E4-multiple-sources": ("JD05", ["S4", "S5"], synthetic_pair(profile, "SQL và optimization có nguồn nào?", [clo("DBI202", "CLO5"), clo("MAI391", "CLO4")])
            + synthetic_pair(profile, "PCA và SVM có nguồn nào?", [clo("MAI391", "CLO6"), clo("MAI391", "CLO7")])),
        "E5-holdout": ("JD11", ["S8"], synthetic_pair(profile, "Sorting và hashing trong CSD203 nằm ở đâu?", [clo("CSD203", "CLO6"), clo("CSD203", "CLO7")])),
    }
    history_targets = [
        target("H-HYP", "MAS291 có hypothesis testing", [clo("MAS291", "CLO8")]),
        target("H-DESCR", "MAS291 có descriptive statistics", [clo("MAS291", "CLO5")]),
        target("H-SAMPLING", "MAS291 có sampling distributions và central limit theorem", [clo("MAS291", "CLO6")]),
    ]
    history_target_ids = {
        "E1-clean": ["S1-CI", "S1-LR", "S5-PCA", "H-HYP"],
        "E2-contaminated": ["S1-CI", "S1-LR", "S5-PCA", "H-HYP"],
        "E3-same-course": ["H-DESCR", "H-SAMPLING", "S1-CI", "H-HYP", "S1-LR"],
        "E4-multiple-sources": ["S4-SQL", "S5-OPT", "S5-PCA", "S5-SVM"],
        "E5-holdout": ["S8-SORT", "S8-HASH"],
    }
    summary_question = "Bạn tóm tắt các nội dung học thuật đã trao đổi, kèm nguồn phù hợp và giữ đúng điểm/achievement nếu nhắc lại."
    history_artifact = {}
    for name, (jd, ids, history) in histories.items():
        messages = context(root, profile, jd) + history + [{"role": "user", "content": summary_question}]
        item = add(name, "E", ids, "chat", name, common_instructions, messages, ["human-authored isolated history; not outputs of a live condition"])
        item["target_claim_ids"] = history_target_ids[name]
        history_artifact[name] = {"history": history, "history_sha256": b.fingerprint(history),
            "origin": "human_authored_canonical_descriptions", "known_corruption": "CI source CLO7 changed to CLO9 in reply/reference only" if name == "E2-contaminated" else None}
        if name in ["E1-clean", "E2-contaminated"]:
            item = add(name + "-D2", "E-mapping", ids, "claim_level", name, common_instructions, messages,
                ["schema/field order only relative to same E condition"])
            item["target_claim_ids"] = history_target_ids[name]

    reverse = copy.deepcopy(profile)
    for course in reverse["courses"]:
        course["clos"].reverse()
    ordered = [profile_message(reverse), {"role": "user", "content": atomic_question}]
    item = add("C2-reversed", "ordering", ["S1"], "chat", "C2_reversed_clo_order", ACADEMIC_CHAT_INSTRUCTIONS,
               ordered, ["CLO array order only; course order/metadata/all source values unchanged"])
    item["target_claim_ids"] = ["S1-CI"]
    for original in ["C1", "C4", "E2-contaminated"]:
        base = next(c for c in conditions if c["operation"] == original)
        repeat = copy.deepcopy(base)
        repeat.update(operation=original + "-repeat", family="repeat", repeat_of=original,
            changed_variables=["independent predetermined repetition; identical prompt/input/schema/settings"])
        conditions.append(repeat)

    mapping = []
    for ref in [clo("MAS291", "CLO7"), clo("MAS291", "CLO9")]:
        course = next(c for c in profile["courses"] if c["course_code"] == ref["course_code"])
        outcome = next(c for c in course["clos"] if c["clo"] == ref["clo"])
        mapping.append({"statement": "confidence intervals" if ref["clo"] == "CLO7" else "simple linear regression",
                        "sources": [{**ref, "source_excerpt": outcome["description"]}], "score": outcome["score"], "achievement": outcome["achievement"]})
    base = next(c for c in conditions if c["operation"] == "D-S1-D1")
    messages = copy.deepcopy(base["input"])
    messages.insert(-1, {"role": "user", "content": json.dumps({"externally_verified_mapping": mapping,
        "origin": "human_verified_canonical_data_not_generated_by_another_condition"}, ensure_ascii=False)})
    add("D-S1-verified-mapping", "verified_mapping", ["S1"], "chat", "external_mapping_added", common_instructions,
        messages, ["externally supplied verified mapping added; not an observation of internal selection"])
    # Holdouts execute last. No prompts may be tuned after any outputs are seen.
    conditions = [c for c in conditions if not c["holdout"]] + [c for c in conditions if c["holdout"]]

    # Assessment units are human-authored before live, not inferred from model
    # replies. Compound identification targets share underlying topic units.
    topic_units = {
        "S1": ["confidence intervals", "simple linear regression"],
        "S2": ["data types/bit patterns", "networking"],
        "S3": ["object detection", "face recognition", "object tracking", "Explain versus Implement"],
        "S4": ["DBI202 SQL", "DBI202 T-SQL", "ADY201m SQL", "DAP391m/CLO7 SQL not established", "DBI202/CLO5 basic", "DBI202/CLO6 basic"],
        "S5": ["continuous optimization", "linear regression", "PCA", "SVM"],
        "S6": ["ADY201m tools listing", "DAP391m tools listing", "use-at-least-one choice", "individual GitHub use not established", "individual Jupyter use not established", "individual RStudio use not established"],
        "S7": ["strings", "file handling", "FastAPI not established", "IDE metadata listing", "personal IDE use not established"],
        "S8": ["graphs", "sorting", "hashing", "CLO5 basic", "CLO6 basic", "CLO7 basic"],
    }
    history_units = {
        "E1-clean": ["confidence intervals", "hypothesis testing", "simple linear regression", "PCA"],
        "E2-contaminated": ["confidence intervals", "hypothesis testing", "simple linear regression", "PCA"],
        "E3-same-course": ["descriptive statistics", "sampling/CLT", "confidence intervals", "hypothesis testing", "simple linear regression"],
        "E4-multiple-sources": ["SQL", "continuous optimization", "PCA", "SVM"],
        "E5-holdout": ["sorting", "hashing"],
    }
    for condition in conditions:
        base = condition["repeat_of"] or condition["operation"]
        if condition["family"] in ["C", "ordering"] or base in ["C1", "C4"]:
            units = ["confidence intervals source"]
        elif condition["context_condition"] in history_units:
            units = history_units[condition["context_condition"]]
        else:
            units = list(topic_units[condition["scenario_ids"][0]])
            if condition["schema"] == "identification" and condition["scenario_ids"] == ["S7"]:
                units.remove("personal IDE use not established")
            if condition["schema"] != "identification":
                if condition["scenario_ids"] == ["S1"]:
                    units += ["confidence intervals score", "confidence intervals achievement", "regression score", "regression achievement"]
                elif condition["scenario_ids"] == ["S8"]:
                    units += ["graphs score", "sorting score", "hashing score", "no inferred course-level excellent"]
        condition["asked_atomic_units"] = list(units)
        condition["asked_atomic_denominator"] = len(units)
        condition["assessment_note"] = "A source unit includes correct attribution. Grade/verb properties volunteered beyond these asked units are separate added claims. History grade retention is conditional on mentioning it, not a required omission."

    expected = []
    expected_rows = rows + [{"scenario_id": "history-preservation", "targets": history_targets}]
    for scenario in expected_rows:
        for item in scenario["targets"]:
            evidence = []
            for relation, refs in [("direct", item["acceptable_direct_sources"]), ("related", item["acceptable_related_sources"])]:
                for ref in refs:
                    course = next(c for c in profile["courses"] if c["course_code"] == ref["course_code"])
                    value = next(c for c in course["clos"] if c["clo"] == ref["clo"]) if "clo" in ref else course["metadata"][ref["metadata_field"]]
                    evidence.append({"reference": ref, "relation": relation, "canonical_source": value})
            available = {}
            for condition in conditions:
                if item["claim_id"] not in condition["target_claim_ids"]:
                    continue
                pool = json.loads(condition["input"][0]["content"])["student_academic_profile"]
                codes = {c["course_code"] for c in pool["courses"]}
                available[condition["operation"]] = [e["reference"] for e in evidence if e["reference"]["course_code"] in codes]
            expected.append({"scenario_id": scenario["scenario_id"], **item, "canonical_evidence": evidence,
                "available_acceptable_sources_by_condition": available})
    return {"annotation_protocol.json": {"version": 1, "semantic_assessment": "manual_only", "rubric_path": RUBRIC,
            "rubric_sha256": b.digest((root / RUBRIC).read_bytes()), "severity": b.read_json(root / RUBRIC)["severity"],
            "claim_record_fields": ["operation", "stage", "claim_id", "original_claim_verbatim", "span", "origin_asked_or_added",
                "model_sources", "acceptable_sources", "actually_provided_sources", "quote_provenance", "semantic_support",
                "result", "taxonomy", "severity", "explanation", "reviewer"],
            "metrics": {"asked": "Frozen asked_atomic_units, each once; do not count a compound plus its atoms twice.",
                "answered": "Manually split every factual assertion in final reply, including summaries; independently verify scores, bands, verbs and implied use.",
                "added": "Answered atomic assertions not required by asked units; report counts/errors separately, not extra credit.",
                "omission": "Asked assertion omitted or unanswered; do not penalize an excluded source, nonessential alternative citation or optional grade detail.",
                "wrong_attribution": "Incorrect source-topic association, including a verbatim quote attached to another source.",
                "interpretation_error": "Unsupported cognitive verb, curriculum-to-personal-use, framework, project or achievement inference.",
                "summary_invention": "New unsupported assertion/association first present in summary, after inspecting prior Review/history.",
                "history_propagation": "Same specific incorrect association recurs; topic overlap alone is insufficient.",
                "source_compression": "Combined independent claims lose necessary distinct support; separate missing reference from false binding."},
            "limitations": ["Exact quote is provenance, not entailment or semantic acceptance.",
                "Empty but schema-valid output is not complete or correct.", "Unknown/incomplete/parser/provenance failures are not automatically academic P0.",
                "A/B observable selections do not expose private model reasoning.", "Do not tune after live output or replace frozen expected evidence silently."]},
        "scenarios.json": {"version": 1, "profile_path": PROFILE, "profile_sha256": b.digest((root / PROFILE).read_bytes()),
            "holdouts": ["S7", "S8"], "holdouts_not_used_for_prompt_design": True, "scenarios": rows},
        "expected_evidence.json": {"origin": "human_authored_from_canonical_fields_not_llm_ground_truth", "claims": expected,
            "notes": ["Alternative sources are not all mandatory references.", "Compound claims require each independent atom.",
                "Absence/related and metadata fact versus personal-use distinctions require manual semantic review.",
                "Additional semantically valid sources may be independently adjudicated with exact canonical support; record additions rather than silently rewriting frozen expectations."]},
        "histories.json": {"histories": history_artifact, "verified_mapping": mapping},
        "conditions.json": {"version": 1, "conditions": conditions, "source_paths": source_paths,
            "comparability_notes": ["C uses the exact production prompt/schema, but replaces the historical question with an atomic question.",
                "A/B changes task and schema, so contrast with Chat is not a schema-only causal comparison.",
                "D/E share a diagnostic copy of the production prompt with only the output contract changed; D2 also changes output order and size.",
                "E1 versus E2 changes one attribution in reply and corresponding reference; other E histories are distinct scenarios, not causal ablations.",
                "Ordering is one exploratory check. Three predetermined repeats yield only two observations per repeated condition.",
                "External verified mapping is an intervention, not evidence of hidden model selection.",
                "No diagnostic output becomes another condition's history; synthetic histories are isolated from production sessions."]}}
