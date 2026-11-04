"""Graph-level tests: one per path through the LangGraph flow, all with the fake LLM."""

from jobseeker_assistant.graph import STRICT_SYSTEM_PROMPT, run_graph
from jobseeker_assistant.llm import FakeLLM
from jobseeker_assistant.retrieve import Index

Q = "What is the duration of a work trial?"
GOOD = "A work trial lasts at most six months [S1]."
BAD = "A work trial lasts 12 months and pays a bonus [S1]."  # 12 and 'bonus' not in source


def _path(*middle):
    return ["legal_check", "retrieve", "coverage_gate", *middle]


def test_answer_path(fixture_index):
    llm = FakeLLM(GOOD)
    ans, path = run_graph(Q, fixture_index, llm)
    assert path == _path("generate", "check_grounding", "finalize")
    assert not ans.refused and ans.attempts == 1 and len(llm.calls) == 1
    assert ans.citations[0].url == "https://example.test/work-trial"


def test_retry_path_then_answer(fixture_index):
    replies = iter([BAD, GOOD])
    llm = FakeLLM(lambda system, user: next(replies))
    ans, path = run_graph(Q, fixture_index, llm)
    assert path == _path(
        "generate", "check_grounding", "generate_strict", "check_grounding", "finalize"
    )
    assert not ans.refused and ans.attempts == 2 and ans.text == GOOD
    strict_system, strict_user = llm.calls[1]
    assert strict_system == STRICT_SYSTEM_PROMPT
    assert "12 months and pays a bonus" in strict_user  # the model is told what failed
    assert "number 12 not in source" in strict_user


def test_retry_path_then_refuse(fixture_index):
    llm = FakeLLM(BAD)
    ans, path = run_graph(Q, fixture_index, llm)
    assert path == _path(
        "generate", "check_grounding", "generate_strict", "check_grounding", "refuse"
    )
    assert ans.refused and ans.refusal_reason == "not_grounded"
    assert len(llm.calls) == 2  # exactly one retry, never more


def test_legal_advice_refuses_first(fixture_index):
    llm = FakeLLM(GOOD)
    ans, path = run_graph("My work trial ended. Should I sue them?", fixture_index, llm)
    assert path == ["legal_check", "refuse"]
    assert ans.refusal_reason.startswith("legal_advice") and llm.calls == []


def test_no_passages_refuses_before_llm(fixture_index):
    llm = FakeLLM(GOOD)
    ans, path = run_graph("pizza", fixture_index, llm)
    assert path == ["legal_check", "retrieve", "refuse"]
    assert ans.refusal_reason == "no_passages" and llm.calls == []


def test_low_coverage_refuses_before_llm(fixture_index):
    llm = FakeLLM(GOOD)
    ans, path = run_graph("benefit pizza helsinki", fixture_index, llm)
    assert path == _path("refuse")
    assert ans.refusal_reason == "low_coverage" and llm.calls == []


def test_not_covered_refuses_without_retry(fixture_index):
    llm = FakeLLM("NOT_COVERED")
    ans, path = run_graph(Q, fixture_index, llm)
    assert path == _path("generate", "refuse")
    assert ans.refusal_reason == "not_covered" and len(llm.calls) == 1


def test_historical_page_without_replacement_refuses_in_finalize(tagged_index):
    idx = Index([p for p in tagged_index.passages if "new-benefit" not in p.url])

    def reply(system, user):
        label = next(line for line in user.splitlines() if "old-benefit" in line).split("]")[0]
        return f"You can get the old benefit if you are an unemployed jobseeker {label}]."

    ans, path = run_graph("Can I get the old benefit?", idx, FakeLLM(reply))
    assert path == _path("generate", "check_grounding", "finalize", "refuse")
    assert ans.refusal_reason == "replacement_unavailable"


def test_extractive_fake_is_grounded_on_real_snapshots():
    """The offline demo model quotes its source, so it must always pass the self-check."""
    from jobseeker_assistant import snapshots
    from jobseeker_assistant.source_tags import load_tags

    idx = Index.from_snapshots(snapshots.load_all(), load_tags())
    ans, path = run_graph("How long can a work try-out last?", idx, FakeLLM())
    assert "generate_strict" not in path and not ans.refused
