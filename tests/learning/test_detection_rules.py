"""Tests for engine/learning/detection_rules.py"""


def test_trigger_rule_recommendation():
    from core.engine.learning.detection_rules import trigger_rule_for

    rule = trigger_rule_for("canvas.recommendation.shifted", {"top_pillar": "experience", "top_discipline": "ux"})
    assert rule is not None
    assert rule.emission_kind == "recommendation"


def test_trigger_rule_uncertainty():
    from core.engine.learning.detection_rules import trigger_rule_for

    rule = trigger_rule_for("canvas.uncertainty.opened", {"query_id": "q123"})
    assert rule is not None
    assert rule.emission_kind == "uncertainty"


def test_trigger_rule_drift_up():
    """drift trigger only fires when new_blocked_frac > prev_blocked_frac (up direction)."""
    from core.engine.learning.detection_rules import trigger_rule_for

    # up direction: should trigger
    rule = trigger_rule_for(
        "canvas.drift.crossed",
        {"new_blocked_frac": 0.6, "prev_blocked_frac": 0.3},
    )
    assert rule is not None
    assert rule.emission_kind == "drift"


def test_trigger_rule_drift_down_no_trigger():
    """drift does NOT trigger when drift is going down."""
    from core.engine.learning.detection_rules import trigger_rule_for

    # down direction: should NOT trigger (drift rule only opens on up)
    rule = trigger_rule_for(
        "canvas.drift.crossed",
        {"new_blocked_frac": 0.2, "prev_blocked_frac": 0.5},
    )
    assert rule is None


def test_trigger_rule_intelligence_classified():
    from core.engine.learning.detection_rules import trigger_rule_for

    rule = trigger_rule_for("canvas.intelligence.classified", {"observation_id": "obs:1", "discipline": "security"})
    assert rule is not None
    assert rule.emission_kind == "intelligence_classified"


def test_trigger_rule_pattern_matched():
    from core.engine.learning.detection_rules import trigger_rule_for

    rule = trigger_rule_for("canvas.pattern.matched", {"pattern_slug": "missing-auth"})
    assert rule is not None
    assert rule.emission_kind == "pattern_matched"


def test_trigger_rule_unknown_event():
    from core.engine.learning.detection_rules import trigger_rule_for

    rule = trigger_rule_for("canvas.unknown.event", {})
    assert rule is None


def test_action_rules_for_code_edited():
    """canvas.code.edited should match recommendation and intelligence_classified rules."""
    from core.engine.learning.detection_rules import action_rules_for

    rules = action_rules_for("canvas.code.edited")
    kinds = {r.emission_kind for r in rules}
    assert "recommendation" in kinds
    assert "intelligence_classified" in kinds


def test_action_rules_for_uncertainty_answered():
    from core.engine.learning.detection_rules import action_rules_for

    rules = action_rules_for("canvas.uncertainty.answered")
    kinds = {r.emission_kind for r in rules}
    assert "uncertainty" in kinds


def test_action_rules_for_drift_crossed():
    """canvas.drift.crossed is also an action event (for detecting recovery)."""
    from core.engine.learning.detection_rules import action_rules_for

    rules = action_rules_for("canvas.drift.crossed")
    kinds = {r.emission_kind for r in rules}
    assert "drift" in kinds


def test_drift_action_predicate_down():
    """Drift action predicate fires when drift goes DOWN (recovery detected)."""
    from core.engine.learning.detection_rules import DETECTION_RULES

    drift_rule = next(r for r in DETECTION_RULES if r.emission_kind == "drift")
    obs = {"emission_kind": "drift"}
    # down direction: acted on
    assert drift_rule.action_predicate({"new_blocked_frac": 0.1, "prev_blocked_frac": 0.5}, obs) is True
    # up direction: NOT an action
    assert drift_rule.action_predicate({"new_blocked_frac": 0.8, "prev_blocked_frac": 0.3}, obs) is False


def test_emission_id_recommendation_deterministic():
    """For a given payload in the same minute, emission_id must be stable."""
    from core.engine.learning.detection_rules import _id_from_rec

    payload = {"top_pillar": "experience", "top_discipline": "ux"}
    id1 = _id_from_rec(payload)
    id2 = _id_from_rec(payload)
    assert id1 == id2
    assert "experience" in id1
    assert "ux" in id1


def test_emission_id_uncertainty_uses_query_id():
    from core.engine.learning.detection_rules import _id_from_uncertainty

    payload = {"query_id": "q:abc123"}
    assert _id_from_uncertainty(payload) == "q:abc123"


def test_emission_id_drift_deterministic():
    from core.engine.learning.detection_rules import _id_from_drift

    payload = {"product_id": "product:platform"}
    id1 = _id_from_drift(payload)
    id2 = _id_from_drift(payload)
    assert id1 == id2
    assert "product:platform" in id1


def test_emission_id_intelligence_uses_observation_id():
    from core.engine.learning.detection_rules import _id_from_intel

    payload = {"observation_id": "obs:xyz"}
    assert _id_from_intel(payload) == "obs:xyz"


def test_emission_id_pattern_deterministic():
    from core.engine.learning.detection_rules import _id_from_pattern

    payload = {"pattern_slug": "missing-auth"}
    id1 = _id_from_pattern(payload)
    id2 = _id_from_pattern(payload)
    assert id1 == id2
    assert "missing-auth" in id1


def test_discipline_match_predicate():
    from core.engine.learning.detection_rules import _discipline_match

    obs = {"discipline": "security"}
    assert _discipline_match({"discipline": "security"}, obs) is True
    assert _discipline_match({"discipline": "ux"}, obs) is False
    assert _discipline_match({}, obs) is False


def test_query_id_match_predicate():
    from core.engine.learning.detection_rules import _query_id_match

    obs = {"emission_id": "q123"}
    assert _query_id_match({"query_id": "q123"}, obs) is True
    assert _query_id_match({"query_id": "q999"}, obs) is False


def test_pattern_slug_match_predicate():
    from core.engine.learning.detection_rules import _pattern_slug_match

    # emission_topic format: "pattern_matched:missing-auth"
    obs = {"emission_topic": "pattern_matched:missing-auth"}
    assert _pattern_slug_match({"pattern_slug": "missing-auth"}, obs) is True
    assert _pattern_slug_match({"pattern_slug": "other-pattern"}, obs) is False
    assert _pattern_slug_match({}, obs) is False


def test_canvas_event_types_match_enum():
    """All rule event types in DETECTION_RULES reference valid LivingCanvasEventType values."""
    from core.engine.events.canvas import LivingCanvasEventType
    from core.engine.learning.detection_rules import DETECTION_RULES

    valid_prefixed = {f"canvas.{e.value}" for e in LivingCanvasEventType}

    for rule in DETECTION_RULES:
        assert rule.trigger_event_type in valid_prefixed, (
            f"trigger_event_type '{rule.trigger_event_type}' for {rule.emission_kind} not in LivingCanvasEventType"
        )
        for action_et in rule.action_event_types:
            # canvas.code.edited is new (added by this spec) — we check the rest
            if action_et != "canvas.code.edited":
                assert action_et in valid_prefixed, (
                    f"action_event_type '{action_et}' for {rule.emission_kind} not in LivingCanvasEventType"
                )
