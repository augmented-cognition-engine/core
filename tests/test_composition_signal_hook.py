from unittest.mock import AsyncMock, patch

import pytest

from core.engine.core.tokens import TokenAccumulator
from core.engine.orchestration.hooks import HookContext


def test_hook_context_has_new_fields():
    """HookContext includes frameworks_used, engagement_result, token_accumulator."""
    acc = TokenAccumulator()
    ctx = HookContext(
        task_id="task:test",
        product_id="product:default",
        domain_path="security",
        output="test output",
        snapshot={"insights": []},
        classification={
            "discipline": "security",
            "archetype": "analyst",
            "mode": "reactive",
            "complexity": "simple",
            "perspectives": ["practitioner"],
            "engagement": {"perspectives": ["practitioner"]},
        },
        frameworks_used=["stride"],
        engagement_result={"spin_count": 1},
        token_accumulator=acc,
    )
    assert ctx.frameworks_used == ["stride"]
    assert ctx.engagement_result == {"spin_count": 1}
    assert ctx.token_accumulator is acc


@pytest.mark.asyncio
async def test_composition_signal_hook_writes_record():
    """composition_signal_hook creates a composition_signal record."""
    from core.engine.orchestration.hooks import composition_signal_hook

    acc = TokenAccumulator()
    acc.record("complete", 100, 50, purpose="classifier")
    acc.record("complete_structured", 200, 150, purpose="spin")

    ctx = HookContext(
        task_id="task:test123",
        product_id="product:default",
        domain_path="security",
        output="test output",
        snapshot={"insights": []},
        classification={
            "discipline": "security",
            "archetype": "analyst",
            "mode": "deliberative",
            "complexity": "moderate",
            "perspectives": ["practitioner", "strategist"],
            "specialties": ["web-security"],
            "engagement": {"perspectives": ["practitioner", "strategist"]},
        },
        frameworks_used=["stride"],
        engagement_result={"spin_count": 2, "adversarial_diversity": 0.45},
        token_accumulator=acc,
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"id": "composition_signal:new"}])

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", return_value=None),
    ):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await composition_signal_hook(ctx)

    mock_db.query.assert_called_once()
    query_str = mock_db.query.call_args[0][0]
    assert "CREATE composition_signal" in query_str


@pytest.mark.asyncio
async def test_composition_signal_hook_handles_missing_accumulator():
    """Hook gracefully handles None token_accumulator."""
    from core.engine.orchestration.hooks import composition_signal_hook

    ctx = HookContext(
        task_id="task:test",
        product_id="product:default",
        domain_path="security",
        output="test",
        snapshot={},
        classification={
            "discipline": "security",
            "archetype": "analyst",
            "mode": "reactive",
            "complexity": "simple",
            "perspectives": ["practitioner"],
            "engagement": {"perspectives": ["practitioner"]},
        },
        frameworks_used=[],
        engagement_result=None,
        token_accumulator=None,
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"id": "composition_signal:new"}])

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", return_value=None),
    ):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await composition_signal_hook(ctx)

    mock_db.query.assert_called_once()


@pytest.mark.asyncio
async def test_composition_signal_hook_handles_missing_baseline():
    """Hook writes None for estimated_tokens_saved when no baseline exists."""
    from core.engine.orchestration.hooks import composition_signal_hook

    acc = TokenAccumulator()
    acc.record("complete", 100, 50)

    ctx = HookContext(
        task_id="task:test",
        product_id="product:default",
        domain_path="testing",
        output="test",
        snapshot={},
        classification={
            "discipline": "testing",
            "archetype": "analyst",
            "mode": "reactive",
            "complexity": "simple",
            "perspectives": ["practitioner"],
            "engagement": {"perspectives": ["practitioner"]},
        },
        frameworks_used=[],
        engagement_result=None,
        token_accumulator=acc,
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[{"id": "composition_signal:new"}])

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", return_value=None),
    ):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await composition_signal_hook(ctx)

    query_str = mock_db.query.call_args[0][0]
    assert "composition_signal" in query_str


# ---------------------------------------------------------------------------
# _outcome_confidence_from_traces
# ---------------------------------------------------------------------------


def test_outcome_confidence_from_traces_mean_of_non_tainted():
    """Returns mean confidence of non-tainted phases."""
    from core.engine.orchestration.hooks import _outcome_confidence_from_traces

    traces = [
        {"phase_idx": 0, "confidence": 0.8, "tainted": False},
        {"phase_idx": 1, "confidence": 0.6, "tainted": False},
        {"phase_idx": 2, "confidence": 0.4, "tainted": False},
    ]
    result = _outcome_confidence_from_traces(traces)
    assert abs(result - 0.6) < 1e-9


def test_outcome_confidence_from_traces_skips_tainted():
    """Tainted phases (execution failure) are excluded from mean."""
    from core.engine.orchestration.hooks import _outcome_confidence_from_traces

    traces = [
        {"phase_idx": 0, "confidence": 0.9, "tainted": False},
        {"phase_idx": 1, "confidence": 0.0, "tainted": True},  # excluded
    ]
    result = _outcome_confidence_from_traces(traces)
    assert result == 0.9


def test_outcome_confidence_from_traces_all_tainted_returns_none():
    """Returns None when all phases are tainted."""
    from core.engine.orchestration.hooks import _outcome_confidence_from_traces

    traces = [
        {"phase_idx": 0, "confidence": 0.0, "tainted": True},
        {"phase_idx": 1, "confidence": 0.0, "tainted": True},
    ]
    assert _outcome_confidence_from_traces(traces) is None


def test_outcome_confidence_from_traces_empty_returns_none():
    """Returns None for empty trace list."""
    from core.engine.orchestration.hooks import _outcome_confidence_from_traces

    assert _outcome_confidence_from_traces([]) is None


@pytest.mark.asyncio
async def test_composition_signal_hook_writes_routing_quality_fields():
    """Hook writes outcome_confidence, discipline_confidence, mode_confidence, routing_uncertain."""
    from core.engine.orchestration.hooks import composition_signal_hook

    ctx = HookContext(
        task_id="task:test",
        product_id="product:default",
        domain_path="architecture",
        output="output",
        snapshot={},
        classification={
            "discipline": "architecture",
            "archetype": "advisor",
            "mode": "deliberative",
            "complexity": "complex",
            "perspectives": ["strategist"],
            "engagement": {"perspectives": ["strategist"]},
            "discipline_confidence": 0.85,
            "mode_confidence": 0.72,
            "archetype_confidence": 0.78,
        },
        frameworks_used=["first-principles"],
        token_accumulator=None,
        phase_traces=[
            {"phase_idx": 0, "confidence": 0.75, "tainted": False},
            {"phase_idx": 1, "confidence": 0.65, "tainted": False},
        ],
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", return_value=None),
    ):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await composition_signal_hook(ctx)

    call_kwargs = mock_db.query.call_args[0][1]
    assert abs(call_kwargs["outcome_confidence"] - 0.7) < 1e-9  # mean of 0.75, 0.65
    assert call_kwargs["discipline_confidence"] == 0.85
    assert call_kwargs["mode_confidence"] == 0.72
    assert call_kwargs["routing_uncertain"] is False  # 0.72 >= 0.5


@pytest.mark.asyncio
async def test_hook_writes_instrument_and_tool_perf_with_product_and_score():
    """Learning loop activation: instrument_perf AND tool_perf rows are written WITH
    product and a real outcome_score (from outcome_confidence) — so FrameworkClassifier
    and ToolClassifier can actually match (WHERE product = ...) and rank them."""
    from core.engine.cognition.models import CognitiveComposition, RecipePhase
    from core.engine.orchestration.hooks import composition_signal_hook

    phase = RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")
    composition = CognitiveComposition(
        meta_skills=["coding_intelligence"],
        depth=3,
        active_phases=[phase],
        resolved_instruments={"0": ["constraint-theory"]},
        prompt_sections=[],
        fusion_mode=False,
        resolved_tools={"0": ["ace_code_context"]},
    )

    ctx = HookContext(
        task_id="task:test",
        product_id="product:default",
        domain_path="architecture",
        output="o",
        snapshot={},
        classification={
            "discipline": "architecture",
            "task_type": "code",
            "archetype": "executor",
            "mode": "deliberative",
            "complexity": "complex",
            "perspectives": ["practitioner"],
            "engagement": {"perspectives": ["practitioner"]},
            "cognitive_composition": composition,
        },
        frameworks_used=["constraint-theory"],
        token_accumulator=None,
        phase_traces=[{"phase_idx": 0, "confidence": 0.8, "tainted": False}],
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", return_value=None),
    ):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await composition_signal_hook(ctx)

    calls = mock_db.query.call_args_list
    inst = [c for c in calls if "CREATE instrument_perf" in c[0][0]]
    tool = [c for c in calls if "CREATE tool_perf" in c[0][0]]
    assert inst, "expected an instrument_perf write"
    assert tool, "expected a tool_perf write"
    # instrument_perf: product set in the query AND a real outcome_score (was None before)
    assert "product = <record>$product" in inst[0][0][0]
    assert inst[0][0][1]["product"] == "product:default"
    assert abs(inst[0][0][1]["outcome_score"] - 0.8) < 1e-9
    # tool_perf: correct slug, product, and the same score
    assert "product = <record>$product" in tool[0][0][0]
    assert tool[0][0][1]["tool_slug"] == "ace_code_context"
    assert tool[0][0][1]["product"] == "product:default"
    assert abs(tool[0][0][1]["outcome_score"] - 0.8) < 1e-9


@pytest.mark.asyncio
async def test_composition_signal_hook_flags_routing_uncertain():
    """Hook sets routing_uncertain=True when mode_confidence < 0.5."""
    from core.engine.orchestration.hooks import composition_signal_hook

    ctx = HookContext(
        task_id="task:test",
        product_id="product:default",
        domain_path="architecture",
        output="output",
        snapshot={},
        classification={
            "discipline": "architecture",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "perspectives": ["practitioner"],
            "engagement": {"perspectives": ["practitioner"]},
            "mode_confidence": 0.35,  # low — routing uncertain
        },
        frameworks_used=[],
        token_accumulator=None,
    )

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    with (
        patch("core.engine.orchestration.hooks.pool") as mock_pool,
        patch("core.engine.orchestration.hooks.estimate_baseline", return_value=None),
    ):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = mock_cm
        await composition_signal_hook(ctx)

    call_kwargs = mock_db.query.call_args[0][1]
    assert call_kwargs["routing_uncertain"] is True
    assert call_kwargs["outcome_confidence"] is None  # no phase traces
    assert call_kwargs["mode_confidence"] == 0.35
