"""Idea state machine — full lifecycle with spec and plan review gates.

Primary states: captured → qualifying → ready → speccing → spec_review → planned → plan_review → promoted
Plus: archived (from any non-terminal state)
Legacy states (open, incubating, active, completed, proposed) map to open-like transitions.
"""

from __future__ import annotations


class IdeaStateError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid idea transition: {current} -> {target}")


VALID_STATES = {
    "captured",
    "qualifying",
    "ready",
    "speccing",
    "spec_review",
    "planned",
    "plan_review",
    "promoted",
    "archived",
    # Legacy compat
    "open",
    "incubating",
    "active",
    "completed",
    "proposed",
}

# Map of current_state -> set of allowed target states
TRANSITIONS: dict[str, set[str]] = {
    "captured": {"qualifying", "ready", "archived"},
    "qualifying": {"ready", "captured", "archived"},
    "ready": {"speccing", "promoted", "archived"},
    "speccing": {"spec_review", "ready", "archived"},
    "spec_review": {"planned", "ready", "archived"},
    "planned": {"plan_review", "archived"},
    "plan_review": {"promoted", "planned", "archived"},
    "promoted": {"archived"},
    "archived": set(),
    # Legacy compat — allow forward transitions
    "open": {"qualifying", "ready", "speccing", "promoted", "archived"},
    "incubating": {"ready", "speccing", "promoted", "archived"},
    "proposed": {"ready", "speccing", "promoted", "archived"},
    "active": {"promoted", "archived"},
    "completed": {"archived"},
}

# States that represent a gate waiting for review
GATE_STATES = {"spec_review", "plan_review"}


def transition(current: str, target: str) -> str:
    """Validate and return the target state.

    Raises:
        IdeaStateError: If the transition is not allowed.
    """
    if current not in VALID_STATES:
        raise IdeaStateError(current, target)
    if target not in TRANSITIONS.get(current, set()):
        raise IdeaStateError(current, target)
    return target
