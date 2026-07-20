"""Unified context loader — pulls from all 4 intelligence graph layers.

This module hosts two distinct loaders:

  load_full_context(...)      Legacy flat-dict loader used by the task record
                              snapshot. Untouched by the L5 work.

  load_decision_context(...)  Layer 5 tier-tagged decision-history loader
                              (decision:lv6stu70piemfwypde2e). Three concurrent
                              tiers (capability / discipline / recency), each
                              wrapped in an asyncio.wait_for deadline, with a
                              per-process circuit breaker. Returns a
                              TieredDecisionResult that exposes both the
                              decision list AND a degraded_tiers signal so
                              partial failure is observable.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


async def load_full_context(product_id: str, discipline: str = "") -> dict:
    """Load context from all 4 graph layers for prompt injection.

    Returns: {
        "decisions": [...],      # Recent PM decisions
        "initiatives": [...],    # Active/blocked initiatives
        "quality_gaps": [...],   # Capabilities with low quality scores
        "live_agents": int,      # Count of active agent sessions
    }
    """
    context = {
        "decisions": [],
        "initiatives": [],
        "quality_gaps": [],
        "live_agents": 0,
    }

    async with pool.connection() as db:
        # Recent decisions (last 10)
        try:
            result = await db.query(
                """SELECT title, decision_type, rationale, outcome, created_at
                   FROM decision
                   WHERE product = <record>$product
                   ORDER BY created_at DESC
                   LIMIT 10""",
                {"product": product_id},
            )
            context["decisions"] = parse_rows(result)
        except Exception as e:
            logger.debug(f"Failed to load decisions: {e}")

        # Active/blocked initiatives with progress
        try:
            result = await db.query(
                """SELECT title, status, description, priority, cost_used, cost_budget, created_at
                   FROM initiative
                   WHERE product = <record>$product AND status IN ['active', 'blocked', 'review', 'planning', 'ready']
                   ORDER BY created_at DESC
                   LIMIT 8""",
                {"product": product_id},
            )
            context["initiatives"] = parse_rows(result)
        except Exception as e:
            logger.debug(f"Failed to load initiatives: {e}")

        # Quality gaps — capabilities scoring below 0.5 in any discipline
        try:
            result = await db.query(
                """SELECT capability, dimension, score, gaps
                   FROM capability_quality
                   WHERE product = <record>$product AND score < 0.5
                   ORDER BY score ASC
                   LIMIT 10""",
                {"product": product_id},
            )
            context["quality_gaps"] = parse_rows(result)
        except Exception as e:
            logger.debug(f"Failed to load quality gaps: {e}")

        # Live agent count
        try:
            result = await db.query(
                """SELECT count() AS c FROM agent_execution
                   WHERE product = <record>$product AND status IN ['active', 'starting']
                   GROUP ALL""",
                {"product": product_id},
            )
            rows = parse_rows(result)
            context["live_agents"] = rows[0].get("c", 0) if rows else 0
        except Exception as e:
            logger.debug(f"Failed to load agent count: {e}")

    return context


# =============================================================================
# Layer 5 — tier-tagged decision-history loader
# =============================================================================
# decision:lv6stu70piemfwypde2e closes the gap where every engagement started
# cold despite the canvas decision ledger existing. Spec: docs/superpowers/
# specs/2026-05-14-layer5-context-assembly-design.md §5–§7.


_TierName = Literal["capability", "discipline", "recency"]


@dataclass(frozen=True)
class TieredDecision:
    """A single decision surfaced by the L5 loader, tagged with its tier."""

    decision_id: str
    title: str
    rationale: str
    decision_type: str
    discipline_hint: str | None
    affected_capabilities: list[str]
    created_at: datetime
    tier: _TierName
    relevance_score: float

    # Decision quality signals (review finding §1)
    # Matches the actual decision-table schema: ASSERT $value INSIDE
    # ['accepted', 'rejected', 'superseded', 'pending']. The spec originally
    # imagined 'success/failure/deferred' but those values aren't in the
    # schema — reconciled to the lifecycle the table actually models.
    outcome: Literal["accepted", "rejected", "superseded", "pending"] | None
    status: Literal["active", "archived"] | None

    # Epistemic provenance (review finding §2)
    # None  → row was human-authored; treat as ground truth
    # float → LLM-inferred; this is the inference model's reported confidence
    affected_capabilities_confidence: float | None


@dataclass(frozen=True)
class TieredDecisionResult:
    """Wrapper for load_decision_context() return.

    Keeps tier-failure visibility first-class (degraded_tiers) and surfaces
    cross-tier contradictions without changing the list type at consumer sites.
    """

    decisions: list[TieredDecision]
    degraded_tiers: frozenset[str]
    elapsed_ms: float
    contradictions: list[tuple[str, str, str]] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Module-level circuit-breaker state (per-process).
# Future-work in plan: migrate to SurrealDB when ACE goes multi-worker.
# -----------------------------------------------------------------------------
_tier_failure_times: dict[str, list[float]] = {
    "capability": [],
    "discipline": [],
    "recency": [],
}
_tier_suspended_until: dict[str, float] = {
    "capability": 0.0,
    "discipline": 0.0,
    "recency": 0.0,
}

# Consecutive-miss streak for layer5.no_capability_match (TODO-14 escalation).
_no_capability_match_streak: dict[str, int] = {}


def _record_tier_failure(tier: str) -> None:
    """Update circuit-breaker state on a tier failure.

    If the trailing window contains >= failure threshold, suspend the tier.
    """
    now = time.monotonic()
    window_seconds = settings.layer5_circuit_breaker_window_min * 60.0
    suspend_seconds = settings.layer5_circuit_breaker_suspend_min * 60.0

    # Trim old entries outside the window
    times = _tier_failure_times.get(tier, [])
    times = [t for t in times if (now - t) <= window_seconds]
    times.append(now)
    _tier_failure_times[tier] = times

    if len(times) >= settings.layer5_circuit_breaker_failures:
        _tier_suspended_until[tier] = now + suspend_seconds
        logger.warning(
            "layer5.tier_circuit_breaker_tripped tier=%s failures=%d window_min=%d suspended_for_min=%d",
            tier,
            len(times),
            settings.layer5_circuit_breaker_window_min,
            settings.layer5_circuit_breaker_suspend_min,
        )


def _is_tier_suspended(tier: str) -> bool:
    """Return True if the tier is currently in a circuit-breaker suspension."""
    return time.monotonic() < _tier_suspended_until.get(tier, 0.0)


def _reset_circuit_breaker_state() -> None:
    """Clear breaker state. For tests only."""
    for tier in ("capability", "discipline", "recency"):
        _tier_failure_times[tier] = []
        _tier_suspended_until[tier] = 0.0
    _no_capability_match_streak.clear()


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------


async def load_decision_context(
    task_description: str,
    classification: dict[str, Any],
    product_id: str,
    *,
    limit: int = 5,
    pool=None,
) -> TieredDecisionResult:
    """Layered decision-history loader for L5 context assembly.

    Three tiers (capability → discipline → recency) run concurrently via
    asyncio.gather, each wrapped in asyncio.wait_for with a per-tier deadline
    from settings. Returns a TieredDecisionResult — never raises.

    Tier failures (timeout, DB error, circuit-breaker suspension, cancellation)
    populate the .degraded_tiers set and the remaining tiers proceed.

    Empty results across all three tiers are valid: cold-start products simply
    return an empty list.
    """
    from core.engine.core.db import pool as default_pool

    start = time.time()
    if pool is None:
        pool = default_pool

    # Honor the feature flag — disabled mode short-circuits with an empty result.
    if settings.layer5_context_tiers == "disabled":
        return TieredDecisionResult(
            decisions=[],
            degraded_tiers=frozenset(),
            elapsed_ms=(time.time() - start) * 1000.0,
            contradictions=[],
        )

    cap_slugs = await _extract_candidate_capabilities(task_description, classification, product_id, pool)
    discipline = classification.get("discipline") or ""

    # In tier1_only mode, run only the capability tier — closes the prompt-bloat
    # path the kill-switch sentinel may flip to under token-cost pressure.
    if settings.layer5_context_tiers == "tier1_only":
        tier_coros = [
            _run_tier_with_deadline(
                "capability",
                settings.layer5_tier_timeout_capability_ms,
                _load_capability_tier,
                cap_slugs,
                product_id,
                limit,
                pool,
            ),
        ]
    else:
        tier_coros = [
            _run_tier_with_deadline(
                "capability",
                settings.layer5_tier_timeout_capability_ms,
                _load_capability_tier,
                cap_slugs,
                product_id,
                limit,
                pool,
            ),
            _run_tier_with_deadline(
                "discipline",
                settings.layer5_tier_timeout_discipline_ms,
                _load_discipline_tier,
                discipline,
                product_id,
                limit,
                pool,
            ),
            _run_tier_with_deadline(
                "recency",
                settings.layer5_tier_timeout_recency_ms,
                _load_recency_tier,
                product_id,
                limit,
                pool,
            ),
        ]

    tier_outcomes = await asyncio.gather(*tier_coros, return_exceptions=True)

    decisions: list[TieredDecision] = []
    degraded: set[str] = set()
    for outcome in tier_outcomes:
        if isinstance(outcome, BaseException):
            # _run_tier_with_deadline catches everything; reaching here means
            # gather itself surfaced a cancellation we couldn't suppress.
            logger.warning("layer5.gather_exception %r", outcome)
            continue
        tier_name, tier_decisions, tier_failed = outcome
        if tier_failed:
            degraded.add(tier_name)
        decisions.extend(tier_decisions)

    # Consecutive-miss escalation for capability tier (TODO-14).
    if cap_slugs and not any(d.tier == "capability" for d in decisions) and "capability" not in degraded:
        streak = _no_capability_match_streak.get(product_id, 0) + 1
        _no_capability_match_streak[product_id] = streak
        level = logging.WARNING if streak >= settings.layer5_circuit_breaker_failures else logging.DEBUG
        logger.log(
            level,
            "layer5.no_capability_match_streak product=%s streak=%d candidate_slugs=%s",
            product_id,
            streak,
            cap_slugs,
        )
    else:
        # Reset streak on successful capability match (or no candidate slugs at all).
        _no_capability_match_streak.pop(product_id, None)

    merged = _merge_and_dedupe(decisions, limit)
    contradictions = _detect_contradictions(merged)

    elapsed_ms = (time.time() - start) * 1000.0
    return TieredDecisionResult(
        decisions=merged,
        degraded_tiers=frozenset(degraded),
        elapsed_ms=elapsed_ms,
        contradictions=contradictions,
    )


# -----------------------------------------------------------------------------
# Tier execution with per-tier deadline + circuit breaker
# -----------------------------------------------------------------------------


async def _run_tier_with_deadline(
    tier_name: _TierName,
    timeout_ms: int,
    loader_fn,
    *args,
) -> tuple[str, list[TieredDecision], bool]:
    """Run a single tier loader with timeout + circuit-breaker handling.

    Returns (tier_name, decisions, failed_flag). Never raises; on any failure
    returns ([], True) for the tier and records a circuit-breaker event.
    """
    if _is_tier_suspended(tier_name):
        logger.debug("layer5.tier_suspended tier=%s — returning empty", tier_name)
        return (tier_name, [], True)

    try:
        decisions = await asyncio.wait_for(loader_fn(*args), timeout=timeout_ms / 1000.0)
        return (tier_name, decisions, False)
    except asyncio.TimeoutError:
        logger.warning("layer5.tier_timed_out tier=%s timeout_ms=%d", tier_name, timeout_ms)
        _record_tier_failure(tier_name)
        return (tier_name, [], True)
    except asyncio.CancelledError:
        logger.warning("layer5.tier_cancelled tier=%s", tier_name)
        _record_tier_failure(tier_name)
        return (tier_name, [], True)
    except Exception:
        logger.warning("layer5.tier_failed tier=%s", tier_name, exc_info=True)
        _record_tier_failure(tier_name)
        return (tier_name, [], True)


# -----------------------------------------------------------------------------
# Candidate capability extraction (feeds the capability tier query)
# -----------------------------------------------------------------------------


async def _extract_candidate_capabilities(
    task_description: str,
    classification: dict[str, Any],
    product_id: str,
    pool,
) -> list[str]:
    """Pull likely capability slugs for the task.

    Prefers the graph_classifier output if present (`classification.affected_capabilities`),
    falls back to a heuristic substring/slug match on `task_description` against
    the capability table.
    """
    pre_attached = classification.get("affected_capabilities")
    if isinstance(pre_attached, list) and pre_attached:
        # Already-attached caps from upstream classifier (graph-aware path).
        return [str(c) for c in pre_attached if c]

    # Heuristic fallback — fetch capability slugs for the product, find any
    # mentioned in the task description. Bounded by LIMIT 50 so the heuristic
    # is fast even on large capability catalogs.
    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT slug FROM capability
                   WHERE product = <record>$product
                   LIMIT 50""",
                {"product": product_id},
            )
        rows = parse_rows(result)
    except Exception:
        logger.debug("layer5.capability_heuristic_query_failed", exc_info=True)
        return []

    desc_lower = (task_description or "").lower()
    hits = [str(row["slug"]) for row in rows if row.get("slug") and str(row["slug"]).lower() in desc_lower]
    return hits[:10]


# -----------------------------------------------------------------------------
# Tier loaders — each shares three filter clauses (spec §6.1):
#   1. outcome ∈ {success, failure, deferred, accepted} (drops 'superseded')
#   2. affected_capabilities_confidence IS NONE OR >= $min_conf
#   3. affected_capabilities IS NOT NONE  (defensive against transient claim)
# -----------------------------------------------------------------------------


# Surfaces accepted / rejected / pending — the active-precedent values from
# the actual schema (ASSERT INSIDE ['accepted','rejected','superseded','pending']).
# 'superseded' is filtered out: replaced decisions aren't useful precedent.
#: The composite index (product, created_at), schema-defined since v097.
#:
#: Every tier query is `WHERE product = … ORDER BY created_at DESC LIMIT n`, and the
#: ORDER BY made SurrealDB's planner prefer `idx_decision_recency` — an index on
#: created_at ALONE — then filter each row by product as it walked. So each tier query
#: became a BACKWARD SCAN OF THE WHOLE `decision` TABLE, stopping only once it had
#: enough rows for the product it wanted.
#:
#: The cost is therefore INVERTED: the fewer decisions a product has, the more of the
#: table gets read. A product with none reads all of it and finds nothing. Measured on a
#: 17k-row table — discipline tier: 296ms on the main product (budget 80ms), 306ms on a
#: new one; recency: 28ms on the main product but 297ms on a new one (budget 50ms).
#:
#: So the discipline tier was timing out on the MAIN product on every call, and every
#: tier timed out for any new product — cold start, when a partner has least context and
#: can least afford to lose more. And it never failed loudly: a tier timeout is caught,
#: recorded in `degraded_tiers`, and the caller gets a plausible, quieter answer.
#:
#: This index serves the equality AND the ordering. It existed the whole time; the planner
#: simply never chose it. With the hint: 20-30ms across every tier and every product.
_TIER_INDEX = "idx_decision_product_created"

_OUTCOME_FILTER = " AND (outcome IS NONE OR outcome IN ['accepted','rejected','pending'])"
_CONFIDENCE_FILTER = " AND (affected_capabilities_confidence IS NONE OR affected_capabilities_confidence >= $min_conf)"
_CAPS_NOT_NONE_FILTER = " AND affected_capabilities IS NOT NONE"


async def _load_capability_tier(
    cap_slugs: list[str],
    product_id: str,
    limit: int,
    pool,
) -> list[TieredDecision]:
    """Decisions touching any of the candidate capabilities."""
    if not cap_slugs:
        return []
    async with pool.connection() as db:
        result = await db.query(
            "SELECT id, title, rationale, decision_type, discipline_hint, "
            "affected_capabilities, affected_capabilities_confidence, "
            "outcome, status, created_at FROM decision"
            f" WITH INDEX {_TIER_INDEX}"
            " WHERE product = <record>$product"
            " AND affected_capabilities CONTAINSANY $slugs"
            + _CAPS_NOT_NONE_FILTER
            + _OUTCOME_FILTER
            + _CONFIDENCE_FILTER
            + " ORDER BY created_at DESC LIMIT $lim",
            {
                "product": product_id,
                "slugs": cap_slugs,
                "min_conf": settings.layer5_min_confidence,
                "lim": limit,
            },
        )
    return [_row_to_tiered(row, "capability") for row in parse_rows(result)]


async def _load_discipline_tier(
    discipline: str,
    product_id: str,
    limit: int,
    pool,
) -> list[TieredDecision]:
    """Decisions tagged with the same discipline as the current task."""
    if not discipline:
        return []
    async with pool.connection() as db:
        result = await db.query(
            "SELECT id, title, rationale, decision_type, discipline_hint, "
            "affected_capabilities, affected_capabilities_confidence, "
            "outcome, status, created_at FROM decision"
            f" WITH INDEX {_TIER_INDEX}"
            " WHERE product = <record>$product"
            " AND discipline_hint = $discipline"
            + _OUTCOME_FILTER
            + _CONFIDENCE_FILTER
            + " ORDER BY created_at DESC LIMIT $lim",
            {
                "product": product_id,
                "discipline": discipline,
                "min_conf": settings.layer5_min_confidence,
                "lim": limit,
            },
        )
    return [_row_to_tiered(row, "discipline") for row in parse_rows(result)]


async def _load_recency_tier(
    product_id: str,
    limit: int,
    pool,
) -> list[TieredDecision]:
    """Plain recency: most recent N decisions on the product."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT id, title, rationale, decision_type, discipline_hint, "
            "affected_capabilities, affected_capabilities_confidence, "
            "outcome, status, created_at FROM decision"
            f" WITH INDEX {_TIER_INDEX}"
            " WHERE product = <record>$product"
            + _OUTCOME_FILTER
            + _CONFIDENCE_FILTER
            + " ORDER BY created_at DESC LIMIT $lim",
            {
                "product": product_id,
                "min_conf": settings.layer5_min_confidence,
                "lim": limit,
            },
        )
    return [_row_to_tiered(row, "recency") for row in parse_rows(result)]


# -----------------------------------------------------------------------------
# Row → TieredDecision conversion + relevance scoring
# -----------------------------------------------------------------------------


def _row_to_tiered(row: dict, tier: _TierName) -> TieredDecision:
    """Convert a raw decision row into a TieredDecision with computed score."""
    created_at = row.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = datetime.now(timezone.utc)
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    return TieredDecision(
        decision_id=str(row.get("id", "")),
        title=str(row.get("title") or ""),
        rationale=str(row.get("rationale") or ""),
        decision_type=str(row.get("decision_type") or ""),
        discipline_hint=row.get("discipline_hint"),
        affected_capabilities=list(row.get("affected_capabilities") or []),
        created_at=created_at,
        tier=tier,
        relevance_score=_compute_relevance_score(tier, created_at),
        outcome=row.get("outcome"),
        status=row.get("status"),
        affected_capabilities_confidence=row.get("affected_capabilities_confidence"),
    )


# Tier base values per spec §5.1. Gapped so a stale capability-tier decision
# (0.9) still outranks a fresh discipline-tier decision (0.6 + 0.1 = 0.7).
_TIER_BASE = {"capability": 0.9, "discipline": 0.6, "recency": 0.3}
_TIER_HALFLIFE_DAYS = {"capability": 7.0, "discipline": 14.0, "recency": 21.0}


def _compute_relevance_score(tier: _TierName, created_at: datetime) -> float:
    """Tier base + monotonic recency-decay bonus capped at 0.1."""
    base = _TIER_BASE.get(tier, 0.0)
    halflife = _TIER_HALFLIFE_DAYS.get(tier, 14.0)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 86400.0)
    bonus = 0.1 * math.pow(2.0, -age_days / halflife)
    return round(base + bonus, 4)


# -----------------------------------------------------------------------------
# Merge / dedupe / contradiction detection
# -----------------------------------------------------------------------------


_TIER_RANK = {"capability": 0, "discipline": 1, "recency": 2}


def _merge_and_dedupe(decisions: list[TieredDecision], limit: int) -> list[TieredDecision]:
    """Deterministic merge across tiers.

    Single decision in multiple tiers → capability tier wins. Sort key:
      (tier_rank, -relevance_score, -created_at_epoch)
    Caps at `limit`.
    """
    # Keep the highest-priority (lowest rank) entry per decision_id.
    by_id: dict[str, TieredDecision] = {}
    for d in decisions:
        prev = by_id.get(d.decision_id)
        if prev is None or _TIER_RANK[d.tier] < _TIER_RANK[prev.tier]:
            by_id[d.decision_id] = d

    deduped = list(by_id.values())
    deduped.sort(
        key=lambda d: (
            _TIER_RANK[d.tier],
            -d.relevance_score,
            -d.created_at.timestamp(),
        )
    )
    return deduped[:limit]


def _detect_contradictions(decisions: list[TieredDecision]) -> list[tuple[str, str, str]]:
    """Pairwise scan for opposing outcomes on a shared capability slug.

    v1 rule, reconciled with the actual decision-table schema
    (outcome ∈ {'accepted', 'rejected', 'superseded', 'pending'}): two
    decisions are contradictory iff they share at least one capability slug
    AND one has outcome='accepted' while the other has outcome='rejected'.

    The semantic: someone considered approach X for the capability and rejected
    it; someone else then accepted approach X (or vice versa). That's the
    contested-precedent signal the composer surfaces to the LLM. Returns
    (decision_a_id, decision_b_id, capability_slug) tuples. O(limit²) ≈ O(25).

    Superseded/pending are not contradictions: superseded means replaced (not
    contested), pending means not-yet-decided (not contested either).
    """
    out: list[tuple[str, str, str]] = []
    n = len(decisions)
    for i in range(n):
        a = decisions[i]
        if a.outcome not in ("accepted", "rejected"):
            continue
        for j in range(i + 1, n):
            b = decisions[j]
            if b.outcome not in ("accepted", "rejected"):
                continue
            if a.outcome == b.outcome:
                continue
            shared = set(a.affected_capabilities) & set(b.affected_capabilities)
            if not shared:
                continue
            slug = sorted(shared)[0]
            out.append((a.decision_id, b.decision_id, slug))
    return out
