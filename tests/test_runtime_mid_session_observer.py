"""Tests for mid-session observer (Tier 2 capture pipeline)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.runtime.mid_session_observer import MidSessionObserver
from core.engine.runtime.models import AssistantMessage, UserMessage


def _make_messages(n_turns: int) -> list:
    """Build a conversation with n_turns user/assistant pairs."""
    msgs = []
    for i in range(n_turns):
        msgs.append(UserMessage(content=f"User message {i}: how do I implement feature {i}?"))
        msgs.append(
            AssistantMessage(
                content=f"Assistant response {i}: use the factory pattern here, it allows decoupling",
                model="claude-haiku-4-5-20251001",
                tool_use=[],
            )
        )
    return msgs


# ---------------------------------------------------------------------------
# Turn counting
# ---------------------------------------------------------------------------


def test_turn_count_starts_at_zero():
    obs = MidSessionObserver("product:test")
    assert obs.turn_count == 0


def test_turn_count_increments():
    obs = MidSessionObserver("product:test")
    obs.record_turn([])
    obs.record_turn([])
    assert obs.turn_count == 2


def test_scan_does_not_fire_before_interval():
    obs = MidSessionObserver("product:test", scan_interval=5)
    fired = []

    with patch.object(obs, "_fire", side_effect=lambda msgs: fired.append(1)):
        for _ in range(4):
            obs.record_turn([])

    assert len(fired) == 0


def test_scan_fires_at_interval():
    obs = MidSessionObserver("product:test", scan_interval=5)
    fired = []

    with patch.object(obs, "_fire", side_effect=lambda msgs: fired.append(1)):
        for _ in range(5):
            obs.record_turn([])

    assert len(fired) == 1


def test_scan_fires_at_every_interval():
    obs = MidSessionObserver("product:test", scan_interval=5)
    fired = []

    with patch.object(obs, "_fire", side_effect=lambda msgs: fired.append(1)):
        for _ in range(15):
            obs.record_turn([])

    assert len(fired) == 3  # at turns 5, 10, 15


def test_custom_scan_interval():
    obs = MidSessionObserver("product:test", scan_interval=3)
    fired = []

    with patch.object(obs, "_fire", side_effect=lambda msgs: fired.append(1)):
        for _ in range(9):
            obs.record_turn([])

    assert len(fired) == 3  # at turns 3, 6, 9


# ---------------------------------------------------------------------------
# Scan — excerpt building
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_skips_empty_messages():
    obs = MidSessionObserver("product:test")
    # Should complete without error and without calling LLM
    with patch("core.engine.core.llm.get_llm") as mock_llm:
        await obs._scan([])
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_scan_skips_short_content():
    obs = MidSessionObserver("product:test")
    messages = [
        UserMessage(content="hi"),
        AssistantMessage(content="hello", model="claude-haiku-4-5-20251001", tool_use=[]),
    ]
    with patch("core.engine.core.llm.get_llm") as mock_llm:
        await obs._scan(messages)
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_scan_filters_meta_messages():
    obs = MidSessionObserver("product:test")
    messages = [
        UserMessage(content="context compacted" * 20, is_meta=True),
        UserMessage(content="fix the auth bug" * 10),
        AssistantMessage(
            content="I found the issue: the token expires after 1 hour" * 5,
            model="claude-haiku-4-5-20251001",
            tool_use=[],
        ),
    ]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": []})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            await obs._scan(messages)

    prompt_text = mock_llm.complete_json.call_args[0][0]
    # Meta message content should not appear in excerpt
    assert "context compacted" not in prompt_text


@pytest.mark.asyncio
async def test_scan_uses_sliding_window():
    """Only the last _WINDOW_TURNS*2 messages should appear in the excerpt."""
    obs = MidSessionObserver("product:test")
    messages = _make_messages(20)  # 20 turns = 40 messages, window = 10 turns = 20 messages

    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": []})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            await obs._scan(messages)

    prompt_text = mock_llm.complete_json.call_args[0][0]
    # Early messages should not appear
    assert "User message 0" not in prompt_text
    # Recent messages should appear
    assert "User message 19" in prompt_text


# ---------------------------------------------------------------------------
# Scan — LLM call and write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_calls_haiku_for_classification():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": []})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch(
            "core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"
        ) as mock_route:
            await obs._scan(messages)

    mock_route.assert_called_with("mid_session_scan")
    mock_llm.complete_json.assert_called_once()


@pytest.mark.asyncio
async def test_scan_writes_decision_finding():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    findings = [
        {
            "type": "decision",
            "content": "Use async context managers for DB connections",
            "domain": "architecture",
            "confidence": 0.9,
        }
    ]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": findings})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock()) as mock_capture:
                await obs._scan(messages)

    mock_capture.assert_called_once_with(
        observation_type="decision",
        content="Use async context managers for DB connections",
        domain_path="architecture",
        confidence=0.9,
        product_id="product:test",
    )


@pytest.mark.asyncio
async def test_scan_maps_discovery_to_learning():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    findings = [
        {
            "type": "discovery",
            "content": "The observer runs before the synthesizer",
            "domain": "architecture",
            "confidence": 0.8,
        }
    ]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": findings})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock()) as mock_capture:
                await obs._scan(messages)

    # discovery → learning (ace_capture's accepted types)
    call_kwargs = mock_capture.call_args[1]
    assert call_kwargs["observation_type"] == "learning"


@pytest.mark.asyncio
async def test_scan_skips_invalid_observation_types():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    findings = [
        {"type": "unknown_type", "content": "some content", "domain": "architecture", "confidence": 0.7},
        {"type": "error", "content": "session_memory not persisting", "domain": "data", "confidence": 0.9},
    ]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": findings})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock()) as mock_capture:
                await obs._scan(messages)

    # Only the valid "error" finding should be written
    assert mock_capture.call_count == 1
    call_kwargs = mock_capture.call_args[1]
    assert call_kwargs["observation_type"] == "error"


@pytest.mark.asyncio
async def test_scan_skips_empty_content():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    findings = [{"type": "decision", "content": "", "domain": "architecture", "confidence": 0.8}]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": findings})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock()) as mock_capture:
                await obs._scan(messages)

    mock_capture.assert_not_called()


@pytest.mark.asyncio
async def test_scan_handles_multiple_findings():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    findings = [
        {"type": "decision", "content": "Use SurrealDB for everything", "domain": "data_modeling", "confidence": 0.9},
        {
            "type": "error",
            "content": "Token tracking double-counts tool calls",
            "domain": "observability",
            "confidence": 0.85,
        },
        {
            "type": "pattern",
            "content": "Always use get_llm() not raw ClaudeProvider",
            "domain": "architecture",
            "confidence": 0.95,
        },
    ]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": findings})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock()) as mock_capture:
                await obs._scan(messages)

    assert mock_capture.call_count == 3


@pytest.mark.asyncio
async def test_scan_handles_llm_failure_gracefully():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    with patch("core.engine.core.llm.get_llm", side_effect=RuntimeError("LLM unavailable")):
        with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock()) as mock_capture:
            # Should not raise
            await obs._scan(messages)

    mock_capture.assert_not_called()


@pytest.mark.asyncio
async def test_scan_handles_ace_capture_failure_gracefully():
    obs = MidSessionObserver("product:test")
    messages = _make_messages(3)

    findings = [{"type": "decision", "content": "Use X", "domain": "architecture", "confidence": 0.8}]
    mock_llm = MagicMock()
    mock_llm.complete_json = AsyncMock(return_value={"findings": findings})

    with patch("core.engine.core.llm.get_llm", return_value=mock_llm):
        with patch("core.engine.runtime.model_config.route_model", return_value="claude-haiku-4-5-20251001"):
            with patch("core.engine.mcp.tools.ace_capture", new=AsyncMock(side_effect=RuntimeError("DB down"))):
                # Should not raise
                await obs._scan(messages)


# ---------------------------------------------------------------------------
# Concurrent scan guard
# ---------------------------------------------------------------------------


def test_fire_skips_if_previous_still_running():
    obs = MidSessionObserver("product:test")

    # Simulate a pending task that hasn't completed
    mock_task = MagicMock()
    mock_task.done.return_value = False
    obs._pending = mock_task

    scheduled = []
    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance
        mock_loop_instance.create_task = MagicMock(side_effect=lambda coro: scheduled.append(coro) or MagicMock())

        obs._fire([])

    assert len(scheduled) == 0  # no new task scheduled


# ---------------------------------------------------------------------------
# Runtime integration
# ---------------------------------------------------------------------------


def test_runtime_creates_mid_session_observer_when_intelligence_enabled():
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=True, product_id="product:test")
    assert rt._mid_session_observer is not None
    assert rt._mid_session_observer._product_id == "product:test"


def test_runtime_skips_mid_session_observer_when_intelligence_disabled():
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)
    assert rt._mid_session_observer is None


def test_model_config_routes_mid_session_scan_to_haiku():
    from core.engine.runtime.model_config import MODEL_TIERS, route_model

    model = route_model("mid_session_scan")
    assert model == MODEL_TIERS["haiku"]
