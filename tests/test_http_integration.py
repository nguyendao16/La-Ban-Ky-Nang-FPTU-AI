import pytest
from examples.http_integration import run_demo


@pytest.mark.parametrize("career_profile_id", [None, "data-analyst"])
def test_full_http_example_uses_real_clos_and_only_mocked_generation(service_offline, monkeypatch, career_profile_id):
    from app.llm import openai
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP integration must not construct an SDK client")
    monkeypatch.setattr(openai, "OpenAI", forbidden)
    result = run_demo(curriculum_code="explicit-example-source", curriculum_source_id="3173", career_profile_id=career_profile_id)
    assert result["catalog_courses"] == 41
    assert result["selection_summary"] == {"course_count": 1}
    assert result["mock_generations"] == result["mock_preflights"] == {"review": 1, "chat": 1}
    assert result["committed_turns"] == 1 and result["session_status"] == "ready"
    assert "access_token" not in result
