"""Failure-contract tests for composed orchestration shells."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.engine.orchestration.agent import AgentConfig, AgentResult
from core.engine.orchestration.composition import ComposedAgentShell
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult


@pytest.mark.asyncio
async def test_composed_shell_preserves_nested_agent_failure():
    inner = AsyncMock()
    inner.execute = AsyncMock(
        return_value=PatternResult(
            run_id="run:test",
            pattern_name="pipeline",
            status="failed",
            agent_results=[AgentResult(agent_id="inner", status="failed", error="invalid provider model")],
        )
    )
    shell = ComposedAgentShell(
        AgentConfig(role="executor"),
        inner,
        PatternConfig(run_id="run:test", product_id="product:test"),
        [AgentConfig(role="analyst")],
    )

    result = await shell.execute("work")

    assert result.status == "failed"
    assert result.error == "invalid provider model"
