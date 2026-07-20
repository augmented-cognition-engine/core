"""Active discipline observation — find the most recent classified event
in a journey-events list and render a partner-voice phrase.

Used by engine/api/journey.py to attach a top-level `active_discipline`
field to the journey response. The portal AmbientIndicator reads it and
renders a small chip — passive observation, not interrogation.

Mirrors the structure of engine/cognition/composition_headline.py
(shipped in the composition-panel feature).
"""

from __future__ import annotations

from typing import Any


def _phase_clause(phase: Any) -> str:
    return f"phase {phase}"


def _pillar_floor_clause(pillar_floor: dict) -> str | None:
    if not isinstance(pillar_floor, dict) or not pillar_floor:
        return None
    pillar, score = next(iter(pillar_floor.items()))
    try:
        score_str = f"{float(score):.2f}"
    except (TypeError, ValueError):
        score_str = str(score)
    return f"{pillar} dipped to {score_str}"


def compose_discipline_phrase(discipline: str, signals: dict[str, Any], topic: str) -> str:
    """Render a partner-voice phrase about the active discipline.

    With recognized signals: "we see you're shaping {discipline} — {clause}."
    Without: "we see you're shaping {discipline} from what we read in the recent {topic} event."

    Both branches always:
      - open with "we see you're shaping" (partner-voice rule)
      - reach ≥75 chars even when discipline is 2 chars (audit length-floor)
    """
    if not discipline:
        raise ValueError("compose_discipline_phrase: discipline must be non-empty")

    # First recognized signal wins (insertion order)
    clause: str | None = None
    if "phase" in signals:
        clause = _phase_clause(signals["phase"])
    elif "pillar_floor" in signals:
        clause = _pillar_floor_clause(signals["pillar_floor"])

    if clause:
        return f"we see you're shaping {discipline} — {clause} from the recent {topic} event."

    # No recognized signal — topic fallback. Keeps the phrase ≥75 chars and
    # honest about WHERE the observation came from.
    return f"we see you're shaping {discipline} from what we read in the most recent {topic} journey event."


def find_active_discipline(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the most-recent event with composition_trace.signals.discipline_classified.

    Returns a dict with shape:
      {
        "discipline": str,
        "phrase": str,                # from compose_discipline_phrase
        "source_event_id": str,
        "observed_at": str,           # ISO timestamp
      }
    Or None if no qualifying event in the list.
    """
    if not events:
        return None

    candidates: list[tuple[str, dict[str, Any]]] = []  # (occurred_at, event)
    for ev in events:
        trace = ev.get("composition_trace")
        if not isinstance(trace, dict):
            continue
        signals = trace.get("signals")
        if not isinstance(signals, dict):
            continue
        discipline = signals.get("discipline_classified")
        if not discipline:
            continue
        occurred = ev.get("occurred_at") or ""
        candidates.append((occurred, ev))

    if not candidates:
        return None

    # Most-recent wins. occurred_at strings are ISO-8601 → string sort works.
    candidates.sort(key=lambda x: x[0], reverse=True)
    occurred, ev = candidates[0]
    trace = ev["composition_trace"]
    signals = trace["signals"]
    discipline = signals["discipline_classified"]
    topic = ev.get("topic") or "unknown"
    return {
        "discipline": discipline,
        "phrase": compose_discipline_phrase(discipline, signals, topic),
        "source_event_id": ev.get("id", ""),
        "observed_at": occurred,
    }
