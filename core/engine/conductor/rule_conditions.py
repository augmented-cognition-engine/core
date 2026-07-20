# engine/conductor/rule_conditions.py
"""Condition evaluator for conductor rules.

Evaluates an array of condition objects against a context dict.
All conditions must pass (AND semantics).
Supports ${path.to.value} interpolation from context.
"""

from __future__ import annotations

import re
from typing import Any

_INTERPOLATION_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_path(obj: dict, path: str) -> Any:
    """Resolve a dotted path like 'payload.score' from a nested dict."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _interpolate(value: Any, context: dict) -> Any:
    """Replace ${path} references in a value with resolved context values."""
    if not isinstance(value, str):
        return value
    match = _INTERPOLATION_RE.fullmatch(value)
    if match:
        # Full interpolation — return the resolved value (preserves type)
        return _resolve_path(context, match.group(1))

    # Partial interpolation (string contains ${...} among other text)
    def _replace(m: re.Match) -> str:
        resolved = _resolve_path(context, m.group(1))
        return str(resolved) if resolved is not None else m.group(0)

    return _INTERPOLATION_RE.sub(_replace, value)


def _evaluate_one(condition: dict, context: dict) -> bool:
    """Evaluate a single condition against the context."""
    field_path = condition.get("field", "")
    op = condition.get("op", "eq")
    raw_value = condition.get("value")

    actual = _resolve_path(context, field_path)
    if actual is None:
        return False

    expected = _interpolate(raw_value, context)

    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "lt":
        return actual < expected
    if op == "gt":
        return actual > expected
    if op == "le":
        return actual <= expected
    if op == "ge":
        return actual >= expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "contains":
        return expected in actual if isinstance(actual, (list, set, str)) else False
    if op == "matches":
        return bool(re.search(str(expected), str(actual)))

    return False


def evaluate_conditions(conditions: list[dict], context: dict) -> bool:
    """Evaluate all conditions. Returns True only if ALL pass."""
    if not conditions:
        return True
    return all(_evaluate_one(c, context) for c in conditions)
