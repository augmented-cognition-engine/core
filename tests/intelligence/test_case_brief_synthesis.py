"""Case-bound governed PREPARED Brief synthesis (additive to the routed path)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from ace.application import (
    CaseBriefSynthesisError,
    CaseBriefSynthesisReplayConflict,
    CaseBriefSynthesisService,
    DomainActivationAdmissionService,
    PreparedIntelligenceLedgerService,
    bind_committed_activation,
)
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningService,
    GovernedStateHeadPreconditionV1Alpha1,
    ReasoningExecutionBindingV1Alpha1,
    canonical_json,
    capability_state_ref_for_artifact,
)
from ace.intelligence import (
    ActivationState,
    CanonicalJsonValueV1Alpha1,
    CaseV1Alpha1,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
    OrganizationOverlayV1,
    PreparedResourceAdmissionV1Alpha1,
    PreparedResourceSetAdmissionV1Alpha1,
    ShiftV1Alpha1,
    detect_numeric_shift,
    deterministic_resource_order,
    resource_reference,
    route_shift_as_signal,
)
from ace.intelligence.contracts.synthesis import CaseBriefSynthesisRequestV1Alpha1, CaseMemberAttentionBindingV1Alpha1
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import compile_pack_document
from ace.testing import InMemoryImmutableRecordStore
from tests.intelligence.test_brief_synthesis import (
    ACTIVATED_AT,
    APPEND_ARTIFACT,
    ARTIFACT,
    BASELINE_AS_OF,
    BRIEF_AS_OF,
    GENERATED_AT,
    PROJECTED_AT,
    REQUESTED_AT,
    ROUTED_AT,
    SHIFT_DETECTED_AT,
    SIGNAL_AS_OF,
    SIGNAL_DETECTED_AT,
    _ActivationAuthority,
    _ActivationStore,
    _Clock,
    _head,
    _Provider,
    _Runtime,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:prepared-brief"
CASE_ASSEMBLED_AT = datetime(2026, 8, 6, 12, 3, tzinfo=UTC)


def _encoded(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _case_pack():
    """One inert Pack IR with two distinct routed templates and personas."""

    modules = {
        "ontology": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "product",
                    "attributes": [
                        {"attribute_id": "name", "value_type": "string", "required": True},
                        {"attribute_id": "price", "value_type": "number", "required": True},
                        {"attribute_id": "rating", "value_type": "number", "required": True},
                    ],
                }
            ],
            "relation_types": [],
        },
        "detection": {
            "contract": "ace.intelligence.detection/v1alpha1",
            "module_id": "detection",
            "numeric_delta_rules": [
                {
                    "detector_id": "price_change",
                    "entity_type_id": "product",
                    "attribute_id": "price",
                    "baseline": "prior_snapshot",
                    "context_attribute_ids": ["name"],
                    "metric": "percent_change",
                    "threshold": 5.0,
                    "direction": "any",
                    "shift_type": "material_price_change",
                    "signal_type": "price_attention",
                },
                {
                    "detector_id": "rating_change",
                    "entity_type_id": "product",
                    "attribute_id": "rating",
                    "baseline": "prior_snapshot",
                    "context_attribute_ids": ["name"],
                    "metric": "percent_change",
                    "threshold": 5.0,
                    "direction": "any",
                    "shift_type": "material_quality_change",
                    "signal_type": "quality_attention",
                },
            ],
        },
        "synthesis": {
            "contract": "ace.intelligence.synthesis/v1alpha2",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "price_brief",
                    "brief_type": "price_brief",
                    "display_name": "Price Change Brief",
                    "objective": "Summarize the exact listed price changes and a bounded action.",
                    "required_sections": ["summary", "recommendation"],
                    "recommendation_required": True,
                },
                {
                    "template_id": "quality_brief",
                    "brief_type": "quality_brief",
                    "display_name": "Quality Change Brief",
                    "objective": "Summarize the exact listed quality changes and a bounded action.",
                    "required_sections": ["summary", "recommendation"],
                    "recommendation_required": True,
                },
            ],
        },
        "personas": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [
                {
                    "persona_id": "pricing_reviewer",
                    "display_name": "Pricing Reviewer",
                    "description": "Reviews exact prepared price changes.",
                },
                {
                    "persona_id": "quality_reviewer",
                    "display_name": "Quality Reviewer",
                    "description": "Reviews exact prepared quality changes.",
                },
            ],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "route_price_change",
                    "signal_type": "price_attention",
                    "persona_ids": ["pricing_reviewer"],
                    "minimum_confidence": 0.5,
                    "brief_template_id": "price_brief",
                },
                {
                    "routing_rule_id": "route_quality_change",
                    "signal_type": "quality_attention",
                    "persona_ids": ["quality_reviewer"],
                    "minimum_confidence": 0.5,
                    "brief_template_id": "quality_brief",
                },
            ],
        },
    }
    resources = {f"modules/{module_id}.json": _encoded(payload) for module_id, payload in modules.items()}
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": "prepared_case",
            "version": "0.1.0",
            "display_name": "Prepared Case",
        },
        "resources": [
            {
                "resource_id": module_id,
                "path": f"modules/{module_id}.json",
                "digest": f"sha256:{hashlib.sha256(resources[f'modules/{module_id}.json']).hexdigest()}",
            }
            for module_id in modules
        ],
        "modules": [
            {
                "module_id": "ontology",
                "contract": modules["ontology"]["contract"],
                "resource_id": "ontology",
                "depends_on": [],
            },
            {
                "module_id": "detection",
                "contract": modules["detection"]["contract"],
                "resource_id": "detection",
                "depends_on": ["ontology"],
            },
            {
                "module_id": "synthesis",
                "contract": modules["synthesis"]["contract"],
                "resource_id": "synthesis",
                "depends_on": [],
            },
            {
                "module_id": "personas",
                "contract": modules["personas"]["contract"],
                "resource_id": "personas",
                "depends_on": ["detection", "synthesis"],
            },
        ],
        "capability_requirements": [],
        "authority_requests": [],
        "overlay_slots": [],
    }
    return compile_pack_document(_encoded(manifest), resources)


def _lineage(resource, kind: LineageResourceKind) -> LineageReferenceV1Alpha1:
    reference = resource_reference(resource)
    return LineageReferenceV1Alpha1(
        resource_kind=kind,
        relation=LineageRelation.DERIVED_FROM,
        resource_id=reference.resource_id,
        resource_digest=reference.resource_digest,
        resource_as_of=reference.as_of,
        resource_available_at=reference.available_at,
    )


def _observation(reference, *, entity: str, suffix: str, as_of: datetime, attributes: dict):
    return ObservationV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=as_of,
        source_ref=f"source:{suffix}",
        source_digest="sha256:" + f"{abs(hash(suffix)) % 10:x}" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref=f"acquisition:{suffix}",
        acquisition_receipt_digest="sha256:" + f"{(abs(hash(suffix)) + 3) % 10:x}" * 64,
        source_published_at=as_of,
        observed_at=as_of,
        ingested_at=as_of,
        subject_refs=(entity,),
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(attributes)),
        confidence=0.9,
    )


def _snapshot(reference, *, entity: str, observations, as_of: datetime, attributes: dict):
    return EntitySnapshotV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=as_of,
        lineage=tuple(_lineage(item, LineageResourceKind.OBSERVATION) for item in observations),
        entity_ref=entity,
        entity_type_ref="product",
        attributes=CanonicalJsonValueV1Alpha1(value_json=canonical_json(attributes)),
        projected_at=PROJECTED_AT,
        confidence=0.9,
    )


def _derivation(
    binding,
    *,
    key: str,
    entity: str,
    detector_id: str,
    baseline: dict,
    current: dict,
) -> PreparedResourceAdmissionV1Alpha1:
    reference = binding.prepared_binding.reference
    first = _observation(
        reference,
        entity=entity,
        suffix=f"{key}-baseline",
        as_of=BASELINE_AS_OF,
        attributes=baseline,
    )
    second = _observation(
        reference,
        entity=entity,
        suffix=f"{key}-current",
        as_of=SIGNAL_AS_OF,
        attributes=current,
    )
    baseline_snapshot = _snapshot(
        reference,
        entity=entity,
        observations=(first,),
        as_of=BASELINE_AS_OF,
        attributes=baseline,
    )
    current_snapshot = _snapshot(
        reference,
        entity=entity,
        observations=(second,),
        as_of=SIGNAL_AS_OF,
        attributes=current,
    )
    shift = detect_numeric_shift(
        binding=binding.prepared_binding,
        detector_id=detector_id,
        baseline=baseline_snapshot,
        current=current_snapshot,
        detected_at=SHIFT_DETECTED_AT,
    )
    assert shift is not None
    signal = route_shift_as_signal(
        binding=binding.prepared_binding,
        detector_id=detector_id,
        shift=shift,
        detected_at=SIGNAL_DETECTED_AT,
    )
    resources = (first, second, baseline_snapshot, current_snapshot, shift, signal)
    return PreparedResourceAdmissionV1Alpha1(
        derivation_key=key,
        product_id=PRODUCT,
        activation_revision=reference,
        pack=binding.prepared_binding.revision.spec.pack,
        observations=(first, second),
        entity_snapshots=(baseline_snapshot, current_snapshot),
        shift=shift,
        signal=signal,
        brief=None,
        processing_order=deterministic_resource_order(resources),
        attention_evaluated_at=ROUTED_AT,
    )


@dataclass(frozen=True, slots=True)
class _CaseEnvironment:
    service: CaseBriefSynthesisService
    activation_service: DomainActivationAdmissionService
    ledger: PreparedIntelligenceLedgerService
    store: InMemoryImmutableRecordStore
    provider: _Provider
    binding: object
    context: AuthenticatedRuntimeContextV1Alpha1
    price_first: object
    price_second: object
    quality: object
    independent_shift: ShiftV1Alpha1
    case: CaseV1Alpha1
    request: CaseBriefSynthesisRequestV1Alpha1


async def _case_environment(
    *,
    provider: _Provider | None = None,
    pack=None,
    service_factory=CaseBriefSynthesisService,
) -> _CaseEnvironment:
    pack = pack if pack is not None else _case_pack()
    activation_store = _ActivationStore()
    activation_service = DomainActivationAdmissionService(
        store=activation_store,
        authority=_ActivationAuthority(),
    )
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="prepared_case",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id=PRODUCT,
        activation_key=pack.metadata.pack_id,
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="receipt:prepared-case-compilation",
        conformance_receipt_refs=("receipt:prepared-case-conformance",),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:pricing-reviewer",
        approval_receipt_ref="receipt:prepared-case-approval",
        occurred_at=ACTIVATED_AT,
    )
    committed = await activation_service.admit(
        revision,
        expected_head_revision_id=None,
        committed_at=ACTIVATED_AT + timedelta(seconds=1),
    )
    binding = bind_committed_activation(pack=pack, committed=committed)
    store = InMemoryImmutableRecordStore()
    ledger = PreparedIntelligenceLedgerService(binding=binding, store=store)

    price_first = await ledger.admit(
        _derivation(
            binding,
            key="derivation:case-price-x1",
            entity="entity:edge-x1",
            detector_id="price_change",
            baseline={"name": "Edge X1", "price": 1200.0, "rating": 4.8},
            current={"name": "Edge X1", "price": 1080.0, "rating": 4.8},
        )
    )
    price_second = await ledger.admit(
        _derivation(
            binding,
            key="derivation:case-price-x2",
            entity="entity:edge-x2",
            detector_id="price_change",
            baseline={"name": "Edge X2", "price": 900.0, "rating": 4.5},
            current={"name": "Edge X2", "price": 800.0, "rating": 4.5},
        )
    )
    quality = await ledger.admit(
        _derivation(
            binding,
            key="derivation:case-quality-x3",
            entity="entity:edge-x3",
            detector_id="rating_change",
            baseline={"name": "Edge X3", "price": 500.0, "rating": 4.8},
            current={"name": "Edge X3", "price": 500.0, "rating": 4.0},
        )
    )

    prior_shift = next(item for item in price_first.resources if isinstance(item, ShiftV1Alpha1))
    material = prior_shift.model_dump(mode="python", exclude={"resource_id", "resource_digest"})
    material["title"] = "Independent material change retained without attention"
    material["detected_at"] = prior_shift.detected_at + timedelta(seconds=1)
    independent_shift = ShiftV1Alpha1.model_validate(material)
    await ledger.admit_resource_set(
        PreparedResourceSetAdmissionV1Alpha1(
            admission_key="resource-set:case-independent-shift",
            product_id=PRODUCT,
            activation_revision=binding.prepared_binding.reference,
            pack=binding.prepared_binding.revision.spec.pack,
            resources=(independent_shift,),
            processing_order=deterministic_resource_order((independent_shift,)),
            admitted_at=independent_shift.detected_at,
        )
    )

    case = _case(
        binding,
        members=(
            (_signal(price_first), LineageResourceKind.SIGNAL),
            (_signal(price_second), LineageResourceKind.SIGNAL),
            (independent_shift, LineageResourceKind.SHIFT),
        ),
    )
    await ledger.admit_resource_set(
        PreparedResourceSetAdmissionV1Alpha1(
            admission_key="resource-set:case-orientation",
            product_id=PRODUCT,
            activation_revision=binding.prepared_binding.reference,
            pack=binding.prepared_binding.revision.spec.pack,
            resources=(case,),
            processing_order=deterministic_resource_order((case,)),
            admitted_at=case.assembled_at,
        )
    )

    execution_head = _head("reasoning_configuration", "reasoning_configuration:prepared-brief")
    execution_binding = ReasoningExecutionBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=ARTIFACT,
        configuration_ref="reasoning_configuration:prepared-brief",
        authority="reason",
        grant_ref="authority_grant:prepared-brief",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(execution_head),
    )
    append_head = _head(
        "governed_operation_configuration",
        "governed_operation_configuration:prepared-brief-append",
    )
    append_binding = GovernedOperationBindingV1Alpha1(
        product_id=PRODUCT,
        artifact=APPEND_ARTIFACT,
        configuration_ref="governed_operation_configuration:prepared-brief-append",
        authority="append_immutable_records",
        grant_ref="authority_grant:prepared-brief-append",
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(append_head),
    )
    activation_head = activation_store.heads[
        (
            committed.commit_receipt.state_kind,
            committed.commit_receipt.product_id,
            committed.commit_receipt.state_id,
        )
    ]
    for head in (
        execution_head,
        append_head,
        _head("capability_state", capability_state_ref_for_artifact(ARTIFACT)),
        _head("authority_grant", execution_binding.grant_ref),
        _head("capability_state", capability_state_ref_for_artifact(APPEND_ARTIFACT)),
        _head("authority_grant", append_binding.grant_ref),
        activation_head,
    ):
        store.set_governed_state_head(head)
    runtime = _Runtime(execution_binding=execution_binding, append_binding=append_binding)
    runtime.store = store
    actual_provider = provider or _Provider()
    reasoning = GovernedReasoningService(
        store=store,
        runtime_use=runtime,
        provider=actual_provider,
        clock=_Clock(
            REQUESTED_AT,
            REQUESTED_AT + timedelta(seconds=5),
            REQUESTED_AT + timedelta(seconds=10),
            GENERATED_AT,
            GENERATED_AT,
        ),
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:pricing-reviewer",
        authentication_receipt_ref="authentication:prepared-case",
        authentication_receipt_digest="sha256:" + "e" * 64,
        authenticated_at=BASELINE_AS_OF - timedelta(minutes=1),
        expires_at=REQUESTED_AT + timedelta(minutes=5),
    )
    service = service_factory(
        activation_service=activation_service,
        pack=pack,
        store=store,
        reasoning=reasoning,
        execution_binding=execution_binding,
        append_binding=append_binding,
        clock=_Clock(GENERATED_AT),
    )
    request = CaseBriefSynthesisRequestV1Alpha1(
        synthesis_key="c" * 240,
        reasoning_attempt_key="k" * 240,
        product_id=PRODUCT,
        authenticated_context=context,
        activation_revision=binding.prepared_binding.reference,
        pack=binding.prepared_binding.revision.spec.pack,
        case=resource_reference(case),
        member_attention=(
            _attention_binding(price_first),
            _attention_binding(price_second),
        ),
        brief_as_of=BRIEF_AS_OF,
        context_cutoff_at=ROUTED_AT,
        requested_at=REQUESTED_AT,
    )
    return _CaseEnvironment(
        service=service,
        activation_service=activation_service,
        ledger=ledger,
        store=store,
        provider=actual_provider,
        binding=binding,
        context=context,
        price_first=price_first,
        price_second=price_second,
        quality=quality,
        independent_shift=independent_shift,
        case=case,
        request=request,
    )


def _signal(admission):
    return next(item for item in admission.resources if resource_reference(item).resource_id.startswith("signal:"))


def _attention_binding(admission) -> CaseMemberAttentionBindingV1Alpha1:
    receipt = admission.attention_receipt
    return CaseMemberAttentionBindingV1Alpha1(
        signal_resource_id=receipt.signal.resource_id,
        derivation_key=admission.transaction_receipt.transaction_key,
        attention_receipt_id=str(receipt.receipt_id),
        attention_receipt_digest=str(receipt.receipt_digest),
    )


def _case(binding, *, members, assembled_at: datetime = CASE_ASSEMBLED_AT) -> CaseV1Alpha1:
    resources = tuple(item for item, _ in members)
    return CaseV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=binding.prepared_binding.reference,
        as_of=max(item.as_of for item in resources),
        lineage=tuple(_lineage(item, kind) for item, kind in members),
        case_type_ref="case_type:orientation_window",
        title="Multi-development orientation case",
        purpose="Freeze the exact material developments before governed synthesis.",
        subject_refs=tuple(sorted({subject for item in resources for subject in item.subject_refs})),
        assembled_at=assembled_at,
    )


@pytest.mark.asyncio
async def test_case_bound_brief_binds_every_member_and_replays_without_reasoning_again():
    env = await _case_environment()

    first = await env.service.synthesize(env.request)

    assert first.replayed is False
    assert env.provider.calls == 1
    receipt = first.synthesis_receipt
    assert receipt.case == resource_reference(env.case)
    assert receipt.case_member_ids == tuple(sorted(item.resource_id for item in env.case.lineage))
    assert len(receipt.case_member_ids) == 3
    assert receipt.template_id == "price_brief"
    assert receipt.persona_ids == ("pricing_reviewer",)
    lineage_ids = {item.resource_id for item in first.brief.lineage}
    assert str(env.case.resource_id) in lineage_ids
    assert set(receipt.case_member_ids) <= lineage_ids
    # Complete transitive closure: two derivations of six resources each, one
    # independent Shift that reuses the first derivation's snapshots, plus the Case.
    assert len(lineage_ids) == 14
    assert {item.record.resource_id for item in receipt.selected_context} == lineage_ids

    replay = await env.service.synthesize(env.request)

    assert replay.replayed is True
    assert env.provider.calls == 1
    assert replay.brief == first.brief
    assert replay.synthesis_receipt == receipt
    assert replay.transaction_receipt == first.transaction_receipt


@pytest.mark.asyncio
async def test_case_bound_synthesis_preserves_the_single_derivation_contract_identity():
    """The additive path uses its own transaction key, kind, and contract family."""

    env = await _case_environment()
    admission = await env.service.synthesize(env.request)

    kinds = {record.record_kind for record in env.store.records.values()}
    assert "case_brief_synthesis_receipt" in kinds
    assert "brief_synthesis_receipt" not in kinds
    assert admission.synthesis_receipt.contract == "ace.intelligence.case-brief-synthesis-receipt/v1alpha1"
    assert admission.brief.contract == "ace.intelligence.brief/v1alpha1"


@pytest.mark.asyncio
async def test_missing_case_fails_closed_without_reasoning():
    env = await _case_environment()
    storage = next(key for key, record in env.store.records.items() if record.record_kind == "case")
    del env.store.records[storage]

    with pytest.raises(CaseBriefSynthesisError, match="bound Case is missing"):
        await env.service.synthesize(env.request)
    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_missing_case_member_fails_closed_without_reasoning():
    env = await _case_environment()
    member_id = str(_signal(env.price_second).resource_id)
    storage = next(key for key, record in env.store.records.items() if record.record_key == member_id)
    del env.store.records[storage]

    with pytest.raises(CaseBriefSynthesisError, match="missing from PREPARED scope"):
        await env.service.synthesize(env.request)
    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_changed_case_member_envelope_fails_closed_without_reasoning():
    env = await _case_environment()
    member_id = str(_signal(env.price_second).resource_id)
    storage, record = next((key, value) for key, value in env.store.records.items() if value.record_key == member_id)
    material = record.model_dump(mode="python", exclude={"storage_id", "material_hash"})
    material["available_at"] = record.available_at + timedelta(seconds=1)
    env.store.records[storage] = type(record).model_validate(material)

    with pytest.raises(CaseBriefSynthesisError, match="Case member closure"):
        await env.service.synthesize(env.request)
    assert env.provider.calls == 0


class _ClosureMutatingProvider(_Provider):
    """Drop one exact Case member from durable scope during Core reasoning."""

    def __init__(self) -> None:
        super().__init__()
        self.store: InMemoryImmutableRecordStore | None = None
        self.victim_record_key: str | None = None

    async def execute(self, request):
        output = await super().execute(request)
        if self.store is not None and self.victim_record_key is not None:
            storage = next(
                key for key, record in self.store.records.items() if record.record_key == self.victim_record_key
            )
            del self.store.records[storage]
        return output


@pytest.mark.asyncio
async def test_case_context_changing_during_reasoning_leaves_no_brief():
    provider = _ClosureMutatingProvider()
    env = await _case_environment(provider=provider)
    provider.store = env.store
    provider.victim_record_key = str(env.independent_shift.resource_id)

    with pytest.raises(CaseBriefSynthesisError):
        await env.service.synthesize(env.request)
    assert provider.calls == 1
    assert not any(record.record_kind == "brief" for record in env.store.records.values())
    assert not any(record.record_kind == "case_brief_synthesis_receipt" for record in env.store.records.values())


@pytest.mark.asyncio
async def test_incompatible_member_routes_derive_no_single_brief():
    env = await _case_environment()
    incompatible = _case(
        env.binding,
        members=(
            (_signal(env.price_first), LineageResourceKind.SIGNAL),
            (_signal(env.quality), LineageResourceKind.SIGNAL),
        ),
    )
    await env.ledger.admit_resource_set(
        PreparedResourceSetAdmissionV1Alpha1(
            admission_key="resource-set:case-incompatible",
            product_id=PRODUCT,
            activation_revision=env.binding.prepared_binding.reference,
            pack=env.binding.prepared_binding.revision.spec.pack,
            resources=(incompatible,),
            processing_order=deterministic_resource_order((incompatible,)),
            admitted_at=incompatible.assembled_at,
        )
    )
    request = env.request.model_copy(
        update={
            "case": resource_reference(incompatible),
            "member_attention": (
                _attention_binding(env.price_first),
                _attention_binding(env.quality),
            ),
            "request_id": None,
            "request_digest": None,
        }
    )
    request = CaseBriefSynthesisRequestV1Alpha1.model_validate(request.model_dump(mode="python"))

    with pytest.raises(CaseBriefSynthesisError, match="incompatible Brief templates"):
        await env.service.synthesize(request)
    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_unbound_signal_member_attention_fails_closed():
    env = await _case_environment()
    request = CaseBriefSynthesisRequestV1Alpha1.model_validate(
        env.request.model_copy(
            update={
                "member_attention": (_attention_binding(env.price_first),),
                "request_id": None,
                "request_digest": None,
            }
        ).model_dump(mode="python")
    )

    with pytest.raises(CaseBriefSynthesisError, match="every exact Signal member requires"):
        await env.service.synthesize(request)
    assert env.provider.calls == 0


@pytest.mark.asyncio
async def test_stale_context_cutoff_excludes_a_case_member_and_fails_closed():
    env = await _case_environment()
    stale_cutoff = SIGNAL_DETECTED_AT - timedelta(seconds=1)
    with pytest.raises(ValueError, match="available by the context cutoff"):
        CaseBriefSynthesisRequestV1Alpha1.model_validate(
            env.request.model_copy(
                update={
                    "brief_as_of": stale_cutoff,
                    "context_cutoff_at": stale_cutoff,
                    "request_id": None,
                    "request_digest": None,
                }
            ).model_dump(mode="python")
        )


@pytest.mark.asyncio
async def test_denied_append_authority_leaves_no_case_brief_residue():
    env = await _case_environment()
    env.store.governed_state_heads[
        (
            "governed_operation_configuration",
            PRODUCT,
            "governed_operation_configuration:prepared-brief-append",
        )
    ] = _head(
        "governed_operation_configuration",
        "governed_operation_configuration:prepared-brief-append",
        sequence=2,
    )

    with pytest.raises(CaseBriefSynthesisError):
        await env.service.synthesize(env.request)
    assert env.provider.calls == 1
    assert not any(record.record_kind == "brief" for record in env.store.records.values())
    assert not any(record.record_kind == "case_brief_synthesis_receipt" for record in env.store.records.values())


@pytest.mark.asyncio
async def test_same_synthesis_key_with_different_case_material_is_a_replay_conflict():
    env = await _case_environment()
    await env.service.synthesize(env.request)
    diverged = CaseBriefSynthesisRequestV1Alpha1.model_validate(
        env.request.model_copy(
            update={
                "reasoning_attempt_key": "z" * 240,
                "request_id": None,
                "request_digest": None,
            }
        ).model_dump(mode="python")
    )

    with pytest.raises(CaseBriefSynthesisReplayConflict):
        await env.service.synthesize(diverged)
    assert env.provider.calls == 1
