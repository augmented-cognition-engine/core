from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from core.engine.api import landscape
from core.engine.core.auth import create_access_token
from core.engine.product.living_graph import PROJECTION_VERSION


@pytest.fixture(autouse=True)
def _strong_test_jwt_secret(monkeypatch):
    monkeypatch.setattr(
        "core.engine.core.auth.settings.jwt_secret",
        "g1-landscape-test-secret-at-least-32-bytes",
    )


class _ReadOnlyDatabase:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def query(self, query: str, params: dict):
        self.calls.append((query, params))
        if "FROM ONLY" in query:
            return {"id": "product:alpha", "name": "Alpha"}
        return []


class _ReadOnlyPool:
    def __init__(self, database: _ReadOnlyDatabase):
        self.database = database

    @asynccontextmanager
    async def connection(self):
        yield self.database


class _UnavailablePool:
    @asynccontextmanager
    async def connection(self):
        raise RuntimeError("private database detail must not leak")
        yield


def _headers(product: str = "product:alpha") -> dict[str, str]:
    token = create_access_token({"sub": "user:owner", "product": product})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_landscape_requires_auth_and_rejects_mutating_method():
    from core.engine.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/product/landscape")).status_code == 401
        assert (await client.post("/product/landscape", headers=_headers())).status_code == 405


@pytest.mark.asyncio
async def test_authenticated_scope_cannot_be_overridden_by_crafted_query_parameters():
    from core.engine.api.main import app

    database = _ReadOnlyDatabase()
    with patch.object(landscape, "pool", new=_ReadOnlyPool(database)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/product/landscape",
                params={"product": "product:beta", "filter": '{"method":"POST"}'},
                headers=_headers("product:alpha"),
            )

    assert response.status_code == 200
    assert response.json()["product"]["id"] == "product:alpha"
    assert all(query.lstrip().upper().startswith("SELECT") for query, _params in database.calls)
    assert all(params.get("product", "product:alpha") == "product:alpha" for _query, params in database.calls)


@pytest.mark.asyncio
async def test_unsupported_projection_version_has_deterministic_recovery():
    with pytest.raises(HTTPException) as exc:
        await landscape.get_product_landscape(
            projection_version="ace.living-product-projection.g1.v999",
            user={"product": "product:alpha"},
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "code": "unsupported_projection_version",
        "message": "The requested Living Product Graph projection version is not supported.",
        "recovery": f"Retry with projection_version={PROJECTION_VERSION}.",
        "requested": "ace.living-product-projection.g1.v999",
        "supported": [PROJECTION_VERSION],
    }


@pytest.mark.asyncio
async def test_malformed_authenticated_product_identity_fails_before_database_access():
    with pytest.raises(HTTPException) as exc:
        await landscape.get_product_landscape(
            projection_version=PROJECTION_VERSION,
            user={"product": "product:../beta"},
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "malformed_product_identity"


@pytest.mark.asyncio
async def test_database_unavailability_is_a_safe_deterministic_snapshot_without_raw_exception():
    with patch.object(landscape, "pool", new=_UnavailablePool()):
        snapshot = await landscape.get_product_landscape(
            projection_version=PROJECTION_VERSION,
            user={"product": "product:alpha"},
        )

    assert snapshot["projection_state"]["status"] == "unknown"
    assert {state["status"] for state in snapshot["source_states"]} == {"unavailable"}
    assert "private database detail" not in str(snapshot)


@pytest.mark.asyncio
async def test_unexpected_projection_failure_is_sanitized():
    with patch.object(
        landscape.LivingProductGraphService,
        "snapshot",
        side_effect=RuntimeError("private failure detail"),
    ):
        with pytest.raises(HTTPException) as exc:
            await landscape.get_product_landscape(
                projection_version=PROJECTION_VERSION,
                user={"product": "product:alpha"},
            )

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "landscape_temporarily_unavailable"
    assert "private failure detail" not in str(exc.value.detail)
