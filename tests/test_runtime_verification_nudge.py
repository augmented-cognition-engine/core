"""Tests for the verification nudge."""

from core.engine.runtime.verification_nudge import VerificationNudge


def test_no_nudge_below_threshold():
    nudge = VerificationNudge()
    nudge.record_task_completed()
    nudge.record_task_completed()
    assert not nudge.should_nudge()


def test_nudge_after_three_without_verify():
    nudge = VerificationNudge()
    nudge.record_task_completed()
    nudge.record_task_completed()
    nudge.record_task_completed()
    assert nudge.should_nudge()


def test_no_nudge_if_verified():
    nudge = VerificationNudge()
    nudge.record_task_completed()
    nudge.record_task_completed()
    nudge.record_verification()
    nudge.record_task_completed()
    assert not nudge.should_nudge()


def test_nudge_message():
    nudge = VerificationNudge()
    msg = nudge.get_nudge_message()
    assert "verif" in msg.lower()


def test_reset_after_nudge():
    nudge = VerificationNudge()
    for _ in range(3):
        nudge.record_task_completed()
    assert nudge.should_nudge()
    nudge.reset()
    assert not nudge.should_nudge()
