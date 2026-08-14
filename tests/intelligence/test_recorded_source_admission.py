from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ace.application.domain_activation import DomainActivationAdmissionService, bind_committed_activation
from ace.application.intelligence_build_execution import (
    REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
    AuthorizedIntelligenceBuild,
    IntelligenceBuildStartV1,
    RecordedSourceReferenceV1,
)
from ace.application.intelligence_resource_projection import IntelligenceLedgerResourceProjectionReader
from ace.application.recorded_source_admission import (
    CoreRecordedSourceAdmissionService,
    RecordedSourceAdmissionError,
    RecordedSourceMaterialV1Alpha1,
)
from ace.core import (
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateHeadV1,
    canonical_json,
)
from ace.core.runtime_use import AUTHORITY_GRANT_STATE_KIND
from ace.intelligence import (
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    detect_numeric_shift,
)
from ace.intelligence.contracts.pack import DomainPackManifestV1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourceQueryV1Alpha1,
)
from ace.intelligence.packs.compiler import compile_pack
from ace.testing import InMemoryImmutableRecordStore
from tests.intelligence.conftest import digest_bytes, encode_json
from tests.intelligence.test_domain_activation_admission import _Authority, _MemoryStore
from tests.intelligence.test_source_mapping import (
    _binding,
    _fixture_documents,
    _manifest_and_resources,
    _subject,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:recorded-source"
ACTOR = "principal:personal-operator"
OBSERVED_AT = datetime(2026, 8, 12, 18, tzinfo=UTC)
ADMITTED_AT = datetime(2026, 8, 13, 18, tzinfo=UTC)


def _compiled_recorded_numeric_pack():
    ontology, mapping, _ = _fixture_documents("numeric")
    manifest, resources = _manifest_and_resources(ontology, mapping)
    detection = {
        "contract": "ace.intelligence.detection/v1alpha1",
        "module_id": "detection",
        "numeric_delta_rules": [
            {
                "detector_id": "material_reading_change",
                "entity_type_id": "reading",
                "attribute_id": "value",
                "baseline": "prior_snapshot",
                "context_attribute_ids": ["code"],
                "metric": "percent_change",
                "threshold": 5.0,
                "direction": "any",
                "shift_type": "material_reading_change",
                "signal_type": "reading_attention",
            }
        ],
    }
    detection_bytes = encode_json(detection)
    resources["modules/detection.json"] = detection_bytes
    material = manifest.model_dump(mode="python")
    material["resources"] = (
        *material["resources"],
        {
            "resource_id": "detection_resource",
            "path": "modules/detection.json",
            "digest": digest_bytes(detection_bytes),
        },
    )
    material["modules"] = (
        *material["modules"],
        {
            "module_id": "detection",
            "contract": "ace.intelligence.detection/v1alpha1",
            "resource_id": "detection_resource",
            "depends_on": ("ontology",),
        },
    )
    return compile_pack(DomainPackManifestV1.model_validate(material), resources)


async def _stack():
    pack = _compiled_recorded_numeric_pack()
    prepared = _binding(pack, product_id=PRODUCT)
    activation_store = _MemoryStore()
    committed = await DomainActivationAdmissionService(
        store=activation_store,
        authority=_Authority(),
    ).admit(
        prepared.revision,
        expected_head_revision_id=None,
        committed_at=prepared.revision.occurred_at + timedelta(seconds=1),
    )
    binding = bind_committed_activation(pack=pack, committed=committed)

    grant_head = GovernedStateHeadV1(
        state_kind=AUTHORITY_GRANT_STATE_KIND,
        product_id=PRODUCT,
        state_id="authority_grant:atrium-intelligence-build",
        sequence=1,
        revision_id="authority_grant_revision:recorded-source",
        commit_receipt_id="governed_state_commit:recorded-source",
        updated_at=ADMITTED_AT - timedelta(minutes=1),
    )
    activation_head = activation_store.heads[
        (
            binding.commit_receipt.state_kind,
            PRODUCT,
            str(binding.prepared_binding.revision.activation_id),
        )
    ]
    records = InMemoryImmutableRecordStore(
        governed_state_heads={
            (activation_head.state_kind, activation_head.product_id, activation_head.state_id): activation_head,
            (grant_head.state_kind, grant_head.product_id, grant_head.state_id): grant_head,
        }
    )
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:recorded-source",
        authentication_receipt_digest="sha256:" + "1" * 64,
        authenticated_at=ADMITTED_AT - timedelta(minutes=2),
        expires_at=ADMITTED_AT + timedelta(hours=1),
    )
    _, _, payload = _fixture_documents("numeric")
    payload_json = canonical_json(payload)
    material = RecordedSourceMaterialV1Alpha1(
        source_group_id="official_records",
        mapping_id="reading_snapshot",
        subject_binding=_subject(binding.prepared_binding, "numeric"),
        source_definition_ref="source_definition:numeric",
        source_type_ref="source:reading/v1",
        source_uri="https://example.invalid/recorded/reading-1",
        captured_payload_json=payload_json,
        captured_payload_digest="sha256:" + hashlib.sha256(payload_json.encode()).hexdigest(),
        source_published_at=OBSERVED_AT - timedelta(hours=1),
        event_effective_at=OBSERVED_AT - timedelta(minutes=30),
        observed_at=OBSERVED_AT,
        locator="record:1",
    )
    request = IntelligenceBuildStartV1(
        authority_grant_ref=grant_head.state_id,
        resource_authority_grant_ref="authority_grant:atrium-observe-read",
        activation_approval_receipt_ref=str(binding.commit_receipt.approval.receipt_ref),
        activation_approval_subject_ref=str(binding.prepared_binding.revision.spec.spec_id),
        client_request_id="atrium_request:recorded-source",
        profile_id="intelligence_onboarding_profile:recorded-source-fixture",
        subject="Track the reviewed recorded source for material changes.",
        outcome_id="decision_readiness",
        source_group_ids=("official_records",),
        recorded_source_refs=(
            RecordedSourceReferenceV1(
                source_group_id=material.source_group_id,
                material_id=str(material.material_id),
                material_digest=str(material.material_digest),
            ),
        ),
        cadence_id="daily_pulse",
        approved_effects=REQUIRED_INTELLIGENCE_BUILD_EFFECTS,
        requested_at=ADMITTED_AT - timedelta(minutes=1),
    )
    build_id = "intelligence_build:recorded-source"
    request_digest = "sha256:" + "2" * 64
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authenticated_context=context,
        use_subject_ref=build_id,
        use_subject_digest=request_digest,
        operation="start_intelligence_build",
        authority="intelligence_build",
        grant_ref=grant_head.state_id,
        grant_hash="3" * 64,
        evaluated_at=ADMITTED_AT,
        expires_at=ADMITTED_AT + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1.from_head(grant_head),
    )
    build = AuthorizedIntelligenceBuild(
        build_id=build_id,
        request_digest=request_digest,
        product_id=PRODUCT,
        actor_ref=ACTOR,
        request=request,
        authority_use=authority_use,
        activation_approval=binding.commit_receipt.approval,
    )
    return binding, build, records, material


@pytest.mark.asyncio
async def test_recorded_replay_admits_canonical_observation_entity_and_reopens_exactly() -> None:
    binding, build, records, material = await _stack()
    service = CoreRecordedSourceAdmissionService(build=build, binding=binding, store=records)

    first = await service.admit((material,))
    replay = await CoreRecordedSourceAdmissionService(
        build=build,
        binding=binding,
        store=records,
    ).admit((material,))

    acquisition = first.acquisition_receipts[0]
    assert acquisition.network_capture_performed is False
    assert acquisition.freshness_verified is False
    assert acquisition.live_acquisition is False
    assert acquisition.reusable_authority is False
    assert first.source_snapshots[0].acquisition_mode.value == "recorded_replay"
    assert first.observations[0].mode is IntelligenceResourceMode.PREPARED
    assert first.observations[0].acquisition_mode is EvidenceAcquisitionMode.RECORDED_REPLAY
    assert first.observations[0].acquisition_receipt_ref == acquisition.receipt_id
    assert first.entity_snapshots[0].mode is IntelligenceResourceMode.PREPARED
    assert first.entity_snapshots[0].entity_ref == material.subject_binding.entity_ref
    assert first.entity_snapshots[0].lineage[0].resource_id == first.observations[0].resource_id
    assert len(first.transaction_receipt.records) == 4
    assert len(first.transaction_receipt.governed_state_preconditions) == 2
    assert replay.replayed is True
    assert replay.acquisition_receipts == first.acquisition_receipts
    assert replay.source_snapshots == first.source_snapshots
    assert replay.observations == first.observations
    assert replay.entity_snapshots == first.entity_snapshots
    assert replay.transaction_receipt == first.transaction_receipt


@pytest.mark.asyncio
async def test_one_recorded_batch_preserves_distinct_state_times_for_detection() -> None:
    binding, build, records, baseline_material = await _stack()
    current_payload = canonical_json({"reading": {"value": "90.000"}, "subject": {"code": "AX"}})
    current_material = RecordedSourceMaterialV1Alpha1(
        **baseline_material.model_dump(
            mode="python",
            exclude={
                "source_uri",
                "captured_payload_json",
                "captured_payload_digest",
                "source_published_at",
                "event_effective_at",
                "observed_at",
                "locator",
                "material_id",
                "material_digest",
            },
        ),
        source_uri="https://example.invalid/recorded/reading-2",
        captured_payload_json=current_payload,
        captured_payload_digest="sha256:" + hashlib.sha256(current_payload.encode()).hexdigest(),
        source_published_at=OBSERVED_AT + timedelta(minutes=10),
        event_effective_at=OBSERVED_AT + timedelta(minutes=15),
        observed_at=OBSERVED_AT + timedelta(minutes=30),
        locator="record:2",
    )
    refs = tuple(
        RecordedSourceReferenceV1(
            source_group_id=item.source_group_id,
            material_id=str(item.material_id),
            material_digest=str(item.material_digest),
        )
        for item in (baseline_material, current_material)
    )
    request_material = build.request.model_dump(mode="python")
    request_material["recorded_source_refs"] = refs
    build = replace(build, request=IntelligenceBuildStartV1.model_validate(request_material))

    admitted = await CoreRecordedSourceAdmissionService(build=build, binding=binding, store=records).admit(
        (baseline_material, current_material)
    )
    baseline, current = sorted(admitted.entity_snapshots, key=lambda item: item.as_of)
    shift = detect_numeric_shift(
        binding=binding.prepared_binding,
        detector_id="material_reading_change",
        baseline=baseline,
        current=current,
        detected_at=ADMITTED_AT,
    )

    assert baseline.as_of == baseline_material.event_effective_at
    assert current.as_of == current_material.event_effective_at
    assert baseline.as_of < current.as_of < baseline.projected_at == current.projected_at == ADMITTED_AT
    assert shift is not None
    assert shift.baseline_as_of == baseline.as_of
    assert shift.as_of == current.as_of


@pytest.mark.asyncio
async def test_recorded_observation_is_visible_from_fresh_canonical_resource_projection() -> None:
    binding, build, records, material = await _stack()
    admitted = await CoreRecordedSourceAdmissionService(
        build=build,
        binding=binding,
        store=records,
    ).admit((material,))
    query = IntelligenceResourceQueryV1Alpha1(
        authenticated_context=build.authority_use.authenticated_context,
        product_id=PRODUCT,
        authority_grant_ref="authority_grant:atrium-observe-read",
        resource_kinds=(IntelligenceResourceKind.OBSERVATION,),
        subject_refs=(material.subject_binding.entity_ref,),
        as_of=ADMITTED_AT,
        available_at=ADMITTED_AT,
        page_size=10,
    )
    page = await IntelligenceLedgerResourceProjectionReader(store=records).read(
        query=query,
        after=None,
        limit=10,
    )

    assert len(page.records) == 1
    assert page.records[0].reference.resource_id == admitted.observations[0].resource_id
    assert page.records[0].reference.resource_kind is IntelligenceResourceKind.OBSERVATION

    entity_query = query.model_copy(update={"resource_kinds": (IntelligenceResourceKind.ENTITY,)})
    entity_page = await IntelligenceLedgerResourceProjectionReader(store=records).read(
        query=entity_query,
        after=None,
        limit=10,
    )
    assert len(entity_page.records) == 1
    assert entity_page.records[0].reference.resource_id == admitted.entity_snapshots[0].resource_id
    assert entity_page.records[0].reference.resource_kind is IntelligenceResourceKind.ENTITY


@pytest.mark.asyncio
async def test_substituted_recorded_material_fails_before_any_write() -> None:
    binding, build, records, material = await _stack()
    changed_payload = canonical_json({"reading": {"value": "999.000"}, "subject": {"code": "AX"}})
    changed = RecordedSourceMaterialV1Alpha1(
        **material.model_dump(
            mode="python",
            exclude={"captured_payload_json", "captured_payload_digest", "material_id", "material_digest"},
        ),
        captured_payload_json=changed_payload,
        captured_payload_digest="sha256:" + hashlib.sha256(changed_payload.encode()).hexdigest(),
    )
    with pytest.raises(RecordedSourceAdmissionError, match="exactly match"):
        await CoreRecordedSourceAdmissionService(build=build, binding=binding, store=records).admit((changed,))
    assert await records.scan_product_records(product_id=PRODUCT) == ()


@pytest.mark.asyncio
async def test_missing_or_extra_recorded_material_fails_before_any_write() -> None:
    binding, build, records, material = await _stack()
    service = CoreRecordedSourceAdmissionService(build=build, binding=binding, store=records)
    with pytest.raises(RecordedSourceAdmissionError, match="requires exact reviewed material"):
        await service.admit(())

    extra = RecordedSourceMaterialV1Alpha1(
        **material.model_dump(mode="python", exclude={"source_uri", "material_id", "material_digest"}),
        source_uri="https://example.invalid/recorded/reading-2",
    )
    with pytest.raises(RecordedSourceAdmissionError, match="exactly match"):
        await service.admit((material, extra))
    assert await records.scan_product_records(product_id=PRODUCT) == ()


@pytest.mark.asyncio
async def test_stale_activation_or_authority_head_fails_atomic_append() -> None:
    binding, build, records, material = await _stack()
    records.governed_state_heads.clear()

    with pytest.raises(Exception, match="precondition"):
        await CoreRecordedSourceAdmissionService(build=build, binding=binding, store=records).admit((material,))
    assert await records.scan_product_records(product_id=PRODUCT) == ()
