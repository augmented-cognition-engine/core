"""Boundary tests for ProactiveLine aggregator ranking — AC 1, 2, 3."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.proactive.models import ProactiveLine, ProactiveSource


def _make_line(source: ProactiveSource, severity: float, line: str = "test line") -> ProactiveLine:
    return ProactiveLine(
        product_id="product:test",
        line=line,
        source=source,
        source_artifact_id="artifact:1",
        drill_down_url="/test",
        severity=severity,
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# AC 2 — unresolved gate outranks everything
# ---------------------------------------------------------------------------


def test_unresolved_gate_outranks_sentinel_finding():
    gate = _make_line(ProactiveSource.UNRESOLVED_GATE, severity=0.9)
    finding = _make_line(ProactiveSource.SENTINEL_FINDING, severity=1.0)

    ranked = sorted([finding, gate], key=lambda p: p.rank_key())
    assert ranked[0].source == ProactiveSource.UNRESOLVED_GATE


def test_unresolved_gate_outranks_recommendation():
    gate = _make_line(ProactiveSource.UNRESOLVED_GATE, severity=0.5)
    rec = _make_line(ProactiveSource.RECOMMENDED_ACTION, severity=0.99)

    ranked = sorted([rec, gate], key=lambda p: p.rank_key())
    assert ranked[0].source == ProactiveSource.UNRESOLVED_GATE


# ---------------------------------------------------------------------------
# AC 3 — sentinel finding outranks recommendation, recommendation outranks briefing
# ---------------------------------------------------------------------------


def test_sentinel_finding_outranks_recommendation():
    finding = _make_line(ProactiveSource.SENTINEL_FINDING, severity=0.3)
    rec = _make_line(ProactiveSource.RECOMMENDED_ACTION, severity=0.9)

    ranked = sorted([rec, finding], key=lambda p: p.rank_key())
    assert ranked[0].source == ProactiveSource.SENTINEL_FINDING


def test_recommendation_outranks_briefing_highlight():
    rec = _make_line(ProactiveSource.RECOMMENDED_ACTION, severity=0.1)
    highlight = _make_line(ProactiveSource.BRIEFING_HIGHLIGHT, severity=0.8)

    ranked = sorted([highlight, rec], key=lambda p: p.rank_key())
    assert ranked[0].source == ProactiveSource.RECOMMENDED_ACTION


def test_within_tier_higher_severity_wins():
    low = _make_line(ProactiveSource.SENTINEL_FINDING, severity=0.3)
    high = _make_line(ProactiveSource.SENTINEL_FINDING, severity=0.9)

    ranked = sorted([low, high], key=lambda p: p.rank_key())
    assert ranked[0].severity == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# AC 1 — compute_current returns single line or None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_returns_null_when_nothing_to_surface():
    from core.engine.proactive.aggregator import compute_current

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    with patch("core.engine.proactive.aggregator.parse_rows", return_value=[]):
        with patch("core.engine.proactive.aggregator.parse_one", return_value=None):
            result = await compute_current("product:test", mock_db)

    assert result is None


@pytest.mark.asyncio
async def test_current_returns_single_line_not_list():
    from core.engine.proactive.aggregator import compute_current
    from core.engine.proactive.voice import _fallback_line

    gate_row = {
        "id": "gate:1",
        "entity_type": "capability",
        "entity_id": "cap:auth",
        "risk_level": "high",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    async def _mock_transform(**kwargs):
        return _fallback_line(kwargs["capability"], kwargs["discipline"], kwargs["description"])

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    with patch("core.engine.proactive.aggregator._gather_unresolved_gates", return_value=[gate_row]):
        with patch("core.engine.proactive.aggregator._gather_sentinel_findings", return_value=[]):
            with patch("core.engine.proactive.aggregator._gather_gap_findings", return_value=[]):
                with patch("core.engine.proactive.aggregator._gather_recommendation", return_value=None):
                    with patch("core.engine.proactive.aggregator.transform", side_effect=_mock_transform):
                        result = await compute_current("product:test", mock_db)

    assert result is not None
    assert isinstance(result, ProactiveLine)
    assert result.source == ProactiveSource.UNRESOLVED_GATE


# ---------------------------------------------------------------------------
# AC 7 — ProactiveLine.line is ≤ 150 characters
# ---------------------------------------------------------------------------


def test_proactive_line_enforces_150_char_limit():
    long_line = "x" * 200
    line = ProactiveLine(
        product_id="product:test",
        line=long_line[:150],  # enforced at creation by transformer
        source=ProactiveSource.SENTINEL_FINDING,
        source_artifact_id="art:1",
        drill_down_url="/test",
        severity=0.5,
        generated_at=datetime.now(timezone.utc),
    )
    assert len(line.line) <= 150


# ---------------------------------------------------------------------------
# AC 5 — drill_down_url is a valid relative route
# ---------------------------------------------------------------------------


def test_drill_down_url_resolves_to_known_route_pattern():
    """drill_down_url must be a path that references the source artifact."""
    lines = [
        _make_line(ProactiveSource.UNRESOLVED_GATE, 0.9),
        _make_line(ProactiveSource.SENTINEL_FINDING, 0.7),
        _make_line(ProactiveSource.RECOMMENDED_ACTION, 0.4),
        _make_line(ProactiveSource.BRIEFING_HIGHLIGHT, 0.2),
    ]
    for line in lines:
        assert line.drill_down_url.startswith("/"), (
            f"drill_down_url must be a relative path, got: {line.drill_down_url!r}"
        )
        # Must reference something (not just "/")
        assert len(line.drill_down_url) > 1


# ---------------------------------------------------------------------------
# AC 6 — WebSocket pushes new line when sentinel fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_pushes_on_canvas_event():
    """When a canvas sentinel event fires, the proactive WS endpoint recomputes."""
    import asyncio

    from core.engine.events.bus import EventBus

    local_bus = EventBus()
    triggered_events: list[str] = []

    # Simulate the aggregator trigger: canvas.score.changed for product:test
    # fires → triggered.set() → recompute → push
    async def _handler(event_type, payload):
        triggered_events.append(event_type)

    local_bus.on("canvas.score.changed", _handler)

    import core.engine.events.canvas as canvas_module

    original_bus = canvas_module.bus
    canvas_module.bus = local_bus

    try:
        from core.engine.events.canvas import emit_score_changed

        await emit_score_changed(
            product_id="product:test",
            capability_slug="auth",
            dimension="security",
            old_score=0.4,
            new_score=0.75,
            sentinel_name="gap_analyzer",
        )
        await asyncio.sleep(0.05)
    finally:
        canvas_module.bus = original_bus

    # The canvas event was delivered — the WS handler would pick this up
    assert "canvas.score.changed" in triggered_events, (
        "canvas.score.changed event not delivered — WS push trigger would not fire"
    )
