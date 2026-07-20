"""Regression tests for engine/core/otel.py."""

from __future__ import annotations

import logging


def test_get_tracer_returns_noop_before_setup():
    """get_tracer() is safe to call before setup_otel() — returns a noop tracer."""

    import core.engine.core.otel as otel_mod

    # Reset module-level _tracer so this test is isolated
    original = otel_mod._tracer
    otel_mod._tracer = None
    try:
        tracer = otel_mod.get_tracer()
        assert tracer is not None
    finally:
        otel_mod._tracer = original


def test_current_trace_id_returns_dash_when_no_span():
    """current_trace_id() returns '-' outside of an active span."""
    from core.engine.core.otel import current_trace_id

    assert current_trace_id() == "-"


def test_current_span_id_returns_dash_when_no_span():
    """current_span_id() returns '-' outside of an active span."""
    from core.engine.core.otel import current_span_id

    assert current_span_id() == "-"


def test_otel_trace_id_filter_sets_dash_when_no_span():
    """OTelTraceIDFilter injects '-' fields when no span is active."""
    from core.engine.core.otel import OTelTraceIDFilter

    f = OTelTraceIDFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
    f.filter(record)
    assert record.trace_id == "-"
    assert record.span_id == "-"


def test_setup_otel_runs_without_endpoint(monkeypatch):
    """setup_otel() completes without OTEL_EXPORTER_OTLP_ENDPOINT set."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    import core.engine.core.otel as otel_mod

    # Reset so we can call setup again
    original_tracer = otel_mod._tracer

    try:
        otel_mod.setup_otel(app=None)
        tracer = otel_mod.get_tracer()
        assert tracer is not None
    finally:
        otel_mod._tracer = original_tracer


def test_otel_trace_id_filter_injects_real_ids_when_span_active():
    """OTelTraceIDFilter injects real hex IDs when a span is active."""
    from opentelemetry.sdk.trace import TracerProvider

    from core.engine.core.otel import OTelTraceIDFilter

    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    f = OTelTraceIDFilter()

    with tracer.start_as_current_span("test-span"):
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.trace_id != "-"
        assert len(record.trace_id) == 32
        assert record.span_id != "-"
        assert len(record.span_id) == 16
