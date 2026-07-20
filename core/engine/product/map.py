# engine/product/map.py
"""ProductMap — CRUD operations for capabilities, directions, and quality assessments."""

from __future__ import annotations

import logging
from collections import defaultdict

from core.engine.core.db import parse_one, parse_rows
from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class ProductMap:
    """Read/write operations on the product map."""

    def __init__(self, db_pool):
        self._pool = db_pool

    def _validate_capability_data(self, data: dict, product_id: str) -> None:
        """Validate capability data before DB upsert operations.

        Raises ValidationError for missing required fields or malformed product_id,
        preventing partial writes that would leave the product map in an inconsistent
        state and confuse the capability mapper and gap analyzer.
        """
        if not product_id or ":" not in product_id:
            raise ValidationError(f"Invalid product_id: {product_id!r}")
        if not data.get("slug", "").strip():
            raise ValidationError("capability.slug must be non-empty")
        if not data.get("name", "").strip():
            raise ValidationError("capability.name must be non-empty")

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    async def get_capabilities(
        self,
        product_id: str,
        status: str = None,
        project_slug: str = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """List all capabilities for an org, optionally filtered by status and/or project.

        Args:
            limit: Maximum results (default 500, max 2000).
            offset: Pagination offset for large capability sets.
        """
        limit = max(1, min(limit, 2000))
        base_params: dict = {"product": product_id, "limit": limit, "offset": offset}
        async with self._pool.connection() as db:
            if project_slug and status:
                result = await db.query(
                    """
                    SELECT * FROM capability
                    WHERE product = <record>$product
                      AND status = <string>$status
                      AND project = (
                          SELECT id FROM project
                          WHERE product = <record>$product AND slug = <string>$proj_slug
                          LIMIT 1
                      )[0].id
                    ORDER BY name LIMIT $limit START $offset
                    """,
                    {**base_params, "status": status, "proj_slug": project_slug},
                )
            elif project_slug:
                result = await db.query(
                    """
                    SELECT * FROM capability
                    WHERE product = <record>$product
                      AND project = (
                          SELECT id FROM project
                          WHERE product = <record>$product AND slug = <string>$proj_slug
                          LIMIT 1
                      )[0].id
                    ORDER BY name LIMIT $limit START $offset
                    """,
                    {**base_params, "proj_slug": project_slug},
                )
            elif status:
                result = await db.query(
                    """
                    SELECT * FROM capability
                    WHERE product = <record>$product AND status = <string>$status
                    ORDER BY name LIMIT $limit START $offset
                    """,
                    {**base_params, "status": status},
                )
            else:
                result = await db.query(
                    """
                    SELECT * FROM capability
                    WHERE product = <record>$product
                    ORDER BY name LIMIT $limit START $offset
                    """,
                    base_params,
                )
            rows = parse_rows(result)
        logger.debug(
            "get_capabilities: product=%s status=%s project=%s → %d results (offset=%d)",
            product_id,
            status,
            project_slug,
            len(rows),
            offset,
        )
        return rows

    async def get_capability(self, slug: str, product_id: str) -> dict | None:
        """Get a single capability with attached quality dimensions, dependencies, and realized files."""
        async with self._pool.connection() as db:
            result = await db.query(
                """
                SELECT * FROM capability
                WHERE product = <record>$product AND slug = <string>$slug
                LIMIT 1
                """,
                {"product": product_id, "slug": slug},
            )
            cap = parse_one(result)
            if cap is None:
                return None

            cap_id = cap.get("id")

            # Attach quality dimensions
            quality_result = await db.query(
                """
                SELECT * FROM capability_quality
                WHERE capability = <record>$cap_id AND product = <record>$product
                """,
                {"cap_id": cap_id, "product": product_id},
            )
            cap["quality"] = parse_rows(quality_result)

            # Attach dependencies
            dep_result = await db.query(
                """
                SELECT *, out.slug AS target_slug, out.name AS target_name
                FROM capability_dep
                WHERE in = <record>$cap_id
                """,
                {"cap_id": cap_id},
            )
            cap["dependencies"] = parse_rows(dep_result)

            # Attach realized files
            files_result = await db.query(
                """
                SELECT *, in.path AS file_path
                FROM realizes
                WHERE out = <record>$cap_id
                """,
                {"cap_id": cap_id},
            )
            cap["realized_files"] = parse_rows(files_result)

            return cap

    async def upsert_capability(self, data: dict, product_id: str) -> dict:
        """Create or update a capability by slug."""
        self._validate_capability_data(data, product_id)
        slug = data.get("slug", "")
        # Check if this is a create or update
        existing = await self.get_capability(slug, product_id) if slug else None

        async with self._pool.connection() as db:
            params = {
                "product": product_id,
                "slug": slug,
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "status": data.get("status", "planned"),
                "intent": data.get("intent"),
                "reality": data.get("reality"),
                "parent": data.get("parent_id"),
                "priority": data.get("priority"),
                "tags": data.get("tags", []),
            }
            result = await db.query(
                """
                UPSERT capability SET
                    product = <record>$product,
                    name = $name,
                    slug = <string>$slug,
                    description = $description,
                    status = $status,
                    intent = $intent,
                    reality = $reality,
                    parent = $parent,
                    priority = $priority,
                    tags = $tags,
                    updated_at = time::now()
                WHERE product = <record>$product AND slug = <string>$slug
                """,
                params,
            )
            cap = parse_one(result)
            if cap is None:
                cap = {**data, "product": product_id}

        # Emit typed Living Canvas event
        logger.info(
            "%s: slug=%r product=%s", "capability.updated" if existing else "capability.added", slug, product_id
        )
        try:
            from core.engine.events.canvas import emit_capability_added, emit_capability_updated

            _emitter = emit_capability_updated if existing else emit_capability_added
            await _emitter(
                product_id=product_id,
                slug=slug,
                name=data.get("name", ""),
                status=data.get("status", "planned"),
            )
        except Exception:
            pass

        return cap

    async def update_reality(self, slug: str, reality: dict, product_id: str) -> dict:
        """Update the reality layer (files, metrics) for a capability."""
        async with self._pool.connection() as db:
            result = await db.query(
                """
                UPDATE capability SET
                    reality = $reality,
                    updated_at = time::now()
                WHERE product = <record>$product AND slug = <string>$slug
                """,
                {"product": product_id, "slug": slug, "reality": reality},
            )
            cap = parse_one(result)
            if cap is None:
                return {"slug": slug, "reality": reality}
            return cap

    async def update_quality(self, slug: str, dimension: str, assessment: dict, product_id: str) -> dict:
        """Create or update a quality assessment for a capability dimension."""
        score = float(assessment.get("score", 0.0))
        gaps = assessment.get("gaps", [])

        async with self._pool.connection() as db:
            params = {
                "product": product_id,
                "slug": slug,
                "dimension": dimension,
                "score": score,
                "gaps": gaps,
                "evidence": assessment.get("evidence", []),
                "assessed_by": assessment.get("assessed_by", "human"),
            }
            result = await db.query(
                """
                UPSERT capability_quality SET
                    product = <record>$product,
                    capability = (SELECT id FROM capability WHERE product = <record>$product AND slug = <string>$slug LIMIT 1)[0].id,
                    dimension = <string>$dimension,
                    score = $score,
                    gaps = $gaps,
                    evidence = $evidence,
                    assessed_by = $assessed_by,
                    assessed_at = time::now()
                WHERE product = <record>$product
                    AND capability = (SELECT id FROM capability WHERE product = <record>$product AND slug = <string>$slug LIMIT 1)[0].id
                    AND dimension = <string>$dimension
                """,
                params,
            )
            quality = parse_one(result)
            if quality is None:
                quality = {"dimension": dimension, **assessment}

        logger.debug(
            "update_quality: slug=%r dimension=%s score=%.2f gaps=%d product=%s",
            slug,
            dimension,
            score,
            len(gaps),
            product_id,
        )

        # Emit gap or quality events
        try:
            from core.engine.events.bus import bus

            if score < 0.4 and gaps:
                await bus.emit(
                    "gap.detected",
                    {
                        "product_id": product_id,
                        "capability_slug": slug,
                        "dimension": dimension,
                        "score": score,
                        "gap_count": len(gaps),
                    },
                )
            elif score >= 0.7:
                await bus.emit(
                    "gap.closed",
                    {
                        "product_id": product_id,
                        "capability_slug": slug,
                        "dimension": dimension,
                        "score": score,
                    },
                )
        except Exception:
            pass

        return quality

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    async def get_vision(self, product_id: str) -> dict | None:
        """Get the active product vision."""
        async with self._pool.connection() as db:
            result = await db.query(
                """
                SELECT * FROM product_vision
                WHERE product = <record>$product AND active = true
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"product": product_id},
            )
            return parse_one(result)

    async def set_vision(self, vision: dict, product_id: str) -> dict:
        """Set a new vision, deactivating previous ones. Links via supersedes."""
        async with self._pool.connection() as db:
            active_result = await db.query(
                """
                SELECT * FROM product_vision
                WHERE product = <record>$product AND active = true
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"product": product_id},
            )
            current = parse_one(active_result)
            supersedes_id = current.get("id") if current else None

            await db.query(
                """
                UPDATE product_vision SET active = false
                WHERE product = <record>$product AND active = true
                """,
                {"product": product_id},
            )

            params = {
                "product": product_id,
                "name": vision.get("name", ""),
                "description": vision.get("description", ""),
                "supersedes": supersedes_id,
            }
            create_result = await db.query(
                """
                CREATE product_vision SET
                    product = <record>$product,
                    name = $name,
                    description = $description,
                    active = true,
                    supersedes = $supersedes,
                    created_at = time::now()
                """,
                params,
            )
            new_vision = parse_one(create_result)
            if new_vision is None:
                return {"active": True, **vision}
            return new_vision

    # ------------------------------------------------------------------
    # Themes
    # ------------------------------------------------------------------

    async def get_themes(self, product_id: str, status: str = "active") -> list[dict]:
        """List themes for the org."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM theme WHERE product = <record>$product AND status = <string>$status ORDER BY created_at",
                {"product": product_id, "status": status},
            )
            return parse_rows(result)

    async def create_theme(self, theme: dict, product_id: str) -> dict:
        """Create a new theme."""
        async with self._pool.connection() as db:
            params = {
                "product": product_id,
                "name": theme.get("name", ""),
                "description": theme.get("description", ""),
                "status": theme.get("status", "active"),
            }
            result = await db.query(
                """
                CREATE theme SET
                    name = $name,
                    description = $description,
                    status = $status,
                    created_at = time::now()
                """,
                params,
            )
            new_theme = parse_one(result)
            if new_theme is None:
                return {"status": "active", **theme}
            return new_theme

    async def update_theme(self, theme_id: str, updates: dict, product_id: str) -> dict | None:
        """Update a theme's name, description, or status."""
        # Allowlist enforced here (not only at API layer) to prevent injection
        allowed = {k: v for k, v in updates.items() if k in {"name", "description", "status"}}
        if not allowed:
            return None
        async with self._pool.connection() as db:
            params = {"id": theme_id, "product": product_id, **allowed}
            set_clauses = ", ".join(f"{k} = ${k}" for k in allowed)
            result = await db.query(
                f"UPDATE <record>$id SET {set_clauses} WHERE product = <record>$product",
                params,
            )
            return parse_one(result)

    # ------------------------------------------------------------------
    # Health summary
    # ------------------------------------------------------------------

    async def health_summary(self, product_id: str, project_slug: str = None) -> dict:
        """Aggregate quality scores across all capabilities.

        Returns:
            {
                dimensions: {dim: {avg_score, min_score, assessed_count, total_gaps}},
                total_capabilities: int,
                by_status: {status: count},
            }
        """
        # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
        # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
        # Both clauses below use the IN form. The first is nested inside another
        # IN; the inner subquery still needs IN-conversion because record equality
        # is the failing operation, not the IN at the outer level.
        project_clause = ""
        if project_slug:
            project_clause = (
                " AND capability IN ("
                "SELECT VALUE id FROM capability"
                " WHERE product = <record>$product"
                " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project_slug)"
                ")"
            )
        caps_project_clause = ""
        if project_slug:
            caps_project_clause = (
                " AND project IN (SELECT VALUE id FROM project"
                " WHERE product = <record>$product AND slug = <string>$project_slug)"
            )
        async with self._pool.connection() as db:
            quality_result = await db.query(
                f"""
                SELECT dimension, score, gaps
                FROM capability_quality
                WHERE product = <record>$product{project_clause}
                """,
                {"product": product_id, "project_slug": project_slug},
            )
            quality_rows = parse_rows(quality_result)

            caps_result = await db.query(
                f"""
                SELECT id, status FROM capability
                WHERE product = <record>$product{caps_project_clause}
                """,
                {"product": product_id, "project_slug": project_slug},
            )
            caps_rows = parse_rows(caps_result)

        # Aggregate quality by dimension
        dim_data: dict[str, dict] = defaultdict(lambda: {"scores": [], "total_gaps": 0})
        for row in quality_rows:
            dim = row.get("dimension", "unknown")
            score = row.get("score", 0.0)
            gaps = row.get("gaps") or []
            dim_data[dim]["scores"].append(score)
            dim_data[dim]["total_gaps"] += len(gaps)

        dimensions = {}
        for dim, data in dim_data.items():
            scores = data["scores"]
            dimensions[dim] = {
                "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
                "min_score": min(scores) if scores else 0.0,
                "assessed_count": len(scores),
                "total_gaps": data["total_gaps"],
            }

        # Aggregate capabilities by status
        by_status: dict[str, int] = defaultdict(int)
        for cap in caps_rows:
            status = cap.get("status", "unknown")
            by_status[status] += 1

        result = {
            "dimensions": dimensions,
            "total_capabilities": len(caps_rows),
            "by_status": dict(by_status),
        }
        logger.info(
            "health_summary: product=%s caps=%d dims=%d",
            product_id,
            len(caps_rows),
            len(dimensions),
        )
        return result
