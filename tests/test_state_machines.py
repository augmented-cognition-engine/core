import pytest

from core.engine.live.state_machines import (
    ActiveEditMachine,
    AgentSessionMachine,
    InvalidTransition,
    ResourceLockMachine,
)


class TestAgentSessionMachine:
    def test_valid_starting_to_active(self):
        m = AgentSessionMachine("starting")
        assert m.transition("active") == "active"
        assert m.state == "active"

    def test_valid_active_to_blocked(self):
        m = AgentSessionMachine("active")
        assert m.transition("blocked") == "blocked"

    def test_valid_blocked_to_active(self):
        m = AgentSessionMachine("blocked")
        assert m.transition("active") == "active"

    def test_valid_active_to_completing(self):
        m = AgentSessionMachine("active")
        assert m.transition("completing") == "completing"

    def test_valid_completing_to_done(self):
        m = AgentSessionMachine("completing")
        assert m.transition("done") == "done"

    def test_valid_completing_to_failed(self):
        m = AgentSessionMachine("completing")
        assert m.transition("failed") == "failed"

    def test_abandoned_from_any(self):
        for state in ["starting", "active", "blocked", "completing"]:
            m = AgentSessionMachine(state)
            assert m.transition("abandoned") == "abandoned"

    def test_invalid_done_to_active(self):
        m = AgentSessionMachine("done")
        with pytest.raises(InvalidTransition):
            m.transition("active")

    def test_invalid_starting_to_done(self):
        m = AgentSessionMachine("starting")
        with pytest.raises(InvalidTransition):
            m.transition("done")


class TestActiveEditMachine:
    def test_happy_path(self):
        m = ActiveEditMachine("claimed")
        m.transition("editing")
        m.transition("committing")
        m.transition("released")
        assert m.state == "released"

    def test_conflict_path(self):
        m = ActiveEditMachine("editing")
        m.transition("conflict")
        m.transition("resolved")
        m.transition("released")
        assert m.state == "released"

    def test_conflict_to_abandoned(self):
        m = ActiveEditMachine("conflict")
        m.transition("abandoned")
        assert m.state == "abandoned"

    def test_invalid_claimed_to_released(self):
        m = ActiveEditMachine("claimed")
        with pytest.raises(InvalidTransition):
            m.transition("released")


class TestResourceLockMachine:
    def test_happy_path(self):
        m = ResourceLockMachine("acquired")
        m.transition("held")
        m.transition("releasing")
        m.transition("released")
        assert m.state == "released"

    def test_stolen(self):
        m = ResourceLockMachine("held")
        m.transition("stolen")
        assert m.state == "stolen"

    def test_expired(self):
        m = ResourceLockMachine("held")
        m.transition("expired")
        assert m.state == "expired"

    def test_invalid_released_to_held(self):
        m = ResourceLockMachine("released")
        with pytest.raises(InvalidTransition):
            m.transition("held")
