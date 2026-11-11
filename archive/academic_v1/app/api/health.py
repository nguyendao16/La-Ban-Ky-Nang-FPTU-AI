import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.schemas.responses import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def health(request: Request):
    backend = request.app.state.backend
    if backend is None:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})
    try:
        with backend.database.transaction() as connection:
            connection.execute("SELECT 1").fetchone()
            queued = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            unfinished = connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]
            now = backend.database.clock()
            live_worker = bool(connection.execute("SELECT COUNT(*) FROM workers WHERE state='running' AND last_seen_epoch>?",
                                                   (now - backend.settings.lease_seconds,)).fetchone()[0])
            live_job = bool(connection.execute("SELECT COUNT(*) FROM jobs WHERE status='processing' AND lease_expires_at>?", (now,)).fetchone()[0])
        configured = request.app.state.catalog is not None
        ready = configured and (unfinished == 0 or live_worker or live_job)
        return JSONResponse(status_code=200 if ready else 503, content={
            "status": "ready" if ready else "degraded", "database": "ok",
            "curriculum": "configured" if configured else "unconfigured",
            "review_worker": "available" if live_worker or live_job else "not_seen",
            "queued_review_jobs": queued,
        })
    except sqlite3.Error:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})
