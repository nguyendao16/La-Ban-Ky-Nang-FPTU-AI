"""FastAPI process; importing/starting never launches a comparison worker."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import advisor as advisor_routes, courses, health, clo_sets, careers
from app.api.body_limit import BodyLimitMiddleware
from app.api.errors import register_handlers
from app.config import BackendSettings
from app.services.advisor_service import AdvisorService
from app.services.course_service import CourseService
from app.services.persistent_advisor import PersistentAdvisor
from app.storage.database import Database
from app.storage.job_repository import JobRepository
from app.storage.clo_set_repository import CLOSetRepository
from app.storage.session_repository import SessionRepository
from app.schemas.responses import ErrorResponse
from app.services.errors import IncompatibleDatabaseError


@dataclass
class Backend:
    settings: BackendSettings
    database: Database
    clo_sets: CLOSetRepository
    sessions: SessionRepository
    jobs: JobRepository
    advisor: AdvisorService
    persistent: PersistentAdvisor


def create_app(settings=None, *, advisor_service=None, course_service=None, database=None, semester_map=None, career_catalog=None):
    settings = BackendSettings.from_env() if settings is None else settings
    @asynccontextmanager
    async def lifespan(application):
        db = database or Database(settings.database_path, lease_seconds=settings.lease_seconds)
        advisor = advisor_service or AdvisorService(max_turns=settings.max_turns, max_message_chars=settings.max_message_chars,
                                                    result_cache_dir=settings.result_cache_dir)
        try:
            db.initialize()
            sessions = SessionRepository(db, advisor.validate_snapshot)
            jobs = JobRepository(db, sessions)
            application.state.backend = Backend(settings, db, CLOSetRepository(db), sessions, jobs, advisor,
                                                PersistentAdvisor(advisor, sessions, settings=settings, career_catalog=career_catalog, jobs=jobs))
        except (OSError, sqlite3.Error, IncompatibleDatabaseError) as error:
            application.state.backend = None
            application.state.database_error = str(error) if isinstance(error, IncompatibleDatabaseError) else None
        if course_service is not None:
            application.state.catalog = course_service
        elif settings.curriculum_mapping:
            try:
                application.state.catalog = CourseService(curriculum_mapping=settings.curriculum_mapping,
                    default_curriculum_code=settings.default_curriculum)
                application.state.catalog.list_courses()
            except ValueError:
                application.state.catalog = None
        yield
        advisor.close()

    errors = {status: {"model": ErrorResponse} for status in [401, 403, 404, 409, 413, 422, 500, 502, 503]}
    application = FastAPI(title="SkillBridge Course–Career & JD Backend", version="1.0.0", lifespan=lifespan, responses=errors)
    application.state.backend = None
    application.state.database_error = None
    application.state.catalog = None
    from app.services.semester_map import SemesterMap
    application.state.semester_map = semester_map or SemesterMap()
    application.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    application.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                               allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
    register_handlers(application)
    for router in [courses.router, clo_sets.router, advisor_routes.router, careers.router, health.router]:
        application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
