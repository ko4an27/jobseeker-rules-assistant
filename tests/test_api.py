import logging

import pytest
from fastapi.testclient import TestClient

from jobseeker_assistant import api
from jobseeker_assistant.api import MAX_QUESTION_CHARS, Resources, create_app
from jobseeker_assistant.llm import FakeLLM
from jobseeker_assistant.tracing import NoopTracer


class RecordingTracer:
    enabled = True

    def __init__(self):
        self.records = []

    def record_answer(self, question, answer, metadata):
        self.records.append((question, answer, metadata))


@pytest.fixture
def tracer():
    return RecordingTracer()


@pytest.fixture
def client(fixture_index, tracer):
    res = Resources(fixture_index, FakeLLM(), [], tracer, snapshot_count=2)
    return TestClient(create_app(res))


def test_health(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "snapshots": 2, "llm": "FakeLLM", "tracing": True}


def test_ask_answers_with_citations_and_path(client):
    r = client.post("/ask", json={"question": "What is the duration of a work trial?"})
    assert r.status_code == 200
    body = r.json()
    assert not body["refused"] and body["refusal_reason"] is None
    assert body["citations"][0]["url"] == "https://example.test/work-trial"
    assert body["citations"][0]["section"] == "Duration"
    assert body["path"][-1] == "finalize" and body["path"][0] == "legal_check"
    assert body["attempts"] == 1
    assert "not legal or official advice" in body["disclaimer"]
    assert len(body["request_id"]) == 12


def test_ask_refusal_has_reason(client):
    body = client.post("/ask", json={"question": "Should I sue my employer?"}).json()
    assert body["refused"] and body["refusal_reason"].startswith("legal_advice")
    assert body["path"] == ["legal_check", "refuse"] and body["citations"] == []


def test_ask_off_topic_refused(client):
    body = client.post("/ask", json={"question": "best pizza in helsinki"}).json()
    assert body["refused"] and body["refusal_reason"] in {"no_passages", "low_coverage"}


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "   \n "}, {}, {"q": "x"}])
def test_ask_rejects_empty_or_missing_question(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_ask_rejects_too_long_question(client):
    r = client.post("/ask", json={"question": "a" * (MAX_QUESTION_CHARS + 1)})
    assert r.status_code == 422


def test_ask_accepts_max_length_question(client):
    r = client.post("/ask", json={"question": "work trial " * 45})
    assert r.status_code == 200


def test_question_text_is_never_logged(client, caplog):
    secret = "My name is Matti Meikäläinen, ID 010190-123A, I earn 1450 euros."
    with caplog.at_level(logging.DEBUG):
        client.post("/ask", json={"question": f"{secret} What is the duration of a work trial?"})
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "ask {" in logged  # metadata is logged...
    for fragment in ("Matti", "010190", "1450"):
        assert fragment not in logged  # ...the question text is not


def test_tracer_gets_metadata(client, tracer):
    client.post("/ask", json={"question": "What is the duration of a work trial?"})
    [(question, answer, meta)] = tracer.records
    assert meta["path"][-1] == "finalize" and meta["question_chars"] == len(question)
    assert "question" not in meta and "answer" not in meta


def test_not_configured_returns_503(monkeypatch):
    def boom():
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(api, "load_resources", boom)
    r = TestClient(create_app()).get("/health")
    assert r.status_code == 503 and "ANTHROPIC_API_KEY is not set" in r.json()["detail"]


def test_module_app_loads_real_snapshots_with_fake_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    body = TestClient(create_app()).get("/health").json()
    assert body["status"] == "ok" and body["snapshots"] == 22 and body["tracing"] is False


def test_noop_tracer_is_default_shape():
    assert NoopTracer().enabled is False
