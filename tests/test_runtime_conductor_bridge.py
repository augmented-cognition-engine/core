"""Tests for the conductor bridge."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.runtime.conductor_bridge import ConductorBridge


def test_bridge_creation():
    bridge = ConductorBridge(product_id="product:test")
    assert bridge is not None


@pytest.mark.asyncio
async def test_execute_spec():
    bridge = ConductorBridge(product_id="product:test")
    with patch.object(bridge, "execute_task", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "complete", "output": "Done"}
        result = await bridge.execute_spec("Build auth module")
        assert result["status"] == "complete"


def test_synthesis_mandate():
    """Bridge should enforce the synthesis mandate."""
    bridge = ConductorBridge(product_id="product:test")
    prompt = bridge.build_worker_prompt(
        task="Fix null pointer in auth.py:42",
        findings="Found user field undefined when session expires",
    )
    # Should NOT contain lazy delegation phrases
    assert "based on your findings" not in prompt.lower()
    assert "based on the research" not in prompt.lower()
    # Should be specific
    assert "auth.py" in prompt or "null pointer" in prompt
