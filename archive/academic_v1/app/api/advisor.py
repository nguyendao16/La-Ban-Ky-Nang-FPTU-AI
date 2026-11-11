from fastapi import APIRouter, Response

from app.schemas.requests import MessageRequest, SessionRequest
from app.schemas.responses import CreatedSessionResponse, HistoryResponse, MessageResponse, SessionResponse

from .dependencies import Backend, Capability, IdempotencyKey

router = APIRouter(prefix="/advisor/sessions", tags=["Advisor"])


@router.post("", status_code=202, response_model=CreatedSessionResponse)
def create_session(body: SessionRequest, backend: Backend, capability: Capability,
                   idempotency_key: IdempotencyKey, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return backend.persistent.create_session(body.profile_id, capability, body.job_description, idempotency_key)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, backend: Backend, capability: Capability, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return backend.persistent.get_session(session_id, capability)


@router.post("/{session_id}/messages", response_model=MessageResponse)
def send_message(session_id: str, body: MessageRequest, backend: Backend, capability: Capability,
                 idempotency_key: IdempotencyKey, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return backend.persistent.send_message(session_id, capability, body.message, idempotency_key)


@router.get("/{session_id}/messages", response_model=HistoryResponse)
def history(session_id: str, backend: Backend, capability: Capability, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return backend.persistent.get_history(session_id, capability)
