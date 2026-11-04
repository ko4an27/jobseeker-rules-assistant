import json

import pytest

from jobseeker_assistant.answer import Answer, Citation
from jobseeker_assistant.evals import (
    Case,
    case_signals,
    fact_present,
    grade,
    load_golden,
    run,
    save_report,
    summarize,
    sweep,
)
from jobseeker_assistant.llm import FakeLLM

IN = Case(
    "c1",
    "current",
    "What is the duration of a work trial?",
    False,
    ("six months | 6 months",),
    ("https://example.test/work-trial",),
)
OUT = Case("o1", "out_of_scope", "best pizza helsinki", True)


def test_fact_present_alternatives_and_case():
    assert fact_present("six months | 6 months", "It lasts 6 Months.")
    assert fact_present("50%", "about 50% of pay")
    assert not fact_present("21 weeks", "20 weeks")


def test_load_golden_rejects_bad_cases(tmp_path):
    f = tmp_path / "g.yaml"
    f.write_text("- {id: a, category: current, question: q}\n")
    with pytest.raises(ValueError, match="key_facts"):
        load_golden(f)
    f.write_text(
        "- {id: a, category: out_of_scope, question: q, must_refuse: true, key_facts: [x]}\n"
    )
    with pytest.raises(ValueError, match="must_refuse"):
        load_golden(f)
    f.write_text("- {id: a, category: other, question: q, must_refuse: true}\n")
    with pytest.raises(ValueError, match="category"):
        load_golden(f)
    f.write_text("- {id: a, category: out_of_scope, question: q, must_refuse: true}\n" * 2)
    with pytest.raises(ValueError, match="duplicate"):
        load_golden(f)


def test_grade_in_scope_pass_and_fail():
    cit = Citation("S1", "https://example.test/work-trial", "Duration", "d")
    good = grade(IN, Answer("At most six months [S1].", [cit]), 5.0)
    assert good.passed and good.source_cited and good.facts_in_answer
    wrong_fact = grade(IN, Answer("At most a year [S1].", [cit]), 5.0)
    assert not wrong_fact.passed and wrong_fact.missing_facts == ["six months | 6 months"]
    refused = grade(IN, Answer("I can't confirm", refused=True), 0.0)
    assert not refused.passed and not refused.refusal_ok


def test_grade_counts_deduplicated_copy_as_expected_source():
    cit = Citation(
        "S1",
        "https://other.test/page",
        "Duration",
        "d",
        also_on=("https://example.test/work-trial",),
    )
    assert grade(IN, Answer("Six months [S1].", [cit]), 5.0).source_cited


def test_grade_out_of_scope():
    assert grade(OUT, Answer("I can't confirm", refused=True), 0.0).passed
    assert not grade(OUT, Answer("Pizza place [S1]."), 3.0).passed


def test_run_and_summarize(fixture_index):
    results = run([IN, OUT], fixture_index, FakeLLM())
    summary = summarize(results)
    assert summary["out_of_scope_refused"] == "1/1"
    assert summary["in_scope_answered"] == "1/1"
    assert summary["passed"] == "2/2"


def test_save_report_writes_json_and_markdown(tmp_path, fixture_index):
    results = run([IN, OUT], fixture_index, FakeLLM())
    meta = {
        "run_at": "2026-11-04T10:00:00+0000",
        "llm_provider": "fake",
        "llm": "fake",
        "min_score": 1.0,
        "min_coverage": 0.5,
        "commit": "abc",
        "cases": 2,
    }
    json_path, md_path = save_report(results, meta, tmp_path)
    assert json_path.name == "2026-11-04T100000Z_fake.json"
    data = json.loads(json_path.read_text())
    assert data["summary"]["passed"] == "2/2" and len(data["results"]) == 2
    assert "| c1 | current | ✅" in md_path.read_text()


def test_sweep_counts_tradeoff(fixture_index):
    signals = case_signals([IN, OUT], fixture_index)
    rows = sweep([IN, OUT], signals, "coverage", [0.0, 0.5, 1.01])
    assert [(r["oos_refused"], r["in_scope_kept"]) for r in rows] == [(0, 1), (1, 1), (1, 0)]


def test_save_report_never_overwrites(tmp_path, fixture_index):
    results = run([OUT], fixture_index, FakeLLM())
    meta = {
        "run_at": "2026-11-04T10:00:00+0000",
        "llm_provider": "fake",
        "llm": "fake",
        "min_score": 1.0,
        "commit": "abc",
        "cases": 1,
        "label": "before",
    }
    first, _ = save_report(results, meta, tmp_path)
    second, _ = save_report(results, meta, tmp_path)
    assert first.name == "2026-11-04T100000Z_fake_before.json"
    assert second.name == "2026-11-04T100000Z_fake_before-2.json"


def test_refusal_for_the_wrong_reason_fails():
    legal = Case("l1", "out_of_scope", "Should I sue?", True, refusal_reason="legal_advice")
    assert grade(legal, Answer("no", refused=True, refusal_reason="legal_advice:lawsuit"), 0).passed
    assert not grade(legal, Answer("no", refused=True, refusal_reason="low_coverage"), 0).passed


def test_refusal_reason_needs_must_refuse(tmp_path):
    f = tmp_path / "g.yaml"
    f.write_text(
        "- {id: a, category: current, question: q, refusal_reason: legal_advice,"
        " key_facts: [x], expected_sources: [u]}\n"
    )
    with pytest.raises(ValueError, match="refusal_reason"):
        load_golden(f)
