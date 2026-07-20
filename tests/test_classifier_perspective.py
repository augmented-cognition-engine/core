# tests/test_classifier_perspective.py
"""Tests for perspective, specialties, and org_context classification dimensions."""

from unittest.mock import AsyncMock, patch

import pytest


def test_perspectives_defined():
    """PERSPECTIVES set has exactly 4 values."""
    from core.engine.orchestrator.classifier import PERSPECTIVES

    assert PERSPECTIVES == {"theorist", "practitioner", "strategist", "operator"}


def test_validate_preserves_valid_perspective():
    """Valid perspective passes through _validate unchanged."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "architecture",
            "archetype": "analyst",
            "mode": "deliberative",
            "complexity": "moderate",
            "perspective": "theorist",
            "specialties": [],
            "org_context": [],
        }
    )
    assert result["perspective"] == "theorist"


def test_validate_defaults_invalid_perspective():
    """Invalid perspective is replaced with 'practitioner'."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "testing",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "perspective": "wizard",
        }
    )
    assert result["perspective"] == "practitioner"


def test_validate_defaults_missing_specialties():
    """Missing specialties key defaults to empty list."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "testing",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
        }
    )
    assert result["specialties"] == []


def test_validate_sanitizes_specialties_to_kebab():
    """Specialties are sanitized to kebab-case and capped at 3."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "devops",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "specialties": ["Cloud Security", "FinOps", "MLOps", "DataOps", "DevOps"],
        }
    )
    assert result["specialties"] == ["cloud-security", "finops", "mlops"]


def test_validate_org_context_capped_at_5():
    """org_context is capped at 5 entries."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "testing",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "org_context": ["a", "b", "c", "d", "e", "f", "g"],
        }
    )
    assert result["org_context"] == ["a", "b", "c", "d", "e"]


def test_validate_org_context_non_list_defaults_to_empty():
    """Non-list org_context is replaced with empty list."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "testing",
            "archetype": "executor",
            "mode": "reactive",
            "complexity": "simple",
            "org_context": "not-a-list",
        }
    )
    assert result["org_context"] == []


def test_validate_preserves_valid_discipline():
    """Valid discipline passes through _validate unchanged."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "security",
            "archetype": "sentinel",
            "mode": "deliberative",
            "complexity": "moderate",
        }
    )
    assert result["discipline"] == "security"


def test_validate_rejects_invalid_discipline():
    """Invalid discipline is replaced with 'architecture'."""
    from core.engine.orchestrator.classifier import _validate

    result = _validate(
        {
            "discipline": "finance",
            "archetype": "analyst",
            "mode": "deliberative",
            "complexity": "moderate",
        }
    )
    assert result["discipline"] == "architecture"


@pytest.mark.asyncio
async def test_classify_task_returns_perspective():
    """classify_task result includes perspective field."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "devops",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "perspective": "practitioner",
        "specialties": ["platform-engineering"],
        "org_context": [],
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Build a new deployment pipeline")

    assert "perspective" in result
    assert result["perspective"] == "practitioner"
    assert "specialties" in result
    assert "org_context" in result


@pytest.mark.asyncio
async def test_classify_task_accepts_org_id():
    """classify_task accepts product_id kwarg without breaking."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "deployment",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": "simple",
        "perspective": "operator",
        "specialties": [],
        "org_context": [],
    }

    with (
        patch("core.engine.orchestrator.classifier.llm") as mock_llm,
        patch("core.engine.orchestrator.classifier._load_specialty_catalog", new_callable=AsyncMock, return_value=""),
        patch("core.engine.orchestrator.classifier._load_discipline_catalog", return_value=""),
    ):
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Run the nightly batch job", product_id="org:acme")

    assert result["perspective"] == "operator"


@pytest.mark.asyncio
async def test_classify_task_defaults_include_new_fields():
    """On LLM failure, defaults include perspective, specialties, org_context."""
    from core.engine.orchestrator.classifier import classify_task

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM down"))
        result = await classify_task("do something")

    assert result["perspective"] == "practitioner"
    assert result["specialties"] == []
    assert result["org_context"] == []
    assert result["discipline"] == "architecture"
    assert result["archetype"] == "executor"
