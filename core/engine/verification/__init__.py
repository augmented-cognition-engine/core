# engine/verification/__init__.py
"""Verification V2 — behavioral checks, evaluator honesty, simplicity audit.

Public API:
- run_checks(spec) -> behavioral evidence per criterion
- format_evidence(evidence) -> human-readable text for LLM prompts
- HonestyEnforcer / PreCommitmentProtocol -> evaluator integrity
"""

from core.engine.verification.behavioral import run_checks
from core.engine.verification.models import (
    BehavioralEvidence,
    CheckResult,
    EnforcedVerdict,
    PreCommitment,
    format_evidence,
)

__all__ = [
    "run_checks",
    "format_evidence",
    "BehavioralEvidence",
    "CheckResult",
    "EnforcedVerdict",
    "PreCommitment",
]
