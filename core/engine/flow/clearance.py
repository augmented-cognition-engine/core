# engine/flow/clearance.py
"""Clearance filter logic for intelligence loading.

Pure functions — no DB access. Given a clearance level and requester context,
determines visibility and generates SQL filter clauses.
"""

from __future__ import annotations

import re

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_.:*-]*$")


def _validate_slug(value: str | None, fallback: str = "unknown") -> str | None:
    """Validate a slug against the allowed pattern. Returns fallback for invalid input."""
    if not value:
        return fallback if fallback else None
    if not _SLUG_PATTERN.match(value):
        return fallback if fallback else None
    return value


def is_visible(
    clearance: str,
    task_domain: str,
    task_specialty: str | None,
    insight_domain: str,
    insight_specialty: str | None = None,
) -> bool:
    """Check if an insight with given clearance is visible to a task's context."""
    if clearance == "open":
        return True
    if clearance in ("domain", "restricted"):
        return task_domain == insight_domain
    if clearance == "sealed":
        return task_specialty is not None and insight_specialty is not None and task_specialty == insight_specialty
    return False


def is_visible_via_synapse(clearance: str) -> bool:
    """Check if an insight can cross synapse boundaries. Only open insights flow."""
    return clearance == "open"


def clearance_where_clause(
    task_domain: str,
    task_specialty: str | None = None,
) -> tuple[str, dict]:
    """Generate a SurrealDB WHERE clause fragment for clearance filtering.

    Returns (clause_string, params_dict) with $-placeholders for safe parameterized queries.
    Input validation rejects non-slug characters.
    """
    task_domain = _validate_slug(task_domain, "unknown")
    if task_specialty:
        task_specialty = _validate_slug(task_specialty, fallback=None)

    params = {"task_domain": task_domain}
    parts = ["clearance = 'open'"]
    parts.append("(clearance IN ['domain', 'restricted'] AND domain.slug = <string>$task_domain)")

    if task_specialty:
        parts.append("(clearance = 'sealed' AND specialty = $task_specialty)")
        params["task_specialty"] = task_specialty

    return f"({' OR '.join(parts)})", params


def synaptic_clearance_filter() -> str:
    """WHERE clause for synaptic loading — only open insights cross boundaries."""
    return "clearance = 'open'"
