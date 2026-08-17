from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _pool(query):
    db = AsyncMock()
    db.query = AsyncMock(side_effect=query)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=db)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, db


@pytest.mark.asyncio
async def test_persisted_orchestration_run_stores_product_explicitly():
    from core.engine.orchestration.executor import _persist_events

    calls = []

    async def query(sql, params=None):
        calls.append((sql, params))
        return [[]]

    fake_pool, _ = _pool(query)
    with patch("core.engine.core.db.pool", fake_pool):
        await _persist_events(
            "run:one",
            "product:alpha",
            [],
            {"discipline": "testing"},
            "independent",
            "completed",
            "direct",
            12,
            None,
            1,
        )

    sql, params = calls[0]
    assert "CREATE orchestration_run SET" in sql
    assert "product = <record>$product" in sql
    assert params["product"] == "product:alpha"


@pytest.mark.asyncio
async def test_get_run_fences_run_and_events_to_authenticated_product(monkeypatch):
    import core.engine.api.orchestration as api

    calls = []

    async def query(sql, params=None):
        calls.append((sql, params))
        if "FROM orchestration_run" in sql:
            return [[{"run_id": "shared", "product": "product:alpha"}]]
        return [[]]

    fake_pool, _ = _pool(query)
    monkeypatch.setattr(api, "pool", fake_pool)

    result = await api.get_run("shared", user={"product": "product:alpha"})

    assert result["run"]["product"] == "product:alpha"
    assert all("product = <record>$product" in sql for sql, _ in calls)
    assert all(params["product"] == "product:alpha" for _, params in calls)


@pytest.mark.asyncio
async def test_list_runs_rejects_explicit_cross_product_scope():
    import core.engine.api.orchestration as api

    with pytest.raises(HTTPException) as exc:
        await api.list_runs(product="product:beta", user={"product": "product:alpha"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_missing_product_claim_fails_closed_before_read(monkeypatch):
    import core.engine.api.orchestration as api

    fake_pool, db = _pool(AsyncMock(return_value=[[]]))
    monkeypatch.setattr(api, "pool", fake_pool)

    with pytest.raises(HTTPException) as exc:
        await api.get_run("legacy-productless", user={})
    assert exc.value.status_code == 404
    db.query.assert_not_awaited()
