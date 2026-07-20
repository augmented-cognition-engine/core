# engine/conductor/template_resolver.py
"""Quality template resolution with layered inheritance.

Resolution order (most specific wins):
1. capability_type — matched by capability tags
2. project — per-project defaults
3. org — org-wide defaults
4. universal — ACE defaults (hardcoded fallback)
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows
from core.engine.product.seed_packs import ALL_DISCIPLINES

logger = logging.getLogger(__name__)

# Universal defaults — ship with ACE. Used when no template exists in DB.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "security": 0.6,
    "testing": 0.5,
    "error_handling": 0.5,
    "architecture": 0.4,
    "api_design": 0.4,
    "observability": 0.4,
    "data_modeling": 0.4,
    "business_logic": 0.4,
    "integration": 0.4,
    "performance": 0.3,
    "ux": 0.3,
    "devops": 0.3,
    "data": 0.3,
    "accessibility": 0.3,
    "documentation": 0.3,
    "configuration": 0.3,
    "deployment": 0.3,
    "versioning": 0.3,
    "code_conventions": 0.3,
    "dependency_management": 0.3,
}

DEFAULT_STRETCH: dict[str, float] = {
    "security": 0.8,
    "testing": 0.7,
    "error_handling": 0.7,
    "architecture": 0.6,
    "api_design": 0.6,
    "observability": 0.6,
}

_TEMPLATE_QUERY = """
    SELECT threshold, stretch_target, weight, checklist, scope, org
    FROM quality_template
    WHERE active = true
      AND dimension = <string>$dim
      AND scope = <string>$scope
      AND scope_value = <string>$scope_value
    ORDER BY org DESC
    LIMIT 1
"""

_ORG_TEMPLATE_QUERY = """
    SELECT threshold, stretch_target, weight, checklist, scope
    FROM quality_template
    WHERE active = true
      AND dimension = <string>$dim
      AND scope = 'org'
      AND product = <record>$product
    LIMIT 1
"""

_UNIVERSAL_TEMPLATE_QUERY = """
    SELECT threshold, stretch_target, weight, checklist, scope
    FROM quality_template
    WHERE active = true
      AND dimension = <string>$dim
      AND scope = 'universal'
      AND product IS NONE
    LIMIT 1
"""


class TemplateResolver:
    """Resolve the most specific quality template for a capability x dimension."""

    def __init__(self, db_pool) -> None:
        self._pool = db_pool

    def _validate_dimension(self, dimension: str) -> None:
        """Validate that dimension is a recognised ACE discipline.

        Raises ValueError if the dimension is unknown, preventing typos from
        silently resolving to the universal default and masking data errors.
        """
        if dimension not in ALL_DISCIPLINES:
            raise ValueError(f"Unknown dimension {dimension!r}. Valid: {ALL_DISCIPLINES}")

    async def resolve(self, capability: dict, dimension: str, product_id: str) -> dict:
        """Return the resolved template dict with keys: threshold, stretch_target, weight, checklist, scope.

        Resolution order (most specific wins):
            1. capability_type tag → 2. project → 3. org → 4. universal DB → 5. hardcoded default
        """
        self._validate_dimension(dimension)
        slug = capability.get("slug", "?")

        # 1. Check capability_type templates (by tag)
        for tag in capability.get("tags") or []:
            tmpl = await self._query_template("capability_type", tag, dimension, product_id)
            if tmpl:
                logger.debug("Template resolved: cap=%s dim=%s scope=capability_type/%s", slug, dimension, tag)
                return tmpl

        # 2. Check project template
        project = capability.get("project")
        if project:
            project_slug = project if isinstance(project, str) else str(project)
            tmpl = await self._query_template("project", project_slug, dimension, product_id)
            if tmpl:
                logger.debug("Template resolved: cap=%s dim=%s scope=project/%s", slug, dimension, project_slug)
                return tmpl

        # 3. Check org template
        tmpl = await self._query_org_template(dimension, product_id)
        if tmpl:
            logger.debug("Template resolved: cap=%s dim=%s scope=org", slug, dimension)
            return tmpl

        # 4. Check universal template in DB
        tmpl = await self._query_universal_template(dimension)
        if tmpl:
            logger.debug("Template resolved: cap=%s dim=%s scope=universal_db", slug, dimension)
            return tmpl

        # 5. Hardcoded fallback
        logger.debug("Template fallback: cap=%s dim=%s scope=universal_default", slug, dimension)
        return {
            "threshold": DEFAULT_THRESHOLDS.get(dimension, 0.3),
            "stretch_target": DEFAULT_STRETCH.get(dimension),
            "weight": 1.0,
            "checklist": None,
            "scope": "universal_default",
        }

    async def _query_template(self, scope: str, scope_value: str, dimension: str, product_id: str) -> dict | None:
        async with self._pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    _TEMPLATE_QUERY,
                    {"dim": dimension, "scope": scope, "scope_value": scope_value, "product": product_id},
                )
            )
        return rows[0] if rows else None

    async def _query_org_template(self, dimension: str, product_id: str) -> dict | None:
        async with self._pool.connection() as db:
            rows = parse_rows(await db.query(_ORG_TEMPLATE_QUERY, {"dim": dimension, "product": product_id}))
        return rows[0] if rows else None

    async def _query_universal_template(self, dimension: str) -> dict | None:
        async with self._pool.connection() as db:
            rows = parse_rows(await db.query(_UNIVERSAL_TEMPLATE_QUERY, {"dim": dimension}))
        return rows[0] if rows else None
