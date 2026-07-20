"""Conductor live-page phrase helpers — render partner-voice phrases for
heartbeat freshness, recent rule firings, and pending gates.

Used by engine/api/conductor.py::get_live_state to compose phrases for the
/conductor live page. Pure functions over dicts; trivially unit-testable
without DB.

Mirrors the structure of engine/cognition/loop_iterations.py (defensive
datetime ↔ str handling) and engine/cognition/active_discipline.py and
engine/cognition/handoff.py (helper-module style).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HEARTBEAT_FRESH_SECONDS: int = 60


# Topic → phrase template. All open with "we" and reach ≥75 chars even for
# minimal substitution values. {topic} substitutions for fallback are wired
# through compose_firing_phrase, not these literals.
_TOPIC_PHRASES: dict[str, str] = {
    "conductor.gate_cleared": ("we cleared a pending gate just now and moved the work forward in our shared journey."),
    "conductor.gate_pending": (
        "we recognized a gate that needs your attention before the work can continue moving forward."
    ),
    "conductor.track_changed": (
        "we shifted a track from {from_state} to {to_state} as the work progressed through our shared journey."
    ),
    "conductor.stall_detected": (
        "we noticed a track has been stuck for a while — it may need your attention to unblock our progress."
    ),
    "conductor.action_failed": (
        "we tried to act on a conductor rule but the action failed — review needed before we proceed together."
    ),
    "quality.score_changed": (
        "we observed a quality score change on a tracked capability — worth a glance when you have a moment."
    ),
    "innovation.candidates_ready": (
        "we have a fresh batch of innovation candidates ready for triage whenever you want to look together."
    ),
}


def _parse_iso(ts: str | datetime) -> datetime:
    """Parse an ISO-8601 timestamp. Accepts trailing 'Z' or a datetime
    passed through (SurrealDB hydrates `datetime` columns as datetime
    objects when reading, but seeded test data lands as strings).

    Mirrors the same defensive pattern as
    engine/cognition/loop_iterations.py::_parse_iso so the conductor live
    panels don't repeat the datetime-vs-string drift bug from the
    loop-timeline feature.
    """
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def heartbeat_freshness(
    last_heartbeat_at: str | datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Render the heartbeat freshness summary for the conductor page.

    Returns:
        {
          "is_fresh": bool,
          "age_seconds": int | None,
          "phrase": str,        # always opens with 'we', always ≥75 chars
        }

    None branch: "we haven't seen a heartbeat from the conductor yet — it
    may not be running on this product."

    Fresh branch (age ≤ HEARTBEAT_FRESH_SECONDS): "we last heard from the
    conductor {N} seconds ago — it's actively watching with us."

    Stale branch (age > HEARTBEAT_FRESH_SECONDS): "we haven't heard from
    the conductor in {M} minutes — it may be paused or stopped right now."
    """
    if last_heartbeat_at is None:
        return {
            "is_fresh": False,
            "age_seconds": None,
            "phrase": ("we haven't seen a heartbeat from the conductor yet — it may not be running on this product."),
        }

    if now is None:
        now = datetime.now(timezone.utc)

    try:
        beat_dt = _parse_iso(last_heartbeat_at)
    except (ValueError, AttributeError):
        # Unparseable timestamp behaves like a missing heartbeat — honest
        # fallback rather than crashing the live panel render.
        return {
            "is_fresh": False,
            "age_seconds": None,
            "phrase": ("we haven't seen a heartbeat from the conductor yet — it may not be running on this product."),
        }

    # Normalize tz so subtraction works whether either side is naive.
    if beat_dt.tzinfo is None:
        beat_dt = beat_dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age = int((now - beat_dt).total_seconds())
    # Negative ages (clock skew) clamp to zero so the rendered phrase
    # stays honest ("0 seconds ago") instead of producing "-3 seconds ago".
    if age < 0:
        age = 0

    if age <= HEARTBEAT_FRESH_SECONDS:
        return {
            "is_fresh": True,
            "age_seconds": age,
            "phrase": (f"we last heard from the conductor {age} seconds ago — it's actively watching with us."),
        }

    minutes = max(1, age // 60)
    return {
        "is_fresh": False,
        "age_seconds": age,
        "phrase": (
            f"we haven't heard from the conductor in {minutes} minutes — it may be paused or stopped right now."
        ),
    }


def compose_firing_phrase(event: dict[str, Any]) -> str:
    """Render a partner-voice phrase for a conductor.* / quality.* /
    innovation.* journey event.

    Reads `event["topic"]` to dispatch to the topic-aware phrase template.
    For `conductor.track_changed`, reads `event["payload"]` for
    `from_state` and `to_state`; substitutes "an earlier" / "a new" when
    payload values are missing so the length floor still holds.

    Defensive fallback for unknown topic: a partner-voice phrase that
    names the topic honestly. Never includes the substring
    "[unknown topic:".

    All branches open with "we" and reach ≥75 chars even for worst-case
    inputs (minimal field values).
    """
    topic = event.get("topic") or ""

    if topic == "conductor.track_changed":
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        from_state = payload.get("from_state") or "an earlier"
        to_state = payload.get("to_state") or "a new"
        return _TOPIC_PHRASES["conductor.track_changed"].format(
            from_state=from_state,
            to_state=to_state,
        )

    template = _TOPIC_PHRASES.get(topic)
    if template is not None:
        return template

    # Unknown-topic defensive fallback. Names the topic honestly. Length
    # floor: "we observed a abc signal from the conductor in our shared
    # journey just now." → 75 chars when topic is exactly 3 chars.
    safe_topic = topic if topic else "unrecognized"
    return f"we observed a {safe_topic} signal from the conductor in our shared journey just now."


def _render_relative_time(stuck_since: str | datetime | None, now: datetime | None = None) -> str:
    """Render a partner-voice relative-time phrase ('5 minutes ago',
    '2 hours ago', 'just now', or 'an unspecified time' when None).

    Defensive: tolerates str | datetime | None per the same pattern as
    _parse_iso. Never raises; unparseable inputs collapse to the honest
    "an unspecified time" branch.
    """
    if stuck_since is None:
        return "an unspecified time"

    try:
        stuck_dt = _parse_iso(stuck_since)
    except (ValueError, AttributeError):
        return "an unspecified time"

    if now is None:
        now = datetime.now(timezone.utc)

    if stuck_dt.tzinfo is None:
        stuck_dt = stuck_dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age = int((now - stuck_dt).total_seconds())
    if age < 5:
        return "just now"
    if age < 60:
        return f"{age} seconds ago"
    if age < 3600:
        minutes = age // 60
        return f"{minutes} minutes ago" if minutes != 1 else "1 minute ago"
    if age < 86400:
        hours = age // 3600
        return f"{hours} hours ago" if hours != 1 else "1 hour ago"
    days = age // 86400
    return f"{days} days ago" if days != 1 else "1 day ago"


def compose_pending_gate_phrase(track: dict[str, Any]) -> str:
    """Render a partner-voice phrase for a track in gate_pending state.

    Reads `track["name"]` (defaulting to "an unnamed track") and
    `track["stuck_since"]` (str | datetime | None — defaulting to
    "an unspecified time" when missing or unparseable).

    Always opens with "we" and reaches ≥75 chars even for the empty-dict
    worst case.
    """
    name = track.get("name") or "an unnamed track"
    stuck_since_human = _render_relative_time(track.get("stuck_since"))
    return (
        f"we have {name} waiting at a gate since {stuck_since_human} — your call when you're ready to move it forward."
    )
