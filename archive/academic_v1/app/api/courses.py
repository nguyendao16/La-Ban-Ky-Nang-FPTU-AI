from fastapi import APIRouter

from app.schemas.responses import CourseDetailResponse, CourseListResponse
from app.services.errors import UnknownCourseError

from .dependencies import Catalog

router = APIRouter(prefix="/courses", tags=["Courses"])


def public_entry(entry):
    return {**entry, "diagnostics": [{"field": d["field"], "issue": d["issue"], "message": "Source data unavailable"}
                                     for d in entry["diagnostics"]]}


@router.get("", response_model=CourseListResponse)
def list_courses(catalog: Catalog, curriculum_code: str | None = None):
    code = catalog.default_curriculum_code if curriculum_code is None else curriculum_code
    return {"curriculum_code": code, "courses": [public_entry(r) for r in catalog.list_courses(code)],
            "selection_constraints": catalog.get_selection_constraints(code)}


@router.get("/{course_code}", response_model=CourseDetailResponse)
def get_course(course_code: str, catalog: Catalog, curriculum_code: str | None = None):
    code = catalog.default_curriculum_code if curriculum_code is None else curriculum_code
    row = next((r for r in catalog.list_courses(code) if r["course_code"] == course_code), None)
    if row is None:
        raise UnknownCourseError("Course is not in the requested curriculum")
    row = public_entry(row)
    return {"course_code": course_code, "curriculum_code": code, "catalog": row,
            "metadata": catalog.get_course(course_code, code) if row["availability"]["metadata"] else None,
            "assessments": catalog.get_course_assessments(course_code, code)["assessments"] if row["availability"]["assessments"] else None,
            "availability": row["availability"], "diagnostics": row["diagnostics"]}
