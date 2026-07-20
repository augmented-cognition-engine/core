"""Voice transformer — structured finding → colleague-voice partner prose.

Runs on Haiku (cost-sensitive; called per-finding on every aggregation cycle).
The voice prompt template is the enforcement point for partnership voice rules.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

FORBIDDEN_TONE_STRINGS = ["Alert", "Warning", "Notification", "Issue:", "[INFO]", "[ERROR]"]  # voice-audit:exempt

_VOICE_PROMPT = """\
You are ACE, a thoughtful engineering partner. Transform the finding below into \
a single colleague-voice sentence that a senior engineer would say to a peer.

Rules (enforced — violations fail CI):
- Use "we", "our", or "us" — never "I" alone or "you"
- Phrase as observation + offer, not directive
- Exactly one sentence
- No quotation marks, no emojis, no markdown
- Never use: Alert, Warning, Notification, Issue:, [INFO], [ERROR]
- Maximum 150 characters

Finding:
  source: {source}
  capability: {capability}
  discipline: {discipline}
  description: {description}
  severity: {severity:.2f}

Output (one sentence only, no other text):"""


async def transform(
    source: str,
    capability: str,
    discipline: str,
    description: str,
    severity: float,
) -> str:
    """Transform a structured finding into a colleague-voice ProactiveLine sentence.

    Falls back to a plain-language summary if the LLM call fails.
    Never raises — always returns a string.
    """
    from core.engine.core.config import settings
    from core.engine.core.llm import llm

    prompt = _VOICE_PROMPT.format(
        source=source,
        capability=capability,
        discipline=discipline,
        description=description,
        severity=severity,
    )

    try:
        result = await llm.complete(
            prompt,
            model=getattr(settings, "llm_budget_model", "claude-haiku-4-5-20251001"),
            max_tokens=80,
        )
        line = result.strip().strip('"').strip("'")
        # Enforce 150-char cap (truncation happens here, not in voice transformer)
        if len(line) > 150:
            line = line[:147] + "..."
        return line
    except Exception as exc:
        logger.debug("Voice transformer LLM call failed: %s", exc)
        return _fallback_line(capability, discipline, description)


def _fallback_line(capability: str, discipline: str, description: str) -> str:
    """Plain-language fallback that still respects voice rules."""
    cap_part = f"our {capability}" if capability else "our codebase"
    desc_short = description[:80] if description else "something worth reviewing"
    return f"We noticed {cap_part} has a {discipline} gap — {desc_short[:60]}."[:150]
