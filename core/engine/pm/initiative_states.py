"""Initiative state machine — full lifecycle with decomposition and review gates.

States: planning → decomposing → ready → active → completing → review → completed
Plus: blocked (from active), cancelled (from any non-terminal), failed (terminal).
"""

from __future__ import annotations


class InitiativeStateError(Exception):
    """Raised when an invalid initiative state transition is attempted."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid initiative transition: {current} -> {target}")


VALID_STATES = {
    "planning",
    "decomposing",
    "ready",
    "active",
    "blocked",
    "completing",
    "review",
    "completed",
    "failed",
    "cancelled",
    # Legacy compat
    "paused",
}

TRANSITIONS: dict[str, set[str]] = {
    "planning": {"decomposing", "cancelled"},
    "decomposing": {"ready", "planning", "cancelled"},
    "ready": {"active", "cancelled"},
    "active": {"blocked", "completing", "cancelled"},
    "blocked": {"active", "cancelled"},
    "completing": {"review", "active", "cancelled"},
    "review": {"completed", "active", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    # Legacy compat — paused behaves like blocked
    "paused": {"active", "cancelled"},
}

# States that represent a gate waiting for review
GATE_STATES = {"review"}


def transition(current: str, target: str) -> str:
    """Validate and return the target state.

    Raises:
        InitiativeStateError: If the transition is not allowed.
    """
    if current not in VALID_STATES:
        raise InitiativeStateError(current, target)
    if target not in TRANSITIONS.get(current, set()):
        raise InitiativeStateError(current, target)
    return target
