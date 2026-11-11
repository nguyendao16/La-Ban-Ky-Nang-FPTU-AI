from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import AdvisorService, ReviewAlreadyReadyError, ReviewNotReadyError, SessionNotFoundError
from scripts import academic_chat as chat
from scripts import academic_review as review
from scripts.academic_chat_prompt import ACADEMIC_CHAT_INSTRUCTIONS
from scripts.academic_review_prompt import ACADEMIC_REVIEW_INSTRUCTIONS

pytestmark = pytest.mark.usefixtures("service_offline")


@pytest.fixture
def advisor(tmp_path, sdk_client, service_review, service_reply):
    review_client = sdk_client(service_review)
    chat_client = sdk_client(service_reply)
    with AdvisorService(
        review_settings=review.ReviewSettings(api_key="offline-review", stage="review", model="gpt-5.4",
                                              max_output_tokens=32768, request_timeout=360),
        chat_settings=review.ReviewSettings(api_key="offline-chat", stage="chat", model="gpt-5.4-mini",
                                            max_output_tokens=8192, request_timeout=180),
        review_client=review_client, chat_client=chat_client, session_dir=tmp_path / "sessions",
    ) as service:
        yield service, review_client, chat_client


def test_create_and_resume_pending_need_no_settings_key_or_generation(service_profile, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Creation/resume may not create an OpenAI client or load configuration")
    monkeypatch.setattr(review.openai, "OpenAI", forbidden)
    monkeypatch.setattr(review, "load_dotenv", forbidden)
    directory = tmp_path / "sessions"
    with AdvisorService(session_dir=directory) as service:
        memory = service.create_session(service_profile, "  SQL internship\n")
        assert not directory.exists() and memory.status == "pending_review"
        first = service.create_session(service_profile, "  SQL internship\n", persist=True)
        assert first.fingerprints == memory.fingerprints and first.initial_review is None
        path = directory / f"{first.session_id}.json"
        saved = json.loads(path.read_text())
        assert saved["version"] == 2 and saved["profile"] == service_profile
        assert saved["job_description"] == "  SQL internship\n" and saved["review"] is None
        service.close_session(first.session_id)
        resumed = service.resume_session(first.session_id)
        assert resumed == first and service.get_history(first.session_id) == []


def test_initial_review_once_and_ordered_chat_contract(advisor, service_profile):
    service, review_client, chat_client = advisor
    session = service.create_session(service_profile, "SQL internship")
    with pytest.raises(ReviewNotReadyError):
        service.send_message(session.session_id, "Question")
    review_client.responses.parse.assert_not_called()
    chat_client.responses.parse.assert_not_called()
    result = service.run_initial_review(session.session_id)
    assert service.get_session(session.session_id).status == "ready"
    assert service.get_session(session.session_id).initial_review == result
    with pytest.raises(ReviewAlreadyReadyError):
        service.run_initial_review(session.session_id)
    for message in ["Tôi đã học gì?", "CLO đó bao nhiêu điểm?"]:
        assert service.send_message(session.session_id, message).reply
    assert review_client.responses.parse.call_count == review_client.responses.input_tokens.count.call_count == 1
    assert chat_client.responses.parse.call_count == chat_client.responses.input_tokens.count.call_count == 2
    history = service.get_history(session.session_id)
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert service.get_session(session.session_id).turn_count == 2
    initial_request = review_client.responses.parse.call_args.kwargs
    chat_request = chat_client.responses.parse.call_args.kwargs
    assert initial_request["instructions"] == ACADEMIC_REVIEW_INSTRUCTIONS
    assert chat_request["instructions"] == ACADEMIC_CHAT_INSTRUCTIONS
    for request, model, effort, tokens, timeout in [
        (initial_request, "gpt-5.4", "high", 32768, 360),
        (chat_request, "gpt-5.4-mini", "medium", 8192, 180),
    ]:
        assert request["model"] == model and request["reasoning"] == {"effort": effort}
        assert request["max_output_tokens"] == tokens and request["timeout"] == timeout
        assert request["store"] is False and request["truncation"] == "disabled"
        assert "temperature" not in request and "tools" not in request
    assert json.loads(chat_request["input"][0]["content"])["student_academic_profile"] == service_profile
    assert json.loads(chat_request["input"][2]["content"])["initial_academic_review"] == result.model_dump()
    assert chat_request["input"][-3]["content"] == history[0]["content"]


def test_sessions_preserve_pairing_and_detached_views(advisor, service_profile):
    service, review_client, chat_client = advisor
    original = copy.deepcopy(service_profile)
    a = service.create_session(service_profile, "JD A")
    service_profile["courses"][0]["clos"][0]["score"] = 3
    b = service.create_session(service_profile, "JD B")
    assert a.session_id != b.session_id and a.fingerprints["profile"] != b.fingerprints["profile"]
    service.run_initial_review(a.session_id)
    assert json.loads(review_client.responses.parse.call_args.kwargs["input"][0]["content"])["student_academic_profile"] == original
    service.send_message(a.session_id, "Session A question")
    assert service.get_history(b.session_id) == []
    service.run_initial_review(b.session_id)
    service.send_message(b.session_id, "Session B question")
    payload = json.dumps(chat_client.responses.parse.call_args.kwargs["input"])
    assert "JD B" in payload and "JD A" not in payload and "Session A question" not in payload
    view = service.get_session(a.session_id)
    view.fingerprints.clear()
    view.initial_review.overview = "Caller changed review"
    history = service.get_history(a.session_id)
    history[1]["evidence"].clear()
    assert service.get_session(a.session_id).fingerprints
    assert service.get_session(a.session_id).initial_review.overview != "Caller changed review"
    assert service.get_history(a.session_id)[1]["evidence"]


@pytest.mark.parametrize("operation", ["get_session", "get_history", "send_message", "run_initial_review", "close_session"])
def test_unknown_session_ids(advisor, operation):
    service, _, _ = advisor
    with pytest.raises(SessionNotFoundError):
        getattr(service, operation)("unknown", *(["hello"] if operation == "send_message" else []))


@pytest.mark.parametrize("stage", ["review", "chat"])
@pytest.mark.parametrize("failure", ["incomplete", "schema", "clo", "metadata", "exception", "refusal", "unparsed"])
def test_failed_generations_do_not_commit(advisor, service_profile, stage, failure):
    service, review_client, chat_client = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    path = service._chat_options["session_dir"] / f"{session.session_id}.json"
    if stage == "chat":
        service.run_initial_review(session.session_id)
        service.send_message(session.session_id, "Successful question")
    client = review_client if stage == "review" else chat_client
    raw = copy.deepcopy(client.responses.parse.return_value.output_parsed)
    if failure == "incomplete":
        client.responses.parse.return_value.status = "incomplete"
    elif failure == "schema":
        raw.pop("overview" if stage == "review" else "reply")
    elif failure in {"clo", "metadata"}:
        invalid = {"course_code": "TEST101", "clo": "CLO999"} if failure == "clo" else {"course_code": "TEST101", "metadata_field": "tools"}
        if stage == "review":
            raw["requirement_reviews"][0]["evidence"] = [invalid]
        else:
            raw["evidence"] = [invalid]
    elif failure == "exception":
        client.responses.parse.side_effect = review.openai.APIConnectionError(request=__import__("httpx").Request("POST", "https://example.test"))
    elif failure == "refusal":
        client.responses.parse.return_value.output = [SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal")])]
    elif failure == "unparsed":
        raw = None
    client.responses.parse.return_value.output_parsed = raw
    before = path.read_bytes()
    history = service.get_history(session.session_id)
    count = client.responses.parse.call_count
    with pytest.raises(review.ReviewError):
        if stage == "review":
            service.run_initial_review(session.session_id)
        else:
            service.send_message(session.session_id, "Failed question")
    assert client.responses.parse.call_count == count + 1
    assert path.read_bytes() == before and service.get_history(session.session_id) == history
    assert service.get_session(session.session_id).status == ("pending_review" if stage == "review" else "ready")


def test_metadata_only_evidence(advisor, service_profile, service_review):
    service, review_client, chat_client = advisor
    reference = {"course_code": "TEST101", "metadata_field": "description"}
    raw = copy.deepcopy(service_review)
    raw["requirement_reviews"][0]["evidence"] = [reference]
    review_client.responses.parse.return_value.output_parsed = raw
    chat_client.responses.parse.return_value.output_parsed = {"reply": "Course description đề cập SQL.", "evidence": [reference]}
    session = service.create_session(service_profile, "SQL")
    service.run_initial_review(session.session_id)
    assert service.send_message(session.session_id, "Metadata nói gì?").model_dump()["evidence"] == [reference]


@pytest.mark.parametrize("stage", ["review", "chat"])
def test_atomic_save_failure_rolls_back_and_explicit_retry_is_possible(advisor, service_profile, stage, monkeypatch):
    service, _, _ = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    if stage == "chat":
        service.run_initial_review(session.session_id)
    path = service._chat_options["session_dir"] / f"{session.session_id}.json"
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError("Atomic replace failed")
    with monkeypatch.context() as patch:
        patch.setattr(type(path), "replace", fail)
        with pytest.raises(chat.ChatError):
            if stage == "review":
                service.run_initial_review(session.session_id)
            else:
                service.send_message(session.session_id, "Question")
    assert path.read_bytes() == before and service.get_history(session.session_id) == []
    assert not list(path.parent.glob("*.tmp"))
    if stage == "review":
        service.run_initial_review(session.session_id)
    else:
        service.send_message(session.session_id, "Question")


def test_ready_snapshot_resume_and_locking(advisor, service_profile):
    service, review_client, chat_client = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    service.run_initial_review(session.session_id)
    service.send_message(session.session_id, "First")
    directory = service._chat_options["session_dir"]
    before = service.get_history(session.session_id)
    with AdvisorService(chat_settings=service._chat_options["settings"], chat_client=chat_client, session_dir=directory) as other:
        with pytest.raises(chat.ChatError, match="tiến trình khác"):
            other.resume_session(session.session_id)
        service.close_session(session.session_id)
        restored = other.resume_session(session.session_id)
        assert restored.status == "ready" and other.get_history(session.session_id) == before
        other.send_message(session.session_id, "Second")
        assert other.get_session(session.session_id).turn_count == 2
        assert review_client.responses.parse.call_count == 1
        assert "offline-review" not in (directory / f"{session.session_id}.json").read_text()
    review_client.close.assert_not_called()
    chat_client.close.assert_not_called()


@pytest.mark.parametrize("change", ["profile", "jd", "review", "fingerprint", "version", "id", "dangling", "role", "evidence", "pending_history", "extra", "duplicate_json", "malformed"])
def test_snapshot_tampering_is_rejected(advisor, service_profile, change):
    service, _, _ = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    service.run_initial_review(session.session_id)
    service.send_message(session.session_id, "First")
    path = service._chat_options["session_dir"] / f"{session.session_id}.json"
    service.close_session(session.session_id)
    raw = json.loads(path.read_text())
    if change == "profile": raw["profile"]["courses"][0]["clos"][0]["score"] = 3
    elif change == "jd": raw["job_description"] += "\n"
    elif change == "review": raw["review"]["overview"] = "Changed"
    elif change == "fingerprint": raw["fingerprints"]["profile"] = "0" * 64
    elif change == "version": raw["version"] = 1
    elif change == "id": raw["session_id"] = "wrong"
    elif change == "dangling": raw["messages"].pop()
    elif change == "role": raw["messages"][0]["role"] = "assistant"
    elif change == "evidence": raw["messages"][1]["evidence"][0]["clo"] = "CLO999"
    elif change == "pending_history":
        raw["review"] = None
        raw["fingerprints"].pop("review")
    elif change == "extra": raw["api_key"] = "not allowed"
    path.write_text("{" if change == "malformed" else ('{"version":2,"version":2}' if change == "duplicate_json" else json.dumps(raw)))
    with pytest.raises(review.ReviewError):
        service.resume_session(session.session_id)


@pytest.mark.parametrize("target", ["session", "lock"])
def test_snapshot_storage_rejects_symlinks(advisor, service_profile, target):
    service, _, _ = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    path = service._chat_options["session_dir"] / f"{session.session_id}.json"
    service.close_session(session.session_id)
    candidate = path if target == "session" else path.with_suffix(".lock")
    candidate.unlink()
    candidate.symlink_to(path.parent / "unrelated")
    with pytest.raises(chat.ChatError, match="symlink"):
        service.resume_session(session.session_id)


def test_worker_can_resume_pending_review(advisor, service_profile, service_review):
    service, _, _ = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    service.close_session(session.session_id)
    engine = Mock(return_value=service_review)
    with AdvisorService(review_engine=engine, review_settings=service._review_settings,
                        session_dir=service._chat_options["session_dir"]) as worker:
        worker.resume_session(session.session_id)
        worker.run_initial_review(session.session_id)
        assert worker.get_session(session.session_id).status == "ready"
        engine.assert_called_once()


def test_review_and_chat_payloads_match_existing_engines(advisor, service_profile, service_review, service_reply, sdk_client, tmp_path):
    service, review_client, chat_client = advisor
    legacy_review_client = sdk_client(service_review)
    review.generate_review(service_profile, "SQL", service._review_settings, client=legacy_review_client)
    session = service.create_session(service_profile, "SQL")
    service.run_initial_review(session.session_id)
    assert review_client.responses.parse.call_args == legacy_review_client.responses.parse.call_args
    assert review_client.responses.input_tokens.count.call_args == legacy_review_client.responses.input_tokens.count.call_args
    paths = [tmp_path / "profile.json", tmp_path / "jd.txt", tmp_path / "review.json"]
    for path, value in zip(paths, [json.dumps(service_profile), "SQL", json.dumps(service_review)]):
        path.write_text(value)
    legacy_chat_client = sdk_client(service_reply)
    with chat.AcademicChatSession.from_files(*paths, settings=service._chat_options["settings"], client=legacy_chat_client) as legacy:
        for message in ["First", "Second"]:
            service.send_message(session.session_id, message)
            legacy.send(message)
            assert chat_client.responses.parse.call_args == legacy_chat_client.responses.parse.call_args
            assert chat_client.responses.input_tokens.count.call_args == legacy_chat_client.responses.input_tokens.count.call_args


def test_stage_specific_environment_precedence_is_used(service_profile, service_review, service_reply, sdk_client, monkeypatch):
    for key, value in {"OPENAI_API_KEY": "offline-env", "MODEL": "gpt-4o-mini", "OPENAI_MODEL": "gpt-4.1",
                       "OPENAI_REVIEW_MODEL": "gpt-5.4", "OPENAI_REVIEW_REASONING_EFFORT": "high",
                       "OPENAI_REVIEW_MAX_OUTPUT_TOKENS": "32768", "OPENAI_CHAT_MODEL": "gpt-5.4-mini",
                       "OPENAI_CHAT_REASONING_EFFORT": "medium", "OPENAI_CHAT_MAX_OUTPUT_TOKENS": "8192"}.items():
        monkeypatch.setenv(key, value)
    a, b = sdk_client(service_review), sdk_client(service_reply)
    with AdvisorService(review_client=a, chat_client=b) as service:
        session = service.create_session(service_profile, "SQL")
        service.run_initial_review(session.session_id)
        service.send_message(session.session_id, "Question")
        monkeypatch.delenv("OPENAI_API_KEY")
        with pytest.raises(ReviewAlreadyReadyError):
            service.run_initial_review(session.session_id)
    assert a.responses.parse.call_args.kwargs["model"] == "gpt-5.4"
    assert a.responses.parse.call_args.kwargs["max_output_tokens"] == 32768
    assert b.responses.parse.call_args.kwargs["model"] == "gpt-5.4-mini"
    assert b.responses.parse.call_args.kwargs["reasoning"] == {"effort": "medium"}
    # Existing default timeout is preserved, rather than silently adopting 360.
    assert a.responses.parse.call_args.kwargs["timeout"] == 180


@pytest.mark.parametrize("stage", ["review", "chat"])
def test_interrupt_closes_owner_without_partial_commit(advisor, service_profile, stage):
    service, review_client, chat_client = advisor
    session = service.create_session(service_profile, "SQL", persist=True)
    if stage == "chat": service.run_initial_review(session.session_id)
    path = service._chat_options["session_dir"] / f"{session.session_id}.json"
    before = path.read_bytes()
    (review_client if stage == "review" else chat_client).responses.parse.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        if stage == "review": service.run_initial_review(session.session_id)
        else: service.send_message(session.session_id, "Interrupted")
    assert path.read_bytes() == before and service.get_history(session.session_id) == []
    with pytest.raises(chat.ChatError, match="đã đóng"):
        service.send_message(session.session_id, "Cannot continue")


def test_concurrent_review_attempts_share_session_lock(advisor, service_profile):
    service, client, _ = advisor
    session = service.create_session(service_profile, "SQL")
    started, release = threading.Event(), threading.Event()
    result = client.responses.parse.return_value
    def generation(**kwargs):
        started.set()
        assert release.wait(5)
        return result
    client.responses.parse.side_effect = generation
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.run_initial_review, session.session_id)
        try:
            assert started.wait(5)
            second = executor.submit(service.run_initial_review, session.session_id)
        finally:
            release.set()
        assert first.result().review_type == "academic_knowledge_review"
        with pytest.raises(ReviewAlreadyReadyError): second.result()
    assert client.responses.parse.call_count == 1
