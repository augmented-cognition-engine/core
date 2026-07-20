"""Inline playbook suggestion — detect repeatable patterns on initiative completion."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _validate_playbook_inputs(initiative_id: str, product_id: str, threshold: float) -> None:
    """Validate playbook suggestion inputs before querying historical initiatives.

    Raises ValidationError for empty initiative_id, malformed product_id, or
    threshold outside [0.0, 1.0], which would either skip all suggestions or
    match every initiative as similar.
    """
    if not initiative_id or not initiative_id.strip():
        raise ValidationError("initiative_id must be non-empty")
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id: {product_id!r}")
    if not (0.0 <= threshold <= 1.0):
        raise ValidationError(f"threshold must be in [0.0, 1.0], got {threshold}")


async def check_for_playbook_suggestion(initiative_id: str, product_id: str, threshold: float = 0.6) -> dict | None:
    """Check if a completed initiative matches a repeatable pattern.

    Compares the initiative's milestones/work items against past completed initiatives
    using Jaccard similarity on archetype + domain sets.

    Returns a suggestion dict with similar_initiatives and draft info, or None.
    """
    _validate_playbook_inputs(initiative_id, product_id, threshold)
    async with pool.connection() as db:
        # Load this initiative's milestones
        ms_rows = parse_rows(
            await db.query(
                """
                SELECT id, title, domain_path, sequence FROM milestone
                WHERE initiative = $init AND product = <record>$product
                ORDER BY sequence ASC
                """,
                {"init": initiative_id, "product": product_id},
            )
        )

        if len(ms_rows) < 2:
            return None  # Too simple to be a pattern

        # Load work items for archetype/domain fingerprint
        wi_rows = parse_rows(
            await db.query(
                """
                SELECT archetype, domain_path FROM work_item
                WHERE initiative = $init AND product = <record>$product
                """,
                {"init": initiative_id, "product": product_id},
            )
        )

        current_archetypes = {w.get("archetype") for w in wi_rows if w.get("archetype")}
        current_domains = {w.get("domain_path") for w in wi_rows if w.get("domain_path")}

        if not current_archetypes:
            return None

        # Find completed initiatives (excluding this one)
        past_rows = parse_rows(
            await db.query(
                """
                SELECT id, title, created_at FROM initiative
                WHERE product = <record>$product AND status = 'completed' AND id != $init
                ORDER BY created_at DESC
                LIMIT 20
                """,
                {"product": product_id, "init": initiative_id},
            )
        )

        similar = []
        for past in past_rows:
            past_id = str(past.get("id", ""))
            past_wis = parse_rows(
                await db.query(
                    """
                    SELECT archetype, domain_path FROM work_item
                    WHERE initiative = $init AND product = <record>$product
                    """,
                    {"init": past_id, "product": product_id},
                )
            )

            past_archetypes = {w.get("archetype") for w in past_wis if w.get("archetype")}
            past_domains = {w.get("domain_path") for w in past_wis if w.get("domain_path")}

            # Jaccard on archetypes
            arch_sim = _jaccard(current_archetypes, past_archetypes)
            # Jaccard on domains
            dom_sim = _jaccard(current_domains, past_domains)
            # Combined similarity (weighted)
            combined = arch_sim * 0.6 + dom_sim * 0.4

            if combined >= threshold:
                similar.append(
                    {
                        "id": past_id,
                        "title": past.get("title", ""),
                        "similarity": round(combined, 2),
                        "archetype_overlap": round(arch_sim, 2),
                        "domain_overlap": round(dom_sim, 2),
                    }
                )

        if not similar:
            return None

        similar.sort(key=lambda x: x["similarity"], reverse=True)

        return {
            "initiative_id": initiative_id,
            "similar_initiatives": similar[:3],
            "milestone_count": len(ms_rows),
            "suggestion": f"This initiative followed a similar pattern to {len(similar)} past initiative(s). Consider saving as a playbook template.",
        }


def _jaccard(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)
