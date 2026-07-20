from unittest.mock import AsyncMock, patch

import pytest

from core.engine.canvas.design_renderer import render_design_options


@pytest.mark.asyncio
async def test_render_design_options_returns_artifact_spec():
    fake_response = """<reasoning>
Checking — two layout options under review
Scoring — visual hierarchy is the dominant axis
</reasoning>
<json>
{
  "title": "Homepage layout",
  "question": "Single-column or split?",
  "options": [
    {"name": "Single-column", "scores": {"hierarchy": 8, "scan_cost": 9}, "note": "linear scan, low cognitive load"},
    {"name": "Split-panel", "scores": {"hierarchy": 6, "scan_cost": 5}, "note": "two focal points compete"}
  ],
  "axes": [
    {"name": "hierarchy", "weight": 0.6},
    {"name": "scan_cost", "weight": 0.4}
  ],
  "recommendation": "Single-column for its lower scan cost at early stage"
}
</json>"""

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=fake_response)

    steps = []

    async def capture(label: str, text: str, idx: int) -> None:
        steps.append((label, text, idx))

    with patch("core.engine.canvas.design_renderer.get_llm", return_value=mock_llm):
        spec = await render_design_options(
            prompt="Homepage layout: single-column or split?",
            cited_text=["User scans from top-left"],
            on_step=capture,
        )

    assert spec.shape_kind == "framework_artifact"
    assert spec.payload["framework_kind"] == "design_options"
    assert len(spec.payload["options"]) == 2
    assert len(steps) == 2


@pytest.mark.asyncio
async def test_render_design_options_validates_minimum_options():
    bad_response = """<reasoning>
Checking — only one option
</reasoning>
<json>
{"title": "T", "question": "Q", "options": [{"name": "A", "scores": {"x": 5}, "note": ""}], "axes": [{"name": "x", "weight": 1.0}], "recommendation": "A"}
</json>"""

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=bad_response)

    with patch("core.engine.canvas.design_renderer.get_llm", return_value=mock_llm):
        with pytest.raises(ValueError, match="at least 2"):
            await render_design_options(prompt="Single option?", cited_text=[])
