from jobseeker_assistant import demo


def test_demo_runs_offline_and_shows_paths(monkeypatch, capsys):
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    assert demo.main() == 0
    out = capsys.readouterr().out
    assert out.count("=== ") == 5 and out.count("path:   legal_check") == 5
    assert "REFUSED (low_coverage)" in out or "REFUSED (no_passages)" in out
    assert "REFUSED (legal_advice:predict_outcome)" in out
    assert out.count("Note: this is not legal or official advice.") == 5
