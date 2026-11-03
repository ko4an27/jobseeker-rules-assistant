"""LLM providers behind one tiny interface, chosen by environment variables.

    LLM_PROVIDER = anthropic (default) | fake
    LLM_MODEL    = model id (default: a cheap model for development)
    ANTHROPIC_API_KEY = secret, only from the environment / .env (never committed)

Tests always use FakeLLM, so CI never calls a real model.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Protocol

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-haiku-5-5"


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class FakeLLM:
    """Deterministic stand-in for a real model.

    - FakeLLM("fixed text") always returns that text.
    - FakeLLM(func) returns func(system, user), for tests that need to inspect the prompt.
    - FakeLLM() (no argument) is "extractive": it repeats the first sentence of source [S1]
      with a citation, or says NOT_COVERED when there are no sources. Handy for offline demos.
    """

    def __init__(self, response: str | Callable[[str, str], str] | None = None):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
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
    def __init__(self, model: str, api_key: str, max_tokens: int = 800):
        import anthropic  # imported lazily so tests don't need the package configured

        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")


def get_llm(env: dict[str, str] | None = None) -> LLM:
    env = dict(os.environ) if env is None else env
    provider = env.get("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if provider == "fake":
        return FakeLLM()
    if provider == "anthropic":
        key = env.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Put it in .env (git-ignored), "
                "or use LLM_PROVIDER=fake for an offline demo."
            )
        return AnthropicLLM(model=env.get("LLM_MODEL", DEFAULT_MODEL), api_key=key)
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}' (use 'anthropic' or 'fake')")
