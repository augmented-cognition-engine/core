"""Handoff humility — recognize when ACE's confidence is low and suggest
a better tool. Pure helpers for the classifier to call + the journey API
to render.

Mirrors the structure of engine/cognition/active_discipline.py and
engine/cognition/composition_headline.py.
"""

from __future__ import annotations

from typing import Any

HANDOFF_CONFIDENCE_THRESHOLD: float = 0.4
HANDOFF_DEFAULT_TOOL: str = "Claude"
HANDOFF_TOOL_URL: dict[str, str] = {
    "Claude": "https://claude.ai",
}


def should_handoff(classifier_result: Any) -> tuple[bool, str | None]:
    """Decide whether a classify result warrants a handoff.

    Returns (True, tool_name) when discipline_confidence is strictly
    below HANDOFF_CONFIDENCE_THRESHOLD. (False, None) otherwise — including
    when the input is malformed (not a dict, missing key, non-numeric value).
    """
    if not isinstance(classifier_result, dict):
        return (False, None)
    confidence = classifier_result.get("discipline_confidence")
    if not isinstance(confidence, (int, float)):
        return (False, None)
    if confidence < HANDOFF_CONFIDENCE_THRESHOLD:
        return (True, HANDOFF_DEFAULT_TOOL)
    return (False, None)


def compose_handoff_phrase(tool: str) -> str:
    """Render the partner-voice handoff phrase. Always opens with 'we'
    and is ≥75 chars (audit length-floor) even for 1-char tool names.

    Raises ValueError if tool is empty.
    """
    if not tool:
        raise ValueError("compose_handoff_phrase: tool must be non-empty")
    return (
        f"we recognized this isn't our strength — try {tool} directly, that's where this kind of question lands best."
    )


def find_active_handoff(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the most-recent journey event with topic 'handoff.recognized'.

    Returns:
      {
        "tool": str,
        "url": str,
        "phrase": str,
        "source_event_id": str,
        "observed_at": str,
      }
    or None when no qualifying event in the list.
    """
    if not events:
        return None

    candidates: list[tuple[str, dict[str, Any]]] = []
    for ev in events:
        if ev.get("topic") != "handoff.recognized":
            continue
        candidates.append((ev.get("occurred_at") or "", ev))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    occurred, ev = candidates[0]
    payload = ev.get("payload") or {}
    tool = payload.get("suggested_external_tool") or HANDOFF_DEFAULT_TOOL
    url = HANDOFF_TOOL_URL.get(tool, HANDOFF_TOOL_URL["Claude"])
    return {
        "tool": tool,
        "url": url,
        "phrase": compose_handoff_phrase(tool),
        "source_event_id": ev.get("id", ""),
        "observed_at": occurred,
    }
