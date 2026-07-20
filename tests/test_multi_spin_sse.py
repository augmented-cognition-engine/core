# tests/test_multi_spin_sse.py
"""Tests for multi-spin SSE streaming — event callbacks and content streaming."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.engagement_models import EngagementResult, SpinOutput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spin(perspective: str = "practitioner", **overrides) -> SpinOutput:
    defaults = {
        "content": f"Content from {perspective}",
        "handoff": f"Handoff from {perspective}",
        "confidence": 0.85,
        "open_questions": [],
        "perspective": perspective,
        "specialties_used": ["test-skill"],
    }
    defaults.update(overrides)
    return SpinOutput(**defaults)


_SINGLE_CLASSIFICATION = {
    "domain_path": "architecture",
    "archetype": "executor",
    "mode": "reactive",
    "complexity": "simple",
    "perspective": "practitioner",
    "specialties": ["python"],
    "org_context": [],
    "engagement": {
        "perspectives": ["practitioner"],
        "adversarial_pair": None,
        "rationale": "Single perspective",
    },
}

_PIPELINE_CLASSIFICATION = {
    "domain_path": "architecture",
    "archetype": "executor",
    "mode": "deliberative",
    "complexity": "complex",
    "perspective": "theorist",
    "specialties": ["distributed-systems"],
    "org_context": ["architecture"],
    "engagement": {
        "perspectives": ["theorist", "practitioner"],
        "adversarial_pair": None,
        "rationale": "Ground theory then build",
    },
}


# ---------------------------------------------------------------------------
# test_spin_events_emitted
# ---------------------------------------------------------------------------


class TestSpinEventsEmitted:
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_spin_events_emitted(self):
        """Mock engagement with 2 spins — verify spin_started and spin_completed events."""
        from core.engine.orchestrator.engagement import execute_engagement

        theorist_spin = _make_spin("theorist")
        practitioner_spin = _make_spin("practitioner")

        call_index = 0

        async def mock_execute_spin(
            task_description,
            perspective,
            prior_handoff,
            prior_questions,
            classification,
            product_id,
            event_callback=None,
            snapshot=None,
            budget_multiplier=1.0,
            **kwargs,
        ):
            nonlocal call_index
            call_index += 1
            if perspective == "theorist":
                return theorist_spin
            return practitioner_spin

        callback = AsyncMock()

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                side_effect=mock_execute_spin,
            ),
            patch(
                "core.engine.orchestrator.engagement.synthesize_spins",
                new_callable=AsyncMock,
                return_value="Synthesized",
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            result = await execute_engagement(
                task_description="Design a cache",
                classification=_PIPELINE_CLASSIFICATION,
                product_id="product:test",
                event_callback=callback,
            )

        # Collect event types
        event_types = [call.args[0]["type"] for call in callback.call_args_list]

        assert "spin_started" in event_types
        assert "spin_completed" in event_types
        assert "synthesis_started" in event_types

        # Should have 2 spin_started and 2 spin_completed
        spin_started_events = [c.args[0] for c in callback.call_args_list if c.args[0]["type"] == "spin_started"]
        spin_completed_events = [c.args[0] for c in callback.call_args_list if c.args[0]["type"] == "spin_completed"]

        assert len(spin_started_events) == 2
        assert len(spin_completed_events) == 2

        assert spin_started_events[0]["spin"] == 1
        assert spin_started_events[0]["perspective"] == "theorist"
        assert spin_started_events[0]["total"] == 2

        assert spin_started_events[1]["spin"] == 2
        assert spin_started_events[1]["perspective"] == "practitioner"

        assert spin_completed_events[0]["perspective"] == "theorist"
        assert spin_completed_events[1]["perspective"] == "practitioner"

        assert isinstance(result, EngagementResult)


# ---------------------------------------------------------------------------
# test_single_spin_no_spin_events
# ---------------------------------------------------------------------------


class TestSingleSpinNoSpinEvents:
    @pytest.mark.asyncio
    async def test_single_spin_no_spin_events(self):
        """1 perspective — no spin_started events emitted."""
        from core.engine.orchestrator.engagement import execute_engagement

        spin_output = _make_spin("practitioner")

        async def mock_execute_spin(
            task_description,
            perspective,
            prior_handoff,
            prior_questions,
            classification,
            product_id,
            event_callback=None,
            snapshot=None,
            budget_multiplier=1.0,
            **kwargs,
        ):
            return spin_output

        callback = AsyncMock()

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                side_effect=mock_execute_spin,
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            await execute_engagement(
                task_description="Simple task",
                classification=_SINGLE_CLASSIFICATION,
                product_id="product:test",
                event_callback=callback,
            )

        event_types = [call.args[0]["type"] for call in callback.call_args_list]

        # Single spin should NOT emit spin_started/spin_completed
        assert "spin_started" not in event_types
        assert "spin_completed" not in event_types
        # Single spin should NOT emit synthesis_started either
        assert "synthesis_started" not in event_types


# ---------------------------------------------------------------------------
# test_event_callback_receives_intelligence
# ---------------------------------------------------------------------------


class TestEventCallbackReceivesIntelligence:
    @pytest.mark.asyncio
    async def test_event_callback_receives_intelligence(self):
        """Verify intelligence event has spin + perspective fields."""
        from core.engine.orchestrator.engagement import execute_engagement

        theorist_spin = _make_spin("theorist")
        practitioner_spin = _make_spin("practitioner")

        mock_snapshot = {
            "insights": [
                {"tier": "T1", "content": "Insight A", "confidence": 0.9},
                {"tier": "T2", "content": "Insight B", "confidence": 0.7},
            ],
        }

        async def mock_resolve(specialties, product_id):
            return {"resolved": [{"slug": "test-skill"}]}

        async def mock_load_dual(specialties, product_id, org_context=None, mode="reactive", discipline=""):
            return mock_snapshot

        callback = AsyncMock()

        with (
            patch(
                "core.engine.orchestrator.specialty_resolver.resolve_specialties",
                side_effect=mock_resolve,
            ) as _,
            patch(
                "core.engine.orchestrator.dual_loader.load_dual_intelligence",
                side_effect=mock_load_dual,
            ) as _,
            patch("core.engine.orchestrator.engagement.llm") as mock_llm,
            patch(
                "core.engine.orchestrator.engagement.synthesize_spins",
                new_callable=AsyncMock,
                return_value="Synthesized",
            ),
        ):
            mock_llm.complete_structured = AsyncMock(side_effect=[theorist_spin, practitioner_spin])
            mock_llm.complete_json = AsyncMock(
                return_value={"archetype": "executor", "mode": "reactive", "specialties": []}
            )

            await execute_engagement(
                task_description="Design a cache",
                classification=_PIPELINE_CLASSIFICATION,
                product_id="product:test",
                event_callback=callback,
            )

        intel_events = [c.args[0] for c in callback.call_args_list if c.args[0]["type"] == "intelligence"]

        assert len(intel_events) == 2
        assert intel_events[0]["spin"] == 1
        assert intel_events[0]["perspective"] == "theorist"
        assert intel_events[0]["count"] == 2
        assert intel_events[1]["spin"] == 2
        assert intel_events[1]["perspective"] == "practitioner"


# ---------------------------------------------------------------------------
# test_synthesis_started_event
# ---------------------------------------------------------------------------


class TestSynthesisStartedEvent:
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_synthesis_started_event(self):
        """Verify synthesis_started emitted for multi-spin with correct perspectives."""
        from core.engine.orchestrator.engagement import execute_engagement

        theorist_spin = _make_spin("theorist")
        practitioner_spin = _make_spin("practitioner")

        call_index = 0

        async def mock_execute_spin(
            task_description,
            perspective,
            prior_handoff,
            prior_questions,
            classification,
            product_id,
            event_callback=None,
            snapshot=None,
            budget_multiplier=1.0,
            **kwargs,
        ):
            nonlocal call_index
            call_index += 1
            if perspective == "theorist":
                return theorist_spin
            return practitioner_spin

        callback = AsyncMock()

        with (
            patch(
                "core.engine.orchestrator.engagement._execute_single_spin",
                side_effect=mock_execute_spin,
            ),
            patch(
                "core.engine.orchestrator.engagement.synthesize_spins",
                new_callable=AsyncMock,
                return_value="Synthesized",
            ),
            patch(
                "core.engine.orchestrator.executor._load_snapshot",
                new_callable=AsyncMock,
                return_value={"insights": [], "specialties_loaded": []},
            ),
        ):
            await execute_engagement(
                task_description="Design a cache",
                classification=_PIPELINE_CLASSIFICATION,
                product_id="product:test",
                event_callback=callback,
            )

        synthesis_events = [c.args[0] for c in callback.call_args_list if c.args[0]["type"] == "synthesis_started"]

        assert len(synthesis_events) == 1
        assert synthesis_events[0]["perspectives"] == ["theorist", "practitioner"]
