"""Strict in-memory grade input over the unchanged deterministic builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.academic_review import ReviewError, validate_profile
from scripts.clo_scoring import (
    build_profile_from_report, match_assessment, normalize_assessment_records, parse_grade,
)

from .course_service import CourseService
from .errors import CourseDataError, ScoreValidationError


@dataclass(frozen=True)
class GradeEntry:
    course_code: str
    category: str
    grade: float | int | str | None


GradeInput = Mapping[str, Mapping[str, Any]] | Sequence[GradeEntry]


class ProfileService:
    """Require complete submitted grades; retain legacy source diagnostics.

    build_profile_with_report() exposes the engine's mapping/weight diagnostics.
    The legacy CLI continues accepting partial reports independently.
    """

    def __init__(self, course_service: CourseService):
        self.course_service = course_service

    def _build(self, selected_courses: Sequence[str], assessment_scores: GradeInput, curriculum_code=None):
        issues: list[dict[str, Any]] = []
        if (not isinstance(selected_courses, Sequence) or isinstance(selected_courses, (str, bytes))
                or not selected_courses):
            raise ScoreValidationError([{"issue": "selected_courses_must_be_nonempty_sequence"}])
        selected = list(selected_courses)
        if any(not isinstance(code, str) or not code.strip() for code in selected):
            raise ScoreValidationError([{"issue": "invalid_course_selection"}])
        if len(set(selected)) != len(selected):
            raise ScoreValidationError([{"issue": "duplicate_selected_courses"}])

        records = {}
        for code in selected:
            self.course_service.get_course(code, curriculum_code)
            self.course_service.get_course_clos(code, curriculum_code)
            raw = self.course_service.get_course_assessments(code, curriculum_code)["assessments"]
            records[code] = normalize_assessment_records(raw)

        constraints = self.course_service.get_selection_constraints(curriculum_code)
        for slot in constraints["exclusive_slots"]:
            conflicts = [code for code in selected if code in slot["course_codes"]]
            if len(conflicts) > 1:
                issues.append({"issue": "duplicate_combo_slot_selection", "curriculum_code": slot["curriculum_code"],
                               "slot_identifier": slot["slot_identifier"], "conflicting_course_codes": conflicts})
        if issues:
            raise ScoreValidationError(issues)

        if isinstance(assessment_scores, Mapping):
            entries = []
            for code, grades in assessment_scores.items():
                if not isinstance(code, str) or code not in records:
                    issues.append({"course_code": code, "issue": "scores_for_unselected_course"})
                    continue
                if not isinstance(grades, Mapping):
                    issues.append({"course_code": code, "issue": "course_grades_must_be_object"})
                    continue
                entries.extend(GradeEntry(code, category, grade) for category, grade in grades.items())
        elif isinstance(assessment_scores, Sequence) and not isinstance(assessment_scores, (str, bytes)):
            entries = list(assessment_scores)
        else:
            raise ScoreValidationError([{"issue": "scores_must_be_mapping_or_grade_entries"}])

        academic_report: dict[str, dict[str, Any]] = {code: {} for code in selected}
        matched = {code: set() for code in selected}
        for entry in entries:
            if not isinstance(entry, GradeEntry):
                issues.append({"issue": "invalid_grade_entry"})
                continue
            code, category, grade = entry.course_code, entry.category, entry.grade
            if not isinstance(code, str) or code not in records:
                issues.append({"course_code": code, "issue": "scores_for_unselected_course"})
                continue
            if not isinstance(category, str) or not category.strip():
                issues.append({"course_code": code, "issue": "invalid_assessment_identifier"})
                continue
            match = match_assessment(category, records[code])
            if match.assessment is None:
                issues.append({"course_code": code, "category": category,
                               "issue": "unknown_or_ambiguous_assessment", "match_type": match.match_type})
            elif match.assessment.index in matched[code]:
                issues.append({"course_code": code, "category": category, "issue": "duplicate_assessment_entry"})
            else:
                matched[code].add(match.assessment.index)
            try:
                if isinstance(grade, bool):
                    raise ValueError("Boolean is not a grade")
                parse_grade(grade)
            except (TypeError, ValueError, OverflowError):
                issues.append({"course_code": code, "category": category,
                               "issue": "missing_grade" if grade is None else "invalid_grade"})
            # Preserve the first exact key for diagnostics; no duplicate is accepted.
            academic_report[code].setdefault(category, grade)

        for code in selected:
            for assessment in records[code]:
                if assessment.index not in matched[code]:
                    issues.append({"course_code": code, "category": assessment.category, "issue": "missing_grade"})

        if any(issue["issue"] == "invalid_grade" for issue in issues):
            # Do not pass unsupported/overflowing Python numeric values to the
            # permissive legacy engine. No profile is built for rejected input.
            raise ScoreValidationError(issues, {"report_type": "score_input_validation", "issues": issues})
        profile, report = build_profile_from_report(academic_report, self.course_service.courses_dir)
        if issues:
            raise ScoreValidationError(issues, report)
        if report["courses_could_not_be_processed"] or report["metadata_validation_errors"]:
            raise CourseDataError("Course sources changed or are unusable during profile construction")
        # Mapping/weight-total diagnostics deliberately keep the engine's policy.
        try:
            validate_profile(profile)
        except ReviewError as exc:
            raise CourseDataError("Canonical sources cannot produce a valid academic profile") from exc
        return profile, report

    def build_profile(self, selected_courses: Sequence[str], assessment_scores: GradeInput,
                      *, curriculum_code: str | None = None) -> dict[str, Any]:
        return self._build(selected_courses, assessment_scores, curriculum_code)[0]

    def build_profile_with_report(
        self, selected_courses: Sequence[str], assessment_scores: GradeInput,
        *, curriculum_code: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._build(selected_courses, assessment_scores, curriculum_code)

    def validate_scores(self, selected_courses: Sequence[str], assessment_scores: GradeInput,
                        *, curriculum_code: str | None = None) -> dict[str, Any]:
        return self._build(selected_courses, assessment_scores, curriculum_code)[1]
