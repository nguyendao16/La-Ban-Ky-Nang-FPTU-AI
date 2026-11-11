import copy

from fastapi.testclient import TestClient

from app.main import create_app


def create_body(clo_set, jd="SQL internship"):
    return {"selection_id": clo_set["clo_set_id"], "job_description": jd}


def test_session_creation_is_queued_and_idempotent_without_inference(api_backend, stored_clo_set, queued_session):
    client, headers = api_backend.client, queued_session["headers"]
    repeat = client.post("/api/v1/advisor/sessions", headers=headers, json=create_body(stored_clo_set))
    assert repeat.status_code == 202 and repeat.json()["session_id"] == queued_session["session_id"]
    poll = client.get("/api/v1/advisor/sessions/" + queued_session["session_id"], headers=headers).json()
    assert poll["status"] == "queued" and poll["comparison"] is None
    assert "lease_token" not in str(poll) and "offline-worker" not in str(poll)
    api_backend.review_client.responses.parse.assert_not_called()
    conflict = client.post("/api/v1/advisor/sessions", headers=headers, json=create_body(stored_clo_set, "Different JD"))
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
    assert client.get("/api/v1/health").status_code == 503  # Durable queue exists, worker not yet available.


def test_capability_boundary_and_cross_owner_key_reuse(api_backend, stored_clo_set, queued_session):
    second = api_backend.backend.clo_sets.create("configured", ["TEST101"], stored_clo_set["clo_set"], stored_clo_set["diagnostics"])
    headers = {"Authorization": "Bearer " + second["access_token"], "Idempotency-Key": "create-session"}
    assert api_backend.client.get("/api/v1/advisor/sessions/" + queued_session["session_id"], headers=headers).status_code == 403
    assert api_backend.client.get("/api/v1/advisor/sessions/" + queued_session["session_id"] + "/messages", headers=headers).status_code == 403
    assert api_backend.client.post("/api/v1/advisor/sessions", headers=headers, json=create_body(stored_clo_set)).status_code == 403
    created = api_backend.client.post("/api/v1/advisor/sessions", headers=headers, json=create_body(second))
    assert created.status_code == 202 and created.json()["session_id"] != queued_session["session_id"]


def test_chat_requires_ready_and_idempotency_header(api_backend, queued_session):
    path = "/api/v1/advisor/sessions/" + queued_session["session_id"] + "/messages"
    response = api_backend.client.post(path, headers=queued_session["headers"], json={"message": "SQL?"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "session_not_ready"
    assert api_backend.client.post(path, headers={"Authorization": queued_session["headers"]["Authorization"]}, json={"message": "SQL?"}).status_code == 422
    api_backend.chat_client.responses.parse.assert_not_called()


def test_chat_replay_and_ordered_history_survive_new_app_instances(api_backend, ready_session):
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    headers = {**ready_session["headers"], "Idempotency-Key": "chat-one"}
    first = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
    assert first.status_code == 200 and set(first.json()) == {"message_id", "reply", "evidence"}
    assert api_backend.client.post(path, headers=headers, json={"message": "Other message"}).status_code == 409
    fresh_app = create_app(api_backend.settings, advisor_service=api_backend.advisor,
                           course_service=api_backend.catalog, database=api_backend.database)
    with TestClient(fresh_app) as fresh:
        replay = fresh.post(path, headers=headers, json={"message": "SQL?"})
        assert replay.json() == first.json()
        headers["Idempotency-Key"] = "chat-two"
        assert fresh.post(path, headers=headers, json={"message": "Follow-up"}).status_code == 200
        history = fresh.get(path, headers=headers).json()["turns"]
        assert [t["sequence"] for t in history] == [1, 2]
        assert [t["user_message"] for t in history] == ["SQL?", "Follow-up"]
        assert history[0]["message_id"] == first.json()["message_id"]
    assert api_backend.chat_client.responses.parse.call_count == 2
    assert api_backend.review_client.responses.parse.call_count == 1
    assert "_sessions" not in vars(api_backend.advisor)


def test_lost_http_response_replays_success_without_second_generation(api_backend, ready_session, monkeypatch):
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    headers = {**ready_session["headers"], "Idempotency-Key": "lost-response"}
    send = api_backend.backend.persistent.send_message
    def lost(*args):
        send(*args)
        raise RuntimeError("sk-secret-do-not-expose")
    with monkeypatch.context() as patch:
        patch.setattr(api_backend.backend.persistent, "send_message", lost)
        response = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
        assert response.status_code == 500 and "sk-secret" not in response.text
    repeat = api_backend.client.post(path, headers=headers, json={"message": "SQL?"})
    assert repeat.status_code == 200
    assert api_backend.chat_client.responses.parse.call_count == 1
    assert len(api_backend.client.get(path, headers=headers).json()["turns"]) == 1


def test_metadata_evidence_is_rejected_without_committing(api_backend, ready_session):
    api_backend.chat_client.responses.parse.return_value.output_parsed = {
        "reply": "Metadata is not a comparison source", "evidence": [{"course_code": "TEST101", "metadata_field": "description"}]}
    path = "/api/v1/advisor/sessions/" + ready_session["session_id"] + "/messages"
    response = api_backend.client.post(path, headers={**ready_session["headers"], "Idempotency-Key": "metadata"}, json={"message": "Tools?"})
    assert response.status_code == 502
    assert api_backend.client.get(path, headers=ready_session["headers"]).json()["turns"] == []
