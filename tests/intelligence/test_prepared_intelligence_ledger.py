from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ace.application import (
    DomainActivationAdmissionService,
    PreparedIntelligenceAdmissionError,
    PreparedIntelligenceLedgerService,
    bind_committed_activation,
)
from ace.core import (
    GovernedStateHeadV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ResolvedApprovalReceiptV1,
    canonical_json,
)
from ace.intelligence import (
    ActivationState,
    AttentionDisposition,
    AttentionSuppressionReason,
    BriefV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    ClaimGroundingKind,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    GroundedClaimV1Alpha1,
    IntelligenceRecordKind,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageResourceKind,
    ObservationV1Alpha1,
    OrganizationOverlayV1,
    PreparedResourceAdmissionV1Alpha1,
    detect_numeric_shift,
    deterministic_resource_order,
    resource_reference,
    route_shift_as_signal,
)
from ace.intelligence.packs.activation import compile_overlay, prepare_activation_revision, prepare_domain_activation
from ace.intelligence.packs.compiler import compile_pack_document
from ace.testing import (
    InMemoryImmutableRecordStore,
    exercise_prepared_ledger_restart,
)

pytestmark = pytest.mark.unit

PRODUCT_ID = "product:generic-ledger"
ACTIVATED_AT = datetime(2026, 8, 1, 9, tzinfo=UTC)
FIRST_AS_OF = datetime(2026, 8, 2, 9, tzinfo=UTC)
SECOND_AS_OF = datetime(2026, 8, 3, 9, tzinfo=UTC)


def _encoded(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _compiled_pack(*, route_confidence: float = 0.5, pack_id: str = "generic_measurement"):
    modules = {
        "ontology": {
            "contract": "ace.intelligence.ontology/v1alpha1",
            "module_id": "ontology",
            "entity_types": [
                {
                    "entity_type_id": "subject",
                    "attributes": [
                        {"attribute_id": "measure", "value_type": "number", "required": True},
                        {"attribute_id": "label", "value_type": "string", "required": True},
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
                    "detector_id": "material_measure_change",
                    "entity_type_id": "subject",
                    "attribute_id": "measure",
                    "baseline": "prior_snapshot",
                    "context_attribute_ids": ["label"],
                    "metric": "percent_change",
                    "threshold": 5.0,
                    "direction": "any",
                    "shift_type": "material_measure_change",
                    "signal_type": "measure_attention",
                }
            ],
        },
        "synthesis": {
            "contract": "ace.intelligence.synthesis/v1alpha1",
            "module_id": "synthesis",
            "brief_templates": [
                {
                    "template_id": "status_brief",
                    "brief_type": "status_brief",
                    "display_name": "Status Brief",
                    "objective": "Summarize one material measurement change.",
                    "required_sections": ["summary"],
                    "recommendation_required": False,
                }
            ],
        },
        "personas": {
            "contract": "ace.intelligence.personas/v1alpha1",
            "module_id": "personas",
            "personas": [
                {
                    "persona_id": "reviewer",
                    "display_name": "Reviewer",
                    "description": "Reviews material generic changes.",
                }
            ],
            "signal_routing_rules": [
                {
                    "routing_rule_id": "review_material_change",
                    "signal_type": "measure_attention",
                    "persona_ids": ["reviewer"],
                    "minimum_confidence": route_confidence,
                    "brief_template_id": "status_brief",
                }
            ],
        },
    }
    resources = {f"modules/{module_id}.json": _encoded(payload) for module_id, payload in modules.items()}
    manifest = {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": pack_id,
            "version": "0.1.0",
            "display_name": "Generic Measurement",
        },
        "resources": [
            {
                "resource_id": module_id,
                "path": path,
                "digest": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            }
            for module_id, path, payload in (
                (module_id, f"modules/{module_id}.json", resources[f"modules/{module_id}.json"])
                for module_id in modules
            )
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


class _Authority:
    async def resolve_approval(
        self,
        *,
        receipt_ref,
        product_id,
        subject_ref,
        actor_ref,
        effective_at,
    ):
        return ResolvedApprovalReceiptV1(
            receipt_ref=receipt_ref,
            product_id=product_id,
            subject_ref=subject_ref,
            actor_ref=actor_ref,
            receipt_hash="a" * 64,
            approved_at=effective_at,
        )

    async def resolve_grant(self, **kwargs):
        raise AssertionError(f"generic fixture declared no grants: {kwargs}")


class _ActivationStore:
    def __init__(self):
        self.heads = {}
        self.revisions = {}
        self.receipts = {}

    async def commit(self, request):
        receipt = request.receipt()
        revision = request.revision
        head = GovernedStateHeadV1(
            state_kind=revision.state_kind,
            product_id=revision.product_id,
            state_id=revision.state_id,
            sequence=revision.sequence,
            revision_id=revision.revision_id,
            commit_receipt_id=receipt.receipt_id,
            updated_at=request.committed_at,
        )
        self.heads[(revision.state_kind, revision.product_id, revision.state_id)] = head
        self.revisions[(revision.product_id, revision.revision_id)] = revision
        self.receipts[(revision.product_id, receipt.receipt_id)] = receipt
        return receipt

    async def load_head(self, *, state_kind, product_id, state_id):
        return self.heads.get((state_kind, product_id, state_id))

    async def load_revision(self, revision_id, *, product_id):
        return self.revisions.get((product_id, revision_id))

    async def load_receipt(self, receipt_id, *, product_id):
        return self.receipts.get((product_id, receipt_id))


async def _committed_binding(
    *,
    product_id: str = PRODUCT_ID,
    route_confidence: float = 0.5,
    pack_id: str = "generic_measurement",
    activation_store=None,
):
    pack = _compiled_pack(route_confidence=route_confidence, pack_id=pack_id)
    overlay = compile_overlay(
        pack,
        OrganizationOverlayV1(
            overlay_id="generic_fixture",
            version="0.1.0",
            pack_id=pack.metadata.pack_id,
            pack_version=pack.metadata.version,
            pack_digest=pack.pack_digest,
        ),
    )
    spec = prepare_domain_activation(
        product_id=product_id,
        activation_key=pack.metadata.pack_id,
        pack=pack,
        overlay=overlay,
        compilation_receipt_ref="receipt:generic-compilation",
        conformance_receipt_refs=("receipt:generic-conformance",),
    )
    revision = prepare_activation_revision(
        spec=spec,
        state=ActivationState.ACTIVE,
        actor_ref="principal:generic-reviewer",
        approval_receipt_ref="receipt:generic-approval",
        occurred_at=ACTIVATED_AT,
    )
    committed = await DomainActivationAdmissionService(
        store=activation_store or _ActivationStore(), authority=_Authority()
    ).admit(
        revision,
        expected_head_revision_id=None,
        committed_at=ACTIVATED_AT + timedelta(seconds=1),
    )
    return bind_committed_activation(pack=pack, committed=committed)


def _lineage(resource, kind: LineageResourceKind) -> LineageReferenceV1Alpha1:
    reference = resource_reference(resource)
    return LineageReferenceV1Alpha1(
        resource_kind=kind,
        resource_id=reference.resource_id,
        resource_digest=reference.resource_digest,
        resource_as_of=reference.as_of,
        resource_available_at=reference.available_at,
    )


def _derivation(binding, *, derivation_key: str = "derivation:generic-two-point"):
    reference = binding.prepared_binding.reference
    observation_one = ObservationV1Alpha1(
        product_id=binding.prepared_binding.revision.spec.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=FIRST_AS_OF,
        source_ref="source:generic-first",
        source_digest="sha256:" + "1" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="acquisition:generic-first",
        acquisition_receipt_digest="sha256:" + "2" * 64,
        observed_at=FIRST_AS_OF,
        ingested_at=FIRST_AS_OF,
        subject_refs=("entity:generic-subject",),
        payload=CanonicalJsonValueV1Alpha1(value_json='{"label":"points","measure":100.0}'),
        confidence=0.9,
    )
    observation_two = ObservationV1Alpha1(
        product_id=binding.prepared_binding.revision.spec.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=SECOND_AS_OF,
        source_ref="source:generic-second",
        source_digest="sha256:" + "3" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="acquisition:generic-second",
        acquisition_receipt_digest="sha256:" + "4" * 64,
        observed_at=SECOND_AS_OF,
        ingested_at=SECOND_AS_OF,
        subject_refs=("entity:generic-subject",),
        payload=CanonicalJsonValueV1Alpha1(value_json='{"label":"points","measure":90.0}'),
        confidence=0.9,
    )
    projected_at = SECOND_AS_OF + timedelta(minutes=1)
    snapshot_one = EntitySnapshotV1Alpha1(
        product_id=observation_one.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=FIRST_AS_OF,
        lineage=(_lineage(observation_one, LineageResourceKind.OBSERVATION),),
        entity_ref="entity:generic-subject",
        entity_type_ref="subject",
        attributes=CanonicalJsonValueV1Alpha1(value_json='{"label":"points","measure":100.0}'),
        projected_at=projected_at,
        confidence=0.9,
    )
    snapshot_two = EntitySnapshotV1Alpha1(
        product_id=observation_two.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=SECOND_AS_OF,
        lineage=(_lineage(observation_two, LineageResourceKind.OBSERVATION),),
        entity_ref="entity:generic-subject",
        entity_type_ref="subject",
        attributes=CanonicalJsonValueV1Alpha1(value_json='{"label":"points","measure":90.0}'),
        projected_at=projected_at,
        confidence=0.9,
    )
    shift = detect_numeric_shift(
        binding=binding.prepared_binding,
        detector_id="material_measure_change",
        baseline=snapshot_one,
        current=snapshot_two,
        detected_at=SECOND_AS_OF + timedelta(minutes=2),
    )
    assert shift is not None
    signal = route_shift_as_signal(
        binding=binding.prepared_binding,
        detector_id="material_measure_change",
        shift=shift,
        detected_at=SECOND_AS_OF + timedelta(minutes=3),
    )
    brief = BriefV1Alpha1(
        product_id=signal.product_id,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=reference,
        as_of=signal.as_of,
        lineage=(_lineage(signal, LineageResourceKind.SIGNAL),),
        brief_type_ref="status_brief",
        title="Generic measurement changed",
        executive_summary="The exact two-point comparison crossed the configured threshold.",
        body_markdown="## Summary\n\nThe prepared fixture contains one material change.",
        generated_at=SECOND_AS_OF + timedelta(minutes=4),
        claims=(
            GroundedClaimV1Alpha1(
                statement="The exact prepared comparison crossed its bound threshold.",
                grounding_kind=ClaimGroundingKind.INFERENCE,
                inference_basis_refs=(signal.resource_id,),
                confidence=0.9,
                uncertainty="This is a prepared fixture and grants no live authority.",
            ),
        ),
    )
    resources = (
        observation_one,
        observation_two,
        snapshot_one,
        snapshot_two,
        shift,
        signal,
        brief,
    )
    return PreparedResourceAdmissionV1Alpha1(
        derivation_key=derivation_key,
        product_id=signal.product_id,
        activation_revision=reference,
        pack=binding.prepared_binding.revision.spec.pack,
        observations=(observation_one, observation_two),
        entity_snapshots=(snapshot_one, snapshot_two),
        shift=shift,
        signal=signal,
        brief=brief,
        processing_order=deterministic_resource_order(resources),
        attention_evaluated_at=SECOND_AS_OF + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_generic_derivation_is_atomic_restart_replayable_and_historical():
    binding = await _committed_binding()
    batch = _derivation(binding)
    store = InMemoryImmutableRecordStore()
    first_service = PreparedIntelligenceLedgerService(binding=binding, store=store)
    restarted_service = PreparedIntelligenceLedgerService(binding=binding, store=store)

    result = await exercise_prepared_ledger_restart(
        first_service=first_service,
        restarted_service=restarted_service,
        batch=batch,
    )

    assert len(result.first.resources) == 7
    assert len(result.first.transaction_receipt.records) == 8
    assert result.first.attention_receipt.disposition is AttentionDisposition.ROUTE
    assert result.first.attention_receipt.routing_rule_id == "review_material_change"
    assert result.first.attention_receipt.persona_ids == ("reviewer",)
    assert result.first.attention_receipt.brief_template_id == "status_brief"
    assert result.first.attention_receipt.delivery_authority is False
    assert result.first.live_authority is False
    assert canonical_json([resource.model_dump(mode="json") for resource in result.first.resources]) == canonical_json(
        [resource.model_dump(mode="json") for resource in result.restarted_replay.resources]
    )
    assert result.first.transaction_receipt.receipt_id == result.restarted_replay.transaction_receipt.receipt_id
    assert result.first.attention_receipt.receipt_id == result.restarted_replay.attention_receipt.receipt_id

    cutoff = SECOND_AS_OF - timedelta(seconds=1)
    assert (
        len(
            await restarted_service.read_as_of(
                product_id=PRODUCT_ID,
                mode=IntelligenceResourceMode.PREPARED,
                kind=IntelligenceRecordKind.OBSERVATION,
                available_at=cutoff,
            )
        )
        == 1
    )
    for kind in (
        IntelligenceRecordKind.ENTITY_SNAPSHOT,
        IntelligenceRecordKind.SHIFT,
        IntelligenceRecordKind.SIGNAL,
        IntelligenceRecordKind.BRIEF,
        IntelligenceRecordKind.ATTENTION_DISPOSITION,
    ):
        assert (
            await restarted_service.count_as_of(
                product_id=PRODUCT_ID,
                mode=IntelligenceResourceMode.PREPARED,
                kind=kind,
                available_at=cutoff,
            )
            == 0
        )
        assert (
            await restarted_service.count_as_of(
                product_id=PRODUCT_ID,
                mode=IntelligenceResourceMode.LIVE,
                kind=kind,
                available_at=batch.attention_evaluated_at,
            )
            == 0
        )
        assert (
            await restarted_service.read_as_of(
                product_id=PRODUCT_ID,
                mode=IntelligenceResourceMode.LIVE,
                kind=kind,
                available_at=batch.attention_evaluated_at,
            )
            == ()
        )


@pytest.mark.asyncio
async def test_no_route_persists_explicit_suppression_receipt():
    binding = await _committed_binding(route_confidence=0.99)
    batch = _derivation(binding, derivation_key="derivation:generic-suppressed")
    result = await PreparedIntelligenceLedgerService(
        binding=binding,
        store=InMemoryImmutableRecordStore(),
    ).admit(batch)

    assert result.attention_receipt.disposition is AttentionDisposition.SUPPRESSED
    assert result.attention_receipt.suppression_reason is AttentionSuppressionReason.NO_ELIGIBLE_ROUTE
    assert result.attention_receipt.routing_rule_id is None
    assert result.attention_receipt.persona_ids == ()


@pytest.mark.asyncio
async def test_divergent_replay_fails_and_interruption_leaves_no_partial_chain():
    binding = await _committed_binding()
    batch = _derivation(binding)
    store = InMemoryImmutableRecordStore()
    service = PreparedIntelligenceLedgerService(binding=binding, store=store)
    first = await service.admit(batch)
    divergent_payload = batch.model_dump(mode="python", exclude={"batch_id", "batch_digest"})
    divergent_payload["attention_evaluated_at"] += timedelta(seconds=1)
    divergent = PreparedResourceAdmissionV1Alpha1.model_validate(divergent_payload)

    with pytest.raises(ImmutableRecordReplayConflict):
        await service.admit(divergent)
    assert await service.replay(derivation_key=batch.derivation_key) == first

    interrupted_store = InMemoryImmutableRecordStore(fail_after_records=3)
    with pytest.raises(ImmutableRecordPersistenceError, match="simulated interruption"):
        await PreparedIntelligenceLedgerService(
            binding=binding,
            store=interrupted_store,
        ).admit(_derivation(binding, derivation_key="derivation:interrupted"))
    assert interrupted_store.records == {}
    assert interrupted_store.receipts == {}


@pytest.mark.asyncio
async def test_product_activation_pack_lineage_and_mode_checks_fail_closed():
    binding = await _committed_binding()
    batch = _derivation(binding)
    service = PreparedIntelligenceLedgerService(
        binding=binding,
        store=InMemoryImmutableRecordStore(),
    )
    with pytest.raises(PreparedIntelligenceAdmissionError, match="read crossed"):
        await service.read_as_of(
            product_id="product:foreign",
            mode=IntelligenceResourceMode.PREPARED,
            kind=IntelligenceRecordKind.SIGNAL,
            available_at=batch.attention_evaluated_at,
        )

    foreign_binding = await _committed_binding(product_id="product:foreign", pack_id="foreign_measurement")
    with pytest.raises(PreparedIntelligenceAdmissionError, match="product scope"):
        await service.admit(_derivation(foreign_binding, derivation_key="derivation:foreign"))

    foreign_pack = _compiled_pack(pack_id="foreign_pack_ir")
    forged_pack_payload = batch.model_dump(mode="python", exclude={"batch_id", "batch_digest"})
    forged_pack_payload["pack"] = {
        "pack_id": foreign_pack.metadata.pack_id,
        "pack_version": foreign_pack.metadata.version,
        "compiled_pack_id": foreign_pack.compiled_pack_id,
        "pack_digest": foreign_pack.pack_digest,
    }
    forged_pack = PreparedResourceAdmissionV1Alpha1.model_validate(forged_pack_payload)
    with pytest.raises(PreparedIntelligenceAdmissionError, match="exact committed Pack IR"):
        await service.admit(forged_pack)

    stale_snapshot_payload = batch.entity_snapshots[0].model_dump(
        mode="python", exclude={"resource_id", "resource_digest"}
    )
    stale_lineage = stale_snapshot_payload["lineage"][0]
    stale_lineage["resource_available_at"] += timedelta(seconds=1)
    stale_snapshot_payload["lineage"] = (stale_lineage,)
    stale_snapshot = EntitySnapshotV1Alpha1.model_validate(stale_snapshot_payload)
    stale_batch_payload = batch.model_dump(mode="python", exclude={"batch_id", "batch_digest"})
    stale_batch_payload["entity_snapshots"] = (
        stale_snapshot,
        batch.entity_snapshots[1],
    )
    stale_resources = (
        *batch.observations,
        stale_snapshot,
        batch.entity_snapshots[1],
        batch.shift,
        batch.signal,
        batch.brief,
    )
    stale_batch_payload["processing_order"] = deterministic_resource_order(stale_resources)
    stale_batch = PreparedResourceAdmissionV1Alpha1.model_validate(stale_batch_payload)
    with pytest.raises(PreparedIntelligenceAdmissionError, match="as-of|unavailable"):
        await service.admit(stale_batch)

    live_copy = batch.model_copy(update={"mode": IntelligenceResourceMode.LIVE})
    with pytest.raises(PreparedIntelligenceAdmissionError, match="revalidation"):
        await service.admit(live_copy)
    with pytest.raises(ValidationError, match="prepared"):
        PreparedResourceAdmissionV1Alpha1.model_validate(
            {
                **batch.model_dump(mode="python", exclude={"batch_id", "batch_digest"}),
                "mode": IntelligenceResourceMode.LIVE,
            }
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_surreal_atomic_restart_process_replay_and_interruption(db_pool):
    from core.engine.core.governed_state import SurrealGovernedStateStore
    from core.engine.core.immutable_records import SurrealImmutableRecordStore

    suffix = uuid4().hex
    product_id = f"product:generic-ledger-{suffix}"
    binding = await _committed_binding(
        product_id=product_id,
        activation_store=SurrealGovernedStateStore(db_pool),
    )
    batch = _derivation(binding, derivation_key=f"derivation:real-{suffix}")
    service = PreparedIntelligenceLedgerService(
        binding=binding,
        store=SurrealImmutableRecordStore(db_pool),
    )
    first = await service.admit(batch)
    assert await service.admit(batch) == first
    historical_cutoff = SECOND_AS_OF - timedelta(seconds=1)
    assert (
        len(
            await service.read_as_of(
                product_id=product_id,
                mode=IntelligenceResourceMode.PREPARED,
                kind=IntelligenceRecordKind.OBSERVATION,
                available_at=historical_cutoff,
            )
        )
        == 1
    )
    for kind in (
        IntelligenceRecordKind.ENTITY_SNAPSHOT,
        IntelligenceRecordKind.SHIFT,
        IntelligenceRecordKind.SIGNAL,
        IntelligenceRecordKind.BRIEF,
        IntelligenceRecordKind.ATTENTION_DISPOSITION,
    ):
        assert (
            await service.count_as_of(
                product_id=product_id,
                mode=IntelligenceResourceMode.PREPARED,
                kind=kind,
                available_at=historical_cutoff,
            )
            == 0
        )
        assert (
            await service.count_as_of(
                product_id=product_id,
                mode=IntelligenceResourceMode.LIVE,
                kind=kind,
                available_at=batch.attention_evaluated_at,
            )
            == 0
        )

    divergent_payload = batch.model_dump(mode="python", exclude={"batch_id", "batch_digest"})
    divergent_payload["attention_evaluated_at"] += timedelta(seconds=1)
    divergent = PreparedResourceAdmissionV1Alpha1.model_validate(divergent_payload)
    with pytest.raises(ImmutableRecordReplayConflict):
        await service.admit(divergent)

    script = Path(__file__).with_name("prepared_ledger_restart_process.py")
    process = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        input=json.dumps(
            {
                "product_id": product_id,
                "activation_key": binding.prepared_binding.revision.spec.activation_key,
                "derivation_key": batch.derivation_key,
                "pack": binding.prepared_binding.pack.model_dump(mode="json"),
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr or process.stdout
    reopened = json.loads(process.stdout.strip().splitlines()[-1])
    assert reopened == {
        "attention": first.attention_receipt.model_dump(mode="json"),
        "resources": [resource.model_dump(mode="json") for resource in first.resources],
        "transaction": first.transaction_receipt.model_dump(mode="json"),
    }

    interrupted_product = f"product:generic-ledger-interrupted-{suffix}"
    interrupted_binding = await _committed_binding(
        product_id=interrupted_product,
        activation_store=SurrealGovernedStateStore(db_pool),
    )
    interrupted_batch = _derivation(
        interrupted_binding,
        derivation_key=f"derivation:real-interrupted-{suffix}",
    )
    interrupted_store = SurrealImmutableRecordStore(
        db_pool,
        simulate_failure_after_records=3,
    )
    with pytest.raises(
        ImmutableRecordPersistenceError,
        match="immutable-record transaction failed",
    ) as interrupted:
        await PreparedIntelligenceLedgerService(
            binding=interrupted_binding,
            store=interrupted_store,
        ).admit(interrupted_batch)
    assert "simulated_failure" not in str(interrupted.value)
    assert "simulated_failure" not in repr(interrupted.value.__cause__)
    for kind in IntelligenceRecordKind:
        assert (
            await interrupted_store.count_as_of(
                product_id=interrupted_product,
                record_space=IntelligenceResourceMode.PREPARED.value,
                record_kind=kind.value,
                available_at=interrupted_batch.attention_evaluated_at,
            )
            == 0
        )
    assert (
        await interrupted_store.load_transaction_receipt(
            product_id=interrupted_product,
            record_space=IntelligenceResourceMode.PREPARED.value,
            transaction_key=interrupted_batch.derivation_key,
        )
        is None
    )
