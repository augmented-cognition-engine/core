from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application import PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE
from ace.core import (
    AppendOnlyTransactionRequestV1,
    ImmutableRecordV1,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.personal_intelligence_ownership import router
from core.engine.core.agent_composition_runtime import GovernedCompositionAuthorityError
from core.engine.core.auth import get_current_user
from core.engine.core.personal_intelligence_ownership import (
    CONFIRM_DELETE_OPERATION,
    EXPORT_OPERATION,
    OWNERSHIP_AUTHENTICATION_RECORD_KIND,
    PREVIEW_DELETE_OPERATION,
    PersonalOwnershipHttpRuntime,
    personal_ownership_runtime,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:personal-http"
ACTOR = "actor:personal-owner"
EXPORT_GRANT = "authority_grant:personal-export"
DELETE_GRANT = "authority_grant:personal-delete"
NOW = datetime.now(UTC)


class _Authority:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.calls: list[dict] = []

    async def resolve_authority_use(self, **kwargs):
        self.calls.append(kwargs)
        if self.deny:
            raise GovernedCompositionAuthorityError("inactive grant")
        return object()


def _claims(*, authorities: list[str], include_product: bool = True) -> dict:
    claims = {
        "sub": ACTOR,
        "authorities": authorities,
        "exp": (NOW + timedelta(hours=1)).timestamp(),
    }
    if include_product:
        claims["product"] = PRODUCT
    return claims


def _record(key: str, secret: str) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="live",
        record_kind="brief",
        record_key=key,
        payload_contract="example.brief/v1",
        payload={"secret": secret},
        as_of=NOW - timedelta(minutes=2),
        available_at=NOW - timedelta(minutes=1),
        processing_order=0,
    )


async def _seed(store: InMemoryImmutableRecordStore, record: ImmutableRecordV1, key: str) -> None:
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=PRODUCT,
            record_space=record.record_space,
            transaction_key=key,
            records=(record,),
            submitted_at=NOW,
        )
    )


def _app(*, claims: dict, store: InMemoryImmutableRecordStore, authority: _Authority) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[personal_ownership_runtime] = lambda: PersonalOwnershipHttpRuntime(
        records=store,
        authority=authority,
    )
    return app


@pytest.mark.asyncio
async def test_export_is_authenticated_authorized_and_excludes_control_evidence() -> None:
    store = InMemoryImmutableRecordStore()
    content = _record("brief:1", "private-intelligence")
    await _seed(store, content, "seed")
    authority = _Authority()
    app = _app(
        claims=_claims(authorities=["deliver_export"]),
        store=store,
        authority=authority,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/ownership/export",
            json={"authority_grant_ref": EXPORT_GRANT},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["record_count"] == 1
    assert body["records"][0]["storage_id"] == content.storage_id
    assert body["runnable_restore_supported"] is False
    assert authority.calls[0]["authority"] == "deliver_export"
    assert authority.calls[0]["operation"] == EXPORT_OPERATION
    stored = await store.scan_product_records(product_id=PRODUCT)
    control = [item for item in stored if item.record_space == PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE]
    assert len(control) == 1
    assert control[0].record_kind == OWNERSHIP_AUTHENTICATION_RECORD_KIND
    assert all(item["record_space"] != PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE for item in body["records"])


@pytest.mark.asyncio
async def test_preview_then_confirmation_deletes_exact_content_with_fresh_authentication() -> None:
    store = InMemoryImmutableRecordStore()
    content = _record("brief:1", "delete-me")
    await _seed(store, content, "seed")
    authority = _Authority()
    app = _app(
        claims=_claims(authorities=["administer_lifecycle"]),
        store=store,
        authority=authority,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_response = await client.post(
            "/v1/intelligence/ownership/deletion/preview",
            json={
                "authority_grant_ref": DELETE_GRANT,
                "confirmation_window_seconds": 900,
            },
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        confirm_response = await client.post(
            "/v1/intelligence/ownership/deletion/confirm",
            json={
                "authority_grant_ref": DELETE_GRANT,
                "preview": preview,
                "confirmation_digest": preview["confirmation_digest"],
            },
        )

    assert confirm_response.status_code == 200, confirm_response.text
    result = confirm_response.json()
    assert result["proof"]["removed_count"] == 1
    assert result["proof"]["primary_store_non_reappearance_verified"] is True
    assert result["proof"]["backup_non_reappearance_proven"] is False
    assert [call["operation"] for call in authority.calls] == [
        PREVIEW_DELETE_OPERATION,
        CONFIRM_DELETE_OPERATION,
    ]
    remaining = await store.scan_product_records(product_id=PRODUCT)
    assert all(item.record_space == PERSONAL_INTELLIGENCE_OWNERSHIP_RECORD_SPACE for item in remaining)
    assert all("delete-me" not in str(item.payload) for item in remaining)


@pytest.mark.asyncio
async def test_missing_token_authority_and_current_grant_denial_fail_closed() -> None:
    missing_store = InMemoryImmutableRecordStore()
    missing_app = _app(claims=_claims(authorities=[]), store=missing_store, authority=_Authority())
    async with AsyncClient(transport=ASGITransport(app=missing_app), base_url="http://test") as client:
        missing = await client.post(
            "/v1/intelligence/ownership/export",
            json={"authority_grant_ref": EXPORT_GRANT},
        )
    assert missing.status_code == 403
    assert missing_store.records == {}

    denied_store = InMemoryImmutableRecordStore()
    await _seed(denied_store, _record("brief:1", "preserved"), "seed-denied")
    denied_app = _app(
        claims=_claims(authorities=["deliver_export"]),
        store=denied_store,
        authority=_Authority(deny=True),
    )
    async with AsyncClient(transport=ASGITransport(app=denied_app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/intelligence/ownership/export",
            json={"authority_grant_ref": EXPORT_GRANT},
        )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_expired_authentication_and_authentication_storage_outage_fail_closed() -> None:
    expired_claims = _claims(authorities=["deliver_export"])
    expired_claims["exp"] = (NOW - timedelta(seconds=1)).timestamp()
    expired_store = InMemoryImmutableRecordStore()
    expired_app = _app(claims=expired_claims, store=expired_store, authority=_Authority())
    async with AsyncClient(transport=ASGITransport(app=expired_app), base_url="http://test") as client:
        expired = await client.post(
            "/v1/intelligence/ownership/export",
            json={"authority_grant_ref": EXPORT_GRANT},
        )
    assert expired.status_code == 401
    assert expired_store.records == {}

    unavailable_store = InMemoryImmutableRecordStore(fail_after_records=1)
    unavailable_app = _app(
        claims=_claims(authorities=["deliver_export"]),
        store=unavailable_store,
        authority=_Authority(),
    )
    async with AsyncClient(transport=ASGITransport(app=unavailable_app), base_url="http://test") as client:
        unavailable = await client.post(
            "/v1/intelligence/ownership/export",
            json={"authority_grant_ref": EXPORT_GRANT},
        )
    assert unavailable.status_code == 503
    assert unavailable_store.records == {}


@pytest.mark.asyncio
async def test_missing_product_scope_is_unauthenticated_and_stale_preview_conflicts() -> None:
    missing_product_store = InMemoryImmutableRecordStore()
    missing_product_app = _app(
        claims=_claims(authorities=["deliver_export"], include_product=False),
        store=missing_product_store,
        authority=_Authority(),
    )
    async with AsyncClient(transport=ASGITransport(app=missing_product_app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/ownership/export",
            json={"authority_grant_ref": EXPORT_GRANT},
        )
    assert response.status_code == 401

    store = InMemoryImmutableRecordStore()
    original = _record("brief:1", "preserved")
    await _seed(store, original, "seed")
    app = _app(
        claims=_claims(authorities=["administer_lifecycle"]),
        store=store,
        authority=_Authority(),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview_response = await client.post(
            "/v1/intelligence/ownership/deletion/preview",
            json={"authority_grant_ref": DELETE_GRANT},
        )
        preview = preview_response.json()
        later = _record("brief:2", "later")
        await _seed(store, later, "later")
        stale = await client.post(
            "/v1/intelligence/ownership/deletion/confirm",
            json={
                "authority_grant_ref": DELETE_GRANT,
                "preview": preview,
                "confirmation_digest": preview["confirmation_digest"],
            },
        )
    assert stale.status_code == 409, stale.text
    records = await store.scan_product_records(product_id=PRODUCT)
    assert {original.storage_id, later.storage_id}.issubset({item.storage_id for item in records})


def test_openapi_exposes_only_explicit_post_operations() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert set(paths) == {
        "/v1/intelligence/ownership/export",
        "/v1/intelligence/ownership/deletion/preview",
        "/v1/intelligence/ownership/deletion/confirm",
    }
    assert all(set(operations) == {"post"} for operations in paths.values())
