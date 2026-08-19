"""Atomic activate/deactivate admission and co-activation proof (PI10).

Uses an in-memory ``GovernedStateStore`` double, following the same pattern
already used by ``tests/intelligence/test_composition_policy_admission_ac7.py``
(``CasGovernedStateStore``) rather than the disposable-SurrealDB fixtures used
for Domain Pack activation tests -- this suite exercises the admission
*service*'s own transition/atomicity logic, not the concrete SurrealDB
transaction (which is exercised elsewhere and reused unchanged here).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from ace.application.solution_bundle_activation import (
    BUNDLE_ACTIVATION_STATE_KIND,
    SolutionBundleActivationAdmissionService,
    SolutionBundleActivationError,
)
from ace.core.contracts import canonical_hash
from ace.core.state import (
    GovernedStateCommitRequestV1,
    GovernedStateHeadV1,
    ResolvedApprovalReceiptV1,
)
from ace.intelligence.contracts.activation import CompiledOverlayV1, CompiledPackRefV1
from ace.intelligence.contracts.solution_bundle import (
    AdapterBindingV1,
    AtriumModuleBindingV1,
    BundleActivationAction,
    BundleActivationRuntimeState,
    PolicyBindingV1,
    SolutionBundleActivationRevisionV1,
    SolutionBundleManifestV1,
)
from ace.intelligence.packs.bundle_activation import resolve_solution_bundle

pytestmark = pytest.mark.unit

PRODUCT = "product:pi10-conformance"
BASE = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


class CasGovernedStateStore:
    """In-memory single-transaction double for ``GovernedStateStore``."""

    def __init__(self) -> None:
        self.heads: dict[tuple[str, str, str], GovernedStateHeadV1] = {}
        self.revisions: dict[tuple[str, str], object] = {}
        self.receipts: dict[tuple[str, str], object] = {}
        self.commit_calls = 0

    async def commit(self, request: GovernedStateCommitRequestV1):
        self.commit_calls += 1
        revision = request.revision
        key = (revision.state_kind, revision.product_id, revision.state_id)
        current = self.heads.get(key)
        actual = current.revision_id if current is not None else None
        if actual != request.expected_head_revision_id:
            raise RuntimeError("governed_state_head_conflict")
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
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, str(receipt.receipt_id))] = receipt
        self.heads[key] = head
        return receipt

    async def load_head(self, *, state_kind: str, product_id: str, state_id: str):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id: str, *, product_id: str):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id: str, *, product_id: str):
        return self.receipts.get((product_id, receipt_id))

    async def load_receipt_for_revision(self, revision_id: str, *, product_id: str):
        envelope = self.revisions.get((product_id, revision_id))
        if envelope is None:
            return None
        return self.receipts.get((product_id, envelope.revision_id))


class FailingAfterValidationGovernedStateStore(CasGovernedStateStore):
    """Simulates a transaction that aborts: raises before mutating any state."""

    async def commit(self, request: GovernedStateCommitRequestV1):
        self.commit_calls += 1
        raise RuntimeError("simulated transaction abort mid-commit")


class PresentAuthority:
    async def resolve_approval(self, *, receipt_ref, product_id, subject_ref, actor_ref, effective_at):
        return ResolvedApprovalReceiptV1(
            receipt_ref=receipt_ref,
            product_id=product_id,
            subject_ref=subject_ref,
            actor_ref=actor_ref,
            receipt_hash=canonical_hash([receipt_ref, product_id, subject_ref, actor_ref, effective_at.isoformat()]),
            approved_at=effective_at - timedelta(milliseconds=1),
        )

    async def resolve_grant(self, *, grant_ref, product_id, authority, effective_at):
        raise AssertionError("solution bundle activation must not request authority grants")


def _pack_ref(pack_id: str = "demo_pack") -> CompiledPackRefV1:
    return CompiledPackRefV1(
        pack_id=pack_id,
        pack_version="1.0.0",
        compiled_pack_id=f"pack_ir:{'a' * 32}",
        pack_digest="sha256:" + "a" * 64,
    )


def _manifest(*, bundle_id: str = "demo_bundle", product_id: str = PRODUCT) -> SolutionBundleManifestV1:
    pack = _pack_ref(f"{bundle_id}_pack")
    return SolutionBundleManifestV1(
        product_id=product_id,
        bundle_id=bundle_id,
        bundle_version="1.0.0",
        pack=pack,
        overlay=CompiledOverlayV1(
            overlay_id=f"{bundle_id}_overlay",
            version="1.0.0",
            pack_id=pack.pack_id,
            pack_version=pack.pack_version,
            pack_digest=pack.pack_digest,
            values=(),
        ),
        adapters=(
            AdapterBindingV1(
                adapter_id=f"{bundle_id}_adapter", adapter_version="1.0.0", artifact_digest="sha256:" + "b" * 64
            ),
        ),
        atrium_modules=(
            AtriumModuleBindingV1(
                module_id=f"{bundle_id}_module", module_version="1.0.0", artifact_digest="sha256:" + "c" * 64
            ),
        ),
        policy=PolicyBindingV1(
            policy_id=f"{bundle_id}_policy", policy_version="1.0.0", policy_digest="sha256:" + "d" * 64
        ),
    )


def _revision(
    *,
    manifest: SolutionBundleManifestV1,
    action: BundleActivationAction,
    state: BundleActivationRuntimeState,
    revision: int,
    prior_revision_id: str | None,
    occurred_at: datetime,
    nonce: str,
) -> SolutionBundleActivationRevisionV1:
    return SolutionBundleActivationRevisionV1(
        revision=revision,
        manifest=manifest,
        resolution_receipt=resolve_solution_bundle(manifest),
        action=action,
        state=state,
        prior_revision_id=prior_revision_id,
        actor_ref="principal:tester",
        approval_receipt_ref=f"approval:{nonce}",
        occurred_at=occurred_at,
    )


@pytest.mark.asyncio
async def test_initial_activation_then_reload_round_trips() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()
    revision = _revision(
        manifest=manifest,
        action=BundleActivationAction.ACTIVATE,
        state=BundleActivationRuntimeState.ACTIVE,
        revision=1,
        prior_revision_id=None,
        occurred_at=BASE,
        nonce="1",
    )
    committed = await service.admit(revision, committed_at=BASE + timedelta(seconds=1))
    assert committed.revision.state is BundleActivationRuntimeState.ACTIVE
    assert committed.live_authority is False

    reloaded = await service.reload(product_id=PRODUCT, bundle_id="demo_bundle")
    assert reloaded is not None
    assert reloaded.revision == committed.revision
    assert reloaded.commit_receipt == committed.commit_receipt


@pytest.mark.asyncio
async def test_deactivate_requires_current_active_revision_and_never_calls_commit() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()
    # revision > 1 is the only shape the contract itself allows for DEACTIVATE
    # (the first revision must activate); nothing has ever been admitted to
    # this store, so the *service* must independently reject this transition.
    revision = _revision(
        manifest=manifest,
        action=BundleActivationAction.DEACTIVATE,
        state=BundleActivationRuntimeState.RETIRED,
        revision=2,
        prior_revision_id="solution_bundle_activation_revision:" + "9" * 32,
        occurred_at=BASE,
        nonce="1",
    )
    with pytest.raises(SolutionBundleActivationError):
        await service.admit(revision, committed_at=BASE + timedelta(seconds=1))
    assert store.commit_calls == 0
    assert store.heads == {}


@pytest.mark.asyncio
async def test_activate_deactivate_reactivate_lifecycle_is_append_only() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()

    activated = await service.admit(
        _revision(
            manifest=manifest,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.ACTIVE,
            revision=1,
            prior_revision_id=None,
            occurred_at=BASE,
            nonce="1",
        ),
        committed_at=BASE + timedelta(seconds=1),
    )
    deactivated = await service.admit(
        _revision(
            manifest=manifest,
            action=BundleActivationAction.DEACTIVATE,
            state=BundleActivationRuntimeState.RETIRED,
            revision=2,
            prior_revision_id=activated.revision.revision_id,
            occurred_at=BASE + timedelta(minutes=1),
            nonce="2",
        ),
        committed_at=BASE + timedelta(minutes=1, seconds=1),
    )
    assert deactivated.revision.state is BundleActivationRuntimeState.RETIRED

    reactivated = await service.admit(
        _revision(
            manifest=manifest,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.ACTIVE,
            revision=3,
            prior_revision_id=deactivated.revision.revision_id,
            occurred_at=BASE + timedelta(minutes=2),
            nonce="3",
        ),
        committed_at=BASE + timedelta(minutes=2, seconds=1),
    )
    assert reactivated.revision.state is BundleActivationRuntimeState.ACTIVE
    assert reactivated.revision.revision == 3

    current = await service.reload(product_id=PRODUCT, bundle_id="demo_bundle")
    assert current.revision.revision == 3
    assert current.revision.state is BundleActivationRuntimeState.ACTIVE


@pytest.mark.asyncio
async def test_stale_prior_revision_is_rejected() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()
    await service.admit(
        _revision(
            manifest=manifest,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.ACTIVE,
            revision=1,
            prior_revision_id=None,
            occurred_at=BASE,
            nonce="1",
        ),
        committed_at=BASE + timedelta(seconds=1),
    )
    stale = _revision(
        manifest=manifest,
        action=BundleActivationAction.DEACTIVATE,
        state=BundleActivationRuntimeState.RETIRED,
        revision=2,
        prior_revision_id="solution_bundle_activation_revision:" + "0" * 32,
        occurred_at=BASE + timedelta(minutes=1),
        nonce="stale",
    )
    with pytest.raises(SolutionBundleActivationError):
        await service.admit(stale, committed_at=BASE + timedelta(minutes=1, seconds=1))
    assert store.commit_calls == 1  # only the first, successful admit ever reached the store


@pytest.mark.asyncio
async def test_concurrent_deactivate_attempts_allow_exactly_one_winner() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()
    activated = await service.admit(
        _revision(
            manifest=manifest,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.ACTIVE,
            revision=1,
            prior_revision_id=None,
            occurred_at=BASE,
            nonce="1",
        ),
        committed_at=BASE + timedelta(seconds=1),
    )
    competitors = [
        _revision(
            manifest=manifest,
            action=BundleActivationAction.DEACTIVATE,
            state=BundleActivationRuntimeState.RETIRED,
            revision=2,
            prior_revision_id=activated.revision.revision_id,
            occurred_at=BASE + timedelta(minutes=1),
            nonce=f"race-{index}",
        )
        for index in range(3)
    ]
    outcomes = await asyncio.gather(
        *(service.admit(item, committed_at=BASE + timedelta(minutes=1, seconds=1)) for item in competitors),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in outcomes) == 1
    assert sum(isinstance(item, SolutionBundleActivationError) for item in outcomes) == 2


@pytest.mark.asyncio
async def test_injected_failure_mid_activation_leaves_no_partial_state_and_reports_honestly() -> None:
    store = FailingAfterValidationGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()
    revision = _revision(
        manifest=manifest,
        action=BundleActivationAction.ACTIVATE,
        state=BundleActivationRuntimeState.ACTIVE,
        revision=1,
        prior_revision_id=None,
        occurred_at=BASE,
        nonce="1",
    )
    with pytest.raises(SolutionBundleActivationError) as excinfo:
        await service.admit(revision, committed_at=BASE + timedelta(seconds=1))

    message = str(excinfo.value)
    assert message  # honest: never swallowed into a silent success
    assert len(message) < 200  # bounded: no raw traceback or payload dump leaks into the report
    assert store.heads == {}  # no partial head
    assert store.revisions == {}  # no partial revision
    assert store.receipts == {}  # no partial receipt

    reloaded = await service.reload(product_id=PRODUCT, bundle_id="demo_bundle")
    assert reloaded is None


@pytest.mark.asyncio
async def test_preview_never_calls_the_store() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    manifest = _manifest()
    receipt = service.preview(manifest)
    assert receipt == resolve_solution_bundle(manifest)
    assert store.commit_calls == 0
    assert store.heads == {}


@pytest.mark.asyncio
async def test_two_bundles_co_activate_on_one_product_without_conflict_leakage_or_dependency() -> None:
    store = CasGovernedStateStore()
    service = SolutionBundleActivationAdmissionService(store=store, authority=PresentAuthority())
    personal = _manifest(bundle_id="personal_intelligence")
    code_intelligence = _manifest(bundle_id="code_intelligence")

    # No dependency: Personal activates fully while Code Intelligence has
    # never been registered, previewed, or activated anywhere in the store.
    personal_committed = await service.admit(
        _revision(
            manifest=personal,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.ACTIVE,
            revision=1,
            prior_revision_id=None,
            occurred_at=BASE,
            nonce="personal-1",
        ),
        committed_at=BASE + timedelta(seconds=1),
    )
    assert personal_committed.revision.state is BundleActivationRuntimeState.ACTIVE
    absent_code_intelligence = await service.reload(product_id=PRODUCT, bundle_id="code_intelligence")
    assert absent_code_intelligence is None

    # No conflict: Code Intelligence activates afterwards on the same product.
    code_committed = await service.admit(
        _revision(
            manifest=code_intelligence,
            action=BundleActivationAction.ACTIVATE,
            state=BundleActivationRuntimeState.ACTIVE,
            revision=1,
            prior_revision_id=None,
            occurred_at=BASE + timedelta(minutes=1),
            nonce="code-1",
        ),
        committed_at=BASE + timedelta(minutes=1, seconds=1),
    )
    assert code_committed.revision.state is BundleActivationRuntimeState.ACTIVE

    reloaded_personal = await service.reload(product_id=PRODUCT, bundle_id="personal_intelligence")
    reloaded_code = await service.reload(product_id=PRODUCT, bundle_id="code_intelligence")
    assert reloaded_personal.revision.activation_id != reloaded_code.revision.activation_id

    # No leakage: neither bundle's manifest names the other's bound identifiers.
    personal_ids = {
        reloaded_personal.revision.manifest.pack.pack_id,
        *[a.adapter_id for a in reloaded_personal.revision.manifest.adapters],
        *[m.module_id for m in reloaded_personal.revision.manifest.atrium_modules],
        reloaded_personal.revision.manifest.policy.policy_id,
    }
    code_ids = {
        reloaded_code.revision.manifest.pack.pack_id,
        *[a.adapter_id for a in reloaded_code.revision.manifest.adapters],
        *[m.module_id for m in reloaded_code.revision.manifest.atrium_modules],
        reloaded_code.revision.manifest.policy.policy_id,
    }
    assert personal_ids.isdisjoint(code_ids)

    assert len(store.heads) == 2
    kinds = {key[0] for key in store.heads}
    assert kinds == {BUNDLE_ACTIVATION_STATE_KIND}
