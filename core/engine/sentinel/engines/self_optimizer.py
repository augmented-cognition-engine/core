# engine/sentinel/engines/self_optimizer.py
"""Self-optimizer sentinel engine -- consolidates execution patterns into procedures and affinities.

Scans task history for:
1. Insight co-occurrence clusters -> proposes skills or frameworks
2. Specialty co-loading patterns -> creates retrieval affinities

Triggered by feedback counter crossing threshold, with weekly cron as safety net.
Self-calibrating thresholds adjust based on proposal approval rate.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from core.engine.core.config import settings
from core.engine.core.db import parse_record_ids, parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_DEFAULT_MIN_JACCARD = 0.5


def _validate_optimizer_inputs(product_id: str, budget: int = 100) -> None:
    """Validate self-optimizer inputs before scanning task history.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the optimizer fails fast instead of running expensive DB queries
    and LLM calls against invalid data.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for self-optimizer: {product_id!r}")
    if not (1 <= budget <= 500):
        raise ValidationError(f"budget must be in [1, 500], got {budget}")


@dataclass
class TaskEvidence:
    task_id: str
    specialties_loaded: list[str]
    insights_reflected: list[str]
    utilization_rate: float
    feedback_score: float
    perspective: str
    engagement_perspectives: list[str]

    @property
    def task_combined_score(self) -> float:
        return self.utilization_rate * self.feedback_score


@dataclass
class PatternEvidence:
    task_ids: list[str]
    insight_ids: list[str]
    specialty_ids: list[str]
    avg_utilization: float
    avg_feedback: float
    task_count: int

    @property
    def combined_score(self) -> float:
        return self.avg_utilization * self.avg_feedback


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_by_insight_overlap(
    evidences: list[TaskEvidence],
    min_jaccard: float = _DEFAULT_MIN_JACCARD,
) -> list[list[TaskEvidence]]:
    """Group tasks by overlapping reflected insights using single-linkage clustering."""
    if not evidences:
        return []

    sets = [set(e.insights_reflected) for e in evidences]
    n = len(evidences)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if _jaccard(sets[i], sets[j]) >= min_jaccard:
                union(i, j)

    groups: dict[int, list[TaskEvidence]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(evidences[i])

    return [g for g in groups.values() if len(g) >= 2]


def detect_specialty_affinities(
    evidences: list[TaskEvidence],
    min_tasks: int = 3,
) -> list[dict]:
    """Find specialty pairs that frequently co-occur in successful tasks."""
    pair_stats: dict[tuple[str, str], list[TaskEvidence]] = defaultdict(list)

    for ev in evidences:
        if len(ev.specialties_loaded) < 2:
            continue
        sorted_specs = sorted(ev.specialties_loaded)
        for a, b in combinations(sorted_specs, 2):
            pair_stats[(a, b)].append(ev)

    affinities = []
    for (spec_a, spec_b), tasks in pair_stats.items():
        if len(tasks) < min_tasks:
            continue
        avg_util = sum(t.utilization_rate for t in tasks) / len(tasks)
        avg_fb = sum(t.feedback_score for t in tasks) / len(tasks)
        affinities.append(
            {
                "specialty_a": spec_a,
                "specialty_b": spec_b,
                "co_occurrence": len(tasks),
                "avg_utilization": avg_util,
                "avg_feedback": avg_fb,
                "task_ids": [t.task_id for t in tasks],
            }
        )

    return sorted(affinities, key=lambda x: x["co_occurrence"], reverse=True)


async def extract_task_evidence(product_id: str, db) -> list[TaskEvidence]:
    """Query qualifying tasks and build evidence list."""
    rows = parse_rows(
        await db.query(
            """SELECT id, specialties_loaded, intelligence_utilization, feedback_human,
                  perspective, engagement.perspectives AS engagement_perspectives
           FROM task
           WHERE product = <record>$product
             AND feedback_human IN ['accepted', 'edited']
             AND intelligence_utilization != NONE
             AND created_at > time::now() - 30d""",
            {"product": product_id},
        )
    )

    evidences = []
    for row in rows:
        util = row.get("intelligence_utilization") or {}
        fb = row.get("feedback_human", "")
        fb_score = 1.0 if fb == "accepted" else 0.5

        evidences.append(
            TaskEvidence(
                task_id=str(row.get("id", "")),
                specialties_loaded=row.get("specialties_loaded") or [],
                insights_reflected=util.get("reflected_ids") or [],
                utilization_rate=util.get("utilization_rate", 0.0),
                feedback_score=fb_score,
                perspective=row.get("perspective", "practitioner"),
                engagement_perspectives=row.get("engagement_perspectives") or [row.get("perspective", "practitioner")],
            )
        )

    return evidences


async def _classify_cluster(
    cluster: list[TaskEvidence],
    product_id: str,
    db,
) -> dict | None:
    """Call LLM to classify an insight cluster as skill, framework, or neither."""
    # Collect unique insight IDs from cluster
    all_insights: set[str] = set()
    for ev in cluster:
        all_insights.update(ev.insights_reflected)

    if not all_insights:
        return None

    # Fetch insight content
    insight_rows = parse_rows(
        await db.query(
            "SELECT id, content FROM insight WHERE id IN $ids",
            {"ids": parse_record_ids(list(all_insights)[:20])},
        )
    )
    insight_text = "\n".join(f"- {r.get('content', '')}" for r in insight_rows)
    task_text = "\n".join(f"- Task {ev.task_id}" for ev in cluster[:5])

    try:
        result = await llm.complete_json(
            f"""These insights consistently appear together in successful tasks:
{insight_text}

Tasks where they appeared:
{task_text}

Do these insights describe:
A) A repeatable PROCESS -- steps someone follows (-> propose as a skill)
B) A way of THINKING -- reasoning principles (-> propose as a framework)
C) Neither -- coincidentally co-occurring facts

If A: return a draft skill with job names.
If B: return a system_prompt that captures the reasoning.

Return JSON: {{"type": "skill"|"framework"|"neither", "name": "...", "description": "...", "draft": {{}}}}""",
            model=settings.llm_budget_model,
        )
        if result.get("type") in ("skill", "framework"):
            return result
    except Exception as exc:
        logger.warning("Cluster classification failed: %s", exc)

    return None


async def _calibrate(product_id: str, db, state: dict) -> dict:
    """Adjust thresholds based on approval rate. Returns updated state."""
    proposals = parse_rows(
        await db.query(
            "SELECT status FROM self_optimizer_proposal WHERE product = <record>$product AND created_at > time::now() - 90d",
            {"product": product_id},
        )
    )
    total = len(proposals)
    if total < 5:
        return state

    approved = sum(1 for p in proposals if p.get("status") == "approved")
    rate = approved / total

    min_tasks = state.get("min_tasks", 3)
    min_score = state.get("min_combined_score", 0.25)

    if rate < 0.6:
        min_score = min(0.8, min_score + 0.05)
        min_tasks = min(10, min_tasks + 1)
    elif rate > 0.9:
        min_score = max(0.15, min_score - 0.05)
        min_tasks = max(2, min_tasks - 1)

    await db.query(
        "UPDATE self_optimizer_state SET min_tasks = $mt, min_combined_score = $ms WHERE product = <record>$product",
        {"product": product_id, "mt": min_tasks, "ms": min_score},
    )

    return {**state, "min_tasks": min_tasks, "min_combined_score": min_score}


@register_engine(
    "self_optimizer",
    "0 3 * * sun",
    "Consolidate execution patterns into procedures and retrieval affinities",
)
async def run_self_optimizer(product_id: str, budget: int = 20) -> dict:
    """Main entry: extract evidence, cluster, classify, detect affinities, calibrate."""
    _validate_optimizer_inputs(product_id, budget)
    results = {"proposals": 0, "affinities_created": 0, "evidence_count": 0, "clusters_found": 0}

    async with pool.connection() as db:
        # Load state / thresholds
        state_rows = parse_rows(
            await db.query(
                "SELECT * FROM self_optimizer_state WHERE product = <record>$product",
                {"product": product_id},
            )
        )
        state = state_rows[0] if state_rows else {"min_tasks": 3, "min_combined_score": 0.25}

        # Extract evidence
        evidences = await extract_task_evidence(product_id, db)
        results["evidence_count"] = len(evidences)

        if not evidences:
            await db.query(
                "UPDATE self_optimizer_state SET last_run = time::now() WHERE product = <record>$product",
                {"product": product_id},
            )
            return results

        min_tasks = state.get("min_tasks", 3)
        min_score = state.get("min_combined_score", 0.25)

        # Pass 1+2: Insight clustering -> skill/framework proposals
        clusters = cluster_by_insight_overlap(evidences)
        results["clusters_found"] = len(clusters)

        proposals_created = 0
        for cluster in sorted(
            clusters,
            key=lambda c: sum(e.task_combined_score for e in c),
            reverse=True,
        ):
            if proposals_created >= budget:
                break
            if len(cluster) < min_tasks:
                continue

            avg_util = sum(e.utilization_rate for e in cluster) / len(cluster)
            avg_fb = sum(e.feedback_score for e in cluster) / len(cluster)
            if avg_util * avg_fb < min_score:
                continue

            classification = await _classify_cluster(cluster, product_id, db)
            if not classification:
                continue

            # Store proposal
            all_insights: set[str] = set()
            for ev in cluster:
                all_insights.update(ev.insights_reflected)

            evidence = {
                "task_count": len(cluster),
                "avg_utilization": avg_util,
                "avg_feedback": avg_fb,
                "combined_score": avg_util * avg_fb,
            }

            await db.query(
                """CREATE self_optimizer_proposal SET
                    description = $desc, draft = $draft,
                    evidence = $evidence,
                    source_tasks = $tasks, source_insights = $insights""",
                {
                    "product": product_id,
                    "type": classification["type"],
                    "name": classification.get("name", "Untitled"),
                    "desc": classification.get("description", ""),
                    "draft": classification.get("draft", {}),
                    "evidence": evidence,
                    "tasks": [e.task_id for e in cluster],
                    "insights": list(all_insights)[:50],
                },
            )
            proposals_created += 1

        results["proposals"] = proposals_created

        # Pass 3: Specialty affinities
        # Lazy import to avoid circular deps
        from core.engine.intelligence.affinities import upsert_affinity

        affinity_candidates = detect_specialty_affinities(evidences, min_tasks=min_tasks)
        affinities_created = 0

        for aff in affinity_candidates:
            if aff["avg_utilization"] * aff["avg_feedback"] < min_score:
                continue
            result = await upsert_affinity(
                aff["specialty_a"],
                aff["specialty_b"],
                product_id,
                aff["co_occurrence"],
                aff["avg_utilization"],
                aff["avg_feedback"],
            )
            if result:
                affinities_created += 1

        results["affinities_created"] = affinities_created

        # Calibrate thresholds
        await _calibrate(product_id, db, state)

        # Update last_run
        await db.query(
            "UPDATE self_optimizer_state SET last_run = time::now(), counter = 0 WHERE product = <record>$product",
            {"product": product_id},
        )

    return results
