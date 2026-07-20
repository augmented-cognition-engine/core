# tests/test_systems_depth.py
"""Tests for P3 — Systems Design Depth.

Four new analytical layers on top of the Synthesizer:
  ForwardProjection  — project system state N steps forward after applying a leverage point
  FeedbackLoop       — detect reinforcing/balancing loops in the systems map
  CascadeFailurePath — failure chain if a critical intervention is NOT addressed
  TradeOff           — explicit gains and costs for each leverage point intervention

TDD order:
1. Data model validation (ForwardProjection, FeedbackLoop, CascadeFailurePath, TradeOff)
2. SynthesisResult backward compatibility (new fields default to empty lists)
3. Synthesizer parses new fields from LLM JSON
4. Synthesizer degrades gracefully when new fields are absent
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── ForwardProjection model tests ────────────────────────────────────────────


def test_projection_step_has_required_fields():
    """ProjectionStep captures step index, state description, and key change."""
    from core.engine.orchestrator.systems_map import ProjectionStep

    step = ProjectionStep(
        step=1,
        state="Auth middleware added — inbound requests now validated",
        key_change="JWT validation gate active",
    )
    assert step.step == 1
    assert "Auth middleware" in step.state
    assert "JWT" in step.key_change


def test_forward_projection_has_required_fields():
    """ForwardProjection captures leverage_point_rank, steps, and projected_outcome."""
    from core.engine.orchestrator.systems_map import ForwardProjection, ProjectionStep

    proj = ForwardProjection(
        leverage_point_rank=1,
        steps=[
            ProjectionStep(step=1, state="Auth gate active", key_change="JWT validation"),
            ProjectionStep(step=2, state="Audit trail flowing", key_change="Compliance evidence"),
            ProjectionStep(step=3, state="SOC2 audit ready", key_change="Certification eligible"),
        ],
        projected_outcome="System reaches compliance-eligible state within 3 iterations",
    )
    assert proj.leverage_point_rank == 1
    assert len(proj.steps) == 3
    assert "compliance" in proj.projected_outcome.lower()


def test_forward_projection_to_dict_is_serializable():
    """ForwardProjection.to_dict() returns a JSON-serializable structure."""
    from core.engine.orchestrator.systems_map import ForwardProjection, ProjectionStep

    proj = ForwardProjection(
        leverage_point_rank=2,
        steps=[ProjectionStep(step=1, state="circuit breaker added", key_change="cascades blocked")],
        projected_outcome="Resilience improved",
    )
    d = proj.to_dict()
    assert d["leverage_point_rank"] == 2
    assert len(d["steps"]) == 1
    assert d["steps"][0]["step"] == 1
    assert "projected_outcome" in d


# ── FeedbackLoop model tests ──────────────────────────────────────────────────


def test_feedback_loop_type_must_be_reinforcing_or_balancing():
    """FeedbackLoop.loop_type must be 'reinforcing' or 'balancing'."""
    from core.engine.orchestrator.systems_map import FeedbackLoop

    with pytest.raises(ValueError, match="loop_type"):
        FeedbackLoop(
            loop_type="vicious",
            disciplines=["security", "compliance"],
            description="security gaps grow compliance gaps grow",
            net_effect="amplifying",
        )


def test_feedback_loop_reinforcing_is_valid():
    """FeedbackLoop accepts 'reinforcing' loop_type."""
    from core.engine.orchestrator.systems_map import FeedbackLoop

    loop = FeedbackLoop(
        loop_type="reinforcing",
        disciplines=["security", "compliance", "deployment"],
        description="fixing security unlocks compliance which enables deployment automation",
        net_effect="amplifying",
    )
    assert loop.loop_type == "reinforcing"
    assert len(loop.disciplines) == 3


def test_feedback_loop_balancing_is_valid():
    """FeedbackLoop accepts 'balancing' loop_type."""
    from core.engine.orchestrator.systems_map import FeedbackLoop

    loop = FeedbackLoop(
        loop_type="balancing",
        disciplines=["performance", "testing"],
        description="perf optimization slows test coverage which constrains optimization",
        net_effect="stabilizing",
    )
    assert loop.loop_type == "balancing"


def test_feedback_loop_to_dict_is_serializable():
    """FeedbackLoop.to_dict() returns all fields."""
    from core.engine.orchestrator.systems_map import FeedbackLoop

    loop = FeedbackLoop(
        loop_type="reinforcing",
        disciplines=["security", "compliance"],
        description="security → compliance → security (virtuous cycle)",
        net_effect="amplifying",
    )
    d = loop.to_dict()
    assert d["loop_type"] == "reinforcing"
    assert "disciplines" in d
    assert "description" in d
    assert "net_effect" in d


# ── CascadeFailurePath model tests ───────────────────────────────────────────


def test_cascade_failure_path_has_required_fields():
    """CascadeFailurePath captures the failure origin and cascade sequence."""
    from core.engine.orchestrator.systems_map import CascadeFailurePath

    path = CascadeFailurePath(
        failure_origin="no auth middleware deployed",
        discipline="security",
        cascade_sequence=[
            "security: all endpoints publicly accessible",
            "compliance: PII exposed without access control",
            "deployment: failed SOC2 audit → deployment blocked",
        ],
    )
    assert path.failure_origin == "no auth middleware deployed"
    assert path.discipline == "security"
    assert len(path.cascade_sequence) == 3


def test_cascade_failure_path_blast_radius_is_computed():
    """CascadeFailurePath.blast_radius equals the length of cascade_sequence."""
    from core.engine.orchestrator.systems_map import CascadeFailurePath

    path = CascadeFailurePath(
        failure_origin="no circuit breaker",
        discipline="resilience",
        cascade_sequence=["cascade A", "cascade B", "cascade C", "cascade D"],
    )
    assert path.blast_radius == 4


def test_cascade_failure_path_empty_sequence_has_zero_blast_radius():
    """A path with no cascade sequence has blast_radius of 0."""
    from core.engine.orchestrator.systems_map import CascadeFailurePath

    path = CascadeFailurePath(
        failure_origin="isolated issue",
        discipline="testing",
        cascade_sequence=[],
    )
    assert path.blast_radius == 0


def test_cascade_failure_path_to_dict_is_serializable():
    """CascadeFailurePath.to_dict() includes blast_radius in output."""
    from core.engine.orchestrator.systems_map import CascadeFailurePath

    path = CascadeFailurePath(
        failure_origin="no retries",
        discipline="error_handling",
        cascade_sequence=["network errors surface to user", "bad UX drives churn"],
    )
    d = path.to_dict()
    assert d["failure_origin"] == "no retries"
    assert d["blast_radius"] == 2
    assert len(d["cascade_sequence"]) == 2


# ── TradeOff model tests ──────────────────────────────────────────────────────


def test_trade_off_reversibility_must_be_valid():
    """TradeOff.reversibility must be one of the three valid values."""
    from core.engine.orchestrator.systems_map import TradeOff

    with pytest.raises(ValueError, match="reversibility"):
        TradeOff(
            leverage_point_rank=1,
            intervention="migrate to microservices",
            gains=["scalability", "team autonomy"],
            costs=["operational complexity", "latency"],
            reversibility="maybe",
        )


def test_trade_off_valid_reversibility_values():
    """TradeOff accepts all three valid reversibility values."""
    from core.engine.orchestrator.systems_map import TradeOff

    for rev in ("reversible", "partially_reversible", "irreversible"):
        t = TradeOff(
            leverage_point_rank=1,
            intervention="add caching layer",
            gains=["latency improvement"],
            costs=["cache invalidation complexity"],
            reversibility=rev,
        )
        assert t.reversibility == rev


def test_trade_off_has_required_fields():
    """TradeOff captures leverage_point_rank, intervention, gains, costs, reversibility."""
    from core.engine.orchestrator.systems_map import TradeOff

    t = TradeOff(
        leverage_point_rank=1,
        intervention="add auth middleware",
        gains=["security hardened", "compliance eligible"],
        costs=["latency +5ms per request"],
        reversibility="reversible",
    )
    assert t.leverage_point_rank == 1
    assert len(t.gains) == 2
    assert len(t.costs) == 1


def test_trade_off_to_dict_is_serializable():
    """TradeOff.to_dict() returns all expected keys."""
    from core.engine.orchestrator.systems_map import TradeOff

    t = TradeOff(
        leverage_point_rank=2,
        intervention="add circuit breaker",
        gains=["prevents cascade", "improves resilience"],
        costs=["more config to maintain"],
        reversibility="reversible",
    )
    d = t.to_dict()
    assert d["leverage_point_rank"] == 2
    assert "gains" in d
    assert "costs" in d
    assert d["reversibility"] == "reversible"


# ── SynthesisResult backward compatibility ────────────────────────────────────


def test_synthesis_result_new_fields_default_to_empty_lists():
    """SynthesisResult can be created without P3 fields — they default to empty lists."""
    from core.engine.orchestrator.systems_map import SynthesisResult, SystemsMap

    result = SynthesisResult(
        cross_implication_chains=[],
        leverage_points=[],
        systems_map=SystemsMap(nodes=[], edges=[], task_description=""),
        synthesis_duration_ms=10.0,
    )

    assert result.forward_projections == []
    assert result.feedback_loops == []
    assert result.cascade_failure_paths == []
    assert result.trade_offs == []


def test_synthesis_result_to_dict_includes_p3_fields():
    """SynthesisResult.to_dict() includes all P3 fields."""
    from core.engine.orchestrator.systems_map import SynthesisResult, SystemsMap

    result = SynthesisResult(
        cross_implication_chains=[],
        leverage_points=[],
        systems_map=SystemsMap(nodes=[], edges=[], task_description=""),
        synthesis_duration_ms=10.0,
    )
    d = result.to_dict()
    assert "forward_projections" in d
    assert "feedback_loops" in d
    assert "cascade_failure_paths" in d
    assert "trade_offs" in d


# ── Synthesizer parses new fields ─────────────────────────────────────────────


def _build_full_llm_response() -> str:
    """Build a complete LLM JSON response including all P3 fields."""
    import json

    return json.dumps(
        {
            "cross_implication_chains": [
                {
                    "root_discipline": "security",
                    "root_finding": "no auth middleware",
                    "chain": [
                        {"discipline": "compliance", "finding": "PII exposed", "severity": "critical"},
                    ],
                }
            ],
            "leverage_points": [
                {
                    "rank": 1,
                    "discipline": "security",
                    "intervention": "add JWT auth middleware",
                    "impact_score": 0.9,
                    "affected_dimensions": ["security", "compliance"],
                    "cascade_description": "auth → compliance → deployment",
                },
                {
                    "rank": 2,
                    "discipline": "resilience",
                    "intervention": "add circuit breaker",
                    "impact_score": 0.75,
                    "affected_dimensions": ["resilience", "error_handling"],
                    "cascade_description": "circuit breaker → prevents cascade",
                },
                {
                    "rank": 3,
                    "discipline": "observability",
                    "intervention": "add health endpoints",
                    "impact_score": 0.6,
                    "affected_dimensions": ["observability"],
                    "cascade_description": "health checks → faster incident detection",
                },
            ],
            "systems_map": {
                "nodes": [{"discipline": "security", "score": 0.3, "key_findings": ["no auth"]}],
                "edges": [
                    {
                        "from_discipline": "security",
                        "to_discipline": "compliance",
                        "implication": "no auth exposes PII",
                        "weight": 0.9,
                    }
                ],
            },
            "forward_projections": [
                {
                    "leverage_point_rank": 1,
                    "steps": [
                        {"step": 1, "state": "JWT validation active", "key_change": "auth gate"},
                        {"step": 2, "state": "audit trail flowing", "key_change": "compliance evidence"},
                        {"step": 3, "state": "SOC2 eligible", "key_change": "certification ready"},
                    ],
                    "projected_outcome": "System reaches compliance-ready state",
                }
            ],
            "feedback_loops": [
                {
                    "loop_type": "reinforcing",
                    "disciplines": ["security", "compliance", "deployment"],
                    "description": "security improvements unlock compliance which enables deployment",
                    "net_effect": "amplifying",
                }
            ],
            "cascade_failure_paths": [
                {
                    "failure_origin": "no auth middleware deployed",
                    "discipline": "security",
                    "cascade_sequence": [
                        "all endpoints publicly accessible",
                        "PII exposed without control",
                        "SOC2 audit failed",
                    ],
                }
            ],
            "trade_offs": [
                {
                    "leverage_point_rank": 1,
                    "intervention": "add JWT auth middleware",
                    "gains": ["security hardened", "compliance eligible"],
                    "costs": ["latency +5ms", "token management overhead"],
                    "reversibility": "reversible",
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_synthesizer_parses_forward_projections():
    """Synthesizer parses forward_projections from LLM response."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=_build_full_llm_response())

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(
            {"discipline": "security", "output": "auth gap found", "intelligence_loaded": {}}
        )

    assert len(result.forward_projections) == 1
    proj = result.forward_projections[0]
    assert proj.leverage_point_rank == 1
    assert len(proj.steps) == 3
    assert proj.steps[0].step == 1
    assert "compliance" in proj.projected_outcome.lower()


@pytest.mark.asyncio
async def test_synthesizer_parses_feedback_loops():
    """Synthesizer parses feedback_loops from LLM response."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=_build_full_llm_response())

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(
            {"discipline": "security", "output": "auth gap found", "intelligence_loaded": {}}
        )

    assert len(result.feedback_loops) == 1
    loop = result.feedback_loops[0]
    assert loop.loop_type == "reinforcing"
    assert "security" in loop.disciplines
    assert loop.net_effect == "amplifying"


@pytest.mark.asyncio
async def test_synthesizer_parses_cascade_failure_paths():
    """Synthesizer parses cascade_failure_paths from LLM response."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=_build_full_llm_response())

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(
            {"discipline": "security", "output": "auth gap found", "intelligence_loaded": {}}
        )

    assert len(result.cascade_failure_paths) == 1
    path = result.cascade_failure_paths[0]
    assert path.discipline == "security"
    assert path.blast_radius == 3
    assert "PII" in path.cascade_sequence[1]


@pytest.mark.asyncio
async def test_synthesizer_parses_trade_offs():
    """Synthesizer parses trade_offs from LLM response."""
    from core.engine.orchestrator.synthesizer import Synthesizer

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=_build_full_llm_response())

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(
            {"discipline": "security", "output": "auth gap found", "intelligence_loaded": {}}
        )

    assert len(result.trade_offs) == 1
    tradeoff = result.trade_offs[0]
    assert tradeoff.leverage_point_rank == 1
    assert len(tradeoff.gains) == 2
    assert tradeoff.reversibility == "reversible"


@pytest.mark.asyncio
async def test_synthesizer_degrades_when_p3_fields_absent():
    """Synthesizer returns empty lists for P3 fields when LLM omits them."""
    import json

    from core.engine.orchestrator.synthesizer import Synthesizer

    partial_response = json.dumps(
        {
            "cross_implication_chains": [],
            "leverage_points": [
                {
                    "rank": 1,
                    "discipline": "architecture",
                    "intervention": "add service layer",
                    "impact_score": 0.7,
                    "affected_dimensions": ["architecture"],
                    "cascade_description": "service layer → better separation",
                },
                {
                    "rank": 2,
                    "discipline": "testing",
                    "intervention": "add integration tests",
                    "impact_score": 0.6,
                    "affected_dimensions": ["testing"],
                    "cascade_description": "tests → fewer regressions",
                },
                {
                    "rank": 3,
                    "discipline": "observability",
                    "intervention": "add metrics",
                    "impact_score": 0.5,
                    "affected_dimensions": ["observability"],
                    "cascade_description": "metrics → visibility",
                },
            ],
            "systems_map": {"nodes": [], "edges": []},
            # P3 fields intentionally absent
        }
    )

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=partial_response)

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize(
            {"discipline": "architecture", "output": "spec created", "intelligence_loaded": {}}
        )

    # P3 fields absent from LLM → empty, no error
    assert result.forward_projections == []
    assert result.feedback_loops == []
    assert result.cascade_failure_paths == []
    assert result.trade_offs == []
    # Core fields still work
    assert len(result.leverage_points) == 3


@pytest.mark.asyncio
async def test_synthesizer_skips_malformed_p3_entries():
    """Synthesizer skips individual malformed P3 entries and keeps valid ones."""
    import json

    from core.engine.orchestrator.synthesizer import Synthesizer

    response_with_bad_entry = json.dumps(
        {
            "cross_implication_chains": [],
            "leverage_points": [
                {
                    "rank": 1,
                    "discipline": "security",
                    "intervention": "add auth",
                    "impact_score": 0.8,
                    "affected_dimensions": ["security"],
                    "cascade_description": "auth → compliance",
                },
                {
                    "rank": 2,
                    "discipline": "testing",
                    "intervention": "add tests",
                    "impact_score": 0.6,
                    "affected_dimensions": ["testing"],
                    "cascade_description": "tests → quality",
                },
                {
                    "rank": 3,
                    "discipline": "observability",
                    "intervention": "add metrics",
                    "impact_score": 0.5,
                    "affected_dimensions": ["observability"],
                    "cascade_description": "metrics → visibility",
                },
            ],
            "systems_map": {"nodes": [], "edges": []},
            "trade_offs": [
                {
                    "leverage_point_rank": 1,
                    "intervention": "add auth",
                    "gains": ["security"],
                    "costs": ["latency"],
                    "reversibility": "reversible",
                },
                {
                    # Missing required fields — should be skipped
                    "leverage_point_rank": 2,
                },
            ],
            "feedback_loops": [
                {"loop_type": "invalid_type", "disciplines": ["x"], "description": "bad", "net_effect": "?"},
                {
                    "loop_type": "balancing",
                    "disciplines": ["perf", "testing"],
                    "description": "perf vs tests",
                    "net_effect": "stabilizing",
                },
            ],
        }
    )

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=response_with_bad_entry)

    with patch("core.engine.orchestrator.synthesizer.get_llm", return_value=mock_llm):
        synth = Synthesizer()
        result = await synth.synthesize({"discipline": "security", "output": "review", "intelligence_loaded": {}})

    # Only the valid trade_off should be kept
    assert len(result.trade_offs) == 1
    assert result.trade_offs[0].leverage_point_rank == 1

    # Only the valid feedback loop should be kept
    assert len(result.feedback_loops) == 1
    assert result.feedback_loops[0].loop_type == "balancing"
