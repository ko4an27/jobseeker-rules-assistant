"""Gemini / Groq providers, tested with a fake HTTP function: no network, no key needed."""

import pytest

from jobseeker_assistant.llm import (
    DEFAULT_MODELS,
    FakeLLM,
    GeminiLLM,
    GroqLLM,
    ProviderError,
    Usage,
    get_llm,
)


class Resp:
    def __init__(self, status, body=None, headers=None, text=""):
        self.status_code, self._body = status, body or {}
        self.headers, self.text = headers or {}, text

    def json(self):
        return self._body


class FakePost:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.responses.pop(0)


GEMINI_OK = Resp(
    200,
    {
        "candidates": [{"content": {"parts": [{"text": "Six months "}, {"text": "[S1]."}]}}],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 8},
    },
)
GROQ_OK = Resp(
    200,
    {
        "choices": [{"message": {"content": "Six months [S1]."}}],
        "usage": {"prompt_tokens": 110, "completion_tokens": 7},
    },
)


def test_gemini_request_and_response():
    post = FakePost(GEMINI_OK)
    llm = GeminiLLM("gemini-test", "secret-key", post=post, sleep=lambda s: None)
    assert llm.complete("SYSTEM", "USER") == "Six months [S1]."
    call = post.calls[0]
    assert call["url"].endswith("/models/gemini-test:generateContent")
    assert "secret-key" not in call["url"]  # key in a header, never in the URL
    assert call["headers"]["x-goog-api-key"] == "secret-key"
    assert call["json"]["systemInstruction"]["parts"][0]["text"] == "SYSTEM"
    assert call["json"]["contents"][0]["parts"][0]["text"] == "USER"
    assert call["json"]["generationConfig"]["temperature"] == 0
    assert llm.last_usage == Usage(120, 8)


@pytest.mark.parametrize(
    "model, config",
    [
        ("gemini-3.7-flash", {"thinkingLevel": "low"}),  # Flash rejects "minimal"
        ("gemini-3.5-flash-lite", {"thinkingLevel": "minimal"}),
        ("gemini-2.5-flash", {"thinkingBudget": 0}),  # 2.x: budget, not level
    ],
)
def test_gemini_keeps_thinking_as_small_as_the_model_allows(model, config):
    post = FakePost(GEMINI_OK)
    GeminiLLM(model, "k", post=post, sleep=lambda s: None).complete("s", "u")
    assert post.calls[0]["json"]["generationConfig"]["thinkingConfig"] == config


def test_gemini_falls_back_to_low_when_minimal_is_rejected():
    rejected = Resp(400, text="Thinking level MINIMAL is not supported for this model.")
    post = FakePost(rejected, GEMINI_OK, GEMINI_OK)
    llm = GeminiLLM("gemini-x-flash-lite", "k", post=post, sleep=lambda s: None)
    assert llm.complete("s", "u") == "Six months [S1]."
    levels = [c["json"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] for c in post.calls]
    assert levels == ["minimal", "low"]
    llm.complete("s", "u")  # remembered: no second rejected call
    assert post.calls[-1]["json"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"


def test_gemini_other_400s_are_not_retried_with_low():
    post = FakePost(Resp(400, text="Request contains an invalid argument."))
    with pytest.raises(ProviderError, match="HTTP 400"):
        GeminiLLM("gemini-3.5-flash-lite", "k", post=post, sleep=lambda s: None).complete("s", "u")
    assert len(post.calls) == 1


def test_gemini_drops_thought_parts_and_bills_thinking_tokens():
    body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Let me think...", "thought": True},
                        {"text": "Six months [S1]."},
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 8,
            "thoughtsTokenCount": 40,
        },
    }
    llm = GeminiLLM("gemini-3.7-flash", "k", post=FakePost(Resp(200, body)), sleep=lambda s: None)
    assert llm.complete("s", "u") == "Six months [S1]."
    assert llm.last_usage == Usage(100, 48, 40)


def test_thinking_level_from_env():
    llm = get_llm({"LLM_PROVIDER": "gemini", "LLM_API_KEY": "k", "LLM_THINKING_LEVEL": "medium"})
    assert llm.thinking_level == "medium"
    with pytest.raises(ValueError, match="thinking level"):
        get_llm({"LLM_PROVIDER": "gemini", "LLM_API_KEY": "k", "LLM_THINKING_LEVEL": "max"})


def test_gemini_blocked_answer_is_empty_not_a_crash():
    llm = GeminiLLM("m", "k", post=FakePost(Resp(200, {"candidates": []})), sleep=lambda s: None)
    assert llm.complete("s", "u") == ""


def test_groq_request_and_response():
    post = FakePost(GROQ_OK)
    llm = GroqLLM("llama-test", "secret-key", post=post, sleep=lambda s: None)
    assert llm.complete("SYSTEM", "USER") == "Six months [S1]."
    call = post.calls[0]
    assert call["headers"]["authorization"] == "Bearer secret-key"
    assert call["json"]["model"] == "llama-test"
    assert call["json"]["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER"},
    ]
    assert llm.last_usage == Usage(110, 7)


def test_rate_limit_is_retried_with_retry_after():
    waits = []
    post = FakePost(Resp(429, headers={"Retry-After": "3"}), Resp(503), GROQ_OK)
    llm = GroqLLM("m", "k", post=post, sleep=waits.append)
    assert llm.complete("s", "u") == "Six months [S1]."
    assert waits == [3.0, 4.0]  # Retry-After, then exponential backoff (2**2)


def test_gives_up_after_three_attempts_without_leaking_the_key():
    post = FakePost(*[Resp(429, text="quota for key secret-key exceeded")] * 3)
    llm = GroqLLM("m", "secret-key", post=post, sleep=lambda s: None)
    with pytest.raises(ProviderError) as err:
        llm.complete("s", "u")
    assert "HTTP 429" in str(err.value) and "secret-key" not in str(err.value)
    assert len(post.calls) == 3


def test_client_errors_are_not_retried():
    post = FakePost(Resp(400, text="bad model"))
    with pytest.raises(ProviderError, match="HTTP 400"):
        GeminiLLM("m", "k", post=post, sleep=lambda s: None).complete("s", "u")
    assert len(post.calls) == 1


@pytest.mark.parametrize("provider, cls", [("gemini", GeminiLLM), ("groq", GroqLLM)])
def test_get_llm_builds_free_tier_providers(provider, cls):
    llm = get_llm({"LLM_PROVIDER": provider, "LLM_API_KEY": "k"})
    assert isinstance(llm, cls) and llm.model == DEFAULT_MODELS[provider]
    custom = get_llm({"LLM_PROVIDER": provider, "LLM_API_KEY": "k", "LLM_MODEL": "x"})
    assert custom.model == "x"


def test_get_llm_needs_a_key_for_real_providers():
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        get_llm({"LLM_PROVIDER": "groq"})


def test_judge_settings_fall_back_to_llm_settings_for_the_same_provider():
    env = {"LLM_PROVIDER": "groq", "LLM_API_KEY": "k", "LLM_MODEL": "m1"}
    judge = get_llm(env, prefix="JUDGE")
    assert isinstance(judge, GroqLLM) and judge.model == "m1"


def test_judge_with_other_provider_does_not_borrow_key_or_model():
    env = {
        "LLM_PROVIDER": "groq",
        "LLM_API_KEY": "groq-key",
        "LLM_MODEL": "llama",
        "JUDGE_PROVIDER": "gemini",
    }
    with pytest.raises(RuntimeError, match="JUDGE_API_KEY"):
        get_llm(env, prefix="JUDGE")
    judge = get_llm({**env, "JUDGE_API_KEY": "g-key"}, prefix="JUDGE")
    assert isinstance(judge, GeminiLLM) and judge.model == DEFAULT_MODELS["gemini"]


def test_fake_llm_reports_rough_usage():
    llm = FakeLLM("x")
    llm.complete("a" * 40, "b" * 40)
    assert llm.last_usage.input_tokens == 20


def test_network_timeouts_are_retried_then_become_provider_errors():
    import requests

    calls = []

    def post(url, headers, json, timeout):
        calls.append(1)
        raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=60.0)")

    waits = []
    llm = GeminiLLM("gemini-3.7-flash", "secret-key-123", post=post, sleep=waits.append)
    with pytest.raises(ProviderError, match="no response from model gemini-3.7-flash") as err:
        llm.complete("s", "u")
    assert len(calls) == 3 and waits == [2, 4]
    assert "secret-key-123" not in str(err.value)


def test_a_timeout_then_success_recovers():
    import requests

    replies = [requests.exceptions.ConnectionError("reset"), GEMINI_OK]

    def post(url, headers, json, timeout):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    llm = GeminiLLM("gemini-3.7-flash", "k", post=post, sleep=lambda s: None)
    assert llm.complete("s", "u") == "Six months [S1]."
