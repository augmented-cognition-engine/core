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

logger = logging.getLogger(__name__)
router = APIRouter(tags=["foresight"])


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
        outcomes.append(
            {
                "id": str(r.get("id", "")),
                "prediction_id": str(r.get("prediction", "")),
                "decision_id": decision_id,
                "decision_title": title,
                "archetype": r.get("archetype", ""),
                "discipline": r.get("discipline", ""),
                "calibration_score": float(r.get("calibration_score", 0.0)),
                "predicted_deltas": r.get("predicted_deltas") or {},
                "actual_deltas": r.get("actual_deltas") or {},
                "closed_at": str(r.get("closed_at", "")),
            }
        )
    return {"outcomes": outcomes}
