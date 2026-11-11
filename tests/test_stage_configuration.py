"""Exercise owned SDK construction and real durable stage wiring, offline."""

import json
from unittest.mock import Mock

import pytest

from app.jobs.review_worker import ReviewWorker
from app.services import AdvisorService
from app.settings_diagnostics import resolved_settings
from app import llm
from app.llm import ComparisonError, LLMSettings, load_settings


def configure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-stage-key")
    for stage, model, effort, output, timeout in [
        ("REVIEW", "gpt-5.4", "high", "32768", "360"),
        ("CHAT", "gpt-5.4-mini", "medium", "8192", "180"),
    ]:
        for suffix, value in [("MODEL", model), ("REASONING_EFFORT", effort),
                              ("MAX_OUTPUT_TOKENS", output), ("REQUEST_TIMEOUT", timeout)]:
            monkeypatch.setenv(f"OPENAI_{stage}_{suffix}", value)


def check_request(client, settings):
    count = client.responses.input_tokens.count
    parse = client.responses.parse
    assert count.call_count == parse.call_count == 1
    for request in [count.call_args.kwargs, parse.call_args.kwargs]:
        assert request["timeout"] == settings.timeout
        assert request["model"] == settings.model
        assert request["reasoning"] == {"effort": settings.reasoning_effort}
        assert "temperature" not in request
    assert parse.call_args.kwargs["max_output_tokens"] == settings.max_output_tokens
    assert parse.call_args.kwargs["store"] is False
    assert parse.call_args.kwargs["truncation"] == "disabled"


@pytest.mark.parametrize("stage", ["review", "chat"])
@pytest.mark.parametrize("failure", [False, True])
def test_owned_default_constructor_stage_payload_and_cleanup(service_offline, service_clo_set,
        service_review, service_reply, sdk_client, monkeypatch, stage, failure):
    settings = LLMSettings(api_key="offline-owned", stage=stage,
        model="gpt-5.4" if stage == "review" else "gpt-5.4-mini",
        max_output_tokens=32768 if stage == "review" else 8192,
        request_timeout=360 if stage == "review" else 180)
    client = sdk_client(service_review if stage == "review" else service_reply)
    if failure:
        client.responses.parse.side_effect = ComparisonError("mock failure")
    constructor = Mock(return_value=client)
    monkeypatch.setattr(llm.openai, "OpenAI", constructor)
    advisor = AdvisorService(**{f"{stage}_settings": settings})
    snapshot = advisor.create_snapshot(service_clo_set, "SQL")
    if stage == "chat":
        from app.engines.chat import CLOChatSession
        with CLOChatSession.from_data(service_clo_set, "SQL", service_review) as session:
            snapshot = session.export_snapshot()
    operation = lambda: advisor.review_snapshot(snapshot) if stage == "review" else advisor.chat_snapshot(snapshot, "SQL?")
    if failure:
        with pytest.raises(ComparisonError):
            operation()
    else:
        operation()
    constructor.assert_called_once_with(api_key="offline-owned", timeout=settings.timeout, max_retries=0)
    client.close.assert_called_once()
    check_request(client, settings)
    assert snapshot["messages"] == []  # Caller snapshot stays detached even on failure.


@pytest.mark.parametrize("stage", ["review", "chat"])
def test_injected_client_is_never_recreated_or_closed(service_offline, service_clo_set, service_review,
        service_reply, sdk_client, monkeypatch, stage):
    client = sdk_client(service_review if stage == "review" else service_reply)
    constructor = Mock(side_effect=AssertionError("Injected client must be reused"))
    monkeypatch.setattr(llm.openai, "OpenAI", constructor)
    advisor = AdvisorService(**{f"{stage}_client": client, f"{stage}_settings": LLMSettings(api_key="offline", stage=stage)})
    snapshot = advisor.create_snapshot(service_clo_set, "SQL")
    if stage == "review":
        advisor.review_snapshot(snapshot)
    else:
        from app.engines.chat import CLOChatSession
        with CLOChatSession.from_data(service_clo_set, "SQL", service_review) as session:
            advisor.chat_snapshot(session.export_snapshot(), "SQL?")
    constructor.assert_not_called()
    client.close.assert_not_called()


@pytest.mark.parametrize("target_domain", ["jd", "cwa"], indirect=True)
def test_worker_and_http_chat_resolve_distinct_environment_stages(api_backend, queued_session,
        sdk_client, service_review, service_reply, monkeypatch):
    configure(monkeypatch)
    advisor = api_backend.advisor
    advisor._review_settings = advisor._review_client = None
    advisor._chat_options.update(settings=None, client=None)
    clients = [sdk_client(api_backend.review_client.responses.parse.return_value.output_parsed), sdk_client(service_reply)]
    constructor = Mock(side_effect=clients)
    monkeypatch.setattr(llm.openai, "OpenAI", constructor)
    worker = ReviewWorker(api_backend.backend.jobs, advisor, review_settings_overrides={"request_timeout": 361})
    try:
        worker.run_once()
    finally:
        worker.close()
    path = f'/api/v1/advisor/sessions/{queued_session["session_id"]}/messages'
    headers = {**queued_session["headers"], "Idempotency-Key": "stage-chat"}
    response = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
    assert response.status_code == 200
    assert api_backend.client.post(path, headers=headers, json={"message": "SQL?"}).json() == response.json()
    assert [c.kwargs["timeout"] for c in constructor.call_args_list] == [361, 180]
    assert all(c.kwargs["max_retries"] == 0 for c in constructor.call_args_list)
    check_request(clients[0], load_settings(stage="review", request_timeout=361))
    check_request(clients[1], load_settings(stage="chat"))


def test_timeout_precedence_and_unset_defaults(service_offline, monkeypatch):
    configure(monkeypatch)
    assert load_settings(stage="review").timeout == 360
    assert load_settings(stage="chat").timeout == 180
    assert load_settings(stage="review", request_timeout=420).timeout == 420
    monkeypatch.delenv("OPENAI_REVIEW_REQUEST_TIMEOUT")
    assert load_settings(stage="review").timeout == 180
    monkeypatch.delenv("OPENAI_CHAT_REASONING_EFFORT")
    assert load_settings(model="gpt-4o-mini", reasoning_effort=None, stage="chat").timeout == 180
    monkeypatch.delenv("OPENAI_CHAT_REQUEST_TIMEOUT")
    assert load_settings(model="gpt-4o-mini", stage="chat").timeout == 60


@pytest.mark.parametrize("value", ["oops", "", "0", "-1", "NaN", "inf"])
def test_invalid_environment_timeout_is_rejected_without_echo(service_offline, monkeypatch, value):
    monkeypatch.setenv("OPENAI_REVIEW_REQUEST_TIMEOUT", value)
    with pytest.raises(ComparisonError):
        load_settings(api_key="offline")


def test_nonsecret_diagnostics_never_construct_sdk(service_offline, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(llm.openai, "OpenAI", Mock(side_effect=AssertionError("Offline diagnostics")))
    result = resolved_settings()
    assert result["review"] == {"model": "gpt-5.4", "reasoning_effort": "high", "max_output_tokens": 32768, "request_timeout": 360}
    assert result["chat"] == {"model": "gpt-5.4-mini", "reasoning_effort": "medium", "max_output_tokens": 8192, "request_timeout": 180}
    assert "offline-stage-key" not in json.dumps(result)
