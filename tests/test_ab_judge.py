from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_shadow_comparison_returns_treatment_preference():
    from core.engine.intelligence.ab_judge import run_shadow_comparison

    mock_result = MagicMock()
    mock_result.output = "control output"

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value='{"preference": "A", "rationale": "A is more correct"}')

    with (
        patch("core.engine.intelligence.ab_judge.orchestrate", AsyncMock(return_value=mock_result)),
        patch("core.engine.intelligence.ab_judge.get_llm", return_value=mock_llm),
    ):
        result = await run_shadow_comparison(
            description="build a REST API",
            classification={"discipline": "api_design", "mode": "reactive", "complexity": "simple"},
            product_id="product:test",
            treatment_output="treatment output",
        )

    assert result is not None
    assert result["judge_preference"] == "treatment"
    assert "judge_rationale" in result


@pytest.mark.asyncio
async def test_run_shadow_comparison_normalizes_control_preference():
    from core.engine.intelligence.ab_judge import run_shadow_comparison

    mock_result = MagicMock()
    mock_result.output = "control output"

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value='{"preference": "B", "rationale": "B is cleaner"}')

    with (
        patch("core.engine.intelligence.ab_judge.orchestrate", AsyncMock(return_value=mock_result)),
        patch("core.engine.intelligence.ab_judge.get_llm", return_value=mock_llm),
    ):
        result = await run_shadow_comparison(
            description="write a unit test",
            classification={"discipline": "testing", "mode": "reactive", "complexity": "simple"},
            product_id="product:test",
            treatment_output="treatment",
        )

    assert result["judge_preference"] == "control"


@pytest.mark.asyncio
async def test_run_shadow_comparison_returns_none_on_llm_failure():
    from core.engine.intelligence.ab_judge import run_shadow_comparison

    mock_result = MagicMock()
    mock_result.output = "control"

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM timeout"))

    with (
        patch("core.engine.intelligence.ab_judge.orchestrate", AsyncMock(return_value=mock_result)),
        patch("core.engine.intelligence.ab_judge.get_llm", return_value=mock_llm),
    ):
        result = await run_shadow_comparison(
            description="test",
            classification={"mode": "reactive", "complexity": "simple"},
            product_id="product:test",
            treatment_output="treatment",
        )

    assert result is None


@pytest.mark.asyncio
async def test_shadow_request_has_shadow_run_true():
    from core.engine.intelligence.ab_judge import run_shadow_comparison

    captured_requests = []

    async def mock_orchestrate(req):
        captured_requests.append(req)
        mock = MagicMock()
        mock.output = "control"
        return mock

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value='{"preference": "tie", "rationale": "equal"}')

    with (
        patch("core.engine.intelligence.ab_judge.orchestrate", side_effect=mock_orchestrate),
        patch("core.engine.intelligence.ab_judge.get_llm", return_value=mock_llm),
    ):
        await run_shadow_comparison(
            description="design API",
            classification={"mode": "deliberative", "complexity": "complex"},
            product_id="product:test",
            treatment_output="treatment",
        )

    assert len(captured_requests) == 1
    assert captured_requests[0].shadow_run is True
    assert captured_requests[0].persist_task is False
    assert captured_requests[0].run_post_hooks is False
