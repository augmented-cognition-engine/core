# tests/test_worker_session.py
"""Tests for the ACE Session Intelligence Worker (engine/worker/app.py).

Uses FastAPI's ASGI test transport so no real server or DB needed.
DB-dependent tests are marked e2e and skipped in the fast gate.
"""

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# The boundary tests below load .claude/hooks/ace-intelligence.py directly —
# private session tooling, not shipped in the public export. Skip those (the
# /session/* API tests above test shipped core.engine.worker.app and must
# keep running).
_HOOKS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "hooks"
_HAS_PRIVATE_HOOKS = _HOOKS_DIR.is_dir()
_skip_no_hooks = pytest.mark.skipif(
    not _HAS_PRIVATE_HOOKS, reason="requires private .claude/hooks/ (not shipped in the public export)"
)


@pytest.fixture
async def worker_client():
    """Test client for the worker app with lifespan mocked out (no DB)."""
    from core.engine.worker.app import app

    @asynccontextmanager
    async def mock_lifespan(app):
        yield

    app.router.lifespan_context = mock_lifespan
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_returns_ok(worker_client):
    resp = await worker_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_post_message_returns_queued(worker_client, monkeypatch):
    """POST /session/message returns {status: queued} without hitting DB."""
    from core.engine.worker import session as session_mod

    # Stub out DB calls
    async def fake_on_message(self, session_id, message, product_id):
        pass

    monkeypatch.setattr(session_mod.SessionManager, "on_message", fake_on_message)

    resp = await worker_client.post(
        "/session/message",
        json={"session_id": "test-session-1", "message": "hello", "product_id": "product:test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["session_id"] == "test-session-1"


@pytest.mark.asyncio
async def test_post_message_requires_session_id(worker_client):
    """POST /session/message without session_id should 422."""
    resp = await worker_client.post(
        "/session/message",
        json={"message": "hello"},
    )
    assert resp.status_code == 422


def test_worker_keyword_classify_classifies_current_message():
    """The worker gains an instant keyword classifier so POST can set a
    provisional classification for the CURRENT message (fast-path lag fix)."""
    from core.engine.worker.classifier import keyword_classify

    cls = keyword_classify("add pytest coverage and fixtures")
    assert cls is not None
    assert cls["discipline"] == "testing"
    assert keyword_classify("good morning to you all") is None


@pytest.mark.asyncio
async def test_post_message_sets_provisional_classification_for_current_prompt(worker_client, monkeypatch):
    """Fast-path fix: POST classifies the CURRENT message synchronously and
    persists it tagged with the message seq, so GET /context reflects THIS
    prompt instead of the previous one's classification."""
    from core.engine.worker import app as app_mod
    from core.engine.worker import session as session_mod

    async def fake_on_message(self, session_id, message, product_id):
        return 4  # the new message sequence number

    recorded = {}

    async def fake_update_classification(self, session_id, classification, seq=None):
        recorded["cls"] = classification
        recorded["seq"] = seq

    async def fake_background(session_id, message, product_id, seq=None):
        return None

    monkeypatch.setattr(session_mod.SessionManager, "on_message", fake_on_message)
    monkeypatch.setattr(session_mod.SessionManager, "update_classification", fake_update_classification)
    monkeypatch.setattr(app_mod, "_background_classify", fake_background)

    resp = await worker_client.post(
        "/session/message",
        json={"session_id": "s", "message": "add pytest coverage and fixtures", "product_id": "product:test"},
    )
    assert resp.status_code == 200
    assert recorded.get("cls", {}).get("discipline") == "testing", "current prompt classified synchronously"
    assert recorded.get("seq") == 4, "provisional classification tagged with the message seq"


@pytest.mark.asyncio
async def test_get_context_returns_defaults_when_no_session(worker_client, monkeypatch):
    """GET /session/context with no prior session returns default context."""
    from core.engine.worker import session as session_mod

    async def fake_get_or_create(self, session_id, product_id):
        return {
            "session_id": session_id,
            "product": product_id,
            "message_count": 0,
            "rolling_summary": "",
            "compact_index": "",
            "current_discipline": "architecture",
            "current_mode": "reactive",
            "current_depth": 1,
            "classification": {},
        }

    monkeypatch.setattr(session_mod.SessionManager, "get_or_create", fake_get_or_create)

    resp = await worker_client.get("/session/context", params={"session_id": "test-session-2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "test-session-2"
    assert body["discipline"] == "architecture"
    assert body["mode"] == "reactive"
    assert body["message_count"] == 0
    assert body["compact_index"] == ""


@pytest.mark.asyncio
async def test_get_context_reflects_classification(worker_client, monkeypatch):
    """GET /session/context after message returns classification from state."""
    from core.engine.worker import session as session_mod

    async def fake_get_or_create(self, session_id, product_id):
        return {
            "session_id": session_id,
            "product": product_id,
            "message_count": 5,
            "rolling_summary": "exploring cognitive architecture",
            "compact_index": "## Context\n- 3 design decisions",
            "current_discipline": "ux",
            "current_mode": "deliberative",
            "current_depth": 3,
            "classification": {
                "discipline": "ux",
                "archetype": "creator",
                "mode": "deliberative",
                "perspective": "practitioner",
                "specialties": ["interface-design"],
            },
        }

    monkeypatch.setattr(session_mod.SessionManager, "get_or_create", fake_get_or_create)

    resp = await worker_client.get("/session/context", params={"session_id": "test-session-3"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["discipline"] == "ux"
    assert body["mode"] == "deliberative"
    assert body["message_count"] == 5
    assert body["compact_index"] == "## Context\n- 3 design decisions"
    assert "interface-design" in body["specialties"]


@pytest.mark.asyncio
async def test_get_context_missing_session_id_returns_422(worker_client):
    """GET /session/context without session_id returns 422."""
    resp = await worker_client.get("/session/context")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_complete_returns_ok(worker_client, monkeypatch):
    """POST /session/complete marks session done."""
    from core.engine.worker import session as session_mod

    async def fake_mark_complete(self, session_id):
        pass

    monkeypatch.setattr(session_mod.SessionManager, "mark_complete", fake_mark_complete)

    resp = await worker_client.post(
        "/session/complete",
        json={"session_id": "test-session-4"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["session_id"] == "test-session-4"


# ── Boundary / sentinel tests for hook fallback ────────────────────────────


@_skip_no_hooks
@pytest.mark.asyncio
async def test_hook_fallback_when_worker_unavailable(monkeypatch):
    """Boundary: hook returns valid <ace-intelligence> when worker is unreachable.

    Sentinel check: 'timeout fallback' must NOT appear — that string only fires
    on the 4s asyncio.wait_for timeout, not on connection refused.
    """
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    # Point to a port with nothing listening
    monkeypatch.setenv("ACE_WORKER_URL", "http://localhost:19999")

    # Stub out all DB calls so legacy path doesn't need SurrealDB

    hook_path = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "ace-intelligence.py")
    import importlib.util

    spec = importlib.util.spec_from_file_location("ace_intelligence_hook", hook_path)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    async def fake_compose_legacy(prompt: str) -> str:
        return "<ace-intelligence>\n## ACE Composition\ndiscipline: architecture\n</ace-intelligence>"

    monkeypatch.setattr(hook, "_compose_legacy", fake_compose_legacy)
    monkeypatch.setenv("ACE_WORKER_URL", "http://localhost:19999")

    result = await hook.compose("build the worker service")

    # Sentinel: output must be a valid <ace-intelligence> block
    assert result.startswith("<ace-intelligence>")
    assert result.endswith("</ace-intelligence>")
    # Sentinel: 'timeout fallback' must NOT appear — means compose() fell back cleanly
    assert "timeout fallback" not in result


@_skip_no_hooks
@pytest.mark.asyncio
async def test_hook_uses_worker_context_when_available(monkeypatch):
    """Boundary: hook returns worker's context (not legacy) when worker responds."""
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    hook_path = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "ace-intelligence.py")
    import importlib.util

    spec = importlib.util.spec_from_file_location("ace_intelligence_hook2", hook_path)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    # Stub fire-and-forget to no-op
    async def fake_post(session_id, message):
        pass

    monkeypatch.setattr(hook, "_post_message_async", fake_post)

    # Stub GET context to return deliberative classification
    async def fake_get_context(session_id):
        return {
            "session_id": session_id,
            "discipline": "architecture",
            "archetype": "analyst",
            "mode": "deliberative",
            "perspective": "practitioner",
            "specialties": ["system-design"],
            "rolling_summary": "exploring worker architecture",
            "message_count": 8,
            "compact_index": "## Context\n- 5 decisions",
        }

    monkeypatch.setattr(hook, "_get_session_context", fake_get_context)

    result = await hook.compose("how should we wire the composition graph?")

    assert "deliberative" in result
    assert "architecture" in result
    assert "## Context" in result  # compact_index injected
    assert "timeout fallback" not in result
