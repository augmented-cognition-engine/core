"""Tests for the expanded idea state machine (10 primary states)."""

import pytest

from core.engine.ideas.state_machine import VALID_STATES, IdeaStateError, transition

# --- Valid transitions ---


def test_ready_to_speccing():
    assert transition("ready", "speccing") == "speccing"


def test_speccing_to_spec_review():
    assert transition("speccing", "spec_review") == "spec_review"


def test_spec_review_approved_to_planned():
    assert transition("spec_review", "planned") == "planned"


def test_spec_review_rejected_back_to_ready():
    assert transition("spec_review", "ready") == "ready"


def test_planned_to_plan_review():
    assert transition("planned", "plan_review") == "plan_review"


def test_plan_review_approved_to_promoted():
    assert transition("plan_review", "promoted") == "promoted"


def test_plan_review_rejected_back_to_planned():
    assert transition("plan_review", "planned") == "planned"


def test_ready_skip_to_promoted():
    """Low-risk ideas can skip spec/plan and go straight to promoted."""
    assert transition("ready", "promoted") == "promoted"


# --- Invalid transitions ---


def test_speccing_cannot_go_to_promoted():
    with pytest.raises(IdeaStateError):
        transition("speccing", "promoted")


def test_planned_cannot_go_to_promoted():
    with pytest.raises(IdeaStateError):
        transition("planned", "promoted")


def test_spec_review_cannot_go_to_plan_review():
    with pytest.raises(IdeaStateError):
        transition("spec_review", "plan_review")


# --- Archive from any state ---


@pytest.mark.parametrize(
    "state",
    [
        "captured",
        "qualifying",
        "ready",
        "speccing",
        "spec_review",
        "planned",
        "plan_review",
        "promoted",
    ],
)
def test_archive_from_any_non_terminal(state):
    assert transition(state, "archived") == "archived"


# --- Legacy compat ---


def test_legacy_open_to_speccing():
    assert transition("open", "speccing") == "speccing"


def test_new_states_in_valid_states():
    for s in ("speccing", "spec_review", "planned", "plan_review"):
        assert s in VALID_STATES
