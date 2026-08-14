"""Governed admission of explicitly reviewed recorded source material.

This boundary is intentionally different from LIVE source ingress.  It performs
no network request and makes no freshness claim.  Core binds the exact recorded
bytes to the already-authorized ``connect_sources`` build effect, the current
authority-grant head, and one exact committed Domain Activation head before it
atomically persists a recorded-replay receipt, canonical source snapshot, and
canonical PREPARED Observation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.domain_activation import (
    DOMAIN_ACTIVATION_STATE_KIND,
    CommittedActivationBinding,
    CommittedDomainActivation,
    bind_committed_activation,
)
from ace.application.intelligence_build_execution import (
    AuthorizedIntelligenceBuild,
    IntelligenceBuildRecordedSourcePort,
)
from ace.application.intelligence_ledger import PREPARED_RECORD_SPACE
from ace.core.contracts import FrozenContract, canonical_hash, canonical_json
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.core.source import CanonicalSourceSnapshotV1Alpha1, SourceAcquisitionMode
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.common import (
    validate_digest,
    validate_reference,
    validate_slug,
)
from ace.intelligence.contracts.ledger import IntelligenceRecordKind, resource_available_at
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    EntitySnapshotV1Alpha1,
    EvidenceAcquisitionMode,
    IntelligenceResourceMode,
    ObservationV1Alpha1,
)
from ace.intelligence.contracts.source_mapping import (
    SOURCE_MAPPING_MODULE_VERSION,
    ResolvedSubjectBindingV1Alpha1,
    SourceMappingModuleV1,
)
from ace.intelligence.packs.runtime import resolve_entity_type_declaration
from ace.intelligence.source_mapping import interpret_prepared_source_mapping

RECORDED_SOURCE_MATERIAL_VERSION = "ace.application.recorded-source-material/v1alpha1"
RECORDED_SOURCE_ACQUISITION_RECEIPT_VERSION = "ace.application.recorded-source-acquisition-receipt/v1alpha1"
RECORDED_SOURCE_RECORD_KIND = "recorded_source_acquisition"
SOURCE_SNAPSHOT_RECORD_KIND = "source_snapshot"
CONNECT_SOURCES_EFFECT = "connect_sources"
INTELLIGENCE_BUILD_OPERATION = "start_intelligence_build"
INTELLIGENCE_BUILD_AUTHORITY = "intelligence_build"


class RecordedSourceAdmissionError(RuntimeError):
    """Recorded material failed exact governed admission or replay."""


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _derive(instance: _StrictFrozenContract, *, id_field: str, digest_field: str, prefix: str) -> None:
    material = instance.model_dump(mode="json", exclude={id_field, digest_field})
    digest = canonical_hash(material)
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    supplied_id = getattr(instance, id_field)
    supplied_digest = getattr(instance, digest_field)
    if supplied_id is not None and supplied_id != expected_id:
        raise ValueError(f"{id_field} does not match exact contract material")
    if supplied_digest is not None and supplied_digest != expected_digest:
        raise ValueError(f"{digest_field} does not match exact contract material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class RecordedSourceMaterialV1Alpha1(_StrictFrozenContract):
    """Exact reviewed bytes and metadata; never proof of a fresh acquisition."""

    contract: Literal["ace.application.recorded-source-material/v1alpha1"] = RECORDED_SOURCE_MATERIAL_VERSION
    source_group_id: str
    mapping_id: str
    subject_binding: ResolvedSubjectBindingV1Alpha1
    source_definition_ref: str
    source_type_ref: str
    source_uri: str = Field(min_length=3, max_length=2_048)
    captured_payload_json: str = Field(min_length=1, max_length=1_000_000)
    captured_payload_digest: str
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    locator: str | None = Field(default=None, min_length=1, max_length=1_000)
    material_id: str | None = None
    material_digest: str | None = None

    @field_validator("source_group_id", "mapping_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_slug(value, name=info.field_name)

    @field_validator("source_definition_ref", "material_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("captured_payload_digest", "material_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("captured_payload_json")
    @classmethod
    def require_canonical_payload(cls, value: str) -> str:
        try:
            parsed = json.loads(value, object_pairs_hook=lambda pairs: _unique_object(pairs))
            normalized = canonical_json(parsed)
        except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("captured_payload_json must be bounded canonical JSON") from exc
        if normalized != value:
            raise ValueError("captured_payload_json must already use exact canonical JSON bytes")
        return value

    @field_validator("source_published_at", "event_effective_at", "observed_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_exact_recorded_material(self) -> Self:
        # CanonicalSourceSnapshot performs the strict JSON parse and
        # canonicalization.  Reject an unreviewed byte digest here before Core
        # assigns any acquisition or Observation identity.
        expected = "sha256:" + hashlib.sha256(self.captured_payload_json.encode("utf-8")).hexdigest()
        if self.captured_payload_digest != expected:
            raise ValueError("captured_payload_digest does not match exact submitted bytes")
        if self.source_published_at is not None and self.source_published_at > self.observed_at:
            raise ValueError("source_published_at cannot follow observed_at")
        if self.event_effective_at is not None and self.event_effective_at > self.observed_at:
            raise ValueError("event_effective_at cannot follow observed_at")
        _derive(self, id_field="material_id", digest_field="material_digest", prefix="recorded_source_material")
        return self


class RecordedSourceAcquisitionReceiptV1Alpha1(_StrictFrozenContract):
    """Proof of governed recorded-replay admission, never a network-capture claim."""

    contract: Literal["ace.application.recorded-source-acquisition-receipt/v1alpha1"] = (
        RECORDED_SOURCE_ACQUISITION_RECEIPT_VERSION
    )
    disposition: Literal["recorded_material_admitted"] = "recorded_material_admitted"
    acquisition_mode: Literal[EvidenceAcquisitionMode.RECORDED_REPLAY] = EvidenceAcquisitionMode.RECORDED_REPLAY
    product_id: str
    actor_ref: str
    build_id: str
    build_request_digest: str
    effect: Literal["connect_sources"] = CONNECT_SOURCES_EFFECT
    build_authority_use: AuthorityUseReceiptV1Alpha1
    activation_revision: ActivationRevisionReferenceV1Alpha1
    activation_head_precondition: GovernedStateHeadPreconditionV1Alpha1
    recorded_material_id: str
    recorded_material_digest: str
    source_group_id: str
    source_definition_ref: str
    source_type_ref: str
    source_uri: str
    captured_payload_digest: str
    source_published_at: datetime | None = None
    event_effective_at: datetime | None = None
    observed_at: datetime
    admitted_at: datetime
    network_capture_performed: Literal[False] = False
    freshness_verified: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator(
        "product_id",
        "actor_ref",
        "build_id",
        "recorded_material_id",
        "source_definition_ref",
        "receipt_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("source_group_id")
    @classmethod
    def validate_group(cls, value: str) -> str:
        return validate_slug(value, name="source_group_id")

    @field_validator(
        "build_request_digest",
        "recorded_material_digest",
        "captured_payload_digest",
        "receipt_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("source_published_at", "event_effective_at", "observed_at", "admitted_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_governed_recorded_admission(self) -> Self:
        authority = self.build_authority_use
        if (
            authority.product_id != self.product_id
            or authority.actor_ref != self.actor_ref
            or authority.use_subject_ref != self.build_id
            or authority.use_subject_digest != self.build_request_digest
            or authority.operation != INTELLIGENCE_BUILD_OPERATION
            or authority.authority != INTELLIGENCE_BUILD_AUTHORITY
            or authority.evaluated_at != self.admitted_at
        ):
            raise ValueError("build authority use does not bind the exact recorded admission")
        if (
            self.activation_head_precondition.state_kind not in {DOMAIN_ACTIVATION_STATE_KIND, "domain_activation"}
            or self.activation_head_precondition.product_id != self.product_id
            or self.activation_head_precondition.state_id != self.activation_revision.activation_id
            or self.activation_head_precondition.sequence != self.activation_revision.revision
            or self.activation_head_precondition.revision_id != self.activation_revision.revision_id
        ):
            raise ValueError("recorded admission does not bind the exact activation head")
        if self.activation_revision.product_id != self.product_id:
            raise ValueError("activation revision crossed recorded admission product scope")
        if self.observed_at > self.admitted_at:
            raise ValueError("recorded material cannot be admitted before its stated observation time")
        _derive(self, id_field="receipt_id", digest_field="receipt_digest", prefix="recorded_source_acquisition")
        return self

    @property
    def live_acquisition(self) -> Literal[False]:
        return False

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class RecordedSourceAdmission:
    """Exact reopened recorded evidence, mapped entities, and append receipt."""

    acquisition_receipts: tuple[RecordedSourceAcquisitionReceiptV1Alpha1, ...]
    source_snapshots: tuple[CanonicalSourceSnapshotV1Alpha1, ...]
    observations: tuple[ObservationV1Alpha1, ...]
    entity_snapshots: tuple[EntitySnapshotV1Alpha1, ...]
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool

    @property
    def live_acquisition(self) -> Literal[False]:
        return False


def _activation_head(binding: CommittedActivationBinding) -> GovernedStateHeadPreconditionV1Alpha1:
    revision = binding.prepared_binding.revision
    receipt = binding.commit_receipt
    if revision.activation_id is None or revision.revision_id is None or receipt.receipt_id is None:
        raise RecordedSourceAdmissionError("committed activation is missing exact head coordinates")
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=receipt.state_kind,
        product_id=revision.spec.product_id,
        state_id=revision.activation_id,
        sequence=revision.revision,
        revision_id=revision.revision_id,
        commit_receipt_id=receipt.receipt_id,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _record(
    payload,
    *,
    product_id: str,
    kind: str,
    key: str,
    as_of: datetime,
    available_at: datetime,
    order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=PREPARED_RECORD_SPACE,
        record_kind=kind,
        record_key=key,
        payload_contract=payload.contract,
        payload=payload.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=order,
    )


class CoreRecordedSourceAdmissionService(IntelligenceBuildRecordedSourcePort):
    """Bind reviewed replay bytes to one authorized build and committed activation."""

    def __init__(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        binding: CommittedActivationBinding,
        store: ImmutableRecordStore,
    ) -> None:
        self.build = build
        self.binding = self._validate_binding(binding)
        self.store = store
        self._validate_build()

    @staticmethod
    def _validate_binding(binding: CommittedActivationBinding) -> CommittedActivationBinding:
        try:
            exact = bind_committed_activation(
                pack=binding.prepared_binding.pack,
                committed=CommittedDomainActivation(
                    revision=binding.prepared_binding.revision,
                    commit_receipt=binding.commit_receipt,
                ),
            )
        except Exception:
            raise RecordedSourceAdmissionError("committed activation binding failed exact revalidation") from None
        if exact != binding:
            raise RecordedSourceAdmissionError("committed activation binding changed during revalidation")
        return exact

    def _validate_build(self) -> None:
        authority = self.build.authority_use
        if (
            authority.product_id != self.build.product_id
            or authority.actor_ref != self.build.actor_ref
            or authority.use_subject_ref != self.build.build_id
            or authority.use_subject_digest != self.build.request_digest
            or authority.operation != INTELLIGENCE_BUILD_OPERATION
            or authority.authority != INTELLIGENCE_BUILD_AUTHORITY
            or authority.grant_ref != self.build.request.authority_grant_ref
            or not {CONNECT_SOURCES_EFFECT, "map_concepts"}.issubset(self.build.request.approved_effects)
        ):
            raise RecordedSourceAdmissionError(
                "authorized build does not cover exact recorded source admission and mapping"
            )
        if self.binding.prepared_binding.reference.product_id != self.build.product_id:
            raise RecordedSourceAdmissionError("committed activation crossed the authorized build product")

    def bind_subject(
        self,
        *,
        subject_binding_id: str,
        entity_type_id: str,
        entity_ref: str,
    ) -> ResolvedSubjectBindingV1Alpha1:
        """Resolve one declared subject identity without exposing activation inputs."""

        try:
            declared_types = {
                mapping.entity_type_id
                for module_ir in self.binding.prepared_binding.pack.modules
                if module_ir.contract == SOURCE_MAPPING_MODULE_VERSION
                for mapping in SourceMappingModuleV1.model_validate_json(module_ir.canonical_payload).mappings
                if mapping.subject_binding_id == subject_binding_id
            }
            if len(declared_types) != 1 or entity_type_id not in declared_types:
                raise RecordedSourceAdmissionError(
                    "subject binding and entity type must resolve exactly once in the committed Pack"
                )
            resolved_entity = resolve_entity_type_declaration(
                self.binding.prepared_binding,
                entity_type_id=entity_type_id,
            )
            if resolved_entity.entity_type_id != entity_type_id:
                raise RecordedSourceAdmissionError("subject binding resolved a different Pack entity type")
            return ResolvedSubjectBindingV1Alpha1(
                product_id=self.build.product_id,
                mode=IntelligenceResourceMode.PREPARED,
                activation_revision=self.binding.prepared_binding.reference,
                subject_binding_id=subject_binding_id,
                entity_type_id=entity_type_id,
                entity_ref=entity_ref,
            )
        except RecordedSourceAdmissionError:
            raise
        except Exception:
            raise RecordedSourceAdmissionError("subject binding failed exact committed Pack resolution") from None

    def _materials(
        self,
        materials: tuple[RecordedSourceMaterialV1Alpha1, ...],
    ) -> tuple[RecordedSourceMaterialV1Alpha1, ...]:
        if not materials:
            raise RecordedSourceAdmissionError("recorded source admission requires exact reviewed material")
        try:
            exact = tuple(
                RecordedSourceMaterialV1Alpha1.model_validate(material.model_dump(mode="python"))
                for material in materials
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise RecordedSourceAdmissionError("recorded source material failed exact revalidation") from exc
        ordered = tuple(sorted(exact, key=lambda item: (item.source_group_id, str(item.material_id))))
        actual_refs = tuple(
            (item.source_group_id, str(item.material_id), str(item.material_digest)) for item in ordered
        )
        authorized_refs = tuple(
            (item.source_group_id, item.material_id, item.material_digest)
            for item in self.build.request.recorded_source_refs
        )
        if actual_refs != authorized_refs:
            raise RecordedSourceAdmissionError(
                "recorded source set does not exactly match the reviewed group, material IDs, and digests"
            )
        if any(item.subject_binding.product_id != self.build.product_id for item in ordered):
            raise RecordedSourceAdmissionError("recorded material crossed the authorized build product")
        if any(item.subject_binding.activation_revision != self.binding.prepared_binding.reference for item in ordered):
            raise RecordedSourceAdmissionError("recorded material does not bind the exact committed activation")
        return ordered

    def _transaction_key(self) -> str:
        coordinates = tuple(
            (item.source_group_id, item.material_id, item.material_digest)
            for item in self.build.request.recorded_source_refs
        )
        return f"recorded_source_admission:{canonical_hash([self.build.build_id, coordinates])[:32]}"

    async def admit(self, materials: tuple[RecordedSourceMaterialV1Alpha1, ...]) -> RecordedSourceAdmission:
        exact = self._materials(materials)
        transaction_key = self._transaction_key()
        replay = await self._replay(transaction_key=transaction_key, expected=exact)
        if replay is not None:
            return replay

        admitted_at = self.build.authority_use.evaluated_at
        activation_head = _activation_head(self.binding)
        acquisitions: list[RecordedSourceAcquisitionReceiptV1Alpha1] = []
        snapshots: list[CanonicalSourceSnapshotV1Alpha1] = []
        observations: list[ObservationV1Alpha1] = []
        entities: list[EntitySnapshotV1Alpha1] = []
        for material in exact:
            acquisition = RecordedSourceAcquisitionReceiptV1Alpha1(
                product_id=self.build.product_id,
                actor_ref=self.build.actor_ref,
                build_id=self.build.build_id,
                build_request_digest=self.build.request_digest,
                build_authority_use=self.build.authority_use,
                activation_revision=self.binding.prepared_binding.reference,
                activation_head_precondition=activation_head,
                recorded_material_id=str(material.material_id),
                recorded_material_digest=str(material.material_digest),
                source_group_id=material.source_group_id,
                source_definition_ref=material.source_definition_ref,
                source_type_ref=material.source_type_ref,
                source_uri=material.source_uri,
                captured_payload_digest=material.captured_payload_digest,
                source_published_at=material.source_published_at,
                event_effective_at=material.event_effective_at,
                observed_at=material.observed_at,
                admitted_at=admitted_at,
            )
            snapshot = CanonicalSourceSnapshotV1Alpha1(
                source_definition_ref=material.source_definition_ref,
                source_type_ref=material.source_type_ref,
                source_uri=material.source_uri,
                captured_payload_json=material.captured_payload_json,
                captured_payload_digest=material.captured_payload_digest,
                source_published_at=material.source_published_at,
                event_effective_at=material.event_effective_at,
                observed_at=material.observed_at,
                ingested_at=admitted_at,
                locator=material.locator,
                acquisition_mode=SourceAcquisitionMode.RECORDED_REPLAY,
                acquisition_receipt_ref=str(acquisition.receipt_id),
                acquisition_receipt_digest=str(acquisition.receipt_digest),
            )
            try:
                mapped = interpret_prepared_source_mapping(
                    binding=self.binding.prepared_binding,
                    mapping_id=material.mapping_id,
                    source_snapshot=snapshot,
                    subject_binding=material.subject_binding,
                )
            except Exception:
                raise RecordedSourceAdmissionError("recorded material failed activation-bound source mapping") from None
            observation = mapped.observation
            entity = mapped.entity_snapshot
            if (
                observation.mode is not IntelligenceResourceMode.PREPARED
                or observation.acquisition_mode is not EvidenceAcquisitionMode.RECORDED_REPLAY
                or observation.acquisition_receipt_ref != acquisition.receipt_id
                or observation.acquisition_receipt_digest != acquisition.receipt_digest
                or entity.mode is not IntelligenceResourceMode.PREPARED
                or entity.activation_revision != observation.activation_revision
                or len(entity.lineage) != 1
                or entity.lineage[0].resource_id != observation.resource_id
                or entity.lineage[0].resource_digest != observation.resource_digest
                or entity.lineage[0].resource_as_of != observation.as_of
                or entity.lineage[0].resource_available_at != resource_available_at(observation)
            ):
                raise RecordedSourceAdmissionError(
                    "prepared mapping changed recorded acquisition truth or entity lineage"
                )
            acquisitions.append(acquisition)
            snapshots.append(snapshot)
            observations.append(observation)
            entities.append(entity)

        records_list: list[ImmutableRecordV1] = []
        for acquisition, snapshot, observation, entity in zip(
            acquisitions,
            snapshots,
            observations,
            entities,
            strict=True,
        ):
            base = len(records_list)
            records_list.extend(
                (
                    _record(
                        acquisition,
                        product_id=self.build.product_id,
                        kind=RECORDED_SOURCE_RECORD_KIND,
                        key=str(acquisition.receipt_id),
                        as_of=acquisition.observed_at,
                        available_at=admitted_at,
                        order=base,
                    ),
                    _record(
                        snapshot,
                        product_id=self.build.product_id,
                        kind=SOURCE_SNAPSHOT_RECORD_KIND,
                        key=str(snapshot.source_snapshot_ref),
                        as_of=snapshot.ingested_at,
                        available_at=admitted_at,
                        order=base + 1,
                    ),
                    _record(
                        observation,
                        product_id=self.build.product_id,
                        kind=IntelligenceRecordKind.OBSERVATION.value,
                        key=str(observation.resource_id),
                        as_of=observation.as_of,
                        available_at=admitted_at,
                        order=base + 2,
                    ),
                    _record(
                        entity,
                        product_id=self.build.product_id,
                        kind=IntelligenceRecordKind.ENTITY_SNAPSHOT.value,
                        key=str(entity.resource_id),
                        as_of=entity.as_of,
                        available_at=resource_available_at(entity),
                        order=base + 3,
                    ),
                )
            )
        request = AppendOnlyTransactionRequestV1(
            product_id=self.build.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=transaction_key,
            records=tuple(records_list),
            submitted_at=admitted_at,
            governed_state_preconditions=(
                activation_head,
                self.build.authority_use.state_head_precondition,
            ),
        )
        receipt = await self.store.append(request)
        if receipt != request.receipt():
            raise RecordedSourceAdmissionError("Core append receipt does not bind exact recorded admission")
        reopened = await self._replay(transaction_key=transaction_key, expected=exact, replayed=False)
        if reopened is None:
            raise RecordedSourceAdmissionError("recorded source admission did not reopen")
        return reopened

    async def _replay(
        self,
        *,
        transaction_key: str,
        expected: tuple[RecordedSourceMaterialV1Alpha1, ...],
        replayed: bool = True,
    ) -> RecordedSourceAdmission | None:
        receipt = await self.store.load_transaction_receipt(
            product_id=self.build.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=transaction_key,
        )
        if receipt is None:
            return None
        if len(receipt.records) != len(expected) * 4:
            raise RecordedSourceAdmissionError("recorded admission receipt lost exact material-set shape")
        loaded: list[ImmutableRecordV1] = []
        for reference in receipt.records:
            record = await self.store.load_record(
                reference.storage_id,
                product_id=self.build.product_id,
                record_space=PREPARED_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if record is None or record.reference() != reference:
                raise RecordedSourceAdmissionError("recorded admission has missing or changed immutable material")
            loaded.append(record)
        expected_kinds = (
            RECORDED_SOURCE_RECORD_KIND,
            SOURCE_SNAPSHOT_RECORD_KIND,
            IntelligenceRecordKind.OBSERVATION.value,
            IntelligenceRecordKind.ENTITY_SNAPSHOT.value,
        ) * len(expected)
        if tuple(item.record_kind for item in loaded) != expected_kinds:
            raise RecordedSourceAdmissionError("recorded admission record kinds changed")
        acquisitions: list[RecordedSourceAcquisitionReceiptV1Alpha1] = []
        snapshots: list[CanonicalSourceSnapshotV1Alpha1] = []
        observations: list[ObservationV1Alpha1] = []
        entities: list[EntitySnapshotV1Alpha1] = []
        for index, material in enumerate(expected):
            offset = index * 4
            try:
                acquisition = RecordedSourceAcquisitionReceiptV1Alpha1.model_validate(loaded[offset].payload)
                snapshot = CanonicalSourceSnapshotV1Alpha1.model_validate(loaded[offset + 1].payload)
                observation = ObservationV1Alpha1.model_validate(loaded[offset + 2].payload)
                entity = EntitySnapshotV1Alpha1.model_validate(loaded[offset + 3].payload)
            except (TypeError, ValueError) as exc:
                raise RecordedSourceAdmissionError("recorded admission payload failed exact replay") from exc
            if (
                acquisition.recorded_material_id != material.material_id
                or acquisition.recorded_material_digest != material.material_digest
                or acquisition.build_id != self.build.build_id
                or acquisition.build_request_digest != self.build.request_digest
                or acquisition.activation_revision != self.binding.prepared_binding.reference
                or snapshot.acquisition_receipt_ref != acquisition.receipt_id
                or snapshot.acquisition_receipt_digest != acquisition.receipt_digest
                or observation.source_ref != snapshot.source_snapshot_ref
                or observation.source_digest != snapshot.source_snapshot_digest
                or observation.acquisition_receipt_ref != acquisition.receipt_id
                or observation.acquisition_receipt_digest != acquisition.receipt_digest
                or observation.activation_revision != self.binding.prepared_binding.reference
                or observation.mode is not IntelligenceResourceMode.PREPARED
                or observation.acquisition_mode is not EvidenceAcquisitionMode.RECORDED_REPLAY
                or entity.product_id != self.build.product_id
                or entity.mode is not IntelligenceResourceMode.PREPARED
                or entity.activation_revision != self.binding.prepared_binding.reference
                or len(entity.lineage) != 1
                or entity.lineage[0].resource_id != observation.resource_id
                or entity.lineage[0].resource_digest != observation.resource_digest
                or entity.lineage[0].resource_as_of != observation.as_of
                or entity.lineage[0].resource_available_at != resource_available_at(observation)
                or loaded[offset + 3].available_at != resource_available_at(entity)
            ):
                raise RecordedSourceAdmissionError("recorded admission chain crossed exact governed material")
            acquisitions.append(acquisition)
            snapshots.append(snapshot)
            observations.append(observation)
            entities.append(entity)
        first_acquisition = acquisitions[0]
        expected_preconditions = tuple(
            sorted(
                (
                    first_acquisition.activation_head_precondition,
                    first_acquisition.build_authority_use.state_head_precondition,
                ),
                key=lambda item: (item.state_kind, item.product_id, item.state_id),
            )
        )
        if receipt.governed_state_preconditions != expected_preconditions:
            raise RecordedSourceAdmissionError("recorded admission lost activation or authority precondition")
        return RecordedSourceAdmission(
            acquisition_receipts=tuple(acquisitions),
            source_snapshots=tuple(snapshots),
            observations=tuple(observations),
            entity_snapshots=tuple(entities),
            transaction_receipt=receipt,
            replayed=replayed,
        )


__all__ = [
    "CONNECT_SOURCES_EFFECT",
    "CoreRecordedSourceAdmissionService",
    "IntelligenceBuildRecordedSourcePort",
    "RECORDED_SOURCE_ACQUISITION_RECEIPT_VERSION",
    "RECORDED_SOURCE_MATERIAL_VERSION",
    "RecordedSourceAcquisitionReceiptV1Alpha1",
    "RecordedSourceAdmission",
    "RecordedSourceAdmissionError",
    "RecordedSourceMaterialV1Alpha1",
]
