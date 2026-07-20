# engine/foresight/reconciler.py
"""Close overdue predictions and update archetype calibration scores.

Registered as a sentinel engine (hourly cron) AND as an event-bus handler
for `quality.score_changed` — closing the architecture-doc claim of
"continuous weight updates on capture flush." Hourly cron remains the
safety-net fallback.
"""

from __future__ import annotations

import asyncio
import datetime
import logging

from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_EMA_ALPHA = 0.3  # exponential moving average weight for calibration score updates

# Per-product locks for flush-triggered reconciler runs.
# Prevents concurrent close of the same prediction (which would double-apply
# the EMA shift on archetype_calibration). Module-level so re-imports share state.
_in_flight: dict[str, asyncio.Lock] = {}

# Guard against duplicate handler registration on test re-imports.
_handler_registered: bool = False


def _compute_calibration_score(predicted: float, actual: float) -> float:
    """Score accuracy of a single delta prediction.

    Formula: 1 - |predicted - actual| / 2.0  (max possible error = 2.0)
    Returns float in [0.0, 1.0].
    """
    max_error = 2.0
    raw = 1.0 - abs(predicted - actual) / max_error
    return max(0.0, min(1.0, raw))


@register_engine(
    name="prediction_reconciler",
    # Audit fix (decision:uigaj1ywvn5yhaiznihu): hourly instead of nightly.
    # Reduces max calibration lag from 24h to 1h. Full streaming-on-flush
    # remains future work; this is a 24× latency improvement for ~empty
    # query cost in most hours.
    cron="0 * * * *",
    description="Close overdue predictions, score calibration, update archetype_calibration.",
)
async def run_reconciler(product_id: str) -> dict:
    """Close all overdue predictions for a product and update calibration scores."""
    results = {"predictions_closed": 0, "errors": 0}

    async with pool.connection() as db:
        pred_result = await db.query(
            "SELECT * FROM decision_prediction WHERE product = <record>$product AND closed = false",
            {"product": product_id},
        )
    open_preds = parse_rows(pred_result)

    def _is_overdue(pred: dict) -> bool:
        created_at = pred.get("created_at")
        if created_at is None:
            return False
        if isinstance(created_at, str):
            created_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if not isinstance(created_at, datetime.datetime):
            return False
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        horizon_days = int(pred.get("horizon_days", 14))
        deadline = created_at + datetime.timedelta(days=horizon_days)
        return deadline <= datetime.datetime.now(datetime.timezone.utc)

    overdue = [p for p in open_preds if _is_overdue(p)]
    logger.info("Reconciler: %d open, %d overdue for %s", len(open_preds), len(overdue), product_id)

    for pred in overdue:
        try:
            await _close_prediction(pred, product_id)
            results["predictions_closed"] += 1
        except Exception:
            logger.warning("Failed to close prediction %s", pred.get("id"), exc_info=True)
            results["errors"] += 1

    return results


async def _close_prediction(
    pred: dict,
    product_id: str,
    force_actual: dict[str, float] | None = None,
) -> dict:
    """Fetch current capability scores, compute calibration, write outcome, mark closed.

    When `force_actual` maps capability_id → actual_delta, those values are used
    directly and the capability_quality / capability_quality_snapshot lookups
    are skipped for those caps. Lets demo seeds (Task 5.1) and manual triggers
    (`close_prediction`, below) stage a calibration outcome without waiting for
    real capability score drift to land.

    Returns a summary dict carrying the data downstream surfaces need
    (calibration_score, weight_delta, deltas, agent attribution).
    """
    prediction_id = str(pred["id"])
    archetype = pred.get("archetype", "executor")
    discipline = pred.get("discipline", "general")
    expected_changes = pred.get("expected_changes") or []

    predicted_deltas: dict[str, float] = {}
    actual_deltas: dict[str, float] = {}
    calibration_scores: list[float] = []

    for change in expected_changes:
        cap_id = change.get("capability_id", "")
        predicted_delta = float(change.get("score_delta", 0.0))
        predicted_deltas[cap_id] = predicted_delta

        if force_actual is not None and cap_id in force_actual:
            forced = float(force_actual[cap_id])
            actual_deltas[cap_id] = forced
            calibration_scores.append(_compute_calibration_score(predicted_delta, forced))
            continue

        async with pool.connection() as db:
            # Pre-existing field-name bug fixed alongside this audit closure:
            # schema field is `capability` (record<capability>), not `capability_id`.
            # cap_id from the LLM is a slug; resolve to record id via subquery.
            # decision:jl4ipraz1wg84riouorf — SurrealDB v3 requires the ORDER BY
            # column in the SELECT projection.
            # decision:8vj092dt6wklp60xqfat — `WHERE field = (SELECT VALUE ... LIMIT 1)`
            # returns empty in v3 (subquery is treated as 1-element array). Use IN.
            # Slug+product is unique on `capability`, so IN matches at most one record.
            score_result = await db.query(
                """SELECT score, assessed_at FROM capability_quality
                   WHERE capability IN (
                       SELECT VALUE id FROM capability
                       WHERE slug = <string>$cap_slug AND product = <record>$product
                   )
                   ORDER BY assessed_at DESC LIMIT 1""",
                {"cap_slug": cap_id, "product": product_id},
            )
        scores = parse_rows(score_result)
        if not scores:
            # Audit fix (decision:ukydw0t9zkb5hqh0i7d2): elevate visibility.
            # Silent skip masks calibration data loss.
            logger.warning(
                "Calibration skipped: capability %s not found (prediction %s)",
                cap_id,
                prediction_id,
            )
            continue

        current_score = float(scores[0].get("score", 0.5))

        async with pool.connection() as db:
            # Same field-name fix: snapshot table uses `capability` field.
            # decision:jl4ipraz1wg84riouorf + decision:8vj092dt6wklp60xqfat — see
            # comment on the capability_quality query above for the two SurrealDB
            # v3 quirks (ORDER BY column projection + IN-vs-= for subqueries).
            # decision:080p0aqkp073bmcswfd9 — explicit <datetime> cast on
            # $created_at. The Python SDK may surface created_at as either
            # datetime obj or string depending on row serialization; the bare
            # bind silently returns 0 rows when the param arrives as a string.
            snap_result = await db.query(
                """SELECT score, assessed_at FROM capability_quality_snapshot
                   WHERE capability IN (
                       SELECT VALUE id FROM capability
                       WHERE slug = <string>$cap_slug AND product = <record>$product
                   )
                   AND assessed_at <= <datetime>$created_at
                   ORDER BY assessed_at DESC LIMIT 1""",
                {"cap_slug": cap_id, "product": product_id, "created_at": pred.get("created_at")},
            )
        snaps = parse_rows(snap_result)
        if not snaps:
            # Audit fix (decision:ukydw0t9zkb5hqh0i7d2): predictions on
            # brand-new capabilities silently lost calibration signal — the
            # cases that would teach the system fastest. WARN so it's visible.
            logger.warning(
                "Calibration skipped: no snapshot baseline for capability %s at/before %s "
                "(prediction %s) — auto-snapshot at prediction-create is the right fix",
                cap_id,
                pred.get("created_at"),
                prediction_id,
            )
            continue

        prior_score = float(snaps[0]["score"])
        actual_delta = current_score - prior_score
        actual_deltas[cap_id] = actual_delta
        calibration_scores.append(_compute_calibration_score(predicted_delta, actual_delta))

    overall_calibration = sum(calibration_scores) / len(calibration_scores) if calibration_scores else 0.5

    async with pool.connection() as db:
        await db.query(
            """CREATE prediction_outcome SET
                prediction          = <record>$prediction,
                decision            = <record>$decision,
                product             = <record>$product,
                archetype           = $archetype,
                discipline          = $discipline,
                calibration_score   = $calibration_score,
                predicted_deltas    = $predicted_deltas,
                actual_deltas       = $actual_deltas,
                closed_at           = time::now()
            """,
            {
                "prediction": prediction_id,
                "decision": str(pred.get("decision", "")),
                "product": product_id,
                "archetype": archetype,
                "discipline": discipline,
                "calibration_score": overall_calibration,
                "predicted_deltas": predicted_deltas,
                "actual_deltas": actual_deltas,
            },
        )

        existing_result = await db.query(
            "SELECT calibration_score, sample_count FROM archetype_calibration WHERE archetype = $archetype AND discipline = $discipline LIMIT 1",
            {"archetype": archetype, "discipline": discipline},
        )
        existing = parse_rows(existing_result)

        if existing:
            old_score = float(existing[0].get("calibration_score", 0.5))
            old_count = int(existing[0].get("sample_count", 0))
            new_score = _EMA_ALPHA * overall_calibration + (1 - _EMA_ALPHA) * old_score
            new_count = old_count + 1
        else:
            old_score = 0.5  # implicit prior for a never-seen archetype/discipline pair
            new_score = overall_calibration
            new_count = 1
        weight_delta = new_score - old_score

        cal_id = f"{archetype}_{discipline}"
        await db.query(
            """UPSERT type::record('archetype_calibration', $cal_id) SET
                archetype           = $archetype,
                discipline          = $discipline,
                calibration_score   = $new_score,
                sample_count        = $new_count,
                updated_at          = time::now()
            """,
            {
                "cal_id": cal_id,
                "archetype": archetype,
                "discipline": discipline,
                "new_score": new_score,
                "new_count": new_count,
            },
        )

        await db.query(
            "UPDATE <record>$prediction SET closed = true",
            {"prediction": prediction_id},
        )

    logger.info(
        "Closed prediction %s — calibration: %.3f (archetype=%s, discipline=%s)",
        prediction_id,
        overall_calibration,
        archetype,
        discipline,
    )

    summary = {
        "prediction_id": prediction_id,
        "decision_id": str(pred.get("decision", "")),
        "archetype": archetype,
        "discipline": discipline,
        "calibration_score": overall_calibration,
        "weight_delta": weight_delta,
        "predicted_deltas": predicted_deltas,
        "actual_deltas": actual_deltas,
    }

    try:
        await _emit_prediction_outcome_closed_event(summary)
    except Exception:
        # Best-effort: never let a canvas emit failure block the close itself.
        logger.warning("Failed to emit prediction.outcome.closed for %s", prediction_id, exc_info=True)

    return summary


async def close_prediction(
    prediction_id: str,
    force_actual: dict[str, float] | None = None,
) -> dict:
    """Close a specific prediction by id — regardless of horizon.

    Used by the calibration-moment demo path and by seeds (Task 5.1) that need
    to stage a closed prediction without waiting for real capability drift.
    `force_actual` (cap_id → actual_delta) bypasses snapshot lookup for the
    listed capabilities; unlisted capabilities still consult capability_quality.

    Raises ValueError if the prediction does not exist.
    """
    async with pool.connection() as db:
        pred = parse_one(
            await db.query(
                "SELECT * FROM <record>$pred",
                {"pred": prediction_id},
            )
        )
    if not pred:
        raise ValueError(f"prediction {prediction_id} not found")
    product_id = str(pred.get("product", ""))
    return await _close_prediction(pred, product_id, force_actual=force_actual)


async def _emit_prediction_outcome_closed_event(summary: dict) -> None:
    """Emit prediction.outcome.closed for the canvas session that owns this decision.

    No-ops when the decision wasn't sourced from a canvas session (no
    canvas_session_id linkage). Mirrors the pattern in
    forecaster._emit_prediction_attached_event so both lifecycle endpoints
    (attach + close) push to the same session.
    """
    decision_id = summary.get("decision_id") or ""
    if not decision_id:
        return

    async with pool.connection() as db:
        decision_row = parse_one(
            await db.query(
                "SELECT canvas_session_id, perspectives FROM <record>$d",
                {"d": decision_id},
            )
        )
    if not decision_row:
        return
    canvas_session_id = decision_row.get("canvas_session_id")
    if not canvas_session_id:
        return  # non-canvas decision — no canvas to push to

    perspectives = decision_row.get("perspectives") or []
    # Dominant agent = highest-confidence perspective, fallback to archetype on the prediction.
    agent_id = summary.get("archetype", "ace")
    if perspectives:
        max_conf = max((p.get("confidence", 0.0) for p in perspectives), default=0.0)
        top = next((p for p in perspectives if p.get("confidence", 0.0) == max_conf), None)
        if top:
            agent_id = top.get("archetype", agent_id)

    # Pick the dominant capability — largest |predicted_delta| — for the
    # event's predicted/actual scalars. Roster pulse and CalibrationTab both
    # show a single number; multi-cap close-outs collapse to their loudest.
    predicted_deltas: dict[str, float] = summary.get("predicted_deltas") or {}
    actual_deltas: dict[str, float] = summary.get("actual_deltas") or {}
    if predicted_deltas:
        dominant_cap = max(predicted_deltas, key=lambda k: abs(predicted_deltas[k]))
        predicted = float(predicted_deltas[dominant_cap])
        actual = float(actual_deltas.get(dominant_cap, 0.0))
    else:
        predicted = 0.0
        actual = 0.0

    from core.engine.api.canvas import _persist_and_broadcast
    from core.engine.canvas.event_protocol import (
        EVENT_PREDICTION_OUTCOME_CLOSED,
        PredictionOutcomeClosedPayload,
    )
    from core.engine.canvas.surface_adapter import CanvasSurfaceAdapter

    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)
    await adapter.emit(
        session_id=str(canvas_session_id),
        event_type=EVENT_PREDICTION_OUTCOME_CLOSED,
        payload=PredictionOutcomeClosedPayload(
            prediction_id=str(summary.get("prediction_id", "")),
            agent_id=str(agent_id),
            archetype=str(summary.get("archetype", "")),
            predicted=predicted,
            actual=actual,
            predicted_deltas={k: float(v) for k, v in predicted_deltas.items()},
            actual_deltas={k: float(v) for k, v in actual_deltas.items()},
            calibration_score=float(summary.get("calibration_score", 0.0)),
            weight_delta=float(summary.get("weight_delta", 0.0)),
            discipline=str(summary.get("discipline", "")),
        ),
    )


# ---------------------------------------------------------------------------
# Flush-triggered reconciliation (closes deferred half of
# decision:uigaj1ywvn5yhaiznihu — "wire reconciler to capture-flush event bus")
# ---------------------------------------------------------------------------


async def _on_quality_score_changed(event_type: str, payload: dict) -> None:
    """Handle `quality.score_changed` — run flush-triggered reconciler for the affected product.

    Per-product lock prevents concurrent reconciler runs from double-applying
    the EMA shift on archetype_calibration. Concurrent events for the same
    product are coalesced (later ones skip while the first is still running).

    Never raises — handler failures are logged so event emission stays safe.
    """
    product_id = payload.get("product_id")
    if not product_id:
        logger.debug("quality.score_changed received with no product_id; skipping")
        return

    lock = _in_flight.setdefault(product_id, asyncio.Lock())
    if lock.locked():
        logger.debug("flush-triggered reconciler skipped (already running for %s)", product_id)
        return

    async with lock:
        try:
            result = await run_reconciler(product_id)
            if result.get("predictions_closed", 0) > 0:
                logger.info(
                    "flush-triggered reconciler closed %d prediction(s) for %s",
                    result["predictions_closed"],
                    product_id,
                )
        except Exception:
            logger.warning(
                "flush-triggered reconciler failed for %s",
                product_id,
                exc_info=True,
            )


def _register_event_handlers() -> None:
    """Subscribe the flush-triggered handler to the event bus once per process."""
    global _handler_registered
    if _handler_registered:
        return
    try:
        from core.engine.events.bus import bus

        bus.on("quality.score_changed", _on_quality_score_changed)
        _handler_registered = True
        logger.debug("Reconciler subscribed to quality.score_changed")
    except Exception:
        # Never fail import — flush-trigger is a nice-to-have; hourly cron still runs.
        logger.warning("Failed to register flush-triggered reconciler handler", exc_info=True)


_register_event_handlers()
