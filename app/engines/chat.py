"""Version-3 JD and version-4 career object sessions; SQLite owns persistence and operation fencing."""

import copy
import hashlib
import threading
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from app.json_utils import digest, json_text
from app.llm import load_settings, request_structured_response
from .errors import ChatError, ComparisonAlreadyReadyError, ComparisonNotReadyError
from .models import (
    CLOJDComparison, CLOSet, ChatResponse, EvidenceReference, StrictModel, parse_model,
    validate_chat_response, validate_clo_set, validate_comparison, validate_jd,
)
from .prompts import CHAT_INSTRUCTIONS
from .career import CareerProfile, CareerComparison, comparison_findings, validate_career_comparison

CAREER_CHAT_INSTRUCTIONS = CHAT_INSTRUCTIONS.replace('explain its five dynamic\naxes', 'explain its five supplied\naxes') + """
If the stored CWA profile contains target, its title/scope select the career
and its five axis definitions are fixed application groupings, not official
CWA axes. Explain only the saved comparison within those scopes, including
its overall score; do not add requirements from another specialty. Legacy
results keep their saved axis names, scopes and scores without reinterpretation.
"""


class UserMessage(StrictModel):
    role: Literal["user"]
    content: str


class AssistantMessage(StrictModel):
    role: Literal["assistant"]
    content: str
    evidence: list[EvidenceReference]


class StoredCLOSession(StrictModel):
    version: Literal[3]
    session_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    clo_set: CLOSet
    job_description: str
    comparison: CLOJDComparison | None
    fingerprints: dict[str, str]
    messages: list[Annotated[UserMessage | AssistantMessage, Field(discriminator="role")]]


class StoredCareerSession(StrictModel):
    version: Literal[4]
    session_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    clo_set: CLOSet
    career_profile: CareerProfile
    comparison: CareerComparison | None
    fingerprints: dict[str, str]
    messages: list[Annotated[UserMessage | AssistantMessage, Field(discriminator="role")]]


def career_fingerprints(source, profile, comparison):
    result = {"clo_set": digest(validate_clo_set(source).model_dump()),
              "career_profile": digest(parse_model(CareerProfile, profile).model_dump())}
    if comparison is not None:
        result["comparison"] = digest(validate_career_comparison(comparison, source, profile=profile).model_dump())
    return result


def snapshot_fingerprints(clo_set, jd, comparison):
    result = {"clo_set": digest(validate_clo_set(clo_set).model_dump()),
              "jd": hashlib.sha256(jd.encode("utf-8")).hexdigest()}
    if comparison is not None:
        result["comparison"] = digest(validate_comparison(comparison, clo_set).model_dump())
    return result


def validate_approved_evidence(response, comparison):
    allowed = {(e['course_code'], e['clo']) for row in comparison_findings(comparison) for e in row['evidence']}
    if any((e.course_code, e.clo) not in allowed for e in response.evidence):
        raise ChatError('Chat evidence must belong to the approved comparison')


class CLOChatSession:
    def __init__(self, snapshot, *, settings=None, client=None, context_budget=None,
                 max_turns=20, max_message_chars=4000):
        for value in [max_turns, max_message_chars]:
            if type(value) is not int or value <= 0:
                raise ChatError("Session limits must be positive integers")
        if context_budget is not None and (type(context_budget) is not int or context_budget <= 0):
            raise ChatError("Context budget must be a positive integer")
        if settings is not None and settings.stage != "chat":
            raise ChatError("Chat settings must use stage=chat")
        if settings is not None and context_budget is not None and not settings.max_output_tokens < context_budget <= settings.context_window:
            raise ChatError("Context budget must fit the model and output ceiling")
        self._settings, self._client, self._context_budget = settings, client, context_budget
        self._max_turns, self._max_message_chars = max_turns, max_message_chars
        self._send_lock = threading.RLock()
        self._closed = False
        career = isinstance(snapshot, dict) and snapshot.get('version') == 4
        stored = parse_model(StoredCareerSession if career else StoredCLOSession, snapshot)
        if not career:
            validate_jd(stored.job_description)
        self._snapshot = stored.model_dump()
        expected = (career_fingerprints(self._snapshot['clo_set'], self._snapshot['career_profile'], stored.comparison)
                    if career else snapshot_fingerprints(self._snapshot["clo_set"], stored.job_description, stored.comparison))
        if stored.fingerprints != expected:
            raise ChatError("Snapshot fingerprints do not match the sources")
        if len(stored.messages) % 2 or len(stored.messages) // 2 > max_turns:
            raise ChatError("History must contain bounded complete turns")
        if stored.comparison is None and stored.messages:
            raise ChatError("Pending comparison cannot contain history")
        for offset, message in enumerate(stored.messages):
            if offset % 2 == 0:
                if not isinstance(message, UserMessage) or len(message.content) > max_message_chars:
                    raise ChatError("Invalid user message order or length")
            elif not isinstance(message, AssistantMessage):
                raise ChatError("Invalid assistant message order")
            else:
                response = validate_chat_response({"reply": message.content, "evidence": [e.model_dump() for e in message.evidence]}, stored.clo_set, check_policy=False)
                validate_approved_evidence(response, self._snapshot['comparison'])

    @classmethod
    def from_data(cls, clo_set, jd, comparison=None, **options):
        source = validate_clo_set(clo_set).model_dump()
        jd = validate_jd(jd)
        compared = None if comparison is None else validate_comparison(comparison, source).model_dump()
        return cls({"version": 3, "session_id": uuid4().hex, "clo_set": source,
            "job_description": jd, "comparison": compared,
            "fingerprints": snapshot_fingerprints(source, jd, compared), "messages": []}, **options)

    @classmethod
    def from_career(cls, clo_set, profile, **options):
        source = validate_clo_set(clo_set).model_dump()
        profile = parse_model(CareerProfile, profile).model_dump()
        return cls({'version': 4, 'session_id': uuid4().hex, 'clo_set': source,
                    'career_profile': profile, 'comparison': None,
                    'fingerprints': career_fingerprints(source, profile, None), 'messages': []}, **options)

    @classmethod
    def from_snapshot(cls, snapshot, **options):
        return cls(snapshot, **options)

    def export_snapshot(self):
        with self._send_lock:
            return copy.deepcopy(self._snapshot)

    def run_initial_comparison(self, engine, settings, *, client=None):
        with self._send_lock:
            if self._closed:
                raise ChatError("Session is closed")
            if self._snapshot["comparison"] is not None:
                raise ComparisonAlreadyReadyError("Comparison already exists; create a new session")
            if settings.stage != "review":
                raise ChatError("Comparison settings must use stage=review")
            career = 'career_profile' in self._snapshot
            target = copy.deepcopy(self._snapshot['career_profile']) if career else self._snapshot['job_description']
            raw = engine(copy.deepcopy(self._snapshot["clo_set"]), target, settings, client=client)
            response = (validate_career_comparison(raw, self._snapshot["clo_set"], require_radar=True, profile=target)
                        if career else validate_comparison(raw, self._snapshot["clo_set"], require_radar=True))
            updated = {**self._snapshot, "comparison": response.model_dump()}
            updated["fingerprints"] = (career_fingerprints(updated['clo_set'], updated['career_profile'], response)
                                       if career else snapshot_fingerprints(updated["clo_set"], updated["job_description"], response))
            self._snapshot = updated
            return response.model_copy(deep=True)

    def send(self, message, *, recommendations=None):
        with self._send_lock:
            if self._closed:
                raise ChatError("Session is closed")
            if self._snapshot["comparison"] is None:
                raise ComparisonNotReadyError("Comparison must be ready before Chat")
            if not isinstance(message, str) or not message.strip() or len(message) > self._max_message_chars:
                raise ChatError("Message is empty or exceeds the configured limit")
            if len(self._snapshot["messages"]) // 2 >= self._max_turns:
                raise ChatError("Session reached its turn limit; create a new session")
            settings = self._settings or load_settings(stage="chat")
            from app.public_view import comparison as public_comparison, protect_text
            approved = public_comparison(self._snapshot["comparison"], self._snapshot["clo_set"])
            permitted = [e for row in comparison_findings(self._snapshot["comparison"]) for e in row["evidence"]]
            target = ({'career_profile': self._snapshot['career_profile']} if 'career_profile' in self._snapshot
                      else {'job_description': self._snapshot['job_description']})
            messages = [{"role": "user", "content": json_text(target)},
                        {"role": "user", "content": json_text({"initial_comparison": approved, "permitted_evidence": permitted})}]
            if recommendations is not None:
                messages.append({'role': 'user', 'content': json_text({'saved_recommendations': recommendations})})

            for previous in self._snapshot["messages"]:
                content = previous["content"] if previous["role"] == "user" else json_text({"reply": protect_text(previous["content"], self._snapshot["clo_set"]), "evidence": previous["evidence"]})
                messages.append({"role": previous["role"], "content": content})
            messages.append({"role": "user", "content": message})
            instructions = CAREER_CHAT_INSTRUCTIONS if 'career_profile' in self._snapshot else CHAT_INSTRUCTIONS
            if recommendations is not None:
                from .recommendations import RECOMMENDATION_CHAT_RULES
                instructions += RECOMMENDATION_CHAT_RULES
            raw = request_structured_response(instructions, messages, ChatResponse, settings,
                client=self._client, context_budget=self._context_budget, operation_label="Chat")
            response = validate_chat_response(raw, self._snapshot["clo_set"])
            validate_approved_evidence(response, self._snapshot["comparison"])
            from .recommendations import validate_chat_course_links
            validate_chat_course_links(response.reply, recommendations)
            prospective = self._snapshot["messages"] + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response.reply, "evidence": [e.model_dump() for e in response.evidence]}]
            self._snapshot = {**self._snapshot, "messages": prospective}
            return response.model_copy(deep=True)

    def close(self):
        with self._send_lock:
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
