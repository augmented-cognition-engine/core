"""build_spec — the activation keystone. Turn a roadmap spec into a real arm build:
compose a Solution(spec_id) from the spec and dispatch it. build_spec owns the
building/approved status transitions; capture_outcome owns built-on-success."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_rows
from core.engine.core.db import pool as default_pool

logger = logging.getLogger(__name__)


async def build_spec(spec_id, product_id="product:platform", pool=None) -> dict:
    """Human-triggered: build a spec via an arm (→ review lane). Never raises."""
    pool = pool or default_pool
    try:
        sid = parse_record_id(spec_id)
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT objective, status FROM agent_spec WHERE id = $s", {"s": sid}))
        if not rows:
            return {"built": False, "reason": "spec not found"}
        objective = rows[0].get("objective") or ""
        prior = rows[0].get("status")
        if prior == "shipped":
            return {"built": False, "reason": "already shipped"}
        if prior == "building":
            return {"built": False, "reason": "already building"}
        if prior == "built":
            return {"built": False, "reason": "awaiting review — promote or reject it first"}

        async with pool.connection() as db:
            # Stamp WHEN it went building. Without it, reconcile_stranded_specs cannot tell "this
            # process crashed an hour ago" from "this build started three milliseconds ago", and
            # releasing the wrong one hands the same work to a second builder.
            await db.query("UPDATE $s SET status='building', updated_at=time::now()", {"s": sid})

        from core.engine.arms.dispatch import dispatch_solution
        from core.engine.solution import Solution

        sol = Solution(intent=objective, spec_id=spec_id, domain_hint=None)
        result = await dispatch_solution(sol, product_id=product_id)

        if result is None:
            async with pool.connection() as db:
                await db.query("UPDATE $s SET status=$st", {"s": sid, "st": prior})
            return {"built": False, "reason": "no arm can build this spec yet"}

        _domain, armresult, verdict = result
        if verdict.passed:
            branch = getattr(getattr(armresult, "workspace", None), "branch", None)
            return {"built": True, "branch": branch, "reason": "built — in review"}

        if getattr(verdict, "parked", False):
            # PARKED: the environment broke; the work was never judged. Do NOT return the spec to
            # 'approved' — that is the buildable queue, and an unattended session would pick it
            # straight back up, park again on the same dead model, requeue, forever. BLOCKED takes
            # it out of the queue and puts it in front of a human, which is the honest state.
            async with pool.connection() as db:
                await db.query("UPDATE $s SET status=$st", {"s": sid, "st": "blocked"})
            return {
                "built": False,
                "parked": True,
                "reason": verdict.reason or "environment failure",
                "diagnosis": getattr(verdict, "diagnosis", "") or verdict.reason,
            }

        # A genuine failure IS retryable — the spec goes back in the queue.
        async with pool.connection() as db:
            await db.query("UPDATE $s SET status=$st", {"s": sid, "st": "approved"})
        return {"built": False, "reason": verdict.reason or "build failed"}
    except Exception as exc:
        logger.warning("build_spec failed (non-fatal): %s", exc)
        return {"built": False, "reason": str(exc)}
