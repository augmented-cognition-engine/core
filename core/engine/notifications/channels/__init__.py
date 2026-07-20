"""Notification channels — pluggable delivery adapters.

Each channel implements the `Channel` protocol. The module-level
`channel_registry` singleton is the authoritative registry for all
channels active in the current process.

Usage::

    from core.engine.notifications.channels import channel_registry
    channel_registry.register(InAppChannel())
    ch = channel_registry.get("in_app")
    ok = await ch.send(notification_dict)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Channel(Protocol):
    """Protocol every notification channel must satisfy."""

    name: str

    async def send(self, notification: dict[str, Any]) -> bool:
        """Deliver *notification* via this channel.

        Returns True on success, False on a soft failure (the caller
        decides whether to retry or fall back to another channel).
        """
        ...

    async def health_check(self) -> bool:
        """Return True when the channel is reachable and ready."""
        ...


class ChannelRegistry:
    """Registry of named notification channels.

    Channels are keyed by ``channel.name``.  Registering a channel whose
    name already exists silently replaces the previous entry.
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register *channel*, replacing any existing channel with the same name."""
        self._channels[channel.name] = channel

    def get(self, name: str) -> Channel | None:
        """Return the channel registered under *name*, or None."""
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        """Return the names of all registered channels."""
        return list(self._channels.keys())


# ---------------------------------------------------------------------------
# Module-level singleton — import and use this everywhere.
# ---------------------------------------------------------------------------
channel_registry = ChannelRegistry()
