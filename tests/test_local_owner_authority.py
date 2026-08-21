"""Single-user local-owner authority bootstrap tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ace.application.intelligence_resource_feedback import RESOURCE_FEEDBACK_OPERATION
from ace.core.agent_composition import AuthorityClass
from ace.core.contracts import canonical_hash
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    GovernedStateRevisionV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from core.engine.api.auth_routes import local_owner_authority_store
from core.engine.api.main import app
from core.engine.core.agent_composition_runtime import (
    GRANT_PAYLOAD_CONTRACT,
    CompositionAuthorityGrantMaterial,
)
from core.engine.core.auth import get_current_user
from core.engine.core.governed_state import GovernedStateHeadConflict
from core.engine.core.local_owner_authority import (
    LOCAL_OWNER_ACTOR_REF,
    LOCAL_OWNER_COGNITION,
    LOCAL_OWNER_GRANTS,
    LOCAL_OWNER_POLICY_REF,
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
    "derive_propose",
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
        key = (revision.state_kind, revision.product_id, revision.state_id)
        current_head = self.heads.get(key)
        current_revision_id = current_head.revision_id if current_head is not None else None
        if request.expected_head_revision_id != current_revision_id:
            raise GovernedStateHeadConflict("governed_state_head_conflict")
        revision_key = (revision.product_id, revision.revision_id)
        receipt_key = (revision.product_id, str(receipt.receipt_id))
        if revision_key in self.revisions or receipt_key in self.receipts:
            raise AssertionError("test store refuses a duplicate revision or receipt identity")
        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        self.revisions[revision_key] = revision
        self.receipts[receipt_key] = receipt
        self.heads[key] = head
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


_LEGACY_FEEDBACK_GRANT_REF = "authority_grant:atrium-resource-feedback"


def _legacy_feedback_grant_material(effective_at: datetime) -> CompositionAuthorityGrantMaterial:
    material = {
        "contract": GRANT_PAYLOAD_CONTRACT,
        "grant_ref": _LEGACY_FEEDBACK_GRANT_REF,
        "product_id": LOCAL_OWNER_PRODUCT_ID,
        "actor_ref": LOCAL_OWNER_ACTOR_REF,
        "participant_principal_ref": LOCAL_OWNER_ACTOR_REF,
        "delegator_ref": None,
        "authority_class": AuthorityClass.DERIVE_PROPOSE,
        "operations": (RESOURCE_FEEDBACK_OPERATION,),
        "scope_ref": LOCAL_OWNER_PRODUCT_ID,
        "policy_ref": LOCAL_OWNER_POLICY_REF,
        "lifecycle": "active",
        "effective_at": effective_at,
        "expires_at": None,
        "revoked_at": None,
        "delegation_ceiling": (),
    }
    provisional = CompositionAuthorityGrantMaterial(**material, grant_hash="0" * 64)
    grant_hash = canonical_hash(provisional.model_dump(mode="json", exclude={"grant_hash"}))
    return CompositionAuthorityGrantMaterial(**material, grant_hash=grant_hash)


async def _seed_legacy_feedback_grant(store: InMemoryGovernedStateStore, *, effective_at: datetime) -> None:
    """Seed the exact bootstrap sequence-1 legacy feedback grant, bypassing bootstrap."""

    grant = _legacy_feedback_grant_material(effective_at)
    payload = grant.model_dump(mode="python")
    material_hash = canonical_hash(grant.model_dump(mode="json"))
    approval_subject_ref = "approval_subject:local-owner:atrium-resource-feedback"
    revision = GovernedStateRevisionV1(
        state_kind="authority_grant",
        product_id=LOCAL_OWNER_PRODUCT_ID,
        state_id=grant.grant_ref,
        sequence=1,
        revision_id=f"authority_grant_revision:{material_hash[:32]}",
        material_hash=material_hash,
        approval_subject_ref=approval_subject_ref,
        payload_contract=GRANT_PAYLOAD_CONTRACT,
        payload=payload,
    )
    approval_hash = canonical_hash(
        {
            "actor_ref": LOCAL_OWNER_ACTOR_REF,
            "product_id": LOCAL_OWNER_PRODUCT_ID,
            "subject_ref": approval_subject_ref,
            "approved_at": effective_at.isoformat(),
        }
    )
    request = GovernedStateCommitRequestV1(
        revision=revision,
        actor_ref=LOCAL_OWNER_ACTOR_REF,
        approval=ResolvedApprovalReceiptV1(
            receipt_ref=f"approval:local-owner-bootstrap:{approval_hash[:32]}",
            product_id=LOCAL_OWNER_PRODUCT_ID,
            subject_ref=approval_subject_ref,
            actor_ref=LOCAL_OWNER_ACTOR_REF,
            receipt_hash=approval_hash,
            approved_at=effective_at,
        ),
        authority_grants=(
            ResolvedAuthorityGrantV1(
                grant_ref=grant.grant_ref,
                product_id=grant.product_id,
                authority=grant.authority_class.value,
                grant_hash=grant.grant_hash,
                effective_at=grant.effective_at,
                expires_at=grant.expires_at,
            ),
        ),
        committed_at=effective_at,
    )
    await store.commit(request)


@pytest.mark.asyncio
async def test_bootstrap_creates_then_verifies_fixed_product_scoped_grants():
    store = InMemoryGovernedStateStore()

    created = await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)
    verified = await bootstrap_local_owner_authority(
        user=_owner(),
        store=store,
        approved_at=NOW + timedelta(hours=1),
    )

    assert [item.status for item in created.grants] == ["created"] * len(LOCAL_OWNER_GRANTS)
    assert [item.status for item in verified.grants] == ["verified"] * len(LOCAL_OWNER_GRANTS)
    assert [item.status for item in created.cognition] == ["created"] * len(LOCAL_OWNER_COGNITION)
    assert [item.status for item in verified.cognition] == ["verified"] * len(LOCAL_OWNER_COGNITION)
    assert len(store.heads) == len(LOCAL_OWNER_GRANTS) + len(LOCAL_OWNER_COGNITION) == 9
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
    for spec in LOCAL_OWNER_COGNITION:
        head = store.heads[(spec.state_kind, LOCAL_OWNER_PRODUCT_ID, spec.state_id)]
        receipt = store.receipts[(LOCAL_OWNER_PRODUCT_ID, head.commit_receipt_id)]
        assert receipt.authority_grants == ()
        assert receipt.actor_ref == LOCAL_OWNER_ACTOR_REF
        assert receipt.sequence == 1
        assert receipt.prior_revision_id is None


@pytest.mark.asyncio
async def test_bootstrap_verifies_grants_after_durable_json_round_trip():
    store = JsonRoundTripGovernedStateStore()

    created = await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)
    verified = await bootstrap_local_owner_authority(
        user=_owner(),
        store=store,
        approved_at=NOW + timedelta(hours=1),
    )

    assert [item.status for item in created.grants] == ["created"] * len(LOCAL_OWNER_GRANTS)
    assert [item.status for item in verified.grants] == ["verified"] * len(LOCAL_OWNER_GRANTS)
    assert [item.status for item in created.cognition] == ["created"] * len(LOCAL_OWNER_COGNITION)
    assert [item.status for item in verified.cognition] == ["verified"] * len(LOCAL_OWNER_COGNITION)
    assert len(store.heads) == len(LOCAL_OWNER_GRANTS) + len(LOCAL_OWNER_COGNITION) == 9


@pytest.mark.asyncio
async def test_bootstrap_migrates_the_exact_legacy_feedback_grant_singleton():
    store = InMemoryGovernedStateStore()
    await _seed_legacy_feedback_grant(store, effective_at=NOW)
    feedback_spec = next(spec for spec in LOCAL_OWNER_GRANTS if spec.grant_ref == _LEGACY_FEEDBACK_GRANT_REF)
    legacy_head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)]
    legacy_revision_id = legacy_head.revision_id

    migrated = await bootstrap_local_owner_authority(
        user=_owner(),
        store=store,
        approved_at=NOW + timedelta(hours=1),
    )

    assert len(store.heads) == len(LOCAL_OWNER_GRANTS) + len(LOCAL_OWNER_COGNITION) == 9
    grant_statuses = {item.grant_ref: item.status for item in migrated.grants}
    assert grant_statuses[feedback_spec.grant_ref] == "migrated"
    assert all(status == "created" for ref, status in grant_statuses.items() if ref != feedback_spec.grant_ref)
    assert all(item.status == "created" for item in migrated.cognition)

    new_head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)]
    assert new_head.sequence == 2
    new_revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, new_head.revision_id)]
    assert new_revision.prior_revision_id == legacy_revision_id
    assert (LOCAL_OWNER_PRODUCT_ID, legacy_revision_id) in store.revisions

    widened = CompositionAuthorityGrantMaterial.model_validate(new_revision.payload)
    assert widened.operations == tuple(sorted(feedback_spec.operations))
    assert widened.effective_at == NOW

    second = await bootstrap_local_owner_authority(
        user=_owner(),
        store=store,
        approved_at=NOW + timedelta(hours=2),
    )
    assert next(item.status for item in second.grants if item.grant_ref == feedback_spec.grant_ref) == "verified"
    assert len(store.heads) == 9


@pytest.mark.asyncio
async def test_bootstrap_rejects_legacy_feedback_grant_at_an_invalid_sequence():
    store = InMemoryGovernedStateStore()
    await _seed_legacy_feedback_grant(store, effective_at=NOW)
    feedback_spec = next(spec for spec in LOCAL_OWNER_GRANTS if spec.grant_ref == _LEGACY_FEEDBACK_GRANT_REF)
    legacy_head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)]
    legacy_revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, legacy_head.revision_id)]

    invalid_revision = legacy_revision.model_copy(
        update={"sequence": 3, "prior_revision_id": "authority_grant_revision:bogus"}
    )
    invalid_head = legacy_head.model_copy(update={"sequence": 3})
    store.revisions[(LOCAL_OWNER_PRODUCT_ID, legacy_head.revision_id)] = invalid_revision
    store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)] = invalid_head

    heads_snapshot = dict(store.heads)
    revisions_snapshot = dict(store.revisions)
    receipts_snapshot = dict(store.receipts)

    with pytest.raises(LocalOwnerAuthorityConflict):
        await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=1))

    assert store.heads == heads_snapshot
    assert store.revisions == revisions_snapshot
    assert store.receipts == receipts_snapshot


@pytest.mark.asyncio
async def test_bootstrap_rejects_a_migrated_feedback_grant_with_a_tampered_prior_revision_id():
    store = InMemoryGovernedStateStore()
    await _seed_legacy_feedback_grant(store, effective_at=NOW)
    await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=1))

    feedback_spec = next(spec for spec in LOCAL_OWNER_GRANTS if spec.grant_ref == _LEGACY_FEEDBACK_GRANT_REF)
    migrated_head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)]
    migrated_revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, migrated_head.revision_id)]
    store.revisions[(LOCAL_OWNER_PRODUCT_ID, migrated_head.revision_id)] = migrated_revision.model_copy(
        update={"prior_revision_id": "authority_grant_revision:bogus"}
    )

    heads_snapshot = dict(store.heads)
    revisions_snapshot = dict(store.revisions)
    receipts_snapshot = dict(store.receipts)

    with pytest.raises(LocalOwnerAuthorityConflict):
        await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=2))

    assert store.heads == heads_snapshot
    assert store.revisions == revisions_snapshot
    assert store.receipts == receipts_snapshot


@pytest.mark.asyncio
async def test_bootstrap_rejects_a_migrated_feedback_grant_with_a_tampered_legacy_history():
    store = InMemoryGovernedStateStore()
    await _seed_legacy_feedback_grant(store, effective_at=NOW)
    await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=1))

    feedback_spec = next(spec for spec in LOCAL_OWNER_GRANTS if spec.grant_ref == _LEGACY_FEEDBACK_GRANT_REF)
    migrated_head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)]
    migrated_revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, migrated_head.revision_id)]
    legacy_revision_id = migrated_revision.prior_revision_id
    legacy_revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, legacy_revision_id)]
    store.revisions[(LOCAL_OWNER_PRODUCT_ID, legacy_revision_id)] = legacy_revision.model_copy(update={"sequence": 5})

    heads_snapshot = dict(store.heads)
    revisions_snapshot = dict(store.revisions)
    receipts_snapshot = dict(store.receipts)

    with pytest.raises(LocalOwnerAuthorityConflict):
        await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=2))

    assert store.heads == heads_snapshot
    assert store.revisions == revisions_snapshot
    assert store.receipts == receipts_snapshot


@pytest.mark.asyncio
async def test_bootstrap_rejects_a_cognition_head_with_a_tampered_approval_receipt():
    store = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)

    cognition_spec = LOCAL_OWNER_COGNITION[0]
    cognition_head = store.heads[(cognition_spec.state_kind, LOCAL_OWNER_PRODUCT_ID, cognition_spec.state_id)]
    receipt = store.receipts[(LOCAL_OWNER_PRODUCT_ID, cognition_head.commit_receipt_id)]
    tampered_approval = receipt.approval.model_copy(
        update={"approved_at": receipt.approval.approved_at + timedelta(minutes=5)}
    )
    store.receipts[(LOCAL_OWNER_PRODUCT_ID, cognition_head.commit_receipt_id)] = receipt.model_copy(
        update={"approval": tampered_approval}
    )

    heads_snapshot = dict(store.heads)
    revisions_snapshot = dict(store.revisions)
    receipts_snapshot = dict(store.receipts)

    with pytest.raises(LocalOwnerAuthorityConflict):
        await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=1))

    assert store.heads == heads_snapshot
    assert store.revisions == revisions_snapshot
    assert store.receipts == receipts_snapshot


@pytest.mark.asyncio
async def test_bootstrap_rejects_corrupted_cognition_before_migrating_a_valid_legacy_grant():
    store = InMemoryGovernedStateStore()
    await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW)

    feedback_spec = next(spec for spec in LOCAL_OWNER_GRANTS if spec.grant_ref == _LEGACY_FEEDBACK_GRANT_REF)
    migrated_head = store.heads.pop(("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref))
    store.revisions.pop((LOCAL_OWNER_PRODUCT_ID, migrated_head.revision_id))
    store.receipts.pop((LOCAL_OWNER_PRODUCT_ID, migrated_head.commit_receipt_id))
    await _seed_legacy_feedback_grant(store, effective_at=NOW)

    cognition_spec = LOCAL_OWNER_COGNITION[0]
    cognition_head = store.heads[(cognition_spec.state_kind, LOCAL_OWNER_PRODUCT_ID, cognition_spec.state_id)]
    cognition_revision = store.revisions[(LOCAL_OWNER_PRODUCT_ID, cognition_head.revision_id)]
    corrupted_payload = dict(cognition_revision.payload)
    corrupted_payload["lifecycle"] = "suspended"
    store.revisions[(LOCAL_OWNER_PRODUCT_ID, cognition_head.revision_id)] = cognition_revision.model_copy(
        update={"payload": corrupted_payload}
    )

    heads_snapshot = dict(store.heads)
    revisions_snapshot = dict(store.revisions)
    receipts_snapshot = dict(store.receipts)

    with pytest.raises(LocalOwnerAuthorityConflict):
        await bootstrap_local_owner_authority(user=_owner(), store=store, approved_at=NOW + timedelta(hours=1))

    assert store.heads == heads_snapshot
    assert store.revisions == revisions_snapshot
    assert store.receipts == receipts_snapshot
    reloaded_head = store.heads[("authority_grant", LOCAL_OWNER_PRODUCT_ID, feedback_spec.grant_ref)]
    assert reloaded_head.sequence == 1


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
    assert [item["status"] for item in created.json()["grants"]] == ["created"] * len(LOCAL_OWNER_GRANTS)
    assert [item["status"] for item in created.json()["cognition"]] == ["created"] * len(LOCAL_OWNER_COGNITION)
    assert verified.status_code == 200
    assert [item["status"] for item in verified.json()["grants"]] == ["verified"] * len(LOCAL_OWNER_GRANTS)
    assert [item["status"] for item in verified.json()["cognition"]] == ["verified"] * len(LOCAL_OWNER_COGNITION)


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
