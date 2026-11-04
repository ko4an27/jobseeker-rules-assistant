import builtins
import sys

import pytest

from jobseeker_assistant.tracing import LangfuseTracer, NoopTracer, get_tracer


@pytest.mark.parametrize("value", [None, "", "false", "0", "no", "off", "maybe"])
def test_tracing_is_off_unless_explicitly_enabled(value):
    env = {} if value is None else {"LANGFUSE_ENABLED": value}
    assert isinstance(get_tracer(env), NoopTracer)


def test_off_means_langfuse_is_never_imported(monkeypatch):
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name.startswith("langfuse"):
            raise AssertionError("langfuse imported while tracing is off")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "langfuse", raising=False)
    monkeypatch.setattr(builtins, "__import__", guard)
    tracer = get_tracer({"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})
    tracer.record_answer("q", "a", {"path": []})  # does nothing
    assert tracer.enabled is False


def test_enabled_without_keys_fails_clearly():
    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        get_tracer({"LANGFUSE_ENABLED": "true"})


class FakeClient:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, **kwargs):
        self.spans.append(kwargs)
        import contextlib

        return contextlib.nullcontext()


def test_langfuse_tracer_sends_metadata_only_by_default():
    client = FakeClient()
    LangfuseTracer(client).record_answer("my name is X", "answer", {"path": ["refuse"]})
    [span] = client.spans
    assert span == {"name": "ask", "metadata": {"path": ["refuse"]}}


def test_langfuse_tracer_sends_text_only_when_asked():
    client = FakeClient()
    LangfuseTracer(client, log_text=True).record_answer("q", "a", {})
    assert client.spans[0]["input"] == {"question": "q"}
    assert client.spans[0]["output"] == {"answer": "a"}


def test_enabled_builds_langfuse_client_from_env(monkeypatch):
    import langfuse

    made = {}

    class StubLangfuse:
        def __init__(self, **kwargs):
            made.update(kwargs)

    monkeypatch.setattr(langfuse, "Langfuse", StubLangfuse)
    tracer = get_tracer(
        {
            "LANGFUSE_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_SECRET_KEY": "sk",
            "LANGFUSE_LOG_TEXT": "false",
        }
    )
    assert isinstance(tracer, LangfuseTracer) and tracer.log_text is False
    assert made == {"public_key": "pk", "secret_key": "sk", "host": None}
