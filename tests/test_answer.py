from jobseeker_assistant.answer import (
    DISCLAIMER,
    REFUSAL,
    answer_question,
    build_user_prompt,
)
from jobseeker_assistant.llm import FakeLLM

Q = "How long can a work trial last?"


def test_answer_with_valid_citation(fixture_index):
    llm = FakeLLM("A work trial lasts at most six months [S1].")
    ans = answer_question(Q, fixture_index, llm)
    assert not ans.refused
    assert ans.citations[0].url == "https://example.test/work-trial"
    assert ans.citations[0].section == "Duration"
    assert ans.citations[0].fetched_at.startswith("2026-11-03")


def test_prompt_contains_only_retrieved_sources(fixture_index):
    llm = FakeLLM("x [S1]")
    answer_question(Q, fixture_index, llm)
    system, user = llm.calls[0]
    assert "ONLY the numbered sources" in system
    assert "six months" in user and user.strip().endswith(Q)


def test_extractive_fake_end_to_end(fixture_index):
    ans = answer_question(Q, fixture_index, FakeLLM())
    assert not ans.refused
    assert "six months" in ans.text and "[S1]" in ans.text


def test_no_relevant_sources_refuses_without_calling_llm(fixture_index):
    llm = FakeLLM("should not be used [S1]")
    ans = answer_question("best pizza in Helsinki", fixture_index, llm)
    assert ans.refused and ans.text == REFUSAL
    assert llm.calls == []


def test_model_says_not_covered(fixture_index):
    ans = answer_question(Q, fixture_index, FakeLLM("NOT_COVERED"))
    assert ans.refused


def test_uncited_answer_is_refused(fixture_index):
    ans = answer_question(Q, fixture_index, FakeLLM("It lasts six months."))
    assert ans.refused


def test_invented_citation_is_refused(fixture_index):
    ans = answer_question(Q, fixture_index, FakeLLM("Six months [S9]."))
    assert ans.refused


def test_render_lists_sources_and_always_ends_with_disclaimer(fixture_index):
    ok = answer_question(Q, fixture_index, FakeLLM("Six months [S1]."))
    text = ok.render()
    assert "https://example.test/work-trial — section: Duration" in text
    assert text.endswith(DISCLAIMER)
    refused = answer_question("pizza", fixture_index, FakeLLM()).render()
    assert refused.startswith(REFUSAL) and refused.endswith(DISCLAIMER)


def test_build_user_prompt_numbers_sources(fixture_index):
    hits = fixture_index.search(Q, k=2)
    prompt = build_user_prompt(Q, hits)
    assert "[S1]" in prompt and "[S2]" in prompt and prompt.endswith(f"Question: {Q}")
