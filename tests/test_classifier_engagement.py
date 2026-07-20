# tests/test_classifier_engagement.py
"""Tests for engagement validation in the classifier."""


def test_none_engagement_defaults_to_single_spin():
    """None engagement returns single-perspective default."""
    from core.engine.orchestrator.classifier import _validate_engagement

    result = _validate_engagement(None, "practitioner")
    assert result["perspectives"] == ["practitioner"]
    assert result["adversarial_pair"] is None
    assert result["rationale"] == ""


def test_empty_dict_defaults():
    """Empty dict engagement falls back to single primary perspective."""
    from core.engine.orchestrator.classifier import _validate_engagement

    result = _validate_engagement({}, "strategist")
    assert result["perspectives"] == ["strategist"]
    assert result["adversarial_pair"] is None
    assert result["rationale"] == ""


def test_valid_engagement_preserved():
    """Valid engagement dict is preserved as-is."""
    from core.engine.orchestrator.classifier import _validate_engagement

    engagement = {
        "perspectives": ["theorist", "practitioner"],
        "adversarial_pair": None,
        "rationale": "Grounding before building.",
    }
    result = _validate_engagement(engagement, "theorist")
    assert result["perspectives"] == ["theorist", "practitioner"]
    assert result["adversarial_pair"] is None
    assert result["rationale"] == "Grounding before building."


def test_perspectives_capped_at_4():
    """Perspectives list is capped at 4 entries."""
    from core.engine.orchestrator.classifier import _validate_engagement

    engagement = {
        "perspectives": ["theorist", "practitioner", "strategist", "operator", "theorist"],
        "adversarial_pair": None,
        "rationale": "",
    }
    result = _validate_engagement(engagement, "theorist")
    assert len(result["perspectives"]) == 4


def test_invalid_perspectives_filtered():
    """Unknown perspective values are filtered out."""
    from core.engine.orchestrator.classifier import _validate_engagement

    engagement = {
        "perspectives": ["theorist", "wizard", "practitioner"],
        "adversarial_pair": None,
        "rationale": "",
    }
    result = _validate_engagement(engagement, "theorist")
    assert result["perspectives"] == ["theorist", "practitioner"]


def test_operator_in_adversarial_downgraded():
    """adversarial_pair containing 'operator' is set to None."""
    from core.engine.orchestrator.classifier import _validate_engagement

    engagement = {
        "perspectives": ["strategist", "operator"],
        "adversarial_pair": ["strategist", "operator"],
        "rationale": "Debate",
    }
    result = _validate_engagement(engagement, "strategist")
    assert result["adversarial_pair"] is None


def test_adversarial_pair_must_be_in_perspectives():
    """adversarial_pair members not in perspectives list is set to None."""
    from core.engine.orchestrator.classifier import _validate_engagement

    engagement = {
        "perspectives": ["practitioner"],
        "adversarial_pair": ["theorist", "strategist"],
        "rationale": "conflict",
    }
    result = _validate_engagement(engagement, "practitioner")
    assert result["adversarial_pair"] is None


def test_valid_adversarial_pair():
    """Valid adversarial pair (both in perspectives, no operator) is preserved."""
    from core.engine.orchestrator.classifier import _validate_engagement

    engagement = {
        "perspectives": ["theorist", "strategist"],
        "adversarial_pair": ["theorist", "strategist"],
        "rationale": "High-stakes decision.",
    }
    result = _validate_engagement(engagement, "theorist")
    assert result["adversarial_pair"] == ["theorist", "strategist"]


def test_rationale_truncated():
    """Rationale longer than 500 chars is truncated to 500."""
    from core.engine.orchestrator.classifier import _validate_engagement

    long_rationale = "x" * 600
    engagement = {
        "perspectives": ["practitioner"],
        "adversarial_pair": None,
        "rationale": long_rationale,
    }
    result = _validate_engagement(engagement, "practitioner")
    assert len(result["rationale"]) == 500


def test_validate_includes_engagement():
    """Full _validate() returns an 'engagement' key."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "testing",
            "archetype": "analyst",
            "mode": "deliberative",
            "complexity": "moderate",
            "perspective": "theorist",
            "specialties": [],
            "org_context": [],
            "engagement": {
                "perspectives": ["theorist", "practitioner"],
                "adversarial_pair": None,
                "rationale": "Need grounding first.",
            },
        }
    )
    assert "engagement" in result
    assert result["engagement"]["perspectives"] == ["theorist", "practitioner"]
    assert result["engagement"]["adversarial_pair"] is None
    assert result["engagement"]["rationale"] == "Need grounding first."
