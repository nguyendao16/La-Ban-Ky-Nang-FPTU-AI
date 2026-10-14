"""Reconstruct historical requests and preserve human-selected forensic observations.

Historical annotations are an index of candidates, never automatic ground truth.
Semantic interpretations below are explicitly human-authored and independently
checked against actual supplied sources. Text searches only locate occurrences.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_academic_benchmark as b

RUNS = ["internship-20261013", "metadata-models-20261013", "reasoning-five-jds-20261013"]
LATEST = RUNS[-1]
TAXONOMY = {
    "within_course_misbinding": {"stage": "evidence_identification_or_attribution", "definition": "Topic/description from one outcome is attached to another valid identifier in the same course."},
    "cross_course_misbinding": {"stage": "evidence_identification_or_attribution", "definition": "A real topic in another course/outcome is attributed to a source that does not name it."},
    "missing_support": {"stage": "attribution_or_answer_construction", "definition": "A supported topic is asserted but its source is omitted from the returned evidence."},
    "compound_source_compression": {"stage": "answer_construction", "definition": "Multiple independently supported topics are merged while required distinct references are lost."},
    "source_family_confusion": {"stage": "provenance_or_interpretation", "definition": "Metadata is invented when absent, or a metadata-only fact is assigned an unsupported CLO."},
    "cognitive_verb_upgrade": {"stage": "academic_interpretation", "definition": "Understand/Explain/Explore is strengthened into Apply/Implement/mastery without source support."},
    "outcome_to_completed_project": {"stage": "academic_interpretation", "definition": "Intended graded outcome is used as proof of a completed personal artifact or employment."},
    "choice_to_personal_use": {"stage": "academic_interpretation", "definition": "Tools/examples/use-at-least-one become evidence that every named tool was personally used."},
    "performance_distortion": {"stage": "value_attribution_or_interpretation", "definition": "Score/band is wrong or a per-outcome band is generalized to a subject/course."},
    "jd_requirement_distortion": {"stage": "jd_interpretation", "definition": "Optional/preferred/OR/context is converted to a mandatory or AND requirement."},
    "unsupported_specificity": {"stage": "academic_interpretation_or_synthesis", "definition": "General coursework becomes a named framework, technology or data-domain claim."},
    "summary_invention": {"stage": "answer_construction", "definition": "An unsupported association is newly introduced during summary, rather than copied from history."},
    "history_propagation": {"stage": "context_or_answer_construction", "definition": "An earlier specific unsupported association is repeated; shared topic alone does not establish propagation."},
}


def trace_path(run, operation):
    return f"data/academic_benchmark/evaluations/{run}/requests/{operation}.json"


def api_output(trace):
    if not trace.get("raw_response"):
        return None
    raw = json.loads(trace["raw_response"])
    texts = [c["text"] for item in raw.get("output", []) if item.get("type") == "message"
             for c in item.get("content", []) if c.get("type") == "output_text"]
    return json.loads("".join(texts)) if texts else None


def actual_profile(trace):
    return json.loads(trace["request"]["input"][0]["content"])["student_academic_profile"]


def source_record(profile, course, identifier=None, field=None):
    item = next(c for c in profile["courses"] if c["course_code"] == course)
    if identifier is not None:
        outcome = next(c for c in item["clos"] if c["clo"] == identifier)
        return {"reference": {"course_code": course, "clo": identifier}, "source": outcome}
    return {"reference": {"course_code": course, "metadata_field": field},
            "source": (item.get("metadata") or {}).get(field), "source_present": field in (item.get("metadata") or {})}


def leaf_strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from leaf_strings(child, path + "/" + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaf_strings(child, path + "/" + str(index))


def occurrences(messages, phrases):
    found = []
    for index, message in enumerate(messages):
        try:
            value = json.loads(message["content"])
        except ValueError:
            value = message["content"]
        for path, text in leaf_strings(value):
            for line in text.splitlines():
                if any(phrase.casefold() in line.casefold() for phrase in phrases):
                    found.append({"message_index": index, "role": message["role"], "json_path": path,
                        "exact_text": line, "note": "Lexical occurrence only; not proof of an incorrect association."})
    return found


def build_forensics(root):
    source_fingerprints = {}
    def load(run, operation):
        path = trace_path(run, operation)
        source_fingerprints[path] = b.digest((root / path).read_bytes())
        trace = b.read_json(root / path)
        parsed_raw = api_output(trace)
        if parsed_raw is not None and trace.get("structured_output") != parsed_raw:
            raise ValueError(f"Raw API output and stored parsed output differ: {operation}")
        return trace
    index = []
    for run in RUNS:
        path = f"data/academic_benchmark/evaluations/{run}/manual_assessments.json"
        source_fingerprints[path] = b.digest((root / path).read_bytes())
        annotations = b.read_json(root / path)
        for operation, record in annotations["records"].items():
            index.append({"run": run, "operation": operation, "candidate_findings": record["findings"],
                          "status": "historical_candidate_not_independently_adjudicated_by_this_index"})
    primary = []
    definitions = [
        ("chat-JD05-2", "MAS291", "CLO7", "CLO9", "confidence intervals", ["within_course_misbinding"],
         "Lượt 1 trong actual history dẫn confidence intervals đúng vào MAS291/CLO7 và regression vào CLO9. Review không chứa attribution sai này. Lỗi xuất hiện lần đầu trong reply lượt 2; evidence cũng trả CLO9, nên không chỉ là thiếu aggregate citation."),
        ("chat-JD10-4", "MAS291", "CLO7", "CLO9", "confidence intervals", ["within_course_misbinding", "compound_source_compression", "summary_invention"],
         "Profile có CLO7 cho confidence intervals và CLO9 cho regression. Review và ba assistant replies trước lượt 4 không nêu confidence intervals. Summary tự thêm topic này, gộp với regression và dẫn CLO9. Không có bằng chứng truyền từ history của JD05."),
        ("chat-JD11-1", "CSI106", "CLO3", "CLO4", "data type is stored", ["within_course_misbinding"],
         "Đây là lượt Chat đầu, không có assistant history. Review dẫn CSI106/CLO4–5 đúng cho networking/OS. Reply trích câu data types thuộc CLO3 nhưng ghi CLO4; evidence cũng CLO4. Lỗi không thể được giải thích bằng việc sao chép một assistant reply trước đó trong session."),
    ]
    for operation, course, correct, incorrect, phrase, categories, assessment in definitions:
        trace = load(LATEST, operation)
        messages = trace["request"]["input"]
        output = trace["structured_output"]
        profile = actual_profile(trace)
        line = next(line for line in output["reply"].splitlines() if phrase.casefold() in line.casefold() and incorrect in line)
        review = json.loads(messages[2]["content"])["initial_academic_review"]
        actual_history = messages[3:-1]
        primary.append({"case_id": operation, "run": LATEST, "artifact": trace_path(LATEST, operation),
            "raw_equals_parsed": True, "exact_user_message": messages[-1]["content"],
            "exact_reply": output["reply"], "returned_evidence": output["evidence"], "initial_review": review,
            "history_before_failed_turn": actual_history, "actual_input_sha256": b.fingerprint(messages),
            "source_profile_sha256": b.fingerprint(profile), "input_tokens": trace["usage"]["input_tokens"],
            "api_status": trace["api_status"], "resolved_model": trace["response_model"],
            "canonical_evidence_present_in_actual_input": True,
            "correct_source": source_record(profile, course, correct), "wrong_source": source_record(profile, course, incorrect),
            "relevant_metadata": next(c.get("metadata") for c in profile["courses"] if c["course_code"] == course),
            "original_claim_verbatim": line, "claim_start_char": output["reply"].index(line),
            "first_incorrect_occurrence": {"part": "reply", "turn": int(operation.rsplit("-", 1)[1])},
            "earlier_incorrect_attribution_found_by_manual_review": False,
            "earlier_lexical_occurrences": occurrences(messages[:-1], [phrase]), "categories": categories,
            "severity": "P0", "independent_manual_assessment": assessment,
            "observable_limit": "We observe output associations, not the model's internal evidence-selection process."})

    # Selected original spans and human interpretations; no automatic semantic labels.
    selected = [
        (RUNS[0], "review-JD01", "comment", "PCA trong bối cảnh", ["missing_support", "cross_course_misbinding"],
         [("MAI391", "CLO5"), ("MAI391", "CLO6"), ("MAI391", "CLO7"), ("CPV301", "CLO8")],
         "Regression được gán MAI391/CLO5 đúng trong prose nhưng thiếu aggregate reference (P1); PCA bị gộp vào nhóm CLO1/8 và CLO5/7 không chứa PCA (P0). Có supporting sources ở profile; không phải mất nguồn trong request.", "P0"),
        (RUNS[0], "review-JD03", "comment", "bao gồm cả dữ liệu hình ảnh", ["unsupported_specificity"],
         [("DAP391m", "CLO1"), ("DAP391m", "CLO2")], "General data importing/cleaning được chuyển thành image-specific curriculum mà DAP1/2 không nêu.", "P0"),
        (RUNS[0], "review-JD05", "comment", "kiểm định giả thuyết", ["missing_support", "compound_source_compression"],
         [("MAS291", "CLO8"), ("MAI391", "CLO4")], "Row nhiều phương pháp bỏ aggregate sources cho hypothesis testing và optimization. MAS291/CLO1–9 trong prose đã bao gồm CLO8 đúng. Regrade P1 cho thiếu reference; không dùng omission này riêng lẻ làm bằng chứng model không tìm được nguồn hoặc gán sai ID.", "P1"),
        (RUNS[0], "review-JD07", "comment", "Thành tích good và excellent", ["performance_distortion"],
         [("DAP391m", "CLO1"), ("AIL303m", "CLO1")], "Hai refs được cite đều good (8.45 và 7.56), không phải một good và một excellent.", "P0"),
        (RUNS[0], "review-JD10", "comment", "pandas/numpy", ["unsupported_specificity"],
         [("ADY201m", "CLO5"), ("DAP391m", "CLO1")], "Broad Python/libraries không nêu pandas/numpy; model thêm named libraries. Đây là interpretation/synthesis, không chỉ selection.", "P0"),
        (RUNS[0], "review-JD12", "conclusion", "sử dụng một số công cụ phổ biến như GitHub", ["choice_to_personal_use", "summary_invention"],
         [("ADY201m", "CLO3")], "Comment trước đó đã thừa nhận use-at-least-one chưa xác nhận Git; conclusion lại khẳng định sử dụng GitHub. Có sự mất giới hạn khi tổng hợp.", "P0"),
        (RUNS[0], "chat-JD12-3", "reply", "đáp ứng tốt yêu cầu về SQL", ["cross_course_misbinding", "summary_invention"],
         [("DAP391m", "CLO7"), ("ADY201m", "CLO7")], "Reply chỉ cite DAP391m/CLO7 cho SQL; SQL/database access thực sự nằm ADY201m/CLO7 và các SQL outcomes khác.", "P0"),
        (RUNS[0], "chat-JD12-3", "reply", 'SQL là yêu cầu bắt buộc', ["jd_requirement_distortion"],
         [], "JD12 đặt SQL ở Nice-to-have; reply bịa Required SQL. Cần đối chiếu JD, không sửa bằng source retrieval CLO.", "P1"),
        (RUNS[0], "chat-JD14-1", "reply", "hiểu và triển khai các kỹ thuật", ["cognitive_verb_upgrade"],
         [("CPV301", "CLO3"), ("CPV301", "CLO8"), ("CPV301", "CLO9")], "Gộp implement face recognition với object detection; CPV9 chỉ Explain còn CPV8 có Implement.", "P0"),
        (LATEST, "chat-JD10-1", "reply", "cho thấy bạn đã làm workflow dự án", ["outcome_to_completed_project"],
         [("DAP391m", "CLO7")], "Intended capstone outcome và grade không kèm artifact dự án cá nhân. Có wording đã làm; giữ bối cảnh học thuật nên đánh giá P1, không bịa employment.", "P1"),
        (RUNS[1], "chat-JD11-gpt41", "reply", "có đề cập đến thao tác API", ["cross_course_misbinding", "history_propagation"],
         [("ADY201m", "CLO5"), ("ADY201m", "CLO7"), ("DAP391m", "CLO6"), ("DAP391m", "CLO7")],
         "Cụ thể attribution ADY7/API đã có trong frozen historical input và được nhắc lại sau yêu cầu sửa. Đây là propagation có occurrence cụ thể, khác với ba P0 mới.", "P0"),
    ]
    representative = []
    for run, operation, field, needle, categories, refs, assessment, severity in selected:
        trace = load(run, operation)
        output = trace["structured_output"]
        if field == "comment":
            row = next(r for r in output["requirement_reviews"] if needle in r["comment"])
            text, evidence = row["comment"], row["evidence"]
        else:
            text = output[field]
            row = None
            evidence = output.get("evidence")
        line = next(line for line in text.splitlines() if needle in line)
        messages = trace["request"]["input"]
        jd_key = "job_description" if field != "reply" else "current_job_description"
        jd = json.loads(messages[1]["content"])[jd_key]
        representative.append({"run": run, "operation": operation, "artifact": trace_path(run, operation),
            "raw_equals_parsed": True, "original_claim_verbatim": line, "selected_evidence": evidence,
            "original_requirement_row": row, "canonical_sources_from_actual_input": [source_record(actual_profile(trace), *ref) for ref in refs],
            "exact_jd": jd if "jd_requirement_distortion" in categories else None,
            "prior_matching_occurrences": occurrences(messages[2:-1], ["API", "GitHub", "SQL"]) if any(c in categories for c in ["history_propagation", "summary_invention"]) else [],
            "categories": categories, "severity": severity, "independent_manual_assessment": assessment,
            "first_occurrence_assessment": "Exact prior spans retained for reviewer comparison; do not infer propagation from topic overlap."})
    legacy = load(RUNS[1], "review-JD01-legacy-gpt41")
    legacy_row = next(r for r in legacy["structured_output"]["requirement_reviews"] if any("metadata_field" in e for e in r["evidence"]))
    representative.append({"run": RUNS[1], "operation": "review-JD01-legacy-gpt41", "artifact": trace_path(RUNS[1], "review-JD01-legacy-gpt41"),
        "original_requirement_row": legacy_row, "selected_evidence": legacy_row["evidence"],
        "actual_input_has_metadata": any("metadata" in c for c in actual_profile(legacy)["courses"]),
        "categories": ["source_family_confusion"], "severity": "P0",
        "independent_manual_assessment": "Metadata reference được tạo trong legacy input không có metadata. Validator đã chặn; không dùng enriched profile hiện tại để hợp thức hóa reference lịch sử."})
    controls = []
    for operation, note in [
        ("chat-JD05-1", "Cùng Mini medium dẫn MAS291/CLO7 confidence intervals và CLO9 regression đúng trong actual history trước lỗi."),
        ("chat-JD01-3", "Cùng model phân biệt CPV301/CLO8 Understand/Implement với CLO9 Explain đúng, cùng 8.81/excellent."),
        ("chat-JD11-3", "Cùng model đúng API ADY5/DAP5–6/AIL1 và không gán API cho CLO7."),
    ]:
        trace = load(LATEST, operation)
        controls.append({"operation": operation, "artifact": trace_path(LATEST, operation), "raw_equals_parsed": True,
            "model": trace["response_model"], "reply": trace["structured_output"]["reply"], "evidence": trace["structured_output"]["evidence"],
            "manual_observation": note, "limitation": "A correct conversational example is not an isolated source-identification experiment."})
    for name in ["academic_benchmark_evaluation.md", "academic_metadata_models_evaluation.md", "academic_reasoning_five_jds_evaluation.md"]:
        path = "docs/" + name
        source_fingerprints[path] = b.digest((root / path).read_bytes())
    atomic_annotations = []
    for case in primary:
        atomic_annotations.append({"operation": case["case_id"], "run": case["run"], "stage": "chat",
            "original_claim_verbatim": case["original_claim_verbatim"],
            "atomic_assertion": "confidence intervals attributed to MAS291/CLO9" if case["case_id"] != "chat-JD11-1" else "data types/bit patterns attributed to CSI106/CLO4",
            "origin_asked_or_added": "added", "model_sources": [case["wrong_source"]["reference"]],
            "acceptable_sources": [case["correct_source"]["reference"]],
            "actually_provided_sources": [case["correct_source"], case["wrong_source"]],
            "result": "wrong_attribution", "taxonomy": case["categories"], "severity": "P0",
            "explanation": case["independent_manual_assessment"], "reviewer": "Codex offline canonical recheck; no LLM judge request"})
    # Independently verifiable assertions, not one score per multi-claim paragraph.
    # Acceptable sources support the named topic/corrected fact, never all the
    # inspected sources indiscriminately. Negative assertions may have none.
    representative_atoms = [
        [("Linear regression named correctly as MAI391/CLO5 but aggregate reference omitted", [("MAI391", "CLO5")], "missing_support", "P1"),
         ("PCA compressed into CPV1/8 and MAI5/7 source group", [("MAI391", "CLO6")], "wrong_attribution", "P0")],
        [("DAP391m/CLO1 covers image-specific importing/cleaning", [], "interpretation_error", "P0"),
         ("DAP391m/CLO2 covers image-specific importing/cleaning", [], "interpretation_error", "P0")],
        [("Hypothesis testing without required aggregate source", [("MAS291", "CLO8")], "missing_support", "P1"),
         ("Continuous optimization without required aggregate source", [("MAI391", "CLO4")], "missing_support", "P1")],
        [("At least one of DAP391m/CLO1 and AIL303m/CLO1 has excellent achievement", [], "performance_distortion", "P0")],
        [("Cited broad Python sources establish pandas", [], "unsupported_specificity", "P0"),
         ("Cited broad Python sources establish numpy", [], "unsupported_specificity", "P0")],
        [("Use-at-least-one establishes personal GitHub use", [], "choice_to_personal_use", "P0")],
        [("DAP391m/CLO7 specifically establishes SQL", [("ADY201m", "CLO7"), ("ADY201m", "CLO1"), ("DBI202", "CLO5")], "wrong_attribution", "P0")],
        [("JD12 SQL is Required rather than Nice-to-have", [], "jd_requirement_distortion", "P1")],
        [("CPV301/CLO9 establishes implementation of face recognition", [], "cognitive_verb_upgrade", "P0")],
        [("DAP391m/CLO7 proves a completed personal workflow artifact", [], "outcome_to_completed_project", "P1")],
        [("ADY201m/CLO7 names API operations", [("ADY201m", "CLO5"), ("DAP391m", "CLO6")], "history_propagation", "P0")],
        [("DAP391m metadata description exists in the supplied legacy profile", [], "source_family_confusion", "P0")],
    ]
    for case, atoms in zip(representative, representative_atoms, strict=True):
        trace = load(case["run"], case["operation"])
        profile = actual_profile(trace)
        for assertion, accepted, result, severity in atoms:
            atomic_annotations.append({"operation": case["operation"], "run": case["run"],
                "stage": "chat" if case["operation"].startswith("chat-") else "review",
                "original_claim_verbatim": case.get("original_claim_verbatim") or (case.get("original_requirement_row") or {}).get("comment"),
                "atomic_assertion": assertion, "model_sources": case["selected_evidence"],
                "actually_provided_sources": case.get("canonical_sources_from_actual_input", []) + [source_record(profile, *ref) for ref in accepted],
                "actually_provided_sources_note": "Inspected/acceptable subset of actual input sources; full original profile remains in the raw trace.",
                "acceptable_sources": [source_record(profile, *ref)["reference"] for ref in accepted],
                "acceptable_source_values": [source_record(profile, *ref) for ref in accepted],
                "acceptable_sources_note": "Sources for the corrected topic/fact; [] means the original assertion is not established. Inspected contradictory sources are not automatically acceptable support.",
                "result": result, "taxonomy": case["categories"], "severity": severity,
                "explanation": case["independent_manual_assessment"],
                "reviewer": "Codex offline canonical recheck; no LLM judge request"})
    return {"origin": "offline_forensics_independent_manual_recheck", "historical_output_index": index,
        "primary_cases": primary, "representative_cases": representative, "successful_controls": controls,
        "atomic_annotations": atomic_annotations,
        "taxonomy": TAXONOMY, "source_fingerprints": source_fingerprints,
        "observations": ["All three new errors have correct source descriptions in actual supplied input.",
            "Wrong identifiers occur inside reply and aggregate evidence; no external selection trace exists.",
            "JD05 previously mapped the topic correctly; JD10 adds it in summary; JD11 has no assistant history.",
            "Current validators check identifiers/metadata presence/duplicates, not semantic support.",
            "No context-overflow, truncation or incomplete response explains these three completed outputs.",
            "Earlier failures include interpretation and answer-construction errors, not just evidence selection."],
        "hypotheses": {"H1": "Inconclusive: no isolated-identification experiments yet; successful same-model controls contradict uniform inability.",
            "H2": "Plausible but not established: observable earlier correct mapping can be lost; flat schema causality requires comparisons.",
            "H3": "Inconclusive: authoritative sources, Review and history coexist; absent assistant history rules out propagation as a universal explanation, not other context interference.",
            "H4": "Observed summary invention/compression occurs; causal contribution versus selection/attribution remains inconclusive without experiments."},
        "live_generation_count": 0, "no_hidden_reasoning_observed_or_requested": True}
