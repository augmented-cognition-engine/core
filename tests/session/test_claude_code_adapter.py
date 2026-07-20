"""Boundary tests for ClaudeCodeAdapter — AC 2, 3, 5."""

from __future__ import annotations

from datetime import datetime, timezone

from core.engine.capture.watchers import StreamEvent
from core.engine.session.adapter import SessionAdapter
from core.engine.session.adapters.claude_code import ClaudeCodeAdapter
from core.engine.session.adapters.generic import GenericAdapter
from core.engine.session.registry import resolve

# ---------------------------------------------------------------------------
# AC 2 — SessionAdapter protocol
# ---------------------------------------------------------------------------


def test_claude_code_adapter_satisfies_protocol():
    adapter = ClaudeCodeAdapter()
    assert isinstance(adapter, SessionAdapter)


def test_generic_adapter_satisfies_protocol():
    adapter = GenericAdapter()
    assert isinstance(adapter, SessionAdapter)


# ---------------------------------------------------------------------------
# AC 3 — ClaudeCodeAdapter.ingest normalizes StreamEvent
# ---------------------------------------------------------------------------


def test_claude_code_adapter_normalizes_stream_event():
    """ingest() must produce a SessionEvent with correct semantics."""
    now = datetime.now(timezone.utc)
    raw = StreamEvent(
        timestamp=now,
        event_type="text",
        content="We agreed on SurrealDB for the graph store.",
        session_id="sess-001",
        metadata={"source": "session_import", "index": 0},
    )
    adapter = ClaudeCodeAdapter()
    event = adapter.ingest(raw)

    assert event.event_type == "text"
    assert event.content == "We agreed on SurrealDB for the graph store."
    assert event.session_id == "sess-001"
    assert event.timestamp == now
    assert event.metadata == {"source": "session_import", "index": 0}


def test_claude_code_adapter_ingest_dict_input():
    """ingest() also accepts plain dicts (for test convenience)."""
    adapter = ClaudeCodeAdapter()
    event = adapter.ingest({"event_type": "tool_use", "content": "ran pytest", "session_id": "s2"})
    assert event.event_type == "tool_use"
    assert event.content == "ran pytest"


def test_claude_code_adapter_enumerate_turns_returns_list():
    adapter = ClaudeCodeAdapter()
    turns = adapter.enumerate_turns("any-session-id")
    assert isinstance(turns, list)


# ---------------------------------------------------------------------------
# AC 5 — Registry falls back to GenericAdapter for unknown sources
# ---------------------------------------------------------------------------


def test_adapter_registry_resolves_claude_code():
    adapter = resolve("claude_code")
    assert isinstance(adapter, ClaudeCodeAdapter)


def test_adapter_registry_resolves_unknown_source_to_generic():
    adapter = resolve("foobar")
    assert isinstance(adapter, GenericAdapter)


def test_generic_adapter_ingest_stream_event():
    """GenericAdapter accepts the same input shapes as ClaudeCodeAdapter."""
    raw = StreamEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="text",
        content="cursor event content",
        session_id="cursor-sess",
    )
    adapter = GenericAdapter()
    event = adapter.ingest(raw)
    assert event.content == "cursor event content"
    assert event.event_type == "text"
