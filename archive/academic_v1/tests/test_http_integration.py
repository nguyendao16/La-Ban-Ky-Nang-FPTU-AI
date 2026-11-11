from examples.http_integration import run_demo


def test_full_http_example_uses_real_categories_and_only_mocked_generation(service_offline, monkeypatch):
    from scripts.academic_review import openai
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP integration must not construct an SDK client")
    monkeypatch.setattr(openai, "OpenAI", forbidden)
    result = run_demo(curriculum_code="explicit-example-source", curriculum_source_id="3173")
    assert result["catalog_courses"] == 49 and result["assessments"] == 8
    assert result["profile_summary"] == {"course_count": 1, "clo_count": 7}
    assert result["mock_generations"] == result["mock_preflights"] == {"review": 1, "chat": 1}
    assert result["committed_turns"] == 1 and result["session_status"] == "ready"
    assert "access_token" not in result
