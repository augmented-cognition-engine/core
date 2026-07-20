"""Runtime partner-voice audit — checks rendered text against voice rules.

Used by compose_morning_briefing as a soft warning gate (logs failures but
doesn't block briefing storage). NOT a hard barrier — voice rule failures
are bugs to fix, not reasons to drop a briefing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.engine.voice.rules import find_forbidden_strings, has_we_voice

logger = logging.getLogger(__name__)

_WE_VOICE_MIN_LENGTH = 75

# Voice audit thresholds — single source of truth (per spec AC7)
VOICE_AUDIT_AMBIENT_THRESHOLD = 0.85  # AmbientIndicator badge fires below this
VOICE_AUDIT_TEASER_THRESHOLD = 1.0  # SessionStart hook teaser fires below this (any imperfection)


@dataclass
class AuditResult:
    passed: bool
    violations: list[str] = field(default_factory=list)


def audit_partner_voice(text: str) -> AuditResult:
    """Audit text against partner-voice rules. Returns structured result.

    Rules checked:
      1. No forbidden strings (Alert, Warning, [INFO], operate-shape phrases, etc.)  # voice-audit:exempt
      2. Text > 80 chars contains 'we' / 'our' / 'us' (short utility strings exempt)
    """
    violations: list[str] = []
    forbidden = find_forbidden_strings(text)
    if forbidden:
        violations.append(f"contains forbidden strings: {', '.join(forbidden)}")
    if len(text) > _WE_VOICE_MIN_LENGTH and not has_we_voice(text):
        violations.append("missing 'we'/'our'/'us' in text > 80 chars")
    return AuditResult(passed=not violations, violations=violations)


def audit_or_warn(text: str, label: str = "rendered text") -> AuditResult:
    """Run audit; log a warning if it fails. Caller decides what to do next."""
    result = audit_partner_voice(text)
    if not result.passed:
        logger.warning("Voice audit failed for %s: %s", label, "; ".join(result.violations))
    return result
