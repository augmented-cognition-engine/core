# tests/test_startup_no_db.py
"""OSS Task 8a — a no-database first run must fail fast and friendly.

The stranger's experience without this fix (diagnosed in
.superpowers/sdd/oss-task-8a-brief.md): `make dev` on a machine with no SurrealDB
running either hangs forever (a reachable-but-silent host, no connect timeout) or
dumps a raw ECONNREFUSED traceback (port closed, no friendly handler) — the #1
first-five-minutes cliff for a new user.

Two parts, two groups of tests:
  A. db.py `_create_connection` is bounded by CONNECT_TIMEOUT so it can never hang.
  B. main.py's lifespan catches a pool.init() connection failure, logs an actionable
     message (the URL + the exact `docker compose ... up -d surrealdb` remedy), and
     aborts startup — it does not proceed to serve, and it does not swallow the error.

None of this needs a live SurrealDB — these tests exercise the FAILURE path, so unlike
tests/test_db.py they carry no `e2e` marker and run in the fast suite.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from unittest.mock import AsyncMock

import pytest

from core.engine.core.db import DBUnreachable, SurrealPool


def _closed_port() -> int:
    """A localhost port guaranteed to have nothing listening on it right now.

    Bind to port 0 (the OS picks a free ephemeral port), read the assignment, then
    close immediately — a connect attempt a moment later gets a real, fast
    ECONNREFUSED instead of relying on a hardcoded port number that might collide
    with something already running on the test machine.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# --------------------------------------------------------------------------- #
# Part A — db.py: _create_connection can never hang                           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_connection_against_closed_port_fails_fast_not_hangs(monkeypatch):
    """The common no-Docker case: nothing is listening. This must fail fast — it
    already did before this change (ConnectionRefusedError is immediate) — and this
    test pins that CONNECT_TIMEOUT wrapping did not regress it into a hang."""
    import core.engine.core.db as db_module

    monkeypatch.setattr(db_module.settings, "surreal_url", f"ws://127.0.0.1:{_closed_port()}")
    pool = SurrealPool(max_connections=1)

    t0 = time.monotonic()
    with pytest.raises(OSError):  # ConnectionRefusedError — not a hang
        await pool._create_connection()
    elapsed = time.monotonic() - t0

    assert elapsed < SurrealPool.CONNECT_TIMEOUT + 1.0, (
        f"a closed port took {elapsed:.2f}s to fail — expected fast, not bounded-by-timeout"
    )


@pytest.mark.asyncio
async def test_create_connection_times_out_on_a_silent_host_instead_of_hanging(monkeypatch):
    """The hang class Part A exists to kill: a host that accepts the connection but
    never completes the handshake (VPN, firewall, wrong service on the port).
    Simulated by making connect() hang forever; CONNECT_TIMEOUT is shortened here so
    the test itself stays fast without changing what's being proven."""
    from surrealdb.connections.async_ws import AsyncWsSurrealConnection

    async def _hangs_forever(self, url=None):
        await asyncio.sleep(3600)

    monkeypatch.setattr(SurrealPool, "CONNECT_TIMEOUT", 0.2)
    monkeypatch.setattr(AsyncWsSurrealConnection, "connect", _hangs_forever)
    pool = SurrealPool(max_connections=1)

    t0 = time.monotonic()
    with pytest.raises(DBUnreachable):
        await pool._create_connection()
    elapsed = time.monotonic() - t0

    assert elapsed < 1.0, f"CONNECT_TIMEOUT did not bound the hang — took {elapsed:.2f}s"


# --------------------------------------------------------------------------- #
# Part B — main.py: the lifespan fails fast and friendly, never a raw traceback #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_lifespan_with_no_db_logs_actionable_message_and_aborts(monkeypatch, caplog):
    """pool.init() raising a connection error must produce a message naming the URL
    and the docker-compose remedy, and must NOT let startup proceed — it aborts via
    SystemExit rather than continuing with a DB-less app or dumping a raw traceback."""
    from fastapi import FastAPI

    from core.engine.api import main as main_module

    app = FastAPI()
    monkeypatch.setattr(
        main_module.pool,
        "init",
        AsyncMock(side_effect=ConnectionRefusedError("[Errno 61] Connection refused")),
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc_info:
            async with main_module.lifespan(app):
                pytest.fail("lifespan must not proceed past a failed pool.init()")

    assert exc_info.value.code == 1

    redacted_url = main_module.pool._redact_url(main_module.settings.surreal_url)
    assert redacted_url in caplog.text
    assert "docker compose -f infra/docker-compose.yml up -d surrealdb" in caplog.text
    assert "not reachable" in caplog.text


@pytest.mark.asyncio
async def test_lifespan_with_no_db_message_names_the_dotenv_fallback(monkeypatch, caplog):
    """The message must also tell the reader the OTHER way out — pointing SURREAL_URL
    at an existing SurrealDB — not just the docker-compose path, and it must not
    silently swallow the failure (SystemExit must still propagate)."""
    from fastapi import FastAPI

    from core.engine.api import main as main_module

    app = FastAPI()
    monkeypatch.setattr(
        main_module.pool,
        "init",
        AsyncMock(side_effect=DBUnreachable(main_module.settings.surreal_url, 5.0)),
    )

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        async with main_module.lifespan(app):
            pytest.fail("lifespan must not proceed past a failed pool.init()")

    assert "SURREAL_URL" in caplog.text
    assert "README" in caplog.text
