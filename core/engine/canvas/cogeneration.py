"""Proactive co-generation: produce at most one grounded partner contribution
from the current canvas context. Used by the playground's co-generation loop.

The relevance floor is the engine-side half of the governor — silence beats
noise, so a low-relevance contribution is suppressed (returns None).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.engine.core.llm import get_llm

RELEVANCE_FLOOR = 0.5

_SYSTEM = (
    "You are a thinking partner sharing a canvas with a human. You contribute "
    "unprompted: surface ONE angle, counter-argument, risk, or 'have you "
    "considered' that the human likely has not — never a question that asks them "
    "to do work. If nothing genuinely valuable to add right now, say so with a "
    "low relevance score. Be concise (one or two sentences)."
)

_PROMPT = """The human is thinking about:
{thought}

Recent things on the canvas:
{recent}

Return JSON: {{"contribution": "<one or two sentences, or empty>", "kind": "angle|risk|counter|connection", "relevance": <0.0-1.0>}}.
relevance is how valuable this unprompted contribution is right now; use a low value if you have nothing worth interrupting for."""


@dataclass
class Contribution:
    text: str
    kind: str
    relevance: float


async def generate_contribution(
    originating_thought: str,
    recent_texts: list[str],
    *,
    floor: float = RELEVANCE_FLOOR,
) -> Contribution | None:
    """Generate <=1 contribution grounded in the canvas context, or None if nothing
    clears the relevance floor."""
    thought = (originating_thought or "")[:1000]
    recent = "\n".join(f"- {t[:500]}" for t in recent_texts[:8]) or "(nothing yet)"
    prompt = _PROMPT.format(thought=thought or "(not stated)", recent=recent)
    data = await get_llm().complete_json(prompt, system=_SYSTEM)

    text = str(data.get("contribution") or "").strip()
    try:
        relevance = float(data.get("relevance") or 0.0)
    except (TypeError, ValueError):
        relevance = 0.0
    kind = str(data.get("kind") or "angle").strip() or "angle"

    if not text or relevance < floor:
        return None
    return Contribution(text=text, kind=kind, relevance=relevance)
