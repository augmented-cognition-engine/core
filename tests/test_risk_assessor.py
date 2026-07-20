"""Tests for gate risk assessment."""

from core.engine.pm.risk_assessor import assess_risk

HIGH_RISK_DISCIPLINES = {"security", "architecture", "data_modeling"}


def test_low_risk_simple_idea():
    result = assess_risk(
        entity_type="idea",
        context={"complexity": "simple", "disciplines": ["testing"], "file_count": 2},
    )
    assert result["risk_level"] == "low"
    assert result["auto_approve"] is True


def test_high_risk_security_discipline():
    result = assess_risk(
        entity_type="idea",
        context={"complexity": "moderate", "disciplines": ["security"], "file_count": 3},
    )
    assert result["risk_level"] == "high"
    assert result["auto_approve"] is False
    assert "security" in result["risk_factors"][0].lower()


def test_high_risk_many_files():
    result = assess_risk(
        entity_type="work_item",
        context={"complexity": "moderate", "disciplines": ["testing"], "file_count": 15},
    )
    assert result["risk_level"] == "high"
    assert result["auto_approve"] is False


def test_medium_risk_moderate_files():
    result = assess_risk(
        entity_type="initiative",
        context={"complexity": "moderate", "disciplines": ["testing", "devops"], "file_count": 6},
    )
    assert result["risk_level"] == "medium"
    assert result["auto_approve"] is True  # medium = auto-approve with notification


def test_high_risk_cross_capability():
    result = assess_risk(
        entity_type="initiative",
        context={
            "complexity": "complex",
            "disciplines": ["testing"],
            "file_count": 3,
            "capability_count": 3,
        },
    )
    assert result["risk_level"] == "high"
    assert result["auto_approve"] is False


def test_empty_context_defaults_to_low():
    result = assess_risk(entity_type="idea", context={})
    assert result["risk_level"] == "low"
    assert result["auto_approve"] is True


def test_result_has_all_fields():
    result = assess_risk(entity_type="idea", context={})
    assert "risk_level" in result
    assert "auto_approve" in result
    assert "reason" in result
    assert "risk_factors" in result
