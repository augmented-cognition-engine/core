# tests/test_synthesizer_structured.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.capture.schemas import NewInsight, SynthesizerOutput


@pytest.mark.asyncio
async def test_synthesizer_uses_structured_output():
    """Synthesizer uses complete_structured with SynthesizerOutput schema."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id="product:test", workspace_id=None)

    mock_output = SynthesizerOutput(
        new_insights=[
            NewInsight(
                content="Token naming uses kebab-case",
                tier="subdomain",
                domain_path="ux",
                insight_type="fact",
                confidence=0.9,
                clearance="open",
                source_observations=[0],
            )
        ],
        updates=[],
        conflicts=[],
        skipped=[],
    )

    with patch.object(synth, "_load_existing_insights", new_callable=AsyncMock, return_value=[]):
        with patch("core.engine.capture.synthesizer.llm") as mock_llm:
            mock_llm.complete_structured = AsyncMock(return_value=mock_output)
            synth._pending = [
                {
                    "content": "Token naming uses kebab-case",
                    "observation_type": "fact",
                    "confidence": 0.9,
                    "domain_hint": "ux",
                }
            ]
            counts = await synth.synthesize()

    assert counts["new_insights"] == 1
    mock_llm.complete_structured.assert_called_once()


@pytest.mark.asyncio
async def test_synthesizer_structured_fallback():
    """Synthesizer falls back to complete_json if structured output fails."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer(product_id="product:test", workspace_id=None)

    mock_fallback = {"new_insights": [], "updates": [], "conflicts": [], "skipped": [0]}

    with patch.object(synth, "_load_existing_insights", new_callable=AsyncMock, return_value=[]):
        with patch("core.engine.capture.synthesizer.llm") as mock_llm:
            mock_llm.complete_structured = AsyncMock(side_effect=Exception("fail"))
            mock_llm.complete_json = AsyncMock(return_value=mock_fallback)
            synth._pending = [{"content": "test", "observation_type": "fact", "confidence": 0.5}]
            counts = await synth.synthesize()

    assert counts["skipped"] == 1
