from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class DetectionRule:
    emission_kind: str
    trigger_event_type: str  # canvas.* event that opens an observation
    window_days: int
    action_event_types: list[str]  # canvas.* events that count as action
    # Both predicates take (event_payload, existing_observation_dict) → bool
    trigger_predicate: Callable[[dict], bool] = field(default=lambda p: True)
    action_predicate: Callable[[dict, dict], bool] = field(default=lambda p, o: True)
    # How to derive emission_id for idempotency
    emission_id_fn: Callable[[dict], str] = field(default=lambda p: "")


def _drift_up(payload: dict) -> bool:
    return float(payload.get("new_blocked_frac", 0.0)) > float(payload.get("prev_blocked_frac", 0.0))


def _drift_down(payload: dict, _obs) -> bool:
    return float(payload.get("new_blocked_frac", 0.0)) < float(payload.get("prev_blocked_frac", 0.0))


def _discipline_match(payload: dict, obs: dict) -> bool:
    d = payload.get("discipline")
    return bool(d) and d == obs.get("discipline")


def _query_id_match(payload: dict, obs: dict) -> bool:
    return str(payload.get("query_id", "")) == obs.get("emission_id", "")


def _pattern_slug_match(payload: dict, obs: dict) -> bool:
    slug = payload.get("pattern_slug")
    return bool(slug) and slug == obs.get("emission_topic", "").split(":", 1)[-1]


def _bucket(dt) -> str:
    from datetime import datetime, timezone

    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%d%H%M")


def _id_from_rec(payload: dict) -> str:
    return f"rec:{payload.get('top_pillar', '')}.{payload.get('top_discipline', '')}@{_bucket(None)}"


def _id_from_uncertainty(payload: dict) -> str:
    return str(payload.get("query_id", ""))


def _id_from_drift(payload: dict) -> str:
    return f"drift:{payload.get('product_id', '')}@{_bucket(None)}"


def _id_from_intel(payload: dict) -> str:
    return str(payload.get("observation_id", ""))


def _id_from_pattern(payload: dict) -> str:
    return f"pattern:{payload.get('pattern_slug', '')}@{_bucket(None)}"


DETECTION_RULES: list[DetectionRule] = [
    DetectionRule(
        emission_kind="recommendation",
        trigger_event_type="canvas.recommendation.shifted",
        window_days=14,
        action_event_types=[
            "canvas.code.edited",
            "canvas.capability.lifecycle_changed",
            "canvas.intelligence.classified",
        ],
        action_predicate=_discipline_match,
        emission_id_fn=_id_from_rec,
    ),
    DetectionRule(
        emission_kind="uncertainty",
        trigger_event_type="canvas.uncertainty.opened",
        window_days=30,
        action_event_types=["canvas.uncertainty.answered"],
        action_predicate=_query_id_match,
        emission_id_fn=_id_from_uncertainty,
    ),
    DetectionRule(
        emission_kind="drift",
        trigger_event_type="canvas.drift.crossed",
        window_days=14,
        action_event_types=["canvas.drift.crossed"],
        trigger_predicate=_drift_up,
        action_predicate=_drift_down,
        emission_id_fn=_id_from_drift,
    ),
    DetectionRule(
        emission_kind="intelligence_classified",
        trigger_event_type="canvas.intelligence.classified",
        window_days=7,
        action_event_types=["canvas.code.edited"],
        action_predicate=_discipline_match,
        emission_id_fn=_id_from_intel,
    ),
    DetectionRule(
        emission_kind="pattern_matched",
        trigger_event_type="canvas.pattern.matched",
        window_days=14,
        action_event_types=["canvas.pattern.matched"],
        action_predicate=_pattern_slug_match,
        emission_id_fn=_id_from_pattern,
    ),
]


def trigger_rule_for(event_type: str, payload: dict) -> DetectionRule | None:
    for rule in DETECTION_RULES:
        if rule.trigger_event_type == event_type and rule.trigger_predicate(payload):
            return rule
    return None


def action_rules_for(event_type: str) -> list[DetectionRule]:
    return [r for r in DETECTION_RULES if event_type in r.action_event_types]
