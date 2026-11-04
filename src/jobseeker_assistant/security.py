"""Rate limit and optional API key for POST /ask.

    RATE_LIMIT_PER_MINUTE=10   requests per client per minute (0 turns the limit off)
    API_KEY=...                if set, /ask needs header `X-API-Key: <key>`; unset = no key

The rate limit is in memory, per process, keyed by the client's address: enough for one
small server, not for several replicas behind a load balancer (that needs a shared store).
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

DEFAULT_RATE_LIMIT = 10
WINDOW_SECONDS = 60.0


class RateLimiter:
    """Sliding window: at most `limit` requests per `window` seconds per client."""

    def __init__(
        self,
        limit: int = DEFAULT_RATE_LIMIT,
        window: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str) -> float:
        """0 if the request may go ahead (and counts it); else seconds until it may."""
        if self.limit <= 0:
            return 0.0
        now = self.clock()
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
            return 0.0


def rate_limit_from_env(env: dict[str, str] | None = None) -> int:
    env = dict(os.environ) if env is None else env
    raw = env.get("RATE_LIMIT_PER_MINUTE", "").strip()
    if not raw:
        return DEFAULT_RATE_LIMIT
    value = int(raw)
    if value < 0:
        raise ValueError("RATE_LIMIT_PER_MINUTE must be 0 or more")
    return value


def api_key_from_env(env: dict[str, str] | None = None) -> str:
    env = dict(os.environ) if env is None else env
    return env.get("API_KEY", "").strip()


def key_ok(expected: str, given: str | None) -> bool:
    """True if no key is configured, or the given key matches (constant-time compare)."""
    if not expected:
        return True
    return given is not None and hmac.compare_digest(expected.encode(), given.encode())
