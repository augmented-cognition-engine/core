# tests/test_foresight_forecaster.py
"""Tests for engine/foresight/forecaster.py — attach_prediction()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(query_side_effect):
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=query_side_effect)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_ctx
    return mock_pool


_VALID_LLM_PREDICTION = {
    "horizon_days": 14,
    "expected_changes": [{"capability_id": "capability:auth", "score_delta": 0.2, "confidence": 0.7}],
    "primary_risk": "OAuth callback remains untested after 14 days",
    "leading_indicators": ["test coverage for auth module increases"],
    "falsification_condition": "auth test coverage stays below 60% after 14 days",
}


@pytest.mark.asyncio
async def test_attach_prediction_writes_to_db():
    """attach_prediction should call db.query to CREATE decision_prediction."""
    from core.engine.foresight.forecaster import attach_prediction

    create_result = [{"id": "decision_prediction:pred1", "horizon_days": 14, "closed": False}]

    def query_side(q, params=None):
        if "FROM capability" in q:
            return [[{"slug": "auth", "description": "Auth module"}]]
        return [create_result]

    mock_pool = _make_pool(query_side)

    with patch("core.engine.foresight.forecaster.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=_VALID_LLM_PREDICTION)
        with patch("core.engine.foresight.forecaster.create_edge", AsyncMock()):
            result = await attach_prediction(
                decision_id="decision:d1",
                decision_content="We will add OAuth callback tests",
                product_id="product:platform",
                archetype="executor",
                discipline="testing",
                pool=mock_pool,
            )

    assert result is not None
    assert result.get("horizon_days") == 14


@pytest.mark.asyncio
async def test_attach_prediction_returns_none_on_llm_failure():
    """attach_prediction must never raise — returns None on LLM error."""
    from core.engine.foresight.forecaster import attach_prediction

    mock_pool = _make_pool(lambda q, params=None: [[]])

    with patch("core.engine.foresight.forecaster.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM timeout"))
        result = await attach_prediction(
            decision_id="decision:d1",
            decision_content="some decision",
            product_id="product:platform",
            pool=mock_pool,
        )

    assert result is None


@pytest.mark.asyncio
async def test_attach_prediction_returns_none_on_incomplete_schema():
    """If LLM omits required fields, attach_prediction returns None (no write)."""
    from core.engine.foresight.forecaster import attach_prediction

    incomplete = {"horizon_days": 7}  # missing expected_changes, primary_risk, etc.
    mock_pool = _make_pool(lambda q, params=None: [[]])

    with patch("core.engine.foresight.forecaster.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=incomplete)
        result = await attach_prediction(
            decision_id="decision:d1",
            decision_content="some decision",
            product_id="product:platform",
            pool=mock_pool,
        )

    assert result is None


@pytest.mark.asyncio
async def test_snapshot_baselines_writes_one_row_per_quality_row():
    """_snapshot_capability_baselines should CREATE one snapshot per quality row found."""
    from core.engine.foresight.forecaster import _snapshot_capability_baselines

    create_calls: list[tuple[str, dict]] = []

    def query_side(q, params=None):
        # The helper first SELECTs from capability_quality, then CREATEs snapshots.
        if "SELECT" in q and "capability_quality" in q:
            return [
                [
                    {"capability": "capability:auth", "dimension": "security", "score": 0.4, "confidence": 0.6},
                    {"capability": "capability:auth", "dimension": "testing", "score": 0.3, "confidence": 0.5},
                ]
            ]
        if "CREATE capability_quality_snapshot" in q:
            create_calls.append((q, params))
            return [[{"id": "capability_quality_snapshot:fake"}]]
        return [[]]

    mock_pool = _make_pool(query_side)

    await _snapshot_capability_baselines(
        prediction_id="decision_prediction:p1",
        expected_changes=[{"capability_id": "auth", "score_delta": 0.2, "confidence": 0.7}],
        product_id="product:platform",
        pool=mock_pool,
    )

    # Sentinel: "auto-snapshot at prediction-create" — one snapshot per quality row.
    assert len(create_calls) == 2
    dims = sorted(c[1]["dimension"] for c in create_calls)
    assert dims == ["security", "testing"]


@pytest.mark.asyncio
async def test_snapshot_baselines_logs_and_skips_when_no_quality_data(caplog):
    """When capability has no quality rows yet, helper logs WARNING and skips writes."""
    import logging

    from core.engine.foresight.forecaster import _snapshot_capability_baselines

    create_calls: list = []

    def query_side(q, params=None):
        if "SELECT" in q and "capability_quality" in q:
            return [[]]  # empty quality data
        if "CREATE" in q:
            create_calls.append(q)
        return [[]]

    mock_pool = _make_pool(query_side)

    with caplog.at_level(logging.WARNING, logger="core.engine.foresight.forecaster"):
        await _snapshot_capability_baselines(
            prediction_id="decision_prediction:p1",
            expected_changes=[{"capability_id": "brand-new-cap", "score_delta": 0.1}],
            product_id="product:platform",
            pool=mock_pool,
        )

    assert create_calls == []
    assert any("Snapshot baseline skipped" in r.message for r in caplog.records)
    assert any("brand-new-cap" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_snapshot_baselines_never_raises():
    """Helper must absorb DB errors — prediction itself already succeeded."""
    from core.engine.foresight.forecaster import _snapshot_capability_baselines

    def query_side(q, params=None):
        raise RuntimeError("DB unreachable")

    mock_pool = _make_pool(query_side)

    # Must not propagate.
    await _snapshot_capability_baselines(
        prediction_id="decision_prediction:p1",
        expected_changes=[{"capability_id": "auth"}],
        product_id="product:platform",
        pool=mock_pool,
    )


@pytest.mark.asyncio
async def test_snapshot_baselines_dedupes_capability_slugs():
    """If expected_changes lists the same capability twice, only snapshot it once."""
    from core.engine.foresight.forecaster import _snapshot_capability_baselines

    select_calls: list = []

    def query_side(q, params=None):
        if "SELECT" in q and "capability_quality" in q:
            select_calls.append(params.get("cap_slug") if params else None)
            return [[]]
        return [[]]

    mock_pool = _make_pool(query_side)

    await _snapshot_capability_baselines(
        prediction_id="decision_prediction:p1",
        expected_changes=[
            {"capability_id": "auth", "score_delta": 0.2},
            {"capability_id": "auth", "score_delta": 0.1},  # duplicate
            {"capability_id": "api", "score_delta": 0.3},
        ],
        product_id="product:platform",
        pool=mock_pool,
    )

    # auth queried once (not twice) + api once = 2 lookups
    assert select_calls.count("auth") == 1
    assert select_calls.count("api") == 1


@pytest.mark.asyncio
async def test_attach_prediction_creates_predicts_edge():
    """attach_prediction creates a predicts edge from prediction to decision."""
    from core.engine.foresight.forecaster import attach_prediction

    create_result = [{"id": "decision_prediction:pred1", "closed": False}]

    def query_side(q, params=None):
        if "FROM capability" in q:
            return [[]]
        return [create_result]

    mock_pool = _make_pool(query_side)
    edge_mock = AsyncMock()

    with patch("core.engine.foresight.forecaster.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=_VALID_LLM_PREDICTION)
        with patch("core.engine.foresight.forecaster.create_edge", edge_mock):
            await attach_prediction(
                decision_id="decision:d1",
                decision_content="some decision",
                product_id="product:platform",
                pool=mock_pool,
            )

    edge_mock.assert_called_once()
    args = edge_mock.call_args[0]
    assert args[0] == "predicts"
    assert "decision_prediction" in args[1]
    assert args[2] == "decision:d1"
