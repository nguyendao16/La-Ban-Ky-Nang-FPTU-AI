"""Academic follow-up chat with local, transactional conversation sessions."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, ValidationError

if __package__:
    from .academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
    from .academic_review import (
        AcademicEvidence, AcademicProfile, EvidenceReference, ReviewError, ReviewSettings,
        StrictModel, load_jd, load_profile, load_settings, protect_input_paths,
        request_structured_response, unique_json_fields, validate_evidence_references,
        validate_profile, validate_review, validation_details,
    )
else:
    from academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
    from academic_review import (
        AcademicEvidence, AcademicProfile, EvidenceReference, ReviewError, ReviewSettings,
        StrictModel, load_jd, load_profile, load_settings, protect_input_paths,
        request_structured_response, unique_json_fields, validate_evidence_references,
        validate_profile, validate_review, validation_details,
    )


LOGGER = logging.getLogger("skillbridge.academic_chat")
DEFAULT_SESSION_DIR = Path("data/chat_sessions")


class ChatError(ReviewError):
    """A failed chat operation that must not produce a committed partial turn."""


class AcademicChatResponse(StrictModel):
    reply: str = Field(description="Natural Vietnamese answer with sufficient detail and formatting suited to the question and history. Explain unevidenced JD knowledge without judging actual ability; topics may be suggested conditionally if not already learned elsewhere, without courses, tutorials or roadmaps. Separate professional experience. Support every academic clause, including summaries, with exact CLO descriptions and learning verbs. Compare exact CLO scores and labels separately from curriculum scope, never as an overall SQL level. Correct unsupported historical claims.")
    evidence: list[AcademicEvidence] = Field(description="Exact CLO or metadata description/tools references supporting each academic statement. Metadata is curriculum context, not personal tool use or assessed performance. No duplicates, invented identifiers, score or achievement fields.")


class UserMessage(StrictModel):
    role: Literal["user"]
    content: str


class AssistantMessage(StrictModel):
    role: Literal["assistant"]
    content: str
    evidence: list[AcademicEvidence]


HistoryMessage = Annotated[UserMessage | AssistantMessage, Field(discriminator="role")]


class SourceDocument(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class StoredSession(StrictModel):
    version: Literal[1]
    session_id: str
    sources: dict[str, SourceDocument]
    messages: list[HistoryMessage]


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_json_fields)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ChatError(f"Không thể đọc {label} JSON UTF-8: {path}") from exc


def source_documents(paths: dict[str, Path]) -> dict[str, SourceDocument]:
    try:
        return {
            name: SourceDocument(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            for name, path in paths.items()
        }
    except OSError as exc:
        raise ChatError("Không thể kiểm tra các nguồn của phiên; kiểm tra profile/JD/review") from exc


def validate_session_id(session_id: str) -> str:
    try:
        if not isinstance(session_id, str) or UUID(session_id).hex != session_id:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ChatError("Session ID phải là UUID dạng 32 ký tự hex như ID được CLI tạo") from exc
    return session_id


def validate_chat_response(raw: Any, profile: AcademicProfile) -> AcademicChatResponse:
    try:
        if isinstance(raw, AcademicChatResponse):
            raw = raw.model_dump()
        response = AcademicChatResponse.model_validate(raw)
    except ValidationError as exc:
        raise ChatError(f"Chat response sai schema: {validation_details(exc)}") from exc
    validate_evidence_references(response.evidence, profile, label="Chat response")
    return response


def write_session(path: Path, record: StoredSession) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(record.model_dump(), file, ensure_ascii=False, allow_nan=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temporary_path.replace(path)
        temporary_path = None
    except OSError as exc:
        raise ChatError(f"Không thể lưu phiên: {path}; lượt mới chưa được commit") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class AcademicChatSession:
    """One immutable academic context and an isolated, bounded history.

    Use from_files() and close(), or a context manager. Injected clients remain
    caller-owned; the shared API helper closes clients it creates per request.
    """

    @classmethod
    def from_files(
        cls, profile_path: Path | str, jd_path: Path | str, review_path: Path | str,
        *, settings: ReviewSettings | None = None, client: Any | None = None,
        context_window: int | None = None, context_budget: int | None = None,
        max_turns: int = 20, max_message_chars: int = 4000,
        persist: bool = False, resume: str | None = None,
        session_dir: Path | str = DEFAULT_SESSION_DIR,
    ) -> AcademicChatSession:
        if persist and resume is not None:
            raise ChatError("Chọn tạo phiên --persist hoặc mở lại --resume")
        for label, value in [("max-turns", max_turns), ("max-message-chars", max_message_chars)]:
            if type(value) is not int or value <= 0:
                raise ChatError(f"--{label} phải là số nguyên dương")
        if resume is not None:
            validate_session_id(resume)
        paths = {"profile": Path(profile_path).resolve(), "jd": Path(jd_path).resolve(), "review": Path(review_path).resolve()}
        sources = source_documents(paths)
        profile = load_profile(paths["profile"])
        jd = load_jd(paths["jd"])
        review = validate_review(read_json(paths["review"], "initial review"), profile)
        if source_documents(paths) != sources:
            raise ChatError("Nguồn thay đổi trong khi khởi tạo; mở phiên mới với nguồn ổn định")
        settings = load_settings(context_window, stage="chat") if settings is None else settings
        budget = settings.context_window if context_budget is None else context_budget
        if type(budget) is not int or not settings.max_output_tokens < budget <= settings.context_window:
            raise ChatError("--context-budget phải lớn hơn output budget và không vượt context model")

        self = cls()
        self._session_id = resume if resume is not None else uuid4().hex
        self._sources = sources
        self._paths = paths
        self._profile = validate_profile(profile)
        self._settings = settings
        self._client = client
        self._context_budget = budget
        self._max_turns = max_turns
        self._max_message_chars = max_message_chars
        self._messages: list[UserMessage | AssistantMessage] = []
        self._context_messages = [
            {"role": "user", "content": json.dumps({"student_academic_profile": profile}, ensure_ascii=False, allow_nan=False, indent=2)},
            {"role": "user", "content": json.dumps({"current_job_description": jd}, ensure_ascii=False)},
            {"role": "user", "content": json.dumps({"initial_academic_review": review.model_dump()}, ensure_ascii=False)},
        ]
        self._overview = review.overview
        self._session_path: Path | None = None
        self._lock_file: Any | None = None
        self._send_lock = threading.RLock()
        self._closed = False
        try:
            if persist or resume is not None:
                directory = Path(session_dir).resolve()
                if resume is not None and not directory.is_dir():
                    raise ChatError("Không tìm thấy thư mục phiên để resume")
                directory.mkdir(parents=True, exist_ok=True)
                self._session_path = directory / f"{self.session_id}.json"
                lock_path = directory / f"{self.session_id}.lock"
                for candidate in [self._session_path, lock_path]:
                    if candidate.is_symlink():
                        raise ChatError("Không dùng symlink làm file phiên hoặc file khóa")
                    protect_input_paths(candidate, *paths.values())
                self._acquire_lock(lock_path)
                if resume is None:
                    if self._session_path.exists():
                        raise ChatError("Session ID đã tồn tại; không ghi đè phiên")
                    write_session(self._session_path, self._record([]))
                else:
                    self._load_history()
        except BaseException:
            self.close()
            raise
        return self

    def _acquire_lock(self, lock_path: Path) -> None:
        try:
            import fcntl
        except ImportError as exc:
            raise ChatError("Persistence V1 yêu cầu hệ điều hành POSIX hỗ trợ khóa file") from exc
        try:
            self._lock_file = lock_path.open("a", encoding="utf-8")
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ChatError("Phiên đang được tiến trình khác sử dụng; đóng phiên đó trước khi resume") from exc
        except OSError as exc:
            raise ChatError("Không thể khóa file phiên") from exc

    def _record(self, messages: list[UserMessage | AssistantMessage]) -> StoredSession:
        return StoredSession(version=1, session_id=self.session_id, sources=self._sources, messages=messages)

    def _load_history(self) -> None:
        try:
            stored = StoredSession.model_validate(read_json(self._session_path, "session"))
        except ValidationError as exc:
            raise ChatError(f"File phiên sai schema: {validation_details(exc)}") from exc
        if stored.session_id != self.session_id or stored.sources != self._sources:
            raise ChatError("Profile/JD/review hoặc Session ID không khớp phiên đã lưu; tạo phiên mới")
        if len(stored.messages) % 2 or len(stored.messages) // 2 > self._max_turns:
            raise ChatError("History dở dang hoặc vượt --max-turns; không tự cắt history")
        for offset, message in enumerate(stored.messages):
            if offset % 2 == 0:
                if not isinstance(message, UserMessage) or len(message.content) > self._max_message_chars:
                    raise ChatError("History user sai thứ tự hoặc vượt --max-message-chars")
            else:
                if not isinstance(message, AssistantMessage):
                    raise ChatError("History assistant sai thứ tự")
                validate_chat_response({"reply": message.content, "evidence": message.evidence}, self._profile)
        self._messages = stored.messages

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[dict[str, Any]]:
        return [message.model_dump() for message in self._messages]

    @property
    def turn_count(self) -> int:
        return len(self._messages) // 2

    @property
    def initial_overview(self) -> str:
        return self._overview

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def persistent(self) -> bool:
        return self._session_path is not None

    def send(self, message: str) -> AcademicChatResponse:
        with self._send_lock:
            if self._closed:
                raise ChatError("Phiên đã đóng")
            if not isinstance(message, str) or not message.strip():
                raise ChatError("Câu hỏi không được rỗng")
            if len(message) > self._max_message_chars:
                raise ChatError(f"Câu hỏi vượt {self._max_message_chars} ký tự; không tự cắt nội dung")
            if self.turn_count >= self._max_turns:
                raise ChatError(f"Phiên đã đạt {self._max_turns} lượt; tạo phiên mới")
            if source_documents(self._paths) != self._sources:
                raise ChatError("Nguồn profile/JD/review đã thay đổi; tạo phiên mới")
            messages = copy.deepcopy(self._context_messages)
            for previous in self._messages:
                content = previous.content if isinstance(previous, UserMessage) else json.dumps(
                    {"reply": previous.content, "evidence": [ref.model_dump() for ref in previous.evidence]}, ensure_ascii=False
                )
                messages.append({"role": previous.role, "content": content})
            messages.append({"role": "user", "content": message})
            LOGGER.debug("session=%s turn=%d model=%s", self.session_id, self.turn_count + 1, self.model)
            try:
                raw = request_structured_response(
                    ACADEMIC_CHAT_INSTRUCTIONS, messages, AcademicChatResponse,
                    self._settings, client=self._client, context_budget=self._context_budget,
                    operation_label="câu trả lời",
                )
                response = validate_chat_response(raw, self._profile)
                if source_documents(self._paths) != self._sources:
                    raise ChatError("Nguồn thay đổi trong khi trả lời; lượt chưa được commit, tạo phiên mới")
                prospective = self._messages + [
                    UserMessage(role="user", content=message),
                    AssistantMessage(role="assistant", content=response.reply,
                                     evidence=[ref.model_copy(deep=True) for ref in response.evidence]),
                ]
                if self._session_path is not None:
                    write_session(self._session_path, self._record(prospective))
                self._messages = prospective
                return response
            except KeyboardInterrupt:
                # A signal can interrupt the narrow disk/memory commit boundary.
                # Closing forces any continuation to reload the complete disk state.
                self.close()
                raise

    def close(self) -> None:
        with self._send_lock:
            self._closed = True
            if self._lock_file is not None:
                self._lock_file.close()
                self._lock_file = None

    def __enter__(self) -> AcademicChatSession:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
