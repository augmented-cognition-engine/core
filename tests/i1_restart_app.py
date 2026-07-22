"""Real API fixture for I1 restart persistence without any model call."""

from core.engine.api.main import app
from core.engine.orchestration.executor import OrchestrationResult

__all__ = ["app"]


async def _deterministic_orchestrate(request):
    return OrchestrationResult(
        task_id=request.task_id,
        output="Deterministic I1 receipt fixture output.",
        classification={
            "domain_path": "i1.restart",
            "discipline": "product",
            "archetype": "advisor",
            "mode": "deliberative",
        },
        snapshot={
            "total_count": 0,
            "specialties_loaded": [],
            "token_usage": {
                "total_tokens": 0,
                "providers": ["DeterministicFixtureProvider"],
                "models": ["fixture-v1"],
            },
        },
        events=[],
        status="completed",
        duration_ms=1,
    )


import core.engine.orchestration as orchestration  # noqa: E402

orchestration.orchestrate = _deterministic_orchestrate
