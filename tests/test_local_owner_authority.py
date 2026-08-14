"""Single-user local-owner authority bootstrap tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ace.core.contracts import canonical_hash
from ace.core.state import GovernedStateHeadV1
from core.engine.api.auth_routes import local_owner_authority_store
from core.engine.api.main import app
from core.engine.core.agent_composition_runtime import CompositionAuthorityGrantMaterial
from core.engine.core.auth import get_current_user
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_ACTOR_REF,
    LOCAL_OWNER_GRANTS,
    LOCAL_OWNER_PRODUCT_ID,
    LocalOwnerAuthorityConflict,
    LocalOwnerAuthorityDenied,
    bootstrap_local_owner_authority,
)

NOW = datetime(2026, 8, 13, 20, 0, tzinfo=UTC)
AUTHORITIES = [
    "administer_lifecycle",
    "cognition-review",
    "deliver_export",
    "intelligence_build",
    "observe_read",
]


class InMemoryGovernedStateStore:
    def __init__(self) -> None:
        self.heads: dict[tuple[str, str, str], GovernedStateHeadV1] = {}
        self.revisions: dict[tuple[str, str], object] = {}
        self.receipts: dict[tuple[str, str], object] = {}

    async def commit(self, request):
        revision = request.revision
        receipt = request.receipt()
        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        key = (revision.state_kind, revision.product_id, revision.state_id)
        if key in self.heads:
            raise AssertionError("test store refuses overwrite")
        self.heads[key] = head
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, str(receipt.receipt_id))] = receipt
        return receipt

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id: str, *, product_id: str):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id: str, *, product_id: str):
        return self.receipts.get((product_id, receipt_id))


class JsonRoundTripGovernedStateStore(InMemoryGovernedStateStore):
    """Mirror the JSON-shaped values returned by the durable SurrealDB adapter."""

    async def commit(self, request):
        receipt = await super().commit(request)
        self.heads = {
            key: type(value).model_validate_json(value.model_dump_json()) for key, value in self.heads.items()
        }
        self.revisions = {
            key: type(value).model_validate_json(value.model_dump_json()) for key, value in self.revisions.items()
        }
        self.receipts = {
            key: type(value).model_validate_json(value.model_dump_json()) for key, value in self.receipts.items()
        }
        return receipt


def _owner() -> dict:
    return {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": AUTHORITIES,
        "local_owner": True,
    }


@pytest.mark.asyncio
async def test_bootstrap_creates_then_verifies_four_fixed_product_scoped_grants():
    store = InMemoryGovernedStateStore()

    created = await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)
    verified = await bootstrap_local_owner_authority(
        user=_owner(),
        store=store,
        approved_at=NOW + timedelta(hours=1),
    )

    assert [item.status for item in created.grants] == ["created"] * 4
    assert [item.status for item in verified.grants] == ["verified"] * 4
    assert len(store.heads) == 4
    for spec in LOCAL_OWNER_GRANTS:
        head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, spec.grant_ref)]
        revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)]
        grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
        receipt = store.receipts[(LOCAL_OWNER_PRODUCT_ID, head.commit_receipt_id)]
        assert grant.actor_ref == LOCAL_OWNER_ACTOR_REF
        assert grant.product_id == LOCAL_OWNER_PRODUCT_ID
        assert grant.scope_ref == LOCAL_OWNER_PRODUCT_ID
        assert grant.authority_class == spec.authority_class
        assert grant.operations == tuple(sorted(spec.operations))
        assert grant.lifecycle == "active"
        assert grant.expires_at is None
        assert receipt.authority_grants[0].grant_ref == spec.grant_ref
        assert receipt.authority_grants[0].grant_hash == grant.grant_hash


@pytest.mark.asyncio
async def test_bootstrap_verifies_grants_after_durable_json_round_trip():
    store = JsonRoundTripGovernedStateStore()

    created = await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)
    verified = await bootstrap_local_owner_authority(
        user=_owner(),
        store=store,
        approved_at=NOW + timedelta(hours=1),
    )

    assert [item.status for item in created.grants] == ["created"] * 4
    assert [item.status for item in verified.grants] == ["verified"] * 4
    assert len(store.heads) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [
        {
            "sub": LOCAL_OWNER_ACTOR_REF,
            "product": LOCAL_OWNER_PRODUCT_ID,
            "authorities": [],
            "local_owner": False,
        },
        {**_owner(), "authorities": [*AUTHORITIES, "execute_external"]},
        {**_owner(), "product": "product:other"},
    ],
)
async def test_bootstrap_requires_the_exact_signed_local_owner(claims):
    with pytest.raises(LocalOwnerAuthorityDenied):
        await bootstrap_local_owner_authority(user=claims, store=InMemoryGovernedStateStore(), approved_at=NOW)


@pytest.mark.asyncio
async def test_bootstrap_never_overwrites_a_changed_or_revoked_grant():
    store = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)
    spec = LOCAL_OWNER_GRANTS[-1]
    head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, spec.grant_ref)]
    revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)]
    grant = CompositionAuthorityGrantMaterial.model_validate(revision.payload)
    changed = grant.model_copy(update={"lifecycle": "revoked", "revoked_at": NOW + timedelta(minutes=1)})
    changed_payload = changed.model_dump(mode="python")
    changed_revision = revision.model_copy(
        update={
            "payload": changed_payload,
            "material_hash": canonical_hash(changed.model_dump(mode="json")),
        }
    )
    store.revisions[(LOCAL_OWNER_PRODUCT_ID, head.revision_id)] = changed_revision

    with pytest.raises(LocalOwnerAuthorityConflict):
        await bootstrap_local_owner_authority(
            user=_owner(),
            store=store,
            approved_at=NOW + timedelta(hours=1),
        )

    assert store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, spec.grant_ref)] == head


def test_http_bootstrap_uses_only_the_verified_local_owner_and_is_idempotent():
    store = InMemoryGovernedStateStore()
    app.dependency_overrides[get_current_user] = _owner
    app.dependency_overrides[local_owner_authority_store] = lambda: store
    try:
        client = TestClient(app)
        created = client.post("/auth/local-owner/bootstrap", headers={"Authorization": "Bearer test"})
        verified = client.post("/auth/local-owner/bootstrap", headers={"Authorization": "Bearer test"})
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 200
    assert [item["status"] for item in created.json()["grants"]] == ["created"] * 4
    assert verified.status_code == 200
    assert [item["status"] for item in verified.json()["grants"]] == ["verified"] * 4


def test_http_bootstrap_rejects_demo_claims_without_creating_grants():
    store = InMemoryGovernedStateStore()
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": LOCAL_OWNER_ACTOR_REF,
        "product": LOCAL_OWNER_PRODUCT_ID,
        "authorities": [],
        "local_owner": False,
    }
    app.dependency_overrides[local_owner_authority_store] = lambda: store
    try:
        response = TestClient(app).post(
            "/auth/local-owner/bootstrap",
            headers={"Authorization": "Bearer test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert store.heads == {}
