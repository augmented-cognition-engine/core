"""Tests for adaptive learning from review reactions."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.review.learning import ReviewLearner


@pytest.mark.asyncio
async def test_record_reaction():
    learner = ReviewLearner()
    mock_result = [{"id": "review_reaction:abc", "reaction": "accepted"}]
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[mock_result])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await learner.record_reaction("owner", "repo", 42, 0, "accepted")
    assert result.get("id") == "review_reaction:abc"


@pytest.mark.asyncio
async def test_get_acceptance_rates_empty():
    learner = ReviewLearner()
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        rates = await learner.get_acceptance_rates("owner", "repo")
    assert rates == {}


@pytest.mark.asyncio
async def test_get_acceptance_rates_with_data():
    learner = ReviewLearner()
    rows = [
        {"reaction": "accepted", "meta": {"discipline": "security"}},
        {"reaction": "accepted", "meta": {"discipline": "security"}},
        {"reaction": "dismissed", "meta": {"discipline": "security"}},
        {"reaction": "accepted", "meta": {"discipline": "testing"}},
    ]
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[rows])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        rates = await learner.get_acceptance_rates("owner", "repo")

    # security: 2 accepted out of 3
    assert abs(rates["security"] - 2 / 3) < 0.001
    # testing: 1 accepted out of 1
    assert rates["testing"] == 1.0


@pytest.mark.asyncio
async def test_feed_to_capture_accepted():
    learner = ReviewLearner()
    finding = {"discipline": "security", "message": "Missing validation"}
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:xyz"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        await learner.feed_to_capture("owner", "repo", finding, "accepted")

    mock_conn.query.assert_called_once()
    call_args = mock_conn.query.call_args
    params = call_args[0][1]
    assert params["type"] == "pattern"
    assert "accepted" in params["content"]
    assert "Missing validation" in params["content"]
    assert params["discipline_hint"] == "security"


@pytest.mark.asyncio
async def test_feed_to_capture_dismissed():
    learner = ReviewLearner()
    finding = {"discipline": "testing", "message": "Test coverage low"}
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[{"id": "observation:xyz"}]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        await learner.feed_to_capture("owner", "repo", finding, "dismissed")

    mock_conn.query.assert_called_once()
    call_args = mock_conn.query.call_args
    params = call_args[0][1]
    assert params["type"] == "correction"
    assert "dismissed" in params["content"]
    assert "false positive" in params["content"]


@pytest.mark.asyncio
async def test_feed_to_capture_modified_is_noop():
    """'modified' reactions are not fed to capture."""
    learner = ReviewLearner()
    finding = {"discipline": "security", "message": "Something"}
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        await learner.feed_to_capture("owner", "repo", finding, "modified")

    mock_conn.query.assert_not_called()


@pytest.mark.asyncio
async def test_feed_to_capture_db_error_is_swallowed():
    """DB errors in feed_to_capture should be logged, not raised."""
    learner = ReviewLearner()
    finding = {"discipline": "security", "message": "Something"}
    with patch("core.engine.review.learning.pool") as mock_pool:
        mock_pool.connection.side_effect = RuntimeError("DB down")
        # Should not raise
        await learner.feed_to_capture("owner", "repo", finding, "accepted")
