# engine/pm/decompose.py
"""LLM-powered decomposition engine for the Autonomous PM.

Decomposes initiatives into milestones, and milestones into work items.
Uses deliberative orchestrator mode (primary model, not budget).
THE PM NEVER EXECUTES WORK — it decomposes, assigns, tracks, validates.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

VALID_ARCHETYPES = {"creator", "analyst", "executor", "researcher", "advisor", "sentinel"}
VALID_MODES = {"reactive", "deliberative", "exploratory", "conversational", "procedural", "reflective"}

MIN_MILESTONES = 3
MAX_MILESTONES = 6


class PMDecomposer:
    """Decompose initiatives into milestones and milestones into work items."""

    def __init__(self, db_pool=None, llm=None):
        self._db_pool = db_pool
        self._llm = llm

    def _pool(self):
        if self._db_pool:
            return self._db_pool
        from core.engine.core.db import pool

        return pool

    def _get_llm(self):
        if self._llm:
            return self._llm
        from core.engine.core.llm import llm

        return llm

    async def _load_intelligence_context(self, product_id: str, domain_path: str) -> str:
        """Load relevant intelligence for decomposition context."""
        try:
            # discipline is a flat string; support legacy dotted domain_path by taking first segment
            discipline = domain_path.split(".")[0] if domain_path else ""
            async with self._pool().connection() as db:
                result = await db.query(
                    """
                    SELECT content, confidence, insight_type FROM insight
                    WHERE product = <record>$product
                      AND (tags CONTAINS $discipline OR domain_path CONTAINS $discipline)
                      AND status = 'active'
                      AND confidence >= 0.5
                    ORDER BY confidence DESC
                    LIMIT 20
                    """,
                    {"product": product_id, "discipline": discipline},
                )
                rows = result[0] if result and isinstance(result[0], list) else (result or [])
                if rows:
                    lines = [
                        f"- [{r.get('insight_type', '?')}] {r.get('content', '')} (conf: {r.get('confidence', 0)})"
                        for r in rows
                    ]
                    return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to load intelligence for decomposition: %s", e)
        return "(no intelligence available)"

    async def decompose_initiative(
        self,
        title: str,
        description: str,
        product_id: str,
        domain_path: str,
        success_criteria: list[str] | None = None,
    ) -> list[dict]:
        """Decompose an initiative into 3-6 milestones via LLM (deliberative mode)."""
        intel_context = await self._load_intelligence_context(product_id, domain_path)

        prompt = f"""You are a project manager decomposing an initiative into milestones.
Think step by step. Consider dependencies, risks, and the right sequencing.

## Initiative
Title: {title}
Description: {description}
Domain: {domain_path}
{f"Success Criteria: {', '.join(success_criteria)}" if success_criteria else ""}

## Available Intelligence
{intel_context}

## Instructions
Decompose this initiative into 3-6 milestones in logical sequence.
For each milestone provide:
- title: Clear milestone name (e.g., "M1: Design token schema")
- description: What this milestone achieves
- done_criteria: Array of specific, measurable criteria (how do we know it's done?)
- requires_approval: boolean — does this need human sign-off before proceeding?
- sequence: integer (1, 2, 3...)

Return JSON: {{"milestones": [...]}}"""

        llm = self._get_llm()
        result = await llm.complete_json(prompt)

        milestones = result.get("milestones", [])

        # Enforce bounds
        if len(milestones) > MAX_MILESTONES:
            milestones = milestones[:MAX_MILESTONES]

        # Ensure sequential numbering
        for i, ms in enumerate(milestones):
            ms["sequence"] = i + 1
            ms.setdefault("done_criteria", [])
            ms.setdefault("requires_approval", False)
            ms.setdefault("description", "")

        return milestones

    async def decompose_milestone(
        self,
        milestone_title: str,
        milestone_description: str,
        done_criteria: list[str],
        initiative_title: str,
        product_id: str,
        domain_path: str,
    ) -> list[dict]:
        """Decompose a milestone into work items via LLM (deliberative mode)."""
        intel_context = await self._load_intelligence_context(product_id, domain_path)

        prompt = f"""You are a project manager decomposing a milestone into concrete work items.
Think step by step. Identify what can run in parallel vs. what has dependencies.

## Initiative
Title: {initiative_title}

## Milestone
Title: {milestone_title}
Description: {milestone_description}
Done Criteria: {", ".join(done_criteria)}
Domain: {domain_path}

## Available Intelligence
{intel_context}

## Instructions
Break this milestone into concrete work items. For each work item provide:
- title: Clear work item name
- description: What this work item delivers
- archetype: One of: creator, analyst, executor, researcher, advisor, sentinel
- mode: One of: reactive, deliberative, exploratory, conversational, procedural, reflective
- reasoning: One sentence explaining why you chose this archetype + mode for THIS task
- skill: Optional skill slug (e.g., "deep-research", "brainstorm") or null
- domain_path: Domain path for intelligence loading
- parallel_group: Integer — items with same group can run concurrently
- files_touched: Array of file paths this item will likely modify
- requires_human: boolean — does this need a human to do the work?

IMPORTANT: Two items can be parallel if they touch different files and don't depend on each other's output.
Items in a later parallel_group depend on earlier groups completing first.

Return JSON: {{"work_items": [...]}}"""

        llm = self._get_llm()
        result = await llm.complete_json(prompt)

        work_items = result.get("work_items", [])

        # Validate and fix each work item
        for wi in work_items:
            if wi.get("archetype") not in VALID_ARCHETYPES:
                wi["archetype"] = "executor"
            if wi.get("mode") not in VALID_MODES:
                wi["mode"] = "reactive"
            wi.setdefault("parallel_group", 1)
            wi.setdefault("files_touched", [])
            wi.setdefault("requires_human", False)
            wi.setdefault("skill", None)
            wi.setdefault("domain_path", domain_path)
            wi.setdefault("description", "")
            wi.setdefault("reasoning", "")

        return work_items
