import copy

import pytest

from app.services import ProfileService


def valid_body():
    return {"curriculum_code": "configured", "selected_courses": ["TEST101"], "grades": [
        {"course_code": "TEST101", "category": "Quiz 1", "grade": 10},
        {"course_code": "TEST101", "category": "Final exam", "grade": 8}]}


def test_profile_storage_equals_service_output_and_capability_is_hashed(api_backend, stored_profile):
    headers = {"Authorization": "Bearer " + stored_profile["access_token"]}
    response = api_backend.client.get("/api/v1/profiles/" + stored_profile["profile_id"], headers=headers)
    assert response.status_code == 200 and "access_token" not in response.json()
    assert response.json()["profile"] == ProfileService(api_backend.catalog).build_profile(
        ["TEST101"], {"TEST101": {"Quiz 1": 10, "Final exam": 8}})
    assert response.json()["summary"] == {"course_count": 1, "clo_count": 2}
    with api_backend.database.transaction() as connection:
        row = dict(connection.execute("SELECT * FROM profiles").fetchone())
    assert stored_profile["access_token"] not in str(row) and len(row["owner_hash"]) == 64
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("case", ["missing", "null", "negative", "too_high", "boolean", "duplicate", "unknown", "foreign", "mixed_curriculum", "duplicate_course"])
def test_invalid_grades_never_create_partial_rows(api_backend, case):
    body = valid_body()
    if case == "missing": body["grades"].pop()
    elif case == "null": body["grades"][0]["grade"] = None
    elif case == "negative": body["grades"][0]["grade"] = -1
    elif case == "too_high": body["grades"][0]["grade"] = 10.1
    elif case == "boolean": body["grades"][0]["grade"] = True
    elif case == "duplicate": body["grades"].append(copy.deepcopy(body["grades"][0]))
    elif case == "unknown": body["grades"][0]["category"] = "unknown"
    elif case == "foreign": body["grades"][0]["course_code"] = "OTHER201"
    elif case == "mixed_curriculum": body["selected_courses"].append("FOREIGN301")
    elif case == "duplicate_course": body["selected_courses"].append("TEST101")
    response = api_backend.client.post("/api/v1/profiles", json=body)
    assert response.status_code in {422, 404}
    with api_backend.database.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_zero_is_legitimate_and_old_profile_is_immutable(api_backend, stored_profile):
    body = valid_body()
    for entry in body["grades"]: entry["grade"] = 0
    response = api_backend.client.post("/api/v1/profiles", json=body)
    assert response.status_code == 201
    assert all(c["score"] == 0 for c in response.json()["profile"]["courses"][0]["clos"])
    assert response.json()["profile_id"] != stored_profile["profile_id"]
    old = api_backend.backend.profiles.get(stored_profile["profile_id"], stored_profile["access_token"])
    assert old["profile"] == stored_profile["profile"]
    assert api_backend.client.get("/api/v1/profiles/" + old["profile_id"]).status_code == 401
    assert api_backend.client.get("/api/v1/profiles/" + old["profile_id"], headers={
        "Authorization": "Bearer " + response.json()["access_token"]}).status_code == 403


def test_body_limits_malformed_json_and_safe_validation_errors(api_backend):
    response = api_backend.client.post("/api/v1/profiles", content='{"grades":[],"grades":[]}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_json"
    response = api_backend.client.post("/api/v1/profiles", content='{"x":NaN}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert api_backend.client.post("/api/v1/profiles", json={"secret": "x" * 10000}).status_code == 413
    response = api_backend.client.post("/api/v1/profiles", json={"secret": "sk-do-not-echo"})
    assert response.status_code == 422 and "sk-do-not-echo" not in response.text
    assert api_backend.client.get("/not-an-endpoint").json()["error"]["code"] == "resource_not_found"


def test_body_limit_also_bounds_chunked_upload_without_content_length(api_backend):
    def chunks():
        yield b'{"message":"'
        yield b"x" * 5000
        yield b'"}'
    response = api_backend.client.post("/api/v1/profiles", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413 and response.json()["error"]["code"] == "request_too_large"
