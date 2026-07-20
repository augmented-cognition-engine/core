"""Template instantiation — variable substitution + initiative creation.

Accepts variable values, substitutes {{var}} across all milestone/work_item
templates, creates an initiative via the PM pipeline with source='template'.
"""

from __future__ import annotations

import logging
import re

from core.engine.core.db import pool
from core.engine.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class TemplateVariableError(Exception):
    """Raised when a required variable is missing."""


def _validate_template_inputs(playbook: dict, product_id: str, user_id: str) -> None:
    """Validate template instantiation inputs before substitution and DB writes.

    Raises ValidationError for missing product_id/user_id format or an empty
    playbook, preventing partial initiative creation that would leave orphaned
    milestones in the DB.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id: {product_id!r}")
    if not user_id or not user_id.strip():
        raise ValidationError("user_id must be non-empty")
    if not playbook or not isinstance(playbook, dict):
        raise ValidationError("playbook must be a non-empty dict")


def substitute_variables(text: str, variables: dict[str, str]) -> str:
    """Replace all {{var}} placeholders in text with variable values."""

    def replacer(match):
        var_name = match.group(1)
        if var_name in variables:
            return variables[var_name]
        return match.group(0)  # Leave unresolved

    return VAR_PATTERN.sub(replacer, text)


def substitute_in_milestones(milestones: list[dict], variables: dict[str, str]) -> list[dict]:
    """Substitute variables across all milestone and work item templates."""
    result = []
    for ms in milestones:
        new_ms = {
            "title": substitute_variables(ms.get("title", ""), variables),
            "description": substitute_variables(ms.get("description", ""), variables),
            "done_criteria": [substitute_variables(c, variables) for c in ms.get("done_criteria", [])],
            "requires_approval": ms.get("requires_approval", False),
            "work_items": [],
        }
        for wi in ms.get("work_items", []):
            new_ms["work_items"].append(
                {
                    "title": substitute_variables(wi.get("title", ""), variables),
                    "description": substitute_variables(wi.get("description", ""), variables),
                    "archetype": wi.get("archetype", "executor"),
                    "mode": wi.get("mode", "reactive"),
                    "domain_path": wi.get("domain_path", ""),
                    "requires_human": wi.get("requires_human", False),
                }
            )
        result.append(new_ms)
    return result


async def instantiate_template(
    playbook: dict,
    variables: dict[str, str],
    user_id: str,
    product_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Create an initiative from a template with variable substitution.

    Raises:
        TemplateVariableError: If a required variable is missing.
    """
    _validate_template_inputs(playbook, product_id, user_id)
    # Check required variables
    for var_def in playbook.get("variables", []):
        var_name = var_def["name"]
        if var_name not in variables:
            if var_def.get("default") is not None:
                variables[var_name] = var_def["default"]
            else:
                raise TemplateVariableError(f"Missing required variable: {var_name}")

    # Substitute variables in milestones
    milestones = substitute_in_milestones(playbook.get("milestones", []), variables)

    # Substitute in description
    description = substitute_variables(playbook.get("description", ""), variables)

    async with pool.connection() as db:
        # Create initiative
        result = await db.query(
            """
            CREATE initiative SET
                product = <record>$product,
                user = <record>$user,
                title = $title,
                description = $description,
                source = $source,
                playbook = $playbook_id,
                milestones = $milestones,
                owner = <record>$user,
                status = 'planning',
                created_at = time::now()
            """,
            {
                "product": product_id,
                "workspace": workspace_id,
                "user": user_id,
                "title": playbook.get("name", "Untitled"),
                "description": description,
                "source": "template",
                "playbook_id": playbook.get("id"),
                "milestones": milestones,
            },
        )
        rows = result[0] if result and isinstance(result[0], list) else (result or [])

        # Update times_used
        await db.query(
            "UPDATE <record>$id SET times_used = times_used + 1",
            {"id": playbook.get("id")},
        )

    return (
        rows[0]
        if rows
        else {
            "source": "template",
            "playbook": playbook.get("id"),
            "title": playbook.get("name"),
        }
    )
