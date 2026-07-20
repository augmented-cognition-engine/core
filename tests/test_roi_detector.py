# tests/test_roi_detector.py
"""Tests for ROI detection — post-task hook identifying intelligence value."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_mistake_prevented_from_correction():
    """Correction-type reflected insight produces mistake_prevented event."""
    from core.engine.intelligence.roi_detector import detect_roi_events

    db = AsyncMock()
    db.query = AsyncMock(return_value=[[{"id": "roi_event:1"}]])

    task = {
        "id": "task:t1",
        "domain_path": "architecture",
        "intelligence_loaded": {
            "insights": [
                {
                    "id": "insight:c1",
                    "content": "Never use eval() in prod",
                    "insight_type": "correction",
                    "confidence": 0.9,
                },
            ],
            "cross_domain": [],
        },
    }
    utilization = {"reflected_ids": ["insight:c1"], "loaded_count": 1, "reflected_count": 1}

    events = await detect_roi_events(task, utilization, "product:test", db)
    assert len(events) == 1
    # Verify CREATE was called with mistake_prevented
    call_args = db.query.call_args_list
    create_calls = [c for c in call_args if "CREATE roi_event" in str(c)]
    assert len(create_calls) == 1
    assert create_calls[0][0][1]["event_type"] == "mistake_prevented"


@pytest.mark.asyncio
async def test_gap_filled_from_gap_researcher():
    """Gap-researcher sourced insight produces gap_filled event."""
    from core.engine.intelligence.roi_detector import detect_roi_events

    db = AsyncMock()
    db.query = AsyncMock(return_value=[[{"id": "roi_event:2"}]])

    task = {
        "id": "task:t2",
        "domain_path": "architecture",
        "intelligence_loaded": {
            "insights": [
                {
                    "id": "insight:g1",
                    "content": "Redis TTL default is 300s",
                    "insight_type": "fact",
                    "source_domain": "sentinel.gap_researcher",
                    "confidence": 0.8,
                },
            ],
            "cross_domain": [],
        },
    }
    utilization = {"reflected_ids": ["insight:g1"], "loaded_count": 1, "reflected_count": 1}

    events = await detect_roi_events(task, utilization, "product:test", db)
    assert len(events) == 1
    create_calls = [c for c in db.query.call_args_list if "CREATE roi_event" in str(c)]
    assert create_calls[0][0][1]["event_type"] == "gap_filled"


@pytest.mark.asyncio
async def test_connection_surfaced_from_cross_domain():
    """Cross-domain reflected insights produce connection_surfaced event."""
    from core.engine.intelligence.roi_detector import detect_roi_events

    db = AsyncMock()
    db.query = AsyncMock(return_value=[[{"id": "roi_event:3"}]])

    task = {
        "id": "task:t3",
        "domain_path": "architecture",
        "intelligence_loaded": {
            "insights": [],
            "cross_domain": [
                {
                    "insight_id": "insight:cd1",
                    "content": "Legal requires GDPR notice",
                    "source_subdomain": "security",
                },
            ],
        },
    }
    utilization = {"reflected_ids": ["insight:cd1"], "loaded_count": 1, "reflected_count": 1}

    events = await detect_roi_events(task, utilization, "product:test", db)
    assert len(events) == 1
    create_calls = [c for c in db.query.call_args_list if "CREATE roi_event" in str(c)]
    assert create_calls[0][0][1]["event_type"] == "connection_surfaced"
    assert create_calls[0][0][1]["time_saved"] == 120


@pytest.mark.asyncio
async def test_no_events_when_nothing_reflected():
    """No ROI events when no insights were reflected."""
    from core.engine.intelligence.roi_detector import detect_roi_events

    db = AsyncMock()

    task = {
        "id": "task:t4",
        "domain_path": "architecture",
        "intelligence_loaded": {"insights": [{"id": "insight:x", "content": "test"}], "cross_domain": []},
    }
    utilization = {"reflected_ids": [], "loaded_count": 1, "reflected_count": 0}

    events = await detect_roi_events(task, utilization, "product:test", db)
    assert events == []
    db.query.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_events_from_mixed_insights():
    """Task using both a correction and cross-domain insight produces two events."""
    from core.engine.intelligence.roi_detector import detect_roi_events

    db = AsyncMock()
    db.query = AsyncMock(return_value=[[{"id": "roi_event:m1"}]])

    task = {
        "id": "task:t5",
        "domain_path": "architecture",
        "intelligence_loaded": {
            "insights": [
                {"id": "insight:corr", "content": "Don't use MD5", "insight_type": "correction", "confidence": 0.9},
            ],
            "cross_domain": [
                {"insight_id": "insight:cd2", "content": "Security requires SHA256", "source_subdomain": "security"},
            ],
        },
    }
    utilization = {"reflected_ids": ["insight:corr", "insight:cd2"], "loaded_count": 2, "reflected_count": 2}

    events = await detect_roi_events(task, utilization, "product:test", db)
    assert len(events) == 2
    event_types = {
        e.get("event_type") or db.query.call_args_list[i][0][1].get("event_type", "") for i, e in enumerate(events)
    }
    # We have at least mistake_prevented and connection_surfaced
    create_calls = [c for c in db.query.call_args_list if "CREATE roi_event" in str(c)]
    types_created = {c[0][1]["event_type"] for c in create_calls}
    assert "mistake_prevented" in types_created
    assert "connection_surfaced" in types_created
