"""Completion summarizer — raw agent result → colleague-voice summary.

Uses Sonnet (one call per hand-off completion; quality matters).
Voice rules: we/our/us, observation + offer, no system-tone strings.
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.llm import llm

logger = logging.getLogger(__name__)

SUMMARY_GENERIC_STRINGS = ["Task completed successfully", "Done.", "Completed"]

_VOICE_PROMPT = """\
You completed a task as our AI partner. Summarize the result in one sentence
using "we" or "our" — write as a colleague, not a system.

Include: one observation about what happened (including any concerns) and one
offer for next steps.

Rules:
- Use "we", "our", or "us" — not "I" or "the agent"
- ONE sentence only
- Note concerns honestly (failing tests, warnings, skipped work)
- End with an offer: "Want me to..." or "Should we..."
- Maximum 200 characters
- NEVER say: "Task completed successfully", "Done.", "Completed", [INFO], [ERROR]

Result:
{result_summary}

Agent: {agent}
"""


async def summarize(result: dict, agent: str) -> str:
    """Generate a colleague-voice completion summary. Never raises."""
    result_summary = _format_result(result)
    prompt = _VOICE_PROMPT.format(result_summary=result_summary, agent=agent)

    try:
        raw = await llm.complete(prompt, model=settings.llm_model, max_tokens=200)
        summary = raw.strip().strip('"').strip("'")
        if summary[:3] in ("```",):
            summary = summary.split("\n", 1)[-1].strip()
        if summary and summary not in SUMMARY_GENERIC_STRINGS and len(summary) > 10:
            if not any(t in summary.lower() for t in ("we ", "our ", " us")):
                summary = _fallback_summary(result)
            return summary[:200]
    except Exception as exc:
        logger.debug("summarizer LLM call failed (non-fatal): %s", exc)

    return _fallback_summary(result)


def _format_result(result: dict) -> str:
    completed = result.get("completed", 0)
    failed = result.get("failed", 0)
    blocked = result.get("blocked", 0)
    total = result.get("total_units", completed + failed + blocked)
    status = result.get("spec_status", "unknown")
    parts = [f"Units: {completed}/{total} completed"]
    if failed:
        parts.append(f"{failed} failed")
    if blocked:
        parts.append(f"{blocked} blocked")
    parts.append(f"Final status: {status}")
    return ", ".join(parts)


def _fallback_summary(result: dict) -> str:
    """Fallback when LLM unavailable — always partnership voice, never generic."""
    completed = result.get("completed", 0)
    failed = result.get("failed", 0)
    blocked = result.get("blocked", 0)
    total = result.get("total_units", completed + failed + blocked)

    if failed > 0:
        return f"We finished {completed}/{total} units — {failed} failed and need attention. Want me to spec the fixes?"
    if blocked > 0:
        return (
            f"We completed {completed}/{total} units; {blocked} were blocked by dependencies. "
            f"Should we investigate the blockers?"
        )
    return f"We finished all {total} units. Want me to run a spec review before we call it done?"
