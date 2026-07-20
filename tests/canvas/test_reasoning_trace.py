"""Tests for reasoning trace collection in render_via_orchestration and FrameworkCompletedPayload."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PERSPECTIVE_END,
    EVENT_AGENT_PERSPECTIVE_START,
    EVENT_AGENT_PERSPECTIVE_STEP,
    EVENT_SYNTHESIS_END,
    EVENT_SYNTHESIS_STEP,
    AgentPerspectiveEndPayload,
    AgentPerspectiveStartPayload,
    AgentPerspectiveStepPayload,
    FrameworkCompletedPayload,
    SynthesisStepPayload,
)
from core.engine.canvas.framework_renderer import ArtifactSpec

# ---------------------------------------------------------------------------
# ArtifactSpec
# ---------------------------------------------------------------------------


def test_artifact_spec_reasoning_trace_defaults_to_none():
    spec = ArtifactSpec(shape_kind="framework_artifact", payload={})
    assert spec.reasoning_trace is None


def test_artifact_spec_accepts_reasoning_trace():
    trace = {"classify": {"discipline": "architecture"}, "perspectives": []}
    spec = ArtifactSpec(shape_kind="framework_artifact", payload={}, reasoning_trace=trace)
    assert spec.reasoning_trace is not None
    assert spec.reasoning_trace["classify"]["discipline"] == "architecture"


# ---------------------------------------------------------------------------
# FrameworkCompletedPayload round-trip
# ---------------------------------------------------------------------------


def test_framework_completed_payload_reasoning_trace_defaults_to_none():
    p = FrameworkCompletedPayload(shape_kind="framework_artifact", framework_kind="trade_off_matrix", payload={})
    assert p.reasoning_trace is None


def test_framework_completed_payload_reasoning_trace_round_trip():
    trace = {
        "classify": {"discipline": "architecture", "archetype": "analyst", "mode": "deliberative", "specialties": []},
        "compose": None,
        "orchestrate": {"perspectives": ["analyst", "sentinel"], "total": 2},
        "perspectives": [
            {
                "archetype": "analyst",
                "mode": "deliberative",
                "index": 0,
                "content": "Analysis text",
                "handoff": "pass to sentinel",
                "confidence": 0.9,
                "complete": True,
            },
            {
                "archetype": "sentinel",
                "mode": "deliberative",
                "index": 1,
                "content": "Risk found",
                "handoff": "",
                "confidence": 0.75,
                "complete": True,
            },
        ],
        "synthesis": {"content": "Final synthesis", "complete": True},
    }
    p = FrameworkCompletedPayload(
        shape_kind="framework_artifact",
        framework_kind="trade_off_matrix",
        payload={"title": "Test"},
        reasoning_trace=trace,
    )
    dumped = p.model_dump()
    assert dumped["reasoning_trace"] is not None
    persp = dumped["reasoning_trace"]["perspectives"]
    # sentinel: archetype and confidence must survive the round-trip
    assert persp[0]["archetype"] == "analyst"
    assert persp[0]["confidence"] == pytest.approx(0.9)
    assert persp[1]["archetype"] == "sentinel"
    assert persp[1]["confidence"] == pytest.approx(0.75)
    assert dumped["reasoning_trace"]["synthesis"]["content"] == "Final synthesis"


# ---------------------------------------------------------------------------
# render_via_orchestration — trace collection
# ---------------------------------------------------------------------------


async def _fake_engagement_emitting_events(task, classification, product_id, on_canvas_event):
    """Simulate run_canvas_engagement emitting perspective + synthesis events."""
    await on_canvas_event(
        EVENT_AGENT_PERSPECTIVE_START,
        AgentPerspectiveStartPayload(
            archetype="analyst", mode="deliberative", perspective_index=0, total_perspectives=2
        ).model_dump(),
    )
    await on_canvas_event(
        EVENT_AGENT_PERSPECTIVE_STEP,
        AgentPerspectiveStepPayload(archetype="analyst", content="Analyst view here", perspective_index=0).model_dump(),
    )
    await on_canvas_event(
        EVENT_AGENT_PERSPECTIVE_END,
        AgentPerspectiveEndPayload(
            archetype="analyst", handoff="hand off to advisor", confidence=0.88, perspective_index=0
        ).model_dump(),
    )
    await on_canvas_event(
        EVENT_AGENT_PERSPECTIVE_START,
        AgentPerspectiveStartPayload(
            archetype="advisor", mode="deliberative", perspective_index=1, total_perspectives=2
        ).model_dump(),
    )
    await on_canvas_event(
        EVENT_AGENT_PERSPECTIVE_END,
        AgentPerspectiveEndPayload(archetype="advisor", handoff="", confidence=0.72, perspective_index=1).model_dump(),
    )
    await on_canvas_event(
        EVENT_SYNTHESIS_STEP,
        SynthesisStepPayload(content="Synthesized output").model_dump(),
    )
    await on_canvas_event(EVENT_SYNTHESIS_END, {})
    return "Synthesized output"


@pytest.mark.asyncio
async def test_render_via_orchestration_collects_trace():
    fake_spec = ArtifactSpec(shape_kind="framework_artifact", payload={"framework_kind": "trade_off_matrix"})

    with (
        patch(
            "core.engine.canvas.orchestrated_renderer.run_canvas_engagement",
            side_effect=_fake_engagement_emitting_events,
        ),
        patch(
            "core.engine.canvas.orchestrated_renderer._extract_artifact",
            new=AsyncMock(return_value=fake_spec),
        ),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        spec = await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="Option A vs B?",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
        )

    assert spec.reasoning_trace is not None, "reasoning_trace must be populated"
    trace = spec.reasoning_trace

    # classify captured
    assert trace["classify"]["archetype"] == "analyst"

    # perspectives: archetype + confidence sentinel
    persp = trace["perspectives"]
    assert len(persp) == 2
    assert persp[0]["archetype"] == "analyst"
    assert persp[0]["confidence"] == pytest.approx(0.88)
    assert persp[0]["complete"] is True
    assert persp[1]["archetype"] == "advisor"
    assert persp[1]["confidence"] == pytest.approx(0.72)

    # synthesis captured
    assert trace["synthesis"]["content"] == "Synthesized output"
    assert trace["synthesis"]["complete"] is True


@pytest.mark.asyncio
async def test_render_via_orchestration_trace_none_when_no_events():
    """When no events are emitted (degenerate path), perspectives list is empty."""
    fake_spec = ArtifactSpec(shape_kind="framework_artifact", payload={})

    with (
        patch(
            "core.engine.canvas.orchestrated_renderer.run_canvas_engagement",
            new=AsyncMock(return_value="analysis"),
        ),
        patch(
            "core.engine.canvas.orchestrated_renderer._extract_artifact",
            new=AsyncMock(return_value=fake_spec),
        ),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        spec = await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="simple?",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
        )

    # trace_data only has pipeline.classify emitted (classify event always fires)
    # so reasoning_trace is not None, but perspectives list is empty
    assert spec.reasoning_trace is not None
    assert spec.reasoning_trace.get("perspectives", []) == []


@pytest.mark.asyncio
async def test_render_via_orchestration_single_perspective_no_synthesis():
    """Single-perspective path: synthesis events are not emitted; trace.synthesis is None."""

    async def _single_perspective(task, classification, product_id, on_canvas_event):
        await on_canvas_event(
            EVENT_AGENT_PERSPECTIVE_START,
            AgentPerspectiveStartPayload(
                archetype="executor", mode="deliberative", perspective_index=0, total_perspectives=1
            ).model_dump(),
        )
        await on_canvas_event(
            EVENT_AGENT_PERSPECTIVE_END,
            AgentPerspectiveEndPayload(
                archetype="executor", handoff="", confidence=0.65, perspective_index=0
            ).model_dump(),
        )
        # no synthesis events — single perspective short-circuit
        return "executor analysis"

    fake_spec = ArtifactSpec(shape_kind="framework_artifact", payload={})

    with (
        patch("core.engine.canvas.orchestrated_renderer.run_canvas_engagement", side_effect=_single_perspective),
        patch("core.engine.canvas.orchestrated_renderer._extract_artifact", new=AsyncMock(return_value=fake_spec)),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        spec = await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="single?",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
        )

    trace = spec.reasoning_trace
    assert trace is not None
    assert len(trace["perspectives"]) == 1
    assert trace["perspectives"][0]["archetype"] == "executor"
    assert trace["perspectives"][0]["confidence"] == pytest.approx(0.65)
    # synthesis not emitted → None
    assert trace.get("synthesis") is None
