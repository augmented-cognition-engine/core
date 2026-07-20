"""Journey partner-voice generator — hand-written templates per topic.

Each /journey card surfaces a one-line partner-voice summary. Per
feedback_user_centric_always.md, these lines are hand-written templates,
NOT LLM-generated — so they are deterministic, fast, and pass the voice
sentinel rules in engine/voice/rules.py (no FORBIDDEN_STRINGS, observation
shape rather than directive shape).

The 21 canvas.* templates mirror engine.events.canvas.LivingCanvasEventType.
A safety-net test (test_known_topics_covers_canvas_enum) asserts every
enum value has a template — adding a new event without a template will
fail the test loudly.

render_summary uses a defensive format_map so missing payload keys render
as the literal "<key>" rather than raising KeyError. This way the surface
degrades gracefully when payloads vary across emit sites.
"""

from __future__ import annotations

from typing import Any


class UnknownTopicError(KeyError):
    """Raised when render_summary is called with a topic that has no template.

    Subclassing KeyError keeps callers that catch KeyError working, but the
    distinct type lets the journey renderer log "missing template" cleanly.
    """


class _MissingKey(dict):
    """format_map helper — missing keys render as the literal "<key>".

    Defensive against payload drift: emit sites add and rename fields over
    time, and a missing key shouldn't take down the whole journey render.
    """

    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return f"<{key}>"


# ---------------------------------------------------------------------------
# Bus topics — non-canvas events the journey surfaces
# ---------------------------------------------------------------------------

_BUS_TOPICS: dict[str, str] = {
    "gap.detected": "We noticed a gap in {pillar} — worth a look.",
    "gap.closed": "Gap in {pillar} is closed.",
    "spec.created": "We started a new spec — {spec_id}.",
    "spec.completed": "Spec {spec_id} is done.",
    "decision.captured": "We captured a decision — {title}.",
    "session.started": "Session opened.",
    "session.start.rendered": "We rendered the session-start greeting",
    "session.ended": "Session wrapped.",
    "briefing.posted": "We posted a fresh briefing.",
    "review.requested": "Review requested on {target}.",
    "review.completed": "Review wrapped on {target}.",
    "outcome.committed": "We marked the {emission_kind} on {pillar} as committed — you shipped it.",
    "outcome.ignored": "We let go of the {emission_kind} on {pillar} — neither of us moved on it in time.",
    "effectiveness.score.recomputed": "We re-scored {pillar}/{discipline} — our effectiveness moved to {score}.",
    "handoff.recognized": "We recognized that's outside our strength — pointing you to {suggested_external_tool}.",
}


# ---------------------------------------------------------------------------
# Canvas topics — one per LivingCanvasEventType (21 total)
# ---------------------------------------------------------------------------

_CANVAS_TOPICS: dict[str, str] = {
    "canvas.capability.added": "We added a capability — {name}.",
    "canvas.capability.updated": "We updated capability {slug}.",
    "canvas.capability.lifecycle_changed": "Capability {slug} moved lifecycle stages.",
    "canvas.decision.captured": "We captured a decision — {title}.",
    "canvas.edge.added": "We linked {from_id} to {to_id} via {edge_type}.",
    "canvas.score.changed": "Score on {capability_slug}.{dimension} shifted to {new_score}.",
    "canvas.sentinel.fired": "Sentinel {sentinel_name} fired — {summary}.",
    "canvas.briefing.updated": "Briefing refreshed — {summary}.",
    "canvas.proactive.line.updated": "Fresh proactive line — {line}.",
    "canvas.handoff.started": "We dispatched a hand-off to {agent}.",
    "canvas.handoff.progress": "Hand-off progress — {plain_language}.",
    "canvas.handoff.completed": "Hand-off {handoff_id} completed — {status}.",
    "canvas.drift.crossed": "We crossed a drift threshold.",
    "canvas.recommendation.shifted": "Our recommendation shifted.",
    "canvas.uncertainty.opened": "We opened a question we want answered.",
    "canvas.uncertainty.answered": "We closed an open question.",
    "canvas.intelligence.classified": "Classifier read this as {discipline}.",
    "canvas.pattern.matched": "We spotted a familiar pattern.",
    "canvas.code.edited": "Code changed under our watch.",
    "canvas.thread.committed": "We committed to working on {topic}.",
    "canvas.thread.resolved": "Thread on {topic} is resolved.",
    "canvas.composition.selected": "We composed the team — {meta_skills} weighing in.",
}


# Frozen union — single source of truth for callers / tests.
KNOWN_TOPICS: frozenset[str] = frozenset(_BUS_TOPICS) | frozenset(_CANVAS_TOPICS)


def _template_for(topic: str) -> str:
    if topic in _BUS_TOPICS:
        return _BUS_TOPICS[topic]
    if topic in _CANVAS_TOPICS:
        return _CANVAS_TOPICS[topic]
    raise UnknownTopicError(topic)


def render_summary(
    topic: str,
    payload: dict[str, Any],
    trace: Any | None = None,
) -> str:
    """Render a one-line partner-voice summary for a journey card.

    Args:
        topic: bus or canvas.* topic string. Must be in KNOWN_TOPICS.
        payload: dict of substitution values for the template.
        trace: optional composition trace — accepted for forward
            compatibility with reasoning-trace-aware templates, currently
            unused.

    Returns:
        Rendered template string, with missing keys substituted as "<key>".

    Raises:
        UnknownTopicError: if topic has no registered template.
    """
    template = _template_for(topic)
    return template.format_map(_MissingKey(payload or {}))


__all__ = [
    "KNOWN_TOPICS",
    "UnknownTopicError",
    "render_summary",
]
