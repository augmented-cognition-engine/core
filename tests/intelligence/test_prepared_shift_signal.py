from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from ace.application import (
    CorePreparedShiftSignalDerivationService,
    DomainActivationAdmissionService,
    IntelligenceBuildStartV1,
    PreparedIntelligenceLedgerService,
    PreparedShiftSignalDerivationError,
    PreparedShiftSignalDerivationRequestV1Alpha1,
    bind_committed_activation,
)
from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    AuthorizedIntelligenceBuild,
)
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
)
from ace.core.runtime_use import AUTHORITY_GRANT_STATE_KIND
from ace.intelligence import (
    IntelligenceRecordKind,
    PreparedResourceSetAdmissionV1Alpha1,
    deterministic_resource_order,
    resource_reference,
)
from ace.testing import InMemoryImmutableRecordStore
from tests.intelligence.test_categorical_transition_detection import (
    AS_OF as CATEGORICAL_AS_OF,
)
from tests.intelligence.test_categorical_transition_detection import (
    DETECTOR_ID as CATEGORICAL_DETECTOR_ID,
)
from tests.intelligence.test_categorical_transition_detection import (
    _binding as _categorical_prepared_binding,
)
from tests.intelligence.test_categorical_transition_detection import (
    _snapshot as _categorical_snapshot,
)
from tests.intelligence.test_prepared_intelligence_ledger import (
    SECOND_AS_OF,
    _ActivationStore,
    _Authority,
    _committed_binding,
    _derivation,
)

pytestmark = pytest.mark.unit

ACTOR = "principal:personal-operator"
EVALUATED_AT = SECOND_AS_OF + timedelta(minutes=5)


class _CurrentBuildAuthority:
    def __init__(self, original: AuthorityUseReceiptV1Alpha1, *, replacement_head=None, denied: bool = False) -> None:
        self.original = original
        self.replacement_head = replacement_head
        self.denied = denied

    async def resolve_authority_use(self, *, evaluated_at, **_request):
        if self.denied:
            raise RuntimeError("denied")
        return AuthorityUseReceiptV1Alpha1(
            **self.original.model_dump(
                mode="python", exclude={"evaluated_at", "state_head_precondition", "receipt_id", "receipt_digest"}
            ),
            evaluated_at=evaluated_at,
            state_head_precondition=self.replacement_head or self.original.state_head_precondition,
        )

    async def resolve_capability_use(self, **_request):
        raise AssertionError("prepared derivation requires no new capability")


def _build(
    binding,
    grant_head: GovernedStateHeadV1,
    *,
    evaluated_at=EVALUATED_AT,
) -> AuthorizedIntelligenceBuild:
    product_id = binding.prepared_binding.reference.product_id
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=product_id,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:prepared-derivation",
        authentication_receipt_digest="sha256:" + "1" * 64,
        authenticated_at=evaluated_at - timedelta(hours=1),
        expires_at=evaluated_at + timedelta(hours=1),
    )
    request = IntelligenceBuildStartV1(
        authority_grant_ref=grant_head.state_id,
        resource_authority_grant_ref="authority_grant:atrium-observe-read",
        activation_approval_receipt_ref=str(binding.commit_receipt.approval.receipt_ref),
        activation_approval_subject_ref=str(binding.prepared_binding.revision.spec.spec_id),
        client_request_id="atrium_request:prepared-derivation",
        profile_id="intelligence_onboarding_profile:prepared-derivation-fixture",
        subject="Track exact stored entity changes with the configured detector.",
        outcome_id="decision_readiness",
        source_group_ids=(),
        recorded_source_refs=(),
        cadence_id="daily_pulse",
        approved_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=evaluated_at - timedelta(minutes=2),
    )
    build_id = "intelligence_build:prepared-derivation"
    request_digest = "sha256:" + "2" * 64
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=ACTOR,
        authenticated_context=context,
        use_subject_ref=build_id,
        use_subject_digest=request_digest,
        operation="start_intelligence_build",
        authority="intelligence_build",
        grant_ref=grant_head.state_id,
        grant_hash="3" * 64,
        evaluated_at=evaluated_at - timedelta(minutes=1),
        expires_at=evaluated_at + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(grant_head),
    )
    return AuthorizedIntelligenceBuild(
        build_id=build_id,
        request_digest=request_digest,
        product_id=product_id,
        actor_ref=ACTOR,
        request=request,
        authority_use=authority_use,
        activation_approval=binding.commit_receipt.approval,
    )


async def _stack(*, fail_after_records: int | None = None):
    activation_store = _ActivationStore()
    binding = await _committed_binding(activation_store=activation_store)
    full = _derivation(binding)
    activation_head = activation_store.heads[
        (
            binding.commit_receipt.state_kind,
            binding.prepared_binding.reference.product_id,
            str(binding.prepared_binding.revision.activation_id),
        )
    ]
    grant_head = GovernedStateHeadV1(
        state_kind=AUTHORITY_GRANT_STATE_KIND,
        product_id=binding.prepared_binding.reference.product_id,
        state_id="authority_grant:atrium-intelligence-build",
        sequence=1,
        revision_id="authority_grant_revision:prepared-derivation",
        commit_receipt_id="governed_state_commit:prepared-derivation",
        updated_at=EVALUATED_AT - timedelta(minutes=2),
    )
    records = InMemoryImmutableRecordStore(
        governed_state_heads={
            (activation_head.state_kind, activation_head.product_id, activation_head.state_id): activation_head,
            (grant_head.state_kind, grant_head.product_id, grant_head.state_id): grant_head,
        }
    )
    ledger = PreparedIntelligenceLedgerService(binding=binding, store=records)
    source_resources = (*full.observations, *full.entity_snapshots)
    await ledger.admit_resource_set(
        PreparedResourceSetAdmissionV1Alpha1(
            admission_key="resource_set:prepared-derivation-entities",
            product_id=binding.prepared_binding.reference.product_id,
            activation_revision=binding.prepared_binding.reference,
            pack=binding.prepared_binding.revision.spec.pack,
            resources=source_resources,
            processing_order=deterministic_resource_order(source_resources),
            admitted_at=EVALUATED_AT - timedelta(minutes=2),
        )
    )
    records.fail_after_records = fail_after_records
    build = _build(binding, grant_head)
    request = PreparedShiftSignalDerivationRequestV1Alpha1(
        derivation_key="prepared_derivation:generic-two-point",
        detector_id="material_measure_change",
        baseline_snapshot=resource_reference(full.entity_snapshots[0]),
        current_snapshot=resource_reference(full.entity_snapshots[1]),
        evaluated_at=EVALUATED_AT,
    )
    service = CorePreparedShiftSignalDerivationService(
        build=build,
        binding=binding,
        ledger=ledger,
        governed_state=activation_store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
    )
    return activation_store, binding, build, records, request, service


@pytest.mark.asyncio
async def test_prepared_entities_derive_only_shift_signal_attention_and_restart_replay() -> None:
    activation_store, binding, build, records, request, service = await _stack()
    before = await records.scan_product_records(product_id=build.product_id)

    first = await service.derive(request)
    restarted = CorePreparedShiftSignalDerivationService(
        build=build,
        binding=binding,
        ledger=PreparedIntelligenceLedgerService(binding=binding, store=records),
        governed_state=activation_store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
    )
    replay = await restarted.derive(request)
    after = await records.scan_product_records(product_id=build.product_id)

    assert first.material_shift is True
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.admission == first.admission
    assert tuple(item.record_kind for item in first.admission.transaction_receipt.records) == (
        IntelligenceRecordKind.SHIFT.value,
        IntelligenceRecordKind.SIGNAL.value,
        IntelligenceRecordKind.ATTENTION_DISPOSITION.value,
    )
    assert len(after) == len(before) + 3
    assert first.shift.lineage[0].resource_id in {
        request.baseline_snapshot.resource_id,
        request.current_snapshot.resource_id,
    }
    assert first.signal.lineage[0].resource_id == first.shift.resource_id
    assert len(first.admission.transaction_receipt.governed_state_preconditions) == 2


@pytest.mark.asyncio
async def test_categorical_prepared_entities_use_the_same_exact_governed_bridge() -> None:
    evaluated_at = CATEGORICAL_AS_OF + timedelta(minutes=5)
    activation_store = _ActivationStore()
    prepared = _categorical_prepared_binding(activated_at=CATEGORICAL_AS_OF - timedelta(hours=1))
    committed = await DomainActivationAdmissionService(store=activation_store, authority=_Authority()).admit(
        prepared.revision,
        expected_head_revision_id=None,
        committed_at=prepared.revision.occurred_at + timedelta(seconds=1),
    )
    binding = bind_committed_activation(pack=prepared.pack, committed=committed)
    baseline = _categorical_snapshot(
        binding.prepared_binding,
        "draft",
        as_of=CATEGORICAL_AS_OF - timedelta(days=10),
        projected_at=CATEGORICAL_AS_OF,
    )
    current = _categorical_snapshot(
        binding.prepared_binding,
        "active",
        as_of=CATEGORICAL_AS_OF - timedelta(days=5),
        projected_at=CATEGORICAL_AS_OF,
    )
    activation_head = activation_store.heads[
        (
            binding.commit_receipt.state_kind,
            binding.prepared_binding.reference.product_id,
            str(binding.prepared_binding.revision.activation_id),
        )
    ]
    grant_head = GovernedStateHeadV1(
        state_kind=AUTHORITY_GRANT_STATE_KIND,
        product_id=binding.prepared_binding.reference.product_id,
        state_id="authority_grant:atrium-intelligence-build",
        sequence=1,
        revision_id="authority_grant_revision:categorical-derivation",
        commit_receipt_id="governed_state_commit:categorical-derivation",
        updated_at=evaluated_at - timedelta(minutes=2),
    )
    records = InMemoryImmutableRecordStore(
        governed_state_heads={
            (activation_head.state_kind, activation_head.product_id, activation_head.state_id): activation_head,
            (grant_head.state_kind, grant_head.product_id, grant_head.state_id): grant_head,
        }
    )
    ledger = PreparedIntelligenceLedgerService(binding=binding, store=records)
    source_resources = (baseline, current)
    await ledger.admit_resource_set(
        PreparedResourceSetAdmissionV1Alpha1(
            admission_key="resource_set:categorical-derivation-entities",
            product_id=binding.prepared_binding.reference.product_id,
            activation_revision=binding.prepared_binding.reference,
            pack=binding.prepared_binding.revision.spec.pack,
            resources=source_resources,
            processing_order=deterministic_resource_order(source_resources),
            admitted_at=evaluated_at - timedelta(minutes=2),
        )
    )
    build = _build(binding, grant_head, evaluated_at=evaluated_at)
    request = PreparedShiftSignalDerivationRequestV1Alpha1(
        derivation_key="prepared_derivation:categorical-transition",
        detector_id=CATEGORICAL_DETECTOR_ID,
        baseline_snapshot=resource_reference(baseline),
        current_snapshot=resource_reference(current),
        evaluated_at=evaluated_at,
    )
    service = CorePreparedShiftSignalDerivationService(
        build=build,
        binding=binding,
        ledger=ledger,
        governed_state=activation_store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
    )

    result = await service.derive(request)

    assert result.material_shift is True
    assert result.shift.as_of < binding.prepared_binding.revision.occurred_at < result.shift.detected_at
    assert result.shift.shift_type_ref == "material_stage_transition"
    assert result.signal.signal_type_ref == "stage_attention"
    assert result.admission.attention_receipt.disposition.value == "suppressed"


@pytest.mark.asyncio
async def test_wrong_detector_and_changed_exact_reference_fail_without_derived_writes() -> None:
    _, _, build, records, request, service = await _stack()
    before = await records.scan_product_records(product_id=build.product_id)
    missing = request.model_copy(update={"detector_id": "missing_detector", "request_id": None, "request_digest": None})
    with pytest.raises(PreparedShiftSignalDerivationError, match="detector interpretation"):
        await service.derive(missing)

    changed_reference = request.current_snapshot.model_copy(update={"resource_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValidationError, match="resource_id and digest"):
        PreparedShiftSignalDerivationRequestV1Alpha1(
            derivation_key="prepared_derivation:changed-reference",
            detector_id=request.detector_id,
            baseline_snapshot=request.baseline_snapshot,
            current_snapshot=changed_reference,
            evaluated_at=EVALUATED_AT,
        )
    assert await records.scan_product_records(product_id=build.product_id) == before


@pytest.mark.asyncio
async def test_stale_build_authority_and_activation_head_fail_before_derivation() -> None:
    activation_store, binding, build, records, request, _ = await _stack()
    stale_grant = build.authority_use.state_head_precondition.model_copy(
        update={
            "sequence": 2,
            "revision_id": "authority_grant_revision:prepared-derivation-2",
            "commit_receipt_id": "governed_state_commit:prepared-derivation-2",
        }
    )
    stale_authority = CorePreparedShiftSignalDerivationService(
        build=build,
        binding=binding,
        ledger=PreparedIntelligenceLedgerService(binding=binding, store=records),
        governed_state=activation_store,
        runtime_use=_CurrentBuildAuthority(build.authority_use, replacement_head=stale_grant),
    )
    with pytest.raises(PreparedShiftSignalDerivationError, match="changed exact authorized material"):
        await stale_authority.derive(request)

    key = (
        binding.commit_receipt.state_kind,
        build.product_id,
        str(binding.prepared_binding.revision.activation_id),
    )
    head = activation_store.heads[key]
    activation_store.heads[key] = head.model_copy(
        update={
            "sequence": 2,
            "revision_id": "domain_activation_revision:stale",
            "commit_receipt_id": "governed_state_commit:stale",
        }
    )
    current_authority = CorePreparedShiftSignalDerivationService(
        build=build,
        binding=binding,
        ledger=PreparedIntelligenceLedgerService(binding=binding, store=records),
        governed_state=activation_store,
        runtime_use=_CurrentBuildAuthority(build.authority_use),
    )
    with pytest.raises(PreparedShiftSignalDerivationError, match="no longer the exact current head"):
        await current_authority.derive(request)


@pytest.mark.asyncio
async def test_atomic_failure_persists_no_partial_shift_signal_or_attention() -> None:
    _, _, build, records, request, service = await _stack(fail_after_records=1)
    before = await records.scan_product_records(product_id=build.product_id)
    with pytest.raises(PreparedShiftSignalDerivationError, match="admission failed"):
        await service.derive(request)
    assert await records.scan_product_records(product_id=build.product_id) == before


def test_selection_rejects_reversed_or_cross_product_entity_references() -> None:
    async def _exercise():
        _, _, _, _, request, _ = await _stack()
        with pytest.raises(ValidationError, match="baseline must precede"):
            PreparedShiftSignalDerivationRequestV1Alpha1(
                derivation_key="prepared_derivation:reversed",
                detector_id=request.detector_id,
                baseline_snapshot=request.current_snapshot,
                current_snapshot=request.baseline_snapshot,
                evaluated_at=EVALUATED_AT,
            )
        with pytest.raises(ValidationError, match="crossed product"):
            PreparedShiftSignalDerivationRequestV1Alpha1(
                derivation_key="prepared_derivation:cross-product",
                detector_id=request.detector_id,
                baseline_snapshot=request.baseline_snapshot,
                current_snapshot=request.current_snapshot.model_copy(update={"product_id": "product:other"}),
                evaluated_at=EVALUATED_AT,
            )

    import asyncio

    asyncio.run(_exercise())


@pytest.mark.asyncio
async def test_core_resolves_the_declared_prior_snapshot_baseline_itself() -> None:
    """Every detector rule declares ``baseline="prior_snapshot"``, but until now
    nothing honoured it: each caller had to locate an exact baseline reference
    itself, which a product executor holding only the snapshots it just admitted
    cannot do. Core owns the rule, so Core resolves the baseline."""

    _, _, build, _, request, service = await _stack()

    outcome = await service.derive_against_prior_snapshot(
        derivation_key="prepared_derivation:resolved-baseline",
        detector_id=request.detector_id,
        current_snapshot=request.current_snapshot,
        evaluated_at=request.evaluated_at,
    )

    assert outcome is not None
    assert outcome.material_shift is True
    # It selected exactly the snapshot the manual request named.
    assert outcome.request.baseline_snapshot == request.baseline_snapshot
    assert outcome.request.current_snapshot == request.current_snapshot


@pytest.mark.asyncio
async def test_no_prior_snapshot_yields_an_explicit_no_baseline_outcome() -> None:
    """A first admission has nothing to compare against. That is a truthful
    absence, not a Shift and not an error."""

    _, _, _, records, request, service = await _stack()
    before = await records.scan_product_records(product_id=request.baseline_snapshot.product_id)

    outcome = await service.derive_against_prior_snapshot(
        derivation_key="prepared_derivation:no-baseline",
        detector_id=request.detector_id,
        current_snapshot=request.baseline_snapshot,  # the earliest snapshot has no predecessor
        evaluated_at=request.evaluated_at,
    )
    after = await records.scan_product_records(product_id=request.baseline_snapshot.product_id)

    assert outcome is None
    assert len(after) == len(before)
