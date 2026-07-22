from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_captured_observation_load_preserves_durable_identity_and_provenance():
    from core.engine.api import intel

    db = AsyncMock()
    db.query = AsyncMock(
        return_value=[
            {
                "id": "observation:durable-guidance",
                "content": "Preserve the eleven-tool boundary.",
                "observation_type": "correction",
                "confidence": 1.0,
                "source": "api",
                "created_at": "2026-07-19T17:00:00Z",
            }
        ]
    )

    class FakePool:
        @asynccontextmanager
        async def connection(self):
            yield db

    with patch.object(intel, "pool", new=FakePool()):
        rows = await intel._load_captured_observations("architecture", "product:test")

    assert len(rows) == 1
    expected = {
        "id": "observation:durable-guidance",
        "content": "Preserve the eleven-tool boundary.",
        "insight_type": "correction",
        "confidence": 1.0,
        "created_at": "2026-07-19T17:00:00Z",
        "source": "api",
    }
    assert {key: rows[0][key] for key in expected} == expected
    assert rows[0]["contract_version"] == "correction-v1"
    assert rows[0]["correction_id"] == "observation:durable-guidance"
    assert rows[0]["provenance"]["completeness"] == "degraded"
    query = db.query.await_args.args[0]
    assert "SELECT id, content" in query
