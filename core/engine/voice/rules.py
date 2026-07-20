"""Voice rule helpers — used by every renderer + the runtime audit."""

from __future__ import annotations

import re

# Union of:
#   tests/partnership/test_no_operate_shape_copy.py::FORBIDDEN_PRODUCT_COPY (operate-shape phrases)
#   engine/proactive/voice.py::FORBIDDEN_TONE_STRINGS (tone words)
# voice-audit:exempt — this list is the canonical forbidden set; lines below it are not violations.
FORBIDDEN_STRINGS: list[str] = [
    # Operate-shape (from FORBIDDEN_PRODUCT_COPY)
    "Welcome!",  # voice-audit:exempt
    "Get started",  # voice-audit:exempt
    "Click here",  # voice-audit:exempt
    "Tutorial",  # voice-audit:exempt
    "Onboarding",  # voice-audit:exempt
    "Loading...",  # voice-audit:exempt
    "Processing...",  # voice-audit:exempt
    "Thinking...",  # voice-audit:exempt
    "Please wait",  # voice-audit:exempt
    "[INFO]",  # voice-audit:exempt
    "[ERROR]",  # voice-audit:exempt
    "Successfully created",  # voice-audit:exempt
    "Successfully updated",  # voice-audit:exempt
    "Sign up",  # voice-audit:exempt
    "New conversation",  # voice-audit:exempt
    "Start a new chat",  # voice-audit:exempt
    "Clear chat",  # voice-audit:exempt
    "Session ended",  # voice-audit:exempt
    "Session started",  # voice-audit:exempt
    "Reset conversation",  # voice-audit:exempt
    # Tone (from FORBIDDEN_TONE_STRINGS) — Alert/Warning/Notification/Issue: are NOT in operate-shape list
    "Alert",  # voice-audit:exempt
    "Warning",  # voice-audit:exempt
    "Notification",  # voice-audit:exempt
    "Issue:",  # voice-audit:exempt
]

_WE_VOICE_RE = re.compile(r"\b(we|our|us)\b", re.IGNORECASE)
_DIRECTIVE_LEAD_RE = re.compile(r"^\s*(Fix|Add|Update|Remove|Delete|Configure|Install)\b", re.IGNORECASE)


def has_we_voice(text: str) -> bool:
    """True if text contains 'we' / 'our' / 'us' as a whole word."""
    return bool(_WE_VOICE_RE.search(text))


def has_observation_offer_shape(text: str) -> bool:
    """True if text reads as observation+offer — has — or ; separator AND no directive lead."""
    if _DIRECTIVE_LEAD_RE.search(text):
        return False
    return ("—" in text) or (";" in text)


def find_forbidden_strings(text: str) -> list[str]:
    """Return list of forbidden strings present in text. Empty if clean."""
    return [s for s in FORBIDDEN_STRINGS if s in text]


class VoiceRenderError(ValueError):
    """Raised when a renderer would produce output that violates a hard length cap.

    Fail-loud is intentional — silent ellipsis truncation is exactly the
    'feels like a tool' pattern voice rendering exists to avoid.
    """
