"""Governed LIVE Entity Snapshot -> Shift -> Signal -> attention bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, TypeAdapter

from ace.application.domain_activation import (
    CommittedActivationBinding,
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.application.live_source_ingress import LIVE_SOURCE_RECORD_SPACE
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.reasoning import (
    ContextBindingV1Alpha1,
    FrozenContextItemV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedActionAuthorizationRequestV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningError,
    GovernedReasoningOutcome,
    GovernedReasoningRequestV1Alpha1,
    GovernedReasoningService,
    ReasoningExecutionBindingV1Alpha1,
    ReceiptReferenceV1Alpha1,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.detection import CategoricalTransitionRuleV1
from ace.intelligence.contracts.ledger import (
    AttentionDisposition,
    AttentionDispositionReceiptV1Alpha1,
    AttentionSuppressionReason,
    IntelligenceRecordKind,
    IntelligenceRecordReferenceV1Alpha1,
    resource_available_at,
    resource_kind,
    resource_reference,
)
from ace.intelligence.contracts.live_bridge import (
    LiveDerivationReceiptV1Alpha1,
    LiveDerivationRequestV1Alpha1,
)
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import (
    BriefV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
    LineageReferenceV1Alpha1,
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
    ShiftV1Alpha1,
    SignalV1Alpha1,
)
from ace.intelligence.contracts.synthesis import (
    BriefSelectedContextBindingV1Alpha1,
    BriefSynthesisDraftV1Alpha1,
    BriefSynthesisReceiptV1Alpha1,
    BriefSynthesisRequestV1Alpha1,
)
from ace.intelligence.detection import (
    CategoricalTransitionDetectionError,
    NumericDeltaDetectionError,
    detect_live_categorical_shift,
    detect_live_numeric_shift,
    route_live_categorical_shift_as_signal,
    route_live_shift_as_signal,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBindingError,
    ResolvedBriefSynthesisPolicy,
    resolve_brief_synthesis_policy,
    resolve_detector_rule,
)
from ace.intelligence.routing import (
    SignalRoutingError,
    eligible_live_signal_routes,
)
from ace.intelligence.synthesis import (
    BriefDraftValidationError,
    assemble_canonical_brief,
)

_JSON_OBJECT = TypeAdapter(dict[str, object])


class GovernedActionAuthorizer(Protocol):
    async def authorize_action(
        self,
        request: GovernedActionAuthorizationRequestV1Alpha1,
    ) -> GovernedActionAuthorizationProjection: ...

    async def verify_action_reference(
        self,
        *,
        product_id: str,
        operation: str,
        subject_ref: str,
        subject_digest: str,
        expected: ReceiptReferenceV1Alpha1,
    ) -> GovernedActionAuthorizationProjection: ...


class LiveIntelligenceBridgeError(RuntimeError):
    """A governed LIVE derivation failed closed."""


class LiveIntelligenceBridgeReplayConflict(LiveIntelligenceBridgeError):
    """A stable LIVE derivation key already binds different request material."""


class LiveBriefSynthesisError(LiveIntelligenceBridgeError):
    """Governed LIVE Brief synthesis or replay failed closed."""


class LiveBriefSynthesisReplayConflict(LiveBriefSynthesisError):
    """A stable LIVE synthesis key already binds different request material."""


@dataclass(frozen=True, slots=True)
class LiveIntelligenceDerivationAdmission:
    """Exact atomic LIVE derivation and its Core authorization/append receipts."""

    shift: ShiftV1Alpha1
    signal: SignalV1Alpha1
    attention_receipt: AttentionDispositionReceiptV1Alpha1
    derivation_receipt: LiveDerivationReceiptV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool
    mode: IntelligenceResourceMode = IntelligenceResourceMode.LIVE


@dataclass(frozen=True, slots=True)
class LiveBriefAdmission:
    """One governed LIVE Brief and its semantic and Core append receipts."""

    brief: BriefV1Alpha1
    synthesis_receipt: BriefSynthesisReceiptV1Alpha1
    authorization: GovernedActionAuthorizationProjection
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool
    mode: IntelligenceResourceMode = IntelligenceResourceMode.LIVE


def _activation_precondition(
    binding: CommittedActivationBinding,
) -> GovernedStateHeadPreconditionV1Alpha1:
    revision = binding.prepared_binding.revision
    receipt = binding.commit_receipt
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=receipt.state_kind,
        product_id=revision.spec.product_id,
        state_id=str(revision.activation_id),
        sequence=revision.revision,
        revision_id=str(revision.revision_id),
        commit_receipt_id=str(receipt.receipt_id),
    )


def _activation_receipt(
    binding: CommittedActivationBinding,
) -> ReceiptReferenceV1Alpha1:
    return ReceiptReferenceV1Alpha1(
        receipt_id=str(binding.commit_receipt.receipt_id),
        receipt_digest=f"sha256:{binding.commit_receipt.receipt_hash}",
    )


def _transaction_key(derivation_key: str) -> str:
    return f"live_derivation:{canonical_hash(derivation_key)[:32]}"


def _record(
    value: BaseModel,
    *,
    product_id: str,
    record_kind: str,
    record_key: str,
    as_of,
    available_at,
    processing_order: int,
) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=product_id,
        record_space=LIVE_SOURCE_RECORD_SPACE,
        record_kind=record_kind,
        record_key=record_key,
        payload_contract=str(value.contract),
        payload=value.model_dump(mode="python"),
        as_of=as_of,
        available_at=available_at,
        processing_order=processing_order,
    )


class LiveIntelligenceBridgeService:
    """Interpret admitted LIVE snapshots under current Core-governed authority."""

    def __init__(
        self,
        *,
        activation_service: DomainActivationAdmissionService,
        pack: CompiledDomainPackV1,
        store: ImmutableRecordStore,
        authorizer: GovernedActionAuthorizer,
        operation_binding: GovernedOperationBindingV1Alpha1,
    ) -> None:
        self.activation_service = activation_service
        self.pack = CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
        self.store = store
        self.authorizer = authorizer
        self.operation_binding = GovernedOperationBindingV1Alpha1.model_validate(
            operation_binding.model_dump(mode="python")
        )

    async def _binding(
        self,
        request: LiveDerivationRequestV1Alpha1,
    ) -> CommittedActivationBinding:
        try:
            committed = await self.activation_service.reload(
                product_id=request.product_id,
                activation_key=request.activation_revision.activation_key,
            )
            if committed is None:
                raise LiveIntelligenceBridgeError("current committed activation is missing")
            binding = bind_committed_activation(pack=self.pack, committed=committed)
        except LiveIntelligenceBridgeError:
            raise
        except Exception:
            raise LiveIntelligenceBridgeError("current committed activation failed exact reload") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
            or binding.prepared_binding.revision.spec.product_id != request.product_id
        ):
            raise LiveIntelligenceBridgeError("LIVE derivation does not bind the current activation and Pack IR")
        return binding

    async def _load_snapshot(
        self,
        reference: IntelligenceRecordReferenceV1Alpha1,
    ) -> EntitySnapshotV1Alpha1:
        storage_id = immutable_record_storage_id(
            product_id=reference.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            record_kind=reference.resource_kind.value,
            record_key=reference.resource_id,
        )
        try:
            stored = await self.store.load_record(
                storage_id,
                product_id=reference.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                record_kind=reference.resource_kind.value,
            )
            if stored is None:
                raise LiveIntelligenceBridgeError("exact LIVE snapshot is missing")
            snapshot = EntitySnapshotV1Alpha1.model_validate(stored.payload)
        except LiveIntelligenceBridgeError:
            raise
        except Exception:
            raise LiveIntelligenceBridgeError("exact LIVE snapshot failed durable revalidation") from None
        if (
            snapshot.product_id != reference.product_id
            or snapshot.mode is not IntelligenceResourceMode.LIVE
            or snapshot.resource_id != reference.resource_id
            or snapshot.resource_digest != reference.resource_digest
            or snapshot.contract != reference.resource_contract
            or snapshot.as_of != reference.as_of
            or snapshot.projected_at > reference.available_at
            or stored.record_key != reference.resource_id
            or stored.payload_contract != reference.resource_contract
            or stored.as_of != reference.as_of
            or stored.available_at != reference.available_at
        ):
            raise LiveIntelligenceBridgeError("stored LIVE snapshot does not match exact public coordinates")
        return snapshot

    @staticmethod
    def _attention(
        *,
        request: LiveDerivationRequestV1Alpha1,
        signal: SignalV1Alpha1,
        shift: ShiftV1Alpha1,
        binding: CommittedActivationBinding,
    ) -> AttentionDispositionReceiptV1Alpha1:
        routes = eligible_live_signal_routes(
            binding=binding.prepared_binding,
            signal=signal,
        )
        common = {
            "product_id": request.product_id,
            "mode": IntelligenceResourceMode.LIVE,
            "activation_revision": request.activation_revision,
            "pack": request.pack,
            "signal": resource_reference(signal),
            "source_lineage": (resource_reference(shift),),
            "evaluated_at": request.attention_evaluated_at,
        }
        if routes:
            route = routes[0]
            return AttentionDispositionReceiptV1Alpha1(
                **common,
                disposition=AttentionDisposition.ROUTE,
                routing_rule_id=route.routing_rule_id,
                persona_ids=route.persona_ids,
                brief_template_id=route.brief_template_id,
            )
        return AttentionDispositionReceiptV1Alpha1(
            **common,
            disposition=AttentionDisposition.SUPPRESSED,
            suppression_reason=AttentionSuppressionReason.NO_ELIGIBLE_ROUTE,
        )

    async def _replay(
        self,
        request: LiveDerivationRequestV1Alpha1,
    ) -> LiveIntelligenceDerivationAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                transaction_key=_transaction_key(request.derivation_key),
            )
        except Exception:
            raise LiveIntelligenceBridgeError("LIVE derivation replay load failed closed") from None
        if transaction is None:
            return None
        expected_kinds = (
            IntelligenceRecordKind.SHIFT.value,
            IntelligenceRecordKind.SIGNAL.value,
            IntelligenceRecordKind.ATTENTION_DISPOSITION.value,
            "live_derivation_receipt",
        )
        if tuple(item.record_kind for item in transaction.records) != expected_kinds:
            raise LiveIntelligenceBridgeError("LIVE derivation replay has an invalid exact shape")
        loaded = []
        for reference in transaction.records:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if stored is None or stored.reference() != reference:
                raise LiveIntelligenceBridgeError("LIVE derivation replay material is missing or changed")
            loaded.append(stored)
        try:
            shift = ShiftV1Alpha1.model_validate(loaded[0].payload)
            signal = SignalV1Alpha1.model_validate(loaded[1].payload)
            attention = AttentionDispositionReceiptV1Alpha1.model_validate(loaded[2].payload)
            receipt = LiveDerivationReceiptV1Alpha1.model_validate(loaded[3].payload)
        except Exception:
            raise LiveIntelligenceBridgeError("LIVE derivation replay contracts changed") from None
        if receipt.request_id != request.request_id or receipt.request_digest != request.request_digest:
            raise LiveIntelligenceBridgeReplayConflict("LIVE derivation key already binds different request material")
        if (
            receipt.shift != resource_reference(shift)
            or receipt.signal != resource_reference(signal)
            or receipt.attention != attention.record_reference()
        ):
            raise LiveIntelligenceBridgeError("LIVE derivation receipt is cross-wired")
        try:
            authorization = await self.authorizer.verify_action_reference(
                product_id=request.product_id,
                operation="append_immutable_records",
                subject_ref=str(request.request_id),
                subject_digest=str(request.request_digest),
                expected=receipt.append_authorization,
            )
        except Exception:
            raise LiveIntelligenceBridgeError("LIVE derivation lost exact Core append authorization") from None
        if transaction.governed_state_preconditions != authorization.state_preconditions:
            raise LiveIntelligenceBridgeError("LIVE derivation replay crossed authorized governed-state heads")
        return LiveIntelligenceDerivationAdmission(
            shift=shift,
            signal=signal,
            attention_receipt=attention,
            derivation_receipt=receipt,
            authorization=authorization,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def derive(
        self,
        request: LiveDerivationRequestV1Alpha1,
    ) -> LiveIntelligenceDerivationAdmission:
        try:
            validated = LiveDerivationRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except Exception:
            raise LiveIntelligenceBridgeError("LIVE derivation request failed exact revalidation") from None
        replay = await self._replay(validated)
        if replay is not None:
            return replay
        binding = await self._binding(validated)
        baseline = await self._load_snapshot(validated.baseline)
        current = await self._load_snapshot(validated.current)
        try:
            rule = resolve_detector_rule(
                binding.prepared_binding,
                detector_id=validated.detector_id,
            )
            if isinstance(rule, CategoricalTransitionRuleV1):
                detect_live_shift = detect_live_categorical_shift
                route_live_signal = route_live_categorical_shift_as_signal
            else:
                detect_live_shift = detect_live_numeric_shift
                route_live_signal = route_live_shift_as_signal
            shift = detect_live_shift(
                binding=binding.prepared_binding,
                detector_id=validated.detector_id,
                baseline=baseline,
                current=current,
                detected_at=validated.detected_at,
            )
            if shift is None:
                raise LiveIntelligenceBridgeError("LIVE detector produced no material Shift for this bridge request")
            signal = route_live_signal(
                binding=binding.prepared_binding,
                detector_id=validated.detector_id,
                shift=shift,
                detected_at=validated.detected_at,
            )
            attention = self._attention(
                request=validated,
                signal=signal,
                shift=shift,
                binding=binding,
            )
        except LiveIntelligenceBridgeError:
            raise
        except (
            CategoricalTransitionDetectionError,
            NumericDeltaDetectionError,
            PreparedActivationBindingError,
            SignalRoutingError,
        ) as exc:
            raise LiveIntelligenceBridgeError("LIVE interpretation failed closed") from exc
        activation_precondition = _activation_precondition(binding)
        try:
            authorization = await self.authorizer.authorize_action(
                GovernedActionAuthorizationRequestV1Alpha1(
                    authorization_key=f"live_derivation:{validated.request_id}",
                    product_id=validated.product_id,
                    authenticated_context=validated.authenticated_context,
                    execution_binding=self.operation_binding,
                    operation="append_immutable_records",
                    subject_ref=str(validated.request_id),
                    subject_digest=str(validated.request_digest),
                    requested_at=validated.requested_at,
                    required_state_preconditions=(
                        activation_precondition,
                        self.operation_binding.state_head_precondition,
                    ),
                )
            )
        except Exception:
            raise LiveIntelligenceBridgeError("LIVE derivation append authorization failed closed") from None
        receipt = LiveDerivationReceiptV1Alpha1(
            product_id=validated.product_id,
            derivation_key=validated.derivation_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
            activation_revision=validated.activation_revision,
            activation_commit=_activation_receipt(binding),
            pack=validated.pack,
            detector_id=validated.detector_id,
            baseline=validated.baseline,
            current=validated.current,
            shift=resource_reference(shift),
            signal=resource_reference(signal),
            attention=attention.record_reference(),
            append_authorization=authorization.authorization_ref,
            created_at=authorization.authorized_at,
        )
        records = (
            _record(
                shift,
                product_id=validated.product_id,
                record_kind=resource_kind(shift).value,
                record_key=str(shift.resource_id),
                as_of=shift.as_of,
                available_at=resource_available_at(shift),
                processing_order=0,
            ),
            _record(
                signal,
                product_id=validated.product_id,
                record_kind=resource_kind(signal).value,
                record_key=str(signal.resource_id),
                as_of=signal.as_of,
                available_at=resource_available_at(signal),
                processing_order=1,
            ),
            _record(
                attention,
                product_id=validated.product_id,
                record_kind=IntelligenceRecordKind.ATTENTION_DISPOSITION.value,
                record_key=str(attention.receipt_id),
                as_of=attention.signal.as_of,
                available_at=attention.evaluated_at,
                processing_order=2,
            ),
            _record(
                receipt,
                product_id=validated.product_id,
                record_kind="live_derivation_receipt",
                record_key=str(receipt.receipt_id),
                as_of=receipt.created_at,
                available_at=receipt.created_at,
                processing_order=3,
            ),
        )
        append = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            transaction_key=_transaction_key(validated.derivation_key),
            records=records,
            submitted_at=authorization.authorized_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            transaction = await self.store.append(append)
        except Exception:
            replay = await self._replay(validated)
            if replay is not None:
                return replay
            raise LiveIntelligenceBridgeError(
                "authorized LIVE derivation append failed without durable result"
            ) from None
        if transaction != append.receipt():
            raise LiveIntelligenceBridgeError("Core append receipt does not bind the exact LIVE derivation")
        return LiveIntelligenceDerivationAdmission(
            shift=shift,
            signal=signal,
            attention_receipt=attention,
            derivation_receipt=receipt,
            authorization=authorization,
            transaction_receipt=transaction,
            replayed=False,
        )


def _brief_transaction_key(synthesis_key: str) -> str:
    return f"live_brief:{canonical_hash(synthesis_key)[:32]}"


def _trusted_instructions(policy: ResolvedBriefSynthesisPolicy) -> str:
    return canonical_json(
        {
            "brief_type": policy.template.brief_type,
            "claim_policy": policy.template.claim_policy,
            "instruction_authority": "trusted_application",
            "objective": policy.template.objective,
            "output_contract": "ace.intelligence.brief-synthesis-draft/v1alpha1",
            "personas": [
                {
                    "description": item.description,
                    "display_name": item.display_name,
                    "persona_id": item.persona_id,
                }
                for item in policy.personas
            ],
            "recommendation_required": policy.template.recommendation_required,
            "required_sections": list(policy.template.required_sections),
            "support_reference_policy": "exact_resource_ids_only",
        }
    )


class LiveBriefSynthesisService:
    """Synthesize one route-triggered LIVE Brief through Core reasoning."""

    def __init__(
        self,
        *,
        activation_service: DomainActivationAdmissionService,
        pack: CompiledDomainPackV1,
        store: ImmutableRecordStore,
        reasoning: GovernedReasoningService,
        execution_binding: ReasoningExecutionBindingV1Alpha1,
        append_binding: GovernedOperationBindingV1Alpha1,
    ) -> None:
        self.activation_service = activation_service
        self.pack = CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
        self.store = store
        self.reasoning = reasoning
        self.execution_binding = ReasoningExecutionBindingV1Alpha1.model_validate(
            execution_binding.model_dump(mode="python")
        )
        self.append_binding = GovernedOperationBindingV1Alpha1.model_validate(append_binding.model_dump(mode="python"))

    async def _binding(
        self,
        request: BriefSynthesisRequestV1Alpha1,
    ) -> CommittedActivationBinding:
        try:
            committed = await self.activation_service.reload(
                product_id=request.product_id,
                activation_key=request.activation_revision.activation_key,
            )
            if committed is None:
                raise LiveBriefSynthesisError("current committed activation is missing")
            binding = bind_committed_activation(pack=self.pack, committed=committed)
        except LiveBriefSynthesisError:
            raise
        except Exception:
            raise LiveBriefSynthesisError("current committed activation failed exact reload") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
            or binding.prepared_binding.revision.spec.product_id != request.product_id
        ):
            raise LiveBriefSynthesisError("LIVE Brief does not bind the current activation and Pack IR")
        return binding

    async def _stored(self, reference: IntelligenceRecordReferenceV1Alpha1):
        if reference.mode is not IntelligenceResourceMode.LIVE or reference.product_id == "":
            raise LiveBriefSynthesisError("exact context reference is outside LIVE scope")
        storage_id = immutable_record_storage_id(
            product_id=reference.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            record_kind=reference.resource_kind.value,
            record_key=reference.resource_id,
        )
        try:
            stored = await self.store.load_record(
                storage_id,
                product_id=reference.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                record_kind=reference.resource_kind.value,
            )
        except Exception:
            raise LiveBriefSynthesisError("exact LIVE context load failed closed") from None
        if stored is None or (
            stored.record_key != reference.resource_id
            or stored.payload_contract != reference.resource_contract
            or stored.as_of != reference.as_of
            or stored.available_at != reference.available_at
        ):
            raise LiveBriefSynthesisError("exact LIVE context is missing or changed")
        return stored

    async def _load_resource(
        self,
        reference: IntelligenceRecordReferenceV1Alpha1,
    ):
        stored = await self._stored(reference)
        models = {
            IntelligenceRecordKind.OBSERVATION: ObservationV1Alpha1,
            IntelligenceRecordKind.ENTITY_SNAPSHOT: EntitySnapshotV1Alpha1,
            IntelligenceRecordKind.SHIFT: ShiftV1Alpha1,
            IntelligenceRecordKind.SIGNAL: SignalV1Alpha1,
        }
        model = models.get(reference.resource_kind)
        if model is None:
            raise LiveBriefSynthesisError("record kind is not LIVE reasoning context")
        try:
            resource = model.model_validate(stored.payload)
        except Exception:
            raise LiveBriefSynthesisError("LIVE context contract changed") from None
        if resource_reference(resource) != reference:
            raise LiveBriefSynthesisError("LIVE context identity changed")
        return resource

    async def _lineage(
        self,
        edge: LineageReferenceV1Alpha1,
        *,
        product_id: str,
    ):
        kinds = {
            LineageResourceKind.OBSERVATION: (
                IntelligenceRecordKind.OBSERVATION,
                "ace.intelligence.observation/v1alpha1",
            ),
            LineageResourceKind.ENTITY_SNAPSHOT: (
                IntelligenceRecordKind.ENTITY_SNAPSHOT,
                "ace.intelligence.entity-snapshot/v1alpha1",
            ),
            LineageResourceKind.SHIFT: (
                IntelligenceRecordKind.SHIFT,
                "ace.intelligence.shift/v1alpha1",
            ),
        }
        resolved = kinds.get(edge.resource_kind)
        if resolved is None:
            raise LiveBriefSynthesisError("unsupported LIVE lineage kind")
        kind, contract = resolved
        storage_id = immutable_record_storage_id(
            product_id=product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            record_kind=kind.value,
            record_key=edge.resource_id,
        )
        stored = await self.store.load_record(
            storage_id,
            product_id=product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            record_kind=kind.value,
        )
        if stored is None or stored.payload_contract != contract:
            raise LiveBriefSynthesisError("exact LIVE lineage record is missing")
        model = {
            IntelligenceRecordKind.OBSERVATION: ObservationV1Alpha1,
            IntelligenceRecordKind.ENTITY_SNAPSHOT: EntitySnapshotV1Alpha1,
            IntelligenceRecordKind.SHIFT: ShiftV1Alpha1,
        }[kind]
        try:
            resource = model.model_validate(stored.payload)
        except Exception:
            raise LiveBriefSynthesisError("exact LIVE lineage contract changed") from None
        intrinsic = resource_reference(resource)
        if (
            intrinsic.resource_id != edge.resource_id
            or intrinsic.resource_digest != edge.resource_digest
            or intrinsic.as_of != edge.resource_as_of
            or intrinsic.available_at != edge.resource_available_at
            or stored.as_of != edge.resource_as_of
            or stored.available_at < edge.resource_available_at
        ):
            raise LiveBriefSynthesisError("exact LIVE lineage material is cross-wired")
        return resource

    async def _storage_reference(self, resource) -> IntelligenceRecordReferenceV1Alpha1:
        intrinsic = resource_reference(resource)
        storage_id = immutable_record_storage_id(
            product_id=intrinsic.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            record_kind=intrinsic.resource_kind.value,
            record_key=intrinsic.resource_id,
        )
        stored = await self.store.load_record(
            storage_id,
            product_id=intrinsic.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            record_kind=intrinsic.resource_kind.value,
        )
        if stored is None or (
            stored.record_key != intrinsic.resource_id
            or stored.payload_contract != intrinsic.resource_contract
            or stored.as_of != intrinsic.as_of
            or stored.available_at < intrinsic.available_at
        ):
            raise LiveBriefSynthesisError("LIVE resource lacks an exact admitted storage coordinate")
        return intrinsic.model_copy(update={"available_at": stored.available_at})

    async def _derivation(
        self,
        request: BriefSynthesisRequestV1Alpha1,
    ) -> tuple[
        SignalV1Alpha1,
        ShiftV1Alpha1,
        tuple[EntitySnapshotV1Alpha1, ...],
        tuple[ObservationV1Alpha1, ...],
        AttentionDispositionReceiptV1Alpha1,
        LiveDerivationReceiptV1Alpha1,
    ]:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                transaction_key=_transaction_key(request.derivation_key),
            )
        except Exception:
            raise LiveBriefSynthesisError("LIVE derivation replay failed closed") from None
        if transaction is None or tuple(item.record_kind for item in transaction.records) != (
            "shift",
            "signal",
            "attention_disposition",
            "live_derivation_receipt",
        ):
            raise LiveBriefSynthesisError("exact LIVE derivation is missing or malformed")
        records = []
        for reference in transaction.records:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if stored is None or stored.reference() != reference:
                raise LiveBriefSynthesisError("LIVE derivation material is missing or changed")
            records.append(stored)
        try:
            shift = ShiftV1Alpha1.model_validate(records[0].payload)
            signal = SignalV1Alpha1.model_validate(records[1].payload)
            attention = AttentionDispositionReceiptV1Alpha1.model_validate(records[2].payload)
            receipt = LiveDerivationReceiptV1Alpha1.model_validate(records[3].payload)
        except Exception:
            raise LiveBriefSynthesisError("LIVE derivation contract replay failed") from None
        if (
            attention.receipt_id != request.attention_receipt_id
            or attention.receipt_digest != request.attention_receipt_digest
            or attention.disposition is not AttentionDisposition.ROUTE
            or attention.brief_template_id is None
            or not attention.persona_ids
            or receipt.attention != attention.record_reference()
            or receipt.signal != resource_reference(signal)
            or receipt.shift != resource_reference(shift)
            or signal.as_of != request.brief_as_of
        ):
            raise LiveBriefSynthesisError("LIVE route receipt is missing or cross-wired")
        try:
            await self.reasoning.verify_action_reference(
                product_id=request.product_id,
                operation="append_immutable_records",
                subject_ref=receipt.request_id,
                subject_digest=receipt.request_digest,
                expected=receipt.append_authorization,
            )
        except GovernedReasoningError:
            raise LiveBriefSynthesisError("LIVE derivation lost its Core append authorization") from None
        if len(signal.lineage) != 1 or signal.lineage[0].resource_kind is not LineageResourceKind.SHIFT:
            raise LiveBriefSynthesisError("LIVE Signal must derive from one exact Shift")
        loaded_shift = await self._lineage(
            signal.lineage[0],
            product_id=request.product_id,
        )
        if loaded_shift != shift or not shift.lineage:
            raise LiveBriefSynthesisError("LIVE Signal and Shift lineage are not exact")
        entities = []
        observations = []
        for edge in shift.lineage:
            if (
                edge.resource_kind is not LineageResourceKind.ENTITY_SNAPSHOT
                or edge.relation is not LineageRelation.DERIVED_FROM
            ):
                raise LiveBriefSynthesisError("LIVE Shift lineage must name Entity Snapshots")
            entity = await self._lineage(edge, product_id=request.product_id)
            if not isinstance(entity, EntitySnapshotV1Alpha1) or not entity.lineage:
                raise LiveBriefSynthesisError("LIVE Entity Snapshot lineage is incomplete")
            entities.append(entity)
            for observation_edge in entity.lineage:
                if observation_edge.resource_kind is not LineageResourceKind.OBSERVATION:
                    raise LiveBriefSynthesisError("LIVE Entity Snapshot must derive from Observations")
                observation = await self._lineage(
                    observation_edge,
                    product_id=request.product_id,
                )
                if not isinstance(observation, ObservationV1Alpha1) or observation.lineage:
                    raise LiveBriefSynthesisError("LIVE Observation must terminate the resource lineage")
                observations.append(observation)
        closure = (signal, shift, *entities, *observations)
        if any(
            item.product_id != request.product_id
            or item.mode is not IntelligenceResourceMode.LIVE
            or item.activation_revision != request.activation_revision
            or item.as_of > request.brief_as_of
            or resource_reference(item).available_at > request.context_cutoff_at
            for item in closure
        ):
            raise LiveBriefSynthesisError("LIVE closure crossed mode, activation, or cutoff")
        if len({str(item.resource_id) for item in closure}) != len(closure):
            raise LiveBriefSynthesisError("LIVE closure contains duplicate identities")
        return signal, shift, tuple(entities), tuple(observations), attention, receipt

    async def _freeze(
        self,
        resource,
    ) -> tuple[FrozenContextItemV1Alpha1, IntelligenceRecordReferenceV1Alpha1]:
        reference = await self._storage_reference(resource)
        stored = await self._stored(reference)
        return (
            FrozenContextItemV1Alpha1(
                product_id=stored.product_id,
                record_space=stored.record_space,
                record_kind=stored.record_kind,
                record_key=stored.record_key,
                storage_id=str(stored.storage_id),
                material_digest=str(stored.material_hash),
                payload_contract=stored.payload_contract,
                as_of=stored.as_of,
                available_at=stored.available_at,
                content_json=canonical_json(_JSON_OBJECT.dump_python(stored.payload, mode="json")),
            ),
            reference,
        )

    async def _reasoning_material(
        self,
        *,
        request: BriefSynthesisRequestV1Alpha1,
        binding: CommittedActivationBinding,
        policy: ResolvedBriefSynthesisPolicy,
        closure: tuple,
    ):
        frozen_by_resource = {str(resource.resource_id): await self._freeze(resource) for resource in closure}
        frozen = tuple(frozen_by_resource[str(resource.resource_id)][0] for resource in closure)
        reasoning_request = GovernedReasoningRequestV1Alpha1(
            attempt_key=request.reasoning_attempt_key,
            product_id=request.product_id,
            authenticated_context=request.authenticated_context,
            artifact=self.execution_binding.artifact,
            configuration_ref=self.execution_binding.configuration_ref,
            authority=self.execution_binding.authority,
            grant_ref=self.execution_binding.grant_ref,
            instruction_json=_trusted_instructions(policy),
            context_items=frozen,
            cutoff_at=request.context_cutoff_at,
            requested_at=request.requested_at,
            required_state_preconditions=(
                _activation_precondition(binding),
                self.execution_binding.state_head_precondition,
            ),
        )
        selected = tuple(
            BriefSelectedContextBindingV1Alpha1(
                record=frozen_by_resource[str(resource.resource_id)][1],
                context=ContextBindingV1Alpha1.from_item(frozen_by_resource[str(resource.resource_id)][0]),
            )
            for resource in closure
        )
        return frozen, reasoning_request, selected

    @staticmethod
    def _receipt(
        *,
        request: BriefSynthesisRequestV1Alpha1,
        binding: CommittedActivationBinding,
        attention: AttentionDispositionReceiptV1Alpha1,
        policy: ResolvedBriefSynthesisPolicy,
        outcome: GovernedReasoningOutcome,
        assembly,
        authorization: GovernedActionAuthorizationProjection,
    ) -> BriefSynthesisReceiptV1Alpha1:
        brief = assembly.brief
        return BriefSynthesisReceiptV1Alpha1(
            product_id=request.product_id,
            mode=IntelligenceResourceMode.LIVE,
            synthesis_key=request.synthesis_key,
            reasoning_attempt_key=request.reasoning_attempt_key,
            request_id=str(request.request_id),
            request_digest=str(request.request_digest),
            reasoning_request_id=str(outcome.acceptance.request_id),
            reasoning_request_digest=str(outcome.acceptance.request_digest),
            activation_revision=request.activation_revision,
            activation_commit=_activation_receipt(binding),
            pack=request.pack,
            derivation_key=request.derivation_key,
            attention_receipt_id=str(attention.receipt_id),
            attention_receipt_digest=str(attention.receipt_digest),
            module_id=policy.module_id,
            module_digest=policy.module_digest,
            template_id=policy.template.template_id,
            template_digest=policy.template_digest,
            persona_ids=attention.persona_ids,
            required_section_ids=assembly.required_section_ids,
            actual_section_ids=assembly.actual_section_ids,
            section_claims=assembly.section_claims,
            recommendation_claim_id=assembly.recommendation_claim_id,
            claim_supports=assembly.claim_supports,
            selected_context=assembly.selected_context,
            write_intent_id=str(brief.resource_id),
            write_intent_digest=str(brief.resource_digest),
            write_authorization=authorization.authorization_ref,
            reasoning_terminal=ReceiptReferenceV1Alpha1(
                receipt_id=str(outcome.terminal.receipt_id),
                receipt_digest=str(outcome.terminal.receipt_digest),
            ),
            reasoning_result_id=str(outcome.result.result_id),
            reasoning_result_digest=str(outcome.result.result_digest),
            brief_id=str(brief.resource_id),
            brief_digest=str(brief.resource_digest),
            created_at=authorization.authorized_at,
        )

    async def _replay(
        self,
        request: BriefSynthesisRequestV1Alpha1,
        *,
        delivery_context=None,
    ) -> LiveBriefAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                transaction_key=_brief_transaction_key(request.synthesis_key),
            )
        except Exception:
            raise LiveBriefSynthesisError("LIVE Brief replay load failed closed") from None
        if transaction is None:
            return None
        if tuple(item.record_kind for item in transaction.records) != (
            "brief",
            "brief_synthesis_receipt",
        ):
            raise LiveBriefSynthesisError("LIVE Brief replay has an invalid exact shape")
        records = []
        for reference in transaction.records:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=request.product_id,
                record_space=LIVE_SOURCE_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
            if stored is None or stored.reference() != reference:
                raise LiveBriefSynthesisError("LIVE Brief replay material is missing or changed")
            records.append(stored)
        try:
            brief = BriefV1Alpha1.model_validate(records[0].payload)
            receipt = BriefSynthesisReceiptV1Alpha1.model_validate(records[1].payload)
        except Exception:
            raise LiveBriefSynthesisError("LIVE Brief replay contracts changed") from None
        if receipt.request_id != request.request_id or receipt.request_digest != request.request_digest:
            raise LiveBriefSynthesisReplayConflict("LIVE synthesis key already binds different request material")
        binding = await self._binding(request)
        signal, shift, entities, observations, attention, _ = await self._derivation(request)
        closure = (signal, shift, *entities, *observations)
        try:
            policy = resolve_brief_synthesis_policy(
                binding.prepared_binding,
                template_id=str(attention.brief_template_id),
                persona_ids=attention.persona_ids,
            )
        except PreparedActivationBindingError as exc:
            raise LiveBriefSynthesisError("LIVE synthesis policy is no longer exact") from exc
        frozen, _, selected = await self._reasoning_material(
            request=request,
            binding=binding,
            policy=policy,
            closure=closure,
        )
        try:
            outcome = await self.reasoning.execute_historical(
                product_id=request.product_id,
                attempt_key=request.reasoning_attempt_key,
                expected_request_id=receipt.reasoning_request_id,
                expected_request_digest=receipt.reasoning_request_digest,
                instruction_json=_trusted_instructions(policy),
                context_items=frozen,
                cutoff_at=request.context_cutoff_at,
                requested_at=request.requested_at,
                delivery_context=delivery_context or request.authenticated_context,
                delivery_binding=self.execution_binding,
            )
            draft = BriefSynthesisDraftV1Alpha1.model_validate_json(outcome.result.structured_json)
            assembly = assemble_canonical_brief(
                product_id=request.product_id,
                activation_revision=request.activation_revision,
                brief_as_of=request.brief_as_of,
                generated_at=brief.generated_at,
                draft=draft,
                policy=policy,
                closure=closure,
                observations=observations,
                selected_context=selected,
                mode=IntelligenceResourceMode.LIVE,
            )
            authorization = await self.reasoning.verify_action_reference(
                product_id=request.product_id,
                operation="append_immutable_records",
                subject_ref=receipt.write_intent_id,
                subject_digest=receipt.write_intent_digest,
                expected=receipt.write_authorization,
            )
        except (GovernedReasoningError, ValueError, BriefDraftValidationError) as exc:
            raise LiveBriefSynthesisError("LIVE Brief replay failed governed reconstruction") from exc
        expected_receipt = self._receipt(
            request=request,
            binding=binding,
            attention=attention,
            policy=policy,
            outcome=outcome,
            assembly=assembly,
            authorization=authorization,
        )
        if (
            assembly.brief != brief
            or expected_receipt != receipt
            or transaction.governed_state_preconditions != authorization.state_preconditions
        ):
            raise LiveBriefSynthesisError("LIVE Brief replay diverged from exact governed material")
        return LiveBriefAdmission(
            brief=brief,
            synthesis_receipt=receipt,
            authorization=authorization,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def synthesize(
        self,
        request: BriefSynthesisRequestV1Alpha1,
        *,
        delivery_context=None,
    ) -> LiveBriefAdmission:
        try:
            validated = BriefSynthesisRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except Exception:
            raise LiveBriefSynthesisError("LIVE Brief request failed exact revalidation") from None
        if validated.mode is not IntelligenceResourceMode.LIVE:
            raise LiveBriefSynthesisError("LIVE Brief service accepts only LIVE requests")
        replay = await self._replay(validated, delivery_context=delivery_context)
        if replay is not None:
            return replay
        binding = await self._binding(validated)
        signal, shift, entities, observations, attention, _ = await self._derivation(validated)
        closure = (signal, shift, *entities, *observations)
        try:
            policy = resolve_brief_synthesis_policy(
                binding.prepared_binding,
                template_id=str(attention.brief_template_id),
                persona_ids=attention.persona_ids,
            )
        except PreparedActivationBindingError as exc:
            raise LiveBriefSynthesisError("routed LIVE synthesis policy failed resolution") from exc
        frozen, reasoning_request, selected = await self._reasoning_material(
            request=validated,
            binding=binding,
            policy=policy,
            closure=closure,
        )
        try:
            outcome = await self.reasoning.execute(
                reasoning_request,
                delivery_context=delivery_context or validated.authenticated_context,
                delivery_binding=self.execution_binding,
            )
            if set(outcome.result.referenced_context_ids) != {str(item.context_id) for item in frozen}:
                raise LiveBriefSynthesisError("LIVE structured output did not attribute every selected context item")
            draft = BriefSynthesisDraftV1Alpha1.model_validate_json(outcome.result.structured_json)
            assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.brief_as_of,
                generated_at=outcome.result.completed_at,
                draft=draft,
                policy=policy,
                closure=closure,
                observations=observations,
                selected_context=selected,
                mode=IntelligenceResourceMode.LIVE,
            )
        except LiveBriefSynthesisError:
            raise
        except (GovernedReasoningError, ValueError, BriefDraftValidationError) as exc:
            raise LiveBriefSynthesisError("Core governed LIVE reasoning failed closed") from exc
        post_binding = await self._binding(validated)
        if _activation_precondition(post_binding) != _activation_precondition(binding):
            raise LiveBriefSynthesisError("activation changed during LIVE Brief synthesis")
        brief = assembly.brief
        try:
            authorization = await self.reasoning.authorize_action(
                GovernedActionAuthorizationRequestV1Alpha1(
                    authorization_key=f"live_brief:{validated.request_id}",
                    product_id=validated.product_id,
                    authenticated_context=validated.authenticated_context,
                    execution_binding=self.append_binding,
                    operation="append_immutable_records",
                    subject_ref=str(brief.resource_id),
                    subject_digest=str(brief.resource_digest),
                    requested_at=outcome.result.completed_at,
                    required_state_preconditions=(
                        _activation_precondition(post_binding),
                        self.append_binding.state_head_precondition,
                    ),
                )
            )
        except Exception:
            raise LiveBriefSynthesisError("LIVE Brief append authorization failed closed") from None
        receipt = self._receipt(
            request=validated,
            binding=binding,
            attention=attention,
            policy=policy,
            outcome=outcome,
            assembly=assembly,
            authorization=authorization,
        )
        records = (
            _record(
                brief,
                product_id=validated.product_id,
                record_kind="brief",
                record_key=str(brief.resource_id),
                as_of=brief.as_of,
                available_at=brief.generated_at,
                processing_order=0,
            ),
            _record(
                receipt,
                product_id=validated.product_id,
                record_kind="brief_synthesis_receipt",
                record_key=str(receipt.receipt_id),
                as_of=receipt.created_at,
                available_at=receipt.created_at,
                processing_order=1,
            ),
        )
        append = AppendOnlyTransactionRequestV1(
            product_id=validated.product_id,
            record_space=LIVE_SOURCE_RECORD_SPACE,
            transaction_key=_brief_transaction_key(validated.synthesis_key),
            records=records,
            submitted_at=authorization.authorized_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            transaction = await self.store.append(append)
        except Exception:
            replay = await self._replay(validated, delivery_context=delivery_context)
            if replay is not None:
                return replay
            raise LiveBriefSynthesisError("authorized LIVE Brief append failed without durable result") from None
        if transaction != append.receipt():
            raise LiveBriefSynthesisError("Core append receipt does not bind the LIVE Brief")
        return LiveBriefAdmission(
            brief=brief,
            synthesis_receipt=receipt,
            authorization=authorization,
            transaction_receipt=transaction,
            replayed=False,
        )


__all__ = [
    "LiveBriefAdmission",
    "LiveBriefSynthesisError",
    "LiveBriefSynthesisReplayConflict",
    "LiveBriefSynthesisService",
    "LiveIntelligenceBridgeError",
    "LiveIntelligenceBridgeReplayConflict",
    "LiveIntelligenceBridgeService",
    "LiveIntelligenceDerivationAdmission",
]
