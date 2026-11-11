"""Coordinate comparison and Chat engines over isolated snapshots."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable

from app.engines.chat import CLOChatSession
from app.engines.comparison import generate_comparison
from app.engines.career import generate_career_comparison
from app.engines.recommendations import generate_recommendations, recommendation_context, validate_recommendations
from app.llm import ComparisonError, LLMSettings, load_settings, openai
from .result_cache import ResultCache


class AdvisorService:
    """Independent comparison and Chat engines around validated JD and career snapshots."""

    def __init__(
        self, *, review_engine: Callable = generate_comparison,
        career_engine: Callable = generate_career_comparison,
        recommendation_engine: Callable = generate_recommendations, recommendation_client: Any | None = None,
        chat_session_factory: type[CLOChatSession] = CLOChatSession,
        review_settings: LLMSettings | None = None, chat_settings: LLMSettings | None = None,
        review_client: Any | None = None, chat_client: Any | None = None,
        context_budget: int | None = None,
        max_turns: int = 20, max_message_chars: int = 4000,
        result_cache_dir=None,
    ):
        for stage, settings in [("review", review_settings), ("chat", chat_settings)]:
            if settings is not None and settings.stage != stage:
                raise ComparisonError(f"Injected {stage} settings must use stage={stage}")
        self._review_engine = review_engine
        self._career_engine = career_engine
        self._recommendation_engine, self._recommendation_client = recommendation_engine, recommendation_client
        self._chat_factory = chat_session_factory
        self._review_settings = review_settings
        self._chat_options = dict(settings=chat_settings, client=chat_client,
                                  context_budget=context_budget, max_turns=max_turns,
                                  max_message_chars=max_message_chars)
        self._review_client = review_client
        self._result_cache = ResultCache(result_cache_dir) if result_cache_dir is not None else None

    def _snapshot_options(self):
        return dict(self._chat_options)

    def create_snapshot(self, clo_set, job_description) -> dict[str, Any]:
        with self._chat_factory.from_data(clo_set, job_description, **self._snapshot_options()) as session:
            return session.export_snapshot()

    def create_career_snapshot(self, clo_set, profile) -> dict[str, Any]:
        with self._chat_factory.from_career(clo_set, profile, **self._snapshot_options()) as session:
            return session.export_snapshot()

    def validate_snapshot(self, snapshot) -> dict[str, Any]:
        with self._chat_factory.from_snapshot(snapshot, **self._snapshot_options()) as session:
            return session.export_snapshot()

    def prepare_review_settings(self, **overrides) -> LLMSettings:
        if self._review_settings is not None:
            if overrides:
                from dataclasses import replace
                return replace(self._review_settings, **overrides)
            return self._review_settings
        return load_settings(stage="review", **overrides)

    def prepare_chat_settings(self) -> LLMSettings:
        return self._chat_options["settings"] if self._chat_options["settings"] is not None else load_settings(stage="chat")

    @contextmanager
    def _snapshot_client(self, settings, injected, *, use_default):
        # Durable operations cannot safely retry an ambiguous remote dispatch.
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
            engine = self._career_engine if 'career_profile' in snapshot else self._review_engine
            key = self._result_cache.key('comparison', snapshot, settings) if self._result_cache else None
            cached = self._result_cache.get(key) if key else None
            if cached is not None:
                engine = lambda source, target, options, *, client=None: cached
            with self._snapshot_client(settings, self._review_client,
                    use_default=engine in (generate_comparison, generate_career_comparison)) as client:
                response = session.run_initial_comparison(engine, settings, client=client)
            if key and cached is None:
                self._result_cache.put(key, response.model_dump())
            return session.export_snapshot(), response

    def recommend_snapshot(self, snapshot, *, settings=None):
        snapshot = self.validate_snapshot(snapshot)
        context = recommendation_context(snapshot)
        settings = self.prepare_review_settings() if settings is None else settings
        key = self._result_cache.key('recommendations', snapshot, settings) if self._result_cache else None
        cached = self._result_cache.get(key) if key else None
        if cached is not None:
            return validate_recommendations(cached, context, source=snapshot['clo_set'])
        with self._snapshot_client(settings, self._recommendation_client,
                use_default=self._recommendation_engine is generate_recommendations) as client:
            raw = self._recommendation_engine(context, settings, client=client)
        result = validate_recommendations(raw, context, source=snapshot['clo_set'])
        if key:
            self._result_cache.put(key, result.model_dump())
        return result

    def chat_snapshot(self, snapshot, message, *, settings=None, recommendations=None):
        options = self._snapshot_options()
        settings = self.prepare_chat_settings() if settings is None else settings
        options["settings"] = settings
        with self._snapshot_client(settings, options["client"], use_default=self._chat_factory is CLOChatSession) as client:
            options["client"] = client
            with self._chat_factory.from_snapshot(snapshot, **options) as session:
                response = session.send(message, recommendations=recommendations) if recommendations is not None else session.send(message)
                return session.export_snapshot(), response

    def close(self):
        # Snapshot clients are per-operation; injected clients remain caller-owned.
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
