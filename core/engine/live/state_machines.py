"""State machines for LIVE layer entities.

Each machine defines valid states and transitions. Every transition
emits an event on the main bus. Invalid transitions raise InvalidTransition.
"""

from __future__ import annotations


class InvalidTransition(Exception):
    def __init__(self, entity: str, current: str, target: str) -> None:
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(f"Invalid {entity} transition: {current} -> {target}")


_AGENT_SESSION_TRANSITIONS: dict[str, set[str]] = {
    "starting": {"active", "abandoned"},
    "active": {"blocked", "completing", "abandoned"},
    "blocked": {"active", "abandoned"},
    "completing": {"done", "failed", "abandoned"},
    "done": set(),
    "failed": set(),
    "abandoned": set(),
}

_ACTIVE_EDIT_TRANSITIONS: dict[str, set[str]] = {
    "claimed": {"editing", "abandoned"},
    "editing": {"committing", "conflict", "abandoned"},
    "committing": {"released", "abandoned"},
    "conflict": {"resolved", "abandoned"},
    "resolved": {"released", "abandoned"},
    "released": set(),
    "abandoned": set(),
}

_RESOURCE_LOCK_TRANSITIONS: dict[str, set[str]] = {
    "acquired": {"held", "released"},
    "held": {"releasing", "stolen", "expired"},
    "releasing": {"released"},
    "released": set(),
    "stolen": set(),
    "expired": set(),
}


class _StateMachine:
    """Base state machine with transition validation."""

    _transitions: dict[str, set[str]]
    _entity_name: str

    def __init__(self, initial: str) -> None:
        if initial not in self._transitions:
            raise ValueError(f"Unknown {self._entity_name} state: {initial}")
        self._state = initial

    @property
    def state(self) -> str:
        return self._state

    def transition(self, target: str) -> str:
        if target not in self._transitions.get(self._state, set()):
            raise InvalidTransition(self._entity_name, self._state, target)
        self._state = target
        return target

    def can_transition(self, target: str) -> bool:
        return target in self._transitions.get(self._state, set())


class AgentSessionMachine(_StateMachine):
    _transitions = _AGENT_SESSION_TRANSITIONS
    _entity_name = "agent_session"


class ActiveEditMachine(_StateMachine):
    _transitions = _ACTIVE_EDIT_TRANSITIONS
    _entity_name = "active_edit"


class ResourceLockMachine(_StateMachine):
    _transitions = _RESOURCE_LOCK_TRANSITIONS
    _entity_name = "resource_lock"


# ── ATC Flight ────────────────────────────────────────────────────────────

_ATC_FLIGHT_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"cleared", "holding", "cancelled"},
    "cleared": {"active", "holding", "cancelled"},
    "active": {"landing", "holding", "cancelled", "failed"},
    "holding": {"cleared", "cancelled"},
    "landing": {"landed", "failed"},
    "landed": set(),
    "failed": {"planning"},  # can retry
    "cancelled": set(),
}


class ATCFlightMachine(_StateMachine):
    _transitions = _ATC_FLIGHT_TRANSITIONS
    _entity_name = "atc_flight"
