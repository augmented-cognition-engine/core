# engine/intelligence/cascade_router.py
"""Cascade model routing — cheapest model that can do the job well.

Philosophy: Haiku tries first → low confidence escalates to Sonnet.
Higher models get the lower model's attempt as context (warm start, not cold start).
Opus is opt-in only — pass ceiling="opus" to CascadeRouter to unlock.

Every LLM call returns {"result": ..., "confidence": 0.0-1.0}.
Escalation thresholds are tunable per task type.

Anti-patterns:
- Don't escalate during bulk operations (Phase 3a). Accept noise, fix in synthesis.
- Always cascade: haiku → sonnet, never skip tiers.
- Track escalation rates. If >30% escalate, reassign the task to the higher model.
- Don't use Opus as a default ceiling — frameworks upskill Haiku/Sonnet more cheaply.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from surrealdb import RecordID

from core.engine.runtime.model_config import MODEL_TIERS, TASK_ROUTING, TIER_ORDER

logger = logging.getLogger(__name__)

# Alias for backward compat (callers that import MODEL_ROUTING directly)
MODEL_ROUTING = TASK_ROUTING

# ============================================================
# Escalation thresholds
# ============================================================

DEFAULT_THRESHOLDS = {
    "haiku_to_sonnet": 0.8,
    # sonnet_to_opus intentionally omitted — Opus is opt-in via ceiling="opus"
}

TASK_THRESHOLDS: dict[str, dict[str, float]] = {
    "routing": {"haiku_to_sonnet": 0.85},
    "context_summary": {"haiku_to_sonnet": 0.75},
    "verification_simple": {"haiku_to_sonnet": 0.9},
    # verification_complex starts at Sonnet (see TASK_ROUTING) — haiku_to_sonnet never fires
    "verification": {"haiku_to_sonnet": 0.9},
}

# ============================================================
# Cost profile (per MTok)
# ============================================================

MODEL_COSTS = {
    "haiku": {"input": 1.00, "output": 5.00},
    "sonnet": {"input": 3.00, "output": 15.00},
    "opus": {"input": 5.00, "output": 25.00},
}

# ============================================================
# Escalation tracking (for self-tuning)
# ============================================================

_escalation_counts: dict[str, dict[str, int]] = {}


def _track_escalation(task_type: str, from_tier: str, to_tier: str) -> None:
    """Record an escalation event for self-tuning.

    Increments only `escalated` — `total` is bumped exactly once per cascade call
    by the terminal _track_success (every cascade terminates on a success/ceiling/
    bulk path). So `total` counts cascade *calls* (tasks) and the escalation rate
    is the fraction of tasks that escalated — which is what the REASSIGN threshold
    (>0.3) means. (Incrementing total here too would double-count the denominator.)
    """
    _ = f"{from_tier}_to_{to_tier}"  # logged but not stored per-transition yet
    if task_type not in _escalation_counts:
        _escalation_counts[task_type] = {"total": 0, "escalated": 0}
    _escalation_counts[task_type]["escalated"] += 1


def _track_success(task_type: str) -> None:
    """Track non-escalated success."""
    if task_type not in _escalation_counts:
        _escalation_counts[task_type] = {"total": 0, "escalated": 0}
    _escalation_counts[task_type]["total"] += 1


def get_escalation_rates() -> dict[str, float]:
    """Get escalation rates per task type. >0.3 means consider reassignment."""
    rates = {}
    for task_type, counts in _escalation_counts.items():
        total = counts["total"]
        if total > 0:
            rates[task_type] = counts["escalated"] / total
    return rates


# ============================================================
# Durable escalation memory (routing_perf table)
#
# The in-process counts above reset every process. These two functions persist
# and re-seed them so the learned routing signal accumulates across restarts.
# route_model reads the aggregate via model_config.refresh_learned_routing, which
# queries the same routing_perf table — the two modules share a table, not an
# import, so there is no cycle (cascade_router already imports model_config).
# ============================================================


def _routing_perf_id(product_id: str, task_type: str) -> RecordID:
    """Deterministic per-(product, task_type) record id so repeated flushes overwrite."""
    slug = hashlib.md5(f"{product_id}|{task_type}".encode()).hexdigest()[:16]
    return RecordID("routing_perf", slug)


async def persist_escalation_counts(product_id: str, db=None) -> None:
    """Snapshot the in-process escalation counts to routing_perf (durable learning).

    One row per (product, task_type), keyed by a deterministic RecordID so repeated
    flushes overwrite rather than accumulate. Absolute SET (not increment): the
    in-process _escalation_counts is the authoritative running aggregate — it is
    seeded from this same table at startup via load_escalation_counts. Fail-safe:
    a flush failure must never disturb teardown, so this never raises.

    Single-process assumption: two processes that loaded the same snapshot and
    flush concurrently resolve last-writer-wins (no merge), so one session's
    observations can be lost. Fine for the CLI-first deployment; revisit (atomic
    per-call increments) if ACE ever runs multiple writers against one product.
    """
    if not _escalation_counts:
        return

    from core.engine.core.db import pool

    async def _flush(conn) -> None:
        for task_type, counts in list(_escalation_counts.items()):
            try:
                await conn.query(
                    """UPSERT $rid SET
                       product = <record>$product,
                       task_type = $task_type,
                       total = $total,
                       escalated = $escalated,
                       updated_at = time::now()""",
                    {
                        "rid": _routing_perf_id(product_id, task_type),
                        "product": product_id,
                        "task_type": task_type,
                        "total": int(counts.get("total", 0)),
                        "escalated": int(counts.get("escalated", 0)),
                    },
                )
            except Exception as exc:
                logger.warning("persist_escalation_counts row failed (%s): %s", task_type, exc)

    try:
        if db is not None:
            await _flush(db)
        else:
            async with pool.connection() as conn:
                await _flush(conn)
    except Exception as exc:
        logger.warning("persist_escalation_counts failed (non-fatal): %s", exc)


async def load_escalation_counts(product_id: str, db=None) -> int:
    """Seed the in-process escalation counts from routing_perf at startup.

    Lets the learning loop accumulate across process restarts (a fresh CLI run
    would otherwise start from zero and never reach the sample floor). Seeds only
    task types not already present in-process, so a re-entrant call never clobbers
    live observations. Returns the number of task types loaded. Fail-safe: returns
    0 on any error.
    """
    from core.engine.core.db import parse_rows, pool

    async def _read(conn) -> list[dict]:
        return parse_rows(
            await conn.query(
                "SELECT task_type, total, escalated FROM routing_perf WHERE product = <record>$product",
                {"product": product_id},
            )
        )

    try:
        rows = await _read(db) if db is not None else None
        if rows is None:
            async with pool.connection() as conn:
                rows = await _read(conn)

        loaded = 0
        for row in rows:
            task_type = row.get("task_type")
            if not task_type or task_type in _escalation_counts:
                continue
            _escalation_counts[task_type] = {
                "total": int(row.get("total") or 0),
                "escalated": int(row.get("escalated") or 0),
            }
            loaded += 1
        return loaded
    except Exception as exc:
        logger.warning("load_escalation_counts failed (non-fatal): %s", exc)
        return 0


# ============================================================
# Static routing — delegates to model_config (single source of truth)
# ============================================================

from core.engine.runtime.model_config import route_model  # noqa: F401, E402

# ============================================================
# Cascade Router
# ============================================================


def _get_threshold(task_type: str, transition: str) -> float:
    """Get escalation threshold for a task type."""
    overrides = TASK_THRESHOLDS.get(task_type, {})
    return overrides.get(transition, DEFAULT_THRESHOLDS.get(transition, 0.8))


def _next_tier(current: str) -> str | None:
    """Get the next tier up. Returns None if at ceiling."""
    idx = TIER_ORDER.index(current) if current in TIER_ORDER else -1
    if idx < 0 or idx >= len(TIER_ORDER) - 1:
        return None
    return TIER_ORDER[idx + 1]


def resolve_start_tier(task_type: str, classification: dict | None, ceiling: str) -> str:
    """Starting tier for a cascade: static table → classifier bump → learned up-route → ceiling cap.

    Distinct from route_model: the cascade deliberately keeps strong classifier
    signals at sonnet (not opus) so it can escalate sonnet→opus at runtime on low
    confidence rather than paying for opus upfront. The learned up-route is shared —
    task types that chronically escalate start one tier higher (model_config owns the
    learned cache; we reuse its bump helper, no new dependency since cascade_router
    already imports model_config).
    """
    from core.engine.runtime.model_config import _learned_tier_bump

    starting_tier = TASK_ROUTING.get(task_type, "sonnet")

    # Classifier override — bump tier based on signals (capped at sonnet here)
    if classification:
        opus_signals = sum(
            1
            for key, value in [("complexity", "complex"), ("archetype", "researcher"), ("mode", "exploratory")]
            if classification.get(key) == value
        )
        if opus_signals >= 2:
            starting_tier = "sonnet"  # strong signals → sonnet; Opus requires ceiling="opus"
        elif opus_signals == 1 and starting_tier == "haiku":
            starting_tier = "sonnet"

    # Learned up-route — start chronically-escalating task types one tier higher.
    starting_tier = _learned_tier_bump(task_type, starting_tier)

    # Cap at ceiling
    ceiling_idx = TIER_ORDER.index(ceiling) if ceiling in TIER_ORDER else len(TIER_ORDER) - 1
    tier_idx = TIER_ORDER.index(starting_tier) if starting_tier in TIER_ORDER else 1
    if tier_idx > ceiling_idx:
        starting_tier = TIER_ORDER[ceiling_idx]

    return starting_tier


class CascadeRouter:
    """Cascade model routing with confidence-based escalation.

    Default ceiling is "sonnet" — Haiku tries first, escalates to Sonnet on low
    confidence. Opus is opt-in: pass ceiling="opus" explicitly to unlock.

    Usage:
        router = CascadeRouter()                   # ceiling=sonnet (default)
        router = CascadeRouter(ceiling="opus")     # opt-in to Opus escalation
        result = await router.call(
            task_type="code_analysis",
            prompt="Analyze this file...",
        )
        # result = {"result": {...}, "confidence": 0.92, "model_used": "haiku", "escalated": False}
    """

    def __init__(self, ceiling: str = "sonnet") -> None:
        self._ceiling = ceiling

    async def call(
        self,
        task_type: str,
        prompt: str,
        system: str = 'Return JSON with a confidence field: {"result": {...}, "confidence": 0.0-1.0}',
        classification: dict | None = None,
        bulk_mode: bool = False,
    ) -> dict[str, Any]:
        """Route a task through the cascade.

        Args:
            task_type: Task type key from MODEL_ROUTING
            prompt: The prompt to send
            system: System prompt (should ask for confidence)
            classification: Optional classifier output for override
            bulk_mode: If True, skip escalation (accept noise, fix in synthesis)

        Returns:
            {"result": ..., "confidence": float, "model_used": str, "escalated": bool, "tiers_used": [str]}
        """
        # Starting tier: static table → classifier bump → learned up-route → ceiling cap.
        starting_tier = resolve_start_tier(task_type, classification, self._ceiling)
        ceiling_idx = TIER_ORDER.index(self._ceiling)

        current_tier = starting_tier
        previous_attempt: dict | None = None
        tiers_used = []

        while current_tier is not None:
            model = MODEL_TIERS[current_tier]
            tiers_used.append(current_tier)

            # Build prompt — include previous attempt if escalating
            full_prompt = prompt
            if previous_attempt:
                prev_tier = tiers_used[-2] if len(tiers_used) >= 2 else "lower"
                full_prompt = (
                    f"A {prev_tier}-tier model analyzed this and returned:\n"
                    f"```json\n{json.dumps(previous_attempt.get('result', {}), indent=2)}\n```\n"
                    f"Confidence: {previous_attempt.get('confidence', 0)}\n\n"
                    f"Do you agree with this analysis? If so, return it with higher confidence. "
                    f"If not, provide a better analysis.\n\n"
                    f"Original task:\n{prompt}"
                )

            # Call the model
            try:
                from core.engine.core.llm import get_llm

                llm = get_llm()
                raw = await llm.complete_json(
                    f"{system}\n\n{full_prompt}",
                    model=model,
                )

                # Extract confidence
                confidence = float(raw.get("confidence", 0.5))
                result = raw.get("result", raw)

                # Remove confidence from result if it leaked in
                if isinstance(result, dict):
                    result.pop("confidence", None)

            except Exception as exc:
                logger.warning("Cascade %s on %s failed: %s", current_tier, task_type, exc)
                confidence = 0.0
                result = {"error": str(exc)}

            # Check if we should escalate
            if bulk_mode:
                # Bulk mode: accept whatever we get, don't escalate
                _track_success(task_type)
                return {
                    "result": result,
                    "confidence": confidence,
                    "model_used": model,
                    "tier": current_tier,
                    "escalated": len(tiers_used) > 1,
                    "tiers_used": tiers_used,
                }

            next_tier = _next_tier(current_tier)
            if next_tier is None or TIER_ORDER.index(next_tier) > ceiling_idx:
                # At ceiling — accept result
                _track_success(task_type)
                return {
                    "result": result,
                    "confidence": confidence,
                    "model_used": model,
                    "tier": current_tier,
                    "escalated": len(tiers_used) > 1,
                    "tiers_used": tiers_used,
                }

            # Check threshold
            threshold_key = f"{current_tier}_to_{next_tier}"
            threshold = _get_threshold(task_type, threshold_key)

            if confidence >= threshold:
                # Confident enough — accept
                _track_success(task_type)
                return {
                    "result": result,
                    "confidence": confidence,
                    "model_used": model,
                    "tier": current_tier,
                    "escalated": len(tiers_used) > 1,
                    "tiers_used": tiers_used,
                }

            # Escalate
            logger.info(
                "Cascade: %s on %s got confidence %.2f < threshold %.2f → escalating to %s",
                current_tier,
                task_type,
                confidence,
                threshold,
                next_tier,
            )
            _track_escalation(task_type, current_tier, next_tier)
            previous_attempt = {"result": result, "confidence": confidence}
            current_tier = next_tier

        # Should not reach here
        return {
            "result": result,
            "confidence": confidence,
            "model_used": model,
            "tier": current_tier,
            "escalated": True,
            "tiers_used": tiers_used,
        }
