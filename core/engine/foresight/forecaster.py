# engine/foresight/forecaster.py
"""Attach a forward prediction to a decision immediately after it is committed.

Fire-and-forget safe: attach_prediction catches all exceptions and returns None on failure.
Never propagates errors to callers.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_one, parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.core.llm import llm
from core.engine.graph.edge_writer import create_edge

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {
    "horizon_days",
    "expected_changes",
    "primary_risk",
    "leading_indicators",
    "falsification_condition",
}

_PROMPT = """\
You are a technical strategist. Given a decision and capability context, predict its consequences.

DECISION: {decision_content}

CAPABILITY CONTEXT:
{capability_context}

Predict the impact in observable, measurable terms only. Use capability slugs exactly as listed above.
No fuzzy metrics (user satisfaction, vision alignment). Every prediction must be falsifiable.

Return JSON only:
{{
  "horizon_days": <int 7-30 — when to evaluate this prediction>,
  "expected_changes": [
    {{
      "capability_id": "<capability slug from context above>",
      "score_delta": <float -1.0 to 1.0 — predicted quality score change>,
      "confidence": <float 0.0-1.0>
    }}
  ],
  "primary_risk": "<one falsifiable sentence — what could go wrong>",
  "leading_indicators": ["<observable signal that confirms the prediction>"],
  "falsification_condition": "<observable signal that would refute this prediction>"
}}"""


async def attach_prediction(
    decision_id: str,
    decision_content: str,
    product_id: str,
    archetype: str = "executor",
    discipline: str = "general",
    pool=None,
) -> dict | None:
    """Attach a forward prediction to a committed decision.

    Called immediately after create_decision. Non-blocking: any failure returns None
    without raising. The prediction is linked to the decision via a `predicts` edge.
    """
    if pool is None:
        pool = default_pool
    try:
        async with pool.connection() as db:
            cap_result = await db.query(
                """SELECT slug, description FROM capability
                   WHERE product = <record>$product
                     AND status IN ['built', 'partial', 'building', 'planned']
                   LIMIT 15""",
                {"product": product_id},
            )
        capabilities = parse_rows(cap_result)

        if capabilities:
            capability_context = "\n".join(
                f"- {c.get('slug', '?')}: {(c.get('description') or '')[:80]}" for c in capabilities
            )
        else:
            capability_context = "(no capabilities defined for this product yet)"

        raw = await llm.complete_json(
            _PROMPT.format(
                decision_content=decision_content[:600],
                capability_context=capability_context,
            ),
            model=settings.llm_budget_model,
        )

        if not _REQUIRED_FIELDS.issubset(raw):
            missing = _REQUIRED_FIELDS - set(raw)
            logger.warning("Forecaster: LLM response missing fields %s, skipping", missing)
            return None

        async with pool.connection() as db:
            result = await db.query(
                """CREATE decision_prediction SET
                    decision        = <record>$decision,
                    product         = <record>$product,
                    archetype       = $archetype,
                    discipline      = $discipline,
                    horizon_days    = $horizon_days,
                    expected_changes= $expected_changes,
                    primary_risk    = $primary_risk,
                    leading_indicators      = $leading_indicators,
                    falsification_condition = $falsification_condition,
                    closed          = false,
                    created_at      = time::now()
                """,
                {
                    "decision": decision_id,
                    "product": product_id,
                    "archetype": archetype,
                    "discipline": discipline,
                    "horizon_days": int(raw["horizon_days"]),
                    "expected_changes": raw["expected_changes"],
                    "primary_risk": str(raw["primary_risk"]),
                    "leading_indicators": list(raw.get("leading_indicators", [])),
                    "falsification_condition": str(raw["falsification_condition"]),
                },
            )
        prediction = parse_one(result)
        if not prediction:
            return None

        prediction_id = str(prediction["id"])
        await create_edge("predicts", prediction_id, decision_id, pool=pool)

        # Emit canvas event so the prediction tile materializes on the canvas.
        try:
            await _emit_prediction_attached_event(
                decision_id=decision_id,
                prediction_id=prediction_id,
                raw=raw,
                pool=pool,
            )
        except Exception:
            logger.warning("Failed to emit decision.prediction.attached event", exc_info=True)

        # Audit closure (decision:ukydw0t9zkb5hqh0i7d2): auto-snapshot at
        # prediction-create. The reconciler needs a baseline `capability_quality_snapshot`
        # row dated at or before the prediction's created_at — without it, the
        # per-capability calibration is silently skipped. Writing a snapshot
        # now guarantees the baseline always exists for capabilities that have
        # current quality data.
        await _snapshot_capability_baselines(
            prediction_id=prediction_id,
            expected_changes=raw["expected_changes"],
            product_id=product_id,
            pool=pool,
        )

        logger.info("Attached prediction %s to decision %s", prediction_id, decision_id)
        return prediction

    except Exception:
        logger.warning("attach_prediction failed for decision %s", decision_id, exc_info=True)
        return None


def _dominant_agent(perspectives: list[dict] | None, option_label: str = "") -> str:
    """Pick the agent who proposed the dominant option for prediction attribution.

    Heuristic (fallback chain):
    1. The perspective with the highest `confidence`.
    2. If tied, the first whose `contribution_summary` substring-matches `option_label`.
    3. The first perspective in the list.
    4. "ace" ghost sentinel if no perspectives recorded.
    """
    if not perspectives:
        return "ace"
    max_conf = max((p.get("confidence", 0.0) for p in perspectives), default=0.0)
    top = [p for p in perspectives if p.get("confidence", 0.0) == max_conf]
    if len(top) > 1 and option_label:
        for p in top:
            summary = (p.get("contribution_summary") or "").lower()
            if option_label.lower() in summary:
                return p.get("archetype", "ace")
    return top[0].get("archetype", "ace") if top else perspectives[0].get("archetype", "ace")


async def _emit_prediction_attached_event(
    decision_id: str,
    prediction_id: str,
    raw: dict,
    pool,
) -> None:
    """Emit decision.prediction.attached event for the canvas session that owns this decision.

    Best-effort: silently no-ops if the decision wasn't sourced from a canvas
    session (i.e., no canvas_session_id linkage).
    """
    async with pool.connection() as db:
        decision_row = parse_one(
            await db.query(
                "SELECT canvas_session_id, perspectives FROM <record>$d;",
                {"d": decision_id},
            )
        )
    if not decision_row:
        return
    canvas_session_id = decision_row.get("canvas_session_id")
    if not canvas_session_id:
        return  # non-canvas decision — no canvas to push to
    perspectives = decision_row.get("perspectives") or []
    agent_id = _dominant_agent(perspectives)

    expected_changes = raw.get("expected_changes") or []
    predicted_delta = 0.0
    if expected_changes:
        # Largest absolute delta wins
        deltas = [float(c.get("score_delta", 0.0)) for c in expected_changes]
        predicted_delta = max(deltas, key=abs)

    from core.engine.api.canvas import _persist_and_broadcast
    from core.engine.canvas.event_protocol import (
        EVENT_DECISION_PREDICTION_ATTACHED,
        DecisionPredictionAttachedPayload,
    )
    from core.engine.canvas.surface_adapter import CanvasSurfaceAdapter

    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)
    await adapter.emit(
        session_id=str(canvas_session_id),
        event_type=EVENT_DECISION_PREDICTION_ATTACHED,
        payload=DecisionPredictionAttachedPayload(
            decision_id=decision_id,
            prediction_id=prediction_id,
            agent_id=agent_id,
            predicted_delta=predicted_delta,
            falsifier=str(raw.get("falsification_condition", ""))[:200],
            horizon_days=int(raw.get("horizon_days", 0)),
        ),
    )


async def _snapshot_capability_baselines(
    prediction_id: str,
    expected_changes: list[dict],
    product_id: str,
    pool,
) -> None:
    """Write a capability_quality_snapshot row per capability in expected_changes.

    Closes audit finding decision:ukydw0t9zkb5hqh0i7d2 — auto-snapshot at
    prediction-create so the reconciler always has a baseline. Without this,
    predictions on never-snapshotted capabilities silently lose calibration
    signal (the cases that would teach the system fastest).

    Best-effort: never raises. Capabilities without current quality data are
    logged at WARNING; the prediction itself still succeeds.
    """
    if not expected_changes:
        return

    seen_slugs: set[str] = set()
    for change in expected_changes:
        cap_slug = change.get("capability_id")
        if not cap_slug or cap_slug in seen_slugs:
            continue
        seen_slugs.add(cap_slug)

        try:
            async with pool.connection() as db:
                # decision:8vj092dt6wklp60xqfat — `WHERE field = (SELECT VALUE ...)`
                # returns empty in SurrealDB v3 (subquery yields an array).
                # Slug+product is unique, so IN matches at most one capability.
                qa_result = await db.query(
                    """SELECT capability, dimension, score, confidence
                       FROM capability_quality
                       WHERE capability IN (
                           SELECT VALUE id FROM capability
                           WHERE slug = <string>$cap_slug AND product = <record>$product
                       )""",
                    {"cap_slug": cap_slug, "product": product_id},
                )
            qa_rows = parse_rows(qa_result)

            if not qa_rows:
                logger.warning(
                    "Snapshot baseline skipped: capability %s has no quality data yet "
                    "(prediction %s) — calibration will skip this capability at close-time",
                    cap_slug,
                    prediction_id,
                )
                continue

            async with pool.connection() as db:
                for qa in qa_rows:
                    await db.query(
                        """CREATE capability_quality_snapshot SET
                            capability  = $capability,
                            product     = <record>$product,
                            dimension   = $dimension,
                            score       = $score,
                            confidence  = $confidence,
                            gaps_count  = 0,
                            assessed_at = time::now()
                        """,
                        {
                            "capability": qa["capability"],
                            "product": product_id,
                            "dimension": qa.get("dimension", "overall"),
                            "score": float(qa.get("score", 0.5)),
                            "confidence": float(qa.get("confidence", 0.5)),
                        },
                    )
            logger.debug(
                "Snapshotted %d quality rows for capability %s (prediction %s)",
                len(qa_rows),
                cap_slug,
                prediction_id,
            )

        except Exception:
            logger.warning(
                "Snapshot baseline write failed for capability %s (prediction %s)",
                cap_slug,
                prediction_id,
                exc_info=True,
            )
