"""OpenTelemetry setup for the ACE FastAPI app.

Behaviour
---------
- No-op by default: if OTEL_EXPORTER_OTLP_ENDPOINT is unset, traces go to
  a noop exporter so zero external dependency is required to run locally.
- OTLP (gRPC) exporter when OTEL_EXPORTER_OTLP_ENDPOINT is set (Jaeger,
  Grafana, Honeycomb, or any OTel Collector).
- FastAPI + HTTPX auto-instrumented when setup_otel(app) is called.
- Trace ID injected into every log record via OTelTraceIDFilter so all JSON
  log lines include trace_id and span_id alongside correlation_id.

Usage (main.py lifespan)::

    from core.engine.core.otel import setup_otel
    setup_otel(app)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ace-engine")
_tracer: trace.Tracer | None = None


def setup_otel(app=None) -> None:
    """Initialize OTel tracing. Call once at app startup."""
    global _tracer

    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    resource = Resource(attributes={SERVICE_NAME: _SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel: OTLP exporter → %s", endpoint)
    else:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
        logger.debug("OTel: in-memory noop exporter (set OTEL_EXPORTER_OTLP_ENDPOINT for export)")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(_SERVICE_NAME)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls="/health/live,/health/ready,/health/ops,/metrics",
            )
        except Exception:
            logger.warning("OTel: FastAPI auto-instrumentation unavailable", exc_info=True)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception:
        logger.warning("OTel: HTTPX auto-instrumentation unavailable", exc_info=True)

    logging.getLogger().addFilter(OTelTraceIDFilter())
    logger.info("OTel: tracing initialised (service=%s)", _SERVICE_NAME)


def get_tracer() -> trace.Tracer:
    """Return the module-level tracer. Falls back to noop tracer if setup_otel not called."""
    if _tracer is not None:
        return _tracer
    return trace.get_tracer(_SERVICE_NAME)


@contextmanager
def gen_ai_span(system: str, model: str, operation: str = "chat"):
    """Open an OpenTelemetry GenAI span around one LLM call.

    Sets the request-side GenAI semantic-convention attributes (gen_ai.system,
    gen_ai.operation.name, gen_ai.request.model) and yields the span so the caller
    can attach response attrs via set_gen_ai_usage(). The tracer's context manager
    records exceptions and marks the span ERROR automatically.

    No-op-safe: get_tracer() returns a noop tracer until setup_otel() runs / an
    OTLP endpoint is configured, so this adds negligible overhead when tracing is
    off and never affects the LLM call's result.
    """
    with get_tracer().start_as_current_span(f"{operation} {model}") as span:
        if span.is_recording():
            span.set_attribute("gen_ai.system", system)
            span.set_attribute("gen_ai.operation.name", operation)
            span.set_attribute("gen_ai.request.model", model)
        yield span


def set_gen_ai_usage(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    response_model: str | None = None,
) -> None:
    """Attach GenAI response attrs (usage tokens, response model) to the CURRENT span.

    Reads the active span via the OTel context, so a provider can enrich whatever
    gen_ai_span is open above it without holding a span handle. Recording-guarded
    and exception-free — a no-op when no span is recording.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return
    if response_model:
        span.set_attribute("gen_ai.response.model", str(response_model))
    span.set_attribute("gen_ai.usage.input_tokens", int(input_tokens or 0))
    span.set_attribute("gen_ai.usage.output_tokens", int(output_tokens or 0))


def current_trace_id() -> str:
    """Return the current span's trace ID as a 32-char hex string, or '-'."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return "-"


def current_span_id() -> str:
    """Return the current span's span ID as a 16-char hex string, or '-'."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        return format(ctx.span_id, "016x")
    return "-"


class OTelTraceIDFilter(logging.Filter):
    """Inject OTel trace_id and span_id into every LogRecord.

    Installed by setup_otel(); no-op when no span is active (fields → '-').
    Complements the existing CorrelationIDFilter — both filters can coexist.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return True
