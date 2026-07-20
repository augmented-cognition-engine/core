# tests/test_synthesizer.py
"""Tests for the Synthesizer layer — cross-discipline implication chains,
leverage point detection, and systems map generation.

TDD order: data models → synthesizer interface → LLM integration → edge cases.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.core.db import parse_one, parse_rows

# ── Data model tests (no I/O) ────────────────────────────────────────────────


def test_systems_map_serializes_to_json():
    """SystemsMap with nodes and edges round-trips through JSON cleanly."""
    from core.engine.orchestrator.systems_map import SystemsMap, SystemsMapEdge, SystemsMapNode

    node_a = SystemsMapNode(discipline="data_modeling", score=0.4, key_findings=["no migration strategy"])
    node_b = SystemsMapNode(discipline="security", score=0.3, key_findings=["PII exposure via schema"])
    edge = SystemsMapEdge(
        from_discipline="data_modeling",
        to_discipline="security",
        implication="schema exposes PII fields without encryption",
        weight=0.8,
    )
    smap = SystemsMap(nodes=[node_a, node_b], edges=[edge], task_description="design user table")

    raw = smap.to_json()
    parsed = json.loads(raw)

    assert parsed["task_description"] == "design user table"
    assert len(parsed["nodes"]) == 2
    assert len(parsed["edges"]) == 1
    assert parsed["edges"][0]["from_discipline"] == "data_modeling"
    assert parsed["edges"][0]["to_discipline"] == "security"


def test_systems_map_to_dict_has_required_keys():
    """SystemsMap.to_dict() contains nodes, edges, and task_description."""
    from core.engine.orchestrator.systems_map import SystemsMap

    smap = SystemsMap(nodes=[], edges=[], task_description="test task")
    d = smap.to_dict()

    assert "nodes" in d
    assert "edges" in d
    assert "task_description" in d


def test_cross_implication_chain_depth_equals_chain_length():
    """CrossImplicationChain.depth is always len(chain)."""
    from core.engine.orchestrator.systems_map import CrossImplicationChain, ImplicationLink

    links = [
        ImplicationLink(discipline="security", finding="no auth check", severity="critical"),
        ImplicationLink(discipline="compliance", finding="audit trail missing", severity="high"),
    ]
    chain = CrossImplicationChain(
        root_discipline="data_modeling",
        root_finding="user_id exposed in response",
        chain=links,
    )

    assert chain.depth == 2
    assert chain.depth == len(chain.chain)


def test_cross_implication_chain_depth_zero_for_empty_chain():
    """A chain with no links has depth 0."""
    from core.engine.orchestrator.systems_map import CrossImplicationChain

    chain = CrossImplicationChain(
        root_discipline="architecture",
        root_finding="monolithic service",
        chain=[],
    )
    assert chain.depth == 0


def test_leverage_point_rank_must_be_1_2_or_3():
    """LeveragePoint rank outside 1-3 raises ValueError."""
    from core.engine.orchestrator.systems_map import LeveragePoint

    with pytest.raises(ValueError, match="rank"):
        LeveragePoint(
            rank=0,
            discipline="security",
            intervention="add auth middleware",
            impact_score=0.9,
            affected_dimensions=["security", "compliance"],
            cascade_description="fixes auth → unblocks audit → enables compliance",
        )

    with pytest.raises(ValueError, match="rank"):
        LeveragePoint(
            rank=4,
            discipline="security",
            intervention="add auth middleware",
            impact_score=0.9,
            affected_dimensions=["security", "compliance"],
            cascade_description="fixes auth → unblocks audit → enables compliance",
        )


def test_leverage_point_impact_score_bounds():
    """LeveragePoint impact_score must be in [0.0, 1.0]."""
    from core.engine.orchestrator.systems_map import LeveragePoint

    with pytest.raises(ValueError, match="impact_score"):
        LeveragePoint(
            rank=1,
            discipline="security",
            intervention="fix this",
            impact_score=1.5,
            affected_dimensions=["security"],
            cascade_description="cascades",
        )


def test_synthesis_result_structure():
    """SynthesisResult exposes cross_implication_chains, leverage_points, systems_map."""
    from core.engine.orchestrator.systems_map import (
        CrossImplicationChain,
        LeveragePoint,
        SynthesisResult,
        SystemsMap,
    )

    result = SynthesisResult(
        cross_implication_chains=[
            CrossImplicationChain(root_discipline="data_modeling", root_finding="no index", chain=[])
        ],
        leverage_points=[
            LeveragePoint(
                rank=1,
                discipline="data_modeling",
                intervention="add composite index",
                impact_score=0.85,
                affected_dimensions=["performance", "data_modeling"],
                cascade_description="index → query time -80% → scale unblocked",
            )
        ],
        systems_map=SystemsMap(nodes=[], edges=[], task_description="optimize queries"),
        synthesis_duration_ms=120.0,
    )

    assert len(result.cross_implication_chains) == 1
    assert len(result.leverage_points) == 1
    assert result.systems_map.task_description == "optimize queries"
    assert result.synthesis_duration_ms == 120.0


# ── Synthesizer interface tests (mocked LLM) ─────────────────────────────────

MOCK_LLM_RESPONSE = json.dumps(
    {
        "cross_implication_chains": [
            {
                "root_discipline": "data_modeling",
                "root_finding": "user table has no row-level encryption",
                "chain": [
                    {"discipline": "security", "finding": "PII exposed in plaintext", "severity": "critical"},
                    {"discipline": "compliance", "finding": "GDPR audit trail missing", "severity": "high"},
                    {"discipline": "deployment", "finding": "no encryption-at-rest config", "severity": "high"},
                ],
            }
        ],
        "leverage_points": [
            {
                "rank": 1,
                "discipline": "data_modeling",
                "intervention": "add column-level encryption to PII fields",
                "impact_score": 0.92,
                "affected_dimensions": ["security", "compliance", "deployment"],
                "cascade_description": "encrypting at model level fixes security + unblocks compliance + forces deployment config",
            },
            {
                "rank": 2,
                "discipline": "observability",
                "intervention": "add structured audit log for all data access",
                "impact_score": 0.75,
                "affected_dimensions": ["compliance", "observability"],
                "cascade_description": "audit log closes GDPR gap and provides visibility",
            },
            {
                "rank": 3,
                "discipline": "error_handling",
                "intervention": "add validation on all PII field writes",
                "impact_score": 0.6,
                "affected_dimensions": ["error_handling", "data_modeling"],
                "cascade_description": "write validation prevents bad data and reduces compliance surface",
            },
        ],
        "systems_map": {
            "nodes": [
                {"discipline": "data_modeling", "score": 0.3, "key_findings": ["no encryption", "no audit trail"]},
                {"discipline": "security", "score": 0.2, "key_findings": ["PII exposure"]},
                {"discipline": "compliance", "score": 0.1, "key_findings": ["GDPR gap"]},
            ],
            "edges": [
                {
                    "from_discipline": "data_modeling",
                    "to_discipline": "security",
                    "implication": "unencrypted schema creates PII exposure",
                    "weight": 0.9,
                }
            ],
        },
    }
)


@pytest.fixture
def mock_llm():
    """Mock LLM that returns a valid synthesis JSON response."""
    m = MagicMock()
    m.complete = AsyncMock(return_value=MOCK_LLM_RESPONSE)
    return m


@pytest.fixture
def sample_task_result():
    """Minimal task result dict from executor."""
    return {
        "id": "task:abc123",
        "discipline": "data_modeling",
        "archetype": "analyst",
        "mode": "deliberative",
        "output": "The user table schema has several issues. PII fields are stored in plaintext...",
        "intelligence_loaded": {
            "insights": [
                {"content": "User schema missing encryption", "confidence": 0.9},
                {"content": "No audit trail configured", "confidence": 0.8},
            ],
            "total_count": 2,
        },
        "status": "completed",
    }


@pytest.mark.asyncio
async def test_synthesizer_returns_synthesis_result(mock_llm, sample_task_result):
    """Synthesizer.synthesize() returns a SynthesisResult given a task result."""
    from core.engine.orchestrator.synthesizer import Synthesizer
    from core.engine.orchestrator.systems_map import SynthesisResult

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert isinstance(result, SynthesisResult)


@pytest.mark.asyncio
async def test_synthesizer_produces_implication_chains(mock_llm, sample_task_result):
    """Synthesizer returns at least one cross-implication chain."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert len(result.cross_implication_chains) >= 1
    assert result.cross_implication_chains[0].root_discipline == "data_modeling"
    assert result.cross_implication_chains[0].depth == 3


@pytest.mark.asyncio
async def test_synthesizer_produces_exactly_three_leverage_points(mock_llm, sample_task_result):
    """Synthesizer returns exactly 3 leverage points ranked 1-3."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert len(result.leverage_points) == 3
    ranks = [lp.rank for lp in result.leverage_points]
    assert sorted(ranks) == [1, 2, 3]


@pytest.mark.asyncio
async def test_synthesizer_produces_systems_map_with_nodes_and_edges(mock_llm, sample_task_result):
    """Synthesizer returns a systems map with nodes and edges."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert len(result.systems_map.nodes) >= 1
    assert len(result.systems_map.edges) >= 1


@pytest.mark.asyncio
async def test_synthesizer_records_duration(mock_llm, sample_task_result):
    """SynthesisResult.synthesis_duration_ms is a positive number."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert result.synthesis_duration_ms > 0


@pytest.mark.asyncio
async def test_synthesizer_handles_empty_intelligence_gracefully(mock_llm):
    """Synthesizer does not raise when intelligence_loaded is empty."""
    from core.engine.orchestrator.synthesizer import Synthesizer
    from core.engine.orchestrator.systems_map import SynthesisResult

    task_result = {
        "id": "task:empty",
        "discipline": "architecture",
        "output": "Some output text.",
        "intelligence_loaded": {},
        "status": "completed",
    }

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(task_result)

    assert isinstance(result, SynthesisResult)


@pytest.mark.asyncio
async def test_synthesizer_degrades_gracefully_on_llm_failure(sample_task_result):
    """When LLM fails, synthesizer returns a degraded result — does not raise."""
    from core.engine.orchestrator.synthesizer import Synthesizer
    from core.engine.orchestrator.systems_map import SynthesisResult

    failing_llm = MagicMock()
    failing_llm.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=failing_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert isinstance(result, SynthesisResult)
    assert result.cross_implication_chains == []
    assert result.leverage_points == []


@pytest.mark.asyncio
async def test_synthesizer_degrades_gracefully_on_malformed_llm_response(sample_task_result):
    """When LLM returns non-JSON, synthesizer returns degraded result — does not raise."""
    from core.engine.orchestrator.synthesizer import Synthesizer
    from core.engine.orchestrator.systems_map import SynthesisResult

    bad_llm = MagicMock()
    bad_llm.complete = AsyncMock(return_value="not valid json at all }{")

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=bad_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    assert isinstance(result, SynthesisResult)
    assert result.cross_implication_chains == []


@pytest.mark.asyncio
async def test_synthesizer_systems_map_serializable(mock_llm, sample_task_result):
    """SynthesisResult.systems_map is JSON-serializable."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(sample_task_result)

    raw = result.systems_map.to_json()
    parsed = json.loads(raw)
    assert "nodes" in parsed
    assert "edges" in parsed


# ── Seam gap wiring test ──────────────────────────────────────────────────────


def test_cross_implication_chain_holds_integration_seam_gap():
    """CrossImplicationChain can represent an integration seam gap finding."""
    from core.engine.orchestrator.systems_map import CrossImplicationChain, ImplicationLink

    seam_link = ImplicationLink(
        discipline="integration",
        finding="frontend expects `from` field but backend returns `in` (SurrealDB native key)",
        severity="critical",
    )
    chain = CrossImplicationChain(
        root_discipline="data_modeling",
        root_finding="SurrealDB native key schema not normalized for API consumers",
        chain=[seam_link],
    )

    assert chain.depth == 1
    assert chain.chain[0].discipline == "integration"
    assert "SurrealDB" in chain.chain[0].finding


@pytest.mark.asyncio
async def test_adds_observation_and_triggers_at_threshold():
    """Synthesizer triggers synthesis when pending count reaches batch_size."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id="product:test", workspace_id=None, batch_size=2)

    mock_result = {
        "new_insights": [
            {
                "content": "Tokens use kebab-case",
                "tier": "subdomain",
                "domain_path": "ux",
                "insight_type": "fact",
                "confidence": 0.9,
                "clearance": "open",
                "source_observations": [0],
            }
        ],
        "updates": [],
        "conflicts": [],
        "skipped": [1],
    }

    with patch.object(synth, "_call_primary_llm", new_callable=AsyncMock, return_value=mock_result):
        with patch.object(synth, "_load_existing_insights", new_callable=AsyncMock, return_value=[]):
            with patch.object(synth, "_write_insight", new_callable=AsyncMock) as mock_write:
                await synth.add_observation({"content": "obs 1", "domain_hint": "ux"})
                assert synth.pending_count == 1
                await synth.add_observation({"content": "obs 2", "domain_hint": "ux"})
                # Should have triggered synthesis, clearing pending
                assert synth.pending_count == 0
                mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_flush_processes_remaining():
    """flush() synthesizes any remaining observations."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id="product:test", workspace_id=None, batch_size=10)

    mock_result = {"new_insights": [], "updates": [], "conflicts": [], "skipped": [0]}

    with patch.object(synth, "_call_primary_llm", new_callable=AsyncMock, return_value=mock_result):
        with patch.object(synth, "_load_existing_insights", new_callable=AsyncMock, return_value=[]):
            await synth.add_observation({"content": "obs 1", "domain_hint": "architecture"})
            assert synth.pending_count == 1
            await synth.flush()
            assert synth.pending_count == 0


@pytest.mark.asyncio
async def test_no_synthesis_when_empty():
    """flush() on empty synthesizer is a no-op."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id="product:test", workspace_id=None)
    await synth.flush()  # should not raise
    assert synth.pending_count == 0


@pytest.mark.asyncio
async def test_emergence_called_after_synthesis():
    """check_emergence() is invoked after successful synthesis when _db_pool is set."""
    from unittest.mock import MagicMock

    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id="product:test", workspace_id=None, batch_size=1)
    synth._db_pool = MagicMock()  # just needs to be truthy

    mock_result = {"new_insights": [], "updates": [], "conflicts": [], "skipped": []}

    with patch.object(synth, "_call_primary_llm", new_callable=AsyncMock, return_value=mock_result):
        with patch.object(synth, "_load_existing_insights", new_callable=AsyncMock, return_value=[]):
            with patch(
                "core.engine.intelligence.emergence.check_emergence", new_callable=AsyncMock, return_value=[]
            ) as mock_emerge:
                await synth.add_observation({"content": "obs 1", "domain_hint": "architecture"})
                mock_emerge.assert_called_once_with("product:test")


@pytest.mark.asyncio
async def test_atomic_capture_write_sets_specialty_field(db_pool):
    """atomic_capture_write must set insight.specialty as a record link so
    dual_loader (which queries `WHERE specialty IN $ids` on the insight FIELD,
    not the informed_by edge) can find the insight.

    DB-backed regression guard: Phase 1 set specialty=NONE and relied on the edge,
    which silently made new insights invisible to specialty-scoped retrieval.
    """
    from surrealdb import RecordID

    from core.engine.capture.atomic_write import atomic_capture_write

    product = "product:test_specialty_30201"
    async with db_pool.connection() as db:
        await db.query("CREATE specialty:test_arch_30201 SET slug='test_arch_30201', name='Test Arch'")
    try:
        iid = await atomic_capture_write(
            db_pool,
            insight_fields={
                "product": product,
                "content": "specialty field regression 30201",
                "insight_type": "pattern",
                "tier": "domain",
                "clearance": "open",
                "confidence": 0.8,
                "source_domain": "test",
                "domain_path": "test",
                "domain": None,
                "subdomain": None,
                "specialty": "specialty:test_arch_30201",
                "tags": [],
            },
            embedding=None,
            specialty_slug=None,
            observation_ids=[],
        )
        async with db_pool.connection() as db:
            row = parse_one(await db.query("SELECT specialty FROM <record>$id", {"id": iid}))
            # dual_loader's exact retrieval shape
            found = parse_rows(
                await db.query(
                    "SELECT id FROM insight WHERE specialty IN $ids AND status = 'active'",
                    {"ids": [RecordID("specialty", "test_arch_30201")]},
                )
            )
        assert row is not None and row.get("specialty") is not None, "insight.specialty not set"
        assert any(str(r["id"]) == iid for r in found), "dual_loader query did not find the insight"
    finally:
        async with db_pool.connection() as db:
            await db.query("DELETE insight WHERE product = <record>$p", {"p": product})
            await db.query("DELETE specialty:test_arch_30201")
