"""Detects top-rec swaps and material score shifts; emits canvas.recommendation.shifted.

v2 additions:
- On swap: also emits canvas.recommendation.resolved for the displaced top-1's topic.
- On new top-1 with a resolved voice_thread (changed within 14d): emits canvas.recommendation.reopened.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.engine.core.db import parse_rows, pool
from core.engine.events.bus import bus
from core.engine.product.strategic_prioritizer import StrategicPrioritizer
from core.engine.voice.thread import read_voice_thread

logger = logging.getLogger(__name__)

_SCORE_SHIFT_THRESHOLD = 0.05
_REOPEN_WINDOW_DAYS = 14


def is_score_shift(prev: float, new: float) -> bool:
    return abs(new - prev) > _SCORE_SHIFT_THRESHOLD


async def on_score_changed(event_type: str, payload: dict) -> None:
    if event_type != "canvas.score.changed":
        return
    product_id = payload.get("product_id")
    if not product_id:
        return
    await _maybe_emit_shift(product_id)


async def _maybe_emit_shift(product_id: str) -> None:
    p = StrategicPrioritizer(pool)
    try:
        ranked = await p.prioritize(product_id)
    except Exception as exc:
        logger.debug("recommendation_shift_detector: prioritize failed: %s", exc)
        return
    if not ranked:
        return
    top = ranked[0]
    new_pillar = top.get("pillar", "")
    new_discipline = top.get("discipline") or top.get("dimension", "")
    new_score = float(top.get("rank") or top.get("priority_score", 0.0))
    new_topic = f"rec:{new_pillar}.{new_discipline}"

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM voice_top_recommendation_state WHERE product = <record>$pid LIMIT 1",
                {"pid": product_id},
            )
        )
        if rows:
            prev = rows[0]
            prev_pillar = prev.get("top_pillar", "")
            prev_discipline = prev.get("top_discipline", "")
            prev_score = float(prev.get("top_rank_score", 0.0))
            swap = (new_pillar, new_discipline) != (prev_pillar, prev_discipline)
            shift = is_score_shift(prev_score, new_score)
            if swap or shift:
                await bus.emit(
                    "canvas.recommendation.shifted",
                    {
                        "product_id": product_id,
                        "top_pillar": new_pillar,
                        "top_discipline": new_discipline,
                        "top_rank_score": new_score,
                        "swap": swap,
                        "rec": top,
                    },
                )

            # G1: On swap, emit resolved for the displaced old top-1
            if swap:
                await bus.emit(
                    "canvas.recommendation.resolved",
                    {
                        "product_id": product_id,
                        "top_pillar": prev_pillar,
                        "top_discipline": prev_discipline,
                        "reason": "displaced_by_swap",
                    },
                )

        # G2: Check if new top-1's thread was recently resolved → reopened
        try:
            thread = await read_voice_thread(product_id, new_topic)
            if thread and thread.status == "resolved":
                days_since_resolved = (datetime.now(timezone.utc) - thread.last_state_changed_at).days
                if days_since_resolved <= _REOPEN_WINDOW_DAYS:
                    await bus.emit(
                        "canvas.recommendation.reopened",
                        {
                            "product_id": product_id,
                            "top_pillar": new_pillar,
                            "top_discipline": new_discipline,
                            "top_rank_score": new_score,
                            "rec": top,
                            "days_since_resolved": days_since_resolved,
                        },
                    )
        except Exception as exc:
            logger.debug("recommendation_shift_detector: reopened check failed: %s", exc)

        # Always upsert persisted state
        await db.query(
            """UPSERT voice_top_recommendation_state CONTENT {
                product: <record>$pid,
                top_pillar: <string>$pillar,
                top_discipline: <string>$discipline,
                top_rank_score: <float>$score,
                updated_at: time::now()
            } WHERE product = <record>$pid""",
            {"pid": product_id, "pillar": new_pillar, "discipline": new_discipline, "score": new_score},
        )


def register_recommendation_shift_detector() -> None:
    bus.on("canvas.score.changed", on_score_changed)
