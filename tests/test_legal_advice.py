import pytest

from jobseeker_assistant.answer import answer_question
from jobseeker_assistant.legal_advice import LEGAL_ADVICE_REFUSAL, detect
from jobseeker_assistant.llm import FakeLLM


@pytest.mark.parametrize(
    "question, rule",
    [
        ("Should I sue my old employer?", "should_i_take_legal_action"),
        ("should we take the landlord to court", "should_i_take_legal_action"),
        ("Can I sue Kela for a late payment?", "lawsuit"),
        ("Will I win if I appeal the decision?", "predict_outcome"),
        ("What are my chances in court?", "predict_outcome"),
        ("Will my appeal succeed?", "predict_outcome"),
        ("Is my employer's dismissal notice legal?", "is_my_situation_legal"),
        ("Was this decision about my benefit lawful?", "is_my_situation_legal"),
        ("I need legal advice about my contract", "asks_for_legal_advice"),
    ],
)
def test_personal_legal_advice_is_detected(question, rule):
    assert detect(question) == rule


@pytest.mark.parametrize(
    "question",
    [
        "How do I appeal a Kela decision?",  # how a process works: answer from sources
        "What happens if I refuse a job offer?",
        "Is the general social security benefit means-tested?",
        "How long can a work try-out last?",
        "Is it legal tender to pay in euros?",  # 'legal' alone is not enough
        "What is a court of appeal?",
        "When did employment services move to municipalities?",
    ],
)
def test_ordinary_questions_are_not_flagged(question):
    assert detect(question) is None


def test_legal_advice_is_refused_before_retrieval(fixture_index):
    # Even if the question shares many words with the sources, the rule refuses it.
    llm = FakeLLM("should not be called [S1]")
    ans = answer_question(
        "My work trial lasts six months. Should I sue the employment office?", fixture_index, llm
    )
    assert ans.refused and ans.text == LEGAL_ADVICE_REFUSAL
    assert ans.refusal_reason == "legal_advice:should_i_take_legal_action"
    assert llm.calls == [] and ans.hits == []


def test_refusal_reasons_are_recorded(fixture_index):
    assert answer_question("pizza", fixture_index, FakeLLM()).refusal_reason == "no_passages"
    ans = answer_question("benefit pizza helsinki", fixture_index, FakeLLM())
    assert ans.refusal_reason == "low_coverage"
    ans = answer_question("What is the duration of a work trial?", fixture_index, FakeLLM("x"))
    assert ans.refusal_reason == "no_or_invented_citation"
