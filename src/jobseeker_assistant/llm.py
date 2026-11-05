"""LLM providers behind one tiny interface, chosen by environment variables.

    LLM_PROVIDER = anthropic (default) | gemini | groq | fake
    LLM_MODEL    = model id (defaults below; check the provider's current model list)
    LLM_API_KEY  = the provider's key, only from the environment / .env (never committed)
                   (ANTHROPIC_API_KEY still works for anthropic)

Gemini and Groq both have free tiers. They are called over plain HTTPS with `requests`
(no extra SDK); the key goes in a request header, never in the URL, so it cannot end up in
logs or error messages. Rate-limit (429) and server errors are retried a few times.

Every provider records `last_usage` (tokens in/out) so the eval budget can count cost.
Tests always use FakeLLM, so CI never calls a real model.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-haiku-5-5"
# Defaults; model names change, so override with LLM_MODEL if one is retired.
# Gemini: picked 2026-11-05 from the list-models endpoint among stable (non-preview,
# non-"latest" alias) text Flash models with generateContent. The newest, gemini-3.8-flash,
# returned 503 "high demand" on every try that day, so the default is gemini-3.7-flash.
# "-latest" aliases are avoided on purpose: they move silently, so eval runs wouldn't compare.
DEFAULT_MODELS = {
    "anthropic": DEFAULT_MODEL,
    "gemini": "gemini-3.7-flash",
    "groq": "llama-3.3-70b-versatile",  # not checked against Groq's model list yet
}
# Cheaper option per provider: set LLM_MODEL to this to save quota or money.
CHEAPER_MODELS = {
    "gemini": "gemini-3.5-flash-lite",  # newest stable text Flash-Lite, 2026-11-05
}
PROVIDERS = (*DEFAULT_MODELS, "fake")
THINKING_LEVELS = ("minimal", "low", "medium", "high")
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0  # includes thinking tokens (they are billed as output)
    thinking_tokens: int = 0


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class ProviderError(RuntimeError):
    """A provider call failed for good (after retries). Never contains the API key."""


class FakeLLM:
    """Deterministic stand-in for a real model.

    - FakeLLM("fixed text") always returns that text.
    - FakeLLM(func) returns func(system, user), for tests that need to inspect the prompt.
    - FakeLLM() (no argument) is "extractive": it repeats the first sentence of source [S1]
      with a citation, or says NOT_COVERED when there are no sources. Handy for offline demos.
    """

    provider = "fake"
    model = "fake"

    def __init__(self, response: str | Callable[[str, str], str] | None = None):
        self.response = response
        self.calls: list[tuple[str, str]] = []
        self.last_usage = Usage()

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        self.last_usage = Usage(len(system + user) // 4, 50)  # rough: ~4 characters a token
        if callable(self.response):
            return self.response(system, user)
        if self.response is not None:
            return self.response
        m = re.search(r"\[S1\][^\n]*\n(.+?)(?:\n\n|\Z)", user, re.S)
        if not m:
            return "NOT_COVERED"
        first_sentence = re.split(r"(?<=[.!?])\s", m.group(1).strip(), maxsplit=1)[0]
        return f"{first_sentence} [S1]"


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, model: str, api_key: str, max_tokens: int = 800):
        import anthropic  # imported lazily so tests don't need the package configured

        self.model = model
        self.max_tokens = max_tokens
        self.last_usage = Usage()
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        self.last_usage = Usage(msg.usage.input_tokens, msg.usage.output_tokens)
        return "".join(block.text for block in msg.content if block.type == "text")


def _default_post(url: str, headers: dict, json: dict, timeout: float) -> Any:
    import requests

    return requests.post(url, headers=headers, json=json, timeout=timeout)


class _HttpLLM:
    """Shared HTTP plumbing: retries on 429/5xx (honouring Retry-After), clean errors."""

    provider = ""
    max_attempts = 3

    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = 800,
        post: Callable[..., Any] = _default_post,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 60.0,
    ):
        self.model, self.max_tokens = model, max_tokens
        self._key, self._post, self._sleep, self._timeout = api_key, post, sleep, timeout
        self.last_usage = Usage()

    def _call(self, url: str, headers: dict, payload: dict) -> dict:
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self._post(url, headers=headers, json=payload, timeout=self._timeout)
            except OSError as exc:  # timeouts / connection errors (requests' are OSErrors)
                if attempt < self.max_attempts:
                    self._sleep(2**attempt)
                    continue
                raise ProviderError(
                    f"{self.provider}: no response from model {self.model} after "
                    f"{self.max_attempts} attempts ({type(exc).__name__})"
                ) from exc
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in RETRY_STATUSES and attempt < self.max_attempts:
                retry_after = resp.headers.get("Retry-After", "")
                wait = (
                    float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2**attempt
                )
                self._sleep(min(wait, 60.0))
                continue
            detail = (resp.text or "")[:300]
            if len(self._key) >= 8:  # mask a real key; a 1-letter test key would mangle text
                detail = detail.replace(self._key, "***")
            raise ProviderError(
                f"{self.provider} returned HTTP {resp.status_code} for model {self.model}: {detail}"
            )
        raise ProviderError(f"{self.provider}: no response")  # pragma: no cover


def default_thinking_level(model: str) -> str:
    """Lowest thinking level each Gemini 3.x family accepts (checked 2026-11-05):
    Flash-Lite takes "minimal"; Flash rejects it ("MINIMAL is not supported"), so "low"."""
    return "minimal" if "flash-lite" in model else "low"


class GeminiLLM(_HttpLLM):
    """Google Gemini (free tier available) via the generateContent REST API.

    Gemini 2.5+ models "think" before answering, and thinking tokens count as (billed) output.
    To keep reasoning from eating the output cap, thinking is kept as small as the model allows:
    - Gemini 2.x: thinkingBudget = 0 (off);
    - Gemini 3.x: thinkingLevel (3.x rejects thinkingBudget with HTTP 400) — "minimal" for
      Flash-Lite, "low" for Flash; if a model rejects the level, retried once with "low".
    LLM_THINKING_LEVEL overrides the level for 3.x models.
    """

    provider = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model: str, api_key: str, thinking_level: str | None = None, **kw):
        super().__init__(model, api_key, **kw)
        self.thinking_level = thinking_level or default_thinking_level(model)

    def thinking_config(self) -> dict:
        if self.model.startswith("gemini-2."):
            return {"thinkingBudget": 0}
        return {"thinkingLevel": self.thinking_level}

    def _payload(self, system: str, user: str) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self.max_tokens,
                "thinkingConfig": self.thinking_config(),
            },
        }

    def complete(self, system: str, user: str) -> str:
        url = f"{self.base_url}/{self.model}:generateContent"
        headers = {"x-goog-api-key": self._key, "content-type": "application/json"}
        try:
            data = self._call(url, headers, self._payload(system, user))
        except ProviderError as exc:
            if "thinking level" not in str(exc).lower() or self.thinking_level == "low":
                raise
            self.thinking_level = "low"  # remembered for the next calls
            data = self._call(url, headers, self._payload(system, user))
        usage = data.get("usageMetadata", {})
        thoughts = usage.get("thoughtsTokenCount", 0)
        self.last_usage = Usage(
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0) + thoughts,  # thinking is billed as output
            thoughts,
        )
        candidates = data.get("candidates") or []
        if not candidates:  # e.g. blocked by a safety filter
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))


class GroqLLM(_HttpLLM):
    """Groq (free tier available) via its OpenAI-compatible chat completions API."""

    provider = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"

    def complete(self, system: str, user: str) -> str:
        data = self._call(
            self.url,
            {"authorization": f"Bearer {self._key}", "content-type": "application/json"},
            {
                "model": self.model,
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        usage = data.get("usage", {})
        self.last_usage = Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        choices = data.get("choices") or []
        return (choices[0].get("message", {}).get("content") or "") if choices else ""


def get_llm(env: dict[str, str] | None = None, prefix: str = "LLM") -> LLM:
    """Build the model from env. `prefix="JUDGE"` reads JUDGE_PROVIDER / JUDGE_MODEL /
    JUDGE_API_KEY instead, falling back to the LLM_* values."""
    env = dict(os.environ) if env is None else env

    def own(name: str) -> str:
        return env.get(f"{prefix}_{name}", "").strip() if prefix != "LLM" else ""

    base_provider = env.get("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    provider = (own("PROVIDER") or base_provider).lower()
    # LLM_MODEL / LLM_API_KEY belong to LLM_PROVIDER; borrow them only for the same provider.
    same = provider == base_provider
    if provider == "fake":
        return FakeLLM()
    if provider not in DEFAULT_MODELS:
        raise ValueError(
            f"Unknown {prefix}_PROVIDER '{provider}' (use one of {', '.join(PROVIDERS)})"
        )
    key = own("API_KEY") or (env.get("LLM_API_KEY", "").strip() if same else "")
    if not key and provider == "anthropic":
        key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        name = f"{prefix}_API_KEY" if prefix != "LLM" and not same else "LLM_API_KEY"
        hint = " (or ANTHROPIC_API_KEY)" if provider == "anthropic" else ""
        raise RuntimeError(
            f"{name}{hint} is not set for provider '{provider}'. Put it in .env "
            "(git-ignored), or use LLM_PROVIDER=fake for an offline demo."
        )
    model = own("MODEL") or (env.get("LLM_MODEL", "").strip() if same else "")
    model = model or DEFAULT_MODELS[provider]
    if provider == "anthropic":
        return AnthropicLLM(model=model, api_key=key)
    if provider == "gemini":
        level = own("THINKING_LEVEL") or (env.get("LLM_THINKING_LEVEL", "").strip() if same else "")
        if level and level not in THINKING_LEVELS:
            raise ValueError(f"thinking level must be one of {', '.join(THINKING_LEVELS)}")
        return GeminiLLM(model=model, api_key=key, thinking_level=level or None)
    return GroqLLM(model=model, api_key=key)
