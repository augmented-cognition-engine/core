"""Initial-corpus governed PREPARED first-Brief synthesis across Core and Intelligence.

This is the additive sibling of :mod:`ace.application.brief_synthesis`. The
routed service binds one Signal derivation and its attention receipt; this
service binds no change event at all. It orients over the already admitted
Observation and Entity Snapshot records at one exact ``corpus_as_of``/
``corpus_available_at``, selects its template and personas from a declared Pack
orientation policy, freezes that exact corpus as Core context, and appends one
grounded Brief whose lineage is exactly the admitted corpus. It never creates a
synthetic Shift or Signal and never performs a second capture or read.

Nothing here is domain-specific. The orientation policy, template, personas,
and corpus records are all resolved from the caller's compiled Pack IR and the
durable ledger; this module only refuses to proceed when any of that is
missing, empty, changed, crossed, stale, unauthorized, or already bound to
different material.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from ace.application.brief_synthesis import (
    BriefSynthesisError,
    BriefSynthesisReplayConflict,
    _activation_precondition,
    _activation_receipt_reference,
    _authorization_attempt_key,
    _operation_state_identities,
    _SinglePackResolver,
)
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
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.ledger import (
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
)
from ace.intelligence.contracts.synthesis import (
    BriefSelectedContextBindingV1Alpha1,
    BriefSynthesisDraftV1Alpha1,
    InitialCorpusBriefSynthesisReceiptV1Alpha1,
    InitialCorpusBriefSynthesisRequestV1Alpha1,
    PreparedInitialCorpusBriefAppendIntentV1Alpha1,
    PreparedInitialCorpusBriefAppendRecordRecipeV1Alpha1,
    PreparedInitialCorpusBriefAppendV1Alpha1,
)
from ace.intelligence.packs.runtime import (
    CompiledPackArtifactResolver,
    PreparedActivationBindingError,
    ResolvedInitialOrientationPolicy,
    resolve_initial_orientation_policy,
)
from ace.intelligence.synthesis import (
    BriefDraftValidationError,
    assemble_canonical_brief,
)

INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_KIND = "initial_corpus_brief_synthesis_receipt"


class InitialCorpusBriefSynthesisError(BriefSynthesisError):
    """Initial-corpus PREPARED first-Brief synthesis or replay failed closed."""


class InitialCorpusBriefSynthesisReplayConflict(
    InitialCorpusBriefSynthesisError,
    BriefSynthesisReplayConflict,
):
    """A stable initial-corpus synthesis key already binds different material."""


@dataclass(frozen=True, slots=True)
class PreparedInitialCorpusBriefAppendAdmission:
    """Exact replayable initial-corpus Brief plus its synthesis receipt."""

    brief: BriefV1Alpha1
    synthesis_receipt: InitialCorpusBriefSynthesisReceiptV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED


@dataclass(frozen=True, slots=True)
class ResolvedInitialCorpusClosure:
    """The complete admitted corpus at one exact as_of/availability instant."""

    closure: tuple[object, ...]
    observations: tuple[ObservationV1Alpha1, ...]
    entity_snapshots: tuple[EntitySnapshotV1Alpha1, ...]


def _corpus_transaction_key(synthesis_key: str) -> str:
    return f"initial_corpus_brief_synthesis:{canonical_hash([synthesis_key, 'initial_corpus_brief'])[:32]}"


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


def _synthesis_record(receipt: InitialCorpusBriefSynthesisReceiptV1Alpha1) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=receipt.product_id,
        record_space=PREPARED_RECORD_SPACE,
        record_kind=INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_KIND,
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=receipt.created_at,
        available_at=receipt.created_at,
        processing_order=1,
    )


def _authorization_neutral_payload_digest(
    *,
    brief: BriefV1Alpha1,
    receipt: InitialCorpusBriefSynthesisReceiptV1Alpha1,
) -> str:
    material = {
        "recipe": "ace.intelligence.prepared-initial-corpus-brief-append-neutral-payload/v1alpha1",
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
    request: InitialCorpusBriefSynthesisRequestV1Alpha1,
    semantic_input_digest: str,
    governed_state_identities: tuple[str, ...],
) -> PreparedInitialCorpusBriefAppendIntentV1Alpha1:
    """Bind semantic inputs and the exact auth-ref/time-dependent append recipe."""

    return PreparedInitialCorpusBriefAppendIntentV1Alpha1(
        product_id=request.product_id,
        transaction_key=_corpus_transaction_key(request.synthesis_key),
        orientation_policy_id=request.orientation_policy_id,
        semantic_input_digest=semantic_input_digest,
        records=(
            PreparedInitialCorpusBriefAppendRecordRecipeV1Alpha1(
                record_kind="brief",
                payload_contract="ace.intelligence.brief/v1alpha1",
                record_key_derivation="brief.resource_id_from_authorized_at",
                payload_digest_derivation="brief.canonical_payload_from_intent_and_authorized_at",
                as_of_derivation="request.corpus_as_of",
                processing_order=0,
            ),
            PreparedInitialCorpusBriefAppendRecordRecipeV1Alpha1(
                record_kind=INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_KIND,
                payload_contract="ace.intelligence.initial-corpus-brief-synthesis-receipt/v1alpha1",
                record_key_derivation="receipt.receipt_id_from_authorization_reference_and_authorized_at",
                payload_digest_derivation="receipt.canonical_payload_from_intent_authorization_and_authorized_at",
                as_of_derivation="authorization.authorized_at",
                processing_order=1,
            ),
        ),
        governed_state_identities=governed_state_identities,
    )


def _assert_append_realizes_intent(
    *,
    intent: PreparedInitialCorpusBriefAppendIntentV1Alpha1,
    packet: PreparedInitialCorpusBriefAppendV1Alpha1,
    authorization: GovernedActionAuthorizationProjection,
) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
    """Materialize and verify every exact record/transaction recipe dimension."""

    try:
        intent = PreparedInitialCorpusBriefAppendIntentV1Alpha1.model_validate(intent.model_dump(mode="python"))
        packet = PreparedInitialCorpusBriefAppendV1Alpha1.model_validate(packet.model_dump(mode="python"))
        authorization = GovernedActionAuthorizationProjection.model_validate(authorization.model_dump(mode="python"))
    except Exception:
        raise InitialCorpusBriefSynthesisError("authorized recipe failed exact revalidation") from None
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
        or intent.transaction_key != _corpus_transaction_key(packet.synthesis_key)
        or intent.orientation_policy_id != packet.synthesis_receipt.orientation_policy_id
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
        raise InitialCorpusBriefSynthesisError("materialized append does not realize the exact authorized recipe")
    return authorization.state_preconditions


class _PreparedInitialCorpusBriefAppendService:
    """Additive append service on its own transaction key and record kind."""

    def __init__(self, *, product_id: str, store: ImmutableRecordStore) -> None:
        self.product_id = product_id
        self.store = store

    async def replay(
        self,
        *,
        synthesis_key: str,
        request_id: str,
        request_digest: str,
    ) -> PreparedInitialCorpusBriefAppendAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_corpus_transaction_key(synthesis_key),
            )
        except Exception:
            raise InitialCorpusBriefSynthesisError("second-phase transaction load failed closed") from None
        if transaction is None:
            return None
        if len(transaction.records) != 2 or tuple(item.record_kind for item in transaction.records) != (
            IntelligenceRecordKind.BRIEF.value,
            INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_KIND,
        ):
            raise InitialCorpusBriefSynthesisError(
                "second-phase transaction does not contain exactly one Brief and receipt"
            )
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
                raise InitialCorpusBriefSynthesisError(
                    "second-phase transaction references missing or changed material"
                )
            records.append(stored)
        try:
            brief = BriefV1Alpha1.model_validate(records[0].payload)
            receipt = InitialCorpusBriefSynthesisReceiptV1Alpha1.model_validate(records[1].payload)
            PreparedInitialCorpusBriefAppendV1Alpha1(
                synthesis_key=synthesis_key,
                request_id=receipt.request_id,
                request_digest=receipt.request_digest,
                brief=brief,
                synthesis_receipt=receipt,
                submitted_at=receipt.created_at,
            )
        except Exception:
            raise InitialCorpusBriefSynthesisError("second-phase transaction failed exact contract replay") from None
        if receipt.request_id != request_id or receipt.request_digest != request_digest:
            raise InitialCorpusBriefSynthesisReplayConflict(
                "initial-corpus synthesis key already binds different Brief request material"
            )
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
            raise InitialCorpusBriefSynthesisError("second-phase envelopes do not match exact replayed contracts")
        try:
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_corpus_transaction_key(synthesis_key),
                records=tuple(records),
                submitted_at=transaction.committed_at,
                governed_state_preconditions=transaction.governed_state_preconditions,
            )
        except Exception:
            reconstructed = None
        if reconstructed is None or transaction != reconstructed.receipt():
            raise InitialCorpusBriefSynthesisError("second-phase transaction request identity failed closed")
        return PreparedInitialCorpusBriefAppendAdmission(
            brief=brief,
            synthesis_receipt=receipt,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def append(
        self,
        packet: PreparedInitialCorpusBriefAppendV1Alpha1,
        *,
        state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> PreparedInitialCorpusBriefAppendAdmission:
        try:
            exact = PreparedInitialCorpusBriefAppendV1Alpha1.model_validate(packet.model_dump(mode="python"))
        except Exception:
            raise InitialCorpusBriefSynthesisError(
                "prepared initial-corpus Brief append failed exact revalidation"
            ) from None
        if exact.brief.product_id != self.product_id:
            raise InitialCorpusBriefSynthesisError("prepared initial-corpus Brief append crossed exact product scope")
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
            transaction_key=_corpus_transaction_key(exact.synthesis_key),
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
                raise InitialCorpusBriefSynthesisReplayConflict(
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
                raise InitialCorpusBriefSynthesisError(
                    "atomic initial-corpus Brief and synthesis-receipt append failed closed"
                ) from None
            return replay
        except Exception:
            raise InitialCorpusBriefSynthesisError(
                "atomic initial-corpus Brief and synthesis-receipt append failed closed"
            ) from None
        if transaction != request.receipt():
            raise InitialCorpusBriefSynthesisError("Core append receipt does not bind the exact second-phase request")
        return PreparedInitialCorpusBriefAppendAdmission(
            brief=exact.brief,
            synthesis_receipt=exact.synthesis_receipt,
            transaction_receipt=transaction,
            replayed=False,
        )


class InitialCorpusBriefSynthesisService:
    """Bind the exact admitted corpus, reason under governance, and persist one Brief."""

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

    # -- exact activation and Pack IR ------------------------------------

    @staticmethod
    def _revalidate_request(
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
    ) -> InitialCorpusBriefSynthesisRequestV1Alpha1:
        try:
            return InitialCorpusBriefSynthesisRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise InitialCorpusBriefSynthesisError(
                "initial-corpus Brief synthesis request failed exact revalidation"
            ) from exc

    async def _load_exact_pack(self, reference: CompiledPackRefV1) -> CompiledDomainPackV1:
        try:
            pack = await self.pack_resolver.load_exact(reference=reference)
            if pack is None:
                raise InitialCorpusBriefSynthesisError("exact historical Pack IR artifact is unavailable")
            validated = CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
        except InitialCorpusBriefSynthesisError:
            raise
        except Exception:
            raise InitialCorpusBriefSynthesisError("exact Pack IR artifact resolution failed closed") from None
        if (
            validated.compiled_pack_id != reference.compiled_pack_id
            or validated.pack_digest != reference.pack_digest
            or validated.metadata.pack_id != reference.pack_id
            or validated.metadata.version != reference.pack_version
        ):
            raise InitialCorpusBriefSynthesisError("resolved Pack IR crossed exact content coordinates")
        return validated

    async def _load_binding(
        self,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
    ) -> CommittedActivationBinding:
        try:
            committed = await self.activation_service.reload(
                product_id=request.product_id,
                activation_key=request.activation_revision.activation_key,
            )
            if committed is None:
                raise InitialCorpusBriefSynthesisError("current committed activation is missing")
            binding = bind_committed_activation(pack=self.pack, committed=committed)
        except InitialCorpusBriefSynthesisError:
            raise
        except Exception:
            raise InitialCorpusBriefSynthesisError("current committed activation failed exact reload") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
            or binding.prepared_binding.revision.spec.product_id != request.product_id
        ):
            raise InitialCorpusBriefSynthesisError("request does not bind the current committed activation and Pack IR")
        return binding

    # -- declared orientation policy -------------------------------------

    def _orientation_policy(
        self,
        *,
        binding: CommittedActivationBinding,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
    ) -> ResolvedInitialOrientationPolicy:
        try:
            return resolve_initial_orientation_policy(
                binding.prepared_binding,
                policy_id=request.orientation_policy_id,
            )
        except PreparedActivationBindingError as exc:
            raise InitialCorpusBriefSynthesisError(
                "declared orientation policy, template, or personas failed exact resolution"
            ) from exc

    # -- exact admitted-corpus closure -----------------------------------

    async def _resolve_corpus_closure(
        self,
        *,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
    ) -> ResolvedInitialCorpusClosure:
        try:
            return await self._resolve_corpus_closure_unchecked(request=request, ledger=ledger)
        except InitialCorpusBriefSynthesisError:
            raise
        except PreparedIntelligenceAdmissionError:
            raise InitialCorpusBriefSynthesisError(
                "exact admitted-corpus closure failed persisted-lineage validation"
            ) from None
        except Exception:
            raise InitialCorpusBriefSynthesisError("exact admitted-corpus closure lower-port failure") from None

    async def _resolve_corpus_closure_unchecked(
        self,
        *,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
    ) -> ResolvedInitialCorpusClosure:
        observations = tuple(
            await ledger.read_as_of(
                product_id=request.product_id,
                mode=IntelligenceResourceMode.PREPARED,
                kind=IntelligenceRecordKind.OBSERVATION,
                available_at=request.corpus_available_at,
            )
        )
        snapshots = tuple(
            await ledger.read_as_of(
                product_id=request.product_id,
                mode=IntelligenceResourceMode.PREPARED,
                kind=IntelligenceRecordKind.ENTITY_SNAPSHOT,
                available_at=request.corpus_available_at,
            )
        )
        if not observations or not snapshots:
            raise InitialCorpusBriefSynthesisError(
                "the admitted initial corpus is empty; a first Brief requires exact admitted material"
            )
        if any(not isinstance(item, ObservationV1Alpha1) for item in observations) or any(
            not isinstance(item, EntitySnapshotV1Alpha1) for item in snapshots
        ):
            raise InitialCorpusBriefSynthesisError("the admitted corpus decoded outside its exact record kinds")
        closure = tuple(sorted((*snapshots, *observations), key=lambda item: str(item.resource_id)))
        ids = [str(item.resource_id) for item in closure]
        if len(ids) != len(set(ids)):
            raise InitialCorpusBriefSynthesisError("exact corpus closure contains duplicate resource identities")
        if any(
            item.product_id != request.product_id
            or item.mode is not IntelligenceResourceMode.PREPARED
            or item.activation_revision != request.activation_revision
            for item in closure
        ):
            raise InitialCorpusBriefSynthesisError(
                "exact corpus closure crossed product, activation, or PREPARED mode scope"
            )
        if any(
            item.as_of != request.corpus_as_of or resource_reference(item).available_at > request.corpus_available_at
            for item in closure
        ):
            raise InitialCorpusBriefSynthesisError(
                "the initial corpus must share one exact as_of and availability instant without future leakage"
            )
        observation_by_id = {str(item.resource_id): item for item in observations}
        for snapshot in snapshots:
            if not snapshot.lineage or any(
                item.resource_kind is not LineageResourceKind.OBSERVATION
                or item.relation is not LineageRelation.DERIVED_FROM
                for item in snapshot.lineage
            ):
                raise InitialCorpusBriefSynthesisError(
                    "every corpus Entity Snapshot must derive only from exact persisted Observations"
                )
            for edge in snapshot.lineage:
                included = observation_by_id.get(edge.resource_id)
                if included is None or resource_reference(included).resource_digest != edge.resource_digest:
                    persisted = await ledger.load_lineage_exact(edge)
                    if persisted is None:
                        raise InitialCorpusBriefSynthesisError(
                            "a corpus Entity Snapshot names a missing source Observation locator"
                        )
                    raise InitialCorpusBriefSynthesisError(
                        "a corpus Entity Snapshot names a source Observation locator foreign to the exact corpus"
                    )
        return ResolvedInitialCorpusClosure(
            closure=closure,
            observations=tuple(observation_by_id[str(item.resource_id)] for item in observations),
            entity_snapshots=tuple(snapshots),
        )

    # -- frozen Core request ---------------------------------------------

    @staticmethod
    def _trusted_instructions(
        policy: ResolvedInitialOrientationPolicy,
        *,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        resolved: ResolvedInitialCorpusClosure,
    ) -> str:
        synthesis = policy.synthesis
        return canonical_json(
            {
                "brief_type": synthesis.template.brief_type,
                "claim_policy": synthesis.template.claim_policy,
                "corpus_boundary": {
                    "corpus_as_of": request.corpus_as_of.isoformat(),
                    "corpus_available_at": request.corpus_available_at.isoformat(),
                    "derivation": "initial_corpus_orientation_no_change_event",
                    "entity_snapshot_ids": sorted(str(item.resource_id) for item in resolved.entity_snapshots),
                    "observation_ids": sorted(str(item.resource_id) for item in resolved.observations),
                    "orientation_policy_id": policy.policy.policy_id,
                },
                "instruction_authority": "trusted_application",
                "objective": synthesis.template.objective,
                "output_contract": "ace.intelligence.brief-synthesis-draft/v1alpha1",
                "personas": [
                    {
                        "description": item.description,
                        "display_name": item.display_name,
                        "persona_id": item.persona_id,
                    }
                    for item in synthesis.personas
                ],
                "recommendation_required": synthesis.template.recommendation_required,
                "required_sections": list(synthesis.template.required_sections),
                "support_reference_policy": "exact_resource_ids_only",
            }
        )

    async def _freeze_reasoning_request(
        self,
        *,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
        activation_precondition: GovernedStateHeadPreconditionV1Alpha1,
        policy: ResolvedInitialOrientationPolicy,
        resolved: ResolvedInitialCorpusClosure,
    ) -> tuple[tuple, GovernedReasoningRequestV1Alpha1]:
        """Reconstruct the one exact authenticated Core request for live use or replay."""

        try:
            exact_execution_binding = ReasoningExecutionBindingV1Alpha1.model_validate(
                self.execution_binding.model_dump(mode="python")
            )
        except Exception:
            raise InitialCorpusBriefSynthesisError("host reasoning binding failed exact revalidation") from None
        if exact_execution_binding.product_id != request.product_id:
            raise InitialCorpusBriefSynthesisError("host reasoning binding crossed exact product scope")
        frozen = []
        for resource in resolved.closure:
            try:
                item = await ledger.freeze_exact(resource_reference(resource))
            except PreparedIntelligenceAdmissionError as exc:
                raise InitialCorpusBriefSynthesisError("exact context freeze/revalidation failed") from exc
            except Exception:
                raise InitialCorpusBriefSynthesisError("exact context freeze lower-port failure") from None
            if item is None:
                raise InitialCorpusBriefSynthesisError(
                    "exact corpus context disappeared before Core request reconstruction"
                )
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
                instruction_json=self._trusted_instructions(policy, request=request, resolved=resolved),
                context_items=tuple(frozen),
                cutoff_at=request.corpus_available_at,
                requested_at=request.requested_at,
                required_state_preconditions=(
                    activation_precondition,
                    exact_execution_binding.state_head_precondition,
                ),
            )
        except Exception:
            raise InitialCorpusBriefSynthesisError(
                "exact governed reasoning request reconstruction failed closed"
            ) from None
        return tuple(frozen), reasoning_request

    def _receipt(
        self,
        *,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        resolved: ResolvedInitialCorpusClosure,
        activation_commit: ReceiptReferenceV1Alpha1,
        policy: ResolvedInitialOrientationPolicy,
        outcome: GovernedReasoningOutcome,
        assembly,
        write_intent_id: str,
        write_intent_digest: str,
        write_authorization: ReceiptReferenceV1Alpha1,
        created_at: datetime,
    ) -> InitialCorpusBriefSynthesisReceiptV1Alpha1:
        synthesis = policy.synthesis
        return InitialCorpusBriefSynthesisReceiptV1Alpha1(
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
            orientation_module_id=policy.module_id,
            orientation_module_digest=policy.module_digest,
            orientation_policy_id=policy.policy.policy_id,
            orientation_policy_digest=policy.policy_digest,
            corpus_as_of=request.corpus_as_of,
            corpus_available_at=request.corpus_available_at,
            corpus_observation_ids=tuple(str(item.resource_id) for item in resolved.observations),
            corpus_entity_snapshot_ids=tuple(str(item.resource_id) for item in resolved.entity_snapshots),
            module_id=synthesis.module_id,
            module_digest=synthesis.module_digest,
            template_id=synthesis.template.template_id,
            template_digest=synthesis.template_digest,
            persona_ids=tuple(item.persona_id for item in synthesis.personas),
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
            brief_id=str(assembly.brief.resource_id),
            brief_digest=str(assembly.brief.resource_digest),
            created_at=created_at,
        )

    # -- deterministic replay --------------------------------------------

    async def _validate_replayed_admission(
        self,
        admission: PreparedInitialCorpusBriefAppendAdmission,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None,
    ) -> PreparedInitialCorpusBriefAppendAdmission:
        receipt = admission.synthesis_receipt
        if (
            receipt.product_id != request.product_id
            or receipt.synthesis_key != request.synthesis_key
            or receipt.reasoning_attempt_key != request.reasoning_attempt_key
            or receipt.request_id != request.request_id
            or receipt.request_digest != request.request_digest
            or receipt.orientation_policy_id != request.orientation_policy_id
            or receipt.corpus_as_of != request.corpus_as_of
            or receipt.corpus_available_at != request.corpus_available_at
        ):
            raise InitialCorpusBriefSynthesisReplayConflict(
                "initial-corpus synthesis key crossed incoming request, policy, or corpus identity"
            )
        try:
            historical_pack = await self._load_exact_pack(request.pack)
            historical = await self.activation_service.load_exact(
                product_id=request.product_id,
                revision_id=request.activation_revision.revision_id,
                commit_receipt_id=str(receipt.activation_commit.receipt_id),
            )
            if historical is None or (
                historical.commit_receipt.receipt_id != receipt.activation_commit.receipt_id
                or f"sha256:{historical.commit_receipt.receipt_hash}" != receipt.activation_commit.receipt_digest
            ):
                raise InitialCorpusBriefSynthesisError("replayed synthesis lost its exact historical activation commit")
            binding = bind_committed_activation(pack=historical_pack, committed=historical)
        except (DomainActivationAdmissionError, ValueError):
            raise InitialCorpusBriefSynthesisError("replayed historical activation failed exact validation") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
        ):
            raise InitialCorpusBriefSynthesisError("replayed synthesis crossed its historical activation or Pack IR")
        activation_precondition = _activation_precondition(binding)
        ledger = PreparedIntelligenceLedgerService(binding=binding, store=self.store)
        resolved = await self._resolve_corpus_closure(request=request, ledger=ledger)
        policy = self._orientation_policy(binding=binding, request=request)
        synthesis = policy.synthesis
        if (
            receipt.activation_revision != request.activation_revision
            or receipt.pack != request.pack
            or receipt.orientation_module_id != policy.module_id
            or receipt.orientation_module_digest != policy.module_digest
            or receipt.orientation_policy_digest != policy.policy_digest
            or receipt.corpus_observation_ids != tuple(sorted(str(item.resource_id) for item in resolved.observations))
            or receipt.corpus_entity_snapshot_ids
            != tuple(sorted(str(item.resource_id) for item in resolved.entity_snapshots))
            or receipt.module_id != synthesis.module_id
            or receipt.module_digest != synthesis.module_digest
            or receipt.template_id != synthesis.template.template_id
            or receipt.template_digest != synthesis.template_digest
            or receipt.persona_ids != tuple(item.persona_id for item in synthesis.personas)
            or receipt.required_section_ids != synthesis.template.required_sections
        ):
            raise InitialCorpusBriefSynthesisError(
                "replayed synthesis receipt crossed activation, corpus, or orientation policy"
            )

        frozen, _ = await self._freeze_reasoning_request(
            request=request,
            ledger=ledger,
            activation_precondition=activation_precondition,
            policy=policy,
            resolved=resolved,
        )
        expected_context = tuple(
            sorted(
                (
                    BriefSelectedContextBindingV1Alpha1(
                        record=resource_reference(resource),
                        context=ContextBindingV1Alpha1.from_item(item),
                    )
                    for resource, item in zip(resolved.closure, frozen, strict=True)
                ),
                key=lambda item: (item.record.resource_kind.value, item.record.resource_id),
            )
        )
        if receipt.selected_context != expected_context:
            raise InitialCorpusBriefSynthesisError(
                "replayed selected resources do not match reconstructed Core frozen context"
            )
        try:
            current_delivery = delivery_context or request.authenticated_context
            outcome = await self.reasoning.execute_historical(
                product_id=request.product_id,
                attempt_key=request.reasoning_attempt_key,
                expected_request_id=receipt.reasoning_request_id,
                expected_request_digest=receipt.reasoning_request_digest,
                instruction_json=self._trusted_instructions(policy, request=request, resolved=resolved),
                context_items=frozen,
                cutoff_at=request.corpus_available_at,
                requested_at=request.requested_at,
                delivery_context=current_delivery,
                delivery_binding=self.execution_binding,
            )
        except GovernedReasoningError:
            raise InitialCorpusBriefSynthesisError(
                "replayed initial-corpus Brief failed exact governed Core request replay"
            ) from None
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
            raise InitialCorpusBriefSynthesisError(
                "replayed synthesis receipt crossed exact Core context or terminal material"
            )

        lineage_by_id = {item.resource_id: item for item in admission.brief.lineage}
        expected_records = {str(item.resource_id): resource_reference(item) for item in resolved.closure}
        selected_records = {item.record.resource_id: item.record for item in receipt.selected_context}
        if selected_records != expected_records:
            raise InitialCorpusBriefSynthesisError("replayed selected context differs from exact admitted corpus")
        for selected in receipt.selected_context:
            reference = selected.record
            lineage = lineage_by_id.get(reference.resource_id)
            if lineage is None or (
                lineage.resource_digest != reference.resource_digest
                or lineage.resource_as_of != reference.as_of
                or lineage.resource_available_at != reference.available_at
            ):
                raise InitialCorpusBriefSynthesisError("replayed Brief lineage differs from selected context mapping")
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
                raise InitialCorpusBriefSynthesisError("replayed selected record load failed closed") from None
            if stored is None or (
                stored.storage_id != selected.context.storage_id
                or stored.material_hash != selected.context.material_digest
                or stored.record_key != reference.resource_id
                or stored.payload_contract != reference.resource_contract
                or stored.as_of != reference.as_of
                or stored.available_at != reference.available_at
            ):
                raise InitialCorpusBriefSynthesisError(
                    "replayed selected Intelligence record changed Core frozen mapping"
                )
        if set(lineage_by_id) != {item.record.resource_id for item in receipt.selected_context}:
            raise InitialCorpusBriefSynthesisError("replayed Brief contains lineage outside exact selected context")

        try:
            core_draft = BriefSynthesisDraftV1Alpha1.model_validate_json(outcome.result.structured_json)
            assembly = assemble_canonical_brief(
                product_id=request.product_id,
                activation_revision=request.activation_revision,
                brief_as_of=request.corpus_as_of,
                generated_at=receipt.created_at,
                draft=core_draft,
                policy=synthesis,
                closure=resolved.closure,
                observations=resolved.observations,
                selected_context=receipt.selected_context,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise InitialCorpusBriefSynthesisError("Core structured result fails replayed synthesis policy") from exc
        if (
            assembly.brief != admission.brief
            or assembly.selected_context != receipt.selected_context
            or assembly.required_section_ids != receipt.required_section_ids
            or assembly.actual_section_ids != receipt.actual_section_ids
            or assembly.section_claims != receipt.section_claims
            or assembly.recommendation_claim_id != receipt.recommendation_claim_id
            or assembly.claim_supports != receipt.claim_supports
        ):
            raise InitialCorpusBriefSynthesisError("replayed Brief is not the canonical rendering of receipted claims")
        try:
            write_authorization = await self.reasoning.verify_action_reference(
                product_id=request.product_id,
                operation="append_immutable_records",
                subject_ref=receipt.write_intent_id,
                subject_digest=receipt.write_intent_digest,
                expected=receipt.write_authorization,
            )
        except GovernedReasoningError:
            raise InitialCorpusBriefSynthesisError(
                "replayed initial-corpus Brief lost exact private append authorization"
            ) from None
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
            raise InitialCorpusBriefSynthesisError("replayed append intent differs from exact historical synthesis")
        expected_preconditions = _assert_append_realizes_intent(
            intent=intent,
            packet=PreparedInitialCorpusBriefAppendV1Alpha1(
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
            raise InitialCorpusBriefSynthesisError(
                "replayed initial-corpus Brief append crossed exact governed heads or commit time"
            )
        return admission

    # -- public entry point ----------------------------------------------

    async def synthesize(
        self,
        request: InitialCorpusBriefSynthesisRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
    ) -> PreparedInitialCorpusBriefAppendAdmission:
        validated = self._revalidate_request(request)
        append_service = _PreparedInitialCorpusBriefAppendService(
            product_id=validated.product_id,
            store=self.store,
        )
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
        resolved = await self._resolve_corpus_closure(request=validated, ledger=ledger)
        policy = self._orientation_policy(binding=binding, request=validated)
        frozen, reasoning_request = await self._freeze_reasoning_request(
            request=validated,
            ledger=ledger,
            activation_precondition=activation_precondition,
            policy=policy,
            resolved=resolved,
        )
        current_context = delivery_context or validated.authenticated_context
        try:
            outcome: GovernedReasoningOutcome = await self.reasoning.execute(
                reasoning_request,
                delivery_context=current_context,
                delivery_binding=self.execution_binding,
            )
        except GovernedReasoningError as exc:
            raise InitialCorpusBriefSynthesisError("Core governed reasoning failed closed") from exc
        expected_context_ids = {str(item.context_id) for item in frozen}
        if set(outcome.result.referenced_context_ids) != expected_context_ids:
            raise InitialCorpusBriefSynthesisError(
                "structured output did not attribute every exact selected context item"
            )
        context_mapping = tuple(
            BriefSelectedContextBindingV1Alpha1(
                record=resource_reference(resource),
                context=ContextBindingV1Alpha1.from_item(item),
            )
            for resource, item in zip(resolved.closure, frozen, strict=True)
        )
        uses_by_context = {item.context.context_id: item for item in outcome.context_uses}
        if set(uses_by_context) != {item.context.context_id for item in context_mapping} or any(
            uses_by_context[item.context.context_id].context != item.context for item in context_mapping
        ):
            raise InitialCorpusBriefSynthesisError("Core terminal context uses do not match exact frozen mapping")
        try:
            draft = BriefSynthesisDraftV1Alpha1.model_validate_json(outcome.result.structured_json)
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise InitialCorpusBriefSynthesisError("provider output violates exact Brief synthesis policy") from exc

        post_binding = await self._load_binding(validated)
        post_precondition = _activation_precondition(post_binding)
        if post_precondition != activation_precondition:
            raise InitialCorpusBriefSynthesisError("committed activation changed during initial-corpus synthesis")
        post_resolved = await self._resolve_corpus_closure(request=validated, ledger=ledger)
        if post_resolved.closure != resolved.closure:
            raise InitialCorpusBriefSynthesisError("the exact admitted corpus changed during governed reasoning")
        activation_commit = _activation_receipt_reference(binding)
        try:
            provisional_assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.corpus_as_of,
                generated_at=outcome.result.completed_at,
                draft=draft,
                policy=policy.synthesis,
                closure=resolved.closure,
                observations=resolved.observations,
                selected_context=context_mapping,
            )
            provisional_receipt = self._receipt(
                request=validated,
                resolved=resolved,
                activation_commit=activation_commit,
                policy=policy,
                outcome=outcome,
                assembly=provisional_assembly,
                write_intent_id="prepared_initial_corpus_brief_append_intent:" + "0" * 32,
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
            raise InitialCorpusBriefSynthesisError("Core draft failed provisional append-recipe assembly") from exc
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
            requested_at=max(outcome.result.completed_at, current_context.authenticated_at),
            required_state_preconditions=required_append_preconditions,
        )
        try:
            write_authorization = await self.reasoning.authorize_action(authorization_request)
        except GovernedReasoningError:
            raise InitialCorpusBriefSynthesisError("current authority denied exact atomic append subject") from None
        generated_at = write_authorization.authorized_at
        if generated_at < outcome.result.completed_at:
            raise InitialCorpusBriefSynthesisError("durable append authorization predates Core reasoning completion")
        try:
            assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.corpus_as_of,
                generated_at=generated_at,
                draft=draft,
                policy=policy.synthesis,
                closure=resolved.closure,
                observations=resolved.observations,
                selected_context=context_mapping,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise InitialCorpusBriefSynthesisError("Core draft failed canonical Brief assembly") from exc
        synthesis_receipt = self._receipt(
            request=validated,
            resolved=resolved,
            activation_commit=activation_commit,
            policy=policy,
            outcome=outcome,
            assembly=assembly,
            write_intent_id=str(intent.intent_id),
            write_intent_digest=str(intent.intent_digest),
            write_authorization=write_authorization.authorization_ref,
            created_at=generated_at,
        )
        packet = PreparedInitialCorpusBriefAppendV1Alpha1(
            synthesis_key=validated.synthesis_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
            brief=assembly.brief,
            synthesis_receipt=synthesis_receipt,
            submitted_at=generated_at,
        )
        state_preconditions = _assert_append_realizes_intent(
            intent=intent,
            packet=packet,
            authorization=write_authorization,
        )
        admission = await append_service.append(packet, state_preconditions=state_preconditions)
        if admission.replayed:
            return await self._validate_replayed_admission(
                admission,
                validated,
                delivery_context=delivery_context,
            )
        return admission


__all__ = [
    "INITIAL_CORPUS_BRIEF_SYNTHESIS_RECEIPT_KIND",
    "InitialCorpusBriefSynthesisError",
    "InitialCorpusBriefSynthesisReplayConflict",
    "InitialCorpusBriefSynthesisService",
    "PreparedInitialCorpusBriefAppendAdmission",
    "ResolvedInitialCorpusClosure",
]
