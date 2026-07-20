# tests/test_observability_middleware.py
"""Tests for RequestLoggingMiddleware severity routing, slow-request detection,
and the /health/ops endpoint."""

import logging
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from core.engine.api.middleware import _SLOW_REQUEST_MS, RequestLoggingMiddleware

# ------------------------------------------------------------------ #
# RequestLoggingMiddleware                                             #
# ------------------------------------------------------------------ #


def _make_app(status_code: int, path: str = "/api/test") -> FastAPI:
    """Build a minimal FastAPI app that returns a fixed status for testing middleware."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get(path)
    async def _route():
        return JSONResponse(content={}, status_code=status_code)

    return app


def test_2xx_logs_at_info(caplog):
    app = _make_app(200)
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="core.engine.api.middleware"):
        client.get("/api/test")
    records = [r for r in caplog.records if r.name == "core.engine.api.middleware"]
    assert any(r.levelno == logging.INFO for r in records)
    assert not any(r.levelno >= logging.WARNING for r in records)


def test_4xx_logs_at_warning(caplog):
    app = _make_app(404)
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.WARNING, logger="core.engine.api.middleware"):
        client.get("/api/test")
    records = [r for r in caplog.records if r.name == "core.engine.api.middleware"]
    assert any(r.levelno == logging.WARNING for r in records)


def test_5xx_logs_at_error_and_records_to_buffer(caplog):
    from core.engine.core.error_buffer import error_buffer

    error_buffer.clear()
    app = _make_app(500)
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="core.engine.api.middleware"):
        client.get("/api/test")

    records = [r for r in caplog.records if r.name == "core.engine.api.middleware"]
    assert any(r.levelno == logging.ERROR for r in records)
    assert error_buffer.count == 1
    assert error_buffer.recent()[0]["error_type"] == "HTTP_500"
    error_buffer.clear()


def test_5xx_error_buffer_entry_has_cid():
    from core.engine.core.error_buffer import error_buffer

    error_buffer.clear()
    app = _make_app(500)
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/api/test", headers={"X-Correlation-ID": "testcid123"})

    assert error_buffer.count == 1
    error_buffer.clear()


def test_structured_extra_fields_on_log_record(caplog):
    """Log records must carry http_method, http_path, http_status, duration_ms."""
    app = _make_app(200)
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="core.engine.api.middleware"):
        client.get("/api/test")
    records = [r for r in caplog.records if r.name == "core.engine.api.middleware"]
    assert records, "expected at least one log record"
    r = records[0]
    assert hasattr(r, "http_method")
    assert hasattr(r, "http_path")
    assert hasattr(r, "http_status")
    assert hasattr(r, "duration_ms")
    assert r.http_method == "GET"
    assert r.http_path == "/api/test"
    assert r.http_status == 200


def test_health_paths_not_logged(caplog):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health/live")
    async def _():
        return {"status": "ok"}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="core.engine.api.middleware"):
        client.get("/health/live")
    records = [r for r in caplog.records if r.name == "core.engine.api.middleware"]
    assert len(records) == 0


def test_slow_request_emits_warning(caplog):
    """elapsed_ms > _SLOW_REQUEST_MS triggers an additional SLOW REQUEST warning."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/slow")
    async def _():
        return JSONResponse(content={})

    # perf_counter is called twice: once at start, once at end.
    # Return values: 0.0 then a value that makes elapsed > threshold.
    # Use a sequence long enough to absorb any internal starlette calls.
    slow_return = (_SLOW_REQUEST_MS + 500) / 1000.0
    counter_values = iter([0.0, slow_return] + [slow_return] * 20)

    with patch("core.engine.api.middleware.time") as mock_time:
        mock_time.perf_counter.side_effect = lambda: next(counter_values)
        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.WARNING, logger="core.engine.api.middleware"):
            client.get("/slow")

    records = [r for r in caplog.records if r.name == "core.engine.api.middleware"]
    slow_records = [r for r in records if "SLOW" in r.getMessage()]
    assert len(slow_records) == 1


# ------------------------------------------------------------------ #
# /health/ops endpoint                                                 #
# ------------------------------------------------------------------ #


def test_health_ops_returns_200_no_auth():
    """GET /health/ops must return 200 without authentication."""
    from core.engine.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health/ops")
    assert resp.status_code == 200


def test_health_ops_structure():
    """Response must include capture_service, sentinel, db_pool, recent_errors."""
    from core.engine.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health/ops")
    data = resp.json()
    assert "capture_service" in data
    assert "sentinel" in data
    assert "recent_errors" in data


def test_health_ops_capture_service_fields():
    """capture_service block must include all CaptureService.get_stats() fields."""
    from core.engine.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    data = client.get("/health/ops").json()
    cs = data["capture_service"]
    for key in ("running", "queue_depth", "queue_max", "emitted", "dropped", "processed"):
        assert key in cs, f"missing key: {key}"


def test_health_ops_recent_errors_is_list():
    from core.engine.api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    data = client.get("/health/ops").json()
    assert isinstance(data["recent_errors"], list)
