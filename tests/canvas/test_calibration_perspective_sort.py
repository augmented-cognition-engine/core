"""B.8 — calibration weights re-sort perspectives in render_via_orchestration."""

from unittest.mock import MagicMock, patch

import pytest


def _make_classification(perspectives):
    return {
        "discipline": "architecture",
        "archetype": "analyst",
        "mode": "deliberative",
        "engagement": {"perspectives": perspectives, "adversarial_pair": None, "rationale": ""},
        "specialties": [],
    }


@pytest.mark.asyncio
async def test_perspectives_reordered_by_calibration():
    """Higher-calibration archetype moves to front of perspectives list."""
    # Canvas hardcodes ["analyst", "advisor"]; calibration re-sorts advisor (0.9) before analyst (0.6).
    calibration = {"advisor": 0.9, "analyst": 0.6}

    captured_perspectives: dict = {}

    async def fake_engagement(task, clf, product_id, emit):
        captured_perspectives["perspectives"] = clf.get("engagement", {}).get("perspectives", [])
        return "analysis text"

    async def fake_compose(self, clf, product_id):
        result = MagicMock()
        result.prompt_sections = []
        result.meta_skills = []
        result.depth = 1
        result.fusion_mode = True
        result.active_phases = []
        return result

    async def fake_extract(kind, prompt, analysis, cited, prior):
        from core.engine.canvas.framework_renderer import ArtifactSpec

        return ArtifactSpec(shape_kind="framework_artifact", payload={})

    with (
        patch("core.engine.canvas.orchestrated_renderer.run_canvas_engagement", fake_engagement),
        patch("core.engine.cognition.composer.CognitiveComposer.compose", fake_compose),
        patch("core.engine.canvas.orchestrated_renderer._extract_artifact", fake_extract),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="test",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
            calibration_weights=calibration,
        )

    # advisor (0.9) should lead over analyst (0.6)
    perspectives = captured_perspectives["perspectives"]
    assert perspectives[0] == "advisor"


@pytest.mark.asyncio
async def test_perspectives_unchanged_when_no_calibration():
    """Hardcoded default order preserved when calibration_weights is empty."""
    captured_perspectives: dict = {}

    async def fake_engagement(task, clf, product_id, emit):
        captured_perspectives["perspectives"] = clf.get("engagement", {}).get("perspectives", [])
        return "analysis text"

    async def fake_compose(self, clf, product_id):
        result = MagicMock()
        result.prompt_sections = []
        result.meta_skills = []
        result.depth = 1
        result.fusion_mode = True
        result.active_phases = []
        return result

    async def fake_extract(kind, prompt, analysis, cited, prior):
        from core.engine.canvas.framework_renderer import ArtifactSpec

        return ArtifactSpec(shape_kind="framework_artifact", payload={})

    with (
        patch("core.engine.canvas.orchestrated_renderer.run_canvas_engagement", fake_engagement),
        patch("core.engine.cognition.composer.CognitiveComposer.compose", fake_compose),
        patch("core.engine.canvas.orchestrated_renderer._extract_artifact", fake_extract),
    ):
        from core.engine.canvas.orchestrated_renderer import render_via_orchestration

        await render_via_orchestration(
            kind="trade_off_matrix",
            prompt="test",
            cited_text=[],
            prior_decisions=None,
            product_id="product:test",
            calibration_weights={},
        )

    assert captured_perspectives["perspectives"] == ["analyst", "advisor"]
