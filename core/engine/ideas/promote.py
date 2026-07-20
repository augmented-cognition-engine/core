# engine/ideas/promote.py
"""Promote ideas to tasks or initiatives with context carryover."""

from __future__ import annotations

import logging
from typing import Any

from core.engine.core.db import parse_one

logger = logging.getLogger(__name__)


async def promote_to_task(
    db: Any,
    idea: dict,
    product_id: str,
    user_id: str = "user:default",
) -> str:
    """Create a task from an idea. Returns task ID."""
    brief = idea.get("brief") or {}
    description = brief.get("what") or idea.get("raw_input", "")
    if brief.get("approach"):
        description += f"\n\nApproach: {brief['approach']}"
    workspace_id = idea.get("workspace") or "workspace:default"

    result = await db.query(
        """
        CREATE task SET
            product = <record>$product,
            user = <record>$user,
            description = $desc,
            status = 'pending',
            source_idea = $idea_id,
            created_at = time::now()
        """,
        {
            "product": product_id,
            "workspace": workspace_id,
            "user": user_id,
            "desc": description,
            "idea_id": idea["id"],
        },
    )
    row = parse_one(result)
    task_id = str(row.get("id", "") if row else "")

    await db.query(
        "UPDATE <record>$id SET status = 'promoted'",
        {"id": idea["id"]},
    )

    logger.info("Promoted idea %s to task %s", idea["id"], task_id)
    return task_id


async def promote_to_initiative(
    db: Any,
    idea: dict,
    product_id: str,
    user_id: str = "user:default",
) -> str:
    """Create an initiative from an idea. Returns initiative ID."""
    brief = idea.get("brief") or {}
    title = idea.get("title") or idea.get("raw_input", "")[:80]
    description = brief.get("what") or idea.get("raw_input", "")
    if brief.get("why"):
        description += f"\n\nWhy: {brief['why']}"
    if brief.get("approach"):
        description += f"\n\nApproach: {brief['approach']}"
    workspace_id = idea.get("workspace") or "workspace:default"

    result = await db.query(
        """
        CREATE initiative SET
            product = <record>$product,
            user = <record>$user,
            title = $title,
            description = $desc,
            source = 'idea',
            source_idea = $idea_id,
            owner = <record>$user,
            status = 'planning',
            priority = 'medium',
            created_at = time::now()
        """,
        {
            "product": product_id,
            "workspace": workspace_id,
            "user": user_id,
            "title": title,
            "desc": description,
            "idea_id": idea["id"],
        },
    )
    row = parse_one(result)
    init_id = str(row.get("id", "") if row else "")

    await db.query(
        "UPDATE <record>$id SET status = 'promoted'",
        {"id": idea["id"]},
    )

    logger.info("Promoted idea %s to initiative %s", idea["id"], init_id)
    return init_id
