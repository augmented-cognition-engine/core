"""Boundary tests for BriefingDiff — AC 3, 4, 5."""

from __future__ import annotations

from datetime import datetime, timezone

from core.engine.product.briefing_diff import (
    BriefingDiff,
    diff_briefings,
)


def _briefing(bid: str, created_at: str, highlights=None, risks=None, score_deltas=None) -> dict:
    return {
        "id": bid,
        "created_at": datetime.fromisoformat(created_at),
        "content": {
            "narrative": "ACE Intelligence Briefing",
            "highlights": highlights or [],
            "recommendations": [],
            "risks": risks or [],
            "score_deltas": score_deltas or {},
        },
    }


# ---------------------------------------------------------------------------
# AC 3 — diff shape: added, removed, changed, score_deltas
# ---------------------------------------------------------------------------


def test_briefing_diff_added_items():
    """New sentinel finding in newer briefing appears in diff.added."""
    older = _briefing(
        "briefing:1",
        "2026-01-01T06:00:00+00:00",
        highlights=[{"item_key": "gaps_filled", "content": "3 gaps filled"}],
    )
    newer = _briefing(
        "briefing:2",
        "2026-01-08T06:00:00+00:00",
        highlights=[
            {"item_key": "gaps_filled", "content": "3 gaps filled"},
            {"item_key": "competitive_insights", "content": "5 competitive insights written"},
        ],
    )

    result = diff_briefings(older, newer)

    assert isinstance(result, BriefingDiff)
    added_keys = {i.item_key for i in result.added}
    assert "competitive_insights" in added_keys


def test_briefing_diff_removed_items():
    """Finding resolved in newer briefing (no longer present) appears in diff.removed."""
    older = _briefing(
        "briefing:1",
        "2026-01-01T06:00:00+00:00",
        risks=[{"item_key": "conflicts_found", "content": "4 unresolved conflicts"}],
    )
    newer = _briefing(
        "briefing:2",
        "2026-01-08T06:00:00+00:00",
        risks=[],  # conflicts resolved
    )

    result = diff_briefings(older, newer)

    removed_keys = {i.item_key for i in result.removed}
    assert "conflicts_found" in removed_keys


def test_briefing_diff_changed_items():
    """Reframed recommendation in newer briefing appears in diff.changed with delta_kind."""
    older = _briefing(
        "briefing:1",
        "2026-01-01T06:00:00+00:00",
        highlights=[{"item_key": "gaps_filled", "content": "2 gaps filled"}],
    )
    newer = _briefing(
        "briefing:2",
        "2026-01-08T06:00:00+00:00",
        highlights=[{"item_key": "gaps_filled", "content": "7 gaps filled"}],
    )

    result = diff_briefings(older, newer)

    changed_keys = {c.item_key for c in result.changed}
    assert "gaps_filled" in changed_keys
    change = next(c for c in result.changed if c.item_key == "gaps_filled")
    assert change.delta_kind in ("escalated", "minor_edit", "reframed", "resolved")


def test_briefing_diff_score_deltas():
    """Score deltas reflect discipline score changes between briefings."""
    older = _briefing(
        "briefing:1",
        "2026-01-01T06:00:00+00:00",
        score_deltas={"security": 0.40, "scalability": 0.70},
    )
    newer = _briefing(
        "briefing:2",
        "2026-01-08T06:00:00+00:00",
        score_deltas={"security": 0.75, "scalability": 0.65},
    )

    result = diff_briefings(older, newer)

    assert "security" in result.score_deltas
    assert "scalability" in result.score_deltas
    assert abs(result.score_deltas["security"] - 0.35) < 0.001
    assert abs(result.score_deltas["scalability"] - (-0.05)) < 0.001


def test_briefing_diff_identical_briefings_has_no_changes():
    """Two identical briefings produce an empty diff."""
    b = _briefing(
        "briefing:1",
        "2026-01-01T06:00:00+00:00",
        highlights=[{"item_key": "gaps_filled", "content": "3 gaps filled"}],
    )
    result = diff_briefings(b, b)

    assert result.added == []
    assert result.removed == []
    assert result.changed == []


def test_briefing_diff_legacy_string_content():
    """Legacy briefings with string content are handled as a single narrative item."""
    older = {
        "id": "briefing:1",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "content": "Old narrative text here.",
    }
    newer = {
        "id": "briefing:2",
        "created_at": datetime(2026, 1, 8, tzinfo=timezone.utc),
        "content": "New narrative text here.",
    }

    result = diff_briefings(older, newer)

    # Both have a "narrative" item_key; content changed → shows up in changed
    assert any(c.item_key == "narrative" for c in result.changed)


def test_diff_auto_orders_by_created_at():
    """diff_briefings returns consistent older_id/newer_id regardless of argument order."""
    a = _briefing("briefing:1", "2026-01-01T06:00:00+00:00")
    b = _briefing("briefing:2", "2026-01-08T06:00:00+00:00")

    result_forward = diff_briefings(a, b)
    result_backward = diff_briefings(b, a)

    # Both should identify briefing:1 as older and briefing:2 as newer
    assert result_forward.older_id == "briefing:1"
    assert result_forward.newer_id == "briefing:2"
    # Reversed args still produce the same canonical ordering
    assert result_backward.older_id == "briefing:1"
    assert result_backward.newer_id == "briefing:2"
