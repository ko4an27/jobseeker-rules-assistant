"""Optional Langfuse tracing. OFF by default.

    LANGFUSE_ENABLED=true        turn tracing on (anything else: off)
    LANGFUSE_PUBLIC_KEY=...      keys only from the environment / .env, never committed
    LANGFUSE_SECRET_KEY=...
    LANGFUSE_HOST=...            optional, e.g. https://cloud.langfuse.com
    LANGFUSE_LOG_TEXT=true       also send question and answer text (default: metadata only)

With tracing off, the langfuse package is not even imported, so nothing can be sent.
With tracing on, by default only metadata is sent (path through the graph, refusal reason,
attempts, cited URLs, latency, question length): a question may contain personal data,
so its text leaves the machine only if LANGFUSE_LOG_TEXT=true is set explicitly.
"""

from __future__ import annotations

import os
from typing import Any, Protocol


class Tracer(Protocol):
    enabled: bool

    def record_answer(self, question: str, answer: str, metadata: dict[str, Any]) -> None: ...


class NoopTracer:
    enabled = False

    def record_answer(self, question: str, answer: str, metadata: dict[str, Any]) -> None:
        return None


def _flag(env: dict[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


class LangfuseTracer:
    enabled = True

    def __init__(self, client: Any, log_text: bool = False):
        self.client = client
        self.log_text = log_text

    def record_answer(self, question: str, answer: str, metadata: dict[str, Any]) -> None:
        kwargs: dict[str, Any] = {"name": "ask", "metadata": metadata}
        if self.log_text:
            kwargs["input"] = {"question": question}
            kwargs["output"] = {"answer": answer}
        with self.client.start_as_current_span(**kwargs):
            pass


def get_tracer(env: dict[str, str] | None = None) -> Tracer:
    env = dict(os.environ) if env is None else env
    if not _flag(env, "LANGFUSE_ENABLED"):
        return NoopTracer()
    public, secret = env.get("LANGFUSE_PUBLIC_KEY", ""), env.get("LANGFUSE_SECRET_KEY", "")
    if not public or not secret:
        raise RuntimeError(
            "LANGFUSE_ENABLED=true but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set. "
            "Put them in .env (git-ignored) or turn tracing off."
        )
    from langfuse import Langfuse  # imported only when tracing is on

    client = Langfuse(public_key=public, secret_key=secret, host=env.get("LANGFUSE_HOST") or None)
    return LangfuseTracer(client, log_text=_flag(env, "LANGFUSE_LOG_TEXT"))
