"""Loop iteration helpers — cluster journey events by temporal proximity
and render partner-voice summary phrases for each iteration.

Used by engine/api/loop.py to render the /loop timeline. Pure functions
over event dicts; trivially unit-testable without DB.

Mirrors the structure of engine/cognition/active_discipline.py and
engine/cognition/handoff.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

ITERATION_GAP_SECONDS: int = 90


def _parse_iso(ts: str | datetime) -> datetime:
    """Parse an ISO-8601 timestamp. Accepts trailing 'Z' or a datetime
    passed through (SurrealDB hydrates `datetime` columns as datetime
    objects when reading, but seeded test data lands as strings)."""
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _to_iso(ts: str | datetime) -> str:
    """Normalize a timestamp value to its ISO-8601 string form for
    inclusion in the iteration card response (which must be JSON-safe)."""
    if isinstance(ts, datetime):
        return ts.isoformat()
    return ts


def cluster_events(
    events: list[dict[str, Any]],
    gap_seconds: int = ITERATION_GAP_SECONDS,
) -> list[dict[str, Any]]:
    """Group events by temporal proximity. Two events belong to the same
    iteration if their occurred_at timestamps are within gap_seconds.

    Input: events sorted by occurred_at ascending. Each event must carry
    'id', 'occurred_at' (ISO-8601 string), and 'topic'.

    Output: list of iteration dicts:
        {started_at, ended_at, event_ids: list[str], topics: dict[str, list[str]]}
    """
    if not events:
        return []

    iterations: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_dt: datetime | None = None

    for ev in events:
        occurred = ev.get("occurred_at") or ""
        try:
            ev_dt = _parse_iso(occurred)
        except (ValueError, AttributeError):
            # Skip events with unparseable timestamps rather than crashing the
            # whole timeline render.
            continue

        ev_id = ev.get("id", "")
        topic = ev.get("topic") or "unknown"

        start_new = current is None or last_dt is None or (ev_dt - last_dt).total_seconds() > gap_seconds

        occurred_iso = _to_iso(occurred)
        if start_new:
            current = {
                "started_at": occurred_iso,
                "ended_at": occurred_iso,
                "event_ids": [ev_id],
                "topics": {topic: [ev_id]},
            }
            iterations.append(current)
        else:
            current["ended_at"] = occurred_iso
            current["event_ids"].append(ev_id)
            current["topics"].setdefault(topic, []).append(ev_id)

        last_dt = ev_dt

    return iterations


def summarize_topics(
    event_ids_by_topic: dict[str, list[str]],
    max_named: int = 3,
) -> str:
    """Render a compact comma-joined topic list for the phrase.

    Topics are sorted by count descending. Top max_named are joined with
    ", "; any remainder is compressed to ", +N more". Empty dict → "".
    """
    if not event_ids_by_topic:
        return ""

    ranked = sorted(
        event_ids_by_topic.items(),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )
    named = [name for name, _ in ranked[:max_named]]
    remainder = len(ranked) - len(named)
    body = ", ".join(named)
    if remainder > 0:
        body = f"{body}, +{remainder} more"
    return body


def compose_iteration_phrase(iteration: dict[str, Any]) -> str:
    """Render a partner-voice summary sentence for an iteration.

    Always opens with 'we' or 'between'. Always reaches ≥75 chars when
    topics is non-empty. Always names at least one topic.

    Two shapes:
      - Single-event iteration: "we observed a {topic} signal at {started_at}
        and recorded it across our shared journey."
      - Multi-event iteration: "between {started_at} and {ended_at} we noticed
        {n} signals — {topic_summary} — across our shared journey."
    """
    event_ids = iteration.get("event_ids") or []
    topics = iteration.get("topics") or {}
    started_at = iteration.get("started_at") or ""
    ended_at = iteration.get("ended_at") or started_at

    n = len(event_ids)

    if n <= 1:
        # Single-event branch — name the topic we recorded.
        topic = next(iter(topics.keys()), "activity")
        return f"we observed a {topic} signal at {started_at} and recorded it across our shared journey."

    # Multi-event branch — summarize the topic mix.
    summary = summarize_topics(topics) or "activity"
    return f"between {started_at} and {ended_at} we noticed {n} signals — {summary} — across our shared journey."
