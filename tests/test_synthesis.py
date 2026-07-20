# tests/test_synthesis.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_single_result_returns_as_is():
    from core.engine.reasoning.synthesis import synthesize_framework_results

    results = [{"framework_slug": "first-principles", "output": "Analysis result"}]
    synthesis = await synthesize_framework_results(results)

    assert synthesis["synthesis"] == "Analysis result"
    assert synthesis["agreements"] == []


@pytest.mark.asyncio
async def test_multiple_results_calls_llm():
    from core.engine.reasoning.synthesis import synthesize_framework_results

    results = [
        {"framework_slug": "mece", "output": "MECE breakdown..."},
        {"framework_slug": "rca", "output": "Root cause found..."},
    ]

    with patch("core.engine.reasoning.synthesis.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(
            return_value={
                "agreements": ["Both identify process as key factor"],
                "disagreements": ["MECE suggests 3 categories, RCA suggests 2"],
                "unique_insights": ["RCA found hidden feedback loop"],
                "synthesis": "Unified analysis...",
            }
        )
        synthesis = await synthesize_framework_results(results)

    assert len(synthesis["agreements"]) == 1
    assert len(synthesis["disagreements"]) == 1
    assert len(synthesis["unique_insights"]) == 1
    assert synthesis["synthesis"] == "Unified analysis..."


@pytest.mark.asyncio
async def test_synthesis_fallback_on_error():
    from core.engine.reasoning.synthesis import synthesize_framework_results

    results = [
        {"framework_slug": "a", "output": "Output A"},
        {"framework_slug": "b", "output": "Output B"},
    ]

    with patch("core.engine.reasoning.synthesis.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=RuntimeError("LLM error"))
        synthesis = await synthesize_framework_results(results)

    # Fallback: concatenate
    assert "Output A" in synthesis["synthesis"]
    assert "Output B" in synthesis["synthesis"]
