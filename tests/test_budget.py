import pytest

from jobseeker_assistant.budget import (
    Budget,
    BudgetExceeded,
    GuardedLLM,
    Prices,
    ResponseCache,
    estimate_cost,
    format_cost,
    max_calls_from_env,
    prices_for,
)
from jobseeker_assistant.llm import FakeLLM, Usage


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _guarded(tmp_path, max_calls=10, commit="abc123", **kw):
    budget = Budget(max_calls)
    llm = FakeLLM(lambda s, u: f"answer to {u}")
    guard = GuardedLLM(llm, budget, ResponseCache(tmp_path), commit, min_interval=0, **kw)
    return guard, budget, llm


def test_limit_aborts_cleanly_before_the_extra_call(tmp_path):
    guard, budget, llm = _guarded(tmp_path, max_calls=2)
    guard.complete("s", "q1")
    guard.complete("s", "q2")
    with pytest.raises(BudgetExceeded, match="limit reached \\(2\\)"):
        guard.complete("s", "q3")
    assert len(llm.calls) == 2 and budget.calls == 2


def test_cache_reuses_answers_for_same_commit_and_prompt(tmp_path):
    guard, budget, llm = _guarded(tmp_path)
    assert guard.complete("s", "q") == guard.complete("s", "q") == "answer to q"
    assert len(llm.calls) == 1 and budget.calls == 1 and budget.cache_hits == 1


def test_cache_misses_when_commit_or_prompt_changes(tmp_path):
    guard, _, llm = _guarded(tmp_path, commit="aaa")
    guard.complete("s", "q")
    guard.complete("s", "other question")
    other_commit, _, llm2 = _guarded(tmp_path, commit="bbb")
    other_commit.complete("s", "q")
    assert len(llm.calls) == 2 and len(llm2.calls) == 1


def test_cached_calls_do_not_count_against_the_limit(tmp_path):
    guard, budget, _ = _guarded(tmp_path, max_calls=1)
    guard.complete("s", "q")
    for _ in range(5):
        guard.complete("s", "q")  # all from cache
    assert budget.calls == 1 and budget.cache_hits == 5


def test_disabled_cache_never_stores(tmp_path):
    budget = Budget(10)
    llm = FakeLLM("x")
    guard = GuardedLLM(llm, budget, ResponseCache(tmp_path, enabled=False), "c", min_interval=0)
    guard.complete("s", "q")
    guard.complete("s", "q")
    assert len(llm.calls) == 2 and not list(tmp_path.iterdir())


def test_pacing_spaces_out_real_calls(tmp_path):
    clock, waits = Clock(), []
    budget = Budget(10)
    guard = GuardedLLM(
        FakeLLM("x"),
        budget,
        ResponseCache(tmp_path, enabled=False),
        "c",
        min_interval=6.0,
        clock=clock,
        sleep=waits.append,
    )
    guard.complete("s", "q1")
    clock.now = 2.0
    guard.complete("s", "q2")
    assert waits == [4.0]


def test_tokens_and_cost_are_counted(tmp_path):
    guard, budget, _ = _guarded(tmp_path, prices=Prices(1.0, 5.0))
    guard.complete("a" * 4000, "b" * 4000)  # fake reports 2000 in, 50 out
    assert budget.input_tokens == 2000 and budget.output_tokens == 50
    assert budget.cost == pytest.approx((2000 * 1.0 + 50 * 5.0) / 1e6)


def test_unknown_price_makes_cost_unknown(tmp_path):
    guard, budget, _ = _guarded(tmp_path, prices=Prices(None, None))
    guard.complete("s", "q")
    assert budget.cost is None and "unknown" in format_cost(budget.cost)


def test_prices_free_tiers_and_env():
    assert prices_for("gemini", {}) == Prices(0.0, 0.0) == prices_for("groq", {})
    assert not prices_for("anthropic", {}).known  # never hard-coded: prices change
    paid = prices_for(
        "anthropic", {"LLM_PRICE_INPUT_PER_MTOK": "1", "LLM_PRICE_OUTPUT_PER_MTOK": "5"}
    )
    assert paid == Prices(1.0, 5.0)


def test_estimate_and_format():
    assert estimate_cost(Prices(0.0, 0.0), 100) == 0.0
    assert format_cost(0.0) == "$0.0000"
    assert estimate_cost(Prices(None, None), 100) is None


def test_max_calls_from_env():
    assert max_calls_from_env({}) == 200
    assert max_calls_from_env({"EVAL_MAX_CALLS": "30"}) == 30
    with pytest.raises(ValueError):
        max_calls_from_env({"EVAL_MAX_CALLS": "0"})


def test_usage_passthrough(tmp_path):
    guard, _, _ = _guarded(tmp_path)
    guard.complete("s" * 40, "q")
    assert isinstance(guard.last_usage, Usage) and guard.last_usage.output_tokens == 50
