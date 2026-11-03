from conftest import FIXTURES
from jobseeker_assistant import cli, snapshots


def test_cli_answers_with_fake_llm(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setattr(snapshots, "DEFAULT_SOURCES_DIR", FIXTURES / "sources")
    assert cli.main(["How long can a work trial last?"]) == 0
    out = capsys.readouterr().out
    assert "example.test/work-trial" in out and "Note:" in out


def test_cli_without_snapshots(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(snapshots, "DEFAULT_SOURCES_DIR", tmp_path)
    assert cli.main(["question"]) == 1
    assert "make ingest" in capsys.readouterr().out


def test_cli_without_question(capsys):
    assert cli.main([]) == 2
