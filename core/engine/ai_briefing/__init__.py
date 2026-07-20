"""AI-side briefing — structured payload sent to dispatched AIs before reasoning.

Every AI that ACE invokes (Claude via CLIProvider, future Cursor/Claude Code
integrations, browser agents) receives a briefing payload as the first thing it
sees. Closes the cold-start ignorance gap that every IDE-layer AI suffers:
without briefing, the AI theorizes about a codebase it has never seen; with
briefing, it operates from ground truth.

Three primitives:

    build_briefing(product_id)   — assemble AIBriefing from substrate state
    render_briefing(briefing)    — render as system-prompt prefix text
    briefing_for_dispatched_ai() — convenience wrapper: build + render

This is the AI-side counterpart to engine.sentinel.engines.briefing
(which produces human-readable briefings). Same substrate, different consumer.
"""

from core.engine.ai_briefing.builder import (
    AIBriefing,
    briefing_for_dispatched_ai,
    build_briefing,
    invalidate_briefing_cache,
    render_briefing,
)

__all__ = [
    "AIBriefing",
    "build_briefing",
    "render_briefing",
    "briefing_for_dispatched_ai",
    "invalidate_briefing_cache",
]
