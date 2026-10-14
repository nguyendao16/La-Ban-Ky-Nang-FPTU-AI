"""Post-inference manual annotations; no API client or semantic judge.

Topic/source assignments below are reviewer decisions after reading every raw
output and canonical source. String lookup only anchors those decisions in the
original public text; it is not an entailment algorithm or an inference change.
Frozen runner/prompts/schemas/fixtures are never edited by this module.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from research.diagnostics import evidence_bound_response as p
from research.diagnostics.evidence_bound_results import summarize

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / p.DIRECTORY
PROFILE = p.b.read_json(ROOT / "data/student_academic_profile.enriched.json")
EXPECTED = {c["target_id"]: c for c in p.b.read_json(DIRECTORY / "expected_evidence.json")["targets"]}


def ref(name):
    course, field = name.split("/")
    return {"course_code": course, "clo" if field.startswith("CLO") else "metadata_field": field}


def canonical(name):
    reference = ref(name)
    course = next(c for c in PROFILE["courses"] if c["course_code"] == reference["course_code"])
    return next(c for c in course["clos"] if c["clo"] == reference["clo"]) if "clo" in reference else course["metadata"][reference["metadata_field"]]


class Review:
    def __init__(self, condition):
        self.condition = condition
        self.op, self.arm = condition["operation"], condition["arm"]
        self.trace = p.b.read_json(DIRECTORY / "live/requests" / f"{self.op}.json")
        raw = json.loads(self.trace["raw_response"])
        texts = [c["text"] for x in raw.get("output", []) if x["type"] == "message"
                 for c in x.get("content", []) if c["type"] == "output_text"]
        self.original = json.loads(texts[0]) if texts else None
        assert self.original == self.trace.get("structured_output")
        self.reply = "" if self.original is None else self.original["reply"] if self.arm == "A" else p.raw_render(p.EvidenceBoundResponse.model_validate(self.original))["reply"]
        self.aggregate = [] if self.original is None else self.original["evidence"] if self.arm == "A" else p.raw_render(p.EvidenceBoundResponse.model_validate(self.original))["evidence"]
        self.claims, self.findings, self.answered = [], [], set()
        self.offsets = []
        offset = 0
        for s in self.original.get("segments", []) if self.original else []:
            self.offsets.append((offset, offset + len(s["text"]), s))
            offset += len(s["text"]) + 2

    def add(self, anchor, names=(), *, target=None, segment=None, relation="direct", normalized=None, start=0):
        refs = [ref(n) for n in names]
        for name in names:
            canonical(name)  # Actual canonical data, not remembered grade/description.
        base, text = 0, self.reply
        if segment is not None:
            base, end, s = self.offsets[segment]
            text = self.reply[base:end]
        position = text.casefold().find(anchor.casefold(), start)
        if position < 0:
            raise ValueError(f"Manual anchor absent in {self.op}: {anchor}")
        left, right = base + position, base + position + len(anchor)
        local = self.aggregate
        kind, selected_segment = None, None
        if self.arm == "B":
            selected_segment = next(i for i, (lo, hi, _) in enumerate(self.offsets) if lo <= left < hi)
            s = self.offsets[selected_segment][2]
            kind = s["kind"]
            local = [{k: v for k, v in source.items() if k != "source_excerpt"} for source in s["academic_sources"]]
        availability = [r for r in refs if any(r == actual for actual in self.aggregate)]
        completeness = "not_required_for_absence" if relation == "correct_absence" else "complete" if all(r in local for r in refs) else "aggregate_only_local_missing" if len(availability) == len(refs) else "missing_aggregate_reference"
        asked = target in self.condition["asked_atomic_units"] and target not in self.answered
        if asked:
            self.answered.add(target)
        claim = {"claim_id": f"{self.op}-C{len(self.claims)+1:03}", "operation": self.op,
            "original_claim_verbatim": self.reply[left:right], "span": [left, right],
            "claim_context": text, "normalized_claim": normalized or anchor,
            "segment_index": selected_segment, "kind": kind,
            "asked_atom_id": target if asked else None, "origin_asked_or_added": "asked" if asked else "added",
            "model_sources": copy.deepcopy(local), "aggregate_sources": copy.deepcopy(self.aggregate),
            "acceptable_sources": refs, "provided_sources": refs,
            "provided_source_pool": "conditions.json input[0], full 15-course/122-CLO enriched profile",
            "canonical_support": [{"reference": ref(n), "value": canonical(n)} for n in names],
            "provenance": "valid_source_identity; B exact quotations checked separately by gate",
            "semantic_support": relation, "reference_completeness": completeness,
            "history_or_review_origin": "asked/history topic" if asked else "additional supported detail or restatement",
            "summary_scope": "within_requested_scope", "taxonomy": [], "severity": None,
            "explanation": "Reviewer verified this observable assertion against the actually provided canonical source; string anchoring is not semantic judging."}
        if completeness == "aggregate_only_local_missing":
            claim.update(taxonomy=["kind_misclassification", "local_binding_missing"], severity="P1",
                explanation="Academic fact is correct and aggregate evidence is present, but this B segment declares no local source. This is B-contract correspondence, not a false academic fact.")
        self.claims.append(claim)
        return claim

    def group(self, name, terms, *, segment=None, target=None):
        # The term list/source association is manually selected for each output.
        # Optional terms are included only if actually asserted in public text.
        text = self.reply if segment is None else self.offsets[segment][2]["text"]
        marker = name if name in text else name.split("/")[1]
        start = text.find(marker)
        if start < 0:
            start = 0
        remaining = text[start:]
        for number, term in enumerate(terms):
            position = remaining.casefold().find(term.casefold())
            if position < 0:
                # Topic often precedes the CLO identifier in the same sentence.
                position = text.casefold().find(term.casefold())
                if position < 0:
                    continue
                selected_start = position
            else:
                selected_start = start + position
            self.add(term, [name], segment=segment, target=target if number == 0 else None,
                relation="metadata" if name.endswith(("/description", "/tools")) else "direct",
                normalized=f"{name} curriculum/outcome: {term}", start=selected_start)

    def grade(self, name, *, segment=None, band_only=False):
        outcome = canonical(name)
        text = self.reply if segment is None else self.offsets[segment][2]["text"]
        marker = name if name in text else name.split("/")[1]
        start = max(0, text.find(marker))
        anchor = "đều có achievement excellent" if band_only else str(outcome["score"])
        if text.find(anchor, start) < 0:
            start = 0
        target = {"MAS291/CLO7": "S1-CI-GRADE", "MAS291/CLO9": "S1-LR-GRADE"}.get(name) if self.condition["scenario_id"] == "S1" else None
        claim = self.add(anchor, [name], segment=segment, target=target, start=start,
            normalized=f"{name} assessment: " + (outcome["achievement"] if band_only else f"{outcome['score']}/{outcome['achievement']}"))
        claim["assessment"] = {"actual_score": outcome["score"], "actual_achievement": outcome["achievement"],
            "score_stated": not band_only, "grade_tuple_matches_canonical": True}
        if band_only:
            claim["taxonomy"].append("assessment_comparison_missing_score")
            claim["severity"] = "P1"
            claim["explanation"] = "Band is correct. Grouped comparison states excellent for CLO1–6 without their individual numeric scores, contrary to the frozen production comparison rule; no wrong grade is alleged."

    def finding(self, identifier, severity, taxonomy, anchor, explanation, sources=()):
        pos = self.reply.find(anchor)
        assert pos >= 0, (self.op, anchor)
        self.findings.append({"finding_id": identifier, "operation": self.op, "scenario_id": self.condition["scenario_id"],
            "severity": severity, "taxonomy": taxonomy, "original_claim_verbatim": anchor, "span": [pos, pos+len(anchor)],
            "canonical_sources": [{"reference": ref(n), "value": canonical(n)} for n in sources],
            "explanation": explanation})

    def scope_violation(self, anchor):
        self.finding(self.op+"-scope", "P1", "out_of_scope_summary", anchor,
            "Actual preceding dialogue covers MAS291/CLO5–9 only. Added Python/SQL/data-analysis/ML topics come from Review/profile, not that dialogue. Academic source facts are correct, but expansion is unauthorized for the frozen conversation-summary scope.", ["MAS291/CLO5", "MAS291/CLO6", "MAS291/CLO7", "MAS291/CLO8", "MAS291/CLO9"])
        for claim in self.claims:
            refs = claim["acceptable_sources"]
            if any(r["course_code"] != "MAS291" for r in refs):
                claim["summary_scope"] = "supported_but_outside_conversation_scope"
                claim["history_or_review_origin"] = "profile/Initial Review only; new to this summary"
                claim["taxonomy"].append("out_of_scope_summary")
                claim["severity"] = "P1"

    def finalize(self):
        if self.original is None:
            assert self.trace["api_status"] == "incomplete"
            return {**self.condition_fields(), "review_status": "completed", "completion_assessment": "max_output_tokens; no public text to assess",
                "claims": [], "answered_asked_units": [], "omissions": [], "unassessable_asked_units": self.condition["asked_atomic_units"],
                "raw_semantic_p0": None, "p1": 0, "p2": 0, "raw_semantically_correct": None,
                "source_provenance_correct": None, "academic_facts_correct": None, "scope_correct": None,
                "naturalness": None, "completeness": "not_assessable_no_reply", "usable_response": False,
                "findings": [], "reviewer": "Codex manual inspection; no API judge", "raw_equals_parsed": True,
                "explanation": "Completion failure with known usage; no academic P0/omission or semantic correctness invented for an absent answer."}
        missing = [t for t in self.condition["asked_atomic_units"] if t not in self.answered]
        scope_ok = not any(f["taxonomy"] == "out_of_scope_summary" for f in self.findings)
        binding_ok = all(c["reference_completeness"] not in {"aggregate_only_local_missing", "missing_aggregate_reference"} for c in self.claims)
        return {**self.condition_fields(), "review_status": "completed", "claims": self.claims,
            "answered_asked_units": sorted(self.answered), "omissions": missing, "unassessable_asked_units": [],
            "raw_semantic_p0": 0, "p1": sum(f["severity"] == "P1" for f in self.findings), "p2": sum(f["severity"] == "P2" for f in self.findings),
            "raw_semantically_correct": True, "academic_facts_correct": True, "source_provenance_correct": True,
            "scope_correct": scope_ok, "local_segment_binding_complete": binding_ok,
            "naturalness": "mild_degradation" if any(f["severity"] == "P2" for f in self.findings) else "no_issue",
            "completeness": "essential_requested_content_missing" if missing else "complete_requested_topics",
            "usable_response": scope_ok and not missing,
            "prototype_contract_conformant": scope_ok and not missing and binding_ok and not any(c["taxonomy"] == ["assessment_comparison_missing_score"] for c in self.claims),
            "findings": self.findings, "raw_equals_parsed": True,
            "reviewer": "Codex manual inspection of raw public text, sources, history and Review; no API judge",
            "explanation": "Academic factual truth is separate from scope, local binding and completeness. P1 policy/contract failures do not become invented false academic facts. Mild P2 does not by itself make a response unusable."}

    def condition_fields(self):
        return {k: self.condition[k] for k in ["operation", "scenario_id", "arm", "scope", "phase", "holdout", "asked_atomic_units"]}


def basic(review):
    sid, op = review.condition["scenario_id"], review.op
    if sid == "S1":
        review.group("MAS291/CLO7", ["confidence intervals", "population parameters", "differences between population parameters"], target="S1-CI")
        review.group("MAS291/CLO9", ["simple linear regression", "prediction", "interpretation"], target="S1-LR")
        review.grade("MAS291/CLO7"); review.grade("MAS291/CLO9")
        if review.arm == "B":
            last = len(review.offsets)-1
            if review.offsets[last][2]["kind"] == "general_explanation":
                review.group("MAS291/CLO7", ["confidence intervals"], segment=last)
                review.group("MAS291/CLO9", ["simple linear regression"], segment=last)
                if "9.43" in review.offsets[last][2]["text"]:
                    review.grade("MAS291/CLO7", segment=last); review.grade("MAS291/CLO9", segment=last)
                anchor = review.offsets[last][2]["text"]
                review.finding(op+"-binding", "P1", "kind_misclassification", anchor,
                    "Source-free general_explanation repeats specific academic/CLO facts (and repeat grades). They are true and aggregate evidence is correct; the promised segment-local binding is incomplete.", ["MAS291/CLO7", "MAS291/CLO9"])
    elif sid == "S3":
        review.group("CPV301/CLO8", ["object detection"], target="S3-OD")
        review.group("CPV301/CLO9", ["face recognition"], target="S3-FACE")
        review.group("CPV301/CLO9", ["object tracking"], target="S3-TRACK")
        review.group("CPV301/description", ["object detection", "object recognition", "object tracking"])
        anchor = "câu trả lời là **không**" if review.arm == "A" else "chưa có CLO nào nói rõ triển khai hai phần đó"
        review.add(anchor, ["CPV301/CLO8", "CPV301/CLO9"], target="S3-LIMIT", relation="correct_absence",
            normalized="No assessed Implement outcome for face recognition/tracking; keep Explain versus Implement")
        if review.arm == "B":
            review.group("CPV301/CLO8", ["object detection"], segment=1)
            review.group("CPV301/CLO9", ["face recognition", "object tracking"], segment=1)
            review.finding(op+"-binding", "P1", "kind_misclassification", review.offsets[1][2]["text"],
                "Correct verb/source distinction is repeated in a source-free general_explanation. Academic facts remain correct; B-local binding is incomplete.", ["CPV301/CLO8", "CPV301/CLO9"])
    elif sid == "S5":
        for name, term, target in [("MAS291/CLO7", "confidence intervals", "S5-CI"), ("MAS291/CLO8", "hypothesis testing", "S5-HYP"),
                                   ("MAS291/CLO9", "simple linear regression", "S5-LR"), ("MAI391/CLO6", "PCA", "S5-PCA")]:
            review.group(name, [term], target=target); review.grade(name)
        if op == "scope-S5-A-S1":
            for name, terms in [("MAS291/CLO7", ["means", "proportions", "differences between two means/proportions"]),
                ("MAS291/CLO8", ["formulating hypotheses", "critical values", "test statistics", "p-values", "testing errors"]),
                ("MAS291/CLO9", ["least-squares estimation", "sums of squares", "regression equations", "correlation coefficients", "significance tests"]),
                ("MAI391/CLO6", ["covariance matrices", "maximum-variance subspaces", "low-rank matrix approximation", "projection perspectives", "eigenvector computation", "key practical PCA steps"])]:
                review.group(name, terms)
        if "Nếu cần" in review.reply:
            review.finding(op+"-offer", "P2", "redundant_offer", review.reply[review.reply.index("Nếu cần"):], "Offers another summary immediately after the requested summary; mild redundancy only.")
    elif sid == "S7":
        review.group("CSD203/CLO6", ["sorting"], target="S7-SORT")
        review.group("CSD203/CLO7", ["hashing"], target="S7-HASH")
        review.group("CSD203/CLO6", ["selection sort", "insertion sort", "bubble sort", "quicksort", "merge sort", "heap sort", "bucket sort", "radix sort"])
        review.group("CSD203/CLO7", ["hash tables", "hash functions", "collision handling", "load factors", "rehashing", "efficiency considerations", "Python hash table implementation"])
        review.grade("CSD203/CLO6");review.grade("CSD203/CLO7")


def other(review):
    if review.condition["scenario_id"] == "S2":
        review.group("CSI106/CLO3", ["bit patterns" if review.arm == "B" else "bit patterns", "operations on data"], target="S2-DATA")
        review.group("CSI106/CLO4", ["tầng mạng" if review.arm == "B" else "layers in networking"], target="S2-NET")
        review.group("CSI106/description", ["Numbering system & data representation"])
        if review.arm == "B":
            for base in ["decimal (10)", "binary (2)", "octal (8)", "hexadecimal (16)"]:
                review.add("10/2/8/16", ["CSI106/CLO2"], normalized=f"CSI106/CLO2 covers conversion involving {base}")
        else:
            review.group("CSI106/CLO2", ["decimal", "binary", "octal", "hexadecimal"])
        anchor = "nền tảng để hiểu" if review.arm == "B" else "Điều này hỗ trợ tư duy"
        review.add(anchor, ["CSI106/CLO3", "CSI106/CLO4"], target="S2-LINK", relation="related", normalized="Foundational relationship to backend, without named-framework/professional-use inference")
        for term in (["FastAPI", "SQLAlchemy", "event-driven backend"] if review.arm == "B" else ["FastAPI", "SQLAlchemy", "REST API design", "event-driven systems", "queues/caching", "cloud deployment"]):
            review.add(term, ["CSI106/CLO3", "CSI106/CLO4"], relation="correct_absence", normalized=f"CSI106 alone does not directly establish {term}")
        if review.arm == "B":
            for term in ["FastAPI", "SQLAlchemy", "schemas/queries/caching", "AI and enterprise services", "event-driven systems", "pipelines"]:
                review.add(term, segment=1, relation="jd_requirement", normalized=f"Actual JD responsibility: {term}")
            review.finding(review.op+"-english", "P2", "excessive_english_quote", review.offsets[1][2]["text"],
                "A standalone verbatim English responsibilities paragraph lacks a conversational Vietnamese transition; no JD fact or modality error.")
    elif review.condition["scenario_id"] == "S4":
        for term, target in [("C programming tools", "S4-C"), ("Maxima", "S4-MAXIMA")]:
            review.add(term, ["MAD101/tools"], target=target, relation="metadata", normalized=f"MAD101 metadata.tools lists {term} as example, not individual use")
        anchor = "không** xác nhận" if review.arm == "A" else "chưa xác nhận bạn đã dùng riêng từng công cụ"
        for target, tool in [("S4-USE-C", "C programming tools"), ("S4-USE-MAXIMA", "Maxima")]:
            review.add(anchor, ["MAD101/tools"], target=target, relation="correct_absence", normalized=f"Individual use of {tool} is unverified")
        anchor = "không thấy CLO nào tách riêng" if review.arm == "A" else "chưa cho thấy có đánh giá tách biệt"
        review.add(anchor, ["MAD101/tools"], target="S4-GRADE", relation="correct_absence", normalized="No individually assessed score for each named tool")
        if review.arm == "A":
            for name, terms in [("MAD101/CLO1", ["mệnh đề", "vị từ"]), ("MAD101/CLO2", ["tập hợp", "hàm", "dãy"]),
                ("MAD101/CLO3", ["độ phức tạp thuật toán"]), ("MAD101/CLO4", ["số học mô-đun"]),
                ("MAD101/CLO5", ["quy nạp", "đệ quy"]), ("MAD101/CLO6", ["đếm"]), ("MAD101/CLO7", ["đồ thị"]), ("MAD101/CLO8", ["cây"])]:
                review.group(name, terms)
            review.finding(review.op+"-offer", "P2", "redundant_offer", review.reply[review.reply.index("Nếu bạn muốn"):], "Answer already resolves listing/use/assessment; a further generic source-selection offer is unnecessary.")


STATISTICS = {
    "MAS291/CLO5": ["numerical summaries", "visual displays", "descriptive statistics", "stem-and-leaf", "frequency distributions", "histograms", "box plots", "quartiles", "outlier identification", "outliers", "time sequence plots"],
    "MAS291/CLO6": ["sampling distributions", "point estimation", "Central Limit Theorem"],
    "MAS291/CLO7": ["confidence intervals", "population parameters", "differences between population parameters", "means", "proportions"],
    "MAS291/CLO8": ["hypothesis testing", "formulating hypotheses", "critical values", "test statistics", "p-values", "testing errors", "means/proportions"],
    "MAS291/CLO9": ["simple linear regression", "prediction", "interpretation", "least-squares estimation", "sums of squares", "regression equations", "correlation coefficients"]}
STAT_TARGETS = {"MAS291/CLO5": "S6-DESCR", "MAS291/CLO6": "S6-SAMPLING", "MAS291/CLO7": "S6-CI", "MAS291/CLO8": "S6-HYP", "MAS291/CLO9": "S6-LR"}


def statistics(review):
    for name, terms in STATISTICS.items():
        # CLO5 short summaries may use 'mô tả dữ liệu' without the named statistics term.
        selected = terms if name != "MAS291/CLO5" else ["numerical summaries", *terms[1:]]
        segment = 1 if review.arm == "B" and review.op in EXTRA_GROUPS else 0 if review.arm == "B" else None
        review.group(name, selected, target=STAT_TARGETS[name], segment=segment);review.grade(name, segment=segment)
    if review.op == "primary-S6-B-S0":
        review.add("Verify claims about population parameters", ["MAS291/CLO8"], segment=1, target="S6-HYP",
            normalized="Correct shortened CLO8 statistical-verification description; preserves the discussed hypothesis-testing outcome without its English label")
    if "Central Limit Theorem" in review.reply:
        review.add("Central Limit Theorem", ["MAS291/CLO6"], target="S6-CLT", normalized="MAS291/CLO6 applies CLT to means sampling distributions")
    if review.op == "primary-S6-B-S0":
        review.finding(review.op+"-CLT", "P1", "omission", 'MAS291/CLO6 với "Discuss sampling distributions and point estimation"',
            "CLT is an essential frozen asked leaf and appeared in the actual prior MAS291/CLO6 history; this reply omits it while adding many unrelated topics.", ["MAS291/CLO6"])
    if "Nếu bạn muốn" in review.reply:
        review.finding(review.op+"-offer", "P2", "redundant_offer", review.reply[review.reply.index("Nếu bạn muốn"):], "Another summary offer after fulfilling a summary is mildly repetitive.")


# Manually reviewed additional curriculum assertions in the three expanded S6
# outputs. These are correct canonical facts; their defect is conversation scope.
EXTRA_GROUPS = {
    "primary-S6-A-S0": [
        ("DAP391m/CLO2", ["import", "clean/wrangle data", "exploratory data analysis", "visualizations"]),
        ("DAP391m/CLO7", ["mini capstone", "data collection", "data wrangling", "EDA", "model development", "model evaluation", "reporting"]),
        ("ADY201m/CLO7", ["guided project", "Python fundamentals", "data structures", "SQL/database access", "preprocessing", "modeling", "evaluation", "deployment", "visualization", "reporting"]),
        ("AIL303m/CLO1", ["retrieving", "cleaning", "SQL", "NoSQL", "APIs", "Cloud"]),
        ("AIG202c/CLO2", ["Machine Learning", "Deep Learning", "Neural Networks"]),
        ("AIL303m/CLO4", ["supervised models", "Linear Regression"]),
        ("AIL303m/CLO8", ["clustering", "dimensionality reduction"]), ("AIL303m/CLO9", ["clustering", "dimensionality reduction"]),
        ("MAI391/CLO5", ["linear regression"]), ("MAI391/CLO6", ["PCA"]), ("MAI391/CLO7", ["SVM classification"]),
        ("DBI202/CLO5", ["DDL", "DML", "basic queries", "multi-relation queries", "nested queries", "database modifications", "Microsoft SQL Server"]),
        ("DBI202/CLO6", ["T-SQL", "views", "cursors", "stored procedures", "functions", "triggers", "transaction concepts"]),
        ("ADY201m/CLO1", ["foundational SQL", "database fundamentals", "nested queries", "multi-table SELECT"]),
        ("DAP391m/CLO4", ["visualization"]), ("DAP391m/description", ["data visualization tools and techniques", "interactive dashboards"])],
    "primary-S6-B-S0": [
        ("ADY201m/CLO6", ["statistics for data science", "mean", "median", "mode", "variance", "standard deviation", "data visualization", "probability distributions", "regression analysis"]),
        ("DAP391m/CLO2", ["import data", "clean", "wrangle data", "exploratory data analysis", "data visualizations"]),
        ("DAP391m/CLO7", ["mini capstone", "data collection", "data wrangling", "EDA", "data visualization", "model development", "model evaluation", "reporting"]),
        ("ADY201m/CLO7", ["guided project", "Python fundamentals", "Python data structures", "SQL/database access", "data understanding", "preprocessing", "modeling", "evaluation", "deployment", "visualization", "probability", "regression analysis", "final reporting"]),
        ("PFP191/CLO7", ["object-oriented programming"]), ("PFP191/CLO1", ["Python environment"]),
        ("PFP191/CLO2", ["variables", "statements"]), ("PFP191/CLO3", ["conditionals", "functions", "loops"]),
        ("PFP191/CLO4", ["strings"]), ("PFP191/CLO5", ["file handling"]), ("PFP191/CLO6", ["lists", "dictionaries", "tuples"]),
        ("ADY201m/CLO5", ["Python fundamentals", "Python libraries", "API support", "Python for data science"]),
        ("DBI202/CLO5", ["SQL", "DDL", "DML", "basic queries", "multi-relation queries", "nested queries", "database modifications"]),
        ("DBI202/CLO6", ["T-SQL", "Microsoft SQL Server", "views", "cursors", "stored procedures", "functions", "triggers", "transaction concepts"]),
        ("ADY201m/CLO1", ["SQL", "accessing databases with Python", "basic through advanced SQL-based data analysis", "database fundamentals", "nested queries", "multi-table SELECT statements"]),
        ("AIG202c/CLO2", ["Machine Learning", "Deep Learning", "Neural Networks"]),
        ("AIL303m/CLO4", ["supervised models", "Linear Regression"]),
        ("AIL303m/CLO9", ["clustering", "dimensionality-reduction algorithms"]),
        ("MAI391/CLO6", ["PCA"]), ("MAI391/CLO7", ["SVM classification"])],
    "repeat-S6-B-S0": [
        ("DAP391m/CLO1", ["importing datasets", "data wrangling"]),
        ("DAP391m/CLO2", ["import", "clean/wrangle data", "exploratory data analysis", "meaningful data visualizations"]),
        ("DAP391m/CLO7", ["mini capstone", "data collection", "wrangling", "EDA", "data visualization", "model development", "evaluation", "reporting"]),
        ("ADY201m/CLO7", ["workflow dự án", "Python fundamentals", "SQL/database access", "preprocessing", "modeling", "evaluation", "deployment", "visualization", "reporting"]),
        ("AIL303m/CLO1", ["retrieving", "SQL", "NoSQL", "APIs", "Cloud", "cleaning"]),
        ("AIG202c/CLO2", ["Machine Learning", "Deep Learning", "Neural Networks"]),
        ("MAI391/CLO5", ["linear regression"]), ("MAI391/CLO6", ["PCA"]), ("MAI391/CLO7", ["SVM classification"]),
        ("AIL303m/CLO4", ["supervised models", "linear regression"]), ("AIL303m/CLO8", ["clustering", "dimensionality-reduction algorithms"]),
        ("AIL303m/CLO9", ["clustering", "dimensionality-reduction algorithms"]), ("AIL303m/CLO10", ["mini capstone ML project"]),
        ("PFP191/CLO7", ["OOP"]), ("ADY201m/CLO5", ["Python fundamentals", "libraries", "API support"]),
        ("DBI202/CLO5", ["SQL", "DDL", "DML", "multi-relation queries", "nested queries", "modifications", "Microsoft SQL Server"]),
        ("DBI202/CLO6", ["T-SQL", "views", "cursors", "stored procedures", "functions", "triggers"]),
        ("DBI202/CLO7", ["indexes", "query optimization"]),
        ("ADY201m/CLO1", ["SQL/database access"]),
        ("DAP391m/CLO3", ["biểu diễn dữ liệu hiệu quả cho quy mô nhỏ và lớn"]),
        ("DAP391m/CLO4", ["waffle charts", "histograms", "bar charts", "pie charts", "scatter plots", "word clouds", "choropleth maps"]),
        ("MAE101/CLO3", ["đạo hàm", "phân tích hàm", "giải bài toán ứng dụng"]),
        ("MAD101/CLO3", ["phân tích thuật toán", "độ phức tạp"]),
        ("MAI391/CLO4", ["continuous optimization", "gradient descent", "Lagrange multipliers", "convex optimization", "linear programming"])]}


def expanded_statistics(review):
    statistics(review)
    for name, terms in EXTRA_GROUPS.get(review.op, []):
        segment = None
        if review.op == "primary-S6-B-S0":
            segment = 1 if name == "ADY201m/CLO6" else 2 if name in {"DAP391m/CLO2", "DAP391m/CLO7", "ADY201m/CLO7"} else 3 if name.startswith("PFP191") or name == "ADY201m/CLO5" else 4 if name.startswith("DBI202") or name == "ADY201m/CLO1" else 5
        elif review.op == "repeat-S6-B-S0":
            segment = 2 if name in {"DAP391m/CLO1", "DAP391m/CLO2", "DAP391m/CLO7", "ADY201m/CLO7", "AIL303m/CLO1"} else 3 if name.startswith(("AIG202c", "MAI391/CLO5", "MAI391/CLO6", "MAI391/CLO7", "AIL303m")) else 5 if name in {"DAP391m/CLO3", "DAP391m/CLO4"} else 6 if name.startswith(("MAE101", "MAD101", "MAI391/CLO4")) else 4
        review.group(name, terms, segment=segment)
        if name.endswith("description"):
            continue
        if review.op == "primary-S6-A-S0" and name == "DAP391m/CLO4":
            continue  # It is cited for visualization, without a stated grade.
        if review.op == "primary-S6-B-S0" and name.startswith("PFP191/CLO") and name != "PFP191/CLO7":
            review.grade(name, band_only=True, segment=segment)
        else:
            review.grade(name, segment=segment)
    if review.op in EXTRA_GROUPS:
        anchor = "Data processing / analysis" if review.arm == "A" else "Về data processing/analysis" if review.op.startswith("primary") else "Về data processing và data analysis"
        review.scope_violation(anchor)
    if review.op == "primary-S6-B-S0":
        review.finding(review.op+"-scores", "P1", "assessment_comparison_missing_score", "đều có achievement excellent",
            "The six PFP191 bands are correct and their refs are present, but their individual scores are omitted during the grouped achievement comparison.", [f"PFP191/CLO{i}" for i in range(1,7)])


def main():
    p.check_bundle(ROOT, DIRECTORY, deep=True)
    conditions = p.b.read_json(DIRECTORY / "conditions.json")["conditions"]
    outputs = []
    for condition in conditions:
        review = Review(condition)
        if review.original is not None:
            basic(review); other(review)
            if condition["scenario_id"] == "S6":
                expanded_statistics(review)
        outputs.append(review.finalize())
    assert len(outputs) == 32 and sum(o["raw_semantic_p0"] is not None for o in outputs) == 26
    p.b.atomic_json(DIRECTORY / "manual_annotations.json", {"version": 1, "status": "completed",
        "review_method": "manual raw-output/canonical/history review; no additional generation or LLM judge",
        "annotation_granularity": "One manually mapped curriculum/topic assertion per source clause, plus separate CLO/score/band tuple. Independently named curriculum topics are split; redundant same-clause paraphrases are not counted twice. Additional restatements/details are not completion credit.",
        "semantic_boolean_definition": "Academic factual support only; scope, segment-local binding and completeness are separate fields. Correct facts outside conversation scope are not hallucination.",
        "outputs": outputs})
    p.b.atomic_json(DIRECTORY / "manual_review_findings.json", {"findings": [f for o in outputs for f in o["findings"]],
        "p0_observed_in_public_text": 0, "completion_failures_are_not_academic_p0": True})
    summary = summarize(DIRECTORY)
    summary.update(recommendation="summary_scope_only_in_later_verified_production_task; retain current schema; B raw grounding benefit inconclusive",
        semantic_status="26_public_replies_manually_reviewed; six_incomplete_responses_unassessable",
        semantic_boolean_definition="Academic factual support only; scope/local binding/completeness are separate measures")
    p.b.atomic_json(DIRECTORY / "comparison_summary.json", summary)
    print("Manually annotated", len(outputs), "operations; atomic assertions", sum(len(o["claims"]) for o in outputs))


if __name__ == "__main__":
    main()
