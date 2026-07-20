# engine/conductor/state_machine.py
"""Capability lifecycle state machine.

Tracks per capability x dimension. Follows the _StateMachine base pattern
from engine/live/state_machines.py.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CLT_TRANSITIONS: dict[str, set[str]] = {
    "unassessed": {"gap_identified", "met", "exceeded"},
    "gap_identified": {"spec_pending", "met"},
    "spec_pending": {"spec_review", "gap_identified"},
    "spec_review": {"executing", "spec_pending", "gap_identified"},
    "executing": {"verifying", "needs_rework", "gap_identified"},
    "verifying": {"met", "needs_rework", "exceeded"},
    "needs_rework": {"spec_pending", "gap_identified"},
    "met": {"gap_identified", "exceeded"},
    "exceeded": {"gap_identified", "met"},
}

ALL_STATES = set(_CLT_TRANSITIONS.keys())


class InvalidLifecycleTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid lifecycle transition: {current} -> {target}")


class CapabilityLifecycleMachine:
    """In-memory state machine for a single lifecycle track.

    All persistent state lives in the capability_lifecycle_track table.
    This class validates transitions only.
    """

    def __init__(self, initial: str) -> None:
        if initial not in _CLT_TRANSITIONS:
            raise ValueError(f"Unknown lifecycle state: {initial!r}. Valid: {sorted(ALL_STATES)}")
        self._state = initial

    @property
    def state(self) -> str:
        return self._state

    def transition(self, target: str) -> str:
        if target not in _CLT_TRANSITIONS.get(self._state, set()):
            raise InvalidLifecycleTransition(self._state, target)
        self._state = target
        return target

    def can_transition(self, target: str) -> bool:
        return target in _CLT_TRANSITIONS.get(self._state, set())

    def valid_transitions(self) -> list[str]:
        """Return the list of states reachable from the current state."""
        return sorted(_CLT_TRANSITIONS.get(self._state, set()))

    def get_stats(self) -> dict:
        """Return state machine health metrics for observability."""
        return {
            "state": self._state,
            "valid_transitions": self.valid_transitions(),
            "is_terminal": not bool(_CLT_TRANSITIONS.get(self._state)),
        }
