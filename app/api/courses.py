from fastapi import APIRouter, Request, Response
from app.schemas.responses import CourseDetailResponse, CourseListResponse
from app.services.errors import UnknownCourseError
from .dependencies import Catalog

router = APIRouter(prefix='/courses', tags=['Courses'])


def public_entry(entry):
    return {k: entry.get(k) for k in ('course_code', 'name', 'semester', 'credits', 'curriculum_code')}


@router.get('', response_model=CourseListResponse)
def list_courses(catalog: Catalog, request: Request, response: Response, curriculum_code: str | None = None):
    code = catalog.default_curriculum_code if curriculum_code is None else curriculum_code
    plan = request.app.state.semester_map
    rows = {r['course_code']: public_entry(r) for r in catalog.list_courses(code)}
    courses = []
    for track in plan.TRACKS:
        for semester in plan.semesters(track):
            for identifier in semester['course_codes']:
                if any(c['course_code'] == identifier for c in courses):
                    continue
                courses.append(rows.get(identifier, {'course_code': identifier, 'name': {},
                    'semester': semester['semester'], 'credits': None, 'curriculum_code': code}))
    response.headers['Cache-Control'] = 'no-store'
    return {'curriculum_code': code, 'courses': courses, 'semester_map': plan.public()}


@router.get('/{course_code}', response_model=CourseDetailResponse)
def get_course(course_code: str, catalog: Catalog, response: Response, request: Request, curriculum_code: str | None = None):
    code = catalog.default_curriculum_code if curriculum_code is None else curriculum_code
    row = next((r for r in catalog.list_courses(code) if r['course_code'] == course_code), None)
    if row is None and course_code in request.app.state.semester_map.PRESENTATION_ONLY:
        for semester in request.app.state.semester_map.semesters(request.app.state.semester_map.TRACKS[0]):
            if course_code in semester['course_codes']:
                row = {'course_code': course_code, 'name': {}, 'semester': semester['semester'], 'credits': None, 'curriculum_code': code}
                break
    if row is None:
        raise UnknownCourseError('Course is not in the requested curriculum')
    response.headers['Cache-Control'] = 'no-store'
    return public_entry(row)
