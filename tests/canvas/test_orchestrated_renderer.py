from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_render_via_orchestration_returns_artifact_spec():
    events = []

    async def on_event(event_type, payload):
        events.append(event_type)

    fake_classification = {
        "mode": "deliberative",
        "engagement": {"perspectives": ["analyst"], "adversarial_pair": None},
        "specialties": [],
        "discipline": "architecture",
        "archetype": "analyst",
    }
    fake_analysis = "Option A is better because of lower complexity."
    fake_artifact_payload = {
        "title": "Test Matrix",
        "question": "A vs B?",
        "options": [
            {"name": "A", "scores": {"Speed": 8, "Cost": 6}, "note": "fast"},
            {"name": "B", "scores": {"Speed": 5, "Cost": 9}, "note": "cheap"},
        ],
        "axes": [{"name": "Speed", "weight": 0.6}, {"name": "Cost", "weight": 0.4}],
        "recommendation": "Choose A for speed.",
    }

    with (
        patch(
            "core.engine.canvas.orchestrated_renderer.run_canvas_engagement", new=AsyncMock(return_value=fake_analysis)
        ),
        patch(
            "core.engine.canvas.orchestrated_renderer._extract_artifact",
            new=AsyncMock(
                return_value=MagicMock(
                    shape_kind="framework_artifact",
                    payload={"framework_kind": "trade_off_matrix", **fake_artifact_payload},
                )
            ),
        ),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        spec = await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="A vs B?",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
            on_canvas_event=on_event,
        )

    assert spec.shape_kind == "framework_artifact"
    assert spec.payload["framework_kind"] == "trade_off_matrix"


@pytest.mark.asyncio
async def test_canvas_always_uses_deliberative_mode():
    """Canvas pipeline always uses deliberative mode via hardcoded defaults."""
    captured_classification = {}

    async def fake_engagement(task, classification, product_id, on_canvas_event):
        captured_classification.update(classification)
        return "analysis text"

    with (
        patch("core.engine.canvas.orchestrated_renderer.run_canvas_engagement", side_effect=fake_engagement),
        patch(
            "core.engine.canvas.orchestrated_renderer._extract_artifact",
            new=AsyncMock(return_value=MagicMock(shape_kind="framework_artifact", payload={})),
        ),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="simple question",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
            on_canvas_event=AsyncMock(),
        )

    assert captured_classification["mode"] == "deliberative"
    assert captured_classification["engagement"]["perspectives"] == ["analyst", "advisor"]
