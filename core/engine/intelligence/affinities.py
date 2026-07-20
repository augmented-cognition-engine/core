# engine/intelligence/affinities.py
"""Specialty affinities — learned co-occurrence links for retrieval meta-learning.

Affinities track which specialties frequently co-occur in successful tasks.
The dual loader uses them to supplement below-threshold specialties.
Strength decays when affinities don't improve outcomes.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_record_id, parse_record_ids, parse_rows, pool
from core.engine.core.exceptions import AffinityError

logger = logging.getLogger(__name__)

_DECAY_RATE = 0.1
_STRENGTHEN_RATE = 0.05
_MIN_STRENGTH = 0.1


def compute_affinity_strength(
    co_occurrence: int,
    avg_utilization: float,
    avg_feedback: float,
) -> float:
    """Compute affinity strength from evidence. Returns 0.0-1.0.

    Saturates around 20 co-occurrences. Blends count factor (50%) with
    quality factor (avg_utilization * avg_feedback, 50%).
    """
    if co_occurrence == 0:
        return 0.0
    # Normalize co-occurrence (saturates around 20)
    count_factor = min(1.0, co_occurrence / 20.0)
    quality = avg_utilization * avg_feedback
    return min(1.0, count_factor * 0.5 + quality * 0.5)


def decay_affinity(current_strength: float, below_baseline: bool) -> float:
    """Adjust affinity strength based on downstream performance.

    below_baseline=True: tasks using this affinity performed worse than average
        → weaken by _DECAY_RATE (0.1), clamped to 0.0.
    below_baseline=False: tasks performed at or above average
        → strengthen by _STRENGTHEN_RATE (0.05), clamped to 1.0.
    """
    if below_baseline:
        return max(0.0, current_strength - _DECAY_RATE)
    return min(1.0, current_strength + _STRENGTHEN_RATE)


async def get_affinities_for_specialties(
    specialty_ids: list[str],
    product_id: str,
    min_strength: float = 0.3,
) -> list[dict]:
    """Get affinities for a set of specialties, sorted by strength descending.

    Returns all affinity records where either specialty_a or specialty_b is in
    the provided list, filtered by org and minimum strength threshold.
    """
    if not specialty_ids:
        return []
    parsed_ids = parse_record_ids(specialty_ids)
    async with pool.connection() as db:
        result = await db.query(
            """SELECT * FROM specialty_affinity
               WHERE (specialty_a IN $ids OR specialty_b IN $ids)
               AND product = <record>$product AND strength > $min
               ORDER BY strength DESC LIMIT 10""",
            {"ids": parsed_ids, "product": product_id, "min": min_strength},
        )
        rows = parse_rows(result)
    logger.debug(
        "Loaded %d affinities for %d specialties (product=%s, min_strength=%.2f)",
        len(rows),
        len(specialty_ids),
        product_id,
        min_strength,
    )
    return rows


async def upsert_affinity(
    specialty_a: str,
    specialty_b: str,
    product_id: str,
    co_occurrence: int,
    avg_utilization: float,
    avg_feedback: float,
) -> dict | None:
    """Create or update a specialty affinity record.

    Normalizes pair order (alphabetical) to prevent duplicate inverse pairs.
    Skips upsert if computed strength is below _MIN_STRENGTH (0.1).
    Returns the upserted record or None if skipped.
    """
    strength = compute_affinity_strength(co_occurrence, avg_utilization, avg_feedback)
    if strength < _MIN_STRENGTH:
        logger.debug(
            "Skipping affinity upsert: strength %.3f below threshold %.2f (a=%s b=%s)",
            strength,
            _MIN_STRENGTH,
            specialty_a,
            specialty_b,
        )
        return None

    # Normalize pair order (alphabetical) to prevent duplicates
    if str(specialty_a) > str(specialty_b):
        specialty_a, specialty_b = specialty_b, specialty_a

    async with pool.connection() as db:
        # Same UPSERT-CREATE pattern as engine/graph/cooccurrence.py: SCHEMAFULL
        # required fields (specialty_a, specialty_b have no DEFAULT) must be in
        # the SET clause, otherwise the CREATE branch silently fails. The
        # previous SET omitted those plus `product`, so first-time upserts for
        # any specialty pair never persisted, leaving the table empty.
        result = await db.query(
            """UPSERT specialty_affinity SET
                specialty_a = $a, specialty_b = $b,
                product = <record>$product,
                strength = $strength, co_occurrence = $co,
                avg_utilization = $util, avg_feedback = $fb,
                updated_at = time::now()
            WHERE specialty_a = $a AND specialty_b = $b AND product = <record>$product""",
            {
                "a": parse_record_id(specialty_a),
                "b": parse_record_id(specialty_b),
                "product": product_id,
                "strength": strength,
                "co": co_occurrence,
                "util": avg_utilization,
                "fb": avg_feedback,
            },
        )
        rows = parse_rows(result)
        record = rows[0] if rows else None

    if record:
        logger.debug(
            "Upserted affinity strength=%.3f co=%d (a=%s b=%s product=%s)",
            strength,
            co_occurrence,
            specialty_a,
            specialty_b,
            product_id,
        )
    else:
        raise AffinityError(f"Affinity upsert returned no record (a={specialty_a} b={specialty_b})")
    return record
