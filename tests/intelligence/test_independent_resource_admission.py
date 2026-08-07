from __future__ import annotations

from datetime import timedelta

import pytest

from ace.application import (
    PreparedIntelligenceAdmissionError,
    PreparedIntelligenceLedgerService,
    bind_committed_activation,
)
from ace.intelligence import (
    CaseV1Alpha1,
    IntelligenceRecordKind,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    PreparedResourceSetAdmissionV1Alpha1,
    ShiftV1Alpha1,
    deterministic_resource_order,
    resource_reference,
)
from tests.intelligence.test_brief_synthesis import _environment

pytestmark = pytest.mark.unit


def _case_lineage(resource, kind: LineageResourceKind) -> LineageReferenceV1Alpha1:
    reference = resource_reference(resource)
    return LineageReferenceV1Alpha1(
        resource_kind=kind,
        relation=LineageRelation.DERIVED_FROM,
        resource_id=reference.resource_id,
        resource_digest=reference.resource_digest,
        resource_as_of=reference.as_of,
        resource_available_at=reference.available_at,
    )


@pytest.mark.asyncio
async def test_shift_can_be_admitted_and_replayed_without_inventing_a_signal():
    env = await _environment()
    committed = await env.activation_service.reload(
        product_id=env.request.product_id,
        activation_key=env.request.activation_revision.activation_key,
    )
    assert committed is not None
    binding = bind_committed_activation(pack=env.pack, committed=committed)
    ledger = PreparedIntelligenceLedgerService(binding=binding, store=env.store)
    source = await ledger.replay(derivation_key=env.request.derivation_key)
    assert source is not None
    prior = next(item for item in source.resources if isinstance(item, ShiftV1Alpha1))

    material = prior.model_dump(mode="python", exclude={"resource_id", "resource_digest"})
    material["title"] = "Independent material change retained without attention"
    material["detected_at"] = prior.detected_at + timedelta(seconds=1)
    independent = ShiftV1Alpha1.model_validate(material)
    admission = PreparedResourceSetAdmissionV1Alpha1(
        admission_key="resource-set:independent-shift",
        product_id=independent.product_id,
        activation_revision=independent.activation_revision,
        pack=binding.prepared_binding.revision.spec.pack,
        resources=(independent,),
        processing_order=deterministic_resource_order((independent,)),
        admitted_at=independent.detected_at,
    )

    result = await ledger.admit_resource_set(admission)
    replay = await ledger.replay_resource_set(admission_key=admission.admission_key)

    assert replay == result
    assert result.resources == (independent,)
    assert result.attention_receipt is None
    assert result.live_authority is False
    count_cutoff = independent.detected_at + timedelta(minutes=1)
    assert (
        await ledger.count_as_of(
            product_id=independent.product_id,
            mode=independent.mode,
            kind=IntelligenceRecordKind.SIGNAL,
            available_at=count_cutoff,
        )
        == 1
    )
    assert (
        await ledger.count_as_of(
            product_id=independent.product_id,
            mode=independent.mode,
            kind=IntelligenceRecordKind.SHIFT,
            available_at=count_cutoff,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_resource_set_replay_rejects_attention_transaction_shape():
    env = await _environment()
    committed = await env.activation_service.reload(
        product_id=env.request.product_id,
        activation_key=env.request.activation_revision.activation_key,
    )
    assert committed is not None
    binding = bind_committed_activation(pack=env.pack, committed=committed)
    ledger = PreparedIntelligenceLedgerService(binding=binding, store=env.store)

    with pytest.raises(
        PreparedIntelligenceAdmissionError,
        match="must not contain an attention disposition",
    ):
        await ledger.replay_resource_set(admission_key=env.request.derivation_key)


@pytest.mark.asyncio
async def test_case_freezes_multiple_exact_developments_and_replays_transitive_closure():
    env = await _environment()
    committed = await env.activation_service.reload(
        product_id=env.request.product_id,
        activation_key=env.request.activation_revision.activation_key,
    )
    assert committed is not None
    binding = bind_committed_activation(pack=env.pack, committed=committed)
    ledger = PreparedIntelligenceLedgerService(binding=binding, store=env.store)
    source = await ledger.replay(derivation_key=env.request.derivation_key)
    assert source is not None
    prior = next(item for item in source.resources if isinstance(item, ShiftV1Alpha1))

    material = prior.model_dump(mode="python", exclude={"resource_id", "resource_digest"})
    material["title"] = "Second exact development in the same orientation window"
    material["detected_at"] = prior.detected_at + timedelta(seconds=1)
    second = ShiftV1Alpha1.model_validate(material)
    case = CaseV1Alpha1(
        product_id=prior.product_id,
        mode=prior.mode,
        activation_revision=prior.activation_revision,
        as_of=prior.as_of,
        lineage=(
            _case_lineage(second, LineageResourceKind.SHIFT),
            _case_lineage(prior, LineageResourceKind.SHIFT),
        ),
        case_type_ref="case_type:orientation_window",
        title="Two-development orientation case",
        purpose="Freeze the exact material developments before governed synthesis.",
        subject_refs=prior.subject_refs,
        assembled_at=second.detected_at + timedelta(seconds=1),
    )
    resources = (second, case)
    admission = PreparedResourceSetAdmissionV1Alpha1(
        admission_key="resource-set:multi-development-case",
        product_id=case.product_id,
        activation_revision=case.activation_revision,
        pack=binding.prepared_binding.revision.spec.pack,
        resources=resources,
        processing_order=deterministic_resource_order(resources),
        admitted_at=case.assembled_at,
    )

    result = await ledger.admit_resource_set(admission)
    replay = await ledger.replay_resource_set(admission_key=admission.admission_key)
    loaded = await ledger.load_exact(resource_reference(case))

    assert replay == result
    assert result.resources == (second, case)
    assert loaded == case
    assert case.lineage[0].resource_id == str(prior.resource_id)
    assert case.lineage[1].resource_id == str(second.resource_id)
    assert (
        await ledger.count_as_of(
            product_id=case.product_id,
            mode=case.mode,
            kind=IntelligenceRecordKind.CASE,
            available_at=case.assembled_at,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_case_requires_more_than_one_exact_upstream_resource():
    # The shared resource contract refuses to disguise one derivation as an
    # aggregation boundary; consumers should keep using the exact resource.
    env = await _environment()
    committed = await env.activation_service.reload(
        product_id=env.request.product_id,
        activation_key=env.request.activation_revision.activation_key,
    )
    assert committed is not None
    binding = bind_committed_activation(pack=env.pack, committed=committed)
    source = await PreparedIntelligenceLedgerService(
        binding=binding,
        store=env.store,
    ).replay(derivation_key=env.request.derivation_key)
    assert source is not None
    prior = next(item for item in source.resources if isinstance(item, ShiftV1Alpha1))

    with pytest.raises(ValueError, match="at least two exact upstream resources"):
        CaseV1Alpha1(
            product_id=prior.product_id,
            mode=prior.mode,
            activation_revision=prior.activation_revision,
            as_of=prior.as_of,
            lineage=(_case_lineage(prior, LineageResourceKind.SHIFT),),
            case_type_ref="case_type:orientation_window",
            title="Invalid single-development case",
            purpose="Exercise the aggregation invariant.",
            subject_refs=prior.subject_refs,
            assembled_at=prior.detected_at,
        )
