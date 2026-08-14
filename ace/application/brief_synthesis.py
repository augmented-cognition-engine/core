"""Route-triggered PREPARED Brief synthesis across Core and Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal

from ace.application.domain_activation import (
    CommittedActivationBinding,
    DomainActivationAdmissionError,
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.application.intelligence_ledger import (
    PREPARED_RECORD_SPACE,
    PreparedIntelligenceAdmissionError,
    PreparedIntelligenceLedgerService,
)
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
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
    immutable_record_storage_id,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.ledger import (
    AttentionDisposition,
    AttentionDispositionReceiptV1Alpha1,
    IntelligenceRecordKind,
    resource_reference,
)
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import (
    BriefV1Alpha1,
    EntitySnapshotV1Alpha1,
    IntelligenceResourceMode,
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
    PreparedBriefAppendIntentV1Alpha1,
    PreparedBriefAppendRecordRecipeV1Alpha1,
    PreparedBriefAppendV1Alpha1,
)
from ace.intelligence.packs.runtime import (
    CompiledPackArtifactResolver,
    PreparedActivationBindingError,
    ResolvedBriefSynthesisPolicy,
    resolve_brief_synthesis_policy,
)
from ace.intelligence.synthesis import (
    BriefDraftValidationError,
    assemble_canonical_brief,
)


class BriefSynthesisError(RuntimeError):
    """PREPARED Brief synthesis or replay failed closed."""


class BriefSynthesisReplayConflict(BriefSynthesisError):
    """A stable synthesis key already binds different request material."""


class _SinglePackResolver:
    """Backward-compatible exact resolver for the one supplied immutable Pack."""

    def __init__(self, pack: CompiledDomainPackV1) -> None:
        self.pack = pack

    async def load_exact(
        self,
        *,
        reference: CompiledPackRefV1,
    ) -> CompiledDomainPackV1 | None:
        if (
            self.pack.compiled_pack_id != reference.compiled_pack_id
            or self.pack.pack_digest != reference.pack_digest
            or self.pack.metadata.pack_id != reference.pack_id
            or self.pack.metadata.version != reference.pack_version
        ):
            return None
        return CompiledDomainPackV1.model_validate(self.pack.model_dump(mode="python"))


@dataclass(frozen=True, slots=True)
class PreparedBriefAppendAdmission:
    """Exact replayable second-phase Brief plus synthesis receipt."""

    brief: BriefV1Alpha1
    synthesis_receipt: BriefSynthesisReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise BriefSynthesisError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _brief_transaction_key(synthesis_key: str) -> str:
    return f"brief_synthesis:{canonical_hash([synthesis_key, 'brief'])[:32]}"


def _brief_record(brief: BriefV1Alpha1) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=brief.product_id,
        record_space=PREPARED_RECORD_SPACE,
        record_kind=IntelligenceRecordKind.BRIEF.value,
        record_key=str(brief.resource_id),
        payload_contract=brief.contract,
        payload=brief.model_dump(mode="python"),
        as_of=brief.as_of,
        available_at=brief.generated_at,
        processing_order=0,
    )


def _synthesis_record(receipt: BriefSynthesisReceiptV1Alpha1) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=receipt.product_id,
        record_space=PREPARED_RECORD_SPACE,
        record_kind="brief_synthesis_receipt",
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=receipt.created_at,
        available_at=receipt.created_at,
        processing_order=1,
    )


class _PreparedBriefAppendService:
    """Additive second-phase append service; it never reuses a P1B derivation key."""

    def __init__(self, *, product_id: str, store: ImmutableRecordStore) -> None:
        self.product_id = product_id
        self.store = store

    async def replay(
        self,
        *,
        synthesis_key: str,
        request_id: str,
        request_digest: str,
    ) -> PreparedBriefAppendAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_brief_transaction_key(synthesis_key),
            )
        except Exception:
            raise BriefSynthesisError("second-phase transaction load failed closed") from None
        if transaction is None:
            return None
        if len(transaction.records) != 2 or tuple(item.record_kind for item in transaction.records) != (
            IntelligenceRecordKind.BRIEF.value,
            "brief_synthesis_receipt",
        ):
            raise BriefSynthesisError("second-phase transaction does not contain exactly one Brief and receipt")
        records: list[ImmutableRecordV1] = []
        for reference in transaction.records:
            try:
                stored = await self.store.load_record(
                    reference.storage_id,
                    product_id=self.product_id,
                    record_space=PREPARED_RECORD_SPACE,
                    record_kind=reference.record_kind,
                )
            except Exception:
                stored = None
            if stored is None or stored.reference() != reference:
                raise BriefSynthesisError("second-phase transaction references missing or changed material")
            records.append(stored)
        try:
            brief = BriefV1Alpha1.model_validate(records[0].payload)
            receipt = BriefSynthesisReceiptV1Alpha1.model_validate(records[1].payload)
            PreparedBriefAppendV1Alpha1(
                synthesis_key=synthesis_key,
                request_id=receipt.request_id,
                request_digest=receipt.request_digest,
                brief=brief,
                synthesis_receipt=receipt,
                submitted_at=receipt.created_at,
            )
        except Exception:
            raise BriefSynthesisError("second-phase transaction failed exact contract replay") from None
        if receipt.request_id != request_id or receipt.request_digest != request_digest:
            raise BriefSynthesisReplayConflict("synthesis key already binds different Brief request material")
        if (
            records[0].record_key != brief.resource_id
            or records[0].payload_contract != brief.contract
            or records[0].as_of != brief.as_of
            or records[0].available_at != brief.generated_at
            or records[1].record_key != receipt.receipt_id
            or records[1].payload_contract != receipt.contract
            or records[1].as_of != receipt.created_at
            or records[1].available_at != receipt.created_at
            or transaction.committed_at != brief.generated_at
            or transaction.committed_at != receipt.created_at
        ):
            raise BriefSynthesisError("second-phase envelopes do not match exact replayed contracts")
        try:
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_brief_transaction_key(synthesis_key),
                records=tuple(records),
                submitted_at=transaction.committed_at,
                governed_state_preconditions=transaction.governed_state_preconditions,
            )
        except Exception:
            reconstructed = None
        if reconstructed is None or transaction != reconstructed.receipt():
            raise BriefSynthesisError("second-phase transaction request identity failed closed")
        return PreparedBriefAppendAdmission(
            brief=brief,
            synthesis_receipt=receipt,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def append(
        self,
        packet: PreparedBriefAppendV1Alpha1,
        *,
        state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> PreparedBriefAppendAdmission:
        try:
            exact = PreparedBriefAppendV1Alpha1.model_validate(packet.model_dump(mode="python"))
        except Exception:
            raise BriefSynthesisError("prepared Brief append failed exact revalidation") from None
        if exact.brief.product_id != self.product_id:
            raise BriefSynthesisError("prepared Brief append crossed exact product scope")
        replay = await self.replay(
            synthesis_key=exact.synthesis_key,
            request_id=exact.request_id,
            request_digest=exact.request_digest,
        )
        if replay is not None:
            return replay
        request = AppendOnlyTransactionRequestV1(
            product_id=self.product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=_brief_transaction_key(exact.synthesis_key),
            records=(_brief_record(exact.brief), _synthesis_record(exact.synthesis_receipt)),
            submitted_at=exact.submitted_at,
            governed_state_preconditions=state_preconditions,
        )
        try:
            transaction = await self.store.append(request)
        except ImmutableRecordReplayConflict:
            replay = await self.replay(
                synthesis_key=exact.synthesis_key,
                request_id=exact.request_id,
                request_digest=exact.request_digest,
            )
            if replay is None:
                raise BriefSynthesisReplayConflict(
                    "concurrent second-phase append did not expose exact durable material"
                ) from None
            return replay
        except ImmutableRecordPersistenceError:
            replay = await self.replay(
                synthesis_key=exact.synthesis_key,
                request_id=exact.request_id,
                request_digest=exact.request_digest,
            )
            if replay is None:
                raise BriefSynthesisError("atomic Brief and synthesis-receipt append failed closed") from None
            return replay
        except Exception:
            raise BriefSynthesisError("atomic Brief and synthesis-receipt append failed closed") from None
        if transaction != request.receipt():
            raise BriefSynthesisError("Core append receipt does not bind the exact second-phase request")
        return PreparedBriefAppendAdmission(
            brief=exact.brief,
            synthesis_receipt=exact.synthesis_receipt,
            transaction_receipt=transaction,
            replayed=False,
        )


def _activation_precondition(binding: CommittedActivationBinding) -> GovernedStateHeadPreconditionV1Alpha1:
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


def _activation_receipt_reference(
    binding: CommittedActivationBinding,
) -> ReceiptReferenceV1Alpha1:
    return ReceiptReferenceV1Alpha1(
        receipt_id=str(binding.commit_receipt.receipt_id),
        receipt_digest=f"sha256:{binding.commit_receipt.receipt_hash}",
    )


def _synthesis_receipt(
    *,
    request: BriefSynthesisRequestV1Alpha1,
    activation_commit: ReceiptReferenceV1Alpha1,
    attention: AttentionDispositionReceiptV1Alpha1,
    policy: ResolvedBriefSynthesisPolicy,
    outcome: GovernedReasoningOutcome,
    assembly,
    write_intent_id: str,
    write_intent_digest: str,
    write_authorization: ReceiptReferenceV1Alpha1,
    created_at: datetime,
) -> BriefSynthesisReceiptV1Alpha1:
    brief = assembly.brief
    return BriefSynthesisReceiptV1Alpha1(
        product_id=request.product_id,
        synthesis_key=request.synthesis_key,
        reasoning_attempt_key=request.reasoning_attempt_key,
        request_id=str(request.request_id),
        request_digest=str(request.request_digest),
        reasoning_request_id=str(outcome.acceptance.request_id),
        reasoning_request_digest=str(outcome.acceptance.request_digest),
        activation_revision=request.activation_revision,
        activation_commit=activation_commit,
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
        write_intent_id=write_intent_id,
        write_intent_digest=write_intent_digest,
        write_authorization=write_authorization,
        reasoning_terminal=ReceiptReferenceV1Alpha1(
            receipt_id=str(outcome.terminal.receipt_id),
            receipt_digest=str(outcome.terminal.receipt_digest),
        ),
        reasoning_result_id=str(outcome.result.result_id),
        reasoning_result_digest=str(outcome.result.result_digest),
        brief_id=str(brief.resource_id),
        brief_digest=str(brief.resource_digest),
        created_at=created_at,
    )


def _authorization_neutral_payload_digest(
    *,
    brief: BriefV1Alpha1,
    receipt: BriefSynthesisReceiptV1Alpha1,
) -> str:
    material = {
        "recipe": "ace.intelligence.prepared-brief-append-neutral-payload/v1alpha1",
        "brief": brief.model_dump(
            mode="json",
            exclude={"resource_id", "resource_digest", "generated_at"},
        ),
        "synthesis_receipt": receipt.model_dump(
            mode="json",
            exclude={
                "write_intent_id",
                "write_intent_digest",
                "write_authorization",
                "brief_id",
                "brief_digest",
                "created_at",
                "receipt_id",
                "receipt_digest",
            },
        ),
    }
    return f"sha256:{canonical_hash(material)}"


def _append_intent(
    *,
    request: BriefSynthesisRequestV1Alpha1,
    semantic_input_digest: str,
    governed_state_identities: tuple[str, ...],
) -> PreparedBriefAppendIntentV1Alpha1:
    """Bind semantic inputs and the exact auth-ref/time-dependent append recipe."""
    return PreparedBriefAppendIntentV1Alpha1(
        product_id=request.product_id,
        transaction_key=_brief_transaction_key(request.synthesis_key),
        semantic_input_digest=semantic_input_digest,
        records=(
            PreparedBriefAppendRecordRecipeV1Alpha1(
                record_kind="brief",
                payload_contract="ace.intelligence.brief/v1alpha1",
                record_key_derivation="brief.resource_id_from_authorized_at",
                payload_digest_derivation="brief.canonical_payload_from_intent_and_authorized_at",
                as_of_derivation="request.brief_as_of",
                processing_order=0,
            ),
            PreparedBriefAppendRecordRecipeV1Alpha1(
                record_kind="brief_synthesis_receipt",
                payload_contract="ace.intelligence.brief-synthesis-receipt/v1alpha1",
                record_key_derivation="receipt.receipt_id_from_authorization_reference_and_authorized_at",
                payload_digest_derivation="receipt.canonical_payload_from_intent_authorization_and_authorized_at",
                as_of_derivation="authorization.authorized_at",
                processing_order=1,
            ),
        ),
        governed_state_identities=governed_state_identities,
    )


def _operation_state_identities(
    *,
    activation: GovernedStateHeadPreconditionV1Alpha1,
    binding: GovernedOperationBindingV1Alpha1,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            (
                f"{activation.state_kind}|{activation.product_id}|{activation.state_id}",
                (
                    f"{binding.state_head_precondition.state_kind}|"
                    f"{binding.product_id}|{binding.state_head_precondition.state_id}"
                ),
                (f"capability_state|{binding.product_id}|{capability_state_ref_for_artifact(binding.artifact)}"),
                f"authority_grant|{binding.product_id}|{binding.grant_ref}",
            )
        )
    )


def _authorization_attempt_key(
    *,
    synthesis_key: str,
    context: AuthenticatedRuntimeContextV1Alpha1,
    binding: GovernedOperationBindingV1Alpha1,
    required_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
) -> str:
    digest = canonical_hash(
        {
            "synthesis_key": synthesis_key,
            "authentication_receipt_ref": context.authentication_receipt_ref,
            "authentication_receipt_digest": context.authentication_receipt_digest,
            "append_binding_digest": binding.binding_digest,
            "required_preconditions": [
                item.model_dump(mode="json")
                for item in sorted(
                    required_preconditions,
                    key=lambda value: (
                        value.state_kind,
                        value.product_id,
                        value.state_id,
                    ),
                )
            ],
        }
    )
    return f"append_authorization_attempt:{digest[:32]}"


def _assert_append_realizes_intent(
    *,
    intent: PreparedBriefAppendIntentV1Alpha1,
    packet: PreparedBriefAppendV1Alpha1,
    authorization: GovernedActionAuthorizationProjection,
) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
    """Materialize and verify every exact record/transaction recipe dimension."""

    try:
        intent = PreparedBriefAppendIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        packet = PreparedBriefAppendV1Alpha1.model_validate(packet.model_dump(mode="python"))
        authorization = GovernedActionAuthorizationProjection.model_validate(authorization.model_dump(mode="python"))
    except Exception:
        raise BriefSynthesisError("authorized recipe failed exact revalidation") from None
    records = (_brief_record(packet.brief), _synthesis_record(packet.synthesis_receipt))
    identities = tuple(
        sorted(f"{item.state_kind}|{item.product_id}|{item.state_id}" for item in authorization.state_preconditions)
    )
    actual = tuple(
        (
            record.record_kind,
            record.record_key,
            record.payload_contract,
            record.as_of,
            record.available_at,
            record.processing_order,
            record.material_hash,
        )
        for record in records
    )
    if (
        intent.record_space != PREPARED_RECORD_SPACE
        or intent.product_id != packet.brief.product_id
        or intent.transaction_key != _brief_transaction_key(packet.synthesis_key)
        or packet.submitted_at != authorization.authorized_at
        or packet.brief.generated_at != authorization.authorized_at
        or packet.synthesis_receipt.created_at != authorization.authorized_at
        or packet.synthesis_receipt.write_authorization != authorization.authorization_ref
        or packet.synthesis_receipt.write_intent_id != intent.intent_id
        or packet.synthesis_receipt.write_intent_digest != intent.intent_digest
        or _authorization_neutral_payload_digest(
            brief=packet.brief,
            receipt=packet.synthesis_receipt,
        )
        != intent.semantic_input_digest
        or identities != intent.governed_state_identities
        or len(actual) != 2
        or tuple(item[0] for item in actual) != tuple(item.record_kind for item in intent.records)
        or tuple(item[2] for item in actual) != tuple(item.payload_contract for item in intent.records)
        or tuple(item[5] for item in actual) != (0, 1)
        or actual[0][1] != packet.brief.resource_id
        or actual[1][1] != packet.synthesis_receipt.receipt_id
        or actual[0][3] != packet.brief.as_of
        or actual[1][3] != authorization.authorized_at
        or any(item[4] != authorization.authorized_at for item in actual)
        or any(item[6] is None for item in actual)
    ):
        raise BriefSynthesisError("materialized append does not realize the exact authorized recipe")
    return authorization.state_preconditions


class BriefSynthesisService:
    """Resolve, reason, validate, render, and atomically persist one PREPARED Brief."""

    def __init__(
        self,
        *,
        activation_service: DomainActivationAdmissionService,
        pack: CompiledDomainPackV1,
        store: ImmutableRecordStore,
        reasoning: GovernedReasoningService,
        execution_binding: ReasoningExecutionBindingV1Alpha1,
        append_binding: GovernedOperationBindingV1Alpha1,
        clock: Callable[[], datetime],
        pack_resolver: CompiledPackArtifactResolver | None = None,
    ) -> None:
        self.activation_service = activation_service
        self.pack = CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
        self.store = store
        self.reasoning = reasoning
        self.execution_binding = ReasoningExecutionBindingV1Alpha1.model_validate(
            execution_binding.model_dump(mode="python")
        )
        self.append_binding = GovernedOperationBindingV1Alpha1.model_validate(append_binding.model_dump(mode="python"))
        self.clock = clock
        self.pack_resolver = pack_resolver or _SinglePackResolver(self.pack)

    async def _load_exact_pack(self, request: BriefSynthesisRequestV1Alpha1) -> CompiledDomainPackV1:
        try:
            pack = await self.pack_resolver.load_exact(
                reference=request.pack,
            )
            if pack is None:
                raise BriefSynthesisError("exact historical Pack IR artifact is unavailable")
            validated = CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
        except BriefSynthesisError:
            raise
        except Exception:
            raise BriefSynthesisError("exact Pack IR artifact resolution failed closed") from None
        if (
            validated.compiled_pack_id != request.pack.compiled_pack_id
            or validated.pack_digest != request.pack.pack_digest
            or validated.metadata.pack_id != request.pack.pack_id
            or validated.metadata.version != request.pack.pack_version
        ):
            raise BriefSynthesisError("resolved Pack IR crossed exact content coordinates")
        return validated

    @staticmethod
    def _revalidate_request(request: BriefSynthesisRequestV1Alpha1) -> BriefSynthesisRequestV1Alpha1:
        try:
            return BriefSynthesisRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise BriefSynthesisError("Brief synthesis request failed exact revalidation") from exc

    async def _load_binding(
        self,
        request: BriefSynthesisRequestV1Alpha1,
    ) -> CommittedActivationBinding:
        try:
            committed = await self.activation_service.reload(
                product_id=request.product_id,
                activation_key=request.activation_revision.activation_key,
            )
            if committed is None:
                raise BriefSynthesisError("current committed activation is missing")
            binding = bind_committed_activation(pack=self.pack, committed=committed)
        except BriefSynthesisError:
            raise
        except Exception:
            raise BriefSynthesisError("current committed activation failed exact reload") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
            or binding.prepared_binding.revision.spec.product_id != request.product_id
        ):
            raise BriefSynthesisError("request does not bind the current committed activation and Pack IR")
        return binding

    async def _exact_closure(
        self,
        *,
        request: BriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
        attention: AttentionDispositionReceiptV1Alpha1,
    ) -> tuple[
        SignalV1Alpha1,
        tuple[ShiftV1Alpha1, ...],
        tuple[EntitySnapshotV1Alpha1, ...],
        tuple[ObservationV1Alpha1, ...],
    ]:
        try:
            return await self._exact_closure_unchecked(
                request=request,
                ledger=ledger,
                attention=attention,
            )
        except BriefSynthesisError:
            raise
        except PreparedIntelligenceAdmissionError:
            raise BriefSynthesisError("exact routed context closure failed persisted-lineage validation") from None
        except Exception:
            raise BriefSynthesisError("exact routed context closure lower-port failure") from None

    async def _exact_closure_unchecked(
        self,
        *,
        request: BriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
        attention: AttentionDispositionReceiptV1Alpha1,
    ) -> tuple[
        SignalV1Alpha1,
        tuple[ShiftV1Alpha1, ...],
        tuple[EntitySnapshotV1Alpha1, ...],
        tuple[ObservationV1Alpha1, ...],
    ]:
        loaded_signal = await ledger.load_exact(attention.signal)
        if not isinstance(loaded_signal, SignalV1Alpha1):
            raise BriefSynthesisError("routed attention Signal is missing from exact PREPARED scope")
        if loaded_signal.as_of != request.brief_as_of:
            raise BriefSynthesisError("Brief cutoff must equal the routed Signal as_of time")
        if len(loaded_signal.lineage) != 1 or any(
            item.resource_kind is not LineageResourceKind.SHIFT or item.relation is not LineageRelation.DERIVED_FROM
            for item in loaded_signal.lineage
        ):
            raise BriefSynthesisError("routed Signal must have one exact persisted Shift predecessor")

        shifts: list[ShiftV1Alpha1] = []
        entities: list[EntitySnapshotV1Alpha1] = []
        observations: list[ObservationV1Alpha1] = []
        for shift_edge in loaded_signal.lineage:
            shift = await ledger.load_lineage_exact(shift_edge)
            if not isinstance(shift, ShiftV1Alpha1):
                raise BriefSynthesisError("Signal lineage does not resolve its exact persisted Shift")
            if not shift.lineage or any(
                item.resource_kind is not LineageResourceKind.ENTITY_SNAPSHOT
                or item.relation is not LineageRelation.DERIVED_FROM
                for item in shift.lineage
            ):
                raise BriefSynthesisError("Shift must derive only from exact persisted Entity Snapshots")
            shifts.append(shift)
            for entity_edge in shift.lineage:
                entity = await ledger.load_lineage_exact(entity_edge)
                if not isinstance(entity, EntitySnapshotV1Alpha1):
                    raise BriefSynthesisError("Shift lineage does not resolve an exact Entity Snapshot")
                if not entity.lineage or any(
                    item.resource_kind is not LineageResourceKind.OBSERVATION
                    or item.relation is not LineageRelation.DERIVED_FROM
                    for item in entity.lineage
                ):
                    raise BriefSynthesisError("Entity Snapshot must derive only from exact persisted Observations")
                entities.append(entity)
                for observation_edge in entity.lineage:
                    observation = await ledger.load_lineage_exact(observation_edge)
                    if not isinstance(observation, ObservationV1Alpha1) or observation.lineage:
                        raise BriefSynthesisError(
                            "Entity Snapshot lineage must terminate at exact persisted Observations"
                        )
                    observations.append(observation)

        closure = (loaded_signal, *shifts, *entities, *observations)
        ids = [str(item.resource_id) for item in closure]
        if len(ids) != len(set(ids)):
            raise BriefSynthesisError("exact routed closure contains duplicate resource identities")
        if any(
            item.product_id != request.product_id
            or item.mode is not IntelligenceResourceMode.PREPARED
            or item.activation_revision != request.activation_revision
            or item.as_of > request.brief_as_of
            or resource_reference(item).available_at > request.context_cutoff_at
            for item in closure
        ):
            raise BriefSynthesisError(
                "exact routed closure crossed product, activation, PREPARED mode, cutoff, or availability"
            )
        shift_refs = tuple(sorted((resource_reference(item) for item in shifts), key=lambda item: item.resource_id))
        if attention.source_lineage != shift_refs:
            raise BriefSynthesisError("attention receipt does not bind the Signal's exact persisted Shift lineage")
        return loaded_signal, tuple(shifts), tuple(entities), tuple(observations)

    @staticmethod
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

    async def _freeze_reasoning_request(
        self,
        *,
        request: BriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
        activation_precondition: GovernedStateHeadPreconditionV1Alpha1,
        policy: ResolvedBriefSynthesisPolicy,
        closure: tuple,
        execution_binding: ReasoningExecutionBindingV1Alpha1,
    ) -> tuple[
        ReasoningExecutionBindingV1Alpha1,
        tuple[FrozenContextItemV1Alpha1, ...],
        GovernedReasoningRequestV1Alpha1,
    ]:
        """Reconstruct the one exact authenticated Core request for live use or replay."""

        try:
            exact_execution_binding = ReasoningExecutionBindingV1Alpha1.model_validate(
                execution_binding.model_dump(mode="python")
            )
        except Exception:
            raise BriefSynthesisError("host reasoning binding failed exact revalidation") from None
        if exact_execution_binding.product_id != request.product_id:
            raise BriefSynthesisError("host reasoning binding crossed exact product scope")
        frozen = []
        for resource in closure:
            try:
                item = await ledger.freeze_exact(resource_reference(resource))
            except PreparedIntelligenceAdmissionError as exc:
                raise BriefSynthesisError("exact context freeze/revalidation failed") from exc
            except Exception:
                raise BriefSynthesisError("exact context freeze lower-port failure") from None
            if item is None:
                raise BriefSynthesisError("exact routed context disappeared before Core request reconstruction")
            frozen.append(item)
        try:
            reasoning_request = GovernedReasoningRequestV1Alpha1(
                attempt_key=request.reasoning_attempt_key,
                product_id=request.product_id,
                authenticated_context=request.authenticated_context,
                artifact=exact_execution_binding.artifact,
                configuration_ref=exact_execution_binding.configuration_ref,
                authority=exact_execution_binding.authority,
                grant_ref=exact_execution_binding.grant_ref,
                instruction_json=self._trusted_instructions(policy),
                context_items=tuple(frozen),
                cutoff_at=request.context_cutoff_at,
                requested_at=request.requested_at,
                required_state_preconditions=(
                    activation_precondition,
                    exact_execution_binding.state_head_precondition,
                ),
            )
        except Exception:
            raise BriefSynthesisError("exact governed reasoning request reconstruction failed closed") from None
        return exact_execution_binding, tuple(frozen), reasoning_request

    async def _validate_replayed_admission(
        self,
        admission: PreparedBriefAppendAdmission,
        request: BriefSynthesisRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None,
    ) -> PreparedBriefAppendAdmission:
        receipt = admission.synthesis_receipt
        if (
            receipt.product_id != request.product_id
            or receipt.synthesis_key != request.synthesis_key
            or receipt.reasoning_attempt_key != request.reasoning_attempt_key
            or receipt.request_id != request.request_id
            or receipt.request_digest != request.request_digest
        ):
            raise BriefSynthesisReplayConflict("synthesis key crossed incoming request or reasoning-attempt identity")
        try:
            historical_pack = await self._load_exact_pack(request)
            historical = await self.activation_service.load_exact(
                product_id=request.product_id,
                revision_id=request.activation_revision.revision_id,
                commit_receipt_id=str(receipt.activation_commit.receipt_id),
            )
            if historical is None or (
                historical.commit_receipt.receipt_id != receipt.activation_commit.receipt_id
                or f"sha256:{historical.commit_receipt.receipt_hash}" != receipt.activation_commit.receipt_digest
            ):
                raise BriefSynthesisError("replayed synthesis lost its exact historical activation commit")
            binding = bind_committed_activation(
                pack=historical_pack,
                committed=historical,
            )
        except (DomainActivationAdmissionError, ValueError):
            raise BriefSynthesisError("replayed historical activation failed exact validation") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
        ):
            raise BriefSynthesisError("replayed synthesis crossed its historical activation or Pack IR")
        activation_precondition = _activation_precondition(binding)
        ledger = PreparedIntelligenceLedgerService(binding=binding, store=self.store)
        try:
            derivation = await ledger.replay(derivation_key=request.derivation_key)
        except Exception:
            raise BriefSynthesisError("replayed route derivation failed exact validation") from None
        if derivation is None or any(isinstance(item, BriefV1Alpha1) for item in derivation.resources):
            raise BriefSynthesisError("replayed synthesis requires its exact pre-Brief route derivation")
        attention = derivation.attention_receipt
        if (
            attention.receipt_id != request.attention_receipt_id
            or attention.receipt_digest != request.attention_receipt_digest
            or attention.disposition is not AttentionDisposition.ROUTE
            or attention.brief_template_id is None
            or not attention.persona_ids
            or attention.evaluated_at > request.context_cutoff_at
        ):
            raise BriefSynthesisError("replayed synthesis lost its exact routed attention policy")
        signal, shifts, entities, observations = await self._exact_closure(
            request=request,
            ledger=ledger,
            attention=attention,
        )
        closure = (signal, *shifts, *entities, *observations)
        try:
            policy = resolve_brief_synthesis_policy(
                binding.prepared_binding,
                template_id=attention.brief_template_id,
                persona_ids=attention.persona_ids,
            )
        except PreparedActivationBindingError as exc:
            raise BriefSynthesisError("replayed template or persona policy is no longer exact") from exc
        if (
            receipt.activation_revision != request.activation_revision
            or receipt.pack != request.pack
            or receipt.derivation_key != request.derivation_key
            or receipt.attention_receipt_id != attention.receipt_id
            or receipt.attention_receipt_digest != attention.receipt_digest
            or receipt.module_id != policy.module_id
            or receipt.module_digest != policy.module_digest
            or receipt.template_id != policy.template.template_id
            or receipt.template_digest != policy.template_digest
            or receipt.persona_ids != attention.persona_ids
            or receipt.required_section_ids != policy.template.required_sections
        ):
            raise BriefSynthesisError("replayed synthesis receipt crossed activation, route, or template policy")

        _, frozen, _ = await self._freeze_reasoning_request(
            request=request,
            ledger=ledger,
            activation_precondition=activation_precondition,
            policy=policy,
            closure=closure,
            execution_binding=self.execution_binding,
        )
        expected_context = tuple(
            sorted(
                (
                    BriefSelectedContextBindingV1Alpha1(
                        record=resource_reference(resource),
                        context=ContextBindingV1Alpha1.from_item(item),
                    )
                    for resource, item in zip(closure, frozen, strict=True)
                ),
                key=lambda item: (
                    item.record.resource_kind.value,
                    item.record.resource_id,
                ),
            )
        )
        if receipt.selected_context != expected_context:
            raise BriefSynthesisError("replayed selected resources do not match reconstructed Core frozen context")
        try:
            current_delivery = delivery_context or request.authenticated_context
            outcome = await self.reasoning.execute_historical(
                product_id=request.product_id,
                attempt_key=request.reasoning_attempt_key,
                expected_request_id=receipt.reasoning_request_id,
                expected_request_digest=receipt.reasoning_request_digest,
                instruction_json=self._trusted_instructions(policy),
                context_items=frozen,
                cutoff_at=request.context_cutoff_at,
                requested_at=request.requested_at,
                delivery_context=current_delivery,
                delivery_binding=self.execution_binding,
            )
        except GovernedReasoningError:
            raise BriefSynthesisError("replayed Brief failed exact governed Core request replay") from None
        uses_by_context = {item.context.context_id: item for item in outcome.context_uses}
        if (
            receipt.reasoning_terminal.receipt_id != outcome.terminal.receipt_id
            or receipt.reasoning_terminal.receipt_digest != outcome.terminal.receipt_digest
            or receipt.reasoning_request_id != outcome.acceptance.request_id
            or receipt.reasoning_request_digest != outcome.acceptance.request_digest
            or receipt.reasoning_result_id != outcome.result.result_id
            or receipt.reasoning_result_digest != outcome.result.result_digest
            or {item.context.context_id for item in receipt.selected_context} != set(uses_by_context)
            or set(outcome.result.referenced_context_ids) != set(uses_by_context)
            or any(not item.output_referenced for item in uses_by_context.values())
            or any(
                uses_by_context[item.context.context_id].context != item.context for item in receipt.selected_context
            )
            or receipt.created_at < outcome.result.completed_at
        ):
            raise BriefSynthesisError("replayed synthesis receipt crossed exact Core context or terminal material")

        lineage_by_id = {item.resource_id: item for item in admission.brief.lineage}
        expected_records = {str(item.resource_id): resource_reference(item) for item in closure}
        selected_records = {item.record.resource_id: item.record for item in receipt.selected_context}
        if selected_records != expected_records:
            raise BriefSynthesisError("replayed selected context differs from exact routed closure")
        for selected in receipt.selected_context:
            reference = selected.record
            lineage = lineage_by_id.get(reference.resource_id)
            if lineage is None or (
                lineage.resource_digest != reference.resource_digest
                or lineage.resource_as_of != reference.as_of
                or lineage.resource_available_at != reference.available_at
            ):
                raise BriefSynthesisError("replayed Brief lineage differs from selected context mapping")
            expected_storage_id = immutable_record_storage_id(
                product_id=reference.product_id,
                record_space=reference.mode.value,
                record_kind=reference.resource_kind.value,
                record_key=reference.resource_id,
            )
            try:
                stored = await self.store.load_record(
                    expected_storage_id,
                    product_id=reference.product_id,
                    record_space=reference.mode.value,
                    record_kind=reference.resource_kind.value,
                )
            except Exception:
                raise BriefSynthesisError("replayed selected record load failed closed") from None
            if stored is None or (
                stored.storage_id != selected.context.storage_id
                or stored.material_hash != selected.context.material_digest
                or stored.record_key != reference.resource_id
                or stored.payload_contract != reference.resource_contract
                or stored.as_of != reference.as_of
                or stored.available_at != reference.available_at
            ):
                raise BriefSynthesisError("replayed selected Intelligence record changed Core frozen mapping")
        if set(lineage_by_id) != {item.record.resource_id for item in receipt.selected_context}:
            raise BriefSynthesisError("replayed Brief contains lineage outside exact selected context")

        try:
            core_draft = BriefSynthesisDraftV1Alpha1.model_validate_json(outcome.result.structured_json)
            assembly = assemble_canonical_brief(
                product_id=request.product_id,
                activation_revision=request.activation_revision,
                brief_as_of=request.brief_as_of,
                generated_at=receipt.created_at,
                draft=core_draft,
                policy=policy,
                closure=closure,
                observations=observations,
                selected_context=receipt.selected_context,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise BriefSynthesisError("Core structured result fails replayed synthesis policy") from exc
        if (
            assembly.brief != admission.brief
            or assembly.selected_context != receipt.selected_context
            or assembly.required_section_ids != receipt.required_section_ids
            or assembly.actual_section_ids != receipt.actual_section_ids
            or assembly.section_claims != receipt.section_claims
            or assembly.recommendation_claim_id != receipt.recommendation_claim_id
            or assembly.claim_supports != receipt.claim_supports
        ):
            raise BriefSynthesisError("replayed Brief is not the canonical rendering of receipted claims")
        try:
            write_authorization = await self.reasoning.verify_action_reference(
                product_id=request.product_id,
                operation="append_immutable_records",
                subject_ref=receipt.write_intent_id,
                subject_digest=receipt.write_intent_digest,
                expected=receipt.write_authorization,
            )
        except GovernedReasoningError:
            raise BriefSynthesisError("replayed Brief lost exact private append authorization") from None
        intent = _append_intent(
            request=request,
            semantic_input_digest=_authorization_neutral_payload_digest(
                brief=admission.brief,
                receipt=receipt,
            ),
            governed_state_identities=tuple(
                sorted(
                    f"{item.state_kind}|{item.product_id}|{item.state_id}"
                    for item in write_authorization.state_preconditions
                )
            ),
        )
        if receipt.write_intent_id != intent.intent_id or receipt.write_intent_digest != intent.intent_digest:
            raise BriefSynthesisError("replayed append intent differs from exact historical synthesis")
        expected_preconditions = _assert_append_realizes_intent(
            intent=intent,
            packet=PreparedBriefAppendV1Alpha1(
                synthesis_key=request.synthesis_key,
                request_id=str(request.request_id),
                request_digest=str(request.request_digest),
                brief=admission.brief,
                synthesis_receipt=receipt,
                submitted_at=receipt.created_at,
            ),
            authorization=write_authorization,
        )
        if (
            admission.transaction_receipt.governed_state_preconditions != expected_preconditions
            or admission.transaction_receipt.committed_at != receipt.created_at
            or receipt.created_at != admission.brief.generated_at
            or receipt.created_at != write_authorization.authorized_at
        ):
            raise BriefSynthesisError("replayed Brief append crossed exact governed heads or commit time")
        return admission

    async def synthesize(
        self,
        request: BriefSynthesisRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
    ) -> PreparedBriefAppendAdmission:
        validated = self._revalidate_request(request)
        append_service = _PreparedBriefAppendService(product_id=validated.product_id, store=self.store)
        replay = await append_service.replay(
            synthesis_key=validated.synthesis_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
        )
        if replay is not None:
            return await self._validate_replayed_admission(
                replay,
                validated,
                delivery_context=delivery_context,
            )

        binding = await self._load_binding(validated)
        activation_precondition = _activation_precondition(binding)
        ledger = PreparedIntelligenceLedgerService(binding=binding, store=self.store)
        try:
            derivation = await ledger.replay(derivation_key=validated.derivation_key)
        except Exception:
            raise BriefSynthesisError("routed PREPARED derivation failed exact replay") from None
        if derivation is None:
            raise BriefSynthesisError("routed PREPARED derivation is missing")
        if any(isinstance(item, BriefV1Alpha1) for item in derivation.resources):
            raise BriefSynthesisError("route-triggered synthesis requires a derivation with no prebuilt Brief")
        attention = derivation.attention_receipt
        if (
            attention.receipt_id != validated.attention_receipt_id
            or attention.receipt_digest != validated.attention_receipt_digest
            or attention.disposition is not AttentionDisposition.ROUTE
            or attention.brief_template_id is None
            or not attention.persona_ids
            or attention.activation_revision != validated.activation_revision
            or attention.pack != validated.pack
            or attention.evaluated_at > validated.context_cutoff_at
        ):
            raise BriefSynthesisError("request requires one exact routed attention receipt with template and personas")

        signal, shifts, entities, observations = await self._exact_closure(
            request=validated,
            ledger=ledger,
            attention=attention,
        )
        closure = (signal, *shifts, *entities, *observations)
        try:
            policy = resolve_brief_synthesis_policy(
                binding.prepared_binding,
                template_id=attention.brief_template_id,
                persona_ids=attention.persona_ids,
            )
        except PreparedActivationBindingError as exc:
            raise BriefSynthesisError("routed template or persona policy failed exact resolution") from exc
        execution_binding, frozen, reasoning_request = await self._freeze_reasoning_request(
            request=validated,
            ledger=ledger,
            activation_precondition=activation_precondition,
            policy=policy,
            closure=closure,
            execution_binding=self.execution_binding,
        )
        current_context = delivery_context or validated.authenticated_context
        try:
            outcome: GovernedReasoningOutcome = await self.reasoning.execute(
                reasoning_request,
                delivery_context=current_context,
                delivery_binding=self.execution_binding,
            )
        except GovernedReasoningError as exc:
            raise BriefSynthesisError("Core governed reasoning failed closed") from exc
        expected_context_ids = {str(item.context_id) for item in frozen}
        if set(outcome.result.referenced_context_ids) != expected_context_ids:
            raise BriefSynthesisError("structured output did not attribute every exact selected context item")
        context_mapping = tuple(
            BriefSelectedContextBindingV1Alpha1(
                record=resource_reference(resource),
                context=ContextBindingV1Alpha1.from_item(item),
            )
            for resource, item in zip(closure, frozen, strict=True)
        )
        uses_by_context = {item.context.context_id: item for item in outcome.context_uses}
        if set(uses_by_context) != {item.context.context_id for item in context_mapping} or any(
            uses_by_context[item.context.context_id].context != item.context for item in context_mapping
        ):
            raise BriefSynthesisError("Core terminal context uses do not match exact frozen mapping")
        try:
            draft = BriefSynthesisDraftV1Alpha1.model_validate_json(outcome.result.structured_json)
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise BriefSynthesisError("provider output violates exact Brief synthesis policy") from exc

        post_binding = await self._load_binding(validated)
        post_precondition = _activation_precondition(post_binding)
        if post_precondition != activation_precondition:
            raise BriefSynthesisError("committed activation changed during Brief synthesis")
        activation_commit = _activation_receipt_reference(binding)
        try:
            provisional_assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.brief_as_of,
                generated_at=outcome.result.completed_at,
                draft=draft,
                policy=policy,
                closure=closure,
                observations=observations,
                selected_context=context_mapping,
            )
            provisional_receipt = _synthesis_receipt(
                request=validated,
                activation_commit=activation_commit,
                attention=attention,
                policy=policy,
                outcome=outcome,
                assembly=provisional_assembly,
                write_intent_id="prepared_brief_append_intent:" + "0" * 32,
                write_intent_digest="sha256:" + "0" * 64,
                write_authorization=ReceiptReferenceV1Alpha1(
                    receipt_id="governed_action_authorization:" + "0" * 32,
                    receipt_digest="sha256:" + "0" * 64,
                ),
                created_at=outcome.result.completed_at,
            )
            semantic_input_digest = _authorization_neutral_payload_digest(
                brief=provisional_assembly.brief,
                receipt=provisional_receipt,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise BriefSynthesisError("Core draft failed provisional append-recipe assembly") from exc
        intent = _append_intent(
            request=validated,
            semantic_input_digest=semantic_input_digest,
            governed_state_identities=_operation_state_identities(
                activation=post_precondition,
                binding=self.append_binding,
            ),
        )
        required_append_preconditions = (
            post_precondition,
            self.append_binding.state_head_precondition,
        )
        authorization_request = GovernedActionAuthorizationRequestV1Alpha1(
            authorization_key=_authorization_attempt_key(
                synthesis_key=validated.synthesis_key,
                context=current_context,
                binding=self.append_binding,
                required_preconditions=required_append_preconditions,
            ),
            product_id=validated.product_id,
            authenticated_context=current_context,
            execution_binding=self.append_binding,
            operation="append_immutable_records",
            subject_ref=str(intent.intent_id),
            subject_digest=str(intent.intent_digest),
            requested_at=max(
                outcome.result.completed_at,
                current_context.authenticated_at,
            ),
            required_state_preconditions=required_append_preconditions,
        )
        try:
            write_authorization = await self.reasoning.authorize_action(authorization_request)
        except GovernedReasoningError:
            raise BriefSynthesisError("current authority denied exact atomic append subject") from None
        generated_at = write_authorization.authorized_at
        if generated_at < outcome.result.completed_at:
            raise BriefSynthesisError("durable append authorization predates Core reasoning completion")
        try:
            assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.brief_as_of,
                generated_at=generated_at,
                draft=draft,
                policy=policy,
                closure=closure,
                observations=observations,
                selected_context=context_mapping,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise BriefSynthesisError("Core draft failed canonical Brief assembly") from exc
        brief = assembly.brief
        synthesis_receipt = _synthesis_receipt(
            request=validated,
            activation_commit=activation_commit,
            attention=attention,
            policy=policy,
            outcome=outcome,
            assembly=assembly,
            write_intent_id=str(intent.intent_id),
            write_intent_digest=str(intent.intent_digest),
            write_authorization=write_authorization.authorization_ref,
            created_at=generated_at,
        )
        packet = PreparedBriefAppendV1Alpha1(
            synthesis_key=validated.synthesis_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
            brief=brief,
            synthesis_receipt=synthesis_receipt,
            submitted_at=generated_at,
        )
        state_preconditions = _assert_append_realizes_intent(
            intent=intent,
            packet=packet,
            authorization=write_authorization,
        )
        admission = await append_service.append(
            packet,
            state_preconditions=state_preconditions,
        )
        if admission.replayed:
            return await self._validate_replayed_admission(
                admission,
                validated,
                delivery_context=delivery_context,
            )
        return admission


__all__ = [
    "BriefSynthesisError",
    "BriefSynthesisReplayConflict",
    "BriefSynthesisService",
    "PreparedBriefAppendAdmission",
]
