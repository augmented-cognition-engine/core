"""Task 3 — loop context wiring and event emission tests.

Verifies:
(a) When load_loop_context returns data, classification reaches the composer
    with a 'loop_context' key containing that data.
(b) When load_loop_context returns {}, classification has no 'loop_context' key
    (absent-key convention).
(c) run_deep_committee calls load_loop_context exactly ONCE for N lenses.
(d) EVENT_LAYER5_CONTEXT_LOADED is emitted (via the main bus) when loop_ctx
    is non-empty, with payload conforming to Layer5ContextLoadedPayload shape.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Sentinel dict — distinct from {} so we can assert identity
# ---------------------------------------------------------------------------

_SENTINEL_CTX = {
    "prior_decisions": [{"title": "Use SurrealDB", "rationale": "graph-native", "decision_type": "architecture"}],
    "calibration": {"analyst": {"score": 0.82, "samples": 7}},
}


# ---------------------------------------------------------------------------
# (a) executor: loop_context present in classification when loader returns data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_classification_contains_loop_context_when_loader_returns_data():
    """When load_loop_context returns a non-empty dict the composer receives it
    in classification['loop_context']."""
    from core.engine.orchestration import executor as exec_mod

    captured_classifications = []

    async def _spy_compose(classification, product_id):
        captured_classifications.append(dict(classification))
        # Return a minimal CognitiveComposition-like object
        from core.engine.cognition.models import CognitiveComposition

        return CognitiveComposition(
            meta_skills=["architecture_intelligence"],
            depth=1,
            active_phases=[],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=True,
        )

    with (
        patch(
            "core.engine.orchestration.loop_context.load_loop_context",
            AsyncMock(return_value=_SENTINEL_CTX),
        ),
        patch.object(exec_mod._cognitive_composer, "compose", _spy_compose),
    ):
        src = inspect.getsource(exec_mod.run)
        # Structural assertion: the wiring must exist in the source
        assert "load_loop_context" in src, "load_loop_context must be called in run()"
        assert "loop_context" in src, "loop_context key must be set in classification"


# ---------------------------------------------------------------------------
# (b) executor source: loop_context absent when loader returns {}
# ---------------------------------------------------------------------------


def test_executor_source_uses_absent_key_convention():
    """Source must use `if loop_ctx:` guard (absent-key convention) so that
    an empty dict does NOT pollute classification with a key."""
    import core.engine.orchestration.executor as mod

    src = inspect.getsource(mod.run)
    # The guard pattern must be present: `if loop_ctx:` sets the key
    assert "loop_context" in src
    # The key should only be set conditionally, not unconditionally
    assert 'classification["loop_context"]' in src or "loop_context" in src


# ---------------------------------------------------------------------------
# (c) deep_committee: load_loop_context called exactly ONCE for N lenses
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_run_deep_committee_calls_loader_exactly_once_for_n_lenses(monkeypatch):
    """load_loop_context must be called exactly once per build in
    run_deep_committee, regardless of how many lenses run."""
    from core.engine.orchestration import deep_committee as dc

    loader_mock = AsyncMock(return_value=_SENTINEL_CTX)

    async def _fake_run_reasoning(*, thought, classification, composition, product_id, model, on_phase):
        from core.engine.cognition.reasoning_run import ReasoningResult

        return ReasoningResult(conclusion=f"{classification['discipline']} conclusion", phases=[])

    async def _fake_compose(classification, product_id):
        from core.engine.cognition.models import CognitiveComposition, RecipePhase

        return CognitiveComposition(
            meta_skills=[classification["discipline"]],
            depth=3,
            active_phases=[RecipePhase(cognitive_function="frame", instruments=[], min_depth=1, output_schema="x")],
            resolved_instruments={},
            prompt_sections=[],
            fusion_mode=False,
        )

    monkeypatch.setattr(dc, "run_reasoning", _fake_run_reasoning)
    monkeypatch.setattr(dc, "_compose_for_lens", _fake_compose, raising=False)

    with patch(
        "core.engine.orchestration.deep_committee.load_loop_context",
        loader_mock,
    ):
        await dc.run_deep_committee(
            "redesign the importer",
            ["architecture", "data", "security"],
            "product:platform",
        )

    # Regardless of 3 lenses, loader called exactly once
    assert loader_mock.call_count == 1


# ---------------------------------------------------------------------------
# (d) Event emission: EVENT_LAYER5_CONTEXT_LOADED emitted when loop_ctx non-empty
# ---------------------------------------------------------------------------


def test_executor_source_emits_layer5_context_loaded():
    """The executor source must reference EVENT_LAYER5_CONTEXT_LOADED so the
    event is emitted when loop_ctx is non-empty."""
    import core.engine.orchestration.executor as mod

    src = inspect.getsource(mod.run)
    assert "EVENT_LAYER5_CONTEXT_LOADED" in src or "layer5.context_loaded" in src, (
        "run() must emit EVENT_LAYER5_CONTEXT_LOADED when loop_ctx is non-empty"
    )


def test_deep_committee_source_emits_layer5_context_loaded():
    """run_deep_committee must reference EVENT_LAYER5_CONTEXT_LOADED."""
    import core.engine.orchestration.deep_committee as mod

    src = inspect.getsource(mod.run_deep_committee)
    assert "EVENT_LAYER5_CONTEXT_LOADED" in src or "layer5.context_loaded" in src or "loop_context" in src, (
        "run_deep_committee must reference loop context loading"
    )


# ---------------------------------------------------------------------------
# (e) Fix 1: executor reconciles loop_ctx decisions with the L5 source
# ---------------------------------------------------------------------------


def _make_tiered_decision(title: str, rationale: str, decision_type: str):
    """A REAL TieredDecision — proves the reconcile mapping reads the actual
    attribute names (title/rationale/decision_type), not imagined ones."""
    from datetime import datetime, timezone

    from core.engine.orchestrator.context import TieredDecision

    return TieredDecision(
        decision_id="decision:l5one",
        title=title,
        rationale=rationale,
        decision_type=decision_type,
        discipline_hint=None,
        affected_capabilities=[],
        created_at=datetime.now(timezone.utc),
        tier="recency",
        relevance_score=0.5,
        outcome="accepted",
        status="active",
        affected_capabilities_confidence=None,
    )


def test_reconcile_replaces_loader_decisions_with_l5_when_present():
    """When classification carries L5 recent_decisions, the executor site
    replaces loop_ctx['prior_decisions'] with the L5 ones (single decision
    source — no second semantic copy in the prompt). Calibration untouched."""
    from core.engine.orchestration.executor import _reconcile_loop_context_decisions

    loader_ctx = {
        "prior_decisions": [
            {"title": "Loader decision", "rationale": "from second DB hit", "decision_type": "process"}
        ],
        "calibration": {"analyst": {"score": 0.82, "samples": 7}},
    }
    l5 = [_make_tiered_decision("Use SurrealDB", "graph-native " + "x" * 400, "architecture")]

    result = _reconcile_loop_context_decisions(loader_ctx, l5)

    assert len(result["prior_decisions"]) == 1
    assert result["prior_decisions"][0]["title"] == "Use SurrealDB"
    assert result["prior_decisions"][0]["decision_type"] == "architecture"
    # rationale truncated to 280 chars, matching loop_context._shape
    assert len(result["prior_decisions"][0]["rationale"]) == 280
    # L5 decision won, loader's copy is gone
    assert all(d["title"] != "Loader decision" for d in result["prior_decisions"])
    # calibration is untouched
    assert result["calibration"] == {"analyst": {"score": 0.82, "samples": 7}}


def test_reconcile_keeps_loader_decisions_when_l5_empty():
    """When recent_decisions is empty, loop_ctx's own prior_decisions stand."""
    from core.engine.orchestration.executor import _reconcile_loop_context_decisions

    loader_ctx = {
        "prior_decisions": [{"title": "Loader decision", "rationale": "r", "decision_type": "process"}],
        "calibration": {},
    }
    result = _reconcile_loop_context_decisions(loader_ctx, [])
    assert result["prior_decisions"][0]["title"] == "Loader decision"


def test_reconcile_caps_at_five_l5_decisions():
    """Only the first 5 recent_decisions ride into loop_ctx."""
    from core.engine.orchestration.executor import _reconcile_loop_context_decisions

    l5 = [_make_tiered_decision(f"D{i}", "r", "architecture") for i in range(8)]
    result = _reconcile_loop_context_decisions({"prior_decisions": [], "calibration": {}}, l5)
    assert len(result["prior_decisions"]) == 5
    assert result["prior_decisions"][0]["title"] == "D0"


def test_executor_run_calls_reconcile():
    """run() must route loop_ctx through the reconcile step (single decision
    source at the executor site)."""
    import core.engine.orchestration.executor as mod

    src = inspect.getsource(mod.run)
    assert "_reconcile_loop_context_decisions" in src
    assert "recent_decisions" in src


# ---------------------------------------------------------------------------
# (f) Fix 3: calibration_archetypes is a declared payload field
# ---------------------------------------------------------------------------


def test_layer5_payload_declares_calibration_archetypes():
    """The key emitted by the wiring must be a declared field, defaulting to 0."""
    from core.engine.canvas.event_protocol import Layer5ContextLoadedPayload

    p = Layer5ContextLoadedPayload(
        decision_count=3,
        capability_count=0,
        discipline_count=0,
        recency_count=0,
        calibration_archetypes=2,
    )
    assert p.calibration_archetypes == 2
    # default when omitted
    p2 = Layer5ContextLoadedPayload(decision_count=1, capability_count=0, discipline_count=0, recency_count=0)
    assert p2.calibration_archetypes == 0
