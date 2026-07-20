"""Bridge canvas decisions into the existing decision ledger (§A4).

NO NEW DECISION TABLE. Canvas decisions land in the same `decision` table
as CLI- and MCP-captured decisions, written via the canonical
`engine.product.decisions.create_decision` function. After creation, this
bridge UPDATEs the new record to attach `canvas_session_id` (the existing
`source_session` field is typed to `chat_session` and cannot hold a
`canvas_session` record).

HARD IMPORT (no try/except). If `create_decision` moves or is renamed,
this module fails to import and the failure is visible at boot — that's
the desired loud-fail behavior. Silent fallback (the previous draft) is
exactly the §A4 violation pattern this plan refuses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from core.engine.core.db import pool
from core.engine.product.decisions import create_decision  # canonical — verified Pre-flight P4

logger = logging.getLogger(__name__)


async def bridge_decision_to_ledger(
    session_id: str,
    product_id: str,
    title: str,
    rationale: str,
    cited_artifact_ids: list[str],
    framework_kind: Optional[str] = None,
    perspectives: Optional[list[dict]] = None,
    frameworks_used: Optional[list[str]] = None,
) -> str:
    """Persist a canvas decision via the canonical pipeline + canvas linkage.

    Parameters
    ----------
    session_id : record id of the canvas_session this decision originated in
    product_id : record id of the product (= ACE's name for "project")
    title, rationale : human-readable
    cited_artifact_ids : list of canvas_artifact record ids that informed this decision
    framework_kind : "trade_off_matrix" | None (for v1 only matrix is wired)
    perspectives : optional list of {archetype, contribution_summary, confidence}
      dicts captured from the most recent agent.perspective.end events. Used
      by the Decision Ledger to render lineage.
    frameworks_used : optional list of framework slugs used to shape this
      decision (e.g. ["trade_off_matrix"]).
    """
    # frameworks_used defaults to [framework_kind] when only the single kind
    # is known; explicit caller-provided list overrides.
    effective_frameworks = (
        frameworks_used if frameworks_used is not None else ([framework_kind] if framework_kind else [])
    )
    decision_record = await create_decision(
        title=title,
        decision_type="direction",  # canvas decisions are direction-class for v1
        rationale=rationale,
        product_id=product_id,
        source="canvas",
        perspectives=perspectives or [],
        frameworks_used=effective_frameworks,
        # source_session NOT used: typed option<record<chat_session>>, cannot hold canvas_session.
        # canvas_session_id attached below via UPDATE instead.
    )
    decision_id = str(decision_record["id"])

    # Attach canvas-specific linkage. Both `surface` and `canvas_session_id` are
    # DEFINE FIELD'd on `decision` in v103 (per feedback_surrealdb_schemaless_drift.md
    # — bare SCHEMALESS would silently drop these because v040 already DEFINEs other fields).
    #
    # NOTE: `cited_artifact_ids` is retained here as a readable, DEPRECATED index —
    # the `grounds` edge written below is now the source of truth for node<->canvas
    # grounding (v136). Prefer deriving citations via grounding.grounded_in(decision)
    # over reading this array; it is kept only so existing readers do not break.
    async with pool.connection() as db:
        await db.query(
            f"UPDATE {decision_id} SET "
            f"surface = 'canvas', "
            f"canvas_session_id = <record>$sid, "
            f"cited_artifact_ids = $cids, "
            f"framework_kind = $fk;",
            {
                "sid": session_id,
                "cids": cited_artifact_ids,
                "fk": framework_kind,
            },
        )

    # Ground the decision in the canvas artifacts it cites. This `grounds` edge is
    # the authoritative store (the array above is a compat index); grounding is
    # idempotent, so a re-bridge refreshes rather than duplicates. A non-canvas id
    # in the legacy list is skipped, never fatal to decision capture.
    from core.engine.graph.grounding import ground

    for aid in cited_artifact_ids:
        try:
            await ground(decision_id, aid, role="about", pool=pool)
        except ValueError:
            logger.debug("Skipping non-canvas citation %s on decision %s", aid, decision_id)
        except Exception:
            # Best-effort: the decision and its cited_artifact_ids array are already
            # persisted, so a transient edge-write failure must not fail the capture.
            logger.warning("grounds edge write failed for %s on decision %s", aid, decision_id, exc_info=True)

    # Fire prediction attachment as a background task — never blocks the API response.
    # attach_prediction makes one LLM call (~1-3s); the canvas frontend polls for it
    # after the decision_id is returned.
    async def _attach():
        try:
            from core.engine.foresight.forecaster import attach_prediction

            await attach_prediction(
                decision_id=decision_id,
                decision_content=rationale,
                product_id=product_id,
            )
        except Exception:
            logger.warning("Background attach_prediction failed for decision %s", decision_id, exc_info=True)

    asyncio.ensure_future(_attach())

    return decision_id
