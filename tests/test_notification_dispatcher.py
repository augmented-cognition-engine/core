# tests/test_notification_dispatcher.py
"""Tests for notification dispatcher and trigger functions."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_dispatch_creates_notification():
    """Dispatch creates a notification record."""
    from core.engine.notifications.dispatcher import dispatch

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "notification:n1",
                        "tier": "critical",
                        "category": "conflict_detected",
                        "title": "Conflict found",
                        "read": False,
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dispatch(
            product_id="product:test",
            user_id="user:test",
            tier="critical",
            category="conflict_detected",
            title="Conflict found",
        )

    assert result["tier"] == "critical"
    assert result["read"] is False
    create_query = next(
        call.args[0] for call in mock_conn.query.call_args_list if "CREATE notification" in call.args[0]
    )
    assert "product = <record>$product" in create_query


@pytest.mark.asyncio
async def test_dispatch_uses_default_channels():
    """Without explicit prefs, critical gets in_app delivery."""
    from core.engine.notifications.dispatcher import dispatch

    created_params = None

    async def track_create(query_str, params=None):
        nonlocal created_params
        if "CREATE notification" in query_str:
            created_params = params
            return [[{"id": "notification:n2", "tier": "critical", "delivered_via": ["in_app"]}]]
        return [[]]  # pref query returns empty

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = track_create
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await dispatch("product:test", "user:test", "critical", "test", "Test")

    assert created_params is not None
    assert "in_app" in created_params["channels"]


@pytest.mark.asyncio
async def test_trigger_conflict_detected():
    """Conflict detection creates critical notification."""
    from core.engine.notifications.triggers import notify_conflict_detected

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "notification:c1",
                        "tier": "critical",
                        "category": "conflict_detected",
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await notify_conflict_detected("product:test", "user:test", "conflict:c1")

    assert result["tier"] == "critical"
    assert result["category"] == "conflict_detected"


@pytest.mark.asyncio
async def test_trigger_idea_ready():
    """Idea ready creates actionable notification."""
    from core.engine.notifications.triggers import notify_idea_ready

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "notification:i1",
                        "tier": "actionable",
                        "category": "idea_ready",
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await notify_idea_ready("product:test", "user:test", "Multi-brand tokens", "idea:1")

    assert result["tier"] == "actionable"


@pytest.mark.asyncio
async def test_trigger_briefing_ready():
    """Briefing ready creates actionable notification."""
    from core.engine.notifications.triggers import notify_briefing_ready

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "id": "notification:b1",
                        "tier": "actionable",
                        "category": "briefing_ready",
                    }
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await notify_briefing_ready("product:test", "user:test", "briefing:b1")

    assert result["tier"] == "actionable"


@pytest.mark.asyncio
async def test_trigger_tier_mapping():
    """All triggers map to the correct tier."""
    from core.engine.notifications.triggers import TRIGGER_TIERS

    assert TRIGGER_TIERS["approval_needed"] == "critical"
    assert TRIGGER_TIERS["conflict_detected"] == "critical"
    assert TRIGGER_TIERS["engine_error"] == "critical"
    assert TRIGGER_TIERS["milestone_completed"] == "actionable"
    assert TRIGGER_TIERS["idea_ready"] == "actionable"
    assert TRIGGER_TIERS["synapse_proposal"] == "informational"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_failure_returns_fallback_stub():
    """When dispatch raises on every attempt, a fallback stub is returned (no raise)."""
    import core.engine.notifications.dispatcher as dispatcher_mod
    from core.engine.notifications.dispatcher import dispatch

    original_max = dispatcher_mod.RETRY_MAX_ATTEMPTS
    original_base = dispatcher_mod.RETRY_BASE_DELAY
    try:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = 1
        dispatcher_mod.RETRY_BASE_DELAY = 0.0

        with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(side_effect=RuntimeError("DB unavailable"))
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await dispatch(
                product_id="product:test",
                user_id="user:test",
                tier="critical",
                category="engine_error",
                title="Crash",
            )

    finally:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = original_max
        dispatcher_mod.RETRY_BASE_DELAY = original_base

    # Must not raise; must return a fallback dict
    assert result["tier"] == "critical"
    assert result["category"] == "engine_error"
    assert result["_dispatch_failed"] is True
    assert "DB unavailable" in result["_error"]


@pytest.mark.asyncio
async def test_dispatch_retries_on_transient_failure():
    """Dispatch retries after a transient failure and succeeds on the second attempt."""
    import core.engine.notifications.dispatcher as dispatcher_mod
    from core.engine.notifications.dispatcher import dispatch

    original_max = dispatcher_mod.RETRY_MAX_ATTEMPTS
    original_base = dispatcher_mod.RETRY_BASE_DELAY
    call_count = 0

    async def flaky_query(query_str, params=None):
        nonlocal call_count
        if "CREATE notification" in query_str:
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            return [[{"id": "notification:r1", "tier": "actionable", "category": "briefing_ready"}]]
        return [[]]

    try:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = 3
        dispatcher_mod.RETRY_BASE_DELAY = 0.0

        with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = flaky_query
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await dispatch(
                product_id="product:test",
                user_id="user:test",
                tier="actionable",
                category="briefing_ready",
                title="Briefing ready",
            )

    finally:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = original_max
        dispatcher_mod.RETRY_BASE_DELAY = original_base

    assert result["tier"] == "actionable"
    assert "_dispatch_failed" not in result
    assert call_count == 2  # failed once, succeeded on retry


@pytest.mark.asyncio
async def test_dispatch_failure_does_not_block_caller():
    """Caller receives a result even when all retries fail (no exception raised)."""
    import core.engine.notifications.dispatcher as dispatcher_mod
    from core.engine.notifications.dispatcher import dispatch

    original_max = dispatcher_mod.RETRY_MAX_ATTEMPTS
    original_base = dispatcher_mod.RETRY_BASE_DELAY
    try:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = 2
        dispatcher_mod.RETRY_BASE_DELAY = 0.0

        with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(side_effect=OSError("network error"))
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should complete without raising
            result = await dispatch("org:x", "user:x", "informational", "synapse_proposal", "New synapse")

    finally:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = original_max
        dispatcher_mod.RETRY_BASE_DELAY = original_base

    assert isinstance(result, dict)
    assert result.get("_dispatch_failed") is True


@pytest.mark.asyncio
async def test_dispatch_failure_logged_with_details(caplog):
    """Failed dispatch is logged with tier, category, title, and error info."""
    import logging

    import core.engine.notifications.dispatcher as dispatcher_mod
    from core.engine.notifications.dispatcher import dispatch

    original_max = dispatcher_mod.RETRY_MAX_ATTEMPTS
    original_base = dispatcher_mod.RETRY_BASE_DELAY
    try:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = 1
        dispatcher_mod.RETRY_BASE_DELAY = 0.0

        with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(side_effect=ValueError("bad value"))
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            with caplog.at_level(logging.ERROR, logger="core.engine.notifications.dispatcher"):
                await dispatch("org:log", "user:log", "critical", "engine_error", "Crash title")

    finally:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = original_max
        dispatcher_mod.RETRY_BASE_DELAY = original_base

    # At least one ERROR log should mention tier, category, and the error type
    error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_logs, "Expected at least one ERROR log entry"
    combined = " ".join(r.message for r in error_logs)
    assert "critical" in combined
    assert "engine_error" in combined
    assert "ValueError" in combined or "bad value" in combined


@pytest.mark.asyncio
async def test_dispatch_all_retries_exhausted_logs_permanently_failed(caplog):
    """When all retries are exhausted a 'permanently failed' log is emitted."""
    import logging

    import core.engine.notifications.dispatcher as dispatcher_mod
    from core.engine.notifications.dispatcher import dispatch

    original_max = dispatcher_mod.RETRY_MAX_ATTEMPTS
    original_base = dispatcher_mod.RETRY_BASE_DELAY
    try:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = 2
        dispatcher_mod.RETRY_BASE_DELAY = 0.0

        with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(side_effect=RuntimeError("persistent failure"))
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            with caplog.at_level(logging.ERROR, logger="core.engine.notifications.dispatcher"):
                await dispatch("org:p", "user:p", "actionable", "milestone_completed", "Done")

    finally:
        dispatcher_mod.RETRY_MAX_ATTEMPTS = original_max
        dispatcher_mod.RETRY_BASE_DELAY = original_base

    combined = " ".join(r.message for r in caplog.records if r.levelno >= logging.ERROR)
    assert "permanently failed" in combined


def test_backoff_delay_grows_exponentially():
    """_backoff_delay returns exponentially growing values capped at RETRY_MAX_DELAY."""
    import core.engine.notifications.dispatcher as dispatcher_mod
    from core.engine.notifications.dispatcher import _backoff_delay

    original_base = dispatcher_mod.RETRY_BASE_DELAY
    original_max = dispatcher_mod.RETRY_MAX_DELAY
    try:
        dispatcher_mod.RETRY_BASE_DELAY = 1.0
        dispatcher_mod.RETRY_MAX_DELAY = 10.0

        assert _backoff_delay(0) == 1.0
        assert _backoff_delay(1) == 2.0
        assert _backoff_delay(2) == 4.0
        assert _backoff_delay(3) == 8.0
        assert _backoff_delay(4) == 10.0  # capped
        assert _backoff_delay(10) == 10.0  # still capped
    finally:
        dispatcher_mod.RETRY_BASE_DELAY = original_base
        dispatcher_mod.RETRY_MAX_DELAY = original_max


def test_retry_config_defaults():
    """Retry config constants are present and sensible."""
    import core.engine.notifications.dispatcher as dispatcher_mod

    assert dispatcher_mod.RETRY_MAX_ATTEMPTS >= 1
    assert dispatcher_mod.RETRY_BASE_DELAY > 0
    assert dispatcher_mod.RETRY_MAX_DELAY >= dispatcher_mod.RETRY_BASE_DELAY


@pytest.mark.asyncio
async def test_pref_failure_does_not_prevent_dispatch():
    """A failure loading user prefs still allows notification to be dispatched."""
    from core.engine.notifications.dispatcher import dispatch

    call_count = 0

    async def pref_fails_create_succeeds(query_str, params=None):
        nonlocal call_count
        if "notification_pref" in query_str:
            raise RuntimeError("pref DB unavailable")
        call_count += 1
        return [[{"id": "notification:ok", "tier": "actionable", "category": "idea_ready"}]]

    with patch("core.engine.notifications.dispatcher.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = pref_fails_create_succeeds
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dispatch("product:test", "user:test", "actionable", "idea_ready", "Great idea")

    assert result["tier"] == "actionable"
    assert "_dispatch_failed" not in result
    assert call_count == 1


# ---------------------------------------------------------------------------
# External channel routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_routes_to_external_channels():
    """After DB write, dispatch calls send() on each non-in_app channel."""
    from unittest.mock import MagicMock

    from core.engine.notifications.dispatcher import dispatch

    # Build a mock channel that tracks calls
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock(return_value=True)

    mock_registry = MagicMock()
    mock_registry.get = MagicMock(return_value=mock_channel)

    notification_record = {
        "id": "notification:ext1",
        "tier": "informational",
        "category": "synapse_proposal",
    }

    with (
        patch("core.engine.notifications.dispatcher.pool") as mock_pool,
        patch("core.engine.notifications.dispatcher.channel_registry", mock_registry),
        patch(
            "core.engine.notifications.dispatcher.DEFAULT_CHANNELS",
            {"informational": ["in_app", "discord"]},
        ),
    ):
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[notification_record]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await dispatch(
            product_id="product:test",
            user_id="user:test",
            tier="informational",
            category="synapse_proposal",
            title="New synapse",
        )

    # DB dispatch succeeded
    assert result["id"] == "notification:ext1"
    # Registry was queried for the discord channel (not in_app)
    mock_registry.get.assert_called_once_with("discord")
    # send() was called once with the notification record
    mock_channel.send.assert_awaited_once_with(notification_record)


@pytest.mark.asyncio
async def test_dispatch_channel_failure_does_not_propagate():
    """A channel send() failure is caught and logged; dispatch still returns success."""
    from unittest.mock import MagicMock

    from core.engine.notifications.dispatcher import dispatch

    # Channel that always raises
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock(side_effect=RuntimeError("discord down"))

    mock_registry = MagicMock()
    mock_registry.get = MagicMock(return_value=mock_channel)

    notification_record = {
        "id": "notification:ext2",
        "tier": "actionable",
        "category": "milestone_completed",
    }

    with (
        patch("core.engine.notifications.dispatcher.pool") as mock_pool,
        patch("core.engine.notifications.dispatcher.channel_registry", mock_registry),
        patch(
            "core.engine.notifications.dispatcher.DEFAULT_CHANNELS",
            {"actionable": ["in_app", "discord"]},
        ),
    ):
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[notification_record]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # Must not raise even though channel.send() raises
        result = await dispatch(
            product_id="product:test",
            user_id="user:test",
            tier="actionable",
            category="milestone_completed",
            title="Sprint done",
        )

    # Dispatch still returns the notification record
    assert result["id"] == "notification:ext2"
    assert "_dispatch_failed" not in result
    # send() was attempted
    mock_channel.send.assert_awaited_once()
