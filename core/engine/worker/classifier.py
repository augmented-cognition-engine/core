# engine/worker/classifier.py
"""Context-aware classification for the ACE Session Worker.

Unlike the hook's keyword classifier, this runs asynchronously in the
background worker with full conversation context available. Results are
cached to SurrealDB and served to the hook on its next GET /session/context.

Key improvements over the hook's keyword_classify():
1. Full session summary injected into classifier prompt
2. Mode floor raised based on session depth (5+ messages → at least procedural)
3. Recent decisions inform discipline weighting
4. Background async — never blocks the conversation
"""

from __future__ import annotations

import logging

from core.engine.core.config import settings
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

# Instant keyword classifier — POST /session/message uses it to set a provisional
# classification for the current message. Re-exported from the canonical core
# module so the worker and the hook share ONE source of truth (no drift).
from core.engine.keyword_classifier import keyword_classify  # noqa: E402,F401

# Mode floor based on message count in current session.
# Short sessions stay reactive; long sessions are inherently deliberative.
_MODE_FLOOR: list[tuple[int, str]] = [
    (0, "reactive"),  # 0–4 messages: trust keyword classify
    (5, "procedural"),  # 5–9 messages: at least procedural (multi-step)
    (10, "deliberative"),  # 10+ messages: assume deep exploration
]

_OBVIOUS_REACTIVE_PATTERNS = [
    "run pytest",
    "run tests",
    "git status",
    "git diff",
    "git log",
    "ls ",
    "cat ",
    "print(",
    "help",
    "what is the",
]


def _mode_floor_for_count(message_count: int) -> str:
    """Return minimum mode based on how many messages are in this session."""
    floor = "reactive"
    for threshold, mode in _MODE_FLOOR:
        if message_count >= threshold:
            floor = mode
    return floor


def _is_obviously_reactive(message: str) -> bool:
    """True if the message is so simple it can't be deliberative (run command, short lookup)."""
    stripped = message.strip().lower()
    if len(stripped) < 15:
        return True
    return any(stripped.startswith(p) for p in _OBVIOUS_REACTIVE_PATTERNS)


def _raise_mode_floor(mode: str, floor: str) -> str:
    """Return the higher of two modes on the reactive→deliberative scale."""
    _SCALE = ["reactive", "conversational", "procedural", "exploratory", "deliberative", "reflective"]
    try:
        return _SCALE[max(_SCALE.index(mode), _SCALE.index(floor))]
    except ValueError:
        return mode


async def classify_with_context(
    message: str,
    session_summary: str,
    message_count: int,
    recent_decisions: list[dict],
    product_id: str = "product:platform",
) -> dict:
    """LLM classify with full session context.

    Called by the background worker (never blocks the hook). Returns a
    classification dict that gets cached to ace_session and served on the
    next GET /session/context call.

    Key behaviours:
    - Fast-path: obviously reactive messages (run command, short lookup) skip LLM
    - Mode floor: long sessions raise the minimum mode (10+ messages → deliberative)
    - Context injection: session summary and recent decisions are injected into
      the classifier prompt so a short message in a long exploration classifies correctly
    """
    # Fast-path: obviously reactive, skip LLM
    if _is_obviously_reactive(message) and message_count < 5:
        return {
            "discipline": "architecture",
            "archetype": "executor",
            "mode": "reactive",
            "perspective": "practitioner",
            "specialties": [],
            "depth": 1,
            "context_informed": False,
        }

    floor = _mode_floor_for_count(message_count)

    # Build context sections for prompt injection
    context_parts = []
    if session_summary:
        context_parts.append(f"Session context: {session_summary}")
    if recent_decisions:
        dec_lines = [f"  - [{d.get('decision_type', '?')}] {d.get('title', '?')}" for d in recent_decisions[:3]]
        context_parts.append("Recent decisions:\n" + "\n".join(dec_lines))
    if message_count > 0:
        context_parts.append(f"Messages in session: {message_count}")
    if floor != "reactive":
        context_parts.append(
            f"Note: This is a long session ({message_count} messages). "
            f"Mode must be at least '{floor}' unless this message is clearly a one-step command."
        )

    context_block = "\n".join(context_parts)

    disciplines_str = (
        "security, testing, ux, performance, devops, accessibility, documentation, "
        "architecture, api_design, data_modeling, business_logic, integration, "
        "error_handling, observability, configuration, deployment, versioning, "
        "code_conventions, dependency_management"
    )

    prompt = f"""Classify this message for the ACE intelligence system.

{context_block}

Current message: {message[:600]}

Return JSON with exactly these fields:
- discipline: one of ({disciplines_str})
- archetype: one of (creator, analyst, executor, researcher, advisor, sentinel)
- mode: one of (reactive, procedural, exploratory, deliberative, reflective, conversational)
- perspective: one of (practitioner, theorist, strategist, operator)
- specialties: array of 1-3 relevant kebab-case slugs
- depth: integer 1-4 (reactive=1, procedural=2, exploratory/deliberative=3, reflective=4)

Classification rules:
- If session_context shows extended exploration → mode must be at least exploratory
- If session_context shows architecture decisions → discipline likely architecture
- If message is short but session is deep → inherit session context for mode
- Deliberative = multi-step reasoning, high-stakes, alternatives need weighing
- Reactive = fast pattern-match, single direct step, clear spec

JSON:"""

    try:
        result = await get_llm().complete_json(prompt, model=settings.llm_budget_model)

        discipline = result.get("discipline", "architecture")
        archetype = result.get("archetype", "executor")
        mode = result.get("mode", "reactive")
        perspective = result.get("perspective", "practitioner")
        specialties = result.get("specialties", [])
        depth = int(result.get("depth", 1))

        # Apply mode floor — long sessions can't be reactive
        final_mode = _raise_mode_floor(mode, floor)
        if final_mode != mode:
            logger.debug(
                "Mode raised from %s to %s (floor=%s, message_count=%d)",
                mode,
                final_mode,
                floor,
                message_count,
            )
            depth = max(depth, _SCALE_TO_DEPTH.get(final_mode, depth))

        return {
            "discipline": discipline,
            "archetype": archetype,
            "mode": final_mode,
            "perspective": perspective,
            "specialties": specialties if isinstance(specialties, list) else [],
            "depth": depth,
            "context_informed": bool(context_parts),
        }

    except Exception as exc:
        logger.warning("classify_with_context failed: %s", exc)
        # Safe fallback — raise mode floor even on failure
        fallback_mode = _raise_mode_floor("reactive", floor)
        return {
            "discipline": "architecture",
            "archetype": "executor",
            "mode": fallback_mode,
            "perspective": "practitioner",
            "specialties": [],
            "depth": _SCALE_TO_DEPTH.get(fallback_mode, 1),
            "context_informed": False,
        }


_SCALE_TO_DEPTH = {
    "reactive": 1,
    "conversational": 1,
    "procedural": 2,
    "exploratory": 3,
    "deliberative": 3,
    "reflective": 4,
}
