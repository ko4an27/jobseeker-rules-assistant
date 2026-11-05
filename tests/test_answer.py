from jobseeker_assistant.answer import (
    DISCLAIMER,
    REFUSAL,
    answer_question,
    build_user_prompt,
)
from jobseeker_assistant.llm import FakeLLM

Q = "What is the duration of a work trial?"


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


OLD_Q = "Can I get the old benefit?"


def test_historical_hit_brings_in_its_replacement(tagged_index):
    llm = FakeLLM("x [S1]")
    answer_question(OLD_Q, tagged_index, llm)
    _, user = llm.calls[0]
    assert "example.test/old-benefit" in user and "example.test/new-benefit" in user
    assert "[HISTORICAL: Old benefit was replaced by the new benefit on 1 May 2026.]" in user


def _label_of(user: str, url: str) -> str:
    return next(line for line in user.splitlines() if url in line).split("]")[0] + "]"


def test_citing_historical_and_replacement_is_accepted(tagged_index):
    def reply(system, user):
        old = _label_of(user, "old-benefit")
        new = _label_of(user, "new-benefit")
        return (
            f"You can get the old benefit if you are an unemployed jobseeker {old}. "
            f"The new benefit is paid to unemployed jobseekers {new}."
        )

    ans = answer_question(OLD_Q, tagged_index, FakeLLM(reply))
    assert not ans.refused
    assert {c.historical for c in ans.citations} == {True, False}
    assert "[historical]" in ans.render()


def test_citing_only_historical_page_adds_note_and_replacement(tagged_index):
    def reply(system, user):
        return f"You can get the old benefit {_label_of(user, 'old-benefit')}."

    ans = answer_question(OLD_Q, tagged_index, FakeLLM(reply))
    assert not ans.refused
    [note] = ans.added_notes
    labels = {c.url: c.label for c in ans.citations}
    old, new = (
        labels["https://example.test/old-benefit"],
        labels["https://example.test/new-benefit"],
    )
    assert (
        note == f"Note: Old benefit was replaced by the new benefit on 1 May 2026. [{old}][{new}]"
    )
    assert {c.url for c in ans.citations} == {
        "https://example.test/old-benefit",
        "https://example.test/new-benefit",
    }
    assert ans.text.endswith(ans.added_notes[0])


def test_note_added_once_even_if_model_cites_both(tagged_index):
    def reply(system, user):
        old, new = _label_of(user, "old-benefit"), _label_of(user, "new-benefit")
        return f"Old {old}{old}. New {new}."

    ans = answer_question(OLD_Q, tagged_index, FakeLLM(reply))
    assert len(ans.added_notes) == 1


def test_refuses_if_replacement_page_is_unavailable(tagged_index):
    # Index without the replacement page: the note can't be backed by a source.
    from jobseeker_assistant.retrieve import Index

    idx = Index([p for p in tagged_index.passages if "new-benefit" not in p.url])

    def reply(system, user):
        return f"You can get the old benefit {_label_of(user, 'old-benefit')}."

    assert answer_question(OLD_Q, idx, FakeLLM(reply)).refused


def test_historical_page_without_replacement_gets_plain_note():
    from jobseeker_assistant.answer import historical_notes
    from jobseeker_assistant.retrieve import Hit, Passage
    from jobseeker_assistant.source_tags import SourceTags

    p = Passage("id", "u", "t", "s", "x", "d", SourceTags(status="historical", note="Old news."))
    assert historical_notes([1], [Hit(p, 1.0)]) == (["Note: Old news. [S1]"], [])


def test_system_prompt_explains_historical_and_employer_labels():
    from jobseeker_assistant.answer import SYSTEM_PROMPT

    assert "HISTORICAL" in SYSTEM_PROMPT
    # The code adds the "replaced by" notes. Asking the model to comment on historical sources
    # made it write sentences ABOUT the sources, which the grounding check rightly rejects
    # (real eval 2026-11-05, reform-municipalities). The prompt must not ask for that.
    assert "cite both" not in SYSTEM_PROMPT
    assert "say clearly that it was replaced" not in SYSTEM_PROMPT
    assert "Do not write about the sources themselves" in SYSTEM_PROMPT
    assert "FOR EMPLOYERS" in SYSTEM_PROMPT and "jobseeker's point" in SYSTEM_PROMPT


def test_employer_pages_are_labelled(tagged_index):
    llm = FakeLLM("The employer applies before the job starts [S1].")
    ans = answer_question("Who applies for the pay subsidy?", tagged_index, llm)
    assert not ans.refused
    assert "[FOR EMPLOYERS]" in llm.calls[0][1]


def test_source_label_for_untagged_page(fixture_index):
    from jobseeker_assistant.answer import source_label

    assert source_label(fixture_index.search("work trial")[0]) == ""


def test_low_coverage_question_is_refused_without_calling_llm(fixture_index):
    llm = FakeLLM("should not be used [S1]")
    ans = answer_question("benefit pizza helsinki", fixture_index, llm)
    assert ans.refused and llm.calls == []


def test_min_coverage_can_be_lowered(fixture_index):
    ans = answer_question("benefit pizza helsinki", fixture_index, FakeLLM(), min_coverage=0.0)
    assert not ans.refused
