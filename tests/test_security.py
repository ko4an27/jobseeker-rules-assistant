import pytest
from fastapi.testclient import TestClient

from jobseeker_assistant.api import Resources, create_app
from jobseeker_assistant.llm import FakeLLM
from jobseeker_assistant.security import (
    DEFAULT_RATE_LIMIT,
    RateLimiter,
    api_key_from_env,
    key_ok,
    rate_limit_from_env,
)
from jobseeker_assistant.tracing import NoopTracer

Q = {"question": "What is the duration of a work trial?"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _client(index, limiter=None, api_key=""):
    res = Resources(index, FakeLLM(), [], NoopTracer(), snapshot_count=2)
    return TestClient(create_app(res, limiter or RateLimiter(limit=100), api_key=api_key))


# --- Rate limiter ---------------------------------------------------------------------


def test_rate_limiter_allows_limit_then_blocks_until_window_passes():
    clock = Clock()
    rl = RateLimiter(limit=3, window=60, clock=clock)
    assert [rl.check("a") for _ in range(3)] == [0, 0, 0]
    assert rl.check("a") == pytest.approx(60)
    clock.now += 30
    assert rl.check("a") == pytest.approx(30)
    clock.now += 30.01
    assert rl.check("a") == 0  # the oldest request left the window


def test_rate_limiter_is_per_client():
    rl = RateLimiter(limit=1, clock=Clock())
    assert rl.check("a") == 0 and rl.check("a") > 0
    assert rl.check("b") == 0


def test_rate_limit_zero_means_off():
    rl = RateLimiter(limit=0, clock=Clock())
    assert all(rl.check("a") == 0 for _ in range(1000))


def test_rate_limit_from_env():
    assert rate_limit_from_env({}) == DEFAULT_RATE_LIMIT == 10
    assert rate_limit_from_env({"RATE_LIMIT_PER_MINUTE": "25"}) == 25
    with pytest.raises(ValueError):
        rate_limit_from_env({"RATE_LIMIT_PER_MINUTE": "-1"})


def test_ask_returns_429_with_retry_after(fixture_index):
    client = _client(fixture_index, RateLimiter(limit=10, clock=Clock()))
    codes = [client.post("/ask", json=Q).status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]
    r = client.post("/ask", json=Q)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"


def test_health_is_not_rate_limited(fixture_index):
    client = _client(fixture_index, RateLimiter(limit=1, clock=Clock()))
    assert all(client.get("/health").status_code == 200 for _ in range(5))


# --- API key --------------------------------------------------------------------------


def test_key_ok():
    assert key_ok("", None) and key_ok("", "anything")  # no key configured
    assert key_ok("s3cret", "s3cret")
    assert not key_ok("s3cret", None) and not key_ok("s3cret", "wrong")


def test_api_key_off_by_default():
    assert api_key_from_env({}) == ""


def test_ask_without_key_when_not_configured(fixture_index):
    assert _client(fixture_index).post("/ask", json=Q).status_code == 200


def test_ask_requires_key_when_configured(fixture_index):
    client = _client(fixture_index, api_key="s3cret")
    assert client.post("/ask", json=Q).status_code == 401
    assert client.post("/ask", json=Q, headers={"X-API-Key": "wrong"}).status_code == 401
    ok = client.post("/ask", json=Q, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200 and not ok.json()["refused"]
    assert client.get("/health").json()["api_key_required"] is True


def test_wrong_key_does_not_use_up_the_rate_limit(fixture_index):
    client = _client(fixture_index, RateLimiter(limit=1, clock=Clock()), api_key="s3cret")
    for _ in range(5):
        client.post("/ask", json=Q, headers={"X-API-Key": "wrong"})
    assert client.post("/ask", json=Q, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_key_never_echoed_in_errors(fixture_index):
    client = _client(fixture_index, api_key="s3cret")
    r = client.post("/ask", json=Q, headers={"X-API-Key": "guess"})
    assert "s3cret" not in r.text and "guess" not in r.text
