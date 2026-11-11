#!/usr/bin/env python3
"""Deterministic CLO scoring and academic profile construction."""

from __future__ import annotations

import json
import math
import re
import os
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__:
    from .course_metadata import read_course_metadata
else:
    from course_metadata import read_course_metadata


ACHIEVEMENT_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (5.0, "below_expected"),
    (7.0, "basic"),
    (8.5, "good"),
    (math.inf, "excellent"),
)

ASSESSMENT_ALIAS_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\btess\b", "test"),
    (r"\bexercices\b", "exercise"),
)


@dataclass(frozen=True)
class AssessmentRecord:
    index: int
    category: str
    part: str
    raw_weight: Any
    raw_clo: Any


@dataclass(frozen=True)
class MatchResult:
    assessment: AssessmentRecord | None
    match_type: str
    candidates: list[str]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as f:
            tmp = Path(f.name)
            json.dump(data, f, ensure_ascii=False, allow_nan=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def classify_achievement(score: float | None) -> str:
    if score is None:
        return "not_evaluated"
    if not math.isfinite(score) or score < 0 or score > 10:
        raise ValueError(f"CLO score must be in the 0-10 range: {score!r}")

    for upper_bound, achievement in ACHIEVEMENT_THRESHOLDS:
        if score < upper_bound or (upper_bound == math.inf and score <= 10):
            return achievement

    raise ValueError(f"CLO score must be in the 0-10 range: {score!r}")


def normalize_assessment_name(name: Any) -> str:
    text = unicodedata.normalize("NFKC", str(name or "")).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def alias_assessment_key(name: Any) -> str:
    text = normalize_assessment_name(name)
    for pattern, replacement in ASSESSMENT_ALIAS_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_weight(raw_weight: Any) -> float:
    if isinstance(raw_weight, str):
        text = raw_weight.strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        value = float(text)
    elif isinstance(raw_weight, (int, float)):
        value = float(raw_weight)
    else:
        raise ValueError("weight must be a number or percentage string")

    if not math.isfinite(value) or value <= 0:
        raise ValueError("weight must be positive")
    return value


def parse_grade(raw_grade: Any) -> float:
    if isinstance(raw_grade, str):
        value = float(raw_grade.strip())
    elif isinstance(raw_grade, (int, float)):
        value = float(raw_grade)
    else:
        raise ValueError("grade must be numeric")

    if not math.isfinite(value) or value < 0 or value > 10:
        raise ValueError("grade must be in the 0-10 range")
    return value


def canonical_clo_key(raw_clo: Any) -> str:
    text = unicodedata.normalize("NFKC", str(raw_clo or "")).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def build_clo_lookup(clos: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for clo in clos:
        clo_id = str(clo.get("clo") or clo.get("clo_name") or "").strip()
        if not clo_id:
            continue
        key = canonical_clo_key(clo_id)
        lookup.setdefault(key, clo_id)
        match = re.fullmatch(r"CLO(\d+)", key)
        if match:
            lookup.setdefault(f"LO{match.group(1)}", clo_id)
        match = re.fullmatch(r"LO(\d+)", key)
        if match:
            lookup.setdefault(f"CLO{match.group(1)}", clo_id)
    return lookup


def split_clo_tokens(raw_clo: Any) -> list[str]:
    if raw_clo is None:
        return []
    if isinstance(raw_clo, list):
        return [str(item).strip() for item in raw_clo if str(item).strip()]
    return [token.strip() for token in re.split(r"[,;/|]+", str(raw_clo)) if token.strip()]


def resolve_clo_tokens(
    raw_clo: Any,
    clo_lookup: dict[str, str],
    course_code: str,
    assessment: AssessmentRecord,
) -> tuple[list[str], list[dict[str, Any]]]:
    tokens = split_clo_tokens(raw_clo)
    issues: list[dict[str, Any]] = []
    if not tokens:
        return [], [
            {
                "course_code": course_code,
                "assessment": assessment.category,
                "assessment_index": assessment.index,
                "issue": "missing_clo_mapping",
                "raw_clo": raw_clo,
            }
        ]

    resolved: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        clo_id = clo_lookup.get(canonical_clo_key(token))
        if not clo_id:
            issues.append(
                {
                    "course_code": course_code,
                    "assessment": assessment.category,
                    "assessment_index": assessment.index,
                    "issue": "unknown_clo",
                    "raw_clo": token,
                }
            )
            continue
        if clo_id in seen:
            issues.append(
                {
                    "course_code": course_code,
                    "assessment": assessment.category,
                    "assessment_index": assessment.index,
                    "issue": "duplicate_clo_mapping",
                    "raw_clo": token,
                    "resolved_clo": clo_id,
                }
            )
            continue
        resolved.append(clo_id)
        seen.add(clo_id)

    if not resolved:
        issues.append(
            {
                "course_code": course_code,
                "assessment": assessment.category,
                "assessment_index": assessment.index,
                "issue": "no_valid_clo_mapping",
                "raw_clo": raw_clo,
            }
        )
    return resolved, issues


def load_course_data(courses_dir: Path, course_code: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    course_dir = courses_dir / course_code
    clos_path = course_dir / "clos.json"
    assessments_path = course_dir / "assessments.json"

    if not course_dir.exists():
        raise FileNotFoundError(f"Course directory not found: {course_dir}")
    if not clos_path.exists():
        raise FileNotFoundError(f"Missing clos.json for {course_code}: {clos_path}")
    if not assessments_path.exists():
        raise FileNotFoundError(f"Missing assessments.json for {course_code}: {assessments_path}")

    clos = load_json(clos_path)
    assessments = load_json(assessments_path)
    if not isinstance(clos, list):
        raise ValueError(f"{clos_path} must contain a JSON array")
    if not isinstance(assessments, list):
        raise ValueError(f"{assessments_path} must contain a JSON array")
    return clos, assessments


def normalize_assessment_records(raw_assessments: list[dict[str, Any]]) -> list[AssessmentRecord]:
    records: list[AssessmentRecord] = []
    for index, item in enumerate(raw_assessments):
        if not isinstance(item, dict):
            records.append(
                AssessmentRecord(
                    index=index,
                    category="",
                    part="",
                    raw_weight=None,
                    raw_clo=None,
                )
            )
            continue
        records.append(
            AssessmentRecord(
                index=index,
                category=str(item.get("category") or "").strip(),
                part=str(item.get("part") or "").strip(),
                raw_weight=item.get("weight"),
                raw_clo=item.get("clo"),
            )
        )
    return records


def _index_by(records: list[AssessmentRecord], key_fn) -> dict[str, list[AssessmentRecord]]:
    index: dict[str, list[AssessmentRecord]] = defaultdict(list)
    for assessment in records:
        key = key_fn(assessment.category)
        if key:
            index[key].append(assessment)
    return dict(index)


def detect_ambiguous_assessment_keys(
    course_code: str,
    records: list[AssessmentRecord],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    indexes = (
        ("duplicate_canonical_identifier", _index_by(records, lambda item: str(item or ""))),
        ("ambiguous_normalized_identifier", _index_by(records, normalize_assessment_name)),
        ("ambiguous_alias_identifier", _index_by(records, alias_assessment_key)),
    )

    emitted: set[tuple[str, tuple[int, ...]]] = set()
    for issue_type, index in indexes:
        for key, candidates in sorted(index.items()):
            if len(candidates) <= 1:
                continue
            candidate_ids = tuple(item.index for item in candidates)
            marker = (issue_type, candidate_ids)
            if marker in emitted:
                continue
            emitted.add(marker)
            issues.append(
                {
                    "course_code": course_code,
                    "issue": issue_type,
                    "key": key,
                    "candidates": [item.category for item in candidates],
                    "assessment_indexes": [item.index for item in candidates],
                }
            )
    return issues


def match_assessment(
    report_assessment: str,
    records: list[AssessmentRecord],
) -> MatchResult:
    exact_index = _index_by(records, lambda item: str(item or ""))
    normalized_index = _index_by(records, normalize_assessment_name)
    alias_index = _index_by(records, alias_assessment_key)

    for match_type, key, index in (
        ("exact", report_assessment, exact_index),
        ("normalized", normalize_assessment_name(report_assessment), normalized_index),
        ("alias", alias_assessment_key(report_assessment), alias_index),
    ):
        candidates = index.get(key, [])
        if len(candidates) == 1:
            return MatchResult(candidates[0], match_type, [candidates[0].category])
        if len(candidates) > 1:
            return MatchResult(None, f"ambiguous_{match_type}", [item.category for item in candidates])

    return MatchResult(None, "unmatched", [])


def score_course_records(
    course_code: str,
    clos: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    grades: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = normalize_assessment_records(assessments)
    clo_lookup = build_clo_lookup(clos)
    canonical_clo_ids = [
        str(item.get("clo") or item.get("clo_name") or "").strip()
        for item in clos
        if str(item.get("clo") or item.get("clo_name") or "").strip()
    ]

    course_report: dict[str, Any] = {
        "course_code": course_code,
        "status": "processed",
        "assessment_count": len(records),
        "clo_count": len(canonical_clo_ids),
        "matched_assessments": [],
        "missing_canonical_assessment_grades": [],
        "unmatched_report_assessments": [],
        "duplicate_or_ambiguous_assessment_matches": detect_ambiguous_assessment_keys(course_code, records),
        "invalid_clo_mappings": [],
        "invalid_assessment_weights": [],
        "invalid_assessment_grades": [],
        "unexpected_weight_total": None,
        "clo_results": [],
    }

    parsed_weights: dict[int, float] = {}
    course_weight_total = 0.0
    for assessment in records:
        try:
            weight = parse_weight(assessment.raw_weight)
        except (TypeError, ValueError) as exc:
            course_report["invalid_assessment_weights"].append(
                {
                    "course_code": course_code,
                    "assessment": assessment.category,
                    "assessment_index": assessment.index,
                    "raw_weight": assessment.raw_weight,
                    "issue": str(exc),
                }
            )
            continue
        parsed_weights[assessment.index] = weight
        course_weight_total += weight

    if records and abs(course_weight_total - 100.0) > 0.01:
        course_report["unexpected_weight_total"] = {
            "course_code": course_code,
            "expected": 100.0,
            "actual": round(course_weight_total, 4),
        }

    mapped_clos_by_assessment: dict[int, list[str]] = {}
    for assessment in records:
        resolved, issues = resolve_clo_tokens(assessment.raw_clo, clo_lookup, course_code, assessment)
        mapped_clos_by_assessment[assessment.index] = resolved
        course_report["invalid_clo_mappings"].extend(issues)

    matched_by_index: dict[int, str] = {}
    grade_matches: dict[int, tuple[str, Any, str]] = {}
    for report_assessment, raw_grade in grades.items():
        match = match_assessment(report_assessment, records)
        if not match.assessment:
            issue = {
                "course_code": course_code,
                "report_assessment": report_assessment,
                "issue": match.match_type,
                "candidates": match.candidates,
            }
            if match.match_type.startswith("ambiguous"):
                course_report["duplicate_or_ambiguous_assessment_matches"].append(issue)
            else:
                course_report["unmatched_report_assessments"].append(issue)
            continue

        assessment = match.assessment
        if assessment.index in matched_by_index:
            course_report["duplicate_or_ambiguous_assessment_matches"].append(
                {
                    "course_code": course_code,
                    "report_assessment": report_assessment,
                    "canonical_assessment": assessment.category,
                    "issue": "duplicate_report_match",
                    "first_report_assessment": matched_by_index[assessment.index],
                }
            )
            continue

        matched_by_index[assessment.index] = report_assessment
        grade_matches[assessment.index] = (report_assessment, raw_grade, match.match_type)
        course_report["matched_assessments"].append(
            {
                "course_code": course_code,
                "report_assessment": report_assessment,
                "canonical_assessment": assessment.category,
                "assessment_index": assessment.index,
                "match_type": match.match_type,
            }
        )

    for assessment in records:
        if assessment.index not in matched_by_index:
            course_report["missing_canonical_assessment_grades"].append(
                {
                    "course_code": course_code,
                    "canonical_assessment": assessment.category,
                    "assessment_index": assessment.index,
                    "issue": "missing_grade",
                }
            )

    accumulators = {
        clo_id: {"weighted_sum": 0.0, "allocated_weight": 0.0, "evidence_count": 0}
        for clo_id in canonical_clo_ids
    }

    for assessment in records:
        if assessment.index not in grade_matches:
            continue
        if assessment.index not in parsed_weights:
            continue
        mapped_clos = mapped_clos_by_assessment.get(assessment.index, [])
        if not mapped_clos:
            continue

        report_assessment, raw_grade, _match_type = grade_matches[assessment.index]
        try:
            grade = parse_grade(raw_grade)
        except (TypeError, ValueError) as exc:
            course_report["invalid_assessment_grades"].append(
                {
                    "course_code": course_code,
                    "report_assessment": report_assessment,
                    "canonical_assessment": assessment.category,
                    "raw_grade": raw_grade,
                    "issue": str(exc),
                }
            )
            continue

        allocated_weight = parsed_weights[assessment.index] / len(mapped_clos)
        for clo_id in mapped_clos:
            accumulator = accumulators[clo_id]
            accumulator["weighted_sum"] += grade * allocated_weight
            accumulator["allocated_weight"] += allocated_weight
            accumulator["evidence_count"] += 1

    profile_clos: list[dict[str, Any]] = []
    for clo in clos:
        clo_id = str(clo.get("clo") or clo.get("clo_name") or "").strip()
        description = str(clo.get("description") or clo.get("clo_details") or "")
        accumulator = accumulators.get(clo_id, {"weighted_sum": 0.0, "allocated_weight": 0.0, "evidence_count": 0})
        total_weight = float(accumulator["allocated_weight"])
        if total_weight > 0:
            score = round(float(accumulator["weighted_sum"]) / total_weight, 2)
        else:
            score = None
        achievement = classify_achievement(score)
        profile_clos.append(
            {
                "clo": clo_id,
                "description": description,
                "score": score,
                "achievement": achievement,
            }
        )
        course_report["clo_results"].append(
            {
                "clo": clo_id,
                "score": score,
                "achievement": achievement,
                "total_allocated_weight": round(total_weight, 4),
                "evidence_count": int(accumulator["evidence_count"]),
            }
        )

    return {"course_code": course_code, "clos": profile_clos}, course_report


def build_profile_from_report(
    academic_report: dict[str, Any],
    courses_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile: dict[str, Any] = {"profile_type": "academic", "courses": []}
    course_reports: list[dict[str, Any]] = []
    courses_could_not_be_processed: list[dict[str, Any]] = []
    metadata_errors: list[dict[str, Any]] = []

    for course_code, grades in academic_report.items():
        if not isinstance(grades, dict):
            courses_could_not_be_processed.append(
                {
                    "course_code": course_code,
                    "issue": "course_grades_must_be_object",
                }
            )
            continue

        try:
            clos, assessments = load_course_data(courses_dir, course_code)
        except (OSError, ValueError) as exc:
            courses_could_not_be_processed.append(
                {
                    "course_code": course_code,
                    "issue": str(exc),
                }
            )
            continue

        profile_course, course_report = score_course_records(course_code, clos, assessments, grades)
        try:
            metadata = read_course_metadata(courses_dir, course_code)
            profile_course = {"course_code": course_code, "metadata": metadata, "clos": profile_course["clos"]}
        except (OSError, ValueError, UnicodeError) as exc:
            metadata_errors.append({"course_code": course_code,
                                    "path": str(courses_dir / course_code / "metadata.json"),
                                    "issue": str(exc)})
        profile["courses"].append(profile_course)
        course_reports.append(course_report)

    total_clos = sum(len(course["clos"]) for course in profile["courses"])
    clos_with_scores = sum(
        1
        for course in profile["courses"]
        for clo in course["clos"]
        if clo["score"] is not None
    )

    report = {
        "report_type": "clo_scoring_validation",
        "academic_report_courses": len(academic_report),
        "processed_courses": len(profile["courses"]),
        "courses_with_metadata": len(profile["courses"]) - len(metadata_errors),
        "courses_without_metadata": len(metadata_errors),
        "metadata_validation_errors": metadata_errors,
        "total_clos_evaluated": total_clos,
        "clos_with_scores": clos_with_scores,
        "clos_with_missing_scores": total_clos - clos_with_scores,
        "missing_or_unmatched_assessment_grades": [],
        "missing_canonical_assessment_grades": [],
        "duplicate_or_ambiguous_assessment_matches": [],
        "invalid_clo_mappings": [],
        "invalid_assessment_weights": [],
        "invalid_assessment_grades": [],
        "unexpected_course_weight_totals": [],
        "courses_could_not_be_processed": courses_could_not_be_processed,
        "courses": course_reports,
    }

    for course_report in course_reports:
        missing_canonical = course_report["missing_canonical_assessment_grades"]
        unmatched_report = course_report["unmatched_report_assessments"]
        report["missing_canonical_assessment_grades"].extend(missing_canonical)
        report["missing_or_unmatched_assessment_grades"].extend(unmatched_report)
        report["missing_or_unmatched_assessment_grades"].extend(missing_canonical)
        report["duplicate_or_ambiguous_assessment_matches"].extend(
            course_report["duplicate_or_ambiguous_assessment_matches"]
        )
        report["invalid_clo_mappings"].extend(course_report["invalid_clo_mappings"])
        report["invalid_assessment_weights"].extend(course_report["invalid_assessment_weights"])
        report["invalid_assessment_grades"].extend(course_report["invalid_assessment_grades"])
        if course_report["unexpected_weight_total"]:
            report["unexpected_course_weight_totals"].append(course_report["unexpected_weight_total"])

    return profile, report


def build_student_academic_profile(
    academic_report_path: Path | str,
    courses_dir: Path | str,
    output_path: Path | str | None = None,
    report_output_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    academic_report_file = Path(academic_report_path)
    courses_root = Path(courses_dir)
    academic_report = load_json(academic_report_file)
    if not isinstance(academic_report, dict):
        raise ValueError(f"{academic_report_file} must contain a JSON object")

    profile, report = build_profile_from_report(academic_report, courses_root)

    if output_path is not None:
        write_json(Path(output_path), profile)
    if report_output_path is not None:
        write_json(Path(report_output_path), report)

    return profile, report
