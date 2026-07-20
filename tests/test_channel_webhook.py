# tests/test_channel_webhook.py
"""Tests for the webhook notification channel adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel(url: str = "https://example.com/hook", secret: str = "s3cr3t"):
    from core.engine.notifications.channels.webhook import WebhookChannel

    return WebhookChannel(url=url, secret=secret)


def _compute_expected_sig(payload: dict, secret: str) -> str:
    body = json.dumps(payload, default=str, sort_keys=True).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# Task 5: WebhookChannel adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_send_posts_json():
    """send() performs an HTTP POST to the configured URL."""
    url = "https://example.com/hook"
    notification = {"title": "Test", "tier": "informational"}
    channel = _make_channel(url=url)

    mock_response = MagicMock()
    mock_response.status = 200

    mock_post = AsyncMock(return_value=mock_response)
    mock_session = MagicMock()
    mock_session.post = mock_post
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_cls = MagicMock(return_value=mock_session)

    with patch("aiohttp.ClientSession", mock_session_cls):
        result = await channel.send(notification)

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == url or call_kwargs[1].get("url") == url or mock_post.call_args.args[0] == url


@pytest.mark.asyncio
async def test_webhook_includes_hmac_signature():
    """send() adds X-ACE-Signature header with correct HMAC-SHA256 value."""
    url = "https://example.com/hook"
    secret = "my-webhook-secret"
    notification = {"title": "Alert", "tier": "critical"}
    channel = _make_channel(url=url, secret=secret)

    expected_sig = _compute_expected_sig(notification, secret)

    mock_response = MagicMock()
    mock_response.status = 200

    mock_post = AsyncMock(return_value=mock_response)
    mock_session = MagicMock()
    mock_session.post = mock_post
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_cls = MagicMock(return_value=mock_session)

    with patch("aiohttp.ClientSession", mock_session_cls):
        result = await channel.send(notification)

    assert result is True
    _, call_kwargs = mock_post.call_args
    headers = call_kwargs.get("headers", {})
    assert "X-ACE-Signature" in headers
    assert headers["X-ACE-Signature"] == expected_sig


@pytest.mark.asyncio
async def test_webhook_health_check():
    """health_check() always returns True (stateless channel)."""
    channel = _make_channel()
    result = await channel.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_webhook_returns_false_on_error_status():
    """send() returns False when the HTTP response status is >= 300."""
    notification = {"title": "Test", "tier": "informational"}
    channel = _make_channel()

    mock_response = MagicMock()
    mock_response.status = 500

    mock_post = AsyncMock(return_value=mock_response)
    mock_session = MagicMock()
    mock_session.post = mock_post
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", MagicMock(return_value=mock_session)):
        result = await channel.send(notification)

    assert result is False


@pytest.mark.asyncio
async def test_webhook_returns_false_on_exception():
    """send() catches exceptions and returns False rather than raising."""
    notification = {"title": "Test", "tier": "informational"}
    channel = _make_channel()

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", MagicMock(return_value=mock_session)):
        result = await channel.send(notification)

    assert result is False


def test_webhook_channel_name():
    """WebhookChannel.name is 'webhook'."""
    from core.engine.notifications.channels.webhook import WebhookChannel

    assert WebhookChannel.name == "webhook"
