"""Tests for Phase C foresight signal integration in ProactiveLine."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_high_confidence_signal_appears_in_aggregate():
    """Signals with confidence >= 0.7 are included in aggregate() output."""
    signal_rows = [
        {
            "id": "signal:s1",
            "kind": "capability_decline",
            "description": "capability:auth score declined 0.20 over 7 days",
            "confidence": 0.85,
            "subject": "capability:auth",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "signal" in q and "confidence" in q:
            return [signal_rows]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    async def fake_transform(**kwargs):
        return "Our auth capability is declining — we should prioritize stabilizing it before expanding."

    with (
        patch("core.engine.proactive.aggregator.pool", mock_pool),
        patch("core.engine.proactive.voice.transform", side_effect=fake_transform),
    ):
        from core.engine.proactive.aggregator import aggregate

        lines = await aggregate("product:test", mock_conn)

    from core.engine.proactive.models import ProactiveSource

    sources = [line.source for line in lines]
    assert ProactiveSource.FORESIGHT_SIGNAL in sources


@pytest.mark.asyncio
async def test_low_confidence_signal_excluded():
    """Signals with confidence < 0.7 are not surfaced on the Proactive Line."""
    signal_rows = [
        {
            "id": "signal:s2",
            "kind": "decision_velocity_drop",
            "description": "Decision cadence dropped 30%",
            "confidence": 0.35,
            "subject": "decisions",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    async def fake_query(q, params=None):
        if "signal" in q and "confidence" in q:
            return [signal_rows]
        return [[]]

    mock_conn.query = AsyncMock(side_effect=fake_query)
    mock_pool = MagicMock()
    mock_pool.connection.return_value = mock_conn

    with (
        patch("core.engine.proactive.aggregator.pool", mock_pool),
        patch("core.engine.proactive.voice.transform", AsyncMock(return_value="some line")),
    ):
        from core.engine.proactive.aggregator import aggregate

        lines = await aggregate("product:test", mock_conn)

    from core.engine.proactive.models import ProactiveSource

    signal_lines = [line for line in lines if line.source == ProactiveSource.FORESIGHT_SIGNAL]
    assert signal_lines == []


@pytest.mark.asyncio
async def test_foresight_signal_rank_below_sentinel_above_recommended():
    """FORESIGHT_SIGNAL tier ranks below SENTINEL_FINDING but above RECOMMENDED_ACTION."""
    from core.engine.proactive.models import ProactiveLine, ProactiveSource

    now = datetime.now(timezone.utc)
    sentinel_line = ProactiveLine(
        product_id="p",
        line="s",
        source=ProactiveSource.SENTINEL_FINDING,
        source_artifact_id="f1",
        drill_down_url="/x",
        severity=0.5,
        generated_at=now,
    )
    signal_line = ProactiveLine(
        product_id="p",
        line="f",
        source=ProactiveSource.FORESIGHT_SIGNAL,
        source_artifact_id="s1",
        drill_down_url="/x",
        severity=0.5,
        generated_at=now,
    )
    recommended_line = ProactiveLine(
        product_id="p",
        line="r",
        source=ProactiveSource.RECOMMENDED_ACTION,
        source_artifact_id="r1",
        drill_down_url="/x",
        severity=0.5,
        generated_at=now,
    )

    ranked = sorted([recommended_line, signal_line, sentinel_line], key=lambda x: x.rank_key())
    assert ranked[0].source == ProactiveSource.SENTINEL_FINDING
    assert ranked[1].source == ProactiveSource.FORESIGHT_SIGNAL
    assert ranked[2].source == ProactiveSource.RECOMMENDED_ACTION
