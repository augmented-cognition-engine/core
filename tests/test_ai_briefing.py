"""Tests for the AI-side briefing primitive.

Covers AIBriefing dataclass shape, render_briefing() rendering rules,
build_briefing() resilience when substrate is unreachable, and the
end-to-end briefing_for_dispatched_ai() convenience wrapper.

Substrate queries are mocked — these are unit tests, not integration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.ai_briefing import (
    AIBriefing,
    briefing_for_dispatched_ai,
    build_briefing,
    invalidate_briefing_cache,
    render_briefing,
)
from core.engine.ai_briefing.builder import _briefing_cache

# ---------------------------------------------------------------------------
# AIBriefing dataclass shape
# ---------------------------------------------------------------------------


def test_ai_briefing_defaults():
    """Empty AIBriefing has sensible defaults — no None pitfalls."""
    b = AIBriefing()
    assert b.architecture_digest == ""
    assert b.current_phase == ""
    assert b.recent_decisions == []
    assert b.active_capabilities == []
    assert b.known_gaps == []
    assert b.active_meta_skills == []
    assert b.product_id == ""


# ---------------------------------------------------------------------------
# render_briefing
# ---------------------------------------------------------------------------


def test_render_briefing_empty_returns_empty_string():
    """Render of empty briefing is empty — no '## ACE Substrate' header for nothing."""
    out = render_briefing(AIBriefing())
    assert out == ""


def test_render_briefing_architecture_only():
    """Only architecture_digest renders — sections without content are dropped."""
    b = AIBriefing(architecture_digest="ACE has 9 layers.")
    out = render_briefing(b)
    assert "ACE Substrate" in out
    assert "9 layers" in out
    # No empty section headers
    assert "Recent Decisions" not in out
    assert "Already Built" not in out
    assert "Known Gaps" not in out
    assert "Active Meta-Intelligences" not in out


def test_render_briefing_leads_with_roadmap():
    """roadmap_headline renders, FIRST — the partner reaches the plan through its own front door.
    (Regression: the field was computed in build_briefing but never rendered, hiding the roadmap.)"""
    b = AIBriefing(
        roadmap_headline="Now: Phase 2 · Close the Loop (backward-flow edges)", architecture_digest="ACE has 9 layers."
    )
    out = render_briefing(b)
    assert "Current Roadmap" in out
    assert "Phase 2 · Close the Loop" in out
    # it leads — the roadmap section comes before the substrate section
    assert out.index("Current Roadmap") < out.index("ACE Substrate")


def test_render_briefing_has_no_dead_content_fields():
    """Dead-field guard: every CONTENT field of AIBriefing must be surfaced by render_briefing.
    Catches the bug class where a field is computed in the builder but never rendered (the
    roadmap_headline regression). Metadata fields intentionally absent from the prefix are allowlisted.
    If you add an AIBriefing content field, render it AND add its marker here — or this test fails."""
    import dataclasses

    NOT_RENDERED = {"current_phase", "product_id"}  # metadata, intentionally not in the prefix
    marker = {
        "architecture_digest": "MARK_ARCH",
        "roadmap_headline": "MARK_ROADMAP",
        "recent_decisions": "MARK_DECISION",
        "active_capabilities": "MARK_CAP",
        "known_gaps": "MARK_GAP",
        "active_meta_skills": "MARK_SKILL",
    }
    b = AIBriefing(
        architecture_digest=marker["architecture_digest"],
        roadmap_headline=marker["roadmap_headline"],
        recent_decisions=[{"title": marker["recent_decisions"], "type": "architecture", "rationale_lead": ""}],
        active_capabilities=[{"slug": marker["active_capabilities"], "description": ""}],
        known_gaps=[{"slug": marker["known_gaps"]}],
        active_meta_skills=[marker["active_meta_skills"]],
    )
    out = render_briefing(b)

    content_fields = {f.name for f in dataclasses.fields(AIBriefing)} - NOT_RENDERED
    assert content_fields == set(marker), (
        f"AIBriefing content fields changed — update the dead-field guard: {content_fields ^ set(marker)}"
    )
    for name, mk in marker.items():
        assert mk in out, f"field '{name}' is computed but NEVER rendered by render_briefing (dead field)"


def test_render_briefing_with_decisions():
    """Recent decisions section includes type, title, and rationale lead."""
    b = AIBriefing(
        recent_decisions=[
            {"title": "Use SurrealDB", "type": "architecture", "rationale_lead": "Graph + relational"},
            {"title": "Adopt SDK", "type": "direction", "rationale_lead": "Builder ergonomics"},
        ]
    )
    out = render_briefing(b)
    assert "Recent Decisions" in out
    assert "[architecture] Use SurrealDB" in out
    assert "why: Graph + relational" in out
    assert "[direction] Adopt SDK" in out


def test_render_briefing_with_capabilities_includes_scores():
    """Capabilities section includes the score so the AI knows maturity."""
    b = AIBriefing(
        active_capabilities=[
            {"slug": "code_intelligence", "description": "LSP-grounded", "status": "built", "score": 0.85},
            {"slug": "voice", "description": "Articulation", "status": "partial", "score": None},
        ]
    )
    out = render_briefing(b)
    assert "Already Built" in out
    assert "code_intelligence" in out
    assert "(score 0.85)" in out
    # None score is rendered without score tag
    assert "voice" in out
    assert "voice (score" not in out


def test_render_briefing_with_gaps_includes_scores():
    """Known gaps section includes low scores to set AI expectations."""
    b = AIBriefing(
        known_gaps=[
            {"slug": "deployment", "description": "deploy infra", "score": 0.17},
        ]
    )
    out = render_briefing(b)
    assert "Known Gaps" in out
    assert "deployment" in out
    assert "(score 0.17)" in out


def test_render_briefing_with_meta_skills():
    """Active meta-skills appear as a comma-joined list under their header."""
    b = AIBriefing(active_meta_skills=["coding_intelligence", "creative_intelligence"])
    out = render_briefing(b)
    assert "Active Meta-Intelligences" in out
    assert "coding_intelligence, creative_intelligence" in out


def test_render_briefing_full_includes_all_sections():
    """A fully populated briefing renders every section in expected order."""
    b = AIBriefing(
        architecture_digest="9 layers.",
        recent_decisions=[{"title": "X", "type": "direction", "rationale_lead": "Y"}],
        active_capabilities=[{"slug": "cap", "description": "desc", "status": "built", "score": 0.7}],
        known_gaps=[{"slug": "gap", "description": "g", "score": 0.2}],
        active_meta_skills=["coding_intelligence"],
    )
    out = render_briefing(b)
    # Order: architecture, decisions, capabilities, gaps, meta-skills
    arch_idx = out.find("ACE Substrate")
    dec_idx = out.find("Recent Decisions")
    cap_idx = out.find("Already Built")
    gap_idx = out.find("Known Gaps")
    meta_idx = out.find("Active Meta-Intelligences")
    assert 0 <= arch_idx < dec_idx < cap_idx < gap_idx < meta_idx


# ---------------------------------------------------------------------------
# build_briefing — substrate query resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_briefing_returns_architecture_when_substrate_fails():
    """If the DB query raises, the briefing still has the architecture digest.

    Cold-start ignorance protection must work even when the substrate itself is
    unreachable — the architecture digest is the always-available floor.
    """
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("substrate down")

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        b = await build_briefing("product:test")

    assert b.product_id == "product:test"
    assert "9-layer reasoning substrate" in b.architecture_digest
    assert b.recent_decisions == []
    assert b.active_capabilities == []
    assert b.known_gaps == []


@pytest.mark.asyncio
async def test_build_briefing_populates_from_substrate_rows():
    """Successful substrate queries populate recent_decisions, capabilities, gaps."""
    # Mock the async context manager for pool.connection()
    mock_db = MagicMock()
    mock_db.query = AsyncMock()
    # Return shape: a list of dicts (parse_rows accepts both list-of-list and list-of-dict)
    mock_db.query.side_effect = [
        # decisions
        [{"title": "D1", "decision_type": "architecture", "rationale": "R1", "created_at": "2026-05-27"}],
        # capabilities
        [{"slug": "c1", "description": "desc1", "status": "built", "score": 0.8}],
        # gaps
        [{"slug": "g1", "description": "g desc", "score": 0.3}],
    ]

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        b = await build_briefing("product:test")

    assert b.product_id == "product:test"
    assert len(b.recent_decisions) == 1
    assert b.recent_decisions[0]["title"] == "D1"
    assert b.recent_decisions[0]["type"] == "architecture"
    assert len(b.active_capabilities) == 1
    assert b.active_capabilities[0]["slug"] == "c1"
    assert len(b.known_gaps) == 1
    assert b.known_gaps[0]["slug"] == "g1"


# ---------------------------------------------------------------------------
# briefing_for_dispatched_ai — convenience wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_briefing_for_dispatched_ai_includes_meta_skills():
    """Convenience wrapper injects meta_skills list into the rendered output."""
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("substrate down")  # force fallback

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        text = await briefing_for_dispatched_ai(
            "product:test",
            meta_skills=["coding_intelligence", "creative_intelligence"],
        )

    assert "Active Meta-Intelligences" in text
    assert "coding_intelligence, creative_intelligence" in text
    # Architecture digest still present even with substrate down
    assert "9-layer reasoning substrate" in text


@pytest.mark.asyncio
async def test_briefing_for_dispatched_ai_no_meta_skills():
    """Calling without meta_skills produces a valid briefing minus that section."""
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("substrate down")

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        text = await briefing_for_dispatched_ai("product:test")

    assert "Active Meta-Intelligences" not in text
    assert "9-layer reasoning substrate" in text


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_briefing_cache():
    """Reset the in-process cache between tests."""
    invalidate_briefing_cache()
    yield
    invalidate_briefing_cache()


@pytest.mark.asyncio
async def test_build_briefing_caches_successful_substrate_result():
    """A successful substrate build is cached; second call doesn't re-query."""
    mock_db = MagicMock()
    mock_db.query = AsyncMock(return_value=[])  # empty rows, but no exception

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        await build_briefing("product:cached")
        first_call_count = mock_db.query.call_count

        # Second call should hit cache — no additional substrate queries
        await build_briefing("product:cached")
        second_call_count = mock_db.query.call_count

    assert first_call_count == 3, f"first build should issue 3 queries, got {first_call_count}"
    assert second_call_count == first_call_count, "second build should hit cache (no new queries)"


@pytest.mark.asyncio
async def test_build_briefing_substrate_failure_not_cached():
    """When substrate fails, the architecture-only briefing is NOT cached —
    next call retries the substrate."""
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("substrate down")

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        await build_briefing("product:flaky")
        assert "product:flaky" not in _briefing_cache, "failed build should not be cached"


@pytest.mark.asyncio
async def test_invalidate_briefing_cache_per_product():
    """invalidate_briefing_cache(product_id) drops only that entry."""
    mock_db = MagicMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        await build_briefing("product:a")
        await build_briefing("product:b")
        assert "product:a" in _briefing_cache
        assert "product:b" in _briefing_cache

        invalidate_briefing_cache("product:a")
        assert "product:a" not in _briefing_cache
        assert "product:b" in _briefing_cache

        invalidate_briefing_cache()  # drop all
        assert _briefing_cache == {}


@pytest.mark.asyncio
async def test_build_briefing_use_cache_false_bypasses_cache():
    """use_cache=False forces a fresh substrate query even if cache is fresh."""
    mock_db = MagicMock()
    mock_db.query = AsyncMock(return_value=[])

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("core.engine.ai_briefing.builder.pool", mock_pool):
        await build_briefing("product:nocache")  # populates cache
        first = mock_db.query.call_count

        await build_briefing("product:nocache", use_cache=False)  # bypass
        second = mock_db.query.call_count

    assert second > first, "use_cache=False should issue fresh queries"
