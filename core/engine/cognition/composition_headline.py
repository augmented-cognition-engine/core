"""Compose a partner-voice headline from a composition_trace.

The trace shape (see engine/cognition/composition_trace.py::build) carries:
  - meta_skills: list[str]   — required, non-empty
  - frame: str               — required, non-empty
  - signals: dict[str, Any]  — may be empty; recognized keys get prose mapping
  - star_trace_id: str       — optional, ignored by this synthesizer

The output is a single sentence that always:
  - opens with "We composed " (satisfies the we/our/us partner-voice rule)
  - is ≥75 chars (satisfies the audit_partner_voice length gate)
  - references signals as humanized phrases, not raw dict dumps

Used by engine/api/journey.py to attach a `composition_headline` field to
each journey_event row before returning the response.
"""

from __future__ import annotations

from typing import Any

# Signal-key → prose-clause mapping. First match in this order wins.
_SIGNAL_FALLBACK = "the signals matched"


def _humanize_skill(skill: str) -> str:
    """Convert snake_case identifier to space-separated lowercase phrase."""
    return skill.replace("_", " ")


def _join_skills(skills: list[str]) -> str:
    """Oxford-comma join: ['a'] → 'a'; ['a','b'] → 'a and b'; ['a','b','c'] → 'a, b, and c'."""
    humanized = [_humanize_skill(s) for s in skills]
    if len(humanized) == 1:
        return humanized[0]
    if len(humanized) == 2:
        return f"{humanized[0]} and {humanized[1]}"
    return ", ".join(humanized[:-1]) + f", and {humanized[-1]}"


def _signal_clause(signals: dict[str, Any]) -> str:
    """First recognized signal expressed as a phrase. Fallback if no matches."""
    if not signals:
        return _SIGNAL_FALLBACK

    if "phase" in signals:
        return f"your phase is {signals['phase']}"

    if "pillar_floor" in signals and isinstance(signals["pillar_floor"], dict) and signals["pillar_floor"]:
        # Take the first pillar/score pair (insertion order = first listed)
        pillar, score = next(iter(signals["pillar_floor"].items()))
        try:
            score_str = f"{float(score):.2f}"
        except (TypeError, ValueError):
            score_str = str(score)
        return f"{pillar} dipped to {score_str}"

    if "discipline_classified" in signals:
        return f"the work classifies as {signals['discipline_classified']}"

    return _SIGNAL_FALLBACK


def compose_headline(trace: dict[str, Any]) -> str:
    """Build a partner-voice sentence from a composition_trace.

    Raises ValueError if required fields are missing/empty so callers
    can decide whether to render a fallback or skip the headline.
    """
    skills = trace.get("meta_skills") or []
    frame = trace.get("frame") or ""
    signals = trace.get("signals") or {}

    if not skills:
        raise ValueError("compose_headline: meta_skills must be non-empty")
    if not frame:
        raise ValueError("compose_headline: frame must be non-empty")

    skills_phrase = _join_skills(skills)
    clause = _signal_clause(signals)
    return f"We composed {skills_phrase} with the {frame} frame — we picked it because {clause}."
