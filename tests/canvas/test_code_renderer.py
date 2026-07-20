from unittest.mock import AsyncMock, patch

import pytest

from core.engine.canvas.code_renderer import render_code_architecture


@pytest.mark.asyncio
async def test_render_code_architecture_returns_artifact():
    fake_response = """<reasoning>
Checking — engine/canvas/participant.py has 3 direct dependents
Scoring — blast radius: medium; 8 files import from it
Weighing — changing CanvasParticipant state machine affects all surface adapters
Conclusion — refactor with backward compat shim, not flag-day rename
</reasoning>
<json>
{
  "title": "CanvasParticipant architecture",
  "module": "core/engine/canvas/participant.py",
  "nodes": [
    {"id": "participant", "label": "CanvasParticipant", "type": "core"},
    {"id": "api_canvas", "label": "core/engine/api/canvas.py", "type": "consumer"},
    {"id": "framework_renderer", "label": "core/engine/canvas/framework_renderer.py", "type": "consumer"}
  ],
  "edges": [
    {"from": "api_canvas", "to": "participant", "label": "imports"},
    {"from": "framework_renderer", "to": "participant", "label": "calls"}
  ],
  "blast_radius": {"score": 0.55, "affected_files": 8, "risk": "medium"},
  "recommendation": "Add backward compat shim before renaming state fields"
}
</json>"""

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=fake_response)
    steps = []

    async def capture(label: str, text: str, idx: int) -> None:
        steps.append(label)

    with patch("core.engine.canvas.code_renderer.get_llm", return_value=mock_llm):
        spec = await render_code_architecture(
            prompt="Refactor CanvasParticipant state machine",
            cited_text=["Current state: IDLE/WATCHING/DRAFTING"],
            on_step=capture,
        )

    assert spec.shape_kind == "framework_artifact"
    assert spec.payload["framework_kind"] == "code_architecture"
    assert "nodes" in spec.payload
    assert "blast_radius" in spec.payload
    assert len(steps) == 4


@pytest.mark.asyncio
async def test_render_code_architecture_validates_minimum_nodes():
    bad_response = """<reasoning>
Checking — only one node
</reasoning>
<json>
{
  "title": "T", "module": "m.py",
  "nodes": [{"id": "a", "label": "A", "type": "core"}],
  "edges": [],
  "blast_radius": {"score": 0.1, "affected_files": 1, "risk": "low"},
  "recommendation": "Fine as-is"
}
</json>"""

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=bad_response)

    with patch("core.engine.canvas.code_renderer.get_llm", return_value=mock_llm):
        with pytest.raises(ValueError, match="at least 2 nodes"):
            await render_code_architecture(prompt="Single node?", cited_text=[])


@pytest.mark.asyncio
async def test_render_code_architecture_validates_risk_enum():
    bad_response = """<reasoning>
Checking — one node, bad risk
</reasoning>
<json>
{
  "title": "T", "module": "m.py",
  "nodes": [{"id": "a", "label": "A", "type": "core"}, {"id": "b", "label": "B", "type": "consumer"}],
  "edges": [],
  "blast_radius": {"score": 0.5, "affected_files": 3, "risk": "critical"},
  "recommendation": "Be careful"
}
</json>"""

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=bad_response)

    with patch("core.engine.canvas.code_renderer.get_llm", return_value=mock_llm):
        with pytest.raises(ValueError, match="blast_radius.risk"):
            await render_code_architecture(prompt="Bad risk?", cited_text=[])
