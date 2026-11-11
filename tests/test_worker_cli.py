from app.jobs.worker_cli import main


def test_empty_once_and_recovery_modes_do_not_construct_sdk(tmp_path, service_offline, monkeypatch, capsys):
    from app.llm import openai
    def forbidden(*args, **kwargs):
        raise AssertionError("No queued work may not create an SDK client")
    monkeypatch.setattr(openai, "OpenAI", forbidden)
    monkeypatch.setenv("SKILLBRIDGE_DATABASE_PATH", str(tmp_path / "cli.sqlite3"))
    assert main(["--once", "--review-timeout", "360"]) == 0
    assert '"no_queued_job"' in capsys.readouterr().out
    assert main(["--recover-only"]) == 0
    assert '"interrupted_operations": 0' in capsys.readouterr().out
