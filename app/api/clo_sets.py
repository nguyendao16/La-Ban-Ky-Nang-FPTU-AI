"""Public selections contain no engine source or source fingerprints."""
from fastapi import APIRouter, Request, Response
from app.schemas.requests import SelectionRequest
from app.schemas.responses import CreatedSelectionResponse, SelectionResponse
from app.services.clo_set_service import CLOSetService
from app.services.errors import UnknownCourseError
from .dependencies import Backend, Capability, Catalog

router = APIRouter(prefix='/selections', tags=['Selections'])


def selection_response(stored):
    result = {'selection_id': stored['clo_set_id'], 'curriculum_code': stored['curriculum_code'],
              'selected_courses': stored['selected_courses'], 'status': 'ready',
              'summary': {'course_count': len(stored['selected_courses'])}, 'created_at': stored['created_at']}
    if 'access_token' in stored:
        result['access_token'] = stored['access_token']
    return result


@router.post('', status_code=201, response_model=CreatedSelectionResponse)
def create_selection(body: SelectionRequest, backend: Backend, catalog: Catalog, response: Response, request: Request):
    plan = request.app.state.semester_map
    plan.validate_selection(body.selected_courses, body.combo)
    members = {r['course_code'] for r in catalog.list_courses(body.curriculum_code)}
    mapped = [c for c in body.selected_courses if c not in plan.PRESENTATION_ONLY]
    excluded = [c for c in body.selected_courses if c in plan.PRESENTATION_ONLY]
    if any(c not in members for c in mapped):
        raise UnknownCourseError('Course is outside the configured curriculum')
    source = CLOSetService(catalog).build_clo_set(mapped, curriculum_code=body.curriculum_code) if mapped else {'courses': []}
    stored = backend.clo_sets.create(body.curriculum_code, body.selected_courses, source,
                                    {'excluded_courses': excluded})
    response.headers['Cache-Control'] = 'no-store'
    return selection_response(stored)


@router.get('/{selection_id}', response_model=SelectionResponse)
def get_selection(selection_id: str, backend: Backend, capability: Capability, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return selection_response(backend.clo_sets.get(selection_id, capability))
