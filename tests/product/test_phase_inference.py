import pytest

from core.engine.product.phase_inference import SuggestedPhase, suggest_phase


@pytest.mark.asyncio
async def test_suggest_phase_returns_suggestion(db_pool):
    suggestion = await suggest_phase(db_pool, "product:platform")
    assert isinstance(suggestion, SuggestedPhase)
    assert suggestion.phase in {"discovery", "poc", "alpha", "beta", "ga", "mature"}


def test_suggested_phase_has_rationale():
    sp = SuggestedPhase(
        phase="poc",
        confidence=0.75,
        signals={
            "capability_count": 12,
            "completion_rate": 0.55,
            "shipped_demo": False,
        },
        rationale="12 capabilities; 55% complete; no shipped demo recording — fits POC.",
    )
    assert sp.confidence == 0.75
    assert "POC" in sp.rationale
