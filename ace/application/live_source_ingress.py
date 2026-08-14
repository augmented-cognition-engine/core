"""Governed application service for one exact LIVE source admission."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Literal
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from ace.application.domain_activation import (
    DomainActivationAdmissionError,
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordReferenceV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import (
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    RuntimeUseResolver,
    capability_state_ref_for_artifact,
)
from ace.core.source import (
    CanonicalSourceSnapshotV1Alpha1,
    ResolvedSourceDefinitionV1Alpha1,
    SourceAcquisitionMode,
    SourceDefinitionResolver,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.activation import ActivationState
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import (
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    LineageResourceKind,
    ObservationV1Alpha1,
)
from ace.intelligence.contracts.source_acquisition import (
    CapturedSourceMaterialV1Alpha1,
    LiveSourceAdmissionReceiptV1Alpha1,
    LiveSourceIngressRecordKind,
    LiveSourceIngressRequestV1Alpha1,
    SourceAcquisitionReceiptV1Alpha1,
    SourceAdapterCaptureRequestV1Alpha1,
    SourceAdapterRegistry,
)
from ace.intelligence.contracts.source_mapping import ResolvedSubjectBindingV1Alpha1
from ace.intelligence.packs.runtime import resolve_source_mapping_policy
from ace.intelligence.source_mapping import interpret_live_source_mapping

LIVE_SOURCE_RECORD_SPACE = "live"
_JSON_OBJECT = TypeAdapter(dict[str, Any])


class LiveSourceIngressError(RuntimeError):
    """A LIVE acquisition or its exact admission failed closed."""


class LiveSourceIngressReplayConflict(LiveSourceIngressError):
    """One idempotency key already names different immutable intent."""


@dataclass(frozen=True, slots=True)
class LiveSourceAdmission:
    """Five reopened durable records and their enclosing Core append receipt."""

    acquisition_receipt: SourceAcquisitionReceiptV1Alpha1
    source_snapshot: CanonicalSourceSnapshotV1Alpha1
    observation: ObservationV1Alpha1
    entity_snapshot: EntitySnapshotV1Alpha1
    admission_receipt: LiveSourceAdmissionReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool

    @property
    def live_acquisition(self) -> Literal[True]:
        return True

    @property
    def admission_disposition(self) -> Literal["committed"]:
        return "committed"

    @property
    def reusable_authority(self) -> Literal[False]:
        return False


@dataclass(slots=True)
class _IdempotencyLockEntry:
    lock: asyncio.Lock
    users: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _revalidate_request(request: LiveSourceIngressRequestV1Alpha1) -> LiveSourceIngressRequestV1Alpha1:
    try:
        return LiveSourceIngressRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LiveSourceIngressError("LIVE ingress request failed exact revalidation") from exc


def _revalidate_pack(pack: CompiledDomainPackV1) -> CompiledDomainPackV1:
    try:
        return CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LiveSourceIngressError("compiled Pack IR failed exact revalidation") from exc


def _assert_authenticated(request: LiveSourceIngressRequestV1Alpha1, evaluated_at: datetime) -> None:
    context = request.authenticated_context
    if not (context.authenticated_at <= evaluated_at < context.expires_at):
        raise LiveSourceIngressError("runtime use fell outside the exact authenticated actor window")


def _activation_head(committed) -> GovernedStateHeadPreconditionV1Alpha1:
    revision = committed.revision
    receipt = committed.commit_receipt
    if revision.activation_id is None or revision.revision_id is None or receipt.receipt_id is None:
        raise LiveSourceIngressError("committed activation is missing exact head coordinates")
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=receipt.state_kind,
        product_id=revision.spec.product_id,
        state_id=revision.activation_id,
        sequence=revision.revision,
        revision_id=revision.revision_id,
        commit_receipt_id=receipt.receipt_id,
    )


def _assert_record_reference(
    record: ImmutableRecordV1,
    reference: ImmutableRecordReferenceV1,
) -> None:
    if record.reference() != reference:
        raise LiveSourceIngressError("stored LIVE record does not match its exact transaction reference")


def _payload_json(payload: dict[str, Any]) -> bytes:
    return _JSON_OBJECT.dump_json(payload)


def _record(
    payload,
    *,
    product_id: str,
    kind: LiveSourceIngressRecordKind,
    key: str,
    as_of: datetime,
    admitted_at: datetime,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=LIVE_SOURCE_RECORD_SPACE,
        record_kind=kind.value,
        record_key=key,
        payload_contract=payload.contract,
        payload=payload.model_dump(mode="python"),
        as_of=as_of,
        available_at=admitted_at,
        processing_order=processing_order,
    )


class LiveSourceIngressService:
    """Resolve, capture, recheck four heads, atomically append, and reopen."""

    def __init__(
        self,
        *,
        activation_service: DomainActivationAdmissionService,
        source_definitions: SourceDefinitionResolver,
        runtime_use: RuntimeUseResolver,
        adapters: SourceAdapterRegistry,
        store: ImmutableRecordStore,
        clock: Callable[[], datetime] = _now,
        max_payload_chars: int = 1_000_000,
    ) -> None:
        if max_payload_chars < 1 or max_payload_chars > 1_000_000:
            raise ValueError("max_payload_chars must be between 1 and 1,000,000")
        self.activation_service = activation_service
        self.source_definitions = source_definitions
        self.runtime_use = runtime_use
        self.adapters = adapters
        self.store = store
        self.clock = clock
        self.max_payload_chars = max_payload_chars
        self._idempotency_locks: dict[tuple[str, str], _IdempotencyLockEntry] = {}
        self._idempotency_lock_guard = asyncio.Lock()

    async def admit(
        self,
        *,
        request: LiveSourceIngressRequestV1Alpha1,
        pack: CompiledDomainPackV1,
    ) -> LiveSourceAdmission:
        validated_request = _revalidate_request(request)
        validated_pack = _revalidate_pack(pack)
        self._assert_request_pack(validated_request, validated_pack)

        replay = await self._replay(validated_request)
        if replay is not None:
            return replay

        lock_key = (validated_request.product_id, validated_request.idempotency_key)
        async with self._idempotency_lock_guard:
            entry = self._idempotency_locks.setdefault(
                lock_key,
                _IdempotencyLockEntry(lock=asyncio.Lock()),
            )
            entry.users += 1
        try:
            async with entry.lock:
                replay = await self._replay(validated_request)
                if replay is not None:
                    return replay
                return await self._acquire_and_admit(validated_request, validated_pack)
        finally:
            async with self._idempotency_lock_guard:
                entry.users -= 1
                if entry.users == 0 and self._idempotency_locks.get(lock_key) is entry:
                    self._idempotency_locks.pop(lock_key)

    async def replay(
        self,
        *,
        request: LiveSourceIngressRequestV1Alpha1,
    ) -> LiveSourceAdmission | None:
        return await self._replay(_revalidate_request(request))

    @staticmethod
    def _assert_request_pack(
        request: LiveSourceIngressRequestV1Alpha1,
        pack: CompiledDomainPackV1,
    ) -> None:
        if pack.compiled_pack_id != request.compiled_pack_id or pack.pack_digest != request.pack_digest:
            raise LiveSourceIngressError("request does not bind the exact supplied compiled Pack IR")

    async def _load_activation(
        self,
        request: LiveSourceIngressRequestV1Alpha1,
        pack: CompiledDomainPackV1,
    ):
        try:
            committed = await self.activation_service.reload(
                product_id=request.product_id,
                activation_key=request.activation_key,
            )
        except (AttributeError, TypeError, ValueError, DomainActivationAdmissionError) as exc:
            raise LiveSourceIngressError("current committed activation failed exact reload") from exc
        if committed is None or committed.revision.state is not ActivationState.ACTIVE:
            raise LiveSourceIngressError("LIVE ingress requires the current committed ACTIVE activation")
        try:
            binding = bind_committed_activation(pack=pack, committed=committed)
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("current committed activation does not bind the exact Pack IR") from exc
        return committed, binding, _activation_head(committed)

    async def _resolve_definition(
        self,
        request: LiveSourceIngressRequestV1Alpha1,
        *,
        resolved_at: datetime,
    ) -> ResolvedSourceDefinitionV1Alpha1:
        try:
            raw = await self.source_definitions.resolve_source_definition(
                product_id=request.product_id,
                source_definition_ref=request.source_definition_ref,
                resolved_at=resolved_at,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("source-definition resolver failed closed") from exc
        try:
            definition = ResolvedSourceDefinitionV1Alpha1.model_validate(raw.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("source definition failed exact Core revalidation") from exc
        if (
            definition.product_id != request.product_id
            or definition.source_definition_ref != request.source_definition_ref
        ):
            raise LiveSourceIngressError("source definition crossed the exact request scope")
        return definition

    @staticmethod
    def _mapping_bindings(binding, mapping):
        capability_requirements = {
            item.requirement_id: item for item in binding.prepared_binding.pack.capability_requirements
        }
        capability_bindings = {
            item.requirement_id: item for item in binding.prepared_binding.revision.spec.capability_bindings
        }
        authority_requests = {item.request_id: item for item in binding.prepared_binding.pack.authority_requests}
        authority_bindings = {
            item.request_id: item for item in binding.prepared_binding.revision.spec.authority_bindings
        }
        requirement = capability_requirements.get(mapping.capability_requirement_id)
        capability = capability_bindings.get(mapping.capability_requirement_id)
        authority_request = authority_requests.get(mapping.authority_request_id)
        authority = authority_bindings.get(mapping.authority_request_id)
        if (
            requirement is None
            or capability is None
            or authority_request is None
            or authority is None
            or capability.capability != requirement.capability
            or capability.contract != requirement.contract
            or authority.authority != authority_request.authority
        ):
            raise LiveSourceIngressError("activation does not exactly bind mapping capability and authority")
        if capability.configuration_ref is None or capability.secret_ref is not None:
            raise LiveSourceIngressError("alpha LIVE source capability requires exact secret-free configuration")
        artifact = CapabilityArtifactIdentityV1Alpha1(
            capability=capability.capability,
            contract=capability.contract,
            implementation_id=capability.implementation_id,
            implementation_version=capability.implementation_version,
            artifact_digest=capability.artifact_digest,
        )
        return capability, authority, artifact

    @staticmethod
    def _assert_definition_mapping(definition, mapping) -> None:
        if (
            definition.source_definition_ref != mapping.source_definition_ref
            or definition.source_type_ref != mapping.source_type_ref
            or definition.subject_binding_id != mapping.subject_binding_id
            or definition.entity_type_id != mapping.entity_type_id
            or urlsplit(definition.authorized_uri).scheme not in mapping.allowed_uri_schemes
        ):
            raise LiveSourceIngressError("source definition does not match the exact activation-bound mapping")

    async def _capability_use(
        self,
        request: LiveSourceIngressRequestV1Alpha1,
        *,
        artifact: CapabilityArtifactIdentityV1Alpha1,
        capability_state_ref: str,
        configuration_ref: str,
        evaluated_at: datetime,
    ) -> CapabilityUseReceiptV1Alpha1:
        try:
            raw = await self.runtime_use.resolve_capability_use(
                context=request.authenticated_context,
                use_subject_ref=str(request.request_id),
                use_subject_digest=str(request.request_digest),
                operation=request.operation,
                artifact=artifact,
                capability_state_ref=capability_state_ref,
                configuration_ref=configuration_ref,
                evaluated_at=evaluated_at,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("capability-use resolver failed closed") from exc
        try:
            receipt = CapabilityUseReceiptV1Alpha1.model_validate(raw.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("capability-use receipt failed exact Core revalidation") from exc
        if (
            receipt.product_id != request.product_id
            or receipt.actor_ref != request.authenticated_context.actor_ref
            or receipt.authenticated_context != request.authenticated_context
            or receipt.use_subject_ref != request.request_id
            or receipt.use_subject_digest != request.request_digest
            or receipt.operation != request.operation
            or receipt.artifact != artifact
            or receipt.capability_state_ref != capability_state_ref
            or receipt.configuration_ref != configuration_ref
            or receipt.evaluated_at != evaluated_at
            or receipt.resolved_at != evaluated_at
        ):
            raise LiveSourceIngressError("capability use did not resolve the exact actor request and artifact")
        return receipt

    async def _authority_use(
        self,
        request: LiveSourceIngressRequestV1Alpha1,
        *,
        authority: str,
        grant_ref: str,
        evaluated_at: datetime,
    ) -> AuthorityUseReceiptV1Alpha1:
        try:
            raw = await self.runtime_use.resolve_authority_use(
                context=request.authenticated_context,
                use_subject_ref=str(request.request_id),
                use_subject_digest=str(request.request_digest),
                operation=request.operation,
                authority=authority,
                grant_ref=grant_ref,
                evaluated_at=evaluated_at,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("authority-use resolver failed closed") from exc
        try:
            receipt = AuthorityUseReceiptV1Alpha1.model_validate(raw.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("authority-use receipt failed exact Core revalidation") from exc
        if (
            receipt.product_id != request.product_id
            or receipt.actor_ref != request.authenticated_context.actor_ref
            or receipt.authenticated_context != request.authenticated_context
            or receipt.use_subject_ref != request.request_id
            or receipt.use_subject_digest != request.request_digest
            or receipt.operation != request.operation
            or receipt.authority != authority
            or receipt.grant_ref != grant_ref
            or receipt.evaluated_at != evaluated_at
            or (receipt.expires_at is not None and receipt.expires_at <= evaluated_at)
        ):
            raise LiveSourceIngressError("authority use did not resolve the exact actor request and grant")
        return receipt

    async def _acquire_and_admit(
        self,
        request: LiveSourceIngressRequestV1Alpha1,
        pack: CompiledDomainPackV1,
    ) -> LiveSourceAdmission:
        started_at = self.clock()
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise LiveSourceIngressError("service clock must return a timezone-aware value")
        started_at = started_at.astimezone(UTC)
        if request.requested_at > started_at:
            raise LiveSourceIngressError("acquisition cannot start before the exact ingress request")
        _assert_authenticated(request, started_at)

        committed, binding, activation_head = await self._load_activation(request, pack)
        try:
            resolved_mapping = resolve_source_mapping_policy(
                binding.prepared_binding,
                mapping_id=request.mapping_id,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("mapping did not resolve from the exact activation-bound Pack IR") from exc
        mapping = resolved_mapping.rule
        capability_binding, authority_binding, artifact = self._mapping_bindings(binding, mapping)
        definition = await self._resolve_definition(request, resolved_at=started_at)
        self._assert_definition_mapping(definition, mapping)
        if definition.configuration_ref != capability_binding.configuration_ref:
            raise LiveSourceIngressError("source definition and activation name different exact configurations")
        capability_state_ref = capability_state_ref_for_artifact(artifact)

        capability_use = await self._capability_use(
            request,
            artifact=artifact,
            capability_state_ref=capability_state_ref,
            configuration_ref=definition.configuration_ref,
            evaluated_at=started_at,
        )
        authority_use = await self._authority_use(
            request,
            authority=authority_binding.authority,
            grant_ref=authority_binding.grant_ref,
            evaluated_at=started_at,
        )

        adapter = self.adapters.resolve_source_adapter(artifact=artifact)
        if adapter is None:
            raise LiveSourceIngressError("exact installed source adapter artifact is unavailable")
        try:
            installed_identity = CapabilityArtifactIdentityV1Alpha1.model_validate(
                adapter.artifact_identity.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("installed source adapter lacks exact artifact identity") from exc
        if installed_identity != artifact:
            raise LiveSourceIngressError("host registry returned a different source adapter artifact")

        capture_request = SourceAdapterCaptureRequestV1Alpha1(
            product_id=request.product_id,
            authenticated_context=request.authenticated_context,
            use_subject_ref=str(request.request_id),
            use_subject_digest=str(request.request_digest),
            operation=request.operation,
            source_definition_ref=definition.source_definition_ref,
            source_type_ref=definition.source_type_ref,
            requested_uri=definition.authorized_uri,
            adapter_artifact=artifact,
            configuration_ref=definition.configuration_ref,
            configuration_digest=definition.configuration_digest,
            started_at=started_at,
            max_payload_chars=self.max_payload_chars,
        )
        try:
            raw_capture = await adapter.capture(capture_request)
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("source adapter capture failed closed") from exc
        try:
            capture = CapturedSourceMaterialV1Alpha1.model_validate(raw_capture.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise LiveSourceIngressError("source adapter result failed exact revalidation") from exc
        if (
            capture.capture_request_ref != capture_request.request_id
            or capture.capture_request_digest != capture_request.request_digest
            or capture.source_type_ref != definition.source_type_ref
            or capture.requested_uri != definition.authorized_uri
            or capture.effective_uri != definition.authorized_uri
            or len(capture.captured_payload_json) > capture_request.max_payload_chars
            or capture.captured_at < started_at
            or capture.captured_at >= request.authenticated_context.expires_at
        ):
            raise LiveSourceIngressError("source adapter result did not bind the exact bounded request")

        acquisition = SourceAcquisitionReceiptV1Alpha1(
            product_id=request.product_id,
            actor_ref=request.authenticated_context.actor_ref,
            use_subject_ref=str(request.request_id),
            use_subject_digest=str(request.request_digest),
            operation=request.operation,
            source_definition_ref=definition.source_definition_ref,
            source_type_ref=definition.source_type_ref,
            source_definition_head_precondition=definition.state_head_precondition,
            configuration_ref=definition.configuration_ref,
            configuration_digest=definition.configuration_digest,
            requested_uri=capture.requested_uri,
            effective_uri=capture.effective_uri,
            adapter_artifact=artifact,
            capability_use=capability_use,
            authority_use=authority_use,
            captured_payload_digest=capture.captured_payload_digest,
            resolved_ip_addresses=capture.resolved_ip_addresses,
            dns_rebinding_protection_applied=capture.dns_rebinding_protection_applied,
            locator=capture.locator,
            source_published_at=capture.source_published_at,
            event_effective_at=capture.event_effective_at,
            observed_at=capture.observed_at,
            captured_at=capture.captured_at,
        )

        rechecked_at = self.clock()
        if rechecked_at.tzinfo is None or rechecked_at.utcoffset() is None:
            raise LiveSourceIngressError("service clock must return a timezone-aware value")
        rechecked_at = rechecked_at.astimezone(UTC)
        if rechecked_at < capture.captured_at:
            raise LiveSourceIngressError("admission recheck cannot precede exact source capture")
        _assert_authenticated(request, rechecked_at)
        if authority_use.expires_at is not None and authority_use.expires_at <= rechecked_at:
            raise LiveSourceIngressError("authority grant expired before source admission recheck")

        snapshot = CanonicalSourceSnapshotV1Alpha1(
            source_definition_ref=definition.source_definition_ref,
            source_type_ref=definition.source_type_ref,
            source_uri=definition.authorized_uri,
            captured_payload_json=capture.captured_payload_json,
            captured_payload_digest=capture.captured_payload_digest,
            source_published_at=capture.source_published_at,
            event_effective_at=capture.event_effective_at,
            observed_at=capture.observed_at,
            ingested_at=rechecked_at,
            locator=capture.locator,
            acquisition_mode=SourceAcquisitionMode.LIVE,
            acquisition_receipt_ref=str(acquisition.receipt_id),
            acquisition_receipt_digest=str(acquisition.receipt_digest),
        )
        subject = ResolvedSubjectBindingV1Alpha1(
            product_id=request.product_id,
            mode=IntelligenceResourceMode.LIVE,
            activation_revision=binding.prepared_binding.reference,
            subject_binding_id=definition.subject_binding_id,
            entity_type_id=definition.entity_type_id,
            entity_ref=definition.entity_ref,
        )
        mapped = interpret_live_source_mapping(
            binding=binding.prepared_binding,
            mapping_id=request.mapping_id,
            source_snapshot=snapshot,
            subject_binding=subject,
        )

        final_committed, _, final_activation_head = await self._load_activation(request, pack)
        final_definition = await self._resolve_definition(request, resolved_at=rechecked_at)
        final_capability = await self._capability_use(
            request,
            artifact=artifact,
            capability_state_ref=capability_state_ref,
            configuration_ref=definition.configuration_ref,
            evaluated_at=rechecked_at,
        )
        final_authority = await self._authority_use(
            request,
            authority=authority_binding.authority,
            grant_ref=authority_binding.grant_ref,
            evaluated_at=rechecked_at,
        )
        if (
            final_committed != committed
            or final_activation_head != activation_head
            or final_definition != definition
            or final_capability.state_head_precondition != capability_use.state_head_precondition
            or final_capability.artifact != capability_use.artifact
            or final_capability.configuration_ref != capability_use.configuration_ref
            or final_authority.state_head_precondition != authority_use.state_head_precondition
            or final_authority.grant_ref != authority_use.grant_ref
            or final_authority.grant_hash != authority_use.grant_hash
            or final_authority.expires_at != authority_use.expires_at
        ):
            raise LiveSourceIngressError("governed runtime material changed during source acquisition")

        admitted_at = self.clock()
        if admitted_at.tzinfo is None or admitted_at.utcoffset() is None:
            raise LiveSourceIngressError("service clock must return a timezone-aware value")
        admitted_at = admitted_at.astimezone(UTC)
        if admitted_at < rechecked_at:
            raise LiveSourceIngressError("commit-time validation cannot precede final runtime recheck")
        _assert_authenticated(request, admitted_at)
        if (authority_use.expires_at is not None and authority_use.expires_at <= admitted_at) or (
            final_authority.expires_at is not None and final_authority.expires_at <= admitted_at
        ):
            raise LiveSourceIngressError("authority grant expired before atomic source admission")

        source_mapping = mapped.observation.source_mapping
        if source_mapping is None:
            raise LiveSourceIngressError("LIVE Observation is missing exact source-mapping provenance")
        admission = LiveSourceAdmissionReceiptV1Alpha1(
            product_id=request.product_id,
            actor_ref=request.authenticated_context.actor_ref,
            use_subject_ref=str(request.request_id),
            use_subject_digest=str(request.request_digest),
            operation=request.operation,
            activation_revision=binding.prepared_binding.reference,
            activation_head_precondition=activation_head,
            source_definition_head_precondition=definition.state_head_precondition,
            source_mapping=source_mapping,
            acquisition_receipt_ref=str(acquisition.receipt_id),
            acquisition_receipt_digest=str(acquisition.receipt_digest),
            source_snapshot_ref=str(snapshot.source_snapshot_ref),
            source_snapshot_digest=str(snapshot.source_snapshot_digest),
            capability_use_receipt_ref=str(capability_use.receipt_id),
            capability_use_receipt_digest=str(capability_use.receipt_digest),
            authority_use_receipt_ref=str(authority_use.receipt_id),
            authority_use_receipt_digest=str(authority_use.receipt_digest),
            observation_ref=str(mapped.observation.resource_id),
            observation_digest=str(mapped.observation.resource_digest),
            entity_snapshot_ref=str(mapped.entity_snapshot.resource_id),
            entity_snapshot_digest=str(mapped.entity_snapshot.resource_digest),
            admitted_at=admitted_at,
        )
        records = (
            _record(
                acquisition,
                product_id=request.product_id,
                kind=LiveSourceIngressRecordKind.SOURCE_ACQUISITION,
                key=str(acquisition.receipt_id),
                as_of=acquisition.captured_at,
                admitted_at=admitted_at,
                processing_order=0,
            ),
            _record(
                snapshot,
                product_id=request.product_id,
                kind=LiveSourceIngressRecordKind.SOURCE_SNAPSHOT,
                key=str(snapshot.source_snapshot_ref),
                as_of=snapshot.as_of,
                admitted_at=admitted_at,
                processing_order=1,
            ),
            _record(
                mapped.observation,
                product_id=request.product_id,
                kind=LiveSourceIngressRecordKind.OBSERVATION,
                key=str(mapped.observation.resource_id),
                as_of=mapped.observation.as_of,
                admitted_at=admitted_at,
                processing_order=2,
            ),
            _record(
                mapped.entity_snapshot,
                product_id=request.product_id,
                kind=LiveSourceIngressRecordKind.ENTITY_SNAPSHOT,
                key=str(mapped.entity_snapshot.resource_id),
                as_of=mapped.entity_snapshot.as_of,
                admitted_at=admitted_at,
                processing_order=3,
            ),
            _record(
                admission,
                product_id=request.product_id,
                kind=LiveSourceIngressRecordKind.SOURCE_ADMISSION,
                key=str(admission.receipt_id),
                as_of=admission.admitted_at,
                admitted_at=admitted_at,
                processing_order=4,
            ),
        )
        transaction_request = AppendOnlyTransactionRequestV1(
            product_id=request.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            transaction_key=request.idempotency_key,
            records=records,
            submitted_at=admitted_at,
            governed_state_preconditions=(
                activation_head,
                capability_use.state_head_precondition,
                authority_use.state_head_precondition,
                definition.state_head_precondition,
            ),
        )
        transaction_receipt = await self.store.append(transaction_request)
        if transaction_receipt != transaction_request.receipt():
            raise LiveSourceIngressError("Core append receipt does not bind the exact LIVE admission")
        reopened = await self._replay_receipt(
            request=request,
            receipt=transaction_receipt,
            replayed=False,
        )
        if (
            reopened.acquisition_receipt != acquisition
            or reopened.source_snapshot != snapshot
            or reopened.observation != mapped.observation
            or reopened.entity_snapshot != mapped.entity_snapshot
            or reopened.admission_receipt != admission
        ):
            raise LiveSourceIngressError("reopened LIVE admission changed exact persisted material")
        return reopened

    async def _replay(
        self,
        request: LiveSourceIngressRequestV1Alpha1,
    ) -> LiveSourceAdmission | None:
        receipt = await self.store.load_transaction_receipt(
            product_id=request.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            transaction_key=request.idempotency_key,
        )
        if receipt is None:
            return None
        return await self._replay_receipt(request=request, receipt=receipt, replayed=True)

    async def _replay_receipt(
        self,
        *,
        request: LiveSourceIngressRequestV1Alpha1,
        receipt: AppendOnlyTransactionReceiptV1,
        replayed: bool,
    ) -> LiveSourceAdmission:
        if receipt.product_id != request.product_id or receipt.record_space != LIVE_SOURCE_RECORD_SPACE:
            raise LiveSourceIngressError("LIVE transaction receipt crossed exact ledger scope")
        expected_kinds = tuple(item.value for item in LiveSourceIngressRecordKind)
        if (
            len(receipt.records) != 5
            or tuple(item.processing_order for item in receipt.records) != tuple(range(5))
            or tuple(item.record_kind for item in receipt.records) != expected_kinds
        ):
            raise LiveSourceIngressError("LIVE transaction must contain exactly the five ordered admission records")

        loaded: list[ImmutableRecordV1] = []
        for reference in receipt.records:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if stored is None:
                raise LiveSourceIngressError("LIVE transaction references a missing immutable record")
            _assert_record_reference(stored, reference)
            loaded.append(stored)
        try:
            acquisition = SourceAcquisitionReceiptV1Alpha1.model_validate_json(_payload_json(loaded[0].payload))
            snapshot = CanonicalSourceSnapshotV1Alpha1.model_validate_json(_payload_json(loaded[1].payload))
            observation = ObservationV1Alpha1.model_validate_json(_payload_json(loaded[2].payload))
            entity = EntitySnapshotV1Alpha1.model_validate_json(_payload_json(loaded[3].payload))
            admission = LiveSourceAdmissionReceiptV1Alpha1.model_validate_json(_payload_json(loaded[4].payload))
        except (TypeError, ValueError) as exc:
            raise LiveSourceIngressError("persisted LIVE contract failed exact replay validation") from exc

        if admission.use_subject_ref != request.request_id or admission.use_subject_digest != request.request_digest:
            raise LiveSourceIngressReplayConflict("idempotency key already binds a different LIVE ingress request")
        if (
            admission.operation != request.operation
            or admission.product_id != request.product_id
            or admission.actor_ref != request.authenticated_context.actor_ref
            or admission.source_mapping.compiled_pack_id != request.compiled_pack_id
            or admission.source_mapping.pack_digest != request.pack_digest
            or acquisition.source_definition_ref != request.source_definition_ref
            or acquisition.source_definition_head_precondition != admission.source_definition_head_precondition
            or acquisition.use_subject_ref != request.request_id
            or acquisition.use_subject_digest != request.request_digest
            or acquisition.capability_use.authenticated_context != request.authenticated_context
            or acquisition.authority_use.authenticated_context != request.authenticated_context
            or snapshot.acquisition_mode is not SourceAcquisitionMode.LIVE
            or snapshot.acquisition_receipt_ref != acquisition.receipt_id
            or snapshot.acquisition_receipt_digest != acquisition.receipt_digest
            or observation.mode is not IntelligenceResourceMode.LIVE
            or observation.source_ref != snapshot.source_snapshot_ref
            or observation.source_digest != snapshot.source_snapshot_digest
            or observation.acquisition_receipt_ref != acquisition.receipt_id
            or observation.acquisition_receipt_digest != acquisition.receipt_digest
            or entity.mode is not IntelligenceResourceMode.LIVE
            or admission.acquisition_receipt_ref != acquisition.receipt_id
            or admission.acquisition_receipt_digest != acquisition.receipt_digest
            or admission.source_snapshot_ref != snapshot.source_snapshot_ref
            or admission.source_snapshot_digest != snapshot.source_snapshot_digest
            or admission.capability_use_receipt_ref != acquisition.capability_use.receipt_id
            or admission.capability_use_receipt_digest != acquisition.capability_use.receipt_digest
            or admission.authority_use_receipt_ref != acquisition.authority_use.receipt_id
            or admission.authority_use_receipt_digest != acquisition.authority_use.receipt_digest
            or admission.observation_ref != observation.resource_id
            or admission.observation_digest != observation.resource_digest
            or admission.entity_snapshot_ref != entity.resource_id
            or admission.entity_snapshot_digest != entity.resource_digest
        ):
            raise LiveSourceIngressError("persisted LIVE records do not bind one exact admission chain")
        observation_lineage = [item for item in entity.lineage if item.resource_kind is LineageResourceKind.OBSERVATION]
        if len(observation_lineage) != 1 or (
            observation_lineage[0].resource_id != observation.resource_id
            or observation_lineage[0].resource_digest != observation.resource_digest
        ):
            raise LiveSourceIngressError("persisted Entity Snapshot lost exact Observation lineage")
        expected_preconditions = tuple(
            sorted(
                (
                    admission.activation_head_precondition,
                    admission.source_definition_head_precondition,
                    acquisition.capability_use.state_head_precondition,
                    acquisition.authority_use.state_head_precondition,
                ),
                key=lambda item: (
                    item.state_kind,
                    item.product_id,
                    item.state_id,
                    item.sequence,
                    item.revision_id,
                    item.commit_receipt_id,
                ),
            )
        )
        if receipt.governed_state_preconditions != expected_preconditions:
            raise LiveSourceIngressError("transaction receipt lost one of four exact governed heads")
        expected_keys = (
            acquisition.receipt_id,
            snapshot.source_snapshot_ref,
            observation.resource_id,
            entity.resource_id,
            admission.receipt_id,
        )
        if tuple(item.record_key for item in loaded) != expected_keys:
            raise LiveSourceIngressError("persisted LIVE record envelopes do not match payload identities")
        if any(item.available_at != admission.admitted_at for item in loaded):
            raise LiveSourceIngressError("LIVE records do not share one atomic admission availability time")
        return LiveSourceAdmission(
            acquisition_receipt=acquisition,
            source_snapshot=snapshot,
            observation=observation,
            entity_snapshot=entity,
            admission_receipt=admission,
            transaction_receipt=receipt,
            replayed=replayed,
        )


__all__ = [
    "LIVE_SOURCE_RECORD_SPACE",
    "LiveSourceAdmission",
    "LiveSourceIngressError",
    "LiveSourceIngressReplayConflict",
    "LiveSourceIngressService",
]
