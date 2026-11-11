"""Serialize an explicitly authored manual review of the 32 original RCA outputs.

Labels below were chosen by reading outputs and canonical sources, not inferred
by a classifier or an LLM judge. String searches locate original spans only.
Frozen inputs, schemas, expected evidence and raw results are never rewritten.
"""
import json
from collections import Counter
from pathlib import Path

from research.diagnostics import academic_grounding_rca as r
from research.diagnostics.rca_fixtures import clo, metadata

b = r.benchmark
DIRECTORY = r.ROOT / r.DIRECTORY
CONDITIONS = {c["operation"]: c for c in b.read_json(DIRECTORY / "conditions.json")["conditions"]}
TRACES = {op: b.read_json(DIRECTORY / "live/requests" / (op + ".json")) for op in CONDITIONS}
AUDITS = {c["operation"]: c for c in b.read_json(DIRECTORY / "postrun_checks.json")["checks"]}
RECORDS = {op: [] for op in CONDITIONS}
FINDINGS = {op: [] for op in CONDITIONS}


def provided(op, ref):
    profile = json.loads(CONDITIONS[op]["input"][0]["content"])["student_academic_profile"]
    course = next(c for c in profile["courses"] if c["course_code"] == ref["course_code"])
    value = (next(c for c in course["clos"] if c["clo"] == ref["clo"]) if "clo" in ref else course["metadata"][ref["metadata_field"]])
    return {"reference": ref, "canonical_value": value, "source_present_in_actual_input": True}


def span(op, anchor, *, selection=None):
    output = TRACES[op]["structured_output"]
    if selection is not None:
        selected = next(s for s in output["selections"] if s["claim_id"] == selection)
        return selected["claim"], {"component": "selections", "claim_id": selection, "returned_relation": selected["relation"]}
    text = output["reply"]
    assert anchor.casefold() in text.casefold(), (op, anchor)
    line = next(line for line in text.splitlines() if anchor.casefold() in line.casefold())
    return line, {"component": "reply", "start_char": text.index(line), "end_char": text.index(line) + len(line)}


def add(op, assertion, refs, anchor, *, parent=None, kind="curriculum_coverage", result="correct_direct",
        expected=None, severity=None, explanation=None, selection=None, taxonomy=None):
    text, location = span(op, anchor, selection=selection)
    expected = refs if expected is None else expected
    inspected = {b.fingerprint(ref): provided(op, ref) for ref in refs + expected}
    index = len(RECORDS[op]) + 1
    RECORDS[op].append({"claim_id": f"{op}-{index:03d}", "operation": op, "stage": "identification" if selection else "chat",
        "atomic_assertion": assertion, "original_claim_verbatim": text, "span": location, "claim_type": kind,
        "origin_asked_or_added": "asked" if parent is not None else "added", "frozen_parent_unit": parent,
        "model_sources": refs, "acceptable_sources": expected, "actually_provided_sources": list(inspected.values()),
        "actual_profile_message_sha256": b.digest(CONDITIONS[op]["input"][0]["content"].encode()),
        "source_scope": "entire_actual_profile" if kind in {"absence_boundary", "personal_use_boundary", "scope_policy"} else "listed_sources",
        "quote_provenance": "See postrun_checks.json; source-only audit, not semantic proof",
        "result": result, "severity": severity, "taxonomy": taxonomy or [],
        "explanation": explanation or "Đọc claim và source canonical thực có trong input; không suy semantic support từ quote check.",
        "reviewer": "Codex manual canonical recheck, no additional judge/model request"})


def findings(op, category, severity, anchor, explanation):
    text, location = span(op, anchor)
    FINDINGS[op].append({"taxonomy": category, "severity": severity, "original_claim_verbatim": text,
        "span": location, "explanation": explanation})


def performance(op, refs, anchor, *, parents=None, selection=None, result="correct_direct"):
    for ref in refs:
        value = provided(op, ref)["canonical_value"]
        original, _ = span(op, anchor, selection=selection)
        if parents is None:
            assert str(value["score"]) in original and value["achievement"] in original, (op, ref, original)
            add(op, f"{ref['course_code']}/{ref['clo']} score={value['score']}", [ref], anchor, kind="score", selection=selection)
            add(op, f"{ref['course_code']}/{ref['clo']} achievement={value['achievement']}", [ref], anchor, kind="achievement", selection=selection)
        else:
            for kind, parent in parents.items():
                assert str(value[kind]) in original, (op, ref, kind, original)
                add(op, f"{ref['course_code']}/{ref['clo']} {kind}={value[kind]}", [ref], anchor,
                    parent=parent, kind=kind, selection=selection, result=result)


def details(op, ref, anchor, items, *, result="correct_direct", expected=None, severity=None, explanation=None):
    for item in items:
        add(op, f"{ref['course_code']}/{ref['clo']}: {item}", [ref], anchor, result=result,
            expected=expected, severity=severity, explanation=explanation, taxonomy=["wrong_attribution"] if severity == "P0" else [])


def write_review():
    # A/B: actual tasks are target assertions, not each course question. Sources
    # quoted only as evidence do not add every subordinate curriculum assertion.
    targets = {
        "AB-S1": [("S1-CI", "confidence intervals", [clo("MAS291", "CLO7")]), ("S1-LR", "simple linear regression", [clo("MAS291", "CLO9")])],
        "AB-S2": [("S2-DATA", "data types/bit patterns", [clo("CSI106", "CLO3")]), ("S2-NET", "networking", [clo("CSI106", "CLO4")])],
        "AB-S3": [("S3-OD", "object detection", [clo("CPV301", "CLO8")]), ("S3-FR", "face recognition", [clo("CPV301", "CLO9")]), ("S3-FR", "object tracking", [clo("CPV301", "CLO9")])],
        "AB-S4": [("S4-SQL", "DBI202 SQL", [clo("DBI202", "CLO5")]), ("S4-TSQL", "DBI202 T-SQL", [clo("DBI202", "CLO6")]), ("S4-ADY", "ADY201m SQL", [clo("ADY201m", "CLO7")])],
        "AB-S5": [("S5-OPT", "continuous optimization", [clo("MAI391", "CLO4")]), ("S5-LR", "linear regression", [clo("MAI391", "CLO5")]), ("S5-PCA", "PCA", [clo("MAI391", "CLO6")]), ("S5-SVM", "SVM", [clo("MAI391", "CLO7")])],
        "AB-S7": [("S7-STR", "strings", [clo("PFP191", "CLO4")]), ("S7-FILE", "file handling", [clo("PFP191", "CLO5")])],
        "AB-S8": [("S8-GRAPH", "graphs", [clo("CSD203", "CLO5")]), ("S8-SORT", "sorting", [clo("CSD203", "CLO6")]), ("S8-HASH", "hashing", [clo("CSD203", "CLO7")])],
    }
    for op, rows in targets.items():
        for selector, parent, refs in rows:
            add(op, parent, refs, parent, parent=parent, selection=selector)
    for topic in ["face recognition", "object tracking"]:
        add("AB-S3", f"Explain {topic} không xác nhận Implement", [clo("CPV301", "CLO9")], topic,
            parent="Explain versus Implement", kind="learning_verb", result="correct_related_boundary", selection="S3-IMPLEMENT")
    add("AB-S4", "DAP391m/CLO7 không nêu SQL/database access", [clo("DAP391m", "CLO7")], "SQL",
        parent="DAP391m/CLO7 SQL not established", kind="absence_boundary", result="correct_related_boundary", selection="S4-DAP")
    for op, selectors, course, clos in [("AB-S4", "S4-BANDS", "DBI202", ["CLO5", "CLO6"]), ("AB-S8", "S8-BANDS", "CSD203", ["CLO5", "CLO6", "CLO7"])]:
        for identifier in clos:
            parent = f"DBI202/{identifier} basic" if course == "DBI202" else f"{identifier} basic"
            add(op, f"{course}/{identifier} có basic được cung cấp trực tiếp", [clo(course, identifier)], "basic", parent=parent,
                kind="achievement", result="relation_underclaim", severity="P1", selection=selectors,
                taxonomy=["false_absence" if op == "AB-S4" else "relation_underclassification"],
                explanation="Source object có achievement basic trong input; model trả insufficient/related. Đây là underclassification trong task quote/relation, không bịa điểm. Excerpt chỉ được quote description nên contract có thể góp phần; chưa suy model không đọc được grade.")
    for course in ["ADY201m", "DAP391m"]:
        for tool in ["Git", "JupyterLab"]:
            add("AB-S6", f"{course} tools liệt kê {tool}", [metadata(course, "tools")], tool,
                parent=f"{course} tools listing", kind="tool_listing", selection="S6-CONTEXT")
    add("AB-S6", "ADY201m/CLO3 yêu cầu at least one tool", [clo("ADY201m", "CLO3")], "one",
        parent="use-at-least-one choice", selection="S6-CHOICE")
    for tool, parent in [("GitHub", "individual GitHub use not established"), ("JupyterLab", "individual Jupyter use not established"), ("RStudio", "individual RStudio use not established")]:
        add("AB-S6", f"Không xác nhận cá nhân dùng riêng {tool}", [clo("ADY201m", "CLO3"), metadata("ADY201m", "tools"), metadata("DAP391m", "tools")], tool,
            parent=parent, kind="personal_use_boundary", result="correct_related_boundary", selection="S6-USE")
    add("AB-S7", "Không có FastAPI trong actual PFP191 input", [], "FastAPI", parent="FastAPI not established", kind="absence_boundary", result="correct_absence", selection="S7-FASTAPI")
    for tool in ["Visual Studio Code", "Google Colab"]:
        add("AB-S7", f"PFP191 tools liệt kê {tool}", [metadata("PFP191", "tools")], tool,
            parent="IDE metadata listing", kind="tool_listing", selection="S7-IDE")

    # C: one asked source binding; additional explicitly stated values, verbs,
    # interval cases or whole-profile absence are separate assertions.
    for op in ["C1", "C2", "C3", "C4", "C2-reversed", "C1-repeat", "C4-repeat"]:
        ref = clo("MAS291", "CLO7")
        add(op, "Confidence intervals→MAS291/CLO7", [ref], "confidence intervals", parent="confidence intervals source")
        add(op, "MAS291/CLO7: Construct confidence intervals", [ref], "Construct", kind="learning_verb")
        add(op, "MAS291/CLO7: Interpret confidence intervals", [ref], "interpret", kind="learning_verb")
        if op in ["C1", "C2", "C3", "C1-repeat"]:
            performance(op, [ref], "9.43")
        if op in ["C1", "C3", "C4", "C2-reversed"]:
            for detail in ["intervals for means", "intervals for proportions", "intervals for differences between groups"]:
                add(op, detail, [ref], "khoảng tin cậy")
        if op == "C4-repeat":
            add(op, "Không CLO khác nêu confidence intervals", [ref], "các CLO khác", kind="absence_boundary", result="correct_absence",
                explanation="Đọc toàn bộ actual profile: chỉ MAS291/CLO7 có confidence intervals. Không biến course metadata thành CLO hoặc kết luận sinh viên không biết topic khác.")

    for op in ["D-S1-D1", "D-S1-D2", "D-S1-verified-mapping"]:
        for topic, identifier, score_parent, band_parent in [("confidence intervals", "CLO7", "confidence intervals score", "confidence intervals achievement"), ("simple linear regression", "CLO9", "regression score", "regression achievement")]:
            ref = clo("MAS291", identifier)
            add(op, f"{topic}→MAS291/{identifier}", [ref], topic, parent=topic)
            performance(op, [ref], topic, parents={"score": score_parent, "achievement": band_parent})
        details(op, clo("MAS291", "CLO7"), "confidence intervals", ["Construct confidence intervals", "Interpret confidence intervals"])
        details(op, clo("MAS291", "CLO9"), "simple linear regression", ["Construct simple linear regression", "prediction", "interpretation"])

    for op in ["D-S6-D1", "D-S6-D2"]:
        for course in ["ADY201m", "DAP391m"]:
            for tool in ["Git", "GitHub", "Jupyter Notebooks", "JupyterLab", "RStudio IDE"]:
                add(op, f"{course} tools liệt kê {tool}", [metadata(course, "tools")], course, parent=f"{course} tools listing", kind="tool_listing")
            add(op, f"{course} tools còn liệt kê Watson Studio", [metadata(course, "tools")], course, kind="tool_listing")
        add(op, "ADY201m/CLO3 at least one tool", [clo("ADY201m", "CLO3")], "at least one", parent="use-at-least-one choice")
        for tool, parent in [("GitHub", "individual GitHub use not established"), ("JupyterLab", "individual Jupyter use not established"), ("RStudio", "individual RStudio use not established")]:
            add(op, f"Không xác nhận cá nhân dùng riêng {tool}", [clo("ADY201m", "CLO3"), metadata("ADY201m", "tools"), metadata("DAP391m", "tools")], "không xác nhận",
                parent=parent, kind="personal_use_boundary", result="correct_related_boundary")
        # The additional tool examples were expressly repeated only by D1.
        if op == "D-S6-D1":
            for tool in ["Python", "R", "Scala", "SQL"]:
                add(op, f"ADY201m/CLO3 liệt kê {tool} như lựa chọn", [clo("ADY201m", "CLO3")], "CLO3", kind="tool_listing")

    summaries = ["E1-clean", "E1-clean-D2", "E2-contaminated", "E2-contaminated-D2", "E2-contaminated-repeat"]
    for op in summaries:
        bad = op in ["E2-contaminated-D2", "E2-contaminated-repeat"]
        ci_source = clo("MAS291", "CLO9" if bad else "CLO7")
        add(op, "Confidence intervals source", [ci_source], "Confidence intervals", parent="confidence intervals",
            expected=[clo("MAS291", "CLO7")], result="wrong_attribution" if bad else "correct_direct", severity="P0" if bad else None,
            taxonomy=["within_course_misbinding", "history_propagation", "source_compression"] if bad else [],
            explanation="Actual profile có CI7. History contaminated đổi đúng một attribution 7→9; output này lặp/sửa association đó. CI7/CLO9 cùng 9.43/excellent nên số/band không phát hiện lỗi ID.")
        for topic, course, identifier in [("hypothesis testing", "MAS291", "CLO8"), ("simple linear regression", "MAS291", "CLO9"), ("PCA", "MAI391", "CLO6")]:
            add(op, topic, [clo(course, identifier)], topic, parent=topic)
        # Numeric facts about the actual referenced outcome remain numerically
        # correct; they do not repair the independently incorrect topic binding.
        for topic, ref in [("Confidence intervals", ci_source), ("Hypothesis testing", clo("MAS291", "CLO8")), ("Simple linear regression", clo("MAS291", "CLO9")), ("PCA", clo("MAI391", "CLO6"))]:
            performance(op, [ref], topic)
        if bad:
            findings(op, "history_propagation", "P0", "Confidence intervals", "CI quote thuộc CLO7 nhưng gắn CLO9 trong reply; D2 explicit claims cũng sai ngay ở mapping. Aggregate thiếu CLO7. Không sửa bằng cách coi 9.43/excellent giống nhau là đúng attribution.")
    # Other technical topics explicitly listed in E2/E4 are valid subordinate
    # facts. CI subcases in the wrong repeat share its incorrect source binding.
    for op in ["E2-contaminated", "E2-contaminated-repeat"]:
        for ref, anchor, items in [(clo("MAS291", "CLO8"), "Hypothesis testing", ["formulating hypotheses", "critical values", "test statistic", "p-value"]),
            (clo("MAS291", "CLO9"), "Simple linear regression", ["least squares", "regression equation", "correlation coefficient", "regression significance tests"]),
            (clo("MAI391", "CLO6"), "PCA", ["covariance matrices", "maximum-variance subspaces", "principal subspace bases", "low-rank matrix approximation"])]:
            details(op, ref, anchor, items)

    # E3 asked only MAS statistics; other source-grounded curriculum is added,
    # not credited as extra coverage of the original summary question.
    for topic, identifier in [("descriptive statistics", "CLO5"), ("sampling/CLT", "CLO6"), ("confidence intervals", "CLO7"), ("hypothesis testing", "CLO8"), ("simple linear regression", "CLO9")]:
        ref = clo("MAS291", identifier)
        add("E3-same-course", topic, [ref], f"MAS291/{identifier}", parent=topic)
        performance("E3-same-course", [ref], f"MAS291/{identifier}")
    extra_e3 = [("ADY201m", "CLO6", "statistics for data science"), ("DAP391m", "CLO1", "data analysis with Python"),
        ("DAP391m", "CLO2", "import,clean,wrangle,EDA,visualization"), ("DAP391m", "CLO7", "capstone workflow"),
        ("ADY201m", "CLO7", "guided data science project"), ("AIL303m", "CLO1", "SQL retrieval,NoSQL retrieval,API retrieval,Cloud retrieval"),
        ("AIG202c", "CLO2", "ML concepts,DL concepts,NN concepts"), ("AIL303m", "CLO4", "supervised models"),
        ("AIL303m", "CLO8", "curse of dimensionality"), ("AIL303m", "CLO9", "clustering,dimensionality reduction"),
        ("MAI391", "CLO3", "probability,distributions"), ("MAI391", "CLO4", "continuous optimization"),
        ("MAI391", "CLO5", "linear regression"), ("MAI391", "CLO6", "PCA"), ("MAI391", "CLO7", "SVM"),
        ("DBI202", "CLO5", "SQL"), ("DBI202", "CLO6", "T-SQL"), ("ADY201m", "CLO1", "foundational SQL")]
    for course, identifier, topic in extra_e3:
        ref = clo(course, identifier); anchor = f"{course}/{identifier}"
        for atom in topic.split(","):
            add("E3-same-course", atom, [ref], anchor)
        performance("E3-same-course", [ref], anchor)
    details("E3-same-course", clo("MAS291", "CLO5"), "MAS291/CLO5", ["frequency distributions", "histograms", "box plots", "quartiles", "outlier identification", "time sequence plots"])
    details("E3-same-course", clo("ADY201m", "CLO6"), "ADY201m/CLO6", ["mean", "median", "mode", "variance", "probability distributions", "visualization", "regression analysis"])
    details("E3-same-course", clo("DAP391m", "CLO1"), "DAP391m/CLO1", ["building data models", "evaluating data models"])
    details("E3-same-course", clo("DAP391m", "CLO7"), "DAP391m/CLO7", ["data collection", "wrangling", "EDA", "visualization", "model development", "model evaluation", "reporting"])
    details("E3-same-course", clo("ADY201m", "CLO7"), "ADY201m/CLO7", ["preprocessing/wrangling", "modeling", "evaluation", "deployment", "visualization", "reporting"])
    add("E3-same-course", "ADY201m/CLO7 SQL/database access", [clo("ADY201m", "CLO7")], "SQL/database access")
    add("E3-same-course", "ADY201m/CLO7 nêu data collection", [clo("ADY201m", "CLO7")], "gồm data collection",
        expected=[clo("ADY201m", "CLO5"), clo("DAP391m", "CLO7")], result="wrong_attribution", severity="P0",
        taxonomy=["cross_course_misbinding", "summary_invention"],
        explanation="ADY7 không nêu collection; ADY5 nêu collecting data và DAP7 nêu data collection. Initial Review phân biệt DAP7 collection với ADY7 preprocessing đúng; actual E3 history chỉ MAS5–9. Đây là association mới trong summary, không sao chép attribution sai có sẵn.")
    add("E3-same-course", "ADY201m/CLO7 nêu EDA cụ thể", [clo("ADY201m", "CLO7")], "gồm data collection",
        expected=[clo("DAP391m", "CLO2"), clo("DAP391m", "CLO7")], result="interpretation_error", severity="P1",
        taxonomy=["unsupported_specificity"], explanation="ADY7 có data understanding/preprocessing, related với EDA; không nêu EDA cụ thể. Đánh giá P1 vì overlap semantic, không dùng keyword mismatch đơn thuần để tự nâng thành P0.")
    findings("E3-same-course", "summary_scope_expansion", "P1", "Data processing", "User/history chỉ MAS5–9; output kéo thêm nhiều chủ đề từ Review/profile, rồi phát sinh association ADY7 collection sai. Các facts ngoài scope còn lại được kiểm canonical, không tự coi mọi added fact là invention sai.")
    for topic, course, identifier, anchor in [("SQL", "DBI202", "CLO5", "**SQL**"), ("continuous optimization", "MAI391", "CLO4", "**Optimization**"),
        ("PCA", "MAI391", "CLO6", "**PCA**"), ("SVM", "MAI391", "CLO7", "**SVM**")]:
        ref = clo(course, identifier)
        add("E4-multiple-sources", topic, [ref], anchor, parent=topic)
        performance("E4-multiple-sources", [ref], anchor)
    details("E4-multiple-sources", clo("DBI202", "CLO5"), "**SQL**", ["DDL", "basic queries", "multi-relation queries", "nested queries", "aggregation", "INSERT", "UPDATE", "DELETE", "Microsoft SQL Server"])
    details("E4-multiple-sources", clo("MAI391", "CLO4"), "**Optimization**", ["gradient descent", "Lagrange multipliers", "convex optimization", "linear programming"])
    details("E4-multiple-sources", clo("MAI391", "CLO6"), "**PCA**", ["covariance matrices", "maximum-variance subspaces", "principal subspace bases", "low-rank approximation", "practical PCA steps"])
    details("E4-multiple-sources", clo("MAI391", "CLO7"), "**SVM**", ["separating hyperplanes", "primal SVM", "dual SVM", "kernel nonlinear classifiers", "numerical SVM optimization"])

    for op in ["D-S7-D1", "D-S7-D2"]:
        for topic, identifier in [("strings", "CLO4"), ("file handling", "CLO5")]:
            add(op, topic, [clo("PFP191", identifier)], "CLO" + identifier[3:], parent=topic)
        foundations = [clo("PFP191", "CLO7"), clo("ADY201m", "CLO5")] if op == "D-S7-D1" else [clo("PFP191", "CLO4"), clo("PFP191", "CLO5")]
        add(op, "Generic Python không xác nhận FastAPI", foundations, "FastAPI",
            parent="FastAPI not established", kind="absence_boundary", result="correct_absence")
        for tool in ["Visual Studio Code", "Google Colab"]:
            add(op, f"PFP191 tools liệt kê {tool}", [metadata("PFP191", "tools")], "Google Colab", parent="IDE metadata listing", kind="tool_listing")
            add(op, f"PFP191 tools không xác nhận cá nhân dùng {tool}", [metadata("PFP191", "tools")], "Google Colab",
                parent="personal IDE use not established", kind="personal_use_boundary", result="correct_related_boundary")
        if op == "D-S7-D1":
            add(op, "Python/OOP foundation", [clo("PFP191", "CLO7")], "PFP191/CLO7")
            add(op, "API support foundation", [clo("ADY201m", "CLO5")], "ADY201m/CLO5")
        else:
            for topic, identifier in [("data structures", "CLO6"), ("OOP", "CLO7")]:
                add(op, f"PFP191 có {topic} nhưng aggregate ref thiếu", [], "data structures", expected=[clo("PFP191", identifier)],
                    result="missing_support", severity="P1", taxonomy=["missing_support", "reply_mapping_drift"],
                    explanation="Profile có source thật; final reply tự nhắc topic không nằm trong claims mapping hoặc aggregate evidence. Không gán sai ID; đây là thiếu ref, không phải P0 invention.")
    for op in ["D-S8-D1", "D-S8-D2"]:
        for topic, identifier, parent in [("graphs", "CLO5", "CLO5 basic"), ("sorting", "CLO6", "CLO6 basic"), ("hashing", "CLO7", "CLO7 basic")]:
            ref = clo("CSD203", identifier)
            add(op, topic, [ref], topic, parent=topic)
            performance(op, [ref], topic, parents={"score": f"{topic} score", "achievement": parent})
        add(op, "Không suy course-level excellent từ CLO", [clo("CSD203", "CLO5"), clo("CSD203", "CLO6"), clo("CSD203", "CLO7")], "cả môn",
            parent="no inferred course-level excellent", kind="scope_policy", result="correct_related_boundary")
        for identifier in ["CLO1", "CLO2", "CLO3", "CLO4", "CLO8"]:
            ref = clo("CSD203", identifier); value = provided(op, ref)["canonical_value"]
            add(op, f"CSD203/{identifier} achievement={value['achievement']}", [ref], "CLO1", kind="achievement")
        findings(op, "missing_companion_scores", "P1", "CLO1", "Khi so CLO1–4 good với CLO5–8 basic, không nêu 7.26 của CLO1–4 hoặc 6.06 của CLO8. Labels và refs đúng; đây là score omission theo production comparison rule, không bịa score hoặc band.")

    # E5 holdout retains the two asked facts but expands the summary to Review.
    for topic, identifier in [("sorting", "CLO6"), ("hashing", "CLO7")]:
        ref = clo("CSD203", identifier)
        add("E5-holdout", topic, [ref], "Sorting và hashing", parent=topic)
        performance("E5-holdout", [ref], "Sorting và hashing")
    for course, identifier, topic, anchor, band_only in [
        ("PFP191", "CLO3", "Python conditional execution,Python functions,Python loops,Python iteration", "**Python**", True),
        ("PFP191", "CLO6", "Python lists,Python dictionaries,Python tuples", "**Python**", True),
        ("PFP191", "CLO7", "Python OOP", "**Python**", True),
        ("ADY201m", "CLO5", "Python fundamentals,Python libraries,Python API support", "**Python**", True),
        ("DBI202", "CLO4", "ER modeling,relational schema translation", "**SQL /", False),
        ("DBI202", "CLO5", "SQL,DML", "**SQL /", False),
        ("DBI202", "CLO6", "T-SQL", "**SQL /", False),
        ("DBI202", "CLO7", "indexes,query optimization", "**SQL /", False),
        ("ADY201m", "CLO1", "SQL,Python DB access", "**SQL /", False),
        ("ADY201m", "CLO7", "guided SQL project", "**SQL /", False),
        ("DAP391m", "CLO5", "Watson multi-services application", "**Tích hợp AI", True),
        ("DAP391m", "CLO6", "AI applications", "**Tích hợp AI", True),
        ("AIG202c", "CLO5", "Watson Assistant chatbot", "**Tích hợp AI", True),
        ("AIL303m", "CLO1", "SQL retrieval,NoSQL retrieval,API retrieval,Cloud retrieval", "**Nền tảng backend", None),
        ("CSI106", "CLO4", "networking", "**Nền tảng backend", None),
        ("CSI106", "CLO5", "OS", "**Nền tảng backend", None),
        ("CEA201", "CLO9", "ILP trends,superscalar trends", "**Nền tảng backend", None)]:
        ref = clo(course, identifier)
        for atom in topic.split(","):
            add("E5-holdout", atom, [ref], anchor)
        if band_only is False:
            performance("E5-holdout", [ref], anchor)
        elif band_only is True:
            value = provided("E5-holdout", ref)["canonical_value"]
            add("E5-holdout", f"{course}/{identifier} achievement={value['achievement']}", [ref], anchor, kind="achievement")
    for technology in ["FastAPI", "Flask", "Django", "SQLAlchemy", "backend message queues", "caching", "event-driven architecture"]:
        add("E5-holdout", f"Không xác nhận trực tiếp {technology}", [clo("ADY201m", "CLO5"), clo("AIL303m", "CLO1")], "chưa phải bằng chứng", kind="absence_boundary", result="correct_absence")
    details("E5-holdout", clo("CSD203", "CLO6"), "Sorting và hashing", ["selection sort", "insertion sort", "bubble sort", "quicksort", "merge sort", "heap sort", "bucket sort", "radix sort"])
    details("E5-holdout", clo("CSD203", "CLO7"), "Sorting và hashing", ["hash tables", "hash functions", "collision handling", "load factors", "rehashing", "Python hash implementation"])
    findings("E5-holdout", "summary_scope_expansion", "P1", "**Python**", "Actual history chỉ sorting/hashing, nhưng summary mở lại Python/SQL/AI/backend trong Initial Review. Canonical facts vẫn đúng; đây là scope/continuity failure, không phải mọi added topic đều sai nguồn.")

    # Presentation comments are distinct from academic fault counts.
    for op, anchor in [("C3", "Nếu bạn muốn"), ("D-S6-D1", "Nếu cần"), ("E2-contaminated", "Nếu muốn"),
        ("E2-contaminated-D2", "Nếu cần"), ("E4-multiple-sources", "Nếu cần"), ("D-S8-D2", "Nếu bạn muốn"), ("E5-holdout", "Nếu cần")]:
        findings(op, "redundant_offer", "P2", anchor, "Offer tóm tắt tiếp sau khi đã trả lời/tóm tắt làm giảm tự nhiên. Nhắc CV trong offer không được tự coi là đã sinh CV hoặc bịa academic fact.")

    annotations = b.read_json(DIRECTORY / "manual_annotations.json")
    for op, condition in CONDITIONS.items():
        seen, unique = set(), []
        for record in RECORDS[op]:
            identity = b.fingerprint({k: record[k] for k in ["atomic_assertion", "model_sources", "frozen_parent_unit", "claim_type"]})
            if identity not in seen:
                seen.add(identity)
                record["claim_id"] = f"{op}-{len(unique)+1:03d}"
                unique.append(record)
        RECORDS[op] = records = unique
        seen_parents = {c["frozen_parent_unit"] for c in records if c["origin_asked_or_added"] == "asked"}
        assert seen_parents == set(condition["asked_atomic_units"]), (op, seen_parents, condition["asked_atomic_units"])
        annotations["live_conditions"][op] = {"status": "manually_read_original_complete_output",
            "api_completed": True, "runner_validation": TRACES[op]["validation_status"],
            "original_output_artifact": f"live/requests/{op}.json", "claims": records, "findings": FINDINGS[op],
            "frozen_asked_parent_units": len(condition["asked_atomic_units"]),
            "asked_atomic_claims": sum(c["origin_asked_or_added"] == "asked" for c in records),
            "answered_atomic_claims": len(records), "added_atomic_claims": sum(c["origin_asked_or_added"] == "added" for c in records),
            "omitted_asked_units": [], "naturalness": "needs_improvement" if any(f["severity"] == "P2" for f in FINDINGS[op]) else "acceptable_for_task",
            "completeness": "asked_units_addressed; inspect semantic errors and added scope separately"}
    annotations.update(status="forensic_and_live_manual_review_complete", annotation_date="2026-10-14",
        methodology={"frozen_input_contracts_unchanged": True, "all_32_completed_outputs_read": True,
            "unit_expansion": "132 frozen parent units split into atomic tool-list members and personal-use/verb boundaries using the original task targets/questions; no frozen expectations were changed.",
            "counting": "Final reply assertions counted once per distinct topic/property; quoted source payloads are evidence, not automatically extra student claims. D2 mapping audit is reported separately to avoid double-counting claims/reply repetitions.",
            "granularity": "Named topic/source bindings, scores, bands, tool memberships, boundaries and explicitly listed additional techniques are distinct. Scope details within a single topic are not exhaustively lexicalized.",
            "not_a_population_accuracy_estimate": True,
            "band_relation_caveat": "A/B relation underclassification may reflect the description-only quote contract; source objects have grade fields. It is not an invented numeric grade.",
            "manual_mapping_audit": {"D-S1-D2": "CI7/LR9 and assessed values correct; reply consistent",
                "D-S6-D2": "Metadata/tool-choice boundaries correct; reply consistent",
                "E1-clean-D2": "All four topic/source mappings correct; reply consistent",
                "E2-contaminated-D2": "CI→CLO9 wrong already in claims[0], invalid quote; repeated in final reply",
                "D-S7-D2": "Mapping strings/files/tools correct; final reply adds data structures/OOP without refs or mapping entries",
                "D-S8-D2": "Topics/values/group bands correct; reply omits scores for additional band comparison"},
            "adjudicated_alternative": "AB-S2 compound data-representation/networking accepts CSI106 metadata.description: its two exact excerpts explicitly name both topics. Duplicate reference remains a technical failure; frozen expected file is preserved.",
            "grade_comparison_omission": "D-S8 outputs correctly answer scores for CLO5–7. Additional good/basic comparison lacks CLO1–4/CLO8 scores; P1 policy finding, not a wrong supplied number."})
    all_records = [c for rows in RECORDS.values() for c in rows]
    metrics = {"frozen_asked_parent_units": sum(len(c["asked_atomic_units"]) for c in CONDITIONS.values()),
        "asked_atomic_claims": sum(c["origin_asked_or_added"] == "asked" for c in all_records),
        "answered_atomic_claims": len(all_records), "added_atomic_claims": sum(c["origin_asked_or_added"] == "added" for c in all_records),
        "asked_results": dict(Counter(c["result"] for c in all_records if c["origin_asked_or_added"] == "asked")),
        "added_results": dict(Counter(c["result"] for c in all_records if c["origin_asked_or_added"] == "added")),
        "omitted_asked_units": 0, "atomic_severity": dict(Counter(c["severity"] for c in all_records if c["severity"])),
        "outputs_with_p0": [op for op in CONDITIONS if any(c["severity"] == "P0" for c in RECORDS[op]) or any(f["severity"] == "P0" for f in FINDINGS[op])],
        "outputs_with_p1": [op for op in CONDITIONS if any(c["severity"] == "P1" for c in RECORDS[op]) or any(f["severity"] == "P1" for f in FINDINGS[op])],
        "outputs_with_p2": [op for op in CONDITIONS if any(f["severity"] == "P2" for f in FINDINGS[op])]}
    annotations["live_metrics"] = metrics
    b.atomic_json(DIRECTORY / "manual_annotations.json", annotations)
    return metrics


if __name__ == "__main__":
    print(json.dumps(write_review(), ensure_ascii=False, indent=2))
