"""Cross-product specialty broadcast.

When a specialty matures to EXPERT phase on product A, its high-confidence
insights should propagate to other products in the same ecosystem. This is
what makes the ecosystem layer worth having: each product's learning compounds
across the portfolio without re-earning it.

Each copied insight is tagged with source_product so provenance is preserved
(and the receiving product can audit where a piece of intelligence came from).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_BROADCAST_MIN_CONFIDENCE = 0.8
_BROADCAST_MAX_PER_CALL = 20


async def find_connected_products(db, source_product_id: str) -> list[str]:
    """Return every product sharing at least one ecosystem with source_product_id.

    Excludes the source product itself. Non-fatal — returns [] on any failure.
    """
    try:
        from core.engine.core.db import parse_rows

        rows = parse_rows(
            await db.query(
                """SELECT id FROM product
                   WHERE id != <record>$source
                     AND id IN (
                       SELECT product FROM ecosystem
                       WHERE id IN (
                         SELECT id FROM ecosystem
                         WHERE product = <record>$source
                       )
                     )""",
                {"source": source_product_id},
            )
        )
        return [
            str(row.get("id")) for row in rows if str(row.get("id", "")) and str(row.get("id")) != source_product_id
        ]
    except Exception as exc:
        logger.warning("find_connected_products failed (non-fatal): %s", exc)
        return []


async def broadcast_specialty(
    db,
    source_product_id: str,
    specialty_slug: str,
    insights: list[dict],
) -> int:
    """Copy high-confidence insights to every product connected via the ecosystem layer.

    Args:
        db: SurrealDB connection
        source_product_id: The product whose specialty matured to EXPERT
        specialty_slug: The specialty being broadcast (for tag/provenance)
        insights: The full insight list; this function filters to high-confidence

    Returns total count of CREATE insight calls made. Non-fatal on any failure.
    """
    try:
        connected = await find_connected_products(db, source_product_id)
        if not connected:
            return 0

        eligible = [ins for ins in insights if float(ins.get("confidence") or 0.0) >= _BROADCAST_MIN_CONFIDENCE][
            :_BROADCAST_MAX_PER_CALL
        ]
        if not eligible:
            return 0

        count = 0
        for target_product in connected:
            for ins in eligible:
                try:
                    await db.query(
                        """CREATE insight SET
                           product = <record>$product,
                           content = $content,
                           confidence = $confidence,
                           tier = 'specialty',
                           insight_type = 'fact',
                           source_domain = $specialty_slug,
                           source_product = $source_product,
                           status = 'active',
                           tags = [$specialty_slug, 'broadcast'],
                           created_at = time::now()""",
                        {
                            "product": target_product,
                            "content": ins.get("content", ""),
                            "confidence": float(ins.get("confidence") or 0.0),
                            "specialty_slug": specialty_slug,
                            "source_product": source_product_id,
                        },
                    )
                    count += 1
                except Exception as exc:
                    logger.debug(
                        "broadcast CREATE failed for target=%s insight=%s: %s",
                        target_product,
                        ins.get("id"),
                        exc,
                    )
        return count
    except Exception as exc:
        logger.warning("broadcast_specialty failed (non-fatal): %s", exc)
        return 0
