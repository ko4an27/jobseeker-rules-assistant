"""The real-eval path (make eval-real / judge-calibrate), driven with fake model and judge."""

import argparse
import json

import pytest

from jobseeker_assistant import evals
from jobseeker_assistant.budget import Budget, GuardedLLM, ResponseCache
from jobseeker_assistant.glossary import load_glossary
from jobseeker_assistant.judge import FakeJudge
from jobseeker_assistant.llm import FakeLLM


def _args(**kw):
    base = dict(
        min_score=None,
        min_coverage=None,
        set="golden",
        no_save=False,
        label="test",
        real=True,
        judge_calibrate=False,
        sweep=False,
        no_glossary=False,
    )
    return argparse.Namespace(**{**base, **kw})


@pytest.fixture
def real_index():
    from jobseeker_assistant import snapshots
    from jobseeker_assistant.retrieve import Index
    from jobseeker_assistant.source_tags import load_tags

    return Index.from_snapshots(snapshots.load_all(), load_tags())


@pytest.fixture(autouse=True)
def reports_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(evals, "ROOT", tmp_path)
    return tmp_path / "reports"


def _guarded(tmp_path, max_calls):
    budget = Budget(max_calls)
    llm = GuardedLLM(FakeLLM(), budget, ResponseCache(tmp_path / "cache"), "c", min_interval=0)
    return llm, budget


def test_full_real_run_with_judge_saves_report(real_index, tmp_path, reports_in_tmp, capsys):
    llm, budget = _guarded(tmp_path, max_calls=500)
    code = evals.run_real(
        _args(), real_index, load_glossary(), llm, FakeJudge({"plain_language": "fail"}), budget
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "estimated max cost $0.0000" in out and "judge_plain_language" in out
    [report] = reports_in_tmp.glob("*.json")
    data = json.loads(report.read_text())
    assert data["meta"]["budget"]["calls"] == budget.calls > 0
    assert data["summary"]["judge_errors"] == "0/38"
    assert "aborted" not in data["meta"]
    assert data["results"][0]["judge"]["scores"]["plain_language"] == "fail"


def test_budget_limit_aborts_and_saves_partial_report(real_index, tmp_path, reports_in_tmp, capsys):
    llm, budget = _guarded(tmp_path, max_calls=5)
    code = evals.run_real(_args(), real_index, load_glossary(), llm, FakeJudge(), budget)
    assert code == 3 and budget.calls == 5
    assert "ABORTED: model call limit reached (5)" in capsys.readouterr().out
    [report] = reports_in_tmp.glob("*.json")
    data = json.loads(report.read_text())
    assert "stopped after" in data["meta"]["aborted"]
    assert 0 < len(data["results"]) < 38
    assert "ABORTED" in report.with_suffix(".md").read_text()


def test_rerun_uses_cache_and_finishes(real_index, tmp_path, reports_in_tmp):
    llm, budget = _guarded(tmp_path, max_calls=5)
    evals.run_real(_args(no_save=True), real_index, load_glossary(), llm, FakeJudge(), budget)
    llm2, budget2 = _guarded(tmp_path, max_calls=500)
    assert (
        evals.run_real(_args(no_save=True), real_index, load_glossary(), llm2, FakeJudge(), budget2)
        == 0
    )
    assert budget2.cache_hits == 5  # the 5 answers from the aborted run were reused


def test_real_main_refuses_the_fake_provider(monkeypatch, capsys, real_index):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert evals.real_main(_args(), real_index, []) == 2
    assert "needs a real model" in capsys.readouterr().out


def test_real_main_without_key_is_a_clean_error(monkeypatch, capsys, real_index):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert evals.real_main(_args(), real_index, []) == 2
    assert "LLM_API_KEY" in capsys.readouterr().out


def test_run_calibration_with_fake_judge(reports_in_tmp, capsys):
    assert evals.run_calibration(_args(judge_calibrate=True, real=False), FakeJudge()) == 0
    out = capsys.readouterr().out
    assert "not marked reviewed" in out and "judge agreement with labels" in out
    [report] = reports_in_tmp.glob("*judge-calibration*.json")
    assert json.loads(report.read_text())["labels_reviewed"] is False
