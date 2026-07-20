"""Tests for engine/learning/detector.py

Uses db_pool fixture. Each test ensures product:platform exists (seeded by conftest)
and the closed_loop_learning_enabled flag is ON for the test, then reverts it.
"""

import asyncio

import pytest


@pytest.fixture
async def learning_on(db_pool):
    """Turn on closed_loop_learning_enabled for product:platform, yield, turn it off."""
    from core.engine.learning.feature_flag import set_closed_loop_learning_enabled

    pid = "product:platform"
    # Ensure product:platform exists
    async with db_pool.connection() as db:
        await db.query("UPSERT product:platform SET name = 'Platform', tenant = tenant:test, settings = {}")
    await set_closed_loop_learning_enabled(db_pool, pid, True)
    yield pid
    await set_closed_loop_learning_enabled(db_pool, pid, False)
    # Clean up any observations created during this test
    async with db_pool.connection() as db:
        await db.query(
            "DELETE outcome_observation WHERE product = <record>$pid",
            {"pid": pid},
        )


@pytest.mark.asyncio
async def test_open_observation_recommendation(db_pool, learning_on):
    """canvas.recommendation.shifted opens an outcome_observation in open state."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    payload = {
        "product_id": "product:platform",
        "top_pillar": "experience",
        "top_discipline": "ux",
        "discipline": "ux",
    }
    await _on_canvas_event("canvas.recommendation.shifted", payload)

    # Give async DB write time to settle
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = 'recommendation'
                     AND outcome_label = 'open'""",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) >= 1
    row = rows[0]
    assert row["emission_kind"] == "recommendation"
    assert row["outcome_label"] == "open"
    assert row["pillar"] == "experience"


@pytest.mark.asyncio
async def test_open_observation_idempotent(db_pool, learning_on):
    """Calling _on_canvas_event twice for same emission does not create duplicate rows."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    payload = {
        "product_id": "product:platform",
        "top_pillar": "reliability",
        "top_discipline": "observability",
        "discipline": "observability",
    }
    await _on_canvas_event("canvas.recommendation.shifted", payload)
    await _on_canvas_event("canvas.recommendation.shifted", payload)
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = 'recommendation'
                     AND pillar = 'reliability'""",
                {"pid": "product:platform"},
            )
        )
    # Should be exactly 1 (idempotent)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_open_observation_uncertainty(db_pool, learning_on):
    """canvas.uncertainty.opened opens an uncertainty observation."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    payload = {
        "product_id": "product:platform",
        "query_id": "q:test-uncertainty-001",
        "pillar": "security",
        "discipline": "security",
    }
    await _on_canvas_event("canvas.uncertainty.opened", payload)
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = 'uncertainty'
                     AND emission_id = 'q:test-uncertainty-001'""",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) == 1
    assert rows[0]["outcome_label"] == "open"


@pytest.mark.asyncio
async def test_match_uncertainty_answered(db_pool, learning_on):
    """canvas.uncertainty.answered transitions the matching observation to 'answered'."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    qid = "q:test-answer-match-001"
    # Open the observation
    await _on_canvas_event(
        "canvas.uncertainty.opened",
        {"product_id": "product:platform", "query_id": qid, "pillar": "architecture", "discipline": "architecture"},
    )
    await asyncio.sleep(0.1)

    # Now fire the matching action
    await _on_canvas_event(
        "canvas.uncertainty.answered",
        {"product_id": "product:platform", "query_id": qid},
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT outcome_label FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = 'uncertainty'
                     AND emission_id = $qid""",
                {"pid": "product:platform", "qid": qid},
            )
        )
    assert len(rows) == 1
    assert rows[0]["outcome_label"] == "answered"


@pytest.mark.asyncio
async def test_match_recommendation_acted_on(db_pool, learning_on):
    """canvas.code.edited with matching discipline transitions recommendation to 'acted_on'."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    # Open recommendation observation with discipline=ux
    await _on_canvas_event(
        "canvas.recommendation.shifted",
        {
            "product_id": "product:platform",
            "top_pillar": "experience",
            "top_discipline": "ux",
            "discipline": "ux",
        },
    )
    await asyncio.sleep(0.1)

    # Action: code edited with matching discipline
    await _on_canvas_event(
        "canvas.code.edited",
        {"product_id": "product:platform", "discipline": "ux", "path": "portal/src/App.tsx"},
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT outcome_label FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = 'recommendation'
                     AND pillar = 'experience'""",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) >= 1
    assert rows[0]["outcome_label"] == "acted_on"


@pytest.mark.asyncio
async def test_match_recommendation_wrong_discipline_no_match(db_pool, learning_on):
    """canvas.code.edited with non-matching discipline does NOT transition observation."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    # Open recommendation observation with discipline=security
    await _on_canvas_event(
        "canvas.recommendation.shifted",
        {
            "product_id": "product:platform",
            "top_pillar": "reliability",
            "top_discipline": "security",
            "discipline": "security",
        },
    )
    await asyncio.sleep(0.1)

    # Action: code edited with DIFFERENT discipline (ux)
    await _on_canvas_event(
        "canvas.code.edited",
        {"product_id": "product:platform", "discipline": "ux", "path": "portal/src/App.tsx"},
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT outcome_label FROM outcome_observation
                   WHERE product = <record>$pid
                     AND emission_kind = 'recommendation'
                     AND pillar = 'reliability'""",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) >= 1
    # Should still be 'open' — wrong discipline
    assert rows[0]["outcome_label"] == "open"


@pytest.mark.asyncio
async def test_feature_flag_gates_detection(db_pool):
    """When flag is off, no observations are created."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event
    from core.engine.learning.feature_flag import is_closed_loop_learning_enabled

    pid = "product:platform"
    # Ensure flag is off (conftest leaves it off by default)
    assert not await is_closed_loop_learning_enabled(db_pool, pid)

    await _on_canvas_event(
        "canvas.recommendation.shifted",
        {
            "product_id": pid,
            "top_pillar": "flagtest",
            "top_discipline": "flagtest",
            "discipline": "flagtest",
        },
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM outcome_observation
                   WHERE product = <record>$pid AND pillar = 'flagtest'""",
                {"pid": pid},
            )
        )
    assert rows == [], "No observations when flag is off"


@pytest.mark.asyncio
async def test_open_drift_observation(db_pool, learning_on):
    """canvas.drift.crossed (up direction) opens a drift observation."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    await _on_canvas_event(
        "canvas.drift.crossed",
        {
            "product_id": "product:platform",
            "new_blocked_frac": 0.7,
            "prev_blocked_frac": 0.2,
        },
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT emission_kind, outcome_label FROM outcome_observation
                   WHERE product = <record>$pid AND emission_kind = 'drift'""",
                {"pid": "product:platform"},
            )
        )
    assert any(r["outcome_label"] == "open" for r in rows)


@pytest.mark.asyncio
async def test_open_intelligence_classified_observation(db_pool, learning_on):
    """canvas.intelligence.classified opens an intelligence_classified observation."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    await _on_canvas_event(
        "canvas.intelligence.classified",
        {
            "product_id": "product:platform",
            "observation_id": "obs:intel-test-001",
            "discipline": "api_design",
            "pillar": "reliability",
        },
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT emission_kind, emission_id, outcome_label FROM outcome_observation
                   WHERE product = <record>$pid AND emission_kind = 'intelligence_classified'""",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) >= 1
    assert rows[0]["emission_id"] == "obs:intel-test-001"


@pytest.mark.asyncio
async def test_open_pattern_matched_observation(db_pool, learning_on):
    """canvas.pattern.matched opens a pattern_matched observation."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.detector import _on_canvas_event

    await _on_canvas_event(
        "canvas.pattern.matched",
        {
            "product_id": "product:platform",
            "pattern_slug": "missing-input-validation",
        },
    )
    await asyncio.sleep(0.1)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT emission_kind, outcome_label FROM outcome_observation
                   WHERE product = <record>$pid AND emission_kind = 'pattern_matched'""",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) >= 1
    assert rows[0]["outcome_label"] == "open"


def test_register_outcome_detector_subscribes():
    """register_outcome_detector registers _on_canvas_event as a wildcard handler."""
    from core.engine.events.bus import EventBus
    from core.engine.learning.detector import register_outcome_detector

    fresh_bus_handlers: dict = {}
    import core.engine.learning.detector as det_mod

    orig_bus = det_mod.bus

    # Use a fresh EventBus to test registration without polluting the singleton
    test_bus = EventBus()
    det_mod.bus = test_bus
    try:
        register_outcome_detector()
        handlers = test_bus.list_handlers()
        assert "*" in handlers
        assert "_on_canvas_event" in handlers["*"]
    finally:
        det_mod.bus = orig_bus
