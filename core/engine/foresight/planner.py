# engine/foresight/planner.py
"""Depth-3 MCTS-lite rollout planner for the Foresight Engine.

One batched LLM call generates 3 decision paths; each terminal state is scored
by score_hypothetical_state. Results cached in rollout_cache with 4hr TTL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.engine.core.config import settings
from core.engine.core.db import parse_rows
from core.engine.core.db import pool as default_pool
from core.engine.core.llm import llm
from core.engine.foresight.models import RolloutBranch, RolloutResult
from core.engine.foresight.value_model import score_hypothetical_state

logger = logging.getLogger(__name__)

_PROMPT = """\
You are a technical planner. Given a candidate decision and the current capability landscape, \
predict 3 distinct decision paths this initiative likely forces.

CANDIDATE: {candidate}

CURRENT CAPABILITIES (slug: current_score):
{capability_context}

For each branch predict:
- path: the candidate decision followed by the 2 most likely decisions it forces, in order
- score_deltas: predicted quality score change per capability slug (delta from current, range -0.5 to +0.5)
- top_risk: one falsifiable sentence describing the primary risk for this path

Return JSON only, no commentary:
{{
  "branches": [
    {{
      "path": ["{candidate}", "<forced decision 1>", "<forced decision 2>"],
      "score_deltas": {{"<slug>": <float delta>, ...}},
      "top_risk": "<one sentence>"
    }},
    {{
      "path": ["{candidate}", "<forced decision 1 alt>", "<forced decision 2 alt>"],
      "score_deltas": {{"<slug>": <float delta>, ...}},
      "top_risk": "<one sentence>"
    }},
    {{
      "path": ["{candidate}", "<forced decision 1 alt2>", "<forced decision 2 alt2>"],
      "score_deltas": {{"<slug>": <float delta>, ...}},
      "top_risk": "<one sentence>"
    }}
  ]
}}

Generate exactly 3 branches with distinct strategic emphases."""


def _assign_branch_authorship(branches: list[RolloutBranch]) -> None:
    """Assign authoring archetype to each branch based on its terminal score + risk profile.

    Heuristic — in-place mutation:
    - Highest terminal_score → 'pm' (the optimist / capability-builder).
    - Highest risk (longest top_risk) → 'skeptic' (the worrier).
    - Smallest delta from zero (most incremental) → 'technical_architect' (the conservative).
    - Remaining branches cycle through advisor/sentinel for variety.

    The aim is distinct authorship across the three branches so the picker UI
    shows three different agent chips.
    """
    if not branches:
        return
    fallbacks = ["advisor", "sentinel", "creator", "executor"]
    fb_idx = 0
    assigned: set[int] = set()

    # 1) PM gets highest terminal_score
    pm_idx = max(range(len(branches)), key=lambda i: branches[i].terminal_score)
    branches[pm_idx].authored_by_archetype = "pm"
    assigned.add(pm_idx)

    # 2) Skeptic gets longest top_risk string among remaining
    remaining = [i for i in range(len(branches)) if i not in assigned]
    if remaining:
        sk_idx = max(remaining, key=lambda i: len(branches[i].top_risk or ""))
        branches[sk_idx].authored_by_archetype = "skeptic"
        assigned.add(sk_idx)

    # 3) Technical architect gets the most incremental (smallest sum of |overrides|)
    remaining = [i for i in range(len(branches)) if i not in assigned]
    if remaining:
        ta_idx = min(
            remaining,
            key=lambda i: sum(abs(v - 0.5) for v in branches[i].state_override.values()),
        )
        branches[ta_idx].authored_by_archetype = "technical_architect"
        assigned.add(ta_idx)

    # 4) Anything left → cycle fallbacks
    for i in range(len(branches)):
        if i in assigned:
            continue
        branches[i].authored_by_archetype = fallbacks[fb_idx % len(fallbacks)]
        fb_idx += 1


async def plan_rollout(
    candidate_decision: str,
    product_id: str,
    depth: int = 3,
    pool=None,
) -> RolloutResult:
    """Generate a rollout tree for a candidate decision.

    Args:
        candidate_decision: The decision text to roll out (initiative title or free text).
        product_id: SurrealDB record ID string (e.g. "product:platform").
        depth: Controls branch depth. depth=0 returns a single-node result with no LLM call.
               depth>0 triggers a batched LLM call generating 3 paths of (depth-1) forced decisions.
               Hard cap: depth is treated as 3 if greater (trajectory variance exceeds signal beyond depth 3).
        pool: SurrealDB connection pool. Defaults to module-level pool.

    Returns:
        RolloutResult with up to 3 scored branches and the best_path.
    """
    if pool is None:
        pool = default_pool

    cached = await _check_cache(candidate_decision, product_id, pool)
    if cached is not None:
        return cached

    if depth == 0:
        now = datetime.now(timezone.utc).isoformat()
        placeholder = RolloutBranch(
            path=[candidate_decision],
            terminal_score=0.0,
            top_risk="",
            state_override={},
        )
        return RolloutResult(
            candidate=candidate_decision,
            product_id=product_id,
            branches=[placeholder],
            best_path=[candidate_decision],
            created_at=now,
        )

    cap_scores = await _load_cap_scores(product_id, pool)
    constraints = await _load_scenario_constraints(product_id, pool)

    if cap_scores:
        capability_context = "\n".join(
            f"- {cap_id.split(':', 1)[-1]}: {score:.2f}" for cap_id, score in sorted(cap_scores.items())
        )
    else:
        capability_context = "(no capabilities scored yet)"

    constraint_ctx = ""
    if constraints:
        lines = [f"- {c['description']}" for c in constraints if c.get("description")]
        if lines:
            constraint_ctx = (
                "ACTIVE FORESIGHT CONSTRAINTS (weight branches away from these areas):\n" + "\n".join(lines) + "\n\n"
            )

    try:
        raw = await llm.complete_json(
            constraint_ctx
            + _PROMPT.format(
                candidate=candidate_decision[:300],
                capability_context=capability_context,
            ),
            model=settings.llm_budget_model,
        )
    except Exception:
        logger.warning("planner: LLM call failed for candidate=%r", candidate_decision, exc_info=True)
        raw = {}

    raw_branches = raw.get("branches", [])

    branches: list[RolloutBranch] = []
    for b in raw_branches[:3]:
        path = b.get("path", [candidate_decision])
        if not path:
            path = [candidate_decision]

        state_override: dict[str, float] = {}
        for slug, delta in b.get("score_deltas", {}).items():
            cap_id = f"capability:{slug}"
            current = cap_scores.get(cap_id, 0.5)
            state_override[cap_id] = max(0.0, min(1.0, current + float(delta)))

        try:
            scored = await score_hypothetical_state(product_id, state_override, pool)
        except Exception:
            logger.warning("planner: value_model failed for branch path=%r", path, exc_info=True)
            from core.engine.foresight.models import HypotheticalScore

            scored = HypotheticalScore(gap_score=0.0, top_risks=[], capability_scores={})

        branches.append(
            RolloutBranch(
                path=path,
                terminal_score=scored.gap_score,
                top_risk=b.get("top_risk", ""),
                state_override=state_override,
            )
        )

    if not branches:
        logger.warning("planner: no usable branches from LLM for candidate=%r", candidate_decision)
        branches = [
            RolloutBranch(
                path=[candidate_decision],
                terminal_score=0.0,
                top_risk="insufficient data to project this path",
                state_override={},
            )
        ]

    _assign_branch_authorship(branches)

    best = max(branches, key=lambda b: b.terminal_score)
    now = datetime.now(timezone.utc).isoformat()
    result = RolloutResult(
        candidate=candidate_decision,
        product_id=product_id,
        branches=branches,
        best_path=best.path,
        created_at=now,
    )

    try:
        await _write_cache(result, pool)
    except Exception:
        logger.warning("planner: cache write failed for candidate=%r", candidate_decision, exc_info=True)

    try:
        await _write_speculative_decisions(candidate_decision, product_id, branches, best.path, pool)
    except Exception:
        logger.warning("planner: speculative_decision write failed", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _check_cache(candidate: str, product_id: str, pool) -> RolloutResult | None:
    """Return a cached RolloutResult if one exists within the 4hr TTL, else None."""
    async with pool.connection() as db:
        result = await db.query(
            """SELECT * FROM rollout_cache
               WHERE candidate = $candidate
               AND product = <record>$product
               AND created_at > time::now() - 4h
               ORDER BY created_at DESC LIMIT 1""",
            {"candidate": candidate, "product": product_id},
        )
    rows = parse_rows(result)
    if not rows:
        return None
    row = rows[0]
    branches = [
        RolloutBranch(
            path=b.get("path", []),
            terminal_score=float(b.get("terminal_score", 0.0)),
            top_risk=b.get("top_risk", ""),
            state_override=b.get("state_override", {}),
            authored_by_archetype=b.get("authored_by_archetype", ""),
        )
        for b in row.get("branches", [])
    ]
    if not branches:
        return None
    return RolloutResult(
        candidate=row.get("candidate", candidate),
        product_id=product_id,
        branches=branches,
        best_path=row.get("best_path", branches[0].path),
        created_at=str(row.get("created_at", "")),
    )


async def _load_cap_scores(product_id: str, pool) -> dict[str, float]:
    """Return {capability_id_str: mean_score} from capability_quality for the product."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT capability, score FROM capability_quality WHERE product = <record>$product",
            {"product": product_id},
        )
    rows = parse_rows(result)
    buckets: dict[str, list[float]] = {}
    for row in rows:
        cap_id = str(row.get("capability", ""))
        if cap_id:
            buckets.setdefault(cap_id, []).append(float(row.get("score", 0.5)))
    return {cap_id: sum(scores) / len(scores) for cap_id, scores in buckets.items()}


async def _load_scenario_constraints(product_id: str, pool) -> list[dict]:
    """Load active scenario constraints (medium-term risk → near-term planner bias)."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT description, affected_domains, created_at FROM scenario_constraint
                   WHERE product = <record>$product AND active = true
                   ORDER BY created_at DESC LIMIT 5""",
                {"product": product_id},
            )
        return parse_rows(result)
    except Exception:
        return []


async def _write_speculative_decisions(
    candidate: str,
    product_id: str,
    branches: list[RolloutBranch],
    best_path: list[str],
    pool,
) -> None:
    """Persist non-best rollout branches as speculative_decision nodes (TTL 7d).

    Training negatives for future contrastive learning (Phase D).
    """
    # decision:trq7pplh37iyanbtzn7m — server-side `time::now() + duration("7d")`
    # writes a proper datetime column. Prior code stored an ISO string via
    # `.isoformat()`, which silently breaks future readers that pass a datetime
    # filter (smoke-verified: `WHERE expires_at > $datetime_obj` returns [] when
    # the column is a string).
    for branch in branches:
        if branch.path == best_path:
            continue
        async with pool.connection() as db:
            await db.query(
                """CREATE speculative_decision SET
                    product        = <record>$product,
                    candidate      = $candidate,
                    branch_path    = $branch_path,
                    terminal_score = $terminal_score,
                    expires_at     = time::now() + duration("7d"),
                    created_at     = time::now()
                """,
                {
                    "product": product_id,
                    "candidate": candidate,
                    "branch_path": branch.path,
                    "terminal_score": branch.terminal_score,
                },
            )


async def _write_cache(result: RolloutResult, pool) -> None:
    """Write a RolloutResult to rollout_cache."""
    branches_data = [
        {
            "path": b.path,
            "terminal_score": b.terminal_score,
            "top_risk": b.top_risk,
            "state_override": b.state_override,
        }
        for b in result.branches
    ]
    async with pool.connection() as db:
        await db.query(
            """CREATE rollout_cache SET
                candidate  = $candidate,
                product    = <record>$product,
                branches   = $branches,
                best_path  = $best_path,
                created_at = time::now()
            """,
            {
                "candidate": result.candidate,
                "product": result.product_id,
                "branches": branches_data,
                "best_path": result.best_path,
            },
        )
