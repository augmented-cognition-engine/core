# engine/intelligence/maturation.py
"""Maturation scoring — calculate, cache, and track phase transitions.

Implements the scoring rubric from docs/ace-16-maturation-model.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import IntEnum

from core.engine.core.db import parse_one, parse_rows, pool
from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600  # 1 hour
_VALID_NODE_TYPES = frozenset(["specialty", "discipline", "product"])


class MaturationPhase(IntEnum):
    NASCENT = 1
    FORMING = 2
    RELIABLE = 3
    EXPERT = 4
    AUTHORITATIVE = 5


class MaturationResult:
    def __init__(self, phase: MaturationPhase, score: int, metrics: dict):
        self.phase = phase
        self.score = score
        self.metrics = metrics


def score_specialty(metrics: dict) -> MaturationResult:
    """Score a specialty's maturation based on measurable signals. Returns 0-100."""
    score = 0

    # Insight volume (max 25 points)
    ic = metrics.get("insight_count", 0)
    if ic >= 75:
        score += 25
    elif ic >= 36:
        score += 20
    elif ic >= 16:
        score += 15
    elif ic >= 6:
        score += 8
    elif ic >= 1:
        score += 3

    # Average confidence (max 20 points)
    ac = metrics.get("avg_confidence", 0)
    if ac >= 0.9:
        score += 20
    elif ac >= 0.85:
        score += 16
    elif ac >= 0.7:
        score += 12
    elif ac >= 0.5:
        score += 6
    else:
        score += 2

    # Corrections that stuck (max 15 points)
    vc = metrics.get("verified_corrections", 0)
    if vc >= 5:
        score += 15
    elif vc >= 3:
        score += 10
    elif vc >= 1:
        score += 5

    # Synaptic connections (max 10 points)
    sc = metrics.get("synapse_count", 0)
    if sc >= 5:
        score += 10
    elif sc >= 3:
        score += 7
    elif sc >= 1:
        score += 3

    # Task history with positive feedback (max 15 points)
    st = metrics.get("successful_tasks", 0)
    if st >= 50:
        score += 15
    elif st >= 25:
        score += 12
    elif st >= 10:
        score += 8
    elif st >= 3:
        score += 4

    # Verification coverage (max 10 points)
    vr = metrics.get("verified_ratio", 0)
    if vr >= 0.9:
        score += 10
    elif vr >= 0.7:
        score += 7
    elif vr >= 0.3:
        score += 4

    # Skills and playbooks (max 5 points)
    if metrics.get("custom_skills", 0) >= 1 or metrics.get("playbooks", 0) >= 1:
        score += 5
    elif metrics.get("domain_skills_used", 0) >= 1:
        score += 2

    # Phase thresholds
    if score >= 85:
        phase = MaturationPhase.AUTHORITATIVE
    elif score >= 65:
        phase = MaturationPhase.EXPERT
    elif score >= 45:
        phase = MaturationPhase.RELIABLE
    elif score >= 25:
        phase = MaturationPhase.FORMING
    else:
        phase = MaturationPhase.NASCENT

    return MaturationResult(phase=phase, score=score, metrics=metrics)


def weighted_phase(children: list[tuple[MaturationPhase, int]]) -> MaturationPhase:
    """Calculate weighted average phase from child nodes."""
    if not children:
        return MaturationPhase.NASCENT

    total_weight = sum(w for _, w in children)
    if total_weight == 0:
        return MaturationPhase.NASCENT

    weighted_sum = sum(int(phase) * weight for phase, weight in children)
    avg = weighted_sum / total_weight

    # Round to nearest phase
    rounded = round(avg)
    return MaturationPhase(max(1, min(5, rounded)))


def _is_fresh(calculated_at: str | datetime) -> bool:
    """Check if cached maturation is still fresh."""
    if calculated_at is None:
        return False
    if isinstance(calculated_at, str):
        try:
            dt = datetime.fromisoformat(calculated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    else:
        dt = calculated_at

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age < _CACHE_TTL_SECONDS


def _validate_maturation_inputs(node_type: str, node_id: str, product_id: str) -> None:
    """Validate maturation calculation inputs before DB access.

    Raises ValidationError for unknown node_type, empty node_id, or
    malformed product_id to surface configuration errors early.
    """
    if node_type not in _VALID_NODE_TYPES:
        raise ValidationError(f"Unknown node_type {node_type!r}. Valid: {sorted(_VALID_NODE_TYPES)}")
    if not node_id or not node_id.strip():
        raise ValidationError("node_id must be non-empty")
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id: {product_id!r}")


async def calculate_maturation(node_type: str, node_id: str, product_id: str) -> dict:
    """Calculate maturation for any node. Uses cache if fresh.

    Raises ValidationError if inputs are invalid.
    """
    _validate_maturation_inputs(node_type, node_id, product_id)
    logger.debug("Calculating maturation: node_type=%s node_id=%s product=%s", node_type, node_id, product_id)
    async with pool.connection() as db:
        # Check cache
        cached = await db.query(
            """
            SELECT * FROM maturation
            WHERE product = <record>$product AND node_type = $type AND node_id = $id
            LIMIT 1
            """,
            {"product": product_id, "type": node_type, "id": node_id},
        )

        rows = cached[0] if cached and isinstance(cached[0], list) else (cached or [])
        if rows and _is_fresh(rows[0].get("calculated_at", "")):
            row = rows[0]
            return {
                "node_type": row.get("node_type", node_type),
                "node_id": str(row.get("node_id", node_id)),
                "phase": row.get("phase", 1),
                "phase_name": row.get("phase_name", "nascent"),
                "score": row.get("score", 0),
                "metrics": row.get("metrics", {}),
            }

        # Calculate fresh
        if node_type == "specialty":
            metrics = await _get_specialty_metrics(db, node_id, product_id)
            result = score_specialty(metrics)
        else:
            # Subdomain/domain/org: weighted average of children
            result = await _calculate_aggregate(db, node_type, node_id, product_id)

        # Cache result
        previous_phase = rows[0].get("phase") if rows else None

        await db.query(
            """
            UPSERT maturation SET
                product = <record>$product,
                node_type = $type,
                node_id = <record>$id,
                phase = $phase,
                phase_name = $phase_name,
                score = $score,
                metrics = $metrics,
                calculated_at = time::now()
            WHERE product = <record>$product AND node_type = $type AND node_id = <record>$id
            """,
            {
                "product": product_id,
                "type": node_type,
                "id": node_id,
                "phase": int(result.phase),
                "phase_name": result.phase.name.lower(),
                "score": result.score,
                "metrics": result.metrics,
            },
        )

        # Record history if phase changed
        if previous_phase is not None and previous_phase != int(result.phase):
            await db.query(
                """
                CREATE maturation_history SET
                    node_type = $type,
                    node_id = $id,
                    phase = $phase,
                    score = $score,
                    recorded_at = time::now()
                """,
                {
                    "product": product_id,
                    "type": node_type,
                    "id": node_id,
                    "phase": int(result.phase),
                    "score": result.score,
                },
            )

        return {
            "node_type": node_type,
            "node_id": str(node_id),
            "phase": int(result.phase),
            "phase_name": result.phase.name.lower(),
            "score": result.score,
            "metrics": result.metrics,
        }


async def _get_specialty_metrics(db, node_id: str, product_id: str) -> dict:
    """Gather metrics for a specialty from the intelligence graph."""
    result = await db.query(
        """
        SELECT
            count(SELECT id FROM insight WHERE specialty = $id AND status = 'active') AS insight_count,
            math::mean(SELECT VALUE confidence FROM insight WHERE specialty = $id AND status = 'active') AS avg_confidence,
            count(SELECT id FROM insight WHERE specialty = $id AND insight_type = 'correction' AND status = 'active') AS verified_corrections,
            count(SELECT id FROM task WHERE domain_path CONTAINS $slug AND feedback_human = 'accepted') AS successful_tasks,
            count(SELECT id FROM specialty_affinity WHERE (specialty_a = $id OR specialty_b = $id) AND org = <record>$product) AS synapse_count
        """,
        {"id": node_id, "slug": str(node_id), "product": product_id},
    )

    row = parse_one(result) or {}

    return {
        "insight_count": row.get("insight_count", 0),
        "avg_confidence": row.get("avg_confidence", 0) or 0,
        "verified_corrections": row.get("verified_corrections", 0),
        "synapse_count": row.get("synapse_count", 0),  # Phase 2 — now wired
        "successful_tasks": row.get("successful_tasks", 0),
        "verified_ratio": 0.0,  # Phase 3
        "custom_skills": 0,  # Phase 4
        "playbooks": 0,  # Phase 4
        "domain_skills_used": 0,  # Phase 4
    }


async def _calculate_aggregate(db, node_type: str, node_id: str, product_id: str) -> MaturationResult:
    """Calculate weighted average maturation for discipline or product nodes."""
    if node_type == "discipline":
        # specialty.discipline is record<discipline> — traverse via .slug to avoid
        # silent 0-row returns when node_id is a bare slug string.
        specialties = parse_rows(
            await db.query(
                """
                SELECT id, slug, insight_count FROM specialty
                WHERE discipline.slug = $discipline
                  AND (product = <record>$product OR org = <record>product:platform)
                LIMIT 50
                """,
                {"discipline": node_id, "product": product_id},
            )
        )

        if not specialties:
            return MaturationResult(phase=MaturationPhase.NASCENT, score=0, metrics={"specialty_count": 0})

        children = []
        for s in specialties:
            slug = s.get("slug", "")
            cache_rows = parse_rows(
                await db.query(
                    """
                    SELECT phase FROM maturation
                    WHERE node_type = 'specialty' AND node_id = $slug AND product = <record>$product
                    LIMIT 1
                    """,
                    {"slug": slug, "product": product_id},
                )
            )
            cached_phase = cache_rows[0].get("phase", 1) if cache_rows else 1
            phase = MaturationPhase(max(1, min(5, int(cached_phase))))
            weight = max(1, s.get("insight_count") or 1)
            children.append((phase, weight))

        phase = weighted_phase(children)
        score = int(phase) * 20
        return MaturationResult(phase=phase, score=score, metrics={"specialty_count": len(specialties)})

    elif node_type == "product":
        # Aggregate over distinct disciplines present in this product's specialties.
        # discipline field is a record reference — GROUP BY discipline returns record IDs.
        disc_rows = parse_rows(
            await db.query(
                """
                SELECT discipline AS disc, count() AS specialty_count
                FROM specialty
                WHERE product = <record>$product
                GROUP BY discipline
                """,
                {"product": product_id},
            )
        )

        if not disc_rows:
            return MaturationResult(phase=MaturationPhase.NASCENT, score=0, metrics={"discipline_count": 0})

        children = []
        for dr in disc_rows:
            disc_id = str(dr.get("disc", ""))
            cache_rows = parse_rows(
                await db.query(
                    """
                    SELECT phase FROM maturation
                    WHERE node_type = 'discipline' AND node_id = $disc AND product = <record>$product
                    LIMIT 1
                    """,
                    {"disc": disc_id, "product": product_id},
                )
            )
            cached_phase = cache_rows[0].get("phase", 1) if cache_rows else 1
            phase = MaturationPhase(max(1, min(5, int(cached_phase))))
            weight = max(1, dr.get("specialty_count") or 1)
            children.append((phase, weight))

        phase = weighted_phase(children)
        score = int(phase) * 20
        return MaturationResult(phase=phase, score=score, metrics={"discipline_count": len(disc_rows)})

    # Unknown node_type — ValidationError raised by caller before reaching here
    return MaturationResult(phase=MaturationPhase.NASCENT, score=0, metrics={})
