# tests/test_conductor_state_machine.py
"""Tests for CapabilityLifecycleMachine."""

import pytest

from core.engine.conductor.state_machine import (
    CapabilityLifecycleMachine,
    InvalidLifecycleTransition,
)


def test_initial_state():
    m = CapabilityLifecycleMachine("unassessed")
    assert m.state == "unassessed"


def test_invalid_initial_state():
    with pytest.raises(ValueError, match="Unknown"):
        CapabilityLifecycleMachine("bogus")


def test_valid_transition_gap_identified():
    m = CapabilityLifecycleMachine("unassessed")
    m.transition("gap_identified")
    assert m.state == "gap_identified"


def test_valid_transition_met():
    m = CapabilityLifecycleMachine("unassessed")
    m.transition("met")
    assert m.state == "met"


def test_invalid_transition_raises():
    m = CapabilityLifecycleMachine("unassessed")
    with pytest.raises(InvalidLifecycleTransition):
        m.transition("executing")


def test_can_transition_true():
    m = CapabilityLifecycleMachine("gap_identified")
    assert m.can_transition("spec_pending") is True


def test_can_transition_false():
    m = CapabilityLifecycleMachine("gap_identified")
    assert m.can_transition("verifying") is False


def test_regression_met_to_gap():
    m = CapabilityLifecycleMachine("met")
    m.transition("gap_identified")
    assert m.state == "gap_identified"


def test_full_happy_path():
    m = CapabilityLifecycleMachine("unassessed")
    for state in ["gap_identified", "spec_pending", "spec_review", "executing", "verifying", "met"]:
        m.transition(state)
    assert m.state == "met"


def test_rework_path():
    m = CapabilityLifecycleMachine("verifying")
    m.transition("needs_rework")
    m.transition("spec_pending")
    assert m.state == "spec_pending"


def test_exceeded_from_verifying():
    m = CapabilityLifecycleMachine("verifying")
    m.transition("exceeded")
    assert m.state == "exceeded"
