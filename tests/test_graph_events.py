# tests/test_graph_events.py
"""Tests for POST /graph/event — structured graph events from the capture hook."""

import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user

# scripts/ace_capture_hook.py is private client-side tooling — not shipped in
# the public export (scripts/ allow-list is minimal). The "Hook script unit
# tests" section below imports it directly; skip those when absent rather than
# denying this whole file, since the /graph/event API tests above cover
# shipped code and must keep running.
_ACE_CAPTURE_HOOK = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "ace_capture_hook.py"
_HAS_ACE_CAPTURE_HOOK = _ACE_CAPTURE_HOOK.is_file()
_skip_no_capture_hook = pytest.mark.skipif(
    not _HAS_ACE_CAPTURE_HOOK,
    reason="requires scripts/ace_capture_hook.py (private tooling, not shipped in the public export)",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    mock_user = {"sub": "user:test", "product": "product:test"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _mock_db_context(return_value=None):
    """Return a context manager mock that yields a fake DB with a .query() method."""
    db_mock = AsyncMock()
    db_mock.query = AsyncMock(return_value=return_value or [])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db_mock)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_graph_event_requires_auth():
    """Unauthenticated requests must be rejected."""
    client_no_auth = TestClient(app)
    resp = client_no_auth.post(
        "/graph/event",
        json={"type": "file_read", "file_path": "core/engine/core/db.py"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_graph_event_unknown_type_rejected(client):
    """Unknown event types should return 422."""
    resp = client.post(
        "/graph/event",
        json={"type": "mystery_event", "file_path": "core/engine/core/db.py"},
    )
    assert resp.status_code == 422


def test_file_modified_missing_path_rejected(client):
    """file_modified without file_path should return 422."""
    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context()
        resp = client.post(
            "/graph/event",
            json={"type": "file_modified", "context": "Fixed the bug"},
        )
    assert resp.status_code == 422


def test_commit_missing_message_rejected(client):
    """commit without commit_message should return 422."""
    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context()
        resp = client.post(
            "/graph/event",
            json={"type": "commit"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# file_modified
# ---------------------------------------------------------------------------


def test_file_modified_success(client):
    """file_modified with valid payload returns 200 and file_id."""
    decision_row = [{"id": "graph_decision:abc123", "title": "Modified db.py"}]

    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context(return_value=decision_row)
        resp = client.post(
            "/graph/event",
            json={
                "type": "file_modified",
                "file_path": "core/engine/core/db.py",
                "context": "Fixed parse_rows for SurrealDB v3",
                "session_id": "sess-001",
                "graph_id": "default",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "file_modified"
    assert "file_id" in data
    assert data["file_id"].startswith("graph_file:")


def test_file_modified_no_context(client):
    """file_modified without context still works (no decision node created)."""
    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context()
        resp = client.post(
            "/graph/event",
            json={
                "type": "file_modified",
                "file_path": "core/engine/core/db.py",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "file_modified"
    assert data["decision_id"] is None


# ---------------------------------------------------------------------------
# file_created
# ---------------------------------------------------------------------------


def test_file_created_success(client):
    """file_created returns 200 with file_id and decision_id."""
    decision_row = [{"id": "graph_decision:new001", "title": "Created graph_events.py"}]

    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context(return_value=decision_row)
        resp = client.post(
            "/graph/event",
            json={
                "type": "file_created",
                "file_path": "core/engine/api/graph_events.py",
                "context": "New endpoint for structured graph events",
                "session_id": "sess-002",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "file_created"
    assert "file_id" in data


# ---------------------------------------------------------------------------
# file_read
# ---------------------------------------------------------------------------


def test_file_read_success(client):
    """file_read increments access count — returns 200."""
    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context()
        resp = client.post(
            "/graph/event",
            json={
                "type": "file_read",
                "file_path": "engine/core/db.py",
                "session_id": "sess-003",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "file_read"
    assert data["file_id"] == "graph_file:engine_core_db_py"


def test_file_read_path_to_slug():
    """File path slug conversion is deterministic and safe."""
    from core.engine.api.graph_events import _file_path_to_slug

    assert _file_path_to_slug("engine/core/db.py") == "engine_core_db_py"
    assert _file_path_to_slug("tests/test_graph_events.py") == "tests_test_graph_events_py"
    assert _file_path_to_slug("") == "unknown"
    assert _file_path_to_slug("path/with spaces/file.py") == "path_with_spaces_file_py"


# ---------------------------------------------------------------------------
# test_run
# ---------------------------------------------------------------------------


def test_test_run_success(client):
    """test_run creates tests edges between test and source files."""
    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context()
        resp = client.post(
            "/graph/event",
            json={
                "type": "test_run",
                "file_path": "tests/test_api_capture.py",
                "source_files": ["core/engine/api/capture.py", "core/engine/capture/pipeline.py"],
                "session_id": "sess-004",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "test_run"
    assert data["edges_created"] == 2


def test_test_run_no_source_files(client):
    """test_run without source_files still works — 0 edges."""
    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context()
        resp = client.post(
            "/graph/event",
            json={
                "type": "test_run",
                "file_path": "tests/test_api_graph.py",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["edges_created"] == 0


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


def test_commit_success(client):
    """commit event creates a decision node from the commit message."""
    decision_row = [{"id": "graph_decision:commit001", "title": "feat: graph-aware hook"}]

    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context(return_value=decision_row)
        resp = client.post(
            "/graph/event",
            json={
                "type": "commit",
                "commit_message": "feat: graph-aware capture hook — tool calls update the knowledge graph",
                "commit_sha": "abc1234",
                "session_id": "sess-005",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["event"] == "commit"
    assert data["commit_sha"] == "abc1234"


def test_commit_multiline_message(client):
    """Multiline commit message — title is the first line only."""
    decision_row = [{"id": "graph_decision:commit002", "title": "feat: hook upgrade"}]

    with patch("core.engine.api.graph_events.pool") as mock_pool:
        mock_pool.connection.return_value = _mock_db_context(return_value=decision_row)
        resp = client.post(
            "/graph/event",
            json={
                "type": "commit",
                "commit_message": "feat: hook upgrade\n\nMore details about the change here.\nAdditional context.",
            },
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Hook script unit tests
# ---------------------------------------------------------------------------


@_skip_no_capture_hook
def test_hook_build_graph_events_edit():
    """Edit tool call produces a file_modified event."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/home/user/Projects/ace/engine/core/db.py",
            "old_string": "old code",
            "new_string": "new code",
        },
        "tool_response": {},
        "session_id": "test-session",
    }
    events = build_graph_events(payload, [])
    assert len(events) == 1
    assert events[0]["type"] == "file_modified"
    assert "db.py" in events[0]["file_path"]


@_skip_no_capture_hook
def test_hook_build_graph_events_write():
    """Write tool call produces a file_created event."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "engine/api/new_module.py",
            "content": "# new file\n",
        },
        "tool_response": {},
        "session_id": "test-session",
    }
    events = build_graph_events(payload, [])
    assert len(events) == 1
    assert events[0]["type"] == "file_created"
    assert events[0]["file_path"] == "engine/api/new_module.py"


@_skip_no_capture_hook
def test_hook_build_graph_events_read():
    """Read tool call produces a file_read event."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/home/user/Projects/ace/engine/core/db.py"},
        "tool_response": {},
        "session_id": "test-session",
    }
    events = build_graph_events(payload, [])
    assert len(events) == 1
    assert events[0]["type"] == "file_read"


@_skip_no_capture_hook
def test_hook_build_graph_events_bash_pytest():
    """Bash pytest command produces a test_run event."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/test_api_capture.py -v"},
        "tool_response": {},
        "session_id": "test-session",
    }
    events = build_graph_events(payload, [])
    assert len(events) == 1
    assert events[0]["type"] == "test_run"
    assert "test_api_capture.py" in events[0]["file_path"]


@_skip_no_capture_hook
def test_hook_build_graph_events_bash_commit():
    """Bash git commit command produces a commit event."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'feat: upgrade capture hook'"},
        "tool_response": {},
        "session_id": "test-session",
    }
    events = build_graph_events(payload, [])
    assert any(e["type"] == "commit" for e in events)
    commit_event = next(e for e in events if e["type"] == "commit")
    assert "upgrade capture hook" in commit_event["commit_message"]


@_skip_no_capture_hook
def test_hook_build_graph_events_bash_ls():
    """Bash ls command produces no events (not interesting)."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la /home/user/Projects/ace"},
        "tool_response": {"stdout": "total 48\ndrwxr-xr-x..."},
        "session_id": "test-session",
    }
    events = build_graph_events(payload, [])
    assert events == []


@_skip_no_capture_hook
def test_hook_build_graph_events_malformed_input():
    """Malformed or empty tool_input produces no events (no crash)."""
    from scripts.ace_capture_hook import build_graph_events

    payload = {
        "tool_name": "Edit",
        "tool_input": None,
        "tool_response": None,
        "session_id": "",
    }
    # Should not raise
    events = build_graph_events(payload, [])
    assert events == []


@_skip_no_capture_hook
def test_hook_extract_context_from_lines():
    """Context is extracted from the most recent assistant text block."""
    from scripts.ace_capture_hook import extract_context_from_lines

    lines = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "I'll fix this bug now."}]}},
        {"type": "user", "message": {"content": "please fix it"}},
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Updated the parse_rows helper to handle v3 format correctly."}]
            },
        },
    ]
    ctx = extract_context_from_lines(lines)
    assert "parse_rows" in ctx


@_skip_no_capture_hook
def test_hook_skip_self_calls():
    """Hook ignores Bash commands that invoke the hook itself."""
    import io
    import json as _json

    from scripts.ace_capture_hook import main

    payload = _json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python scripts/ace_capture_hook.py"},
            "tool_response": {},
            "session_id": "self-test",
        }
    )

    # Should exit cleanly without making any HTTP calls
    import scripts.ace_capture_hook as hook_module

    with (
        patch.object(hook_module, "get_token", return_value="fake-token") as mock_token,
        patch.object(hook_module, "post_graph_event", return_value=True) as mock_post,
        patch("sys.stdin", io.StringIO(payload)),
    ):
        main()

    mock_token.assert_not_called()
    mock_post.assert_not_called()
