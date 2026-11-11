from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from clo_scoring import (  # noqa: E402
    build_profile_from_report,
    classify_achievement,
    score_course_records,
)


def clos(*ids: str) -> list[dict[str, str]]:
    return [{"clo": clo_id, "description": f"description for {clo_id}"} for clo_id in ids]


def assessment(category: str, weight: str, mapped_clos: str) -> dict[str, str]:
    return {
        "category": category,
        "part": "1",
        "weight": weight,
        "clo": mapped_clos,
    }


def score_one_course(
    course_clos: list[dict[str, str]],
    course_assessments: list[dict[str, str]],
    grades: dict[str, float],
):
    return score_course_records("TST101", course_clos, course_assessments, grades)


def test_single_assessment_mapped_to_one_clo():
    profile, report = score_one_course(
        clos("CLO1"),
        [assessment("Quiz", "20.0%", "CLO1")],
        {"Quiz": 8.0},
    )

    assert profile["clos"][0]["score"] == 8.0
    assert profile["clos"][0]["achievement"] == "good"
    assert report["clo_results"][0]["total_allocated_weight"] == 20.0


def test_assessment_mapped_to_multiple_clos_splits_weight_not_grade():
    profile, report = score_one_course(
        clos("CLO1", "CLO2"),
        [assessment("Project", "20.0%", "CLO1, CLO2")],
        {"Project": 8.0},
    )

    assert [item["score"] for item in profile["clos"]] == [8.0, 8.0]
    assert [item["total_allocated_weight"] for item in report["clo_results"]] == [10.0, 10.0]


def test_multiple_weighted_assessments_use_weighted_average():
    profile, _report = score_one_course(
        clos("CLO1"),
        [
            assessment("A1", "20.0%", "CLO1"),
            assessment("A2", "10.0%", "CLO1"),
        ],
        {"A1": 10.0, "A2": 0.0},
    )

    assert profile["clos"][0]["score"] == 6.67
    assert profile["clos"][0]["achievement"] == "basic"


def test_exact_assessment_name_matching():
    profile, report = score_one_course(
        clos("CLO1"),
        [assessment("Final exam", "100.0%", "CLO1")],
        {"Final exam": 7.5},
    )

    assert profile["clos"][0]["score"] == 7.5
    assert report["matched_assessments"][0]["match_type"] == "exact"


def test_confirmed_spelling_variation_aliases_match():
    profile, report = score_one_course(
        clos("CLO1", "CLO2"),
        [
            assessment("Progress Test 1", "50.0%", "CLO1"),
            assessment("Exercise 1", "50.0%", "CLO2"),
        ],
        {"Progress tess 1": 9.0, "Exercices 1": 6.0},
    )

    assert [item["score"] for item in profile["clos"]] == [9.0, 6.0]
    assert [item["match_type"] for item in report["matched_assessments"]] == ["alias", "alias"]


def test_missing_assessment_grade_is_excluded_not_zeroed():
    profile, report = score_one_course(
        clos("CLO1"),
        [
            assessment("A1", "50.0%", "CLO1"),
            assessment("A2", "50.0%", "CLO1"),
        ],
        {"A1": 8.0},
    )

    assert profile["clos"][0]["score"] == 8.0
    assert report["missing_canonical_assessment_grades"][0]["canonical_assessment"] == "A2"


def test_zero_grade_is_valid_observed_grade():
    profile, report = score_one_course(
        clos("CLO1"),
        [assessment("Quiz", "100.0%", "CLO1")],
        {"Quiz": 0.0},
    )

    assert profile["clos"][0]["score"] == 0.0
    assert profile["clos"][0]["achievement"] == "below_expected"
    assert report["invalid_assessment_grades"] == []


def test_clo_with_no_graded_evidence_is_not_evaluated():
    profile, _report = score_one_course(
        clos("CLO1", "CLO2"),
        [assessment("Quiz", "100.0%", "CLO1")],
        {"Quiz": 8.0},
    )

    assert profile["clos"][1]["score"] is None
    assert profile["clos"][1]["achievement"] == "not_evaluated"


def test_invalid_or_missing_clo_mapping_is_reported_and_skipped():
    profile, report = score_one_course(
        clos("CLO1"),
        [
            assessment("Unknown", "50.0%", "CLO99"),
            assessment("Missing", "50.0%", ""),
        ],
        {"Unknown": 9.0, "Missing": 9.0},
    )

    assert profile["clos"][0]["score"] is None
    assert {item["issue"] for item in report["invalid_clo_mappings"]} >= {
        "unknown_clo",
        "missing_clo_mapping",
    }


def test_duplicate_or_ambiguous_assessment_names_are_reported_without_guessing():
    profile, report = score_one_course(
        clos("CLO1"),
        [
            assessment("Quiz 1", "50.0%", "CLO1"),
            assessment("Quiz-1", "50.0%", "CLO1"),
        ],
        {"Quiz.1": 9.0},
    )

    assert profile["clos"][0]["score"] is None
    issues = report["duplicate_or_ambiguous_assessment_matches"]
    assert any(item["issue"] == "ambiguous_normalized_identifier" for item in issues)
    assert any(item["issue"] == "ambiguous_normalized" for item in issues)


def test_normalized_split_assessment_records_are_not_double_counted():
    profile, report = score_one_course(
        clos("CLO1"),
        [
            assessment("Progress Test 1", "10.0%", "CLO1"),
            assessment("Progress Test 2", "10.0%", "CLO1"),
        ],
        {"Progress tess 1": 6.0, "Progress tess 2": 10.0},
    )

    assert profile["clos"][0]["score"] == 8.0
    assert report["clo_results"][0]["total_allocated_weight"] == 20.0
    assert len(report["matched_assessments"]) == 2


@pytest.mark.parametrize(
    ("score", "achievement"),
    [
        (None, "not_evaluated"),
        (0.0, "below_expected"),
        (4.99, "below_expected"),
        (5.0, "basic"),
        (6.99, "basic"),
        (7.0, "good"),
        (8.49, "good"),
        (8.5, "excellent"),
        (10.0, "excellent"),
    ],
)
def test_achievement_thresholds(score, achievement):
    assert classify_achievement(score) == achievement


def test_original_enriched_descriptions_and_clo_order_are_preserved():
    course_clos = [
        {"clo": "CLO2", "description": "Second description, unchanged."},
        {"clo": "CLO1", "description": "First description, unchanged."},
    ]
    profile, _report = score_one_course(
        course_clos,
        [
            assessment("A", "50.0%", "CLO1"),
            assessment("B", "50.0%", "CLO2"),
        ],
        {"A": 7.0, "B": 8.0},
    )

    assert [item["clo"] for item in profile["clos"]] == ["CLO2", "CLO1"]
    assert [item["description"] for item in profile["clos"]] == [
        "Second description, unchanged.",
        "First description, unchanged.",
    ]


def test_profile_json_schema_and_deterministic_output_order(tmp_path: Path):
    course_dir = tmp_path / "courses" / "TST101"
    course_dir.mkdir(parents=True)
    (course_dir / "clos.json").write_text(
        json.dumps(
            [
                {"clo": "CLO1", "description": "Alpha"},
                {"clo": "CLO2", "description": "Beta"},
            ]
        ),
        encoding="utf-8",
    )
    (course_dir / "assessments.json").write_text(
        json.dumps([assessment("Quiz", "100.0%", "CLO1")]),
        encoding="utf-8",
    )

    profile, report = build_profile_from_report({"TST101": {"Quiz": 7.0}}, tmp_path / "courses")

    assert list(profile.keys()) == ["profile_type", "courses"]
    assert list(profile["courses"][0].keys()) == ["course_code", "clos"]
    assert list(profile["courses"][0]["clos"][0].keys()) == [
        "clo",
        "description",
        "score",
        "achievement",
    ]
    assert [item["clo"] for item in profile["courses"][0]["clos"]] == ["CLO1", "CLO2"]
    assert profile["courses"][0]["clos"][1]["achievement"] == "not_evaluated"
    assert report["processed_courses"] == 1
