"""Tests for webhook ingestion endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db(monkeypatch):
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    from core.engine.core import db as db_module

    monkeypatch.setattr(db_module, "pool", mock_pool)
    return mock_conn


def test_webhook_payload_validation():
    from core.engine.api.webhooks import WebhookPayload

    # Valid
    p = WebhookPayload(source="zendesk", content="Customer reports issue with billing")
    assert p.source == "zendesk"
    assert p.source_id is None

    # With all fields
    p2 = WebhookPayload(
        source="slack",
        source_id="msg-123",
        content="Discussion about architecture",
        metadata={"channel": "#engineering"},
        domain_hint="architecture",
    )
    assert p2.source_id == "msg-123"
    assert p2.metadata["channel"] == "#engineering"


def test_webhook_payload_max_length():
    from pydantic import ValidationError

    from core.engine.api.webhooks import WebhookPayload

    with pytest.raises(ValidationError):
        WebhookPayload(source="x" * 101, content="test")

    with pytest.raises(ValidationError):
        WebhookPayload(source="test", content="x" * 50_001)


def test_webhook_payload_requires_source_and_content():
    from pydantic import ValidationError

    from core.engine.api.webhooks import WebhookPayload

    with pytest.raises(ValidationError):
        WebhookPayload(source="test")  # missing content

    with pytest.raises(ValidationError):
        WebhookPayload(content="test")  # missing source
