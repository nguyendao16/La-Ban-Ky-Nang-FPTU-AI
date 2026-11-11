from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services import GradeEntry, ProfileService, ScoreValidationError, UnknownCourseError
from scripts.clo_scoring import build_profile_from_report, classify_achievement

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.usefixtures("service_offline")


def test_mapping_entries_aliases_and_equivalent_ordered_output(service_catalog):
    service = ProfileService(service_catalog)
    mapping = {"TEST101": {"Quiz 1": 10, "Final exam": 8}}
    entries = [GradeEntry("TEST101", "final EXAM", "8"), GradeEntry("TEST101", "Quiz-1", "10")]
    profile, report = service.build_profile_with_report(["TEST101"], mapping)
    assert profile == service.build_profile(["TEST101"], entries)
    assert profile == build_profile_from_report(mapping, service_catalog.courses_dir)[0]
    assert [c["score"] for c in profile["courses"][0]["clos"]] == [8, 8.8]
    assert report == service.validate_scores(["TEST101"], mapping)
    assert profile["courses"][0]["metadata"]["tools"] == ""


@pytest.mark.parametrize("score", [0, 4.99, 5, 6.99, 7, 8.49, 8.5, 10])
def test_thresholds_are_engine_thresholds(service_catalog, score):
    profile = ProfileService(service_catalog).build_profile(["TEST101"], {"TEST101": {"Quiz 1": score, "Final exam": score}})
    assert all(c["score"] == score and c["achievement"] == classify_achievement(score)
               for c in profile["courses"][0]["clos"])


@pytest.mark.parametrize("grade", [None, True, False, -1, 10.1, float("nan"), float("inf"), "", "bad", [], 10**1000])
def test_invalid_and_missing_numeric_grades(service_catalog, grade):
    with pytest.raises(ScoreValidationError) as error:
        ProfileService(service_catalog).build_profile(["TEST101"], {"TEST101": {"Quiz 1": grade, "Final exam": 8}})
    assert error.value.issues and error.value.report is not None


def test_missing_is_rejected_and_zero_is_observed(service_catalog):
    service = ProfileService(service_catalog)
    with pytest.raises(ScoreValidationError) as error:
        service.build_profile(["TEST101"], {"TEST101": {"Final exam": 0}})
    assert {i["category"] for i in error.value.issues if i["issue"] == "missing_grade"} == {"Quiz 1"}
    profile = service.build_profile(["TEST101"], {"TEST101": {"Quiz 1": 0, "Final exam": 0}})
    assert all(c["score"] == 0 and c["achievement"] == "below_expected" for c in profile["courses"][0]["clos"])
    legacy, _ = build_profile_from_report({"TEST101": {"Final exam": 8}}, service_catalog.courses_dir)
    assert all(c["score"] == 8 for c in legacy["courses"][0]["clos"])


@pytest.mark.parametrize("entries", [
    [GradeEntry("TEST101", "Quiz 1", 8), GradeEntry("TEST101", "Quiz 1", 7), GradeEntry("TEST101", "Final exam", 8)],
    [GradeEntry("TEST101", "Quiz 1", 8), GradeEntry("TEST101", "Quiz-1", 7), GradeEntry("TEST101", "Final exam", 8)],
])
def test_duplicate_exact_and_alias_entries(service_catalog, entries):
    with pytest.raises(ScoreValidationError) as error:
        ProfileService(service_catalog).build_profile(["TEST101"], entries)
    assert any(i["issue"] == "duplicate_assessment_entry" for i in error.value.issues)


@pytest.mark.parametrize("selected,scores,issue", [
    (["TEST101", "TEST101"], {}, "duplicate_selected_courses"),
    (["TEST101"], {"TEST101": {"Unknown": 8}}, "unknown_or_ambiguous_assessment"),
    (["TEST101"], {"OTHER201": {"Quiz 1": 8}}, "scores_for_unselected_course"),
    (["TEST101"], [GradeEntry("OTHER201", "Quiz 1", 8)], "scores_for_unselected_course"),
    (["TEST101"], {"TEST101": {1: 8}}, "invalid_assessment_identifier"),
    (["TEST101"], {"TEST101": []}, "course_grades_must_be_object"),
    (["TEST101"], ["bad"], "invalid_grade_entry"),
    ([], {}, "selected_courses_must_be_nonempty_sequence"),
    ("TEST101", {}, "selected_courses_must_be_nonempty_sequence"),
    ([None], {}, "invalid_course_selection"),
    (["TEST101"], None, "scores_must_be_mapping_or_grade_entries"),
])
def test_input_failures_have_structured_issues(service_catalog, selected, scores, issue):
    with pytest.raises(ScoreValidationError) as error:
        ProfileService(service_catalog).build_profile(selected, scores)
    assert any(i["issue"] == issue for i in error.value.issues)


def test_unknown_course_and_selected_order(service_catalog):
    service = ProfileService(service_catalog)
    with pytest.raises(UnknownCourseError):
        service.build_profile(["FOREIGN301"], {})
    scores = {"TEST101": {"Quiz 1": 8, "Final exam": 8}, "OTHER201": {"Quiz 1": 5, "Final exam": 5}}
    profile = service.build_profile(["OTHER201", "TEST101"], scores)
    assert [c["course_code"] for c in profile["courses"]] == ["OTHER201", "TEST101"]
    assert len(service.build_profile(["TEST101"], {"TEST101": scores["TEST101"]})["courses"]) == 1


def test_actual_legacy_equivalence_and_no_global_writes(actual_course_service):
    protected = [p for p in (ROOT / "data").rglob("*") if p.is_file()] + [ROOT / "academic_report.json", ROOT / ".env"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    scores = json.loads((ROOT / "academic_report.json").read_text())
    actual, actual_report = ProfileService(actual_course_service).build_profile_with_report(list(scores), scores)
    legacy, legacy_report = build_profile_from_report(scores, ROOT / "data/courses")
    assert actual == legacy == json.loads((ROOT / "data/student_academic_profile.enriched.json").read_text())
    assert actual_report == legacy_report
    assert len(actual["courses"]) == 15 and sum(len(c["clos"]) for c in actual["courses"]) == 122
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected} == before


@pytest.mark.parametrize("code,diagnostic", [("SSG105", "invalid_clo_mappings"), ("IMP302", "unexpected_course_weight_totals")])
def test_existing_source_diagnostics_keep_engine_calculation(actual_course_service, code, diagnostic):
    definitions = actual_course_service.get_course_assessments(code)["assessments"]
    scores = {code: {a["category"]: 8 for a in definitions}}
    profile, report = ProfileService(actual_course_service).build_profile_with_report([code], scores)
    assert (profile, report) == build_profile_from_report(scores, actual_course_service.courses_dir)
    assert report[diagnostic]
