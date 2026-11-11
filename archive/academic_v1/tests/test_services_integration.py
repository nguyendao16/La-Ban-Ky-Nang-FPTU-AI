from __future__ import annotations

import importlib

import pytest

from examples.services_integration import main, run_demo
from scripts import academic_review as review

pytestmark = pytest.mark.usefixtures("service_offline")


def test_example_uses_actual_contracts_and_no_sdk_or_console_input(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline example may not create SDK clients or read terminal input")
    monkeypatch.setattr(review.openai, "OpenAI", forbidden)
    monkeypatch.setattr("builtins.input", forbidden)
    result = run_demo(curriculum_code="explicit-example-source", curriculum_source_id="3173")
    assert len(result["courses"]) == 49 and result["session"]["status"] == "ready"
    assert result["mock_calls"] == {"review": {"preflight": 1, "generation": 1}, "chat": {"preflight": 1, "generation": 1}}
    assert len(result["history"]) == 2 and result["session"]["persistent"] is False
    assert result["profile"]["courses"][0]["course_code"] == "ADY201m"


def test_example_cli_requires_explicit_mapping(capsys):
    assert main(["--curriculum-code", "explicit-example-source", "--curriculum-source-id", "3173"]) == 0
    assert '"status": "ready"' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main([])


def test_legacy_cli_modules_importable_without_modifying_sys_path():
    for module in ["scripts.build_student_academic_profile", "scripts.review_academic_profile", "scripts.chat_academic_profile"]:
        assert callable(importlib.import_module(module).main)
