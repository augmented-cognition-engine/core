"""Tests for the initiative state machine (9 states)."""

import pytest

from core.engine.pm.initiative_states import (
    GATE_STATES,
    InitiativeStateError,
    transition,
)

# --- Valid transitions ---


def test_planning_to_decomposing():
    assert transition("planning", "decomposing") == "decomposing"


def test_decomposing_to_ready():
    assert transition("decomposing", "ready") == "ready"


def test_ready_to_active():
    assert transition("ready", "active") == "active"


def test_active_to_blocked():
    assert transition("active", "blocked") == "blocked"


def test_active_to_completing():
    assert transition("active", "completing") == "completing"


def test_blocked_to_active():
    assert transition("blocked", "active") == "active"


def test_completing_to_review():
    assert transition("completing", "review") == "review"


def test_completing_back_to_active():
    assert transition("completing", "active") == "active"


def test_review_to_completed():
    assert transition("review", "completed") == "completed"


def test_review_back_to_active():
    assert transition("review", "active") == "active"


# --- Cancel from any active state ---


@pytest.mark.parametrize(
    "state",
    [
        "planning",
        "decomposing",
        "ready",
        "active",
        "blocked",
        "completing",
        "review",
    ],
)
def test_cancel_from_any_active_state(state):
    assert transition(state, "cancelled") == "cancelled"


# --- Terminal states ---


def test_completed_is_terminal():
    with pytest.raises(InitiativeStateError):
        transition("completed", "active")


def test_failed_is_terminal():
    with pytest.raises(InitiativeStateError):
        transition("failed", "active")


def test_cancelled_is_terminal():
    with pytest.raises(InitiativeStateError):
        transition("cancelled", "active")


# --- Invalid transitions ---


def test_planning_cannot_go_to_active():
    with pytest.raises(InitiativeStateError):
        transition("planning", "active")


def test_ready_cannot_go_to_completing():
    with pytest.raises(InitiativeStateError):
        transition("ready", "completing")


# --- Gate states ---


def test_gate_states():
    assert GATE_STATES == {"review"}


# --- Legacy compat ---


def test_paused_maps_to_blocked():
    """Legacy 'paused' state is treated like 'blocked'."""
    assert transition("paused", "active") == "active"
