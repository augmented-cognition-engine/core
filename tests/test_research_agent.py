"""Tests for ResearchAgent — pure logic steps tested directly; LLM/web steps mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.research.agent import (
    ClassifiedResult,
    ResearchAgent,
    ResearchResult,
    SearchResult,
)
from core.engine.research.source_registry import SourceClass

# --- SearchResult ---


def test_search_result_extracts_domain():
    r = SearchResult(url="https://owasp.org/attacks/xss", title="XSS", content="desc")
    assert "owasp.org" in r.source_domain


def test_search_result_empty_url():
    r = SearchResult(url="", title="t", content="c")
    assert r.source_domain == ""


# --- step3_dedup ---


def test_dedup_removes_exact_duplicate_urls():
    agent = ResearchAgent()
    results = [
        SearchResult(url="https://example.com/a", title="A", content=""),
        SearchResult(url="https://example.com/a", title="A dup", content=""),
        SearchResult(url="https://example.com/b", title="B", content=""),
    ]
    deduped = agent._step3_dedup(results)
    assert len(deduped) == 2


def test_dedup_treats_trailing_slash_as_same():
    agent = ResearchAgent()
    results = [
        SearchResult(url="https://example.com/a/", title="A", content=""),
        SearchResult(url="https://example.com/a", title="A no slash", content=""),
    ]
    deduped = agent._step3_dedup(results)
    assert len(deduped) == 1


def test_dedup_skips_empty_urls():
    agent = ResearchAgent()
    results = [
        SearchResult(url="", title="no url", content=""),
        SearchResult(url="https://example.com", title="ok", content=""),
    ]
    deduped = agent._step3_dedup(results)
    assert len(deduped) == 1


# --- step4_classify ---


def test_classify_reference_url():
    agent = ResearchAgent()
    results = [SearchResult(url="https://owasp.org/top-ten", title="OWASP", content="security")]
    classified = agent._step4_classify(results)
    assert len(classified) == 1
    assert classified[0].source_class == SourceClass.REFERENCE


def test_classify_drops_noise():
    agent = ResearchAgent()
    results = [SearchResult(url="https://spam-seo-junk.example/", title="junk", content="")]
    with patch("core.engine.research.agent.classify_url", return_value=SourceClass.NOISE):
        classified = agent._step4_classify(results)
    assert classified == []


def test_classify_assigns_confidence():
    agent = ResearchAgent()
    results = [SearchResult(url="https://owasp.org/top-ten", title="OWASP", content="sec")]
    classified = agent._step4_classify(results)
    assert classified[0].confidence.value > 0


# --- step9_rerank ---


def test_rerank_reference_before_signal():
    agent = ResearchAgent()
    from core.engine.research.confidence import compute_confidence

    reference = ClassifiedResult(
        result=SearchResult(url="https://owasp.org", title="R", content=""),
        source_class=SourceClass.REFERENCE,
        confidence=compute_confidence(SourceClass.REFERENCE),
    )
    signal = ClassifiedResult(
        result=SearchResult(url="https://medium.com/x", title="S", content=""),
        source_class=SourceClass.SIGNAL,
        confidence=compute_confidence(SourceClass.SIGNAL),
    )
    ranked = agent._step9_rerank([signal, reference])
    assert ranked[0].source_class == SourceClass.REFERENCE


def test_rerank_caps_at_10():
    agent = ResearchAgent()
    from core.engine.research.confidence import compute_confidence

    results = [
        ClassifiedResult(
            result=SearchResult(url=f"https://signal-{i}.com", title=f"S{i}", content=""),
            source_class=SourceClass.SIGNAL,
            confidence=compute_confidence(SourceClass.SIGNAL),
        )
        for i in range(15)
    ]
    ranked = agent._step9_rerank(results)
    assert len(ranked) <= 10


# --- ResearchAgent creation ---


def test_agent_creation():
    agent = ResearchAgent()
    assert agent is not None


def test_agent_with_product_id():
    agent = ResearchAgent(product_id="product:myapp")
    assert agent._product_id == "product:myapp"


# --- async / type2 tests ---


@pytest.mark.asyncio
async def test_run_invalid_research_type_raises():
    agent = ResearchAgent()
    with pytest.raises(ValueError, match="Unknown research_type"):
        await agent.run("topic", research_type="bogus_type")


@pytest.mark.asyncio
async def test_type2_internal_confidence_zero_on_exception():
    from core.engine.mcp import tools as mcp_tools

    agent = ResearchAgent(product_id="product:test")
    with patch.object(mcp_tools, "ace_search", new=AsyncMock(side_effect=RuntimeError("db down"))):
        result = await agent.run("topic", research_type="internal")
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_type2_internal_confidence_zero_on_no_results():
    from core.engine.mcp import tools as mcp_tools

    agent = ResearchAgent(product_id="product:test")
    mock_empty = {"results": [], "count": 0}
    with patch.object(mcp_tools, "ace_search", new=AsyncMock(return_value=mock_empty)):
        result = await agent.run("topic", research_type="internal")
    assert result.confidence == 0.0


# --- helper ---


def _make_mock_search_results() -> list[SearchResult]:
    return [
        SearchResult(url="https://owasp.org/top-ten", title="OWASP Top 10", content="XSS vulnerability guide"),
        SearchResult(url="https://medium.com/article", title="Medium Article", content="some signal content"),
        SearchResult(url="https://martinfowler.com/bliki/", title="Martin Fowler", content="architecture patterns"),
    ]


# --- pipeline integration tests ---


@pytest.mark.asyncio
async def test_pipeline_grounded_how_to_returns_result():
    agent = ResearchAgent(product_id="product:test")

    with (
        patch.object(agent, "_step1_expand", new=AsyncMock(return_value=["how to implement rate limiting"])),
        patch.object(agent, "_step2_search", new=AsyncMock(return_value=_make_mock_search_results())),
        patch.object(agent, "_step5_discipline", new=AsyncMock(return_value="security")),
        patch.object(agent, "_step7_extract", new=AsyncMock(return_value=["extracted content"])),
        patch.object(agent, "_step8_repos", new=AsyncMock(return_value=["express/rate-limit (5k★): Rate limiting"])),
        patch.object(agent, "_step10_synthesize", new=AsyncMock(return_value="Use token bucket algorithm.")),
        patch.object(agent, "_step11_write", new=AsyncMock(return_value="obs:123")),
    ):
        result = await agent.run("rate limiting", research_type="grounded_how_to")

    assert isinstance(result, ResearchResult)
    assert result.topic == "rate limiting"
    assert result.discipline == "security"
    assert result.synthesis == "Use token bucket algorithm."
    assert result.observation_id == "obs:123"
    assert len(result.evidence) > 0


@pytest.mark.asyncio
async def test_pipeline_competitive_skips_repo_enrichment():
    agent = ResearchAgent(product_id="product:test")
    repos_called_with = []

    async def mock_repos(topic):
        repos_called_with.append(topic)
        return []

    with (
        patch.object(agent, "_step1_expand", new=AsyncMock(return_value=["competitors"])),
        patch.object(agent, "_step2_search", new=AsyncMock(return_value=_make_mock_search_results())),
        patch.object(agent, "_step5_discipline", new=AsyncMock(return_value="architecture")),
        patch.object(agent, "_step7_extract", new=AsyncMock(return_value=[])),
        patch.object(agent, "_step8_repos", new=mock_repos),
        patch.object(agent, "_step10_synthesize", new=AsyncMock(return_value="Competitive landscape...")),
        patch.object(agent, "_step11_write", new=AsyncMock(return_value="")),
    ):
        await agent.run("PM tools landscape", research_type="competitive")

    # competitive type must NOT call _step8_repos
    assert repos_called_with == []


@pytest.mark.asyncio
async def test_pipeline_greenfield_uses_sonnet():
    """Greenfield synthesis passes model=None — route_model() selects Sonnet (Opus is opt-in only)."""
    agent = ResearchAgent(product_id="product:test")
    synthesize_calls = []

    async def mock_synthesize(ranked, extracted, repos, topic, discipline, research_type, model, ceiling):
        synthesize_calls.append({"model": model, "type": research_type})
        return "Greenfield synthesis"

    with (
        patch.object(agent, "_step1_expand", new=AsyncMock(return_value=["greenfield topic"])),
        patch.object(agent, "_step2_search", new=AsyncMock(return_value=_make_mock_search_results())),
        patch.object(agent, "_step5_discipline", new=AsyncMock(return_value="architecture")),
        patch.object(agent, "_step7_extract", new=AsyncMock(return_value=[])),
        patch.object(agent, "_step8_repos", new=AsyncMock(return_value=[])),
        patch.object(agent, "_step10_synthesize", new=mock_synthesize),
        patch.object(agent, "_step11_write", new=AsyncMock(return_value="")),
    ):
        await agent.run("build an AI-powered PM tool", research_type="greenfield")

    # model=None means route_model() picks Sonnet — Opus is not used by default
    assert synthesize_calls[0]["model"] is None


@pytest.mark.asyncio
async def test_pipeline_rerequeries_when_no_reference_sources():
    agent = ResearchAgent(product_id="product:test")
    search_call_count = 0

    async def mock_search(queries):
        nonlocal search_call_count
        search_call_count += 1
        # Return only SIGNAL sources (medium.com)
        return [SearchResult(url="https://medium.com/x", title="Blog", content="content")]

    with (
        patch.object(agent, "_step1_expand", new=AsyncMock(return_value=["niche obscure topic"])),
        patch.object(agent, "_step2_search", new=mock_search),
        patch.object(agent, "_step5_discipline", new=AsyncMock(return_value="architecture")),
        patch.object(agent, "_step7_extract", new=AsyncMock(return_value=[])),
        patch.object(agent, "_step8_repos", new=AsyncMock(return_value=[])),
        patch.object(agent, "_step10_synthesize", new=AsyncMock(return_value="synthesis")),
        patch.object(agent, "_step11_write", new=AsyncMock(return_value="")),
    ):
        await agent.run("niche obscure topic", research_type="grounded_how_to")

    # step2 called twice — once initial, once for gap re-query (no REFERENCE sources found)
    assert search_call_count == 2


@pytest.mark.asyncio
async def test_type2_internal_calls_ace_search():
    agent = ResearchAgent(product_id="product:test")

    mock_search_result = {"results": [{"content": "Rate limiting uses token bucket algorithm"}], "count": 1}

    from core.engine.mcp import tools as mcp_tools

    with patch.object(mcp_tools, "ace_search", new=AsyncMock(return_value=mock_search_result)):
        result = await agent.run("rate limiting", research_type="internal")

    assert result.research_type == "internal"
    assert result.evidence == []
    assert result.confidence == 0.9  # success path


@pytest.mark.asyncio
async def test_invalid_research_type_raises():
    agent = ResearchAgent()
    with pytest.raises(ValueError, match="Unknown research_type"):
        await agent.run("topic", research_type="made_up_type")


@pytest.mark.asyncio
async def test_step11_skipped_when_no_product_id():
    agent = ResearchAgent(product_id="")
    obs_id = await agent._step11_write("synthesis", "architecture", "topic", "")
    assert obs_id == ""


@pytest.mark.asyncio
async def test_step1_falls_back_on_llm_failure():
    agent = ResearchAgent()
    with patch("core.engine.core.llm.get_llm", side_effect=ImportError("no llm")):
        queries = await agent._step1_expand("rate limiting", "sonnet")
    assert len(queries) >= 1
    assert "rate limiting" in queries[0]
