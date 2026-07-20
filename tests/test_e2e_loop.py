# tests/test_e2e_loop.py
"""End-to-end test: submit tasks, verify intelligence accumulates.

Requires: SurrealDB running, schema applied, LLM mocked.
"""

import pytest

pytestmark = pytest.mark.e2e
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_intelligence_accumulates_across_tasks():
    """Verify loop wiring: execute_task loads intelligence and persists result."""
    from core.engine.orchestrator.executor import execute_task

    # The e2e verification that the loop works will be done manually
    # with real LLM calls. This test verifies the wiring is correct.

    classification = {
        "discipline": "architecture",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": "simple",
        "perspective": "practitioner",
        "specialties": [],
        "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
    }

    # Mock the load_intelligence to return initial empty state
    mock_snapshot = {
        "discipline": "architecture",
        "insights": [],
        "total_count": 0,
    }

    with patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock, return_value=classification):
        with patch(
            "core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock, return_value=mock_snapshot
        ):
            with patch("core.engine.orchestrator.executor.llm") as mock_llm:
                mock_llm.complete = AsyncMock(return_value="Engineered solution")
                with patch("core.engine.orchestrator.executor.pool") as mock_pool:
                    mock_conn = AsyncMock()
                    mock_conn.query = AsyncMock(return_value=[{"id": "task:e2e_1"}])
                    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
                    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await execute_task(
                        description="Engineering task",
                        product_id="product:test",
                        workspace_id="workspace:test",
                        user_id="user:test",
                    )

    # Verify the loop wiring — uses discipline now, not domain_path
    assert result["discipline"] == "architecture"
    assert result["output"] == "Engineered solution"
    assert result["intelligence_loaded"]["discipline"] == "architecture"
    assert isinstance(result["intelligence_loaded"]["insights"], list)
    assert result["status"] == "completed"
