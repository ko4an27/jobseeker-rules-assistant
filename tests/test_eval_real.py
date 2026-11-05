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
    assert "not marked reviewed" not in out and "overall verdict agreement" in out
    [report] = reports_in_tmp.glob("*judge-calibration*.json")
    assert json.loads(report.read_text())["labels_reviewed"] is True


def test_overall_verdict_needs_every_applicable_check_and_counts_errors_as_not_passed():
    from jobseeker_assistant.evals import CaseResult, judge_summary

    def r(scores, error=""):
        res = CaseResult("i", "current", "q", False, False, "", True, True, True, True, True)
        res.judge = {"scores": scores, "reasons": {}, "error": error}
        return res

    s = judge_summary(
        [
            r({"correct": "pass", "grounded": "pass", "replaced_note": "n/a"}),  # passes
            r({"correct": "pass", "grounded": "fail"}),  # one failing check
            r({}, error="judge reply had no JSON object"),  # judge error
        ]
    )
    assert list(s)[0] == "judge_overall" and s["judge_overall"] == "1/3"
    assert s["judge_grounded"] == "1/2" and s["judge_replaced_note"] == "–"
    assert s["judge_errors"] == "1/3"


class _Model:
    def __init__(self, provider, model):
        self.provider, self.model = provider, model


class _Judge:
    def __init__(self, llm):
        self.llm = llm


def test_self_judged_detection():
    from jobseeker_assistant.evals import is_self_judged

    lite = _Model("gemini", "gemini-3.5-flash-lite")
    assert is_self_judged(lite, _Judge(_Model("gemini", "gemini-3.5-flash-lite")))
    assert not is_self_judged(lite, _Judge(_Model("gemini", "gemini-3.7-flash")))
    assert not is_self_judged(lite, _Judge(_Model("groq", "gemini-3.5-flash-lite")))
    assert not is_self_judged(lite, FakeJudge())  # fake judge has no model


def test_self_judged_run_warns_and_marks_report(real_index, tmp_path, reports_in_tmp, capsys):
    from jobseeker_assistant.judge import LLMJudge

    llm, budget = _guarded(tmp_path, max_calls=500)
    judge = LLMJudge(llm)  # same guarded fake model for answering and judging
    evals.run_real(_args(), real_index, load_glossary(), llm, judge, budget)
    assert "WARNING: the judge is the same model" in capsys.readouterr().out
    [report] = reports_in_tmp.glob("*.json")
    assert json.loads(report.read_text())["meta"]["self_judged"] is True
    assert "same model that wrote the answers" in report.with_suffix(".md").read_text()


class _Down:
    """A model that is always overloaded."""

    provider, model = "gemini", "gemini-3.7-flash"

    def complete(self, system, user):
        from jobseeker_assistant.llm import ProviderError

        raise ProviderError("gemini returned HTTP 503 for model gemini-3.7-flash: high demand")


def test_unavailable_judge_is_recorded_not_fatal(real_index, tmp_path, reports_in_tmp, capsys):
    from jobseeker_assistant.judge import LLMJudge

    llm, budget = _guarded(tmp_path, max_calls=500)
    code = evals.run_real(_args(), real_index, load_glossary(), llm, LLMJudge(_Down()), budget)
    assert code == 0
    [report] = reports_in_tmp.glob("*.json")
    data = json.loads(report.read_text())
    assert data["summary"]["judge_errors"] == "38/38"
    assert data["summary"]["judge_overall"] == "0/38"  # errors never count as passed
    assert "judge unavailable" in data["results"][0]["judge"]["error"]


def test_unavailable_answer_model_aborts_cleanly(real_index, tmp_path, reports_in_tmp, capsys):
    budget = Budget(500)
    code = evals.run_real(_args(), real_index, load_glossary(), _Down(), FakeJudge(), budget)
    assert code == 3
    assert "answering model unavailable" in capsys.readouterr().out
    [report] = reports_in_tmp.glob("*.json")
    assert "answering model unavailable" in json.loads(report.read_text())["meta"]["aborted"]


def test_judge_timeout_is_recorded_not_fatal(real_index, tmp_path, reports_in_tmp):
    """Real run 2026-11-05: a judge read timeout crashed the whole eval."""
    import requests

    from jobseeker_assistant.judge import LLMJudge
    from jobseeker_assistant.llm import GeminiLLM

    def post(url, headers, json, timeout):
        raise requests.exceptions.ReadTimeout("Read timed out.")

    judge_llm = GeminiLLM("gemini-3.7-flash", "k", post=post, sleep=lambda s: None)
    llm, budget = _guarded(tmp_path, max_calls=500)
    assert (
        evals.run_real(_args(), real_index, load_glossary(), llm, LLMJudge(judge_llm), budget) == 0
    )
    [report] = reports_in_tmp.glob("*.json")
    assert json.loads(report.read_text())["summary"]["judge_errors"] == "38/38"


def test_judge_gets_a_larger_output_cap_than_answers():
    from jobseeker_assistant.evals import JUDGE_MAX_TOKENS, judge_model_from_env
    from jobseeker_assistant.llm import get_llm

    env = {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "k", "JUDGE_MODEL": "gemini-3.6-flash"}
    judge = judge_model_from_env(env)
    assert judge.model == "gemini-3.6-flash" and judge.max_tokens == JUDGE_MAX_TOKENS == 2000
    assert get_llm(env).max_tokens == 800  # answers unchanged
