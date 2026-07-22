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
import hashlib
import logging
import math

from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.foresight.contracts import (
    RESOLUTION_CONTRACT_VERSION,
    assess_resolution,
    build_resolution_contract,
    normalize_comparator_observation,
    normalize_forecast_record,
    normalize_intervention_observation,
)
from core.engine.foresight.outside_view import compare_forecast_to_outside_view
from core.engine.foresight.scoring import score_prediction
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
    if not math.isfinite(predicted) or not math.isfinite(actual):
        raise ValueError("calibration inputs must be finite")
    max_error = 2.0
    raw = 1.0 - abs(predicted - actual) / max_error
    return max(0.0, min(1.0, raw))


def _is_overdue(pred: dict, *, now: datetime.datetime | None = None) -> bool:
    created_at = pred.get("created_at")
    if created_at is None:
        return False
    if isinstance(created_at, str):
        try:
            created_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(created_at, datetime.datetime):
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.timezone.utc)
    horizon_days = int(pred.get("horizon_days", 14))
    deadline = created_at + datetime.timedelta(days=horizon_days)
    return deadline <= (now or datetime.datetime.now(datetime.timezone.utc))


async def _latest_intervention_observation(prediction_id: str, product_id: str) -> dict | None:
    async with pool.connection() as db:
        result = await db.query(
            """SELECT * FROM observation
               WHERE product = <record>$product
                 AND observation_type = 'intervention'
                 AND affected_prediction = <record>$prediction
               ORDER BY observed_at DESC, created_at DESC LIMIT 1""",
            {"product": product_id, "prediction": prediction_id},
        )
    return parse_one(result)


async def _latest_eligible_comparator_observation(prediction_id: str, product_id: str) -> dict | None:
    async with pool.connection() as db:
        result = await db.query(
            """SELECT * FROM observation
               WHERE product = <record>$product
                 AND observation_type = 'forecast_comparator'
                 AND affected_prediction = <record>$prediction
                 AND comparator_resolution_eligible = true
               ORDER BY observed_at DESC, created_at DESC LIMIT 1""",
            {"product": product_id, "prediction": prediction_id},
        )
    return parse_one(result)


def _intervention_resolution_inputs(observation: dict | None) -> dict:
    if not observation:
        return {}
    contract = normalize_intervention_observation(observation)
    applicability = contract.get("applicability") or {}
    return {
        "intervention_status": contract.get("status") or "unknown",
        "applicability_conditions_met": applicability.get("conditions_met"),
        "observation_refs": [str(observation.get("id", ""))] + list(contract.get("evidence_refs") or []),
        "confounders": list(contract.get("confounders") or []),
        "missing_evidence": list(contract.get("missing_evidence") or []),
        "resolution_reason": contract.get("reason"),
    }


def _comparator_resolution_inputs(observation: dict | None) -> dict:
    """Project only explicitly eligible comparator effects into resolution inputs."""
    if not observation:
        return {}
    from core.engine.foresight.comparators import comparator_effects

    contract = normalize_comparator_observation(observation)
    effects = comparator_effects(contract)
    if not effects:
        return {}
    comparator = contract.get("comparator") or {}
    plan_alignment = contract.get("plan_alignment") or {}
    observation_id = str(observation.get("id") or contract.get("observation_id") or "")
    return {
        "force_actual": effects,
        "observation_refs": [observation_id] + list(contract.get("evidence_refs") or []),
        "confounders": list(contract.get("confounders") or []),
        "comparator_context": {
            "contract_version": contract.get("contract_version"),
            "observation_id": observation_id,
            "comparator_type": comparator.get("type"),
            "design": comparator.get("design"),
            "attribution_strength": comparator.get("attribution_strength"),
            "effective_attribution_strength": plan_alignment.get(
                "effective_attribution_strength", comparator.get("attribution_strength")
            ),
            "plan_id": plan_alignment.get("plan_id"),
            "plan_alignment_state": plan_alignment.get("state", "unlinked"),
            "plan_deviations": list(plan_alignment.get("deviations") or []),
            "causal_claim": bool(comparator.get("causal_claim")),
            "effect_method": contract.get("effect_method"),
            "effect_deltas": effects,
        },
    }


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

    # Evaluate only frozen machine-resolvable leading-indicator rules. This runs on both the
    # quality-change path and the hourly path, so a missed in-process event is recovered after
    # restart. Idempotent evidence identities prevent duplicate observations.
    from core.engine.foresight.indicators import evaluate_indicator_rules_for_prediction

    for pred in open_preds:
        try:
            indicator_results = await evaluate_indicator_rules_for_prediction(pred, product_id, pool=pool)
            if indicator_results:
                pred["indicator_evidence_state"] = indicator_results[-1].get("indicator_state")
        except Exception:
            logger.warning("Indicator evaluation failed for %s", pred.get("id"), exc_info=True)
            results["errors"] += 1

    eligible: list[tuple[dict, dict]] = []
    for pred in open_preds:
        observation = await _latest_intervention_observation(str(pred.get("id", "")), product_id)
        inputs = _intervention_resolution_inputs(observation)
        invalidated = (
            inputs.get("intervention_status") == "cancelled" or inputs.get("applicability_conditions_met") is False
        )
        if _is_overdue(pred) or invalidated:
            comparator_observation = await _latest_eligible_comparator_observation(str(pred.get("id", "")), product_id)
            comparator_inputs = _comparator_resolution_inputs(comparator_observation)
            if comparator_inputs:
                inputs["force_actual"] = comparator_inputs["force_actual"]
                inputs["comparator_context"] = comparator_inputs["comparator_context"]
                inputs["observation_refs"] = list(inputs.get("observation_refs") or []) + list(
                    comparator_inputs.get("observation_refs") or []
                )
                inputs["confounders"] = list(inputs.get("confounders") or []) + list(
                    comparator_inputs.get("confounders") or []
                )
            eligible.append((pred, inputs))
    logger.info(
        "Reconciler: %d open, %d horizon-or-invalid eligible for %s",
        len(open_preds),
        len(eligible),
        product_id,
    )

    for pred, inputs in eligible:
        try:
            await _close_prediction(pred, product_id, **inputs)
            results["predictions_closed"] += 1
        except Exception:
            logger.warning("Failed to close prediction %s", pred.get("id"), exc_info=True)
            results["errors"] += 1

    return results


async def process_intervention_observation(observation: dict) -> dict:
    """Resolve an invalidated or due prediction from a persisted intervention observation.

    Started, partial, and completed interventions remain open before the forecast horizon. A
    cancellation or failed applicability condition resolves immediately as invalid and unscored.
    The hourly reconciler is the durable retry path because it reloads the latest observation.
    """
    contract = normalize_intervention_observation(observation)
    product_id = str(observation.get("product") or contract.get("product_id") or "")
    prediction_id = str(observation.get("affected_prediction") or contract.get("prediction_id") or "")
    if not product_id or not prediction_id:
        return {"state": "degraded", "reason": "missing_product_or_prediction_identity"}
    if (contract.get("compatibility") or {}).get("state") != "current":
        return {"state": "degraded", "reason": "unsupported_intervention_observation"}

    lock = _in_flight.setdefault(product_id, asyncio.Lock())
    if lock.locked():
        return {"state": "coalesced", "reason": "product_reconciliation_in_flight"}

    async with lock:
        async with pool.connection() as db:
            pred = parse_one(await db.query("SELECT * FROM ONLY <record>$prediction", {"prediction": prediction_id}))
        if not pred or str(pred.get("product", "")) != product_id:
            return {"state": "degraded", "reason": "prediction_not_found_in_product"}
        if bool(pred.get("closed")):
            return {"state": "already_resolved", "prediction_id": prediction_id}

        inputs = _intervention_resolution_inputs(observation)
        invalidated = (
            inputs.get("intervention_status") == "cancelled" or inputs.get("applicability_conditions_met") is False
        )
        if not invalidated and not _is_overdue(pred):
            return {
                "state": "awaiting_horizon",
                "prediction_id": prediction_id,
                "intervention_status": inputs.get("intervention_status"),
            }

        comparator = await _latest_eligible_comparator_observation(prediction_id, product_id)
        comparator_inputs = _comparator_resolution_inputs(comparator)
        if comparator_inputs:
            inputs["force_actual"] = comparator_inputs["force_actual"]
            inputs["comparator_context"] = comparator_inputs["comparator_context"]
            inputs["observation_refs"] = list(inputs.get("observation_refs") or []) + list(
                comparator_inputs.get("observation_refs") or []
            )
            inputs["confounders"] = list(inputs.get("confounders") or []) + list(
                comparator_inputs.get("confounders") or []
            )
        summary = await _close_prediction(pred, product_id, **inputs)
        return {
            "state": "resolved",
            "prediction_id": prediction_id,
            "resolution_state": summary.get("resolution_state"),
            "score_eligible": summary.get("score_eligible"),
            "non_score_reason": summary.get("non_score_reason"),
        }


async def process_comparator_observation(observation: dict) -> dict:
    """Attempt resolution for comparator evidence without bypassing the forecast horizon."""
    contract = normalize_comparator_observation(observation)
    product_id = str(observation.get("product") or contract.get("product_id") or "")
    prediction_id = str(observation.get("affected_prediction") or contract.get("prediction_id") or "")
    if not product_id or not prediction_id:
        return {"state": "degraded", "reason": "missing_product_or_prediction_identity"}
    if not contract.get("resolution_eligible"):
        return {
            "state": "recorded_ineligible",
            "reason": "comparator_not_resolution_eligible",
            "non_eligibility_reasons": contract.get("non_eligibility_reasons") or [],
        }

    lock = _in_flight.setdefault(product_id, asyncio.Lock())
    if lock.locked():
        return {"state": "coalesced", "reason": "product_reconciliation_in_flight"}
    async with lock:
        async with pool.connection() as db:
            pred = parse_one(await db.query("SELECT * FROM ONLY <record>$prediction", {"prediction": prediction_id}))
        if not pred or str(pred.get("product", "")) != product_id:
            return {"state": "degraded", "reason": "prediction_not_found_in_product"}
        if bool(pred.get("closed")):
            return {"state": "already_resolved", "prediction_id": prediction_id}
        if not _is_overdue(pred):
            return {"state": "awaiting_horizon", "prediction_id": prediction_id}

        intervention = await _latest_intervention_observation(prediction_id, product_id)
        inputs = _intervention_resolution_inputs(intervention)
        comparator_inputs = _comparator_resolution_inputs(observation)
        inputs["force_actual"] = comparator_inputs.get("force_actual")
        inputs["comparator_context"] = comparator_inputs.get("comparator_context")
        inputs["observation_refs"] = list(inputs.get("observation_refs") or []) + list(
            comparator_inputs.get("observation_refs") or []
        )
        inputs["confounders"] = list(inputs.get("confounders") or []) + list(comparator_inputs.get("confounders") or [])
        summary = await _close_prediction(pred, product_id, **inputs)
        return {
            "state": "resolved",
            "prediction_id": prediction_id,
            "resolution_state": summary.get("resolution_state"),
            "score_eligible": summary.get("score_eligible"),
            "non_score_reason": summary.get("non_score_reason"),
        }


async def _close_prediction(
    pred: dict,
    product_id: str,
    force_actual: dict[str, float] | None = None,
    *,
    resolution_state: str | None = None,
    intervention_status: str | None = None,
    applicability_conditions_met: bool | None = None,
    observation_refs: list[str] | None = None,
    confounders: list[str] | None = None,
    missing_evidence: list[str] | None = None,
    resolution_reason: str | None = None,
    comparator_context: dict | None = None,
) -> dict:
    """Observe and resolve a prediction without turning absence into a neutral score.

    When `force_actual` maps capability_id → actual_delta, those values are used
    directly and the capability_quality / capability_quality_snapshot lookups
    are skipped for those caps. For backward compatibility, that explicit manual
    override also means the intervention is treated as completed and applicable
    unless the caller supplies stricter values.

    Automatic horizon closure is conservative: a capability delta can be observed,
    but it is not attributed to the decision or used for calibration until the
    intervention and applicability conditions are themselves observed.
    """
    prediction_id = str(pred["id"])
    archetype = pred.get("archetype", "executor")
    discipline = pred.get("discipline", "general")
    expected_changes = pred.get("expected_changes") or []
    forecast_contract = normalize_forecast_record(pred)

    if intervention_status is None:
        if force_actual is not None:
            intervention_status = "completed"
        else:
            intervention_status = str((forecast_contract.get("intervention") or {}).get("status") or "unknown")
    if applicability_conditions_met is None and force_actual is not None:
        applicability_conditions_met = True

    predicted_deltas: dict[str, float] = {}
    actual_deltas: dict[str, float] = {}
    calibration_scores: list[float] = []
    resolved_observation_refs = list(observation_refs or [])
    indicator_state = pred.get("indicator_evidence_state")
    if isinstance(indicator_state, dict):
        resolved_observation_refs.extend(str(ref) for ref in (indicator_state.get("observation_refs") or []) if ref)
    resolved_missing_evidence = list(missing_evidence or [])

    for index, change in enumerate(expected_changes):
        if not isinstance(change, dict):
            resolved_missing_evidence.append(f"expected_changes:{index}:malformed")
            continue
        cap_id = str(change.get("capability_id", "")).strip()
        try:
            predicted_delta = float(change.get("score_delta"))
        except (TypeError, ValueError):
            resolved_missing_evidence.append(f"expected_changes:{index}:invalid_score_delta")
            continue
        if not math.isfinite(predicted_delta):
            resolved_missing_evidence.append(f"expected_changes:{index}:invalid_score_delta")
            continue
        if not cap_id:
            resolved_missing_evidence.append(f"expected_changes:{index}:missing_capability")
            continue
        predicted_deltas[cap_id] = predicted_delta

        if intervention_status == "cancelled" or applicability_conditions_met is False:
            continue

        if force_actual is not None and cap_id in force_actual:
            try:
                forced = float(force_actual[cap_id])
            except (TypeError, ValueError):
                resolved_missing_evidence.append(f"forced_actual:{cap_id}:invalid")
                continue
            if not math.isfinite(forced):
                resolved_missing_evidence.append(f"forced_actual:{cap_id}:invalid")
                continue
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
            logger.warning(
                "Calibration skipped: capability %s not found (prediction %s)",
                cap_id,
                prediction_id,
            )
            resolved_missing_evidence.append(f"capability_quality:{cap_id}")
            continue

        try:
            current_score = float(scores[0].get("score"))
        except (TypeError, ValueError):
            resolved_missing_evidence.append(f"capability_quality:{cap_id}:invalid_score")
            continue
        if not math.isfinite(current_score):
            resolved_missing_evidence.append(f"capability_quality:{cap_id}:invalid_score")
            continue
        assessed_at = scores[0].get("assessed_at")
        if assessed_at is not None:
            resolved_observation_refs.append(f"capability_quality:{cap_id}:{assessed_at}")

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
            logger.warning(
                "Calibration skipped: no snapshot baseline for capability %s at/before %s "
                "(prediction %s) — auto-snapshot at prediction-create is the right fix",
                cap_id,
                pred.get("created_at"),
                prediction_id,
            )
            resolved_missing_evidence.append(f"capability_quality_snapshot:{cap_id}")
            continue

        try:
            prior_score = float(snaps[0]["score"])
        except (KeyError, TypeError, ValueError):
            resolved_missing_evidence.append(f"capability_quality_snapshot:{cap_id}:invalid_score")
            continue
        if not math.isfinite(prior_score):
            resolved_missing_evidence.append(f"capability_quality_snapshot:{cap_id}:invalid_score")
            continue
        actual_delta = current_score - prior_score
        actual_deltas[cap_id] = actual_delta
        calibration_scores.append(_compute_calibration_score(predicted_delta, actual_delta))

    assessment = assess_resolution(
        requested_state=resolution_state,
        intervention_status=intervention_status,
        applicability_conditions_met=applicability_conditions_met,
        actual_deltas=actual_deltas,
        calibration_scores=calibration_scores,
        missing_evidence=resolved_missing_evidence,
    )
    overall_calibration = (
        sum(calibration_scores) / len(calibration_scores) if assessment.score_eligible and calibration_scores else None
    )
    outside_view_comparison = compare_forecast_to_outside_view(
        forecast_contract=forecast_contract,
        predicted_deltas=predicted_deltas,
        actual_deltas=actual_deltas,
    )
    prediction_score = score_prediction(
        forecast_contract=forecast_contract,
        actual_deltas=actual_deltas,
        resolution_score_eligible=assessment.score_eligible,
        non_score_reason=assessment.non_score_reason,
    )
    decision_id = str(pred.get("decision", ""))
    resolved_observation_refs = list(dict.fromkeys(resolved_observation_refs))
    resolution_contract = build_resolution_contract(
        prediction_id=prediction_id,
        decision_id=decision_id,
        product_id=product_id,
        assessment=assessment,
        intervention_status=intervention_status,
        applicability_conditions_met=applicability_conditions_met,
        predicted_deltas=predicted_deltas,
        actual_deltas=actual_deltas,
        calibration_score=overall_calibration,
        observation_refs=resolved_observation_refs,
        confounders=confounders,
        missing_evidence=resolved_missing_evidence,
        resolution_reason=resolution_reason,
        outside_view_comparison=outside_view_comparison,
        prediction_score=prediction_score,
        comparator_context=comparator_context,
    )

    async with pool.connection() as db:
        await db.query(
            """CREATE prediction_outcome SET
                prediction          = <record>$prediction,
                decision            = <record>$decision,
                product             = <record>$product,
                archetype           = $archetype,
                discipline          = $discipline,
                contract_version    = $contract_version,
                resolution_contract = $resolution_contract,
                resolution_state    = $resolution_state,
                score_eligible      = $score_eligible,
                non_score_reason    = $non_score_reason,
                intervention_status = $intervention_status,
                applicability_conditions_met = $applicability_conditions_met,
                observation_refs    = $observation_refs,
                confounders         = $confounders,
                missing_evidence    = $missing_evidence,
                resolution_reason   = $resolution_reason,
                calibration_score   = $calibration_score,
                outside_view_comparison = $outside_view_comparison,
                prediction_score_version = $prediction_score_version,
                prediction_score     = $prediction_score,
                comparator_context    = $comparator_context,
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
                "contract_version": RESOLUTION_CONTRACT_VERSION,
                "resolution_contract": resolution_contract,
                "resolution_state": assessment.state,
                "score_eligible": assessment.score_eligible,
                "non_score_reason": assessment.non_score_reason,
                "intervention_status": intervention_status,
                "applicability_conditions_met": applicability_conditions_met,
                "observation_refs": resolved_observation_refs,
                "confounders": list(confounders or []),
                "missing_evidence": resolved_missing_evidence,
                "resolution_reason": resolution_reason,
                "calibration_score": overall_calibration,
                "outside_view_comparison": outside_view_comparison,
                "prediction_score_version": prediction_score["contract_version"],
                "prediction_score": prediction_score,
                "comparator_context": comparator_context,
                "predicted_deltas": predicted_deltas,
                "actual_deltas": actual_deltas,
            },
        )

        weight_delta = 0.0
        if assessment.score_eligible and overall_calibration is not None:
            existing_result = await db.query(
                """SELECT calibration_score, sample_count FROM archetype_calibration
                   WHERE product = <record>$product
                     AND archetype = $archetype AND discipline = $discipline LIMIT 1""",
                {"product": product_id, "archetype": archetype, "discipline": discipline},
            )
            existing = parse_rows(existing_result)

            if existing:
                old_score = float(existing[0].get("calibration_score", 0.5))
                old_count = int(existing[0].get("sample_count", 0))
                new_score = _EMA_ALPHA * overall_calibration + (1 - _EMA_ALPHA) * old_score
                new_count = old_count + 1
            else:
                old_score = 0.5
                new_score = overall_calibration
                new_count = 1
            weight_delta = new_score - old_score

            cal_id = hashlib.sha256(f"{product_id}|{archetype}|{discipline}".encode()).hexdigest()[:24]
            await db.query(
                """UPSERT type::record('archetype_calibration', $cal_id) SET
                    product             = <record>$product,
                    archetype           = $archetype,
                    discipline          = $discipline,
                    calibration_score   = $new_score,
                    sample_count        = $new_count,
                    updated_at          = time::now()
                """,
                {
                    "cal_id": cal_id,
                    "product": product_id,
                    "archetype": archetype,
                    "discipline": discipline,
                    "new_score": new_score,
                    "new_count": new_count,
                },
            )

        await db.query(
            "UPDATE <record>$prediction SET closed = true, resolution_status = $resolution_status",
            {"prediction": prediction_id, "resolution_status": assessment.state},
        )

    if assessment.score_eligible:
        logger.info(
            "Resolved prediction %s as %s — calibration: %.3f (archetype=%s, discipline=%s)",
            prediction_id,
            assessment.state,
            overall_calibration,
            archetype,
            discipline,
        )
    else:
        logger.info(
            "Resolved prediction %s as %s without calibration (%s)",
            prediction_id,
            assessment.state,
            assessment.non_score_reason,
        )

    summary = {
        "prediction_id": prediction_id,
        "decision_id": decision_id,
        "archetype": archetype,
        "discipline": discipline,
        "resolution_state": assessment.state,
        "score_eligible": assessment.score_eligible,
        "non_score_reason": assessment.non_score_reason,
        "resolution_contract": resolution_contract,
        "calibration_score": overall_calibration,
        "outside_view_comparison": outside_view_comparison,
        "prediction_score": prediction_score,
        "comparator_context": comparator_context,
        "weight_delta": weight_delta,
        "predicted_deltas": predicted_deltas,
        "actual_deltas": actual_deltas,
    }

    if assessment.score_eligible:
        try:
            await _emit_prediction_outcome_closed_event(summary)
        except Exception:
            logger.warning("Failed to emit prediction.outcome.closed for %s", prediction_id, exc_info=True)

    return summary


async def close_prediction(
    prediction_id: str,
    force_actual: dict[str, float] | None = None,
    *,
    resolution_state: str | None = None,
    intervention_status: str | None = None,
    applicability_conditions_met: bool | None = None,
    observation_refs: list[str] | None = None,
    confounders: list[str] | None = None,
    missing_evidence: list[str] | None = None,
    resolution_reason: str | None = None,
    comparator_context: dict | None = None,
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
    return await _close_prediction(
        pred,
        product_id,
        force_actual=force_actual,
        resolution_state=resolution_state,
        intervention_status=intervention_status,
        applicability_conditions_met=applicability_conditions_met,
        observation_refs=observation_refs,
        confounders=confounders,
        missing_evidence=missing_evidence,
        resolution_reason=resolution_reason,
        comparator_context=comparator_context,
    )


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
    try:
        from core.engine.events.bus import bus

        registered = bus.list_handlers().get("quality.score_changed", [])
        if _handler_registered and "_on_quality_score_changed" in registered:
            return
        bus.on("quality.score_changed", _on_quality_score_changed)
        _handler_registered = True
        logger.debug("Reconciler subscribed to quality.score_changed")
    except Exception:
        # Never fail import — flush-trigger is a nice-to-have; hourly cron still runs.
        logger.warning("Failed to register flush-triggered reconciler handler", exc_info=True)


_register_event_handlers()
