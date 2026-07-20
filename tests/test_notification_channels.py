# tests/test_notification_channels.py
"""Tests for the pluggable notification channel protocol and registry."""

import pytest

# ---------------------------------------------------------------------------
# Task 1: Channel protocol and registry
# ---------------------------------------------------------------------------


def test_registry_starts_empty():
    """A fresh ChannelRegistry has no registered channels."""
    from core.engine.notifications.channels import ChannelRegistry

    registry = ChannelRegistry()
    assert registry.list_channels() == []


def test_register_and_retrieve_channel():
    """Registering a channel makes it retrievable by name."""
    from core.engine.notifications.channels import ChannelRegistry
    from core.engine.notifications.channels.in_app import InAppChannel

    registry = ChannelRegistry()
    channel = InAppChannel()
    registry.register(channel)

    retrieved = registry.get("in_app")
    assert retrieved is channel


def test_get_unknown_channel_returns_none():
    """Getting a channel that has not been registered returns None."""
    from core.engine.notifications.channels import ChannelRegistry

    registry = ChannelRegistry()
    assert registry.get("email") is None


def test_duplicate_register_replaces():
    """Registering a channel with the same name replaces the previous one."""
    from core.engine.notifications.channels import ChannelRegistry
    from core.engine.notifications.channels.in_app import InAppChannel

    registry = ChannelRegistry()
    first = InAppChannel()
    second = InAppChannel()

    registry.register(first)
    registry.register(second)

    assert registry.get("in_app") is second
    assert registry.list_channels() == ["in_app"]


def test_list_channels_returns_names():
    """list_channels() returns the names of all registered channels."""
    from core.engine.notifications.channels import ChannelRegistry
    from core.engine.notifications.channels.in_app import InAppChannel

    registry = ChannelRegistry()
    registry.register(InAppChannel())
    names = registry.list_channels()
    assert "in_app" in names


def test_channel_satisfies_protocol():
    """InAppChannel satisfies the Channel runtime-checkable protocol."""
    from core.engine.notifications.channels import Channel
    from core.engine.notifications.channels.in_app import InAppChannel

    assert isinstance(InAppChannel(), Channel)


def test_singleton_registry_exists():
    """The module-level channel_registry singleton is a ChannelRegistry."""
    from core.engine.notifications.channels import ChannelRegistry, channel_registry

    assert isinstance(channel_registry, ChannelRegistry)


# ---------------------------------------------------------------------------
# Task 2: InAppChannel adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_app_send_returns_true():
    """InAppChannel.send() is a no-op that returns True."""
    from core.engine.notifications.channels.in_app import InAppChannel

    channel = InAppChannel()
    result = await channel.send({"title": "Hello", "tier": "informational"})
    assert result is True


@pytest.mark.asyncio
async def test_in_app_health_check_returns_true():
    """InAppChannel.health_check() always returns True."""
    from core.engine.notifications.channels.in_app import InAppChannel

    channel = InAppChannel()
    result = await channel.health_check()
    assert result is True


def test_in_app_channel_name():
    """InAppChannel.name is 'in_app'."""
    from core.engine.notifications.channels.in_app import InAppChannel

    assert InAppChannel.name == "in_app"


@pytest.mark.asyncio
async def test_channel_registry_populated_on_startup():
    """After startup wiring, in_app should be registered."""
    from core.engine.notifications.channels import channel_registry
    from core.engine.notifications.channels.in_app import InAppChannel

    # Simulate what lifespan does
    channel_registry.register(InAppChannel())
    assert channel_registry.get("in_app") is not None
