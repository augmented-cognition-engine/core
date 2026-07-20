"""Verification nudge — structural quality gate.

After 3+ completed tasks without a verification step, inject a reminder
to verify the work. Modeled on Claude Code's TodoWriteTool nudge pattern.
"""

from __future__ import annotations

NUDGE_THRESHOLD = 3


class VerificationNudge:
    """Tracks task completions and nudges for verification."""

    def __init__(self) -> None:
        self._completed_since_verify = 0

    def record_task_completed(self) -> None:
        self._completed_since_verify += 1

    def record_verification(self) -> None:
        self._completed_since_verify = 0

    def should_nudge(self) -> bool:
        return self._completed_since_verify >= NUDGE_THRESHOLD

    def get_nudge_message(self) -> str:
        return (
            f"{self._completed_since_verify} tasks completed without verification. "
            "Consider running tests or spawning a verification agent to confirm "
            "the changes work correctly."
        )

    def reset(self) -> None:
        self._completed_since_verify = 0
