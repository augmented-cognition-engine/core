"""In-app notification channel adapter.

The `in_app` channel is a no-op at delivery time because the notification
record is written to the database by the dispatcher before any channel is
invoked.  This adapter exists so the channel system can treat in-app
delivery uniformly with external channels (email, Discord, webhook, etc.).
"""

from __future__ import annotations

from typing import Any

from core.engine.notifications.audit_buffer import record
from core.engine.voice.audit import audit_or_warn


class InAppChannel:
    """Channel adapter for in-app notifications.

    Delivery is a no-op — the notification record is already persisted to
    the database by the dispatcher, so the end client polls or subscribes
    to that record directly.
    """

    name: str = "in_app"

    async def send(self, notification: dict[str, Any]) -> bool:
        """No-op send — the DB record is the delivery mechanism.

        Always returns True.
        """
        message_text = notification.get("body") or notification.get("description", "")
        product_id = notification.get("product_id", "product:platform")
        if message_text:
            audit_or_warn(message_text, label="in_app")
            record("in_app", product_id, message_text)
        return True

    async def health_check(self) -> bool:
        """Always healthy — no external dependency."""
        return True
