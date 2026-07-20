"""Webhook notification channel adapter.

Delivers notifications via HTTP POST with HMAC-SHA256 request signing.
Each `send()` call opens a fresh `aiohttp.ClientSession` (stateless).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class WebhookChannel:
    """Channel adapter that delivers notifications to an HTTP endpoint.

    The payload is serialized as JSON and signed with an HMAC-SHA256
    signature that is included in the ``X-ACE-Signature`` request header.
    """

    name: str = "webhook"

    def __init__(self, url: str, secret: str) -> None:
        self._url = url
        self._secret = secret

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sign(self, body: bytes) -> str:
        """Return ``sha256=<hex>`` HMAC-SHA256 signature for *body*."""
        digest = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    # ------------------------------------------------------------------
    # Channel protocol
    # ------------------------------------------------------------------

    async def send(self, notification: dict[str, Any]) -> bool:
        """POST *notification* as JSON to the configured URL.

        Signs the payload with HMAC-SHA256 and attaches the signature as
        the ``X-ACE-Signature`` header.

        Returns True when the server responds with HTTP < 300, False on
        any error (non-2xx status or network/timeout exception).
        """
        try:
            body = json.dumps(notification, default=str, sort_keys=True).encode()
            signature = self._sign(body)
            headers = {
                "Content-Type": "application/json",
                "X-ACE-Signature": signature,
            }
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    self._url,
                    data=body,
                    headers=headers,
                )
                if response.status < 300:
                    return True
                logger.warning(
                    "webhook delivery failed: url=%s status=%s",
                    self._url,
                    response.status,
                )
                return False
        except Exception:
            logger.exception("webhook delivery raised an exception: url=%s", self._url)
            return False

    async def health_check(self) -> bool:
        """Return True — webhook channel has no persistent external state."""
        return True
