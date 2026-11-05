import json

import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.judge import (
    CALIBRATION_PATH,
    CRITERIA,
    RUBRIC_PATH,
    FakeJudge,
    JudgeInput,
    LLMJudge,
    build_prompt,
    calibrate,
    load_calibration,
    not_applicable,
    parse_verdict,
)
from jobseeker_assistant.llm import FakeLLM

ITEM = JudgeInput(
    question="How long can a work try-out last?",
    answer="At most six months [S1].",
    passages=[("S1", "https://x.test", "The maximum duration of a work try-out is six months.")],
    key_facts=("six months",),
)


def _reply(**verdicts):
    return json.dumps({c: {"verdict": v, "reason": f"{c} reason"} for c, v in verdicts.items()})


ALL_PASS = {c: "pass" for c in CRITERIA if c != "replaced_note"}


def test_rubric_file_covers_every_criterion():
    rubric = RUBRIC_PATH.read_text()
    for c in CRITERIA:
        assert "## " in rubric and c in rubric


def test_not_applicable_rules():
    assert not_applicable(ITEM) == {"replaced_note"}
    refused = JudgeInput("q", "I can't confirm", [], refused=True, must_refuse=True)
    assert not_applicable(refused) == {
        "correct",
        "grounded",
        "right_source",
        "meaning_preserved",
        "replaced_note",
    }
    named = JudgeInput("labour market subsidy?", "a", [], names_abolished=True)
    assert "replaced_note" not in not_applicable(named)


def test_prompt_contains_rubric_passages_facts_and_only_open_criteria():
    system, user = build_prompt(ITEM, "RUBRIC TEXT")
    assert "RUBRIC TEXT" in system and "replaced_note" not in system.split("exactly these keys")[1]
    assert "[S1] (https://x.test)" in user and "- six months" in user
    assert user.endswith("At most six months [S1].")


def test_parse_verdict_ok_and_code_decided_na():
    v = parse_verdict("Here you go:\n" + _reply(**ALL_PASS) + "\nthanks", ITEM)
    assert v.passed and not v.error
    assert v.scores["replaced_note"] == "n/a"  # decided by code, whatever the judge said


@pytest.mark.parametrize(
    "raw, msg",
    [
        ("no json here", "no JSON"),
        ("{not json}", "not valid JSON"),
        (_reply(correct="pass"), "no valid verdict"),
        (_reply(**{**ALL_PASS, "grounded": "maybe"}), "no valid verdict for 'grounded'"),
    ],
)
def test_parse_verdict_errors_never_raise(raw, msg):
    v = parse_verdict(raw, ITEM)
    assert msg in v.error and not v.passed


def test_llm_judge_uses_the_model_and_reports_failures():
    llm = FakeLLM(_reply(**{**ALL_PASS, "meaning_preserved": "fail"}))
    v = LLMJudge(llm, rubric="R").evaluate(ITEM)
    assert v.failed_criteria == ["meaning_preserved"]
    assert v.reasons["meaning_preserved"] == "meaning_preserved reason"
    assert len(llm.calls) == 1


def test_fake_judge_fixed_scores_respect_na():
    v = FakeJudge({"plain_language": "fail"}).evaluate(ITEM)
    assert v.scores["plain_language"] == "fail" and v.scores["correct"] == "pass"
    assert v.scores["replaced_note"] == "n/a"


# --- Calibration set ------------------------------------------------------------------


def test_calibration_set_loads_ten_reviewed_examples():
    examples, reviewed = load_calibration()
    assert len(examples) == 10 and reviewed is True  # approved by the project owner
    assert len({e.id for e in examples}) == 10


def test_calibration_passages_are_real_source_text():
    """Every passage in the calibration set is copied word for word from its snapshot."""
    bodies = {s.url: " ".join(s.body.split()) for s in snapshots.load_all()}
    for ex in load_calibration()[0]:
        for label, url, text in ex.item.passages:
            assert url in bodies, f"{ex.id}: no snapshot for {url}"
            assert " ".join(text.split()) in bodies[url], f"{ex.id} {label}: not in {url}"


def test_calibration_covers_every_criterion_with_a_fail():
    examples = load_calibration()[0]
    for c in CRITERIA:
        assert any(e.labels[c] == "fail" for e in examples), f"no example fails '{c}'"


def test_calibration_rejects_labels_that_contradict_na_rules(tmp_path):
    import yaml

    data = yaml.safe_load(CALIBRATION_PATH.read_text())
    data["examples"][0]["labels"]["replaced_note"] = "pass"  # c01 names no abolished benefit
    bad = tmp_path / "c.yaml"
    bad.write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ValueError, match="replaced_note"):
        load_calibration(bad)


def test_calibrate_perfect_judge_agrees_fully():
    examples = load_calibration()[0]
    # c06 and c07 share the same refusal text, so key on question + answer.
    labels = {(e.item.question, e.item.answer): e.labels for e in examples}
    result = calibrate(FakeJudge(lambda item: labels[(item.question, item.answer)]), examples)
    assert result["agreement_rate"] == 1.0 and result["disagreements"] == []
    assert result["overall_agreement"] == "10/10"


def test_calibrate_lenient_judge_shows_disagreements():
    examples = load_calibration()[0]
    result = calibrate(FakeJudge({}), examples)  # passes everything
    assert result["agreement_rate"] < 0.8
    assert result["overall_agreement"] == "3/10"  # only c01, c06, c09 are all-pass
    assert {d["id"] for d in result["disagreements"]} >= {
        "c02-negation-flip",
        "c08-missing-replaced-note",
    }
