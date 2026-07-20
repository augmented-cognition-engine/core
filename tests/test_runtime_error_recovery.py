"""Tests for error recovery waterfall."""

from core.engine.runtime.error_recovery import ErrorRecovery


def test_initial_state():
    recovery = ErrorRecovery()
    assert not recovery.has_attempted_compact
    assert recovery.max_output_recovery_count == 0


def test_attempt_compact_once():
    recovery = ErrorRecovery()
    assert recovery.try_compact()  # first attempt succeeds
    assert recovery.has_attempted_compact
    assert not recovery.try_compact()  # second attempt blocked (one-shot)


def test_max_output_recovery():
    recovery = ErrorRecovery()
    assert recovery.try_max_output_recovery()  # attempt 1
    assert recovery.try_max_output_recovery()  # attempt 2
    assert recovery.try_max_output_recovery()  # attempt 3
    assert not recovery.try_max_output_recovery()  # attempt 4 blocked


def test_nudge_message():
    recovery = ErrorRecovery()
    msg = recovery.get_recovery_nudge()
    assert "resume" in msg.lower() or "continue" in msg.lower()


def test_reset():
    recovery = ErrorRecovery()
    recovery.try_compact()
    recovery.try_max_output_recovery()
    recovery.reset()
    assert not recovery.has_attempted_compact
    assert recovery.max_output_recovery_count == 0
