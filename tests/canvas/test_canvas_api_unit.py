"""Canvas REST API unit tests (non-e2e, mock-patched).

These test the /framework endpoint fix:
- Must emit EVENT_FRAMEWORK_COMPLETED (not artifact.placed)
- Must include tldraw_shape_id in the completed event payload
- Must emit WATCHING → DRAFTING → WATCHING state transitions
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.canvas.event_protocol import (
    EVENT_FRAMEWORK_COMPLETED,
    EVENT_PARTICIPANT_STATE_CHANGED,
)


@pytest.mark.asyncio
async def test_framework_endpoint_emits_framework_completed_not_artifact_placed():
    """The /framework endpoint must emit framework.completed, not artifact.placed."""
    emitted_events: list[dict] = []

    async def fake_broadcast(event: dict) -> None:
        emitted_events.append(event)

    fake_spec = MagicMock()
    fake_spec.shape_kind = "framework_artifact"
    fake_spec.payload = {
        "framework_kind": "trade_off_matrix",
        "title": "T",
        "options": [],
        "axes": [],
        "recommendation": "A",
    }

    fake_session = MagicMock()
    fake_session.project_id = "product:test"

    with (
        patch("core.engine.api.canvas._persist_and_broadcast", side_effect=fake_broadcast),
        patch("core.engine.api.canvas.persistence.get_session", return_value=fake_session),
        patch("core.engine.api.canvas.persistence.list_artifacts", return_value=[]),
        patch("core.engine.api.canvas.persistence.upsert_artifact", return_value=MagicMock()),
        patch("core.engine.api.canvas._get_prior_decisions", return_value=[]),
        patch("core.engine.api.canvas.render_via_orchestration", new=AsyncMock(return_value=fake_spec)),
    ):
        from core.engine.api.canvas import RequestFrameworkIn, request_framework

        body = RequestFrameworkIn(framework_kind="trade_off_matrix", prompt="Test?")
        result = await request_framework("canvas_session:test", body)

    event_types = [e["event_type"] for e in emitted_events]
    assert EVENT_FRAMEWORK_COMPLETED in event_types, f"Got: {event_types}"
    assert "artifact.placed" not in event_types, "artifact.placed must not be emitted for framework results"

    completed_event = next(e for e in emitted_events if e["event_type"] == EVENT_FRAMEWORK_COMPLETED)
    assert "tldraw_shape_id" in completed_event["payload"]
    assert completed_event["payload"]["tldraw_shape_id"].startswith("shape:fw_")


@pytest.mark.asyncio
async def test_framework_endpoint_emits_state_transitions():
    """State must transition WATCHING→DRAFTING before render, DRAFTING→WATCHING after."""
    emitted_events: list[dict] = []

    async def fake_broadcast(event: dict) -> None:
        emitted_events.append(event)

    fake_spec = MagicMock()
    fake_spec.shape_kind = "framework_artifact"
    fake_spec.payload = {"framework_kind": "trade_off_matrix"}

    fake_session = MagicMock()
    fake_session.project_id = "product:test"

    with (
        patch("core.engine.api.canvas._persist_and_broadcast", side_effect=fake_broadcast),
        patch("core.engine.api.canvas.persistence.get_session", return_value=fake_session),
        patch("core.engine.api.canvas.persistence.list_artifacts", return_value=[]),
        patch("core.engine.api.canvas.persistence.upsert_artifact", return_value=MagicMock()),
        patch("core.engine.api.canvas._get_prior_decisions", return_value=[]),
        patch("core.engine.api.canvas.render_via_orchestration", new=AsyncMock(return_value=fake_spec)),
    ):
        from core.engine.api.canvas import RequestFrameworkIn, request_framework

        body = RequestFrameworkIn(framework_kind="trade_off_matrix", prompt="Test?")
        await request_framework("canvas_session:test", body)

    state_events = [e for e in emitted_events if e["event_type"] == EVENT_PARTICIPANT_STATE_CHANGED]
    states = [e["payload"]["new_state"] for e in state_events]
    assert "drafting" in states, f"Expected 'drafting' in states, got: {states}"
    assert "watching" in states, f"Expected 'watching' in states, got: {states}"
    # drafting must come before watching
    assert states.index("drafting") < states.index("watching"), (
        f"'drafting' must precede 'watching', got order: {states}"
    )


@pytest.mark.asyncio
async def test_get_forward_momentum_helper_returns_list():
    """_get_forward_momentum must return a list (even when DB is unavailable)."""
    from core.engine.api.canvas import _get_forward_momentum

    # If DB is unreachable, should return empty list not raise
    with patch("core.engine.core.db.pool") as mock_pool:
        mock_pool.connection.side_effect = Exception("DB unavailable")
        result = await _get_forward_momentum("product:test")
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_patch_decision_endpoint_exists():
    """PATCH /canvas/decisions/{id} route must exist and import PatchDecisionIn."""
    import inspect

    from core.engine.api.canvas import PatchDecisionIn, patch_decision

    assert inspect.iscoroutinefunction(patch_decision)
    body = PatchDecisionIn(what_it_led_to="test")
    assert body.what_it_led_to == "test"
