"""Build an immutable text-only comparison source, without inference or I/O writes."""

from collections.abc import Sequence
from app.engines.models import validate_clo_set
from .course_service import CourseService
from .errors import CLOSetValidationError


class CLOSetService:
    def __init__(self, course_service: CourseService):
        self.course_service = course_service

    def build_clo_set(self, selected_courses, *, curriculum_code=None):
        if (not isinstance(selected_courses, Sequence) or isinstance(selected_courses, (str, bytes))
                or not selected_courses or any(not isinstance(c, str) or not c.strip() for c in selected_courses)):
            raise CLOSetValidationError([{"issue": "invalid_course_selection"}])
        selected = list(selected_courses)
        if len(set(selected)) != len(selected):
            raise CLOSetValidationError([{"issue": "duplicate_selected_courses"}])
        constraints = self.course_service.get_selection_constraints(curriculum_code)
        issues = []
        for slot in constraints["exclusive_slots"]:
            conflicts = [code for code in selected if code in slot["course_codes"]]
            if len(conflicts) > 1:
                issues.append({"issue": "duplicate_combo_slot_selection", "curriculum_code": slot["curriculum_code"],
                               "slot_identifier": slot["slot_identifier"], "conflicting_course_codes": conflicts})
        if issues:
            raise CLOSetValidationError(issues)
        source = {"courses": [{"course_code": code,
            "clos": self.course_service.get_course_clos(code, curriculum_code)} for code in selected]}
        return validate_clo_set(source).model_dump()
