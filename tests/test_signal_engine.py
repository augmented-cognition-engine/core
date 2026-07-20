"""Tests for Phase C internal signal engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_capability_decline_detected():
    """capability_decline signal emitted when cap score drops >= 0.1 over 7 days."""
    score_rows = [
        # Most recent first — score has dropped from 0.75 to 0.55 (delta = 0.20)
        {"capability": "capability:auth", "score": 0.55, "assessed_at": "2026-05-11T00:00:00Z"},
        {"capability": "capability:auth", "score": 0.65, "assessed_at": "2026-05-08T00:00:00Z"},
        {"capability": "capability:auth", "score": 0.75, "assessed_at": "2026-05-04T00:00:00Z"},
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[score_rows])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.foresight.signal_engine.pool", mock_pool):
        from core.engine.foresight.signal_engine import compute_capability_decline_signals

        signals = await compute_capability_decline_signals("product:test")

    assert len(signals) == 1
    s = signals[0]
    assert s.kind == "capability_decline"
    assert "auth" in s.subject
    assert s.confidence > 0.0


@pytest.mark.asyncio
async def test_no_decline_signal_when_score_stable():
    """No capability_decline signal when score delta is < 0.1."""
    score_rows = [
        {"capability": "capability:auth", "score": 0.72, "assessed_at": "2026-05-11T00:00:00Z"},
        {"capability": "capability:auth", "score": 0.71, "assessed_at": "2026-05-04T00:00:00Z"},
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[score_rows])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.foresight.signal_engine.pool", mock_pool):
        from core.engine.foresight.signal_engine import compute_capability_decline_signals

        signals = await compute_capability_decline_signals("product:test")

    assert signals == []


@pytest.mark.asyncio
async def test_gap_persistence_detected():
    """gap_persistence signal emitted when score < 0.4 and no decision in 14 days."""
    gap_rows = [
        {
            "capability": "capability:observability",
            "score": 0.28,
            "assessed_at": "2026-05-01T00:00:00Z",
        }
    ]
    decision_rows = []  # no decision addressing this gap

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "score < 0.4" in q:
            return [gap_rows]
        if "decision" in q.lower():
            return [decision_rows]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with patch("core.engine.foresight.signal_engine.pool", mock_pool):
        from core.engine.foresight.signal_engine import compute_gap_persistence_signals

        signals = await compute_gap_persistence_signals("product:test")

    assert len(signals) == 1
    assert signals[0].kind == "gap_persistence"
    assert "observability" in signals[0].subject


@pytest.mark.asyncio
async def test_run_signal_engine_writes_to_db():
    """run_signal_engine writes computed signals to the signal table."""
    from core.engine.foresight.models import Signal

    fake_signal = Signal(
        id="s1",
        kind="capability_decline",
        product_id="product:test",
        subject="capability:auth",
        description="capability:auth score declined 0.20 over 7 days",
        confidence=0.8,
        trend_data={"scores": [0.75, 0.65, 0.55], "days": 7},
        created_at="2026-05-11T00:00:00+00:00",
    )

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.query = AsyncMock(return_value=[[]])
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with (
        patch("core.engine.foresight.signal_engine.pool", mock_pool),
        patch(
            "core.engine.foresight.signal_engine.compute_capability_decline_signals",
            AsyncMock(return_value=[fake_signal]),
        ),
        patch(
            "core.engine.foresight.signal_engine.compute_gap_persistence_signals",
            AsyncMock(return_value=[]),
        ),
        patch(
            "core.engine.foresight.signal_engine.compute_decision_velocity_signals",
            AsyncMock(return_value=[]),
        ),
    ):
        from core.engine.foresight.signal_engine import run_signal_engine

        result = await run_signal_engine("product:test")

    assert result["signals_written"] >= 1


@pytest.mark.asyncio
async def test_run_signal_engine_registered_as_sentinel():
    """run_signal_engine is registered in the sentinel engine registry."""
    import core.engine.foresight.signal_engine  # noqa: F401 — triggers @register_engine
    from core.engine.sentinel.registry import get_engine

    entry = get_engine("signal_engine")
    assert entry is not None
    assert "daily" in entry["description"].lower() or "signal" in entry["description"].lower()
