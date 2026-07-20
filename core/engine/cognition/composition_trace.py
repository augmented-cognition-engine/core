"""Composition trace builder + attach helper.

A composition_trace captures what cognitive composition produced an event:
the meta-skills used, the frame applied, the signals that triggered the
composition, and (optionally) a star_trace id if a proven pattern informed it.

The trace dict is stored on journey_event.composition_trace (option<object>).
"""

from __future__ import annotations

import sys
from typing import Any


def build(
    meta_skills: list[str],
    frame: str,
    signals: dict[str, Any],
    star_trace_id: str | None = None,
) -> dict[str, Any]:
    """Construct a composition_trace dict.

    meta_skills must be non-empty. star_trace_id is optional and omitted from
    the returned dict (not None) when not provided, to keep stored payloads tidy.
    """
    if not meta_skills:
        raise ValueError("meta_skills must be non-empty list")
    trace: dict[str, Any] = {
        "meta_skills": list(meta_skills),
        "frame": frame,
        "signals": dict(signals),
    }
    if star_trace_id is not None:
        trace["star_trace_id"] = star_trace_id
    return trace


async def attach(pool: Any, journey_event_id: str, trace: dict[str, Any]) -> None:
    """UPDATE journey_event SET composition_trace = <trace>. Best-effort."""
    from core.engine.core.db import parse_record_id

    async with pool.connection() as db:
        await db.query(
            "UPDATE $jid SET composition_trace = $trace",
            {"jid": parse_record_id(journey_event_id), "trace": trace},
        )

    # Emit handoff.recognized when the trace carries the handoff signal so
    # the journey feed (and AmbientIndicator) can surface it.
    signals = trace.get("signals") or {}
    if signals.get("handoff_recommended") is True:
        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "handoff.recognized",
                {
                    "journey_event_id": journey_event_id,
                    "suggested_external_tool": signals.get("suggested_external_tool") or "Claude",
                },
            )
        except Exception as exc:
            print(f"warn: handoff.recognized emit failed: {exc!r}", file=sys.stderr)
