"""Foresight API — rollouts, predictions, calibrations.

The /foresight/{product_id}/rollouts endpoint returns the most recent cached
rollout scenario for a product (3 futures, distinct authoring archetypes).
On cache miss, triggers the planner inline. The cache is the `rollout_cache`
SurrealDB table (4hr TTL, defined in schema/v105_rollout_cache.surql).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException

from core.engine.core.db import parse_rows
from core.engine.core.db import pool as _pool
from core.engine.foresight.contracts import (
    normalize_comparator_observation,
    normalize_comparator_plan,
    normalize_forecast_record,
    normalize_indicator_observation,
    normalize_intervention_observation,
    normalize_resolution_record,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["foresight"])


@router.get("/foresight/{product_id:path}/scores")
async def get_prediction_scores(product_id: str, limit: int = 200) -> dict[str, Any]:
    """Return product-scoped Prediction Score v1 rows and sample-aware summaries."""
    from core.engine.foresight.scoring import summarize_prediction_scores

    bounded_limit = max(1, min(int(limit), 500))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, prediction, decision, discipline, resolution_contract,
                          prediction_score_version, prediction_score, closed_at
                   FROM prediction_outcome
                   WHERE product = <record>$product
                   ORDER BY closed_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {
        "summary": summarize_prediction_scores(rows),
        "outcomes": [
            {
                "outcome_id": str(row.get("id", "")),
                "prediction_id": str(row.get("prediction", "")),
                "decision_id": str(row.get("decision", "")),
                "discipline": row.get("discipline"),
                "closed_at": str(row.get("closed_at", "")),
                "prediction_score": row.get("prediction_score"),
            }
            for row in rows
        ],
    }


@router.get("/foresight/{product_id:path}/outside-view")
async def get_outside_view_baselines(product_id: str, limit: int = 20) -> dict[str, Any]:
    """Return frozen, bounded outside-view baselines for recent product forecasts."""
    bounded_limit = max(1, min(int(limit), 100))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, decision, product, archetype, discipline, horizon_days,
                          contract_version, forecast_contract, outside_view_version,
                          outside_view_baseline, closed, created_at
                   FROM decision_prediction
                   WHERE product = <record>$product
                   ORDER BY created_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    baselines = []
    for row in rows:
        contract = normalize_forecast_record(row)
        baseline = contract.get("baseline") if isinstance(contract.get("baseline"), dict) else {}
        baselines.append(
            {
                "prediction_id": str(row.get("id", "")),
                "decision_id": str(row.get("decision", "")),
                "created_at": str(row.get("created_at", "")),
                "outside_view": baseline.get("outside_view"),
                "no_action_grounding": baseline.get("no_action_grounding"),
            }
        )
    return {"baselines": baselines}


@router.get("/foresight/{product_id:path}/indicators")
async def get_indicator_observations(product_id: str, limit: int = 100) -> dict[str, Any]:
    """Return bounded leading-indicator evidence for one product."""
    bounded_limit = max(1, min(int(limit), 200))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'forecast_indicator'
                   ORDER BY observed_at DESC, created_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {"indicators": [normalize_indicator_observation(row) for row in rows]}


@router.get("/foresight/{product_id:path}/interventions")
async def get_intervention_observations(product_id: str, limit: int = 50) -> dict[str, Any]:
    """Return bounded Intervention Observation v1 projections for one product."""
    bounded_limit = max(1, min(int(limit), 100))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'intervention'
                   ORDER BY observed_at DESC, created_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {"interventions": [normalize_intervention_observation(row) for row in rows]}


@router.get("/foresight/{product_id:path}/comparators")
async def get_comparator_observations(product_id: str, limit: int = 50) -> dict[str, Any]:
    """Return bounded Comparator Observation v1 projections for one product."""
    bounded_limit = max(1, min(int(limit), 100))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'forecast_comparator'
                   ORDER BY observed_at DESC, created_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {"comparators": [normalize_comparator_observation(row) for row in rows]}


@router.get("/foresight/{product_id:path}/comparator-plans")
async def get_comparator_plans(product_id: str, limit: int = 50) -> dict[str, Any]:
    """Return optional frozen Comparator Plan v1 projections for recent forecasts."""
    bounded_limit = max(1, min(int(limit), 100))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, decision, product, horizon_days, contract_version, forecast_contract,
                          comparator_plan_version, comparator_plan, comparator_plan_status, created_at
                   FROM decision_prediction
                   WHERE product = <record>$product
                   ORDER BY created_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {
        "plans": [
            {
                "prediction_id": str(row.get("id", "")),
                "decision_id": str(row.get("decision", "")),
                "created_at": str(row.get("created_at", "")),
                "plan": normalize_comparator_plan(row),
            }
            for row in rows
        ]
    }


@router.get("/foresight/{product_id:path}/measurements")
async def get_forecast_measurements(product_id: str, limit: int = 100) -> dict[str, Any]:
    """Return raw Measurement Observation v1 samples and their ingestion status."""
    from core.engine.foresight.measurements import normalize_measurement_observation

    bounded_limit = max(1, min(int(limit), 500))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM observation
                   WHERE product = <record>$product
                     AND observation_type = 'forecast_measurement'
                   ORDER BY measured_at DESC, created_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {
        "measurements": [
            {
                "sample": normalize_measurement_observation(row),
                "ingestion_status": row.get("measurement_ingestion_status") or "collecting",
                "comparator_observation_id": str(row.get("measurement_comparator_observation") or "") or None,
            }
            for row in rows
        ]
    }


@router.get("/foresight/{product_id:path}/measurement-ingestions")
async def get_measurement_ingestions(product_id: str, limit: int = 50) -> dict[str, Any]:
    """Return the latest product-scoped ingestion receipt for each recent prediction."""
    bounded_limit = max(1, min(int(limit), 100))
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT id, decision, measurement_ingestion_version,
                          measurement_ingestion_state, measurement_ingestion_status,
                          measurement_ingestion_updated_at
                   FROM decision_prediction
                   WHERE product = <record>$product
                     AND measurement_ingestion_version != NONE
                   ORDER BY measurement_ingestion_updated_at DESC LIMIT $limit""",
                {"product": product_id, "limit": bounded_limit},
            )
        )
    return {
        "ingestions": [
            {
                "prediction_id": str(row.get("id", "")),
                "decision_id": str(row.get("decision", "")),
                "status": row.get("measurement_ingestion_status"),
                "updated_at": str(row.get("measurement_ingestion_updated_at", "")),
                "receipt": row.get("measurement_ingestion_state"),
            }
            for row in rows
        ]
    }


@router.get("/foresight/{product_id:path}/rollouts")
async def get_rollouts(product_id: str) -> dict[str, Any]:
    """Return up to 3 rollout futures for the product.

    Strategy:
    - Read most recent cached scenario for the product.
    - If none exists, return an empty scenarios list (frontend renders empty state).
      We do NOT auto-trigger plan_rollout here because it requires a candidate
      decision; the foresight tab's "Generate" button is the natural trigger.
    """
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT *, created_at FROM rollout_cache WHERE product = <record>$p ORDER BY created_at DESC LIMIT 1;",
                {"p": product_id},
            )
        )
    if not rows:
        return {"scenarios": []}

    scenario = rows[0]
    # Normalize: ensure branches expose authored_by_archetype (may be empty for legacy rows).
    branches = scenario.get("branches") or []
    for b in branches:
        b.setdefault("authored_by_archetype", "")
    return {"scenarios": [scenario]}


@router.post("/foresight/{product_id:path}/rollouts/generate")
async def generate_rollout(product_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Trigger plan_rollout on a candidate decision.

    Body: {"candidate_decision": "free-text or initiative title"}
    Returns the freshly-generated RolloutResult.
    """
    candidate = (body or {}).get("candidate_decision", "").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="candidate_decision is required")

    from core.engine.foresight.planner import plan_rollout

    result = await plan_rollout(candidate_decision=candidate, product_id=product_id)
    return asdict(result)


@router.get("/foresight/{product_id:path}/calibration")
async def get_calibration(product_id: str, limit: int = 20) -> dict[str, Any]:
    """Return recent closed prediction_outcome rows for the product.

    Powers the Foresight → Calibration tab: shows how each archetype's recent
    predictions actually played out. Ordered most-recent first.

    Each row is enriched with the underlying decision's title so the card
    reads as "Skeptic's call on <decision title> played out at 98%" rather
    than a context-free archetype + score. Outcomes whose decision row no
    longer exists (orphans from test cycles, manual cleanups, etc.) are
    filtered out — a card with no traceability isn't useful.
    """
    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT * FROM prediction_outcome
                   WHERE product = <record>$p
                   ORDER BY closed_at DESC
                   LIMIT $limit""",
                {"p": product_id, "limit": int(limit)},
            )
        )

        # Batched decision-title lookup. SurrealDB v3 won't match record IDs
        # against bare strings, so we cast each bind via <record>$dN.
        decision_id_strs = sorted({str(r.get("decision", "")) for r in rows if r.get("decision")})
        titles: dict[str, str] = {}
        if decision_id_strs:
            in_clause = ", ".join(f"<record>$d{i}" for i in range(len(decision_id_strs)))
            params = {f"d{i}": v for i, v in enumerate(decision_id_strs)}
            decision_rows = parse_rows(
                await db.query(
                    f"SELECT id, title FROM decision WHERE id IN [{in_clause}]",
                    params,
                )
            )
            titles = {str(d["id"]): str(d.get("title", "")) for d in decision_rows}

    outcomes = []
    for r in rows:
        decision_id = str(r.get("decision", ""))
        title = titles.get(decision_id)
        if not title:
            continue  # orphan — decision row no longer exists; skip the ghost
        resolution_contract = normalize_resolution_record(r)
        raw_calibration = r.get("calibration_score")
        outcomes.append(
            {
                "id": str(r.get("id", "")),
                "prediction_id": str(r.get("prediction", "")),
                "decision_id": decision_id,
                "decision_title": title,
                "archetype": r.get("archetype", ""),
                "discipline": r.get("discipline", ""),
                "calibration_score": float(raw_calibration) if raw_calibration is not None else None,
                "outside_view_comparison": r.get("outside_view_comparison")
                or (resolution_contract.get("scoring") or {}).get("outside_view_comparison"),
                "prediction_score": r.get("prediction_score")
                or (resolution_contract.get("scoring") or {}).get("prediction_score"),
                "comparator_context": r.get("comparator_context") or resolution_contract.get("comparator"),
                "resolution_state": r.get("resolution_state") or resolution_contract.get("state"),
                "score_eligible": bool(r.get("score_eligible", resolution_contract.get("score_eligible", False))),
                "non_score_reason": r.get("non_score_reason") or resolution_contract.get("non_score_reason"),
                "predicted_deltas": r.get("predicted_deltas") or {},
                "actual_deltas": r.get("actual_deltas") or {},
                "closed_at": str(r.get("closed_at", "")),
                "contract": resolution_contract,
            }
        )
    return {"outcomes": outcomes}
