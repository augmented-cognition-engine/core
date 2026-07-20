# engine/api/middleware.py
"""Request middleware: API key auth, correlation ID propagation, access logging.

Middleware execution order (added last = runs first in Starlette):
1. APIKeyMiddleware    — outer auth gate (required outside local development)
2. CorrelationIDMiddleware — set/echo correlation ID
3. RequestLoggingMiddleware — log method + path + status + latency
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that never require API key auth (health probes, auth exchange, CI/CD gate)
_AUTH_SKIP_PREFIXES = (
    "/health",
    "/metrics",  # Prometheus scrape endpoint — no auth required
    "/auth/token",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/webhooks/",  # GitHub/GitLab webhook receivers
    "/review/gate/",  # Quality gate — intentionally open for CI/CD
    "/assets/",  # Portal static files — JS/CSS bundles must load before login
    "/favicon",  # Favicon requests
    "/stream/",  # SSE stream — EventSource passes JWT as query param, not header
    "/canvas/ws/",  # Yjs sync (WS — middleware doesn't run for WS upgrades, but list anyway)
    "/canvas/bridge/",  # Canvas agent participant bridge — local-only orchestrator hook
)

_SKIP_LOGGING = frozenset({"/health", "/health/live", "/health/ready", "/health/ops", "/metrics", "/favicon.ico"})

# Requests slower than this threshold get an additional WARNING log
_SLOW_REQUEST_MS = 2000


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Global API key gate with an explicit local-development exception.

    Accepts either:
    - X-API-Key: <key>  header
    - Authorization: Bearer <jwt>  (defers validation to per-route Depends)

    When API_KEY is empty in development or test, this middleware is a no-op.
    Staging and production fail closed if the operator omitted the key.
    Paths in _AUTH_SKIP_PREFIXES bypass the check entirely.
    """

    async def dispatch(self, request: Request, call_next):
        from core.engine.core.config import settings

        api_key = settings.api_key
        if not api_key:
            environment = getattr(settings, "environment", "production")
            if environment in {"development", "test"}:
                return await call_next(request)
            return JSONResponse(
                status_code=503,
                content={"detail": "API authentication is not configured"},
            )

        path = request.url.path
        if any(path.startswith(p) for p in _AUTH_SKIP_PREFIXES):
            return await call_next(request)

        # Accept X-API-Key header
        if request.headers.get("X-API-Key") == api_key:
            return await call_next(request)

        # Validate JWT here as well as in protected route dependencies. Not every
        # legacy router has a per-route dependency, so accepting a bearer-shaped
        # string without verification would bypass the global gate.
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from core.engine.core.auth import verify_token

            try:
                verify_token(auth_header.removeprefix("Bearer ").strip())
            except HTTPException:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return await call_next(request)

        from core.engine.core.log_context import get_correlation_id

        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid API key", "correlation_id": get_correlation_id()},
            headers={"WWW-Authenticate": 'Bearer realm="ACE", charset="UTF-8"'},
        )


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request.

    Priority order:
      1. W3C traceparent header — if present, extract the trace-id fragment and
         use it as the correlation ID so logs correlate with OTel spans.
      2. X-Correlation-ID header — caller-supplied opaque ID.
      3. Generated — new 12-char hex ID.

    Echoes the resolved ID back in X-Correlation-ID so clients can log it.
    Also stores on request.state.correlation_id for use in route handlers.
    """

    async def dispatch(self, request: Request, call_next):
        from core.engine.core.log_context import new_correlation_id, set_correlation_id

        cid: str = ""

        # W3C traceparent: "00-<trace-id>-<parent-id>-<flags>"
        traceparent = request.headers.get("traceparent", "").strip()
        if traceparent:
            parts = traceparent.split("-")
            if len(parts) == 4:
                cid = parts[1][:12]  # first 12 chars of the 32-char trace-id

        if not cid:
            inbound = request.headers.get("X-Correlation-ID", "").strip()
            cid = inbound if inbound else new_correlation_id()

        set_correlation_id(cid)
        request.state.correlation_id = cid

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, and latency for every non-health request.

    Structured extra fields (machine-parseable when JSONLogFormatter is active):
        http_method, http_path, http_status, duration_ms, cid

    Severity routing:
        2xx / 3xx → INFO
        4xx       → WARNING
        5xx       → ERROR  (also recorded in error_buffer)

    Slow requests (>_SLOW_REQUEST_MS) emit an additional WARNING.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_LOGGING:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        from core.engine.core.log_context import get_correlation_id

        cid = get_correlation_id()
        status = response.status_code
        extra = {
            "http_method": request.method,
            "http_path": request.url.path,
            "http_status": status,
            "duration_ms": round(elapsed_ms, 1),
            "cid": cid,
        }

        msg = "%s %s → %d (%.0fms)"
        args = (request.method, request.url.path, status, elapsed_ms)

        if status >= 500:
            logger.error(msg, *args, extra=extra)
            from core.engine.core.error_buffer import error_buffer

            error_buffer.record(
                source="http",
                error_type=f"HTTP_{status}",
                message=f"{request.method} {request.url.path}",
                cid=cid,
                context={"status": status, "duration_ms": round(elapsed_ms, 1)},
            )
        elif status >= 400:
            logger.warning(msg, *args, extra=extra)
        else:
            logger.info(msg, *args, extra=extra)

        if elapsed_ms > _SLOW_REQUEST_MS:
            logger.warning(
                "SLOW REQUEST: %s %s %.0fms (threshold %dms)",
                request.method,
                request.url.path,
                elapsed_ms,
                _SLOW_REQUEST_MS,
                extra={**extra, "slow": True},
            )

        return response


# Current stable API version — increment on breaking changes.
# Clients may inspect X-ACE-API-Version to detect when they need to update.
_API_VERSION = "1"


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Stamp every response with X-ACE-API-Version so clients can detect breaking changes.

    Versioning policy:
      - v1: current stable API (all routes without /v prefix)
      - Breaking changes will introduce /v2 routes with a deprecation period for v1
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-ACE-API-Version"] = _API_VERSION
        return response
