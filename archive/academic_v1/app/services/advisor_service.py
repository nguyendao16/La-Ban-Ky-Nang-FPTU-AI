"""Coordinate existing Review and Chat engines around one session owner."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from scripts.academic_chat import (
    AcademicChatResponse, AcademicChatSession, DEFAULT_SESSION_DIR,
    ReviewAlreadyReadyError, validate_session_id,
)
from scripts.academic_review import (
    AcademicKnowledgeReview, AcademicProfile, ReviewError, ReviewSettings, generate_review, load_settings, openai,
)

from .errors import SessionNotFoundError


class AdvisorSessionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    status: Literal["pending_review", "ready"]
    fingerprints: dict[str, str]
    initial_review: AcademicKnowledgeReview | None
    turn_count: int
    persistent: bool


class AdvisorService:
    """Synchronous operations suitable for later execution by a worker.

    Persistent sessions retain the engine's single-owner POSIX lock until close.
    No LLM/settings loading occurs during session creation or snapshot resume.
    """

    def __init__(
        self, *, review_engine: Callable = generate_review,
        chat_session_factory: type[AcademicChatSession] = AcademicChatSession,
        review_settings: ReviewSettings | None = None, chat_settings: ReviewSettings | None = None,
        review_client: Any | None = None, chat_client: Any | None = None,
        session_dir: Path | str = DEFAULT_SESSION_DIR, context_budget: int | None = None,
        max_turns: int = 20, max_message_chars: int = 4000,
    ):
        for stage, settings in [("review", review_settings), ("chat", chat_settings)]:
            if settings is not None and settings.stage != stage:
                raise ReviewError(f"Injected {stage} settings must use stage={stage}")
        self._review_engine = review_engine
        self._chat_factory = chat_session_factory
        self._review_settings = review_settings
        self._chat_options = dict(settings=chat_settings, client=chat_client, session_dir=session_dir,
                                  context_budget=context_budget, max_turns=max_turns,
                                  max_message_chars=max_message_chars)
        self._review_client = review_client
        self._sessions: dict[str, AcademicChatSession] = {}
        self._registry_lock = threading.RLock()

    def _get(self, session_id: str) -> AcademicChatSession:
        with self._registry_lock:
            if not isinstance(session_id, str) or session_id not in self._sessions:
                raise SessionNotFoundError(f"No active session: {session_id!r}")
            return self._sessions[session_id]

    def create_session(
        self, profile: dict[str, Any] | AcademicProfile, job_description: str, *, persist: bool = False,
    ) -> AdvisorSessionView:
        session = self._chat_factory.from_data(profile, job_description, persist=persist, **self._chat_options)
        with self._registry_lock:
            if session.session_id in self._sessions:
                session.close()
                raise ReviewError("Session ID already registered")
            self._sessions[session.session_id] = session
        return AdvisorSessionView(**session.describe())

    def run_initial_review(self, session_id: str) -> AcademicKnowledgeReview:
        session = self._get(session_id)
        if session.initial_review is not None:
            raise ReviewAlreadyReadyError("Session already has an Initial Review; create a new session")
        settings = self._review_settings
        if settings is None:
            settings = load_settings(stage="review")
        return session.run_initial_review(self._review_engine, settings, client=self._review_client)

    def get_session(self, session_id: str) -> AdvisorSessionView:
        return AdvisorSessionView(**self._get(session_id).describe())

    def send_message(self, session_id: str, message: str) -> AcademicChatResponse:
        return self._get(session_id).send(message)

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        return self._get(session_id).history

    def resume_session(self, session_id: str) -> AdvisorSessionView:
        validate_session_id(session_id)
        with self._registry_lock:
            if session_id in self._sessions:
                raise ReviewError("Session already registered; use get_session")
            session = self._chat_factory.resume_data(session_id, **self._chat_options)
            self._sessions[session_id] = session
        return AdvisorSessionView(**session.describe())

    def close_session(self, session_id: str) -> None:
        session = self._get(session_id)
        session.close()
        with self._registry_lock:
            self._sessions.pop(session_id, None)

    def _snapshot_options(self):
        return {k: v for k, v in self._chat_options.items() if k != "session_dir"}

    def create_snapshot(self, profile, job_description) -> dict[str, Any]:
        with self._chat_factory.from_data(profile, job_description, **self._snapshot_options()) as session:
            return session.export_snapshot()

    def validate_snapshot(self, snapshot) -> dict[str, Any]:
        with self._chat_factory.from_snapshot(snapshot, **self._snapshot_options()) as session:
            return session.export_snapshot()

    def prepare_review_settings(self, **overrides) -> ReviewSettings:
        if self._review_settings is not None:
            if overrides:
                from dataclasses import replace
                return replace(self._review_settings, **overrides)
            return self._review_settings
        return load_settings(stage="review", **overrides)

    def prepare_chat_settings(self) -> ReviewSettings:
        return self._chat_options["settings"] if self._chat_options["settings"] is not None else load_settings(stage="chat")

    @contextmanager
    def _snapshot_client(self, settings, injected, *, use_default):
        # Durable operations cannot safely retry an ambiguous remote dispatch.
        # Legacy registry/file interfaces retain their existing SDK policy.
        owned = injected is None and use_default
        client = openai.OpenAI(api_key=settings.api_key, timeout=settings.timeout, max_retries=0) if owned else injected
        try:
            yield client
        finally:
            if owned:
                client.close()

    def review_snapshot(self, snapshot, *, settings=None):
        with self._chat_factory.from_snapshot(snapshot, **self._snapshot_options()) as session:
            settings = self.prepare_review_settings() if settings is None else settings
            with self._snapshot_client(settings, self._review_client, use_default=self._review_engine is generate_review) as client:
                response = session.run_initial_review(self._review_engine, settings, client=client)
            return session.export_snapshot(), response

    def chat_snapshot(self, snapshot, message, *, settings=None):
        options = self._snapshot_options()
        settings = self.prepare_chat_settings() if settings is None else settings
        options["settings"] = settings
        with self._snapshot_client(settings, options["client"], use_default=self._chat_factory is AcademicChatSession) as client:
            options["client"] = client
            with self._chat_factory.from_snapshot(snapshot, **options) as session:
                response = session.send(message)
                return session.export_snapshot(), response

    def close(self) -> None:
        with self._registry_lock:
            identifiers = list(self._sessions)
        for identifier in identifiers:
            self.close_session(identifier)

    def __enter__(self) -> AdvisorService:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
