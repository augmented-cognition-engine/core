# engine/intelligence/emergence.py
"""Specialty emergence — detect insight clusters and auto-create specialties.

Called after each synthesis run. When 5+ unparented insights share a subdomain,
the system uses a budget LLM call to propose a specialty name and creates it.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm

_EMERGENCE_THRESHOLD = 5

logger = logging.getLogger(__name__)


def _validate_emergence_inputs(product_id: str) -> None:
    """Validate emergence check inputs before running DB queries.

    Raises ValidationError for malformed product_id so emergence detection
    fails fast with a clear error rather than silently querying all records.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for emergence check: {product_id!r}")


async def check_emergence(product_id: str) -> list[dict]:
    """Check for specialty emergence across all subdomains. Returns list of created specialties.

    Raises ValidationError if product_id is malformed.
    """
    _validate_emergence_inputs(product_id)
    logger.info("Emergence check started: product=%s threshold=%d", product_id, _EMERGENCE_THRESHOLD)
    emerged = []

    async with pool.connection() as db:
        # Find subdomains with unparented insight clusters
        clusters = await db.query(
            """
            SELECT source_domain, count() AS count
            FROM insight
            WHERE product = <record>$product
              AND status = 'active'
              AND specialty = NONE
            GROUP BY source_domain
            """,
            {"product": product_id},
        )

        rows = clusters[0] if clusters and isinstance(clusters[0], list) else (clusters or [])
        # Filter by threshold in Python (SurrealDB v3 has no HAVING clause)
        rows = [r for r in rows if (r.get("count") or 0) >= _EMERGENCE_THRESHOLD]

        logger.debug(
            "Emergence check: %d clusters above threshold=%d (product=%s)",
            len(rows),
            _EMERGENCE_THRESHOLD,
            product_id,
        )

        for cluster in rows:
            domain_hint = cluster.get("source_domain")
            if not domain_hint:
                continue

            try:
                # Fetch the unparented insights for this cluster
                insights = await db.query(
                    """
                    SELECT id, content, insight_type, confidence
                    FROM insight
                    WHERE product = <record>$product
                      AND status = 'active'
                      AND specialty = NONE
                      AND source_domain = $hint
                    ORDER BY confidence DESC
                    LIMIT 20
                    """,
                    {"product": product_id, "hint": domain_hint},
                )

                insight_list = insights[0] if insights and isinstance(insights[0], list) else (insights or [])
                if len(insight_list) < _EMERGENCE_THRESHOLD:
                    continue

                # LLM proposes specialty name
                insight_text = "\n".join(f"- {i.get('content', '')}" for i in insight_list[:10])
                proposal = await llm.complete_json(
                    f"""These insights cluster in {domain_hint}. Propose a specialty name.

Insights:
{insight_text}

Return JSON:
{{"name": "Human-readable Name", "slug": "kebab-case-slug"}}""",
                    model=settings.llm_budget_model,
                )

                name = proposal.get("name", domain_hint.split(".")[-1])
                slug = proposal.get("slug", name.lower().replace(" ", "-"))

                # Create specialty — `product` is required (record<product>). The
                # field was named `org` until v059→v061 migration which dropped
                # `org` and made `product` the canonical name; the comment here
                # was stale. SCHEMAFULL CREATE fails silently when the wrong
                # field name is used, which is why the engine log was filling
                # with "Failed to create specialty for X: no id in result" on
                # every emergence attempt.
                result = await db.query(
                    """
                    CREATE specialty SET
                        product = <record>$product,
                        name = $name,
                        slug = $slug,
                        parents = [],
                        task_count = 0,
                        maturation_phase = 1,
                        maturation_score = 0,
                        health_score = 0.0,
                        created_at = time::now(),
                        last_active = time::now()
                    """,
                    {"product": product_id, "name": name, "slug": slug},
                )

                spec_rows = (
                    result[0]
                    if result and isinstance(result[0], list)
                    else (result if isinstance(result, list) else [result])
                )
                spec_row = spec_rows[0] if spec_rows and isinstance(spec_rows[0], dict) else None
                spec_id = spec_row.get("id") if spec_row else None

                if not spec_id:
                    logger.error("Failed to create specialty for %s: no id in result", domain_hint)
                    continue

                # Re-parent insights to the new specialty
                await db.query(
                    """
                    UPDATE insight SET specialty = $spec
                    WHERE product = <record>$product
                      AND status = 'active'
                      AND specialty = NONE
                      AND source_domain = $hint
                    """,
                    {"spec": spec_id, "product": product_id, "hint": domain_hint},
                )

                logger.info(
                    "Specialty emerged: slug=%r name=%r domain=%r (product=%s)",
                    slug,
                    name,
                    domain_hint,
                    product_id,
                )
                emerged.append({"id": str(spec_id), "name": name, "slug": slug, "domain_hint": domain_hint})
            except Exception as exc:
                logger.warning("Emergence failed for cluster %s: %s", domain_hint, exc)
                continue

    logger.info("Emergence check complete: product=%s specialties_created=%d", product_id, len(emerged))
    return emerged
