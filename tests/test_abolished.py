"""Abolished benefits named in the question always get the checked, cited note."""

import pytest

from jobseeker_assistant import snapshots
from jobseeker_assistant.abolished import (
    Abolished,
    load_abolished,
    mentioned,
    parse_abolished,
)
from jobseeker_assistant.graph import run_graph
from jobseeker_assistant.grounding import check_claim
from jobseeker_assistant.llm import FakeLLM
from jobseeker_assistant.retrieve import Index
from jobseeker_assistant.source_tags import load_tags

# Fixture world: the "old benefit" was replaced; the new-benefit page states it.
OLD = Abolished(
    name="old benefit",
    mentioned_as=("old benefit", "vanhatuki"),
    note="The new benefit is paid to unemployed jobseekers who are not entitled to "
    "earnings-related allowance.",
    cite="https://example.test/new-benefit",
    old_page="https://example.test/old-benefit",
)


@pytest.fixture(scope="module")
def real_index():
    return Index.from_snapshots(snapshots.load_all(), load_tags())


def test_mentioned_matches_whole_words_case_insensitive():
    assert mentioned("Is VANHATUKI still paid?", [OLD]) == [OLD]
    assert mentioned("Tell me about the old benefits", [OLD]) == []  # "benefits" != "benefit"
    assert mentioned("How long is a work trial?", [OLD]) == []


def test_parse_abolished_rejects_bad_entries():
    with pytest.raises(ValueError, match="unknown"):
        parse_abolished(
            {
                "abolished": [
                    {"name": "x", "mentioned_as": ["x"], "note": "n", "cite": "u", "colour": 1}
                ]
            }
        )
    with pytest.raises(ValueError, match="needs"):
        parse_abolished(
            {"abolished": [{"name": "x", "mentioned_as": [], "note": "n", "cite": "u"}]}
        )


def test_note_added_even_when_only_current_pages_are_cited(tagged_index):
    # The model answers from the NEW page only; the question names the old benefit.
    def reply(system, user):
        label = next(line for line in user.splitlines() if "new-benefit" in line).split("]")[0]
        return f"The new benefit is paid to unemployed jobseekers {label}]."

    ans, path = run_graph(
        "Is the old benefit still paid to jobseekers?",
        tagged_index,
        FakeLLM(reply),
        abolished=[OLD],
    )
    assert path[-1] == "finalize" and not ans.refused
    [note] = [n for n in ans.added_notes if "new benefit is paid" in n]
    assert "https://example.test/new-benefit" in {c.url for c in ans.citations}
    assert ans.text.endswith(note)


def test_note_only_answer_instead_of_refusal(tagged_index):
    # The model says NOT_COVERED, but the question names the old benefit.
    ans, path = run_graph(
        "Is vanhatuki still paid?", tagged_index, FakeLLM("NOT_COVERED"), abolished=[OLD]
    )
    assert path[-1] == "note_only" and not ans.refused
    assert ans.text.startswith("Note: The new benefit is paid")
    assert ans.citations and ans.citations[0].url == "https://example.test/new-benefit"


def test_legal_advice_is_never_turned_into_a_note(tagged_index):
    ans, path = run_graph(
        "Should I sue them over the old benefit?", tagged_index, FakeLLM(), abolished=[OLD]
    )
    assert path == ["legal_check", "refuse"] and ans.refused


def test_unsupported_note_is_never_added(tagged_index):
    bad = Abolished(
        "old benefit",
        ("old benefit",),
        "The old benefit ended in 1999.",
        "https://example.test/new-benefit",
    )
    ans, path = run_graph(
        "Is the old benefit still paid?", tagged_index, FakeLLM("NOT_COVERED"), abolished=[bad]
    )
    assert path[-2:] == ["note_only", "refuse"] and ans.refused  # 1999 not in the source


def test_no_note_when_cite_page_missing(fixture_index):
    ans, path = run_graph(
        "Is vanhatuki still paid?", fixture_index, FakeLLM("NOT_COVERED"), abolished=[OLD]
    )
    assert path[-1] == "refuse" and ans.refused


# --- Real data -------------------------------------------------------------------------


def test_every_real_note_is_backed_by_its_cited_page(real_index):
    for e in load_abolished():
        support = real_index.best_from_url(e.cite, e.note)
        assert support is not None, f"{e.name}: no snapshot for {e.cite}"
        check = check_claim(f"{e.note} [S1]", [support])
        assert check.supported, f"{e.name}: note not supported by {e.cite} ({check.reason})"


def test_real_notes_say_when_it_changed():
    dates = {e.name: e.note for e in load_abolished()}
    assert "1 May 2026" in dates["labour market subsidy"]
    assert "1 May 2026" in dates["basic unemployment allowance"]
    assert "1 January 2025" in dates["TE Office"]


@pytest.mark.parametrize(
    "question, name",
    [
        ("Can I still apply for labour market subsidy?", "labour market subsidy"),
        ("Is työmarkkinatuki still paid?", "labour market subsidy"),
        ("What happened to peruspäiväraha?", "basic unemployment allowance"),
        ("How much is the basic unemployment allowance per day?", "basic unemployment allowance"),
        ("Where is my nearest TE office?", "TE Office"),
    ],
)
def test_real_questions_always_end_with_the_note(real_index, question, name):
    entry = next(e for e in load_abolished() if e.name == name)
    ans, _ = run_graph(question, real_index, FakeLLM())
    assert not ans.refused
    assert any(entry.note in n for n in ans.added_notes)
    assert entry.cite in {c.url for c in ans.citations}


def test_te_office_question_gets_one_note_not_two(real_index):
    ans, _ = run_graph("Where is my nearest TE office?", real_index, FakeLLM())
    assert len([n for n in ans.added_notes if "TE" in n]) == 1
