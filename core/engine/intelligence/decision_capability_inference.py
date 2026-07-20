# engine/intelligence/decision_capability_inference.py
"""Atomic-claim batch capability inference for decision rows.

This module powers both the bootstrap backfill script and the nightly sentinel.
Key feature: rows are claimed via atomic UPDATE-with-WHERE-IS-NONE BEFORE running
LLM inference, so two concurrent processes never double-pay for the same row.

decision:lv6stu70piemfwypde2e — Layer 5 data layer.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from core.engine.core.config import settings
from core.engine.core.db import parse_rows
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InferenceResult:
    """Result of a batch inference run."""

    inferred: int  # rows successfully inferred and written
    claimed_lost: int  # rows another process grabbed first
    errored: int  # rows where inference raised; written as empty-caps
    elapsed_ms: float


async def infer_capabilities_for_decisions(
    decision_rows: list[dict],
    pool,
    *,
    batch_size: int = 15,
) -> InferenceResult:
    """Batch-infer affected_capabilities for decision rows.

    Performs atomic claim + inference + commit. The function owns
    `affected_capabilities_inferred_at` mutation — callers never touch it.

    Per row:
      1. Atomic claim: `UPDATE decision SET inferred_at = time::now()
         WHERE id = <record>$rid AND inferred_at IS NONE RETURN BEFORE`.
         The RETURN BEFORE rows are the ones we actually won.
      2. Run LLM inference. Per-row failure isolation: a raising call
         logs WARNING and still commits empty-caps so the claimed row
         isn't stuck perpetually.
      3. Commit: `UPDATE <record>$id SET affected_capabilities = $caps,
         affected_capabilities_confidence = $conf`.

    Returns InferenceResult(inferred, claimed_lost, errored, elapsed_ms).
    """
    start = time.time()
    inferred_count = 0
    claimed_lost_count = 0
    errored_count = 0

    if not decision_rows:
        return InferenceResult(0, 0, 0, (time.time() - start) * 1000)

    batches = [decision_rows[i : i + batch_size] for i in range(0, len(decision_rows), batch_size)]

    async with pool.connection() as db:
        for batch in batches:
            # Step 1: claim each row individually (atomic, ~1ms each).
            # SurrealDB v3's WHERE-IN-with-record-IDs requires per-element
            # casting that's clunky; per-row UPDATE WHERE id=<record>$rid
            # is simpler and still fast.
            claimed: list[dict] = []
            for row in batch:
                rid = row["id"]
                try:
                    claim = await db.query(
                        """UPDATE decision SET affected_capabilities_inferred_at = time::now()
                           WHERE id = <record>$rid AND affected_capabilities_inferred_at IS NONE
                           RETURN BEFORE""",
                        {"rid": rid},
                    )
                    if parse_rows(claim):
                        claimed.append(row)
                    else:
                        claimed_lost_count += 1
                except Exception:
                    logger.warning("Atomic claim failed for %s", rid, exc_info=True)
                    claimed_lost_count += 1

            if not claimed:
                continue

            # Step 2: ONE LLM call per batch (per-row JSON output).
            # This is what the spec §6.6 batch_size=15 promised: ~$3-5 total
            # for the full backfill instead of 14k individual calls.
            try:
                results_by_id = await _infer_batch(claimed)
                errored_in_batch = False
            except Exception:
                logger.warning(
                    "LLM batch inference failed (%d rows) — falling back to empty caps",
                    len(claimed),
                    exc_info=True,
                )
                results_by_id = {row["id"]: ([], 0.0) for row in claimed}
                errored_in_batch = True

            # Step 3: commit per-row. Empty-caps on row-level miss (LLM omitted
            # the row from its response) so the row doesn't re-loop.
            for row in claimed:
                rid = row["id"]
                caps, conf = results_by_id.get(rid, ([], 0.0))
                try:
                    await db.query(
                        """UPDATE <record>$rid SET
                            affected_capabilities = $caps,
                            affected_capabilities_confidence = $conf""",
                        {"rid": rid, "caps": caps, "conf": conf},
                    )
                except Exception:
                    logger.warning("Result-commit failed for %s", rid, exc_info=True)
                    # Leave the claim in place; better than re-looping forever.

                if errored_in_batch or rid not in results_by_id:
                    errored_count += 1
                else:
                    inferred_count += 1

    return InferenceResult(
        inferred=inferred_count,
        claimed_lost=claimed_lost_count,
        errored=errored_count,
        elapsed_ms=(time.time() - start) * 1000,
    )


async def _infer_batch(rows: list[dict]) -> dict[str, tuple[list[str], float]]:
    """Run LLM inference for a batch of decision rows in ONE call.

    Sends all rows in a single prompt with a JSON-keyed response shape:
        {"<decision_id>": {"affected_capabilities": [...], "confidence": <float>}, ...}

    Returns a dict mapping decision_id → (caps, confidence). Rows missing from
    the LLM response are NOT included in the dict — callers detect missing
    rows and treat them as errored (empty-caps fallback).

    May raise — callers handle the all-rows-empty-caps fallback path.
    """
    if not rows:
        return {}

    # Build the prompt with one block per row. Truncate aggressively so a
    # batch of 15 stays well under the model context.
    blocks = []
    for row in rows:
        rid = row["id"]
        title = (row.get("title") or "")[:120]
        rationale = (row.get("rationale") or "")[:300]
        blocks.append(f"id: {rid}\ntitle: {title}\nrationale: {rationale}")
    decisions_block = "\n\n".join(blocks)

    prompt = (
        "For each decision below, identify which capability slugs (kebab-case, "
        "e.g. 'auth', 'session-management', 'rollout-planner') it primarily "
        "affects. Use existing slugs from typical product taxonomy; do not "
        "invent fanciful names.\n\n"
        "Return JSON only — an object keyed by decision id, with each value "
        "having 'affected_capabilities' (list of slugs) and 'confidence' "
        "(float 0.0-1.0). Include every decision id from the input.\n\n"
        "Example shape (with 2 decisions):\n"
        "{\n"
        '  "decision:abc": {"affected_capabilities": ["auth"], "confidence": 0.9},\n'
        '  "decision:def": {"affected_capabilities": ["scanner", "graph"], "confidence": 0.7}\n'
        "}\n\n"
        f"Decisions:\n{decisions_block}\n"
    )

    llm = get_llm()
    result = await llm.complete_json(prompt, model=settings.llm_budget_model)

    if not isinstance(result, dict):
        return {}

    out: dict[str, tuple[list[str], float]] = {}
    for rid, payload in result.items():
        if not isinstance(payload, dict):
            continue
        caps = payload.get("affected_capabilities", [])
        conf = payload.get("confidence", 0.0)

        if not isinstance(caps, list):
            caps = []
        caps = [str(c) for c in caps if c]

        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))

        out[str(rid)] = (caps, conf)

    return out
