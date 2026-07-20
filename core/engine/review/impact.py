# engine/review/impact.py
"""PR impact analysis — maps changed files to capabilities, dependents, and quality scores."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)


class PRImpactAnalyzer:
    """Query the ACE code graph to determine the blast radius of a PR's changes."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def affected_capabilities(
        self,
        changed_paths: list[str],
        product_id: str = "product:platform",
    ) -> list[dict]:
        """Find capabilities affected by changed files via ``realizes`` edges.

        Uses ``graph_file → realizes → capability`` edges to map file paths to
        product capabilities.

        Args:
            changed_paths: List of file paths changed in the PR.
            product_id: Org record ID (e.g. ``"product:default"``).

        Returns:
            List of ``{"capability_slug": ..., "capability_name": ...}`` dicts,
            or an empty list when *changed_paths* is empty.
        """
        if not changed_paths:
            return []

        query = """
            SELECT out.slug AS capability_slug, out.name AS capability_name
            FROM realizes WHERE in.path IN $paths
            GROUP BY capability_slug, capability_name
        """
        async with pool.connection() as db:
            result = await db.query(query, {"paths": changed_paths})
        return parse_rows(result)

    async def dependent_files(
        self,
        changed_paths: list[str],
        min_strength: float = 0.5,
    ) -> list[dict]:
        """Find files that frequently co-change with the given paths.

        Uses ``related_to`` edges filtered by a minimum co-change *strength*
        (0.0–1.0).

        Args:
            changed_paths: List of file paths changed in the PR.
            min_strength: Minimum edge strength threshold (default 0.5).

        Returns:
            List of ``{"path": ..., "strength": ...}`` dicts ordered by
            strength descending, capped at 20 results.
        """
        if not changed_paths:
            return []

        query = """
            SELECT out.path AS path, related_to.strength AS strength
            FROM related_to WHERE in.path IN $paths AND strength >= $min_strength
            ORDER BY strength DESC LIMIT 20
        """
        async with pool.connection() as db:
            result = await db.query(query, {"paths": changed_paths, "min_strength": min_strength})
        return parse_rows(result)

    async def quality_scores(
        self,
        capability_slugs: list[str],
        product_id: str = "product:platform",
    ) -> list[dict]:
        """Fetch current quality scores for a set of capabilities.

        Args:
            capability_slugs: List of capability slug strings.
            product_id: Org record ID (e.g. ``"product:default"``).

        Returns:
            List of ``{"slug": ..., "dimension": ..., "score": ...}`` dicts
            ordered by score ascending (lowest quality first).
        """
        if not capability_slugs:
            return []

        query = """
            SELECT capability.slug AS slug, dimension, score
            FROM capability_quality
            WHERE capability.slug IN $slugs AND capability.product = <record>$product
            ORDER BY score ASC
        """
        async with pool.connection() as db:
            result = await db.query(query, {"slugs": capability_slugs, "product": product_id})
        return parse_rows(result)

    async def full_impact(
        self,
        changed_paths: list[str],
        product_id: str = "product:platform",
    ) -> dict:
        """Run a full impact analysis for a set of changed paths.

        Combines affected capabilities, dependent files, and quality scores
        into a single result, and surfaces risk flags for any dimension
        scoring below 0.5.

        Args:
            changed_paths: List of file paths changed in the PR.
            product_id: Org record ID (e.g. ``"product:default"``).

        Returns:
            Dict with keys:
            - ``affected_capabilities``: list of capability dicts
            - ``dependent_files``: list of co-change file dicts
            - ``quality_scores``: list of quality score dicts
            - ``risk_flags``: list of human-readable risk strings for scores < 0.5
        """
        caps = await self.affected_capabilities(changed_paths, product_id=product_id)
        deps = await self.dependent_files(changed_paths)

        slugs = [c["capability_slug"] for c in caps if c.get("capability_slug")]
        scores = await self.quality_scores(slugs, product_id=product_id) if slugs else []

        risk_flags: list[str] = [
            f"{s['slug']} / {s['dimension']} quality is low ({s['score']:.2f})"
            for s in scores
            if isinstance(s.get("score"), (int, float)) and s["score"] < 0.5
        ]

        return {
            "affected_capabilities": caps,
            "dependent_files": deps,
            "quality_scores": scores,
            "risk_flags": risk_flags,
        }
