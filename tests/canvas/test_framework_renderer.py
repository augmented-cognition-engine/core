"""Tests for framework_renderer streaming and context injection."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.canvas.framework_renderer import _parse_reasoning_steps, render_framework


def test_parse_reasoning_steps_extracts_labeled_lines():
    block = """Checking — options look like bootstrap vs Series A
Scoring — dilution axis: bootstrap 9, Series A 5
Weighing — capital access (weight 0.7) outweighs dilution concern
Conclusion — Series A wins on capital access for hiring plan"""
    steps = _parse_reasoning_steps(block)
    assert len(steps) == 4
    assert steps[0] == ("Checking", "options look like bootstrap vs Series A")
    assert steps[3][0] == "Conclusion"


def test_parse_reasoning_steps_handles_missing_separator():
    block = "Just a plain line with no em dash"
    steps = _parse_reasoning_steps(block)
    # Falls back to using full line as text with label "Note"
    assert steps[0][1] == "Just a plain line with no em dash"


@pytest.mark.asyncio
async def test_render_framework_calls_on_step_for_each_reasoning_line():
    fake_response = """<reasoning>
Checking — two options on the table
Scoring — speed vs dilution trade-off
</reasoning>
<json>
{"title": "Funding", "question": "Bootstrap or raise?", "options": [{"name": "Bootstrap", "scores": {"speed": 3, "dilution": 5}, "note": "slow but clean"}, {"name": "Series A", "scores": {"speed": 5, "dilution": 2}, "note": "fast but dilutive"}], "axes": [{"name": "speed", "weight": 0.6}, {"name": "dilution", "weight": 0.4}], "recommendation": "Series A for speed"}
</json>"""

    steps_received = []

    async def capture_step(label: str, text: str, index: int) -> None:
        steps_received.append((label, text, index))

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=fake_response)

    with patch("core.engine.canvas.framework_renderer.get_llm", return_value=mock_llm):
        spec = await render_framework(
            kind="trade_off_matrix",
            prompt="Bootstrap or raise?",
            cited_text=[],
            on_step=capture_step,
        )

    assert len(steps_received) == 2
    assert steps_received[0] == ("Checking", "two options on the table", 0)
    assert spec.shape_kind == "framework_artifact"
    assert spec.payload["framework_kind"] == "trade_off_matrix"


@pytest.mark.asyncio
async def test_render_framework_injects_prior_decisions_into_prompt():
    """prior_decisions must appear in the LLM prompt when provided."""
    captured_prompts = []

    fake_response = """<reasoning>
Checking — context considered
</reasoning>
<json>
{"title": "T", "question": "Q", "options": [{"name": "A", "scores": {"x": 3, "y": 2}, "note": ""}, {"name": "B", "scores": {"x": 4, "y": 3}, "note": ""}], "axes": [{"name": "x", "weight": 0.6}, {"name": "y", "weight": 0.4}], "recommendation": "B"}
</json>"""

    async def fake_complete(prompt: str) -> str:
        captured_prompts.append(prompt)
        return fake_response

    mock_llm = AsyncMock()
    mock_llm.complete = fake_complete

    with patch("core.engine.canvas.framework_renderer.get_llm", return_value=mock_llm):
        await render_framework(
            kind="trade_off_matrix",
            prompt="Pick something",
            cited_text=["A sticky note"],
            prior_decisions=["• Previous hire: hired fullstack engineer"],
        )

    assert "• Previous hire" in captured_prompts[0]


@pytest.mark.asyncio
async def test_unsupported_framework_raises():
    with pytest.raises(NotImplementedError):
        await render_framework(kind="rice", prompt="anything", cited_text=[])


def test_extract_json_handles_code_fence_fallback():
    """_extract_json must strip ``` code fences from LLM output when <json> tag is absent."""
    from core.engine.canvas.framework_renderer import _extract_json

    fenced = '```json\n{"key": "value"}\n```'
    result = _extract_json(fenced)
    assert result == {"key": "value"}


def test_parse_reasoning_steps_hyphenated_label_truncates_at_hyphen():
    """Hyphenated labels like 'Co-Lead' are truncated — the hyphen acts as the separator."""
    from core.engine.canvas.framework_renderer import _parse_reasoning_steps

    block = "Co-Lead — some reasoning text"
    steps = _parse_reasoning_steps(block)
    # The regex [A-Za-z][A-Za-z ]{0,20}?  stops at '-', so 'Co' is the label
    # and 'Lead — some reasoning text' becomes the text portion.
    assert steps[0][0] == "Co"
    assert "Lead" in steps[0][1]


@pytest.mark.asyncio
async def test_render_framework_returns_valid_artifact_when_on_step_is_none():
    """render_framework with on_step=None (default) must return ArtifactSpec even with reasoning block."""
    from core.engine.canvas.framework_renderer import render_framework

    fake_response = """<reasoning>
Checking — two options
Scoring — comparing
</reasoning>
<json>
{"title": "T", "question": "Q", "options": [{"name": "A", "scores": {"x": 3, "y": 4}, "note": ""}, {"name": "B", "scores": {"x": 5, "y": 2}, "note": ""}], "axes": [{"name": "x", "weight": 0.5}, {"name": "y", "weight": 0.5}], "recommendation": "A"}
</json>"""

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=fake_response)

    with patch("core.engine.canvas.framework_renderer.get_llm", return_value=mock_llm):
        # No on_step argument — tests the default None path
        spec = await render_framework(
            kind="trade_off_matrix",
            prompt="Choose?",
            cited_text=[],
        )

    assert spec.shape_kind == "framework_artifact"
    assert spec.payload["framework_kind"] == "trade_off_matrix"
