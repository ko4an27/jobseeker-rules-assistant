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
# Defaults chosen 2026-11; model names change, so override with LLM_MODEL if one is retired.
DEFAULT_MODELS = {
    "anthropic": DEFAULT_MODEL,
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
}
PROVIDERS = (*DEFAULT_MODELS, "fake")
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


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
            resp = self._post(url, headers=headers, json=payload, timeout=self._timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in RETRY_STATUSES and attempt < self.max_attempts:
                retry_after = resp.headers.get("Retry-After", "")
                wait = (
                    float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2**attempt
                )
                self._sleep(min(wait, 60.0))
                continue
            detail = (resp.text or "")[:300].replace(self._key, "***") if self._key else ""
            raise ProviderError(
                f"{self.provider} returned HTTP {resp.status_code} for model {self.model}: {detail}"
            )
        raise ProviderError(f"{self.provider}: no response")  # pragma: no cover


class GeminiLLM(_HttpLLM):
    """Google Gemini (free tier available) via the generateContent REST API."""

    provider = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def complete(self, system: str, user: str) -> str:
        data = self._call(
            f"{self.base_url}/{self.model}:generateContent",
            {"x-goog-api-key": self._key, "content-type": "application/json"},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": self.max_tokens},
            },
        )
        usage = data.get("usageMetadata", {})
        self.last_usage = Usage(
            usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
        )
        candidates = data.get("candidates") or []
        if not candidates:  # e.g. blocked by a safety filter
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts)


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
        return GeminiLLM(model=model, api_key=key)
    return GroqLLM(model=model, api_key=key)
