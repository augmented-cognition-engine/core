# tests/test_research_agent_timeouts.py
"""Tests for ResearchAgent timeout/circuit-breaker behavior.

Before this fix: a hung LLM call in any step could block run() for hours with
no circuit breaker. User reported a 1h+ hang in practice.

After: a global deadline wraps run() and per-step LLM calls get their own
timeout. On expiry, run() returns a partial ResearchResult with a clear error
synthesis rather than propagating a bare asyncio.TimeoutError.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.research.agent import ResearchAgent


@pytest.mark.asyncio
async def test_run_has_global_deadline_constant():
    """Module must expose a global deadline constant that is bounded and sane."""
    from core.engine.research.agent import GLOBAL_RESEARCH_DEADLINE_S

    assert 60 <= GLOBAL_RESEARCH_DEADLINE_S <= 600


@pytest.mark.asyncio
async def test_run_returns_timeout_result_instead_of_hanging():
    """If the pipeline exceeds the global deadline, run() returns a result, not raises."""
    agent = ResearchAgent(product_id="product:test")

    async def _hang(*a, **kw):
        await asyncio.sleep(3600)
        return []

    # Replace the first I/O step with something that hangs forever
    with patch.object(ResearchAgent, "_step1_expand", new=AsyncMock(side_effect=_hang)):
        # Override the deadline to a tiny value so the test doesn't actually wait
        with patch("core.engine.research.agent.GLOBAL_RESEARCH_DEADLINE_S", 0.5):
            result = await agent.run(topic="test", research_type="grounded_how_to")

    assert result is not None
    assert "timeout" in result.synthesis.lower() or "timed out" in result.synthesis.lower()
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_per_step_llm_timeout_constant():
    """Each LLM step must also have a per-call timeout smaller than the global one."""
    from core.engine.research.agent import GLOBAL_RESEARCH_DEADLINE_S, PER_STEP_LLM_TIMEOUT_S

    assert 5 <= PER_STEP_LLM_TIMEOUT_S <= GLOBAL_RESEARCH_DEADLINE_S


@pytest.mark.asyncio
async def test_step1_expand_falls_back_on_llm_timeout():
    """If the step 1 LLM call hangs past its per-step timeout, fall back to default queries."""
    agent = ResearchAgent(product_id="product:test")

    class _HangingLLM:
        async def complete_json(self, *a, **kw):
            await asyncio.sleep(3600)
            return {}

        async def complete(self, *a, **kw):
            await asyncio.sleep(3600)
            return ""

    with patch("core.engine.core.llm.get_llm", return_value=_HangingLLM()):
        with patch("core.engine.research.agent.PER_STEP_LLM_TIMEOUT_S", 0.3):
            queries = await agent._step1_expand(topic="x", ceiling="sonnet")

    # Fallback queries should be used instead of hanging
    assert queries
    assert any("x" in q for q in queries)


@pytest.mark.asyncio
async def test_step5_discipline_falls_back_on_llm_timeout():
    """If the step 5 LLM call hangs past its per-step timeout, fall back to default discipline."""
    agent = ResearchAgent(product_id="product:test")

    class _HangingLLM:
        async def complete_json(self, *a, **kw):
            await asyncio.sleep(3600)
            return {}

    with patch("core.engine.core.llm.get_llm", return_value=_HangingLLM()):
        with patch("core.engine.research.agent.PER_STEP_LLM_TIMEOUT_S", 0.3):
            discipline = await agent._step5_discipline(topic="x", ceiling="sonnet")

    assert discipline == "architecture"


@pytest.mark.asyncio
async def test_step10_synthesize_falls_back_on_llm_timeout():
    """If the step 10 LLM synthesis call hangs, fall back to a concat of sources."""
    from core.engine.research.agent import ClassifiedResult, SearchResult
    from core.engine.research.source_registry import SourceClass

    agent = ResearchAgent(product_id="product:test")

    class _HangingLLM:
        async def complete(self, *a, **kw):
            await asyncio.sleep(3600)
            return ""

    ranked = [
        ClassifiedResult(
            result=SearchResult(url="https://a.com", title="A", content="some content about the topic"),
            source_class=SourceClass.REFERENCE,
            confidence=None,  # type: ignore[arg-type]
        )
    ]

    with patch("core.engine.core.llm.get_llm", return_value=_HangingLLM()):
        with patch("core.engine.research.agent.PER_STEP_LLM_TIMEOUT_S", 0.3):
            out = await agent._step10_synthesize(
                ranked=ranked,
                extracted=[],
                repos=[],
                topic="x",
                discipline="architecture",
                research_type="grounded_how_to",
                model=None,
                ceiling="sonnet",
            )

    # Must return something — fallback to joined source contents
    assert out
    assert out != ""
