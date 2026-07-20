# tests/test_channel_discord.py
"""Tests for Discord DM notification channel adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Tier color mapping
# ---------------------------------------------------------------------------


def test_tier_to_color_mapping():
    """All four tiers have distinct hex color values."""
    from core.engine.notifications.channels.discord import TIER_COLORS

    assert len(TIER_COLORS) == 4
    expected_keys = {"critical", "actionable", "informational", "silent"}
    assert set(TIER_COLORS.keys()) == expected_keys
    # All colors are distinct integers
    color_values = list(TIER_COLORS.values())
    assert len(set(color_values)) == 4, "Each tier should have a unique color"
    # Spot-check specific values
    assert TIER_COLORS["critical"] == 0xDC3545
    assert TIER_COLORS["actionable"] == 0xFD7E14
    assert TIER_COLORS["informational"] == 0x0D6EFD
    assert TIER_COLORS["silent"] == 0x6C757D


# ---------------------------------------------------------------------------
# Category button mapping
# ---------------------------------------------------------------------------


def test_category_to_buttons_mapping():
    """All expected notification categories have button configs."""
    from core.engine.notifications.channels.discord import CATEGORY_BUTTONS

    expected_categories = {
        "gap_detected",
        "conflict_detected",
        "idea_ready",
        "briefing",
        "spec_verified",
    }
    assert expected_categories.issubset(set(CATEGORY_BUTTONS.keys()))

    # Each entry is a non-empty list of tuples
    for category, buttons in CATEGORY_BUTTONS.items():
        assert isinstance(buttons, list), f"{category} buttons should be a list"
        assert len(buttons) > 0, f"{category} should have at least one button"
        for btn in buttons:
            assert len(btn) == 3, "Button tuple should have 3 elements: (label, action_id, style)"


# ---------------------------------------------------------------------------
# DiscordChannel.health_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_health_check():
    """health_check() reflects the _connected state."""
    with patch("core.engine.notifications.channels.discord.discord") as mock_discord:
        from core.engine.notifications.channels.discord import DiscordChannel

        channel = DiscordChannel(user_id=123456789)

        # Starts disconnected
        assert await channel.health_check() is False

        # Simulate connected state
        channel._connected = True
        assert await channel.health_check() is True

        channel._connected = False
        assert await channel.health_check() is False


# ---------------------------------------------------------------------------
# DiscordChannel.send — disconnected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_channel_send_when_disconnected():
    """send() returns False immediately when the bot is not connected."""
    with patch("core.engine.notifications.channels.discord.discord") as mock_discord:
        from core.engine.notifications.channels.discord import DiscordChannel

        channel = DiscordChannel(user_id=123456789)
        # _connected defaults to False — no bot started

        notification = {
            "id": "notification:n1",
            "tier": "critical",
            "category": "conflict_detected",
            "title": "Conflict detected",
            "body": "Two initiatives are overlapping.",
        }

        result = await channel.send(notification)
        assert result is False


# ---------------------------------------------------------------------------
# DiscordChannel.send — connected, formats embed and calls user.send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discord_channel_send_formats_embed():
    """send() fetches the user, builds an embed+view, and calls user.send()."""
    with patch("core.engine.notifications.channels.discord.discord") as mock_discord:
        # Set up mock discord objects
        mock_embed = MagicMock()
        mock_discord.Embed.return_value = mock_embed

        mock_view = MagicMock()
        mock_discord.ui = MagicMock()
        mock_discord.ui.View.return_value = mock_view

        # Mock button style attributes
        mock_discord.ButtonStyle = MagicMock()
        mock_discord.ButtonStyle.primary = 1
        mock_discord.ButtonStyle.secondary = 2

        mock_user = AsyncMock()
        mock_user.send = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.fetch_user = AsyncMock(return_value=mock_user)

        from core.engine.notifications.channels.discord import DiscordChannel

        channel = DiscordChannel(user_id=987654321)
        channel._bot = mock_bot
        channel._connected = True

        notification = {
            "id": "notification:n2",
            "tier": "actionable",
            "category": "gap_detected",
            "title": "Gap detected",
            "body": "Security discipline has unresolved gaps.",
            "source_record": "gap:001",
        }

        result = await channel.send(notification)

        # user.send must have been called
        mock_bot.fetch_user.assert_awaited_once_with(987654321)
        mock_user.send.assert_awaited_once()
        assert result is True
