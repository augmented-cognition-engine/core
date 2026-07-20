# tests/test_otel_gen_ai_spans.py
"""Phase 1 #3 — OpenTelemetry GenAI spans on every LLM call + trace_id in reasoning_run.

otel.py already had setup/trace-id plumbing; what was missing is a span *per LLM
call*. `_TracedLLM` wraps the resolved provider at the get_llm() choke point so
every complete()/complete_json() emits a gen_ai.* span (one seam, all providers),
and create_run stamps the active trace_id onto the reasoning_run so a run is
correlated to its trace.
"""

from __future__ import annotations

import pytest

from core.engine.core import otel
from core.engine.core.otel import gen_ai_span, set_gen_ai_usage


@pytest.fixture
def spans(monkeypatch):
    """Route otel spans into an in-memory exporter.

    Bypasses the global tracer provider (which can be set only once per process)
    by pointing otel._tracer at a private provider + InMemorySpanExporter.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(otel, "_tracer", provider.get_tracer("test"))
    return exporter


# --- gen_ai_span / set_gen_ai_usage --------------------------------------------


def test_gen_ai_span_sets_request_attributes(spans):
    with gen_ai_span("anthropic", "claude-sonnet-4-6"):
        pass
    finished = spans.get_finished_spans()
    assert len(finished) == 1
    s = finished[0]
    assert s.name == "chat claude-sonnet-4-6"
    assert s.attributes["gen_ai.system"] == "anthropic"
    assert s.attributes["gen_ai.operation.name"] == "chat"
    assert s.attributes["gen_ai.request.model"] == "claude-sonnet-4-6"


def test_set_gen_ai_usage_sets_response_attributes(spans):
    with gen_ai_span("anthropic", "m"):
        set_gen_ai_usage(input_tokens=12, output_tokens=34, response_model="claude-x")
    s = spans.get_finished_spans()[0]
    assert s.attributes["gen_ai.usage.input_tokens"] == 12
    assert s.attributes["gen_ai.usage.output_tokens"] == 34
    assert s.attributes["gen_ai.response.model"] == "claude-x"


def test_gen_ai_span_records_exception(spans):
    from opentelemetry.trace import StatusCode

    with pytest.raises(ValueError):
        with gen_ai_span("anthropic", "m"):
            raise ValueError("boom")
    s = spans.get_finished_spans()[0]
    assert s.status.status_code == StatusCode.ERROR
    assert any(e.name == "exception" for e in s.events)


def test_set_gen_ai_usage_is_noop_without_active_span():
    # No recording span in context → must not raise.
    set_gen_ai_usage(input_tokens=1, output_tokens=2)


# --- _instrument_llm (in-place provider instrumentation) -----------------------


@pytest.mark.asyncio
async def test_instrument_llm_spans_call_methods(spans):
    from core.engine.core.llm import _instrument_llm

    class _Inner:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            return f"R:{prompt}"

        async def complete_json(self, prompt, model=None, max_tokens=4096, system=None):
            return {"ok": prompt}

    p = _instrument_llm(_Inner(), "anthropic")

    assert await p.complete("hi", model="claude-x") == "R:hi"
    assert await p.complete_json("hey", model="claude-y") == {"ok": "hey"}

    finished = spans.get_finished_spans()
    assert len(finished) == 2
    assert finished[0].attributes["gen_ai.system"] == "anthropic"
    assert finished[0].attributes["gen_ai.request.model"] == "claude-x"
    assert finished[1].attributes["gen_ai.request.model"] == "claude-y"


@pytest.mark.asyncio
async def test_instrument_llm_preserves_instance_and_is_idempotent(spans):
    from core.engine.core.llm import _instrument_llm

    class ClaudeProvider:  # local stand-in — instance identity is the point
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            return "x"

    p = ClaudeProvider()
    out = _instrument_llm(p, "anthropic")
    assert out is p  # same instance → isinstance/type preserved
    assert isinstance(out, ClaudeProvider)
    wrapped = out.complete
    _instrument_llm(p, "anthropic")  # idempotent — does not re-wrap
    assert out.complete is wrapped


@pytest.mark.asyncio
async def test_instrument_llm_no_double_span_when_complete_json_delegates(spans):
    """A provider whose complete_json calls self.complete must yield ONE span."""
    from core.engine.core.llm import _instrument_llm

    class _Delegating:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            return "raw"

        async def complete_json(self, prompt, model=None, max_tokens=4096, system=None):
            await self.complete(prompt, model=model)  # delegates — must not open a 2nd span
            return {"ok": True}

    p = _instrument_llm(_Delegating(), "anthropic")
    assert await p.complete_json("hi", model="m") == {"ok": True}
    assert len(spans.get_finished_spans()) == 1


@pytest.mark.asyncio
async def test_instrument_llm_model_defaults_to_placeholder(spans):
    from core.engine.core.llm import _instrument_llm

    class _Inner:
        async def complete(self, prompt, model=None, max_tokens=4096, system=None):
            return "x"

    await _instrument_llm(_Inner(), "ollama").complete("hi")  # model omitted
    s = spans.get_finished_spans()[0]
    assert s.attributes["gen_ai.system"] == "ollama"
    assert s.attributes["gen_ai.request.model"] == "default"


@pytest.mark.asyncio
async def test_instrument_llm_wraps_complete_structured(spans):
    from core.engine.core.llm import _instrument_llm

    class _Schema: ...

    class _Inner:
        async def complete_structured(self, prompt, schema, model=None, max_tokens=4096):
            return ("structured", schema)

    out = await _instrument_llm(_Inner(), "anthropic").complete_structured("p", _Schema, model="claude-z")
    assert out == ("structured", _Schema)
    assert spans.get_finished_spans()[0].attributes["gen_ai.request.model"] == "claude-z"


@pytest.mark.asyncio
async def test_instrument_llm_wraps_stream(spans):
    from core.engine.core.llm import _instrument_llm

    class _Inner:
        async def stream(self, prompt, model=None, max_tokens=4096):
            for c in ["a", "b", "c"]:
                yield c

    chunks = [c async for c in _instrument_llm(_Inner(), "ollama").stream("p", model="m")]
    assert chunks == ["a", "b", "c"]
    s = spans.get_finished_spans()[0]
    assert s.attributes["gen_ai.system"] == "ollama"
    assert s.attributes["gen_ai.request.model"] == "m"


@pytest.mark.asyncio
async def test_instrument_llm_wraps_stream_messages(spans):
    from core.engine.core.llm import _instrument_llm

    class _Inner:
        async def stream_messages(self, system, messages, model=None, max_tokens=4096):
            yield "x"
            yield "y"

    p = _instrument_llm(_Inner(), "openai")
    chunks = [c async for c in p.stream_messages("sys", [{"role": "user", "content": "hi"}], model="gpt-x")]
    assert chunks == ["x", "y"]
    assert spans.get_finished_spans()[0].attributes["gen_ai.request.model"] == "gpt-x"


def test_provider_system_mapping():
    from core.engine.core.llm import _provider_system

    class ClaudeProvider: ...

    class CLIProvider: ...

    class OllamaProvider: ...

    class OpenAICompatProvider: ...

    class WeirdProvider: ...

    assert _provider_system(ClaudeProvider()) == "anthropic"
    assert _provider_system(CLIProvider()) == "anthropic"
    assert _provider_system(OllamaProvider()) == "ollama"
    assert _provider_system(OpenAICompatProvider()) == "openai"
    assert _provider_system(WeirdProvider()) == "weird"


# --- trace_id correlation into reasoning_run -----------------------------------


@pytest.mark.asyncio
async def test_create_run_stamps_trace_id(monkeypatch):
    from core.engine.cognition import run_ledger

    captured: list[tuple[str, dict]] = []

    class _Conn:
        async def query(self, sql, params=None):
            captured.append((sql, params or {}))
            return [[{"id": "reasoning_run:abc"}]]

    class _CM:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def connection(self):
            return _CM()

    monkeypatch.setattr("core.engine.core.db.pool", _Pool())
    monkeypatch.setattr(run_ledger, "current_trace_id", lambda: "abc123")

    rid = await run_ledger.create_run(product_id="product:test", thought="t", meta_skills=[], depth=1, discipline=None)

    assert rid == "reasoning_run:abc"
    _sql, params = captured[0]
    assert params["trace_id"] == "abc123"
    assert "trace_id = $trace_id" in _sql
