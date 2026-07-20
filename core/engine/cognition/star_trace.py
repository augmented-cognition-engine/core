# engine/cognition/star_trace.py
"""STaR trace helpers — write/load successful reasoning traces.

After VerificationGate returns verdict="clean", executor.py calls write_star_trace()
to persist the full phase trace as a reusable cognitive artifact.

On future tasks of the same discipline, loader.py calls load_star_traces() to
retrieve top-N traces and inject them as "Proven Reasoning Patterns" context.

STaR = Self-Taught Reasoner (Zelikman et al. 2022).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 3


async def write_star_trace(
    pool,
    product_id: str,
    discipline: str,
    task_description: str,
    phase_traces: list[dict],
    final_output: str,
) -> None:
    """Write a successful reasoning trace to star_trace table. Non-fatal."""
    try:
        async with pool.connection() as db:
            await db.query(
                "CREATE star_trace CONTENT $data",
                {
                    "data": {
                        "product": product_id,
                        "discipline": discipline,
                        "task_description": task_description[:300],
                        "phase_traces": phase_traces,
                        "final_output": final_output[:500],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
    except Exception as exc:
        logger.warning("write_star_trace failed (non-fatal): %s", exc)


async def load_star_traces(
    pool,
    product_id: str,
    discipline: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict]:
    """Load the most recent successful traces for this discipline. Returns [] on error."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT task_description, phase_traces, final_output, created_at
                   FROM star_trace
                   WHERE product = $product AND discipline = $discipline
                   ORDER BY created_at DESC
                   LIMIT $limit""",
                {"product": product_id, "discipline": discipline, "limit": limit},
            )
        from core.engine.core.db import parse_rows

        return parse_rows(result)
    except Exception as exc:
        logger.warning("load_star_traces failed (non-fatal): %s", exc)
        return []
