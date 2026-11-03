import pytest

from jobseeker_assistant.llm import DEFAULT_MODEL, FakeLLM, get_llm


def test_fake_llm_fixed_and_callable():
    assert FakeLLM("hi").complete("s", "u") == "hi"
    fake = FakeLLM(lambda s, u: u.upper())
    assert fake.complete("s", "abc") == "ABC"
    assert fake.calls == [("s", "abc")]


def test_fake_llm_extractive_default():
    user = "Sources:\n\n[S1] T — Sec (https://x.test)\nFirst fact. Second fact.\n\nQuestion: q"
    assert FakeLLM().complete("s", user) == "First fact. [S1]"
    assert FakeLLM().complete("s", "Question: q") == "NOT_COVERED"


def test_get_llm_fake_needs_no_key():
    assert isinstance(get_llm({"LLM_PROVIDER": "fake"}), FakeLLM)


def test_get_llm_anthropic_without_key_gives_clear_error():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_llm({"LLM_PROVIDER": "anthropic"})


def test_get_llm_default_provider_is_anthropic():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_llm({})


def test_get_llm_unknown_provider():
    with pytest.raises(ValueError):
        get_llm({"LLM_PROVIDER": "nope"})


def test_get_llm_anthropic_builds_client_with_model(monkeypatch):
    import jobseeker_assistant.llm as llm_mod

    captured = {}

    class Stub:
        def __init__(self, model, api_key):
            captured.update(model=model, api_key=api_key)

    monkeypatch.setattr(llm_mod, "AnthropicLLM", Stub)
    get_llm({"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k"})
    assert captured == {"model": DEFAULT_MODEL, "api_key": "k"}
