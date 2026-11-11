from unittest.mock import Mock

from app.services import AdvisorService
from scripts.academic_review import ReviewSettings, openai


def test_snapshot_operations_disable_sdk_retries_without_changing_legacy_policy(service_offline, service_profile,
        service_review, service_reply, sdk_client, monkeypatch):
    review_client, chat_client = sdk_client(service_review), sdk_client(service_reply)
    constructor = Mock(side_effect=[review_client, chat_client])
    monkeypatch.setattr(openai, "OpenAI", constructor)
    advisor = AdvisorService(review_settings=ReviewSettings(api_key="offline", stage="review"),
                             chat_settings=ReviewSettings(api_key="offline", stage="chat"))
    snapshot = advisor.create_snapshot(service_profile, "SQL")
    snapshot, _ = advisor.review_snapshot(snapshot)
    snapshot, _ = advisor.chat_snapshot(snapshot, "Question")
    assert all(call.kwargs["max_retries"] == 0 for call in constructor.call_args_list)
    assert constructor.call_count == 2 and len(snapshot["messages"]) == 2
    review_client.close.assert_called_once()
    chat_client.close.assert_called_once()
    assert review_client.responses.parse.call_count == chat_client.responses.parse.call_count == 1
