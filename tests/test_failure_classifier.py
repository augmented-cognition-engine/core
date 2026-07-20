from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.intelligence.failure_classifier import FailureCategory, FailureClassifier


def test_failure_category_values():
    assert FailureCategory.MISSING_EDGE_CASE == "missing_edge_case"
    assert FailureCategory.INCOMPLETE_IMPL == "incomplete_implementation"
    assert FailureCategory.LOGIC_ERROR == "logic_error"
    assert FailureCategory.OFF_SPEC == "off_spec"
    assert FailureCategory.SECURITY_GAP == "security_gap"
    assert FailureCategory.MISSING_ERROR_HANDLING == "missing_error_handling"
    assert FailureCategory.CONTEXT_LOSS == "context_loss"
    assert FailureCategory.OVERCOMPLICATED == "overcomplicated"
    assert FailureCategory.OTHER == "other"


@pytest.mark.asyncio
async def test_capture_writes_observation():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    with patch("core.engine.intelligence.failure_classifier.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        clf = FailureClassifier(product_id="product:test")
        await clf.capture(
            discipline="coding",
            task_type="implementation",
            category=FailureCategory.MISSING_EDGE_CASE,
            issues=["no null check on user.email"],
        )
    mock_db.query.assert_called_once()
    call_args = mock_db.query.call_args
    assert "CREATE observation" in call_args[0][0]
    params = call_args[0][1]
    assert params["type"] == "correction"
    assert params["domain_path"] == "coding"
    assert "missing_edge_case" in params["content"]


@pytest.mark.asyncio
async def test_capture_other_with_other_text():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    with patch("core.engine.intelligence.failure_classifier.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        clf = FailureClassifier(product_id="product:test")
        await clf.capture(
            discipline="coding",
            task_type="implementation",
            category=FailureCategory.OTHER,
            issues=["unexpected pattern"],
            other_text="model refused to produce code",
        )
    params = mock_db.query.call_args[0][1]
    assert "model refused to produce code" in params["content"]


@pytest.mark.asyncio
async def test_capture_opus_success_writes_observation():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    with patch("core.engine.intelligence.failure_classifier.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        clf = FailureClassifier(product_id="product:test")
        await clf.capture_opus_success(
            discipline="coding",
            task_type="implementation",
            sonnet_output="short output",
            opus_output="much longer complete output",
        )
    mock_db.query.assert_called_once()
    params = mock_db.query.call_args[0][1]
    assert "complexity_signal" in params["content"]
    assert params["domain_path"] == "coding"


@pytest.mark.asyncio
async def test_capture_is_non_fatal_on_db_error():
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(side_effect=Exception("db error"))
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    with patch("core.engine.intelligence.failure_classifier.pool") as mock_pool:
        mock_pool.connection.return_value = mock_conn
        clf = FailureClassifier()
        await clf.capture(
            discipline="coding", task_type="impl", category=FailureCategory.LOGIC_ERROR, issues=["bad logic"]
        )
