# tests/test_classifier.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_classify_returns_discipline():
    """Classifier returns dict containing discipline."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "devops",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": "simple",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Fix the CI pipeline")

    assert result["discipline"] == "devops"


@pytest.mark.asyncio
async def test_classify_defaults_on_llm_failure():
    """Classifier returns safe defaults when LLM fails.

    Default mode is deliberative (not reactive) so that LLM parse failures
    activate multi-phase reasoning rather than silently short-circuiting the
    pipeline via depth:1 / fusion_mode=True.
    """
    from core.engine.orchestrator.classifier import classify_task

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=Exception("LLM error"))
        result = await classify_task("do something")

    assert result["discipline"] == "architecture"
    assert result["archetype"] == "executor"
    assert result["mode"] == "deliberative"  # safer default: activates multi-phase on failure
    assert result["complexity"] == "moderate"  # safer default: avoids depth:1 short-circuit


@pytest.mark.asyncio
async def test_classify_validates_discipline():
    """Classifier rejects invalid discipline values from LLM."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "accounting",
        "archetype": "analyst",
        "mode": "deliberative",
        "complexity": "moderate",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Reconcile accounts")

    assert result["discipline"] == "architecture"


@pytest.mark.asyncio
async def test_classify_returns_full_dict():
    """Classifier returns dict with discipline, archetype, mode, complexity."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "architecture",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Design a new authentication module")

    assert isinstance(result, dict)
    assert result["discipline"] == "architecture"
    assert result["archetype"] == "creator"
    assert result["mode"] == "deliberative"
    assert result["complexity"] == "moderate"


@pytest.mark.asyncio
async def test_classify_validates_enums():
    """Classifier defaults invalid archetype/mode/complexity values."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "archetype": "wizard",
        "mode": "turbo",
        "complexity": "insane",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("something")

    assert result["archetype"] == "executor"
    assert result["mode"] == "reactive"
    assert result["complexity"] == "simple"


# ---------------------------------------------------------------------------
# task_type tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_task_type_debug():
    """Classifier correctly identifies debug task_type."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": "moderate",
        "task_type": "debug",
        "task_type_confidence": 0.95,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Fix the NullPointerException in the auth flow")

    assert result["task_type"] == "debug"
    assert result["task_type_confidence"] == 0.95


@pytest.mark.asyncio
async def test_classify_task_type_implement():
    """Classifier correctly identifies implement task_type."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "architecture",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "task_type": "implement",
        "task_type_confidence": 0.88,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Add pagination to the users API endpoint")

    assert result["task_type"] == "implement"
    assert result["task_type_confidence"] == 0.88


@pytest.mark.asyncio
async def test_classify_task_type_plan():
    """Classifier correctly identifies plan task_type."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "architecture",
        "archetype": "advisor",
        "mode": "deliberative",
        "complexity": "complex",
        "task_type": "plan",
        "task_type_confidence": 0.91,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Decompose the migration into phases")

    assert result["task_type"] == "plan"


@pytest.mark.asyncio
async def test_classify_task_type_review():
    """Classifier correctly identifies review task_type."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "security",
        "archetype": "sentinel",
        "mode": "reflective",
        "complexity": "moderate",
        "task_type": "review",
        "task_type_confidence": 0.93,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Review the PR for security issues")

    assert result["task_type"] == "review"


@pytest.mark.asyncio
async def test_classify_task_type_all_valid_values():
    """Every valid task_type value is accepted by the validator."""
    from core.engine.orchestrator.classifier import TASK_TYPES, classify_task

    for tt in TASK_TYPES:
        mock_response = {
            "discipline": "architecture",
            "task_type": tt,
        }
        with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
            mock_llm.complete_json = AsyncMock(return_value=mock_response)
            result = await classify_task("some task")
        assert result["task_type"] == tt, f"Expected task_type={tt!r}, got {result['task_type']!r}"


@pytest.mark.asyncio
async def test_classify_task_type_invalid_defaults_to_implement():
    """Classifier defaults invalid task_type to implement."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "task_type": "teleport",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("something weird")

    assert result["task_type"] == "implement"


@pytest.mark.asyncio
async def test_classify_task_type_missing_defaults_to_implement():
    """Classifier defaults missing task_type to implement."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {"discipline": "devops"}

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("deploy to prod")

    assert result["task_type"] == "implement"


# ---------------------------------------------------------------------------
# quality_bar tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_quality_bar_draft():
    """Classifier correctly identifies draft quality_bar."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "documentation",
        "quality_bar": "draft",
        "quality_bar_confidence": 0.8,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Quickly sketch out a proposal")

    assert result["quality_bar"] == "draft"
    assert result["quality_bar_confidence"] == 0.8


@pytest.mark.asyncio
async def test_classify_quality_bar_production():
    """Classifier correctly identifies production quality_bar."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "quality_bar": "production",
        "quality_bar_confidence": 0.85,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Ship the user auth feature with tests")

    assert result["quality_bar"] == "production"
    assert result["quality_bar_confidence"] == 0.85


@pytest.mark.asyncio
async def test_classify_quality_bar_critical():
    """Classifier correctly identifies critical quality_bar."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "security",
        "quality_bar": "critical",
        "quality_bar_confidence": 0.97,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Audit the payment flow for PCI compliance")

    assert result["quality_bar"] == "critical"
    assert result["quality_bar_confidence"] == 0.97


@pytest.mark.asyncio
async def test_classify_quality_bar_all_valid_values():
    """Every valid quality_bar value is accepted by the validator."""
    from core.engine.orchestrator.classifier import QUALITY_BARS, classify_task

    for qb in QUALITY_BARS:
        mock_response = {
            "discipline": "architecture",
            "quality_bar": qb,
        }
        with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
            mock_llm.complete_json = AsyncMock(return_value=mock_response)
            result = await classify_task("some task")
        assert result["quality_bar"] == qb, f"Expected quality_bar={qb!r}, got {result['quality_bar']!r}"


@pytest.mark.asyncio
async def test_classify_quality_bar_invalid_defaults_to_production():
    """Classifier defaults invalid quality_bar to production."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "quality_bar": "legendary",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("something")

    assert result["quality_bar"] == "production"


@pytest.mark.asyncio
async def test_classify_quality_bar_missing_defaults_to_production():
    """Classifier defaults missing quality_bar to production."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {"discipline": "architecture"}

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("design a system")

    assert result["quality_bar"] == "production"


# ---------------------------------------------------------------------------
# confidence score tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_scores_present_in_output():
    """All _confidence keys are present in the classifier output."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "security",
        "discipline_confidence": 0.9,
        "archetype": "sentinel",
        "archetype_confidence": 0.85,
        "mode": "deliberative",
        "mode_confidence": 0.8,
        "complexity": "moderate",
        "complexity_confidence": 0.75,
        "perspective": "practitioner",
        "perspective_confidence": 0.8,
        "task_type": "review",
        "task_type_confidence": 0.92,
        "quality_bar": "production",
        "quality_bar_confidence": 0.78,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Review the auth module for vulnerabilities")

    confidence_fields = [
        "discipline_confidence",
        "archetype_confidence",
        "mode_confidence",
        "complexity_confidence",
        "perspective_confidence",
        "task_type_confidence",
        "quality_bar_confidence",
    ]
    for field in confidence_fields:
        assert field in result, f"Missing confidence field: {field}"
        assert isinstance(result[field], float), f"{field} should be a float"
        assert 0.0 <= result[field] <= 1.0, f"{field}={result[field]} out of [0.0, 1.0]"


@pytest.mark.asyncio
async def test_confidence_defaults_when_missing():
    """Classifier defaults confidence to 0.7 when absent from LLM response."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": "simple",
        "task_type": "verify",
        "quality_bar": "production",
        # no confidence keys at all
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Run the test suite")

    confidence_fields = [
        "discipline_confidence",
        "archetype_confidence",
        "mode_confidence",
        "complexity_confidence",
        "perspective_confidence",
        "task_type_confidence",
        "quality_bar_confidence",
    ]
    for field in confidence_fields:
        assert result[field] == 0.7, f"{field} should default to 0.7, got {result[field]}"


@pytest.mark.asyncio
async def test_confidence_clipped_above_one():
    """Confidence values above 1.0 are clipped to 0.7 default."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "discipline_confidence": 1.5,  # invalid: above 1.0
        "task_type": "verify",
        "task_type_confidence": 2.0,  # invalid
        "quality_bar": "production",
        "quality_bar_confidence": 0.9,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Run checks")

    assert result["discipline_confidence"] == 0.7
    assert result["task_type_confidence"] == 0.7
    assert result["quality_bar_confidence"] == 0.9


@pytest.mark.asyncio
async def test_confidence_clipped_below_zero():
    """Confidence values below 0.0 are clipped to 0.7 default."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "discipline_confidence": -0.1,  # invalid: below 0.0
        "task_type": "debug",
        "task_type_confidence": -1.0,  # invalid
        "quality_bar": "draft",
        "quality_bar_confidence": 0.0,  # edge: exactly 0.0 is valid
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("find the bug")

    assert result["discipline_confidence"] == 0.7
    assert result["task_type_confidence"] == 0.7
    assert result["quality_bar_confidence"] == 0.0  # 0.0 is valid


@pytest.mark.asyncio
async def test_confidence_invalid_type_defaults():
    """Non-numeric confidence values default to 0.7."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "security",
        "discipline_confidence": "high",  # invalid type
        "task_type": "review",
        "task_type_confidence": None,  # invalid type
        "quality_bar": "critical",
        "quality_bar_confidence": True,  # bool: True == 1.0, which is valid
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("security audit")

    assert result["discipline_confidence"] == 0.7
    assert result["task_type_confidence"] == 0.7
    # True casts to 1.0 in Python, which is within [0.0, 1.0]
    assert result["quality_bar_confidence"] == 1.0


@pytest.mark.asyncio
async def test_confidence_scores_in_default_fallback():
    """Default fallback dict includes all confidence fields at 0.5.

    Defaults are 0.5 (not 0.7) to signal genuine uncertainty — a parse failure
    should not look like a confident classification.
    """
    from core.engine.orchestrator.classifier import classify_task

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=Exception("boom"))
        result = await classify_task("anything")

    confidence_fields = [
        "discipline_confidence",
        "archetype_confidence",
        "mode_confidence",
        "complexity_confidence",
        "perspective_confidence",
        "task_type_confidence",
        "quality_bar_confidence",
    ]
    for field in confidence_fields:
        assert field in result, f"Missing confidence field in default: {field}"
        assert result[field] == 0.5, f"{field} default should be 0.5, got {result[field]}"


# ---------------------------------------------------------------------------
# complexity: new "ambiguous" value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_complexity_ambiguous():
    """Classifier accepts the new 'ambiguous' complexity value."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "architecture",
        "archetype": "advisor",
        "mode": "conversational",
        "complexity": "ambiguous",
        "complexity_confidence": 0.6,
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("not sure what this is")

    assert result["complexity"] == "ambiguous"
    assert result["complexity_confidence"] == 0.6


# ---------------------------------------------------------------------------
# backward-compatibility: existing callers only reading old fields still work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backward_compat_existing_fields_present():
    """All original output fields are still present alongside new ones."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "devops",
        "archetype": "executor",
        "mode": "procedural",
        "complexity": "simple",
        "perspective": "operator",
        "specialties": ["ci-cd"],
        "org_context": ["startup"],
        "engagement": {"perspectives": ["operator"], "adversarial_pair": None, "rationale": "ops task"},
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("Deploy the app to staging")

    # Original fields
    assert result["discipline"] == "devops"
    assert result["archetype"] == "executor"
    assert result["mode"] == "procedural"
    assert result["complexity"] == "simple"
    assert result["perspective"] == "operator"
    assert result["specialties"] == ["ci-cd"]
    assert result["org_context"] == ["startup"]
    assert result["engagement"]["perspectives"] == ["operator"]

    # New fields also present
    assert "task_type" in result
    assert "quality_bar" in result
    assert "task_type_confidence" in result
    assert "quality_bar_confidence" in result


# ---------------------------------------------------------------------------
# Low-confidence guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_mode_confidence_overrides_reactive_to_deliberative():
    """When mode_confidence < 0.5 and mode is reactive, override to deliberative.

    reactive + depth:1 → fusion_mode=True → MultiPhaseExecutor returns '' (silent kill).
    deliberative activates multi-phase and produces output even on misrouted tasks.
    """
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "architecture",
        "archetype": "executor",
        "mode": "reactive",
        "mode_confidence": 0.3,  # low confidence — model is unsure
        "complexity": "moderate",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("something ambiguous")

    assert result["mode"] == "deliberative"  # override fired
    assert result["mode_confidence"] == 0.3  # original low score preserved for observability


@pytest.mark.asyncio
async def test_low_mode_confidence_does_not_override_non_reactive():
    """Low mode_confidence only overrides reactive, not other modes."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "architecture",
        "archetype": "analyst",
        "mode": "exploratory",
        "mode_confidence": 0.35,  # low confidence — but mode is not reactive
        "complexity": "moderate",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("investigate something")

    assert result["mode"] == "exploratory"  # NOT overridden


@pytest.mark.asyncio
async def test_high_mode_confidence_reactive_is_kept():
    """High mode_confidence reactive tasks are not overridden."""
    from core.engine.orchestrator.classifier import classify_task

    mock_response = {
        "discipline": "testing",
        "archetype": "executor",
        "mode": "reactive",
        "mode_confidence": 0.95,  # high confidence
        "complexity": "simple",
    }

    with patch("core.engine.orchestrator.classifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=mock_response)
        result = await classify_task("run the tests")

    assert result["mode"] == "reactive"  # kept — model was confident


# ---------------------------------------------------------------------------
# routing_correction: record and load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_routing_correction_writes_to_db():
    """record_routing_correction writes a routing_correction record."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.orchestrator.classifier import record_routing_correction

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=[])
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    # pool is imported at call time from engine.core.db — patch the source module
    with patch("core.engine.core.db.pool", mock_pool):
        result = await record_routing_correction(
            product_id="product:test",
            task_summary="B2B SaaS startup churn question",
            wrong_discipline="architecture",
            wrong_mode="reactive",
            wrong_archetype="executor",
            correct_discipline="business_logic",
            correct_mode="deliberative",
            correct_archetype="advisor",
            reason="Business strategy question misrouted to software architecture",
        )

    assert result is True
    mock_conn.query.assert_called_once()
    call_args = mock_conn.query.call_args[0]
    assert "routing_correction" in call_args[0]


@pytest.mark.asyncio
async def test_record_routing_correction_returns_false_on_error():
    """record_routing_correction returns False on DB failure."""
    from unittest.mock import MagicMock, patch

    from core.engine.orchestrator.classifier import record_routing_correction

    mock_pool = MagicMock()
    mock_pool.connection.side_effect = Exception("DB down")

    with patch("core.engine.core.db.pool", mock_pool):
        result = await record_routing_correction(
            product_id="product:test",
            task_summary="anything",
            wrong_discipline="architecture",
            wrong_mode="reactive",
            wrong_archetype="executor",
            correct_discipline="business_logic",
            correct_mode="deliberative",
            correct_archetype="advisor",
        )

    assert result is False
