import pytest

from app.config import BackendSettings


def test_default_and_explicit_curriculum_getters(api_backend):
    client = api_backend.client
    response = client.get("/api/v1/courses")
    assert response.status_code == 200
    assert {r["course_code"] for r in response.json()["courses"]} == {"TEST101", "OTHER201"}
    detail = client.get("/api/v1/courses/FOREIGN301?curriculum_code=other")
    assert detail.status_code == 200 and detail.json()["metadata"]["subject_code"] == "FOREIGN301"
    assert detail.json()["assessments"][0] == {"category": "Quiz 1", "part": "1", "weight": "25%", "clo": "CLO1"}
    assert client.get("/api/v1/courses/FOREIGN301").status_code == 404
    assert client.get("/api/v1/courses?curriculum_code=unknown").json()["error"]["code"] == "unknown_curriculum"
    api_backend.review_client.responses.parse.assert_not_called()


def test_health_and_openapi_are_available_without_api_key(api_backend):
    assert api_backend.client.get("/api/v1/health").status_code == 200
    document = api_backend.client.get("/openapi.json").json()
    assert "/api/v1/advisor/sessions/{session_id}/messages" in document["paths"]
    assert document["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert api_backend.client.get("/docs").status_code == 200


def test_unusable_course_metadata_is_reported_as_availability(api_backend):
    (api_backend.catalog.courses_dir / "TEST101/metadata.json").write_text("{}")
    result = api_backend.client.get("/api/v1/courses/TEST101")
    assert result.status_code == 200 and result.json()["metadata"] is None
    assert not result.json()["availability"]["metadata"]


@pytest.mark.parametrize("origin,status", [("http://localhost:5173", 200), ("https://unapproved.example", 400)])
def test_cors_is_explicit_without_wildcard_credentials(api_backend, origin, status):
    response = api_backend.client.options("/api/v1/profiles", headers={"Origin": origin,
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization,Idempotency-Key"})
    assert response.status_code == status
    assert "access-control-allow-credentials" not in response.headers


def test_missing_curriculum_configuration_fails_safely(tmp_path, service_offline):
    from app.main import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(BackendSettings(database_path=tmp_path / "empty.sqlite3"))) as client:
        assert client.get("/api/v1/health").status_code == 503
        assert client.get("/api/v1/courses").json()["error"]["code"] == "backend_unavailable"


@pytest.mark.parametrize("kwargs", [{"cors_origins": ("*",)}, {"lease_seconds": 10, "heartbeat_interval": 5},
                                     {"curriculum_mapping": {"x": "3173"}}, {"database_path": ":memory:"}])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError): BackendSettings(**kwargs)
