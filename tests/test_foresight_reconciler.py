# tests/test_foresight_reconciler.py
"""Tests for engine/foresight/reconciler.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(query_map: dict):
    """Build a mock pool whose db.query returns based on keywords in the query string."""
    mock_db = AsyncMock()

    async def _query(q, params=None):
        for keyword, result in query_map.items():
            if keyword in q:
                return result
        return [[]]

    mock_db.query = AsyncMock(side_effect=_query)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = mock_ctx
    return pool


def test_reconciler_registers():
    """reconciler should be present in engine_registry after import."""
    import core.engine.foresight.reconciler  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "prediction_reconciler" in engine_registry
    entry = engine_registry["prediction_reconciler"]
    # Cron changed nightly→hourly per decision:uigaj1ywvn5yhaiznihu
    # to reduce max calibration lag from 24h to 1h.
    assert entry["cron"] == "0 * * * *"
    assert callable(entry["fn"])


def test_event_handler_registration_is_idempotent():
    """Calling _register_event_handlers() multiple times must not double-register.

    The _handler_registered guard prevents N-fold reconciler runs per single
    quality.score_changed event (which would cause N-fold EMA application on
    calibration).
    """
    import core.engine.foresight.reconciler as recon
    from core.engine.events.bus import bus

    # Calling explicitly multiple times must remain idempotent.
    recon._register_event_handlers()
    recon._register_event_handlers()
    recon._register_event_handlers()

    handlers = bus.list_handlers().get("quality.score_changed", [])
    assert handlers.count("_on_quality_score_changed") == 1


def test_reconciler_subscribes_to_quality_score_changed():
    """Reconciler should register a handler on the event bus for quality.score_changed.

    Closes deferred half of decision:uigaj1ywvn5yhaiznihu — flush-triggered reconciler.
    """
    import core.engine.foresight.reconciler  # noqa: F401
    from core.engine.events.bus import bus

    handlers = bus.list_handlers()
    assert "quality.score_changed" in handlers
    assert "_on_quality_score_changed" in handlers["quality.score_changed"]


@pytest.mark.asyncio
async def test_flush_handler_invokes_run_reconciler_with_product_id():
    """quality.score_changed payload's product_id flows to run_reconciler."""
    from core.engine.foresight.reconciler import _on_quality_score_changed

    with patch(
        "core.engine.foresight.reconciler.run_reconciler",
        AsyncMock(return_value={"predictions_closed": 0, "errors": 0}),
    ) as mock_run:
        await _on_quality_score_changed(
            "quality.score_changed",
            {"product_id": "product:platform", "capability_id": "cap:auth"},
        )

    mock_run.assert_awaited_once_with("product:platform")


@pytest.mark.asyncio
async def test_flush_handler_noop_when_product_id_missing():
    """Handler must not call run_reconciler if payload lacks product_id."""
    from core.engine.foresight.reconciler import _on_quality_score_changed

    with patch("core.engine.foresight.reconciler.run_reconciler", AsyncMock()) as mock_run:
        await _on_quality_score_changed("quality.score_changed", {"capability_id": "cap:auth"})

    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_flush_handler_never_raises_on_reconciler_failure():
    """Handler must absorb exceptions — reconciler failures are non-fatal at the bus."""
    from core.engine.foresight.reconciler import _on_quality_score_changed

    with patch(
        "core.engine.foresight.reconciler.run_reconciler",
        AsyncMock(side_effect=RuntimeError("DB unreachable")),
    ):
        # Must not propagate.
        await _on_quality_score_changed("quality.score_changed", {"product_id": "product:platform"})


@pytest.mark.asyncio
async def test_flush_handler_coalesces_concurrent_events_for_same_product():
    """Two concurrent events for the same product → only one reconciler run.

    Prevents double-applying EMA shift on archetype_calibration.
    """
    import asyncio

    from core.engine.foresight.reconciler import _in_flight, _on_quality_score_changed

    # Reset shared state between test runs.
    _in_flight.clear()

    call_count = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_reconciler(_pid):
        nonlocal call_count
        call_count += 1
        started.set()
        await release.wait()
        return {"predictions_closed": 0, "errors": 0}

    with patch("core.engine.foresight.reconciler.run_reconciler", side_effect=slow_reconciler):
        # Start first reconciler — holds the lock.
        first = asyncio.create_task(_on_quality_score_changed("quality.score_changed", {"product_id": "product:p1"}))
        await started.wait()  # ensure first has the lock

        # Second event for same product should skip immediately.
        await _on_quality_score_changed("quality.score_changed", {"product_id": "product:p1"})

        # Release first.
        release.set()
        await first

    # Only one reconciler run despite two emits.
    assert call_count == 1


@pytest.mark.asyncio
async def test_reconciler_no_open_predictions_is_noop():
    """Reconciler with zero open predictions returns clean result dict, no error."""
    from core.engine.foresight.reconciler import run_reconciler

    pool = _make_pool({"decision_prediction": [[]]})

    with patch("core.engine.foresight.reconciler.pool", pool):
        result = await run_reconciler("product:platform")

    assert result["predictions_closed"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_reconciler_closes_overdue_prediction():
    """Reconciler closes an overdue prediction and reports predictions_closed=1."""
    import datetime

    from core.engine.foresight.reconciler import run_reconciler

    # created 20 days ago, horizon_days=7 → overdue
    old_ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=20)).isoformat()
    open_prediction = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:platform",
        "archetype": "executor",
        "discipline": "testing",
        "horizon_days": 7,
        "created_at": old_ts,
        "expected_changes": [{"capability_id": "capability:auth", "score_delta": 0.2, "confidence": 0.8}],
    }
    current_quality = [{"score": 0.7}]

    pool = _make_pool(
        {
            "FROM decision_prediction": [[open_prediction]],
            "FROM capability_quality": [current_quality],
            "capability_quality_snapshot": [[]],
            "CREATE prediction_outcome": [{"id": "prediction_outcome:po1"}],
            "archetype_calibration": [[]],  # no existing calibration record
            "UPDATE": [{"id": "decision_prediction:p1"}],
        }
    )

    with patch("core.engine.foresight.reconciler.pool", pool):
        result = await run_reconciler("product:platform")

    assert result["predictions_closed"] == 1
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_reconciler_skips_missing_capability_gracefully():
    """If a capability in expected_changes no longer exists, skip that delta gracefully."""
    import datetime

    from core.engine.foresight.reconciler import run_reconciler

    old_ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=20)).isoformat()
    open_prediction = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:platform",
        "archetype": "executor",
        "discipline": "testing",
        "horizon_days": 7,
        "created_at": old_ts,
        "expected_changes": [{"capability_id": "capability:deleted_cap", "score_delta": 0.3, "confidence": 0.6}],
    }

    pool = _make_pool(
        {
            "FROM decision_prediction": [[open_prediction]],
            "FROM capability_quality": [[]],  # capability not found
            "capability_quality_snapshot": [[]],
            "CREATE prediction_outcome": [{"id": "prediction_outcome:po1"}],
            "archetype_calibration": [[]],
            "UPDATE": [{"id": "decision_prediction:p1"}],
        }
    )

    with patch("core.engine.foresight.reconciler.pool", pool):
        result = await run_reconciler("product:platform")

    assert result["predictions_closed"] == 1
    assert result["errors"] == 0


def test_calibration_score_formula():
    """calibration_score = 1 - |predicted - actual| / 2.0, clamped to [0, 1]."""
    from core.engine.foresight.reconciler import _compute_calibration_score

    assert _compute_calibration_score(predicted=0.3, actual=0.3) == pytest.approx(1.0)
    assert _compute_calibration_score(predicted=1.0, actual=-1.0) == pytest.approx(0.0)
    assert _compute_calibration_score(predicted=0.3, actual=0.1) == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_close_prediction_force_actual_bypasses_snapshot_lookup():
    """close_prediction(..., force_actual=...) must skip the snapshot query.

    The calibration-moment demo path and seed scripts use force_actual to
    stage an outcome without waiting for real capability drift. If the
    snapshot lookup ran anyway it'd skip the cap (no baseline) and the
    calibration score would silently fall back to 0.5.
    """
    from core.engine.foresight.reconciler import close_prediction

    open_prediction = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:platform",
        "archetype": "skeptic",
        "discipline": "security",
        "horizon_days": 7,
        "created_at": "2026-01-01T00:00:00+00:00",
        "expected_changes": [
            {"capability_id": "capability:auth", "score_delta": 0.4, "confidence": 0.8},
        ],
    }

    pool = _make_pool(
        {
            "SELECT * FROM <record>$pred": [[open_prediction]],
            "CREATE prediction_outcome": [{"id": "prediction_outcome:po1"}],
            "archetype_calibration": [[]],  # no prior calibration row
            "UPDATE": [{"id": "decision_prediction:p1"}],
            # No canvas_session_id → emit is a no-op for this test.
            "SELECT canvas_session_id": [[]],
        }
    )

    with patch("core.engine.foresight.reconciler.pool", pool):
        result = await close_prediction(
            "decision_prediction:p1",
            force_actual={"capability:auth": 0.4},
        )

    # Perfect prediction (predicted 0.4, actual 0.4) → calibration_score == 1.0
    assert result["calibration_score"] == pytest.approx(1.0)
    # No prior row → weight_delta = new (1.0) - implicit prior (0.5) = 0.5
    assert result["weight_delta"] == pytest.approx(0.5)
    assert result["predicted_deltas"] == {"capability:auth": 0.4}
    assert result["actual_deltas"] == {"capability:auth": 0.4}
    assert result["archetype"] == "skeptic"


@pytest.mark.asyncio
async def test_close_prediction_missing_raises_value_error():
    """close_prediction must surface a clean error when the id doesn't exist."""
    from core.engine.foresight.reconciler import close_prediction

    pool = _make_pool({"SELECT * FROM <record>$pred": [[]]})

    with patch("core.engine.foresight.reconciler.pool", pool):
        with pytest.raises(ValueError, match="not found"):
            await close_prediction("decision_prediction:does_not_exist")


@pytest.mark.asyncio
async def test_close_prediction_emits_outcome_closed_event():
    """When the decision has a canvas_session_id, prediction.outcome.closed fires.

    The frontend roster pulse + CalibrationTab subscribe to this event — losing
    the emit silently breaks the calibration moment without any test failing.
    """
    from core.engine.foresight.reconciler import close_prediction

    open_prediction = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:platform",
        "archetype": "pm",
        "discipline": "product",
        "horizon_days": 7,
        "created_at": "2026-01-01T00:00:00+00:00",
        "expected_changes": [
            {"capability_id": "capability:onboard", "score_delta": 0.3, "confidence": 0.9},
        ],
    }
    decision_with_canvas = [
        {
            "canvas_session_id": "session:abc",
            "perspectives": [
                {"archetype": "pm", "confidence": 0.9, "contribution_summary": "ship now"},
                {"archetype": "skeptic", "confidence": 0.4, "contribution_summary": "risk"},
            ],
        }
    ]

    pool = _make_pool(
        {
            "SELECT * FROM <record>$pred": [[open_prediction]],
            "CREATE prediction_outcome": [{"id": "prediction_outcome:po1"}],
            "archetype_calibration": [[]],
            "UPDATE": [{"id": "decision_prediction:p1"}],
            "SELECT canvas_session_id": [decision_with_canvas],
        }
    )

    emitted: list[tuple[str, str, dict]] = []

    class _StubAdapter:
        def __init__(self, *_a, **_kw):
            pass

        async def emit(self, session_id, event_type, payload):
            emitted.append((session_id, event_type, payload.model_dump()))

    with (
        patch("core.engine.foresight.reconciler.pool", pool),
        patch("core.engine.canvas.surface_adapter.CanvasSurfaceAdapter", _StubAdapter),
    ):
        await close_prediction(
            "decision_prediction:p1",
            force_actual={"capability:onboard": 0.1},
        )

    assert len(emitted) == 1
    session_id, event_type, payload = emitted[0]
    assert session_id == "session:abc"
    assert event_type == "prediction.outcome.closed"
    assert payload["prediction_id"] == "decision_prediction:p1"
    assert payload["agent_id"] == "pm"  # dominant perspective by confidence
    assert payload["archetype"] == "pm"
    assert payload["predicted"] == pytest.approx(0.3)
    assert payload["actual"] == pytest.approx(0.1)
    # |0.3 - 0.1| / 2.0 = 0.1 → 1 - 0.1 = 0.9
    assert payload["calibration_score"] == pytest.approx(0.9)
    # No prior row → weight_delta = 0.9 - 0.5 (implicit prior) = 0.4
    assert payload["weight_delta"] == pytest.approx(0.4)
    assert payload["discipline"] == "product"
    # Per-cap maps must be threaded through so the canvas tile's ClosedState
    # has real deltas (not just the dominant scalar) — caught by advisor.
    assert payload["predicted_deltas"] == pytest.approx({"capability:onboard": 0.3})
    assert payload["actual_deltas"] == pytest.approx({"capability:onboard": 0.1})


@pytest.mark.asyncio
async def test_close_prediction_no_event_without_canvas_session_id():
    """No canvas_session_id on the decision → close succeeds, NO event emitted.

    Fail-open contract: predictions on non-canvas decisions (CLI captures,
    seeds, MCP) must still close and update calibration, but there is no
    canvas session to push to — the emit path must no-op silently rather
    than error or emit to a bogus session.
    """
    from core.engine.foresight.reconciler import close_prediction

    open_prediction = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:platform",
        "archetype": "pm",
        "discipline": "product",
        "horizon_days": 7,
        "created_at": "2026-01-01T00:00:00+00:00",
        "expected_changes": [
            {"capability_id": "capability:onboard", "score_delta": 0.3, "confidence": 0.9},
        ],
    }
    # Decision row exists but was never sourced from a canvas session.
    decision_without_canvas = [{"canvas_session_id": None, "perspectives": []}]

    pool = _make_pool(
        {
            "SELECT * FROM <record>$pred": [[open_prediction]],
            "CREATE prediction_outcome": [{"id": "prediction_outcome:po1"}],
            "archetype_calibration": [[]],
            "UPDATE": [{"id": "decision_prediction:p1"}],
            "SELECT canvas_session_id": [decision_without_canvas],
        }
    )

    emitted: list[tuple[str, str, dict]] = []

    class _StubAdapter:
        def __init__(self, *_a, **_kw):
            pass

        async def emit(self, session_id, event_type, payload):
            emitted.append((session_id, event_type, payload.model_dump()))

    with (
        patch("core.engine.foresight.reconciler.pool", pool),
        patch("core.engine.canvas.surface_adapter.CanvasSurfaceAdapter", _StubAdapter),
    ):
        result = await close_prediction(
            "decision_prediction:p1",
            force_actual={"capability:onboard": 0.1},
        )

    # The close itself still completes with full calibration accounting...
    assert result["calibration_score"] == pytest.approx(0.9)
    assert result["weight_delta"] == pytest.approx(0.4)
    # ...but nothing is pushed to any canvas surface.
    assert emitted == []


@pytest.mark.asyncio
async def test_close_prediction_outcome_stores_decision_as_record_ref():
    """The CREATE prediction_outcome query must cast the decision bind via <record>.

    Live-validation regression: storing decision as a bare string broke
    record-traversal (`decision.title AS …` returns None) and prevented
    the calibration API from joining the decision title back in. Mocked
    tests can't catch SurrealDB syntax bugs, but they can lock the query
    string so accidental cast removal trips here first.
    """
    from core.engine.foresight.reconciler import close_prediction

    open_prediction = {
        "id": "decision_prediction:p1",
        "decision": "decision:d1",
        "product": "product:platform",
        "archetype": "skeptic",
        "discipline": "security",
        "horizon_days": 7,
        "created_at": "2026-01-01T00:00:00+00:00",
        "expected_changes": [{"capability_id": "capability:x", "score_delta": 0.2}],
    }

    seen_queries: list[str] = []

    async def _spy_query(q, params=None):
        seen_queries.append(q)
        # Route by keyword for the orchestration to complete.
        if "SELECT * FROM <record>$pred" in q:
            return [[open_prediction]]
        if "CREATE prediction_outcome" in q:
            return [{"id": "prediction_outcome:po1"}]
        if "archetype_calibration" in q:
            return [[]]
        if "SELECT canvas_session_id" in q:
            return [[]]  # non-canvas decision — emit no-ops
        return [[]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=_spy_query)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = mock_ctx

    with patch("core.engine.foresight.reconciler.pool", pool):
        await close_prediction("decision_prediction:p1", force_actual={"capability:x": 0.2})

    create_queries = [q for q in seen_queries if "CREATE prediction_outcome" in q]
    assert create_queries, "expected at least one CREATE prediction_outcome"
    create_sql = create_queries[0]
    assert "decision            = <record>$decision" in create_sql, (
        "decision field must be cast via <record>$decision so the field stores a "
        "record reference (not a bare string) and record-traversal joins work"
    )
