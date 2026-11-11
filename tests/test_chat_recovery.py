import copy

import pytest


@pytest.mark.parametrize("failure,expected", [("incomplete", 502), ("evidence", 502), ("runtime", 409), ("commit", 409)])
def test_failed_chat_never_commits_a_partial_turn_or_automatically_retries(api_backend, ready_session, failure, expected):
    if failure == "incomplete": api_backend.chat_client.responses.parse.return_value.status = "incomplete"
    elif failure == "evidence":
        raw = copy.deepcopy(api_backend.chat_client.responses.parse.return_value.output_parsed)
        raw["evidence"][0]["clo"] = "CLO999"
        api_backend.chat_client.responses.parse.return_value.output_parsed = raw
    elif failure == "runtime": api_backend.chat_client.responses.parse.side_effect = RuntimeError("sk-secret")
    else:
        with api_backend.database.transaction(write=True) as connection:
            connection.execute("""CREATE TRIGGER fail_chat BEFORE UPDATE OF status ON requests
                WHEN NEW.scope LIKE 'chat:%' AND NEW.status='succeeded' BEGIN SELECT RAISE(ABORT,'commit failure'); END""")
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    headers = {**ready_session["headers"], "Idempotency-Key": "failed-chat"}
    response = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
    assert response.status_code == expected and "sk-secret" not in response.text
    assert api_backend.client.get(path, headers=headers).json()["turns"] == []
    repeat = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
    assert repeat.status_code == expected
    assert api_backend.chat_client.responses.parse.call_count == 1
    with api_backend.database.transaction() as connection:
        row = connection.execute("SELECT snapshot_json,lease_token,revision FROM sessions").fetchone()
        assert row["lease_token"] is None and row["revision"] == 1


pytestmark = pytest.mark.parametrize("target_domain", ["jd", "cwa"], indirect=True)


def test_expired_chat_is_durably_uncertain_on_same_key_retry(api_backend, ready_session):
    lease, _ = api_backend.backend.sessions.claim_chat(ready_session["session_id"], ready_session["access_token"], "SQL?", "abandoned")
    api_backend.backend.sessions.mark_dispatched(lease)
    api_backend.clock.advance(31)
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    response = api_backend.client.post(path, headers={**ready_session["headers"], "Idempotency-Key": "abandoned"}, json={"message": "SQL?"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "operation_interrupted"
    with api_backend.database.transaction() as connection:
        assert connection.execute("SELECT status FROM requests WHERE request_id=?", (lease.operation_id,)).fetchone()[0] == "interrupted"
    api_backend.chat_client.responses.parse.assert_not_called()


def test_corrupt_idempotency_cache_does_not_override_authoritative_history(api_backend, ready_session):
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    headers = {**ready_session["headers"], "Idempotency-Key": "cache"}
    assert api_backend.client.post(path, headers=headers, json={"message": "SQL?"}).status_code == 200
    with api_backend.database.transaction(write=True) as connection:
        connection.execute("UPDATE requests SET response_json='{}' WHERE scope LIKE 'chat:%'")
    response = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
    assert response.status_code == 500 and response.json()["error"]["code"] == "storage_integrity_error"
    assert api_backend.chat_client.responses.parse.call_count == 1
    assert len(api_backend.client.get(path, headers=headers).json()["turns"]) == 1
