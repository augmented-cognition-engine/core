# engine/intelligence/emergence.py
"""Specialty emergence — detect insight clusters and auto-create specialties.

Called after each synthesis run. When 5+ unparented insights share a subdomain,
the system uses a budget LLM call to propose a specialty name and creates it.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.db import parse_rows
from core.engine.core.db import pool as default_pool
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


async def check_emergence(product_id: str, *, pool=None) -> list[dict]:
    """Check for specialty emergence across all subdomains. Returns list of created specialties.

    Raises ValidationError if product_id is malformed.
    """
    if not settings.emergence_enabled:
        logger.debug("Emergence disabled; skipping product %s", product_id)
        return []
    _validate_emergence_inputs(product_id)
    if pool is None:
        pool = default_pool
    logger.info("Emergence check started: product=%s threshold=%d", product_id, _EMERGENCE_THRESHOLD)
    emerged = []

    # Load bounded prompt inputs under the caller's pool, then release the
    # connection before awaiting the model. A slow model must never consume a
    # scarce database connection.
    candidates: list[tuple[str, list[dict]]] = []
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

        rows = parse_rows(clusters)
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
            insight_list = parse_rows(insights)
            if len(insight_list) >= _EMERGENCE_THRESHOLD:
                candidates.append((str(domain_hint), insight_list))

    for domain_hint, insight_list in candidates:
        try:
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

            # Reacquire only for a short, product-scoped eligibility check and
            # persistence phase. Another worker may have claimed the cluster
            # while the model was running; fewer than five unparented rows means
            # this candidate is now stale and must be dropped.
            async with pool.connection() as db:
                current_insights = parse_rows(
                    await db.query(
                        """
                        SELECT id
                        FROM insight
                        WHERE product = <record>$product
                          AND status = 'active'
                          AND specialty = NONE
                          AND source_domain = $hint
                        LIMIT 20
                        """,
                        {"product": product_id, "hint": domain_hint},
                    )
                )
                if len(current_insights) < _EMERGENCE_THRESHOLD:
                    continue

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

                spec_rows = parse_rows(result)
                spec_row = spec_rows[0] if spec_rows else None
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
