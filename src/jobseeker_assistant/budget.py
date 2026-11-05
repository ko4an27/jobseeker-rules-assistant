"""Cost and limits guard for runs against a real model (make eval-real, make judge-calibrate).

    EVAL_MAX_CALLS=200                 at most this many real model calls per run
    LLM_PRICE_INPUT_PER_MTOK=...       price per million input tokens (paid providers)
    LLM_PRICE_OUTPUT_PER_MTOK=...      price per million output tokens

- Cache: a response is stored under (commit, provider, model, full prompt). The same question
  on the same code and model reuses it for free; any code, model or prompt change asks again.
  The cache is off for uncommitted code ("+dirty"), where a stale answer could hide a change.
- Limit: when the next real call would exceed EVAL_MAX_CALLS, BudgetExceeded is raised and the
  run stops cleanly (the eval saves what it has, marked as aborted).
- Cost: free tiers (gemini, groq) count as 0. Paid prices are NOT hard-coded (they change):
  set the two price variables, otherwise the cost is reported as unknown.
- Pacing: free tiers allow few requests per minute, so calls are spaced out per provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LLM, Usage

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "evals" / ".cache"
DEFAULT_MAX_CALLS = 200
FREE_TIER = {"gemini", "groq", "fake"}
# Seconds between real calls, to stay under free-tier requests-per-minute limits.
MIN_INTERVAL = {"gemini": 6.0, "groq": 2.0}
# Rough size of one call, for the up-front estimate only.
EST_INPUT_TOKENS, EST_OUTPUT_TOKENS = 3000, 300


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Prices:
    input_per_mtok: float | None
    output_per_mtok: float | None

    @property
    def known(self) -> bool:
        return self.input_per_mtok is not None and self.output_per_mtok is not None

    def cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if not self.known:
            return None
        return (input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok) / 1e6


def prices_for(provider: str, env: dict[str, str] | None = None) -> Prices:
    env = dict(os.environ) if env is None else env
    if provider in FREE_TIER:
        return Prices(0.0, 0.0)
    raw_in = env.get("LLM_PRICE_INPUT_PER_MTOK", "").strip()
    raw_out = env.get("LLM_PRICE_OUTPUT_PER_MTOK", "").strip()
    return Prices(float(raw_in) if raw_in else None, float(raw_out) if raw_out else None)


def max_calls_from_env(env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    raw = env.get("EVAL_MAX_CALLS", "").strip()
    value = int(raw) if raw else DEFAULT_MAX_CALLS
    if value < 1:
        raise ValueError("EVAL_MAX_CALLS must be at least 1")
    return value


@dataclass
class Budget:
    """Shared by every guarded model in one run (answering model and judge)."""

    max_calls: int
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = 0.0
    by_role: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "max_calls": self.max_calls,
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "calls_by_role": dict(self.by_role),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": None if self.cost is None else round(self.cost, 4),
        }


def estimate_cost(prices: Prices, calls: int) -> float | None:
    return prices.cost(calls * EST_INPUT_TOKENS, calls * EST_OUTPUT_TOKENS)


def format_cost(cost: float | None) -> str:
    if cost is None:
        return "unknown (set LLM_PRICE_INPUT_PER_MTOK and LLM_PRICE_OUTPUT_PER_MTOK)"
    return f"${cost:.4f}"


class ResponseCache:
    def __init__(self, directory: Path = CACHE_DIR, enabled: bool = True):
        self.directory, self.enabled = directory, enabled

    @staticmethod
    def key(commit: str, provider: str, model: str, system: str, user: str) -> str:
        blob = json.dumps([commit, provider, model, system, user], ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> str | None:
        path = self.directory / f"{key}.json"
        if not self.enabled or not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def put(self, key: str, response: str) -> None:
        if not self.enabled:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        path.write_text(json.dumps({"response": response}, ensure_ascii=False), encoding="utf-8")


class GuardedLLM:
    """Wraps a model: cache first, then the call limit, pacing, usage and cost."""

    def __init__(
        self,
        inner: LLM,
        budget: Budget,
        cache: ResponseCache,
        commit: str,
        role: str = "answer",
        prices: Prices | None = None,
        min_interval: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.inner, self.budget, self.cache, self.commit, self.role = (
            inner,
            budget,
            cache,
            commit,
            role,
        )
        self.provider = getattr(inner, "provider", "unknown")
        self.model = getattr(inner, "model", "unknown")
        self.prices = prices or prices_for(self.provider)
        self.min_interval = (
            MIN_INTERVAL.get(self.provider, 0.0) if min_interval is None else min_interval
        )
        self._clock, self._sleep = clock, sleep
        self._last_call: float | None = None
        self.last_usage = Usage()

    def complete(self, system: str, user: str) -> str:
        key = ResponseCache.key(self.commit, self.provider, self.model, system, user)
        cached = self.cache.get(key)
        if cached is not None:
            self.budget.cache_hits += 1
            return cached
        if self.budget.calls >= self.budget.max_calls:
            raise BudgetExceeded(
                f"model call limit reached ({self.budget.max_calls}); raise EVAL_MAX_CALLS "
                "or rerun: answers already received are cached"
            )
        if self._last_call is not None and self.min_interval:
            wait = self.min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        response = self.inner.complete(system, user)
        self._last_call = self._clock()
        self.budget.calls += 1
        self.budget.by_role[self.role] = self.budget.by_role.get(self.role, 0) + 1
        usage = getattr(self.inner, "last_usage", Usage())
        self.last_usage = usage
        self.budget.input_tokens += usage.input_tokens
        self.budget.output_tokens += usage.output_tokens
        cost = self.prices.cost(usage.input_tokens, usage.output_tokens)
        self.budget.cost = (
            None if cost is None or self.budget.cost is None else self.budget.cost + cost
        )
        self.cache.put(key, response)
        return response
