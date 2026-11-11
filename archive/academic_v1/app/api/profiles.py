from fastapi import APIRouter, Response

from app.schemas.requests import ProfileRequest
from app.schemas.responses import CreatedProfileResponse, ProfileResponse
from app.services.profile_service import GradeEntry, ProfileService

from .dependencies import Backend, Capability, Catalog

router = APIRouter(prefix="/profiles", tags=["Profiles"])


def profile_response(stored):
    profile = stored["profile"]
    return {**stored, "status": "ready", "summary": {"course_count": len(profile["courses"]),
                                                      "clo_count": sum(len(c["clos"]) for c in profile["courses"])}}


@router.post("", status_code=201, response_model=CreatedProfileResponse)
def create_profile(body: ProfileRequest, backend: Backend, catalog: Catalog, response: Response):
    grades = [g.model_dump() for g in body.grades]
    profile, report = ProfileService(catalog).build_profile_with_report(
        body.selected_courses, [GradeEntry(**g) for g in grades], curriculum_code=body.curriculum_code,
    )
    stored = backend.profiles.create(body.curriculum_code, body.selected_courses, grades, profile, report)
    response.headers["Cache-Control"] = "no-store"
    return profile_response(stored)


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, backend: Backend, capability: Capability, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return profile_response(backend.profiles.get(profile_id, capability))
