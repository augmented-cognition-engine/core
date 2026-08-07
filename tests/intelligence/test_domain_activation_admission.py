from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ace.application.domain_activation import (
    DOMAIN_ACTIVATION_STATE_KIND,
    DomainActivationAdmissionError,
    DomainActivationAdmissionService,
)
from ace.core.state import (
    GovernedStateCommitRequestV1,
    ResolvedApprovalReceiptV1,
    ResolvedAuthorityGrantV1,
)
from ace.intelligence.contracts.activation import (
    ActivationState,
    AuthorityBindingV1,
    CompiledOverlayV1,
    CompiledPackRefV1,
    DomainActivationSpecV1,
)
from ace.intelligence.packs.activation import prepare_activation_revision
from core.engine.core.db import parse_rows
from core.engine.core.governed_state import (
    GovernedStateHeadConflict,
    SurrealGovernedStateStore,
)

pytestmark = pytest.mark.unit


def _spec(
    *,
    product_id: str,
    authority_bindings: tuple[AuthorityBindingV1, ...] = (),
) -> DomainActivationSpecV1:
    pack_digest = "sha256:" + "a" * 64
    return DomainActivationSpecV1(
        product_id=product_id,
        activation_key="bounded_orientation",
        pack=CompiledPackRefV1(
            pack_id="bounded_orientation",
            pack_version="0.1.0",
            compiled_pack_id="pack_ir:" + "a" * 32,
            pack_digest=pack_digest,
        ),
        overlay=CompiledOverlayV1(
            overlay_id="local_policy",
            version="0.1.0",
            pack_id="bounded_orientation",
            pack_version="0.1.0",
            pack_digest=pack_digest,
        ),
        compilation_receipt_ref="receipt:compilation",
        conformance_receipt_refs=("receipt:conformance",),
        authority_bindings=authority_bindings,
    )


def _revision(
    *,
    spec: DomainActivationSpecV1,
    receipt_ref: str,
    occurred_at: datetime,
    prior=None,
    state: ActivationState = ActivationState.ACTIVE,
):
    return prepare_activation_revision(
        spec=spec,
        state=state,
        actor_ref="principal:operator",
        approval_receipt_ref=receipt_ref,
        occurred_at=occurred_at,
        prior_revision=prior,
    )


class _Authority:
    def __init__(self, *, approval_subject: str | None = None, grant_product: str | None = None):
        self.approval_subject = approval_subject
        self.grant_product = grant_product
        self.approvals: list[dict] = []
        self.grants: list[dict] = []

    async def resolve_approval(self, **kwargs):
        self.approvals.append(kwargs)
        return ResolvedApprovalReceiptV1(
            receipt_ref=kwargs["receipt_ref"],
            product_id=kwargs["product_id"],
            subject_ref=self.approval_subject or kwargs["subject_ref"],
            actor_ref=kwargs["actor_ref"],
            receipt_hash="b" * 64,
            approved_at=kwargs["effective_at"] - timedelta(seconds=1),
        )

    async def resolve_grant(self, **kwargs):
        self.grants.append(kwargs)
        return ResolvedAuthorityGrantV1(
            grant_ref=kwargs["grant_ref"],
            product_id=self.grant_product or kwargs["product_id"],
            authority=kwargs["authority"],
            grant_hash="c" * 64,
            effective_at=kwargs["effective_at"],
        )


class _MemoryStore:
    def __init__(self):
        self.heads = {}
        self.revisions = {}
        self.receipts = {}

    async def commit(self, request: GovernedStateCommitRequestV1):
        revision = request.revision
        key = (revision.state_kind, revision.product_id, revision.state_id)
        current = self.heads.get(key)
        actual = None if current is None else current.revision_id
        if actual != request.expected_head_revision_id:
            raise GovernedStateHeadConflict("governed_state_head_conflict")
        receipt = request.receipt()
        from ace.core.state import GovernedStateHeadV1

        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=str(receipt.receipt_id),
            updated_at=request.committed_at,
        )
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, receipt.receipt_id)] = receipt
        self.heads[key] = head
        return receipt

    async def load_head(self, *, state_kind, product_id, state_id):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id, *, product_id):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id, *, product_id):
        return self.receipts.get((product_id, receipt_id))


@pytest.mark.asyncio
async def test_admission_resolves_exact_approval_and_grants_before_commit():
    product_id = "product:bounded-orientation"
    binding = AuthorityBindingV1(
        request_id="read_source",
        authority="source_read",
        grant_ref="authority_grant:bounded-read",
    )
    spec = _spec(product_id=product_id, authority_bindings=(binding,))
    occurred_at = datetime(2026, 8, 6, 12, tzinfo=UTC)
    revision = _revision(spec=spec, receipt_ref="approval:initial", occurred_at=occurred_at)
    authority = _Authority()
    store = _MemoryStore()

    committed = await DomainActivationAdmissionService(store=store, authority=authority).admit(
        revision,
        expected_head_revision_id=None,
        committed_at=occurred_at + timedelta(seconds=1),
    )

    assert committed.revision == revision
    assert committed.authority_stage == "committed"
    assert committed.live_authority is False
    assert committed.commit_receipt.authority_stage == "committed"
    assert committed.commit_receipt.audit_id.startswith("governed_state_audit:")
    assert authority.approvals[0]["subject_ref"] == spec.spec_id
    assert authority.grants == [
        {
            "grant_ref": binding.grant_ref,
            "product_id": product_id,
            "authority": binding.authority,
            "effective_at": occurred_at,
        }
    ]


@pytest.mark.asyncio
async def test_admission_fails_closed_on_cross_subject_or_cross_product_resolution():
    product_id = "product:scope-a"
    binding = AuthorityBindingV1(
        request_id="read_source",
        authority="source_read",
        grant_ref="authority_grant:scope-a-read",
    )
    spec = _spec(product_id=product_id, authority_bindings=(binding,))
    occurred_at = datetime(2026, 8, 6, 12, tzinfo=UTC)
    revision = _revision(spec=spec, receipt_ref="approval:scope-a", occurred_at=occurred_at)

    with pytest.raises(DomainActivationAdmissionError, match="exact activation specification"):
        await DomainActivationAdmissionService(
            store=_MemoryStore(),
            authority=_Authority(approval_subject="activation_spec:other"),
        ).admit(
            revision,
            expected_head_revision_id=None,
            committed_at=occurred_at + timedelta(seconds=1),
        )
    with pytest.raises(DomainActivationAdmissionError, match="exact product"):
        await DomainActivationAdmissionService(
            store=_MemoryStore(),
            authority=_Authority(grant_product="product:scope-b"),
        ).admit(
            revision,
            expected_head_revision_id=None,
            committed_at=occurred_at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_reload_reconstructs_exact_committed_head_but_not_live_authority():
    product_id = "product:reload"
    spec = _spec(product_id=product_id)
    occurred_at = datetime(2026, 8, 6, 12, tzinfo=UTC)
    revision = _revision(spec=spec, receipt_ref="approval:reload", occurred_at=occurred_at)
    store = _MemoryStore()
    authority = _Authority()
    committed = await DomainActivationAdmissionService(store=store, authority=authority).admit(
        revision,
        expected_head_revision_id=None,
        committed_at=occurred_at + timedelta(seconds=1),
    )

    reloaded = await DomainActivationAdmissionService(store=store, authority=_Authority()).reload(
        product_id=product_id,
        activation_key=spec.activation_key,
    )

    assert reloaded == committed
    assert reloaded.live_authority is False
    assert (
        await DomainActivationAdmissionService(store=store, authority=_Authority()).reload(
            product_id="product:other",
            activation_key=spec.activation_key,
        )
        is None
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_surreal_commit_is_atomic_current_head_checked_and_restart_reloadable(db_pool):
    product_id = f"product:activation-{uuid4().hex}"
    spec = _spec(product_id=product_id)
    first_at = datetime.now(UTC) - timedelta(minutes=2)
    first = _revision(spec=spec, receipt_ref="approval:first", occurred_at=first_at)
    authority = _Authority()
    first_service = DomainActivationAdmissionService(
        store=SurrealGovernedStateStore(db_pool),
        authority=authority,
    )
    committed = await first_service.admit(
        first,
        expected_head_revision_id=None,
        committed_at=first_at + timedelta(seconds=1),
    )

    restarted = DomainActivationAdmissionService(
        store=SurrealGovernedStateStore(db_pool),
        authority=_Authority(),
    )
    assert await restarted.reload(product_id=product_id, activation_key=spec.activation_key) == committed

    winner = _revision(
        spec=spec,
        receipt_ref="approval:winner",
        occurred_at=first_at + timedelta(seconds=10),
        prior=first,
        state=ActivationState.RETIRED,
    )
    loser = _revision(
        spec=spec,
        receipt_ref="approval:loser",
        occurred_at=first_at + timedelta(seconds=11),
        prior=first,
        state=ActivationState.ACTIVE,
    )
    await restarted.admit(
        winner,
        expected_head_revision_id=first.revision_id,
        committed_at=winner.occurred_at + timedelta(seconds=1),
    )
    with pytest.raises(GovernedStateHeadConflict):
        await restarted.admit(
            loser,
            expected_head_revision_id=first.revision_id,
            committed_at=loser.occurred_at + timedelta(seconds=1),
        )

    durable_store = SurrealGovernedStateStore(db_pool)
    assert await durable_store.load_revision(str(loser.revision_id), product_id=product_id) is None
    async with db_pool.connection() as db:
        assert (
            parse_rows(
                await db.query(
                    "SELECT id FROM governed_state_commit_receipt "
                    "WHERE product = <record>$product AND revision_id = $revision_id",
                    {"product": product_id, "revision_id": loser.revision_id},
                )
            )
            == []
        )
        assert (
            parse_rows(
                await db.query(
                    "SELECT id FROM governed_state_audit "
                    "WHERE product = <record>$product AND revision_id = $revision_id",
                    {"product": product_id, "revision_id": loser.revision_id},
                )
            )
            == []
        )
    final = await restarted.reload(product_id=product_id, activation_key=spec.activation_key)
    assert final is not None
    assert final.revision == winner
    assert final.commit_receipt.audit_id.startswith("governed_state_audit:")
    assert final.commit_receipt.state_kind == DOMAIN_ACTIVATION_STATE_KIND
