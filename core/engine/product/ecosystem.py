# engine/product/ecosystem.py
"""Ecosystem and Project management.

Hierarchy: Universal → Ecosystem → Product (Project) → Feature (Capability)
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_rows
from core.engine.core.exceptions import DatabaseError, EcosystemError

logger = logging.getLogger(__name__)


class EcosystemManager:
    def __init__(self, db_pool):
        self._pool = db_pool

    def _validate_slug(self, slug: str) -> None:
        """Validate slug format before issuing DB queries.

        Raises EcosystemError if slug is empty or contains characters that are
        not safe for SurrealDB record IDs (alphanumeric, hyphens, underscores only).
        """
        if not slug:
            raise EcosystemError("slug must be non-empty")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        if not all(c in allowed for c in slug):
            raise EcosystemError(f"Invalid slug {slug!r}: only alphanumeric, hyphens and underscores allowed")

    # ── Ecosystem CRUD ──

    async def create_ecosystem(self, data: dict, product_id: str) -> dict:
        """Create an ecosystem (connected set of products)."""
        slug = data.get("slug", "")
        self._validate_slug(slug)
        logger.info("Creating ecosystem slug=%r product=%s", slug, product_id)
        async with self._pool.connection() as db:
            params = {
                "product": product_id,
                "slug": slug,
                "name": data.get("name", ""),
                "description": data.get("description"),
                "conventions": data.get("conventions"),
                "roadmap": data.get("roadmap"),
            }
            result = await db.query(
                """
                UPSERT ecosystem SET
                    product = <record>$product,
                    name = $name,
                    slug = <string>$slug,
                    description = $description,
                    conventions = $conventions,
                    roadmap = $roadmap,
                    updated_at = time::now()
                WHERE product = <record>$product AND slug = <string>$slug
                """,
                params,
            )
            eco = parse_one(result)
            if eco is None:
                logger.warning("Ecosystem upsert returned no record: slug=%r product=%s", slug, product_id)
                return {**data, "product": product_id}
            logger.debug("Ecosystem upserted: id=%s slug=%r", eco.get("id"), slug)
            return eco

    async def get_ecosystems(self, product_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all ecosystems for an org.

        Args:
            limit: Maximum results (default 100, max 500).
            offset: Pagination offset.
        """
        limit = max(1, min(limit, 500))
        async with self._pool.connection() as db:
            result = await db.query(
                """
                SELECT * FROM ecosystem
                WHERE product = <record>$product
                ORDER BY name
                LIMIT $limit START $offset
                """,
                {"product": product_id, "limit": limit, "offset": offset},
            )
            rows = parse_rows(result)
        logger.debug("Listed %d ecosystems for product=%s (offset=%d)", len(rows), product_id, offset)
        return rows

    async def get_ecosystem(self, slug: str, product_id: str) -> dict | None:
        """Get ecosystem with its projects."""
        self._validate_slug(slug)
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """
                    SELECT * FROM ecosystem
                    WHERE product = <record>$product AND slug = <string>$slug
                    LIMIT 1
                    """,
                    {"product": product_id, "slug": slug},
                )
                eco = parse_one(result)
                if eco is None:
                    return None

                eco_id = eco.get("id")

                projects_result = await db.query(
                    """
                    SELECT * FROM project
                    WHERE product = <record>$product AND ecosystem = <record>$eco_id
                    ORDER BY name
                    """,
                    {"product": product_id, "eco_id": eco_id},
                )
                eco["projects"] = parse_rows(projects_result)

                return eco
        except Exception as exc:
            raise EcosystemError(f"Failed to load ecosystem {slug!r}: {exc}") from exc

    # ── Project CRUD ──

    async def create_project(self, data: dict, product_id: str) -> dict:
        """Create a project (standalone or within an ecosystem)."""
        slug = data.get("slug", "")
        self._validate_slug(slug)
        logger.info("Creating project slug=%r product=%s", slug, product_id)
        async with self._pool.connection() as db:
            ecosystem_id = None
            ecosystem_slug = data.get("ecosystem_slug")
            if ecosystem_slug:
                eco_result = await db.query(
                    """
                    SELECT id FROM ecosystem
                    WHERE product = <record>$product AND slug = <string>$slug
                    LIMIT 1
                    """,
                    {"product": product_id, "slug": ecosystem_slug},
                )
                eco = parse_one(eco_result)
                if eco:
                    ecosystem_id = eco.get("id")

            params = {
                "product": product_id,
                "slug": data.get("slug", ""),
                "name": data.get("name", ""),
                "description": data.get("description"),
                "ecosystem": ecosystem_id,
                "repo_path": data.get("repo_path"),
                "product_type": data.get("product_type"),
                "active_disciplines": data.get("active_disciplines"),
            }
            result = await db.query(
                """
                UPSERT project SET
                    product = <record>$product,
                    name = $name,
                    slug = <string>$slug,
                    description = $description,
                    ecosystem = $ecosystem,
                    repo_path = $repo_path,
                    product_type = $product_type,
                    active_disciplines = $active_disciplines,
                    updated_at = time::now()
                WHERE product = <record>$product AND slug = <string>$slug
                """,
                params,
            )
            proj = parse_one(result)
            if proj is None:
                logger.warning("Project upsert returned no record: slug=%r product=%s", slug, product_id)
                return {**data, "product": product_id}
            logger.debug("Project upserted: id=%s slug=%r", proj.get("id"), slug)
            return proj

    async def get_projects(
        self, product_id: str, ecosystem_slug: str = None, limit: int = 200, offset: int = 0
    ) -> list[dict]:
        """List projects, optionally filtered by ecosystem.

        Args:
            limit: Maximum results (default 200, max 1000).
            offset: Pagination offset.
        """
        limit = max(1, min(limit, 1000))
        async with self._pool.connection() as db:
            if ecosystem_slug:
                # decision:17xtwojp9b4d3qcgsocz — the prior shape combined three
                # SurrealDB v3 bugs at once:
                #   1. `FROM project AND project.ecosystem = ...` had no WHERE
                #      clause (dangling AND).
                #   2. `ORDER BY project.name` without including `name` in the
                #      projection raises a parse error in v3.
                #   3. `= (SELECT ... LIMIT 1)[0].id` is the [0]-scalarize
                #      workaround we documented in decision:8vj092dt6wklp60xqfat,
                #      but `IN (subquery)` is the cleaner v3 idiom.
                # Verified live: prior shape raised at the parse step; the new
                # shape resolves correctly. Slug+product is unique on ecosystem,
                # so IN matches at most one record.
                result = await db.query(
                    """
                    SELECT *, name FROM project
                    WHERE ecosystem IN (
                        SELECT VALUE id FROM ecosystem
                        WHERE product = <record>$product AND slug = <string>$eco_slug
                    )
                    ORDER BY name
                    LIMIT $limit START $offset
                    """,
                    {"product": product_id, "eco_slug": ecosystem_slug, "limit": limit, "offset": offset},
                )
            else:
                result = await db.query(
                    """
                    SELECT * FROM project
                    WHERE product = <record>$product
                    ORDER BY name
                    LIMIT $limit START $offset
                    """,
                    {"product": product_id, "limit": limit, "offset": offset},
                )
            rows = parse_rows(result)
        logger.debug(
            "Listed %d projects for product=%s eco=%r (offset=%d)", len(rows), product_id, ecosystem_slug, offset
        )
        return rows

    async def get_project(self, slug: str, product_id: str) -> dict | None:
        """Get project with its capabilities."""
        self._validate_slug(slug)
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    """
                    SELECT * FROM project
                    WHERE product = <record>$product AND slug = <string>$slug
                    LIMIT 1
                    """,
                    {"product": product_id, "slug": slug},
                )
                proj = parse_one(result)
                if proj is None:
                    return None

                proj_id = proj.get("id")

                caps_result = await db.query(
                    """
                    SELECT * FROM capability
                    WHERE product = <record>$product AND project = <record>$proj_id
                    ORDER BY name
                    """,
                    {"product": product_id, "proj_id": proj_id},
                )
                proj["capabilities"] = parse_rows(caps_result)

                return proj
        except DatabaseError:
            raise
        except Exception as exc:
            raise EcosystemError(f"Failed to load project {slug!r}: {exc}") from exc

    # ── Hierarchy queries ──

    async def get_hierarchy(self, product_id: str) -> dict:
        """Full hierarchy: ecosystems → projects → capability counts."""
        logger.debug("Loading hierarchy for product=%s", product_id)
        async with self._pool.connection() as db:
            eco_result = await db.query(
                """
                SELECT * FROM ecosystem
                WHERE product = <record>$product
                ORDER BY name
                """,
                {"product": product_id},
            )
            ecosystems = parse_rows(eco_result)

            proj_result = await db.query(
                """
                SELECT * FROM project
                WHERE product = <record>$product
                ORDER BY name
                """,
                {"product": product_id},
            )
            projects = parse_rows(proj_result)

            cap_count_result = await db.query(
                """
                SELECT project, count() AS count FROM capability
                WHERE product = <record>$product AND project != NONE
                GROUP BY project
                """,
                {"product": product_id},
            )
            cap_counts = parse_rows(cap_count_result)

        # Build lookup: project_id → capability_count
        count_by_project: dict[str, int] = {}
        for row in cap_counts:
            proj_id = row.get("project")
            if proj_id:
                count_by_project[str(proj_id)] = row.get("count", 0)

        # Build lookup: ecosystem_id → ecosystem dict (with empty projects list)
        eco_by_id: dict[str, dict] = {}
        for eco in ecosystems:
            eco_copy = dict(eco)
            eco_copy["projects"] = []
            eco_by_id[str(eco.get("id"))] = eco_copy

        standalone_projects: list[dict] = []

        for proj in projects:
            proj_copy = dict(proj)
            proj_copy["capability_count"] = count_by_project.get(str(proj.get("id")), 0)
            eco_ref = proj.get("ecosystem")
            if eco_ref and str(eco_ref) in eco_by_id:
                eco_by_id[str(eco_ref)]["projects"].append(proj_copy)
            else:
                standalone_projects.append(proj_copy)

        return {
            "ecosystems": list(eco_by_id.values()),
            "standalone_projects": standalone_projects,
        }
