"""Tests for the canvas-event → UI-protocol bridge."""

import pytest

from core.engine.canvas.canvas_ui_events import translate_canvas_event

RID = "run_x"
PID = "product:platform"


@pytest.mark.unit
def test_pipeline_classify_maps_to_classification():
    ev = translate_canvas_event(
        "pipeline.classify",
        {"discipline": "product_strategy", "archetype": "analyst", "mode": "deliberative"},
        run_id=RID,
        product_id=PID,
    )
    d = ev.to_dict()
    assert d["type"] == "classification"
    assert d["discipline"] == "product_strategy"
    assert d["archetypes"] == ["analyst"]
    assert d["depth"] == 2


@pytest.mark.unit
def test_pipeline_orchestrate_carries_perspectives_without_clobbering_discipline():
    ev = translate_canvas_event(
        "pipeline.orchestrate",
        {"perspectives": ["analyst", "advisor"], "total": 2},
        run_id=RID,
        product_id=PID,
    )
    d = ev.to_dict()
    assert d["type"] == "classification"
    assert d["archetypes"] == ["analyst", "advisor"]
    # discipline/depth left None so the frontend's `?? prev` keeps the prior value
    assert d["discipline"] is None
    assert d["depth"] is None


@pytest.mark.unit
def test_pipeline_orchestrate_empty_perspectives_is_skipped():
    assert translate_canvas_event("pipeline.orchestrate", {"perspectives": []}, run_id=RID, product_id=PID) is None


@pytest.mark.unit
def test_perspective_lifecycle_shares_one_task_id():
    start = translate_canvas_event(
        "agent.perspective.start",
        {"archetype": "analyst", "mode": "deliberative", "perspective_index": 1},
        run_id=RID,
        product_id=PID,
    ).to_dict()
    step = translate_canvas_event(
        "agent.perspective.step",
        {"archetype": "analyst", "content": "Lead with security.", "perspective_index": 1},
        run_id=RID,
        product_id=PID,
    ).to_dict()
    end = translate_canvas_event(
        "agent.perspective.end",
        {"archetype": "analyst", "handoff": "", "confidence": 0.8, "perspective_index": 1},
        run_id=RID,
        product_id=PID,
    ).to_dict()

    assert start["type"] == "engagement_start"
    assert start["archetypes"] == ["analyst"]
    assert step["type"] == "token"
    assert step["content"] == "Lead with security."
    assert end["type"] == "engagement_done"
    # All three target the same track so token/done land where start opened.
    assert start["task_id"] == step["task_id"] == end["task_id"] == "canvas-perspective-1"


@pytest.mark.unit
def test_synthesis_lifecycle_shares_synthesis_task_id():
    start = translate_canvas_event("synthesis.start", {}, run_id=RID, product_id=PID).to_dict()
    step = translate_canvas_event(
        "synthesis.step", {"content": "On balance, ship security-first."}, run_id=RID, product_id=PID
    ).to_dict()
    end = translate_canvas_event("synthesis.end", {}, run_id=RID, product_id=PID).to_dict()
    assert start["type"] == "engagement_start"
    assert step["type"] == "token"
    assert step["content"] == "On balance, ship security-first."
    assert end["type"] == "engagement_done"
    assert start["task_id"] == step["task_id"] == end["task_id"] == "canvas-synthesis"


@pytest.mark.unit
def test_unmapped_event_returns_none():
    assert translate_canvas_event("pipeline.compose", {"depth": 2}, run_id=RID, product_id=PID) is None
    assert translate_canvas_event("block.start", {}, run_id=RID, product_id=PID) is None
