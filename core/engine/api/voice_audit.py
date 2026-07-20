"""Voice audit API — /portal/voice-audit/{product_id}."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from core.engine.api._portal_security import enforce_run_cooldown, verify_product_access
from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.voice.audit import VOICE_AUDIT_AMBIENT_THRESHOLD, VOICE_AUDIT_TEASER_THRESHOLD
from core.engine.voice.audit_runner import run_audit

router = APIRouter(prefix="/portal/voice-audit", tags=["voice-audit"])

_SINCE_TO_INTERVAL = {"day": "1d", "week": "7d", "month": "30d"}


@router.get("/{product_id}")
async def get_voice_audit(
    product_id: str,
    since: Literal["day", "week", "month"] = "week",
    user=Depends(verify_product_access),
) -> dict:
    # FastAPI 422s any since value not in the Literal set; the dict lookup is
    # therefore guaranteed to hit. The interval string is interpolated into the
    # SQL below — restricting the input domain at the type level closes the
    # injection surface that would otherwise depend on the dict-fallback path.
    interval = _SINCE_TO_INTERVAL[since]
    async with pool.connection() as db:
        latest = parse_one(
            await db.query(
                "SELECT * FROM voice_audit_run WHERE product = <record>$pid ORDER BY ran_at DESC LIMIT 1",
                {"pid": product_id},
            )
        )
        history = parse_rows(
            await db.query(
                f"SELECT ran_at, overall_score FROM voice_audit_run "
                f"WHERE product = <record>$pid AND ran_at > time::now() - {interval} "
                "ORDER BY ran_at ASC",
                {"pid": product_id},
            )
        )
    return {
        "latest": latest,
        "history": history,
        "thresholds": {
            "ambient": VOICE_AUDIT_AMBIENT_THRESHOLD,
            "teaser": VOICE_AUDIT_TEASER_THRESHOLD,
        },
    }


@router.post("/{product_id}/run")
async def run_voice_audit_now(product_id: str, user=Depends(verify_product_access)) -> dict:
    # Cooldown: 30s per product. Prevents accidental or malicious spam of the
    # real-compute audit run + persistence path. 429 on too-soon retry, with
    # Retry-After header so clients can back off properly.
    enforce_run_cooldown("voice_audit_run", product_id, min_seconds=30)
    return await run_audit(pool, product_id, trigger="manual", persist=True)
