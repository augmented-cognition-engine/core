"""Status-aware Case-bound governed PREPARED Brief synthesis.

This is the additive sibling of :class:`CaseBriefSynthesisService`. It reuses
that service's exact Case closure resolution, routed attention validation,
template/persona derivation, and canonical Brief assembly verbatim, and adds
exactly one thing: a Domain-Pack-declared, per-statement epistemic status bound
to every ordered claim and persisted as a durable sibling projection inside the
same atomic transaction as the Brief and its synthesis receipt.

Nothing here is domain-specific. The status vocabulary, its generic support
constraints, and the template it governs are all resolved from the caller's
compiled Pack IR. ACE only refuses to proceed when a status is undeclared,
incompatible with the claim's grounding kind, unsupported by the claim's exact
support facts, missing, doubly bound, or inconsistent on replay.

Identity note
-------------
``ace.intelligence.brief/v1alpha1`` and
``ace.intelligence.case-brief-synthesis-receipt/v1alpha1`` are reused unchanged.
Status lives only in
``ace.intelligence.brief-epistemic-status-projection/v1alpha1``, so no existing
contract's canonical payload -- and therefore no existing artifact identity --
moves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ace.application.brief_synthesis import (
    _activation_precondition,
    _activation_receipt_reference,
    _authorization_attempt_key,
    _operation_state_identities,
)
from ace.application.case_brief_synthesis import (
    CASE_BRIEF_SYNTHESIS_RECEIPT_KIND,
    CaseBriefSynthesisError,
    CaseBriefSynthesisReplayConflict,
    CaseBriefSynthesisService,
    ResolvedCaseClosure,
    _brief_record,
    _synthesis_record,
)
from ace.application.domain_activation import (
    DomainActivationAdmissionError,
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
    GovernedReasoningError,
    GovernedReasoningOutcome,
    GovernedReasoningRequestV1Alpha1,
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
from ace.intelligence.contracts.epistemic import (
    BRIEF_EPISTEMIC_STATUS_PROJECTION_KIND,
    EPISTEMIC_STATUS_MODULE_VERSION,
    BriefEpistemicStatusProjectionV1Alpha1,
)
from ace.intelligence.contracts.ledger import IntelligenceRecordKind, resource_reference
from ace.intelligence.contracts.resources import (
    BriefV1Alpha1,
    CaseV1Alpha1,
    IntelligenceResourceMode,
    LineageResourceKind,
)
from ace.intelligence.contracts.synthesis import (
    BriefSelectedContextBindingV1Alpha1,
    BriefSynthesisDraftV1Alpha2,
    CaseBriefSynthesisReceiptV1Alpha1,
    CaseBriefSynthesisRequestV1Alpha1,
    PreparedStatusCaseBriefAppendIntentV1Alpha1,
    PreparedStatusCaseBriefAppendRecordRecipeV1Alpha1,
    PreparedStatusCaseBriefAppendV1Alpha1,
)
from ace.intelligence.epistemic import (
    EpistemicStatusValidationError,
    derive_claim_epistemic_statuses,
)
from ace.intelligence.packs.runtime import (
    PreparedActivationBindingError,
    ResolvedBriefSynthesisPolicy,
    ResolvedEpistemicStatusPolicy,
    resolve_epistemic_status_policy,
)
from ace.intelligence.synthesis import (
    BriefDraftValidationError,
    assemble_canonical_brief,
)

_ZERO_DIGEST = "sha256:" + "0" * 64


@dataclass(frozen=True, slots=True)
class StatusAppendProfile:
    """Every contract literal that differs between status-module versions.

    ``v1alpha1`` and ``v1alpha2`` share one code path; only these values change.
    The ``v1alpha1`` profile reproduces the original literals exactly, so every
    artifact already written under it keeps its identity.
    """

    module_contract: str
    projection_model: type
    append_model: type
    intent_model: type
    recipe_model: type
    projection_kind: str
    projection_contract: str
    transaction_prefix: str
    transaction_salt: str
    neutral_recipe: str
    zero_intent_prefix: str
    intent_extra_fields: tuple[tuple[str, str], ...] = ()

    @property
    def zero_intent_id(self) -> str:
        return f"{self.zero_intent_prefix}:" + "0" * 32


STATUS_PROFILE_V1ALPHA1 = StatusAppendProfile(
    module_contract=EPISTEMIC_STATUS_MODULE_VERSION,
    projection_model=BriefEpistemicStatusProjectionV1Alpha1,
    append_model=PreparedStatusCaseBriefAppendV1Alpha1,
    intent_model=PreparedStatusCaseBriefAppendIntentV1Alpha1,
    recipe_model=PreparedStatusCaseBriefAppendRecordRecipeV1Alpha1,
    projection_kind=BRIEF_EPISTEMIC_STATUS_PROJECTION_KIND,
    projection_contract="ace.intelligence.brief-epistemic-status-projection/v1alpha1",
    transaction_prefix="status_case_brief_synthesis",
    transaction_salt="status_case_brief",
    neutral_recipe="ace.intelligence.prepared-status-case-brief-append-neutral-payload/v1alpha1",
    zero_intent_prefix="prepared_status_case_brief_append_intent",
)
_ZERO_AUTHORIZATION = ReceiptReferenceV1Alpha1(
    receipt_id="governed_action_authorization:" + "0" * 32,
    receipt_digest=_ZERO_DIGEST,
)


class CaseBriefStatusSynthesisError(CaseBriefSynthesisError):
    """Status-aware Case-bound Brief synthesis or replay failed closed."""


class CaseBriefStatusSynthesisReplayConflict(
    CaseBriefStatusSynthesisError,
    CaseBriefSynthesisReplayConflict,
):
    """A stable status synthesis key already binds different request material."""


@dataclass(frozen=True, slots=True)
class PreparedStatusCaseBriefAppendAdmission:
    """Exact replayable Brief, synthesis receipt, and durable status projection."""

    brief: BriefV1Alpha1
    synthesis_receipt: CaseBriefSynthesisReceiptV1Alpha1
    status_projection: BriefEpistemicStatusProjectionV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED


def _status_transaction_key(synthesis_key: str, *, profile: StatusAppendProfile) -> str:
    digest = canonical_hash([synthesis_key, profile.transaction_salt])[:32]
    return f"{profile.transaction_prefix}:{digest}"


def _projection_record(projection, *, profile: StatusAppendProfile) -> ImmutableRecordV1:
    return ImmutableRecordV1(
        product_id=projection.product_id,
        record_space=PREPARED_RECORD_SPACE,
        record_kind=profile.projection_kind,
        record_key=str(projection.projection_id),
        payload_contract=projection.contract,
        payload=projection.model_dump(mode="python"),
        as_of=projection.as_of,
        available_at=projection.generated_at,
        processing_order=2,
    )


def _authorization_neutral_payload_digest(
    *,
    brief: BriefV1Alpha1,
    receipt: CaseBriefSynthesisReceiptV1Alpha1,
    projection,
    profile: StatusAppendProfile,
) -> str:
    material = {
        "recipe": profile.neutral_recipe,
        "brief": brief.model_dump(
            mode="json",
            exclude={"resource_id", "resource_digest", "generated_at"},
        ),
        "status_projection": projection.model_dump(
            mode="json",
            exclude={
                "brief_id",
                "brief_digest",
                "synthesis_receipt_id",
                "synthesis_receipt_digest",
                "generated_at",
                "projection_id",
                "projection_digest",
            },
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


def _status_append_intent(
    *,
    request: CaseBriefSynthesisRequestV1Alpha1,
    status_policy: ResolvedEpistemicStatusPolicy,
    semantic_input_digest: str,
    governed_state_identities: tuple[str, ...],
    profile: StatusAppendProfile,
):
    """Bind semantic inputs, the status vocabulary, and the exact append recipe."""

    return profile.intent_model(
        product_id=request.product_id,
        transaction_key=_status_transaction_key(request.synthesis_key, profile=profile),
        **dict(profile.intent_extra_fields),
        case_id=request.case.resource_id,
        status_set_id=status_policy.status_set.status_set_id,
        status_set_digest=status_policy.status_set_digest,
        semantic_input_digest=semantic_input_digest,
        records=(
            profile.recipe_model(
                record_kind="brief",
                payload_contract="ace.intelligence.brief/v1alpha1",
                record_key_derivation="brief.resource_id_from_authorized_at",
                payload_digest_derivation="brief.canonical_payload_from_intent_and_authorized_at",
                as_of_derivation="request.brief_as_of",
                processing_order=0,
            ),
            profile.recipe_model(
                record_kind=CASE_BRIEF_SYNTHESIS_RECEIPT_KIND,
                payload_contract="ace.intelligence.case-brief-synthesis-receipt/v1alpha1",
                record_key_derivation="receipt.receipt_id_from_authorization_reference_and_authorized_at",
                payload_digest_derivation="receipt.canonical_payload_from_intent_authorization_and_authorized_at",
                as_of_derivation="authorization.authorized_at",
                processing_order=1,
            ),
            profile.recipe_model(
                record_kind=profile.projection_kind,
                payload_contract=profile.projection_contract,
                record_key_derivation="projection.projection_id_from_brief_receipt_and_authorized_at",
                payload_digest_derivation="projection.canonical_payload_from_brief_receipt_and_authorized_at",
                as_of_derivation="request.brief_as_of",
                processing_order=2,
            ),
        ),
        governed_state_identities=governed_state_identities,
    )


def _assert_status_append_realizes_intent(
    *,
    intent,
    packet,
    authorization: GovernedActionAuthorizationProjection,
    profile: StatusAppendProfile,
) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
    """Materialize and verify every exact record/transaction recipe dimension."""

    try:
        intent = profile.intent_model.model_validate(intent.model_dump(mode="python"))
        packet = profile.append_model.model_validate(packet.model_dump(mode="python"))
        authorization = GovernedActionAuthorizationProjection.model_validate(authorization.model_dump(mode="python"))
    except Exception:
        raise CaseBriefStatusSynthesisError("authorized recipe failed exact revalidation") from None
    records = (
        _brief_record(packet.brief),
        _synthesis_record(packet.synthesis_receipt),
        _projection_record(packet.status_projection, profile=profile),
    )
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
        or intent.transaction_key != _status_transaction_key(packet.synthesis_key, profile=profile)
        or intent.case_id != packet.synthesis_receipt.case.resource_id
        or intent.status_set_id != packet.status_projection.status_set_id
        or intent.status_set_digest != packet.status_projection.status_set_digest
        or packet.submitted_at != authorization.authorized_at
        or packet.brief.generated_at != authorization.authorized_at
        or packet.synthesis_receipt.created_at != authorization.authorized_at
        or packet.status_projection.generated_at != authorization.authorized_at
        or packet.synthesis_receipt.write_authorization != authorization.authorization_ref
        or packet.synthesis_receipt.write_intent_id != intent.intent_id
        or packet.synthesis_receipt.write_intent_digest != intent.intent_digest
        or _authorization_neutral_payload_digest(
            brief=packet.brief,
            receipt=packet.synthesis_receipt,
            projection=packet.status_projection,
            profile=profile,
        )
        != intent.semantic_input_digest
        or identities != intent.governed_state_identities
        or len(actual) != 3
        or tuple(item[0] for item in actual) != tuple(item.record_kind for item in intent.records)
        or tuple(item[2] for item in actual) != tuple(item.payload_contract for item in intent.records)
        or tuple(item[5] for item in actual) != (0, 1, 2)
        or actual[0][1] != packet.brief.resource_id
        or actual[1][1] != packet.synthesis_receipt.receipt_id
        or actual[2][1] != packet.status_projection.projection_id
        or actual[0][3] != packet.brief.as_of
        or actual[1][3] != authorization.authorized_at
        or actual[2][3] != packet.brief.as_of
        or any(item[4] != authorization.authorized_at for item in actual)
        or any(item[6] is None for item in actual)
    ):
        raise CaseBriefStatusSynthesisError("materialized append does not realize the exact authorized recipe")
    return authorization.state_preconditions


class _PreparedStatusCaseBriefAppendService:
    """Additive append service on its own transaction key and record triple."""

    def __init__(
        self,
        *,
        product_id: str,
        store: ImmutableRecordStore,
        profile: StatusAppendProfile,
    ) -> None:
        self.product_id = product_id
        self.store = store
        self.profile = profile

    @property
    def _expected_kinds(self) -> tuple[str, str, str]:
        return (
            IntelligenceRecordKind.BRIEF.value,
            CASE_BRIEF_SYNTHESIS_RECEIPT_KIND,
            self.profile.projection_kind,
        )

    async def replay(
        self,
        *,
        synthesis_key: str,
        request_id: str,
        request_digest: str,
    ) -> PreparedStatusCaseBriefAppendAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_status_transaction_key(synthesis_key, profile=self.profile),
            )
        except Exception:
            raise CaseBriefStatusSynthesisError("status second-phase transaction load failed closed") from None
        if transaction is None:
            return None
        if (
            len(transaction.records) != 3
            or tuple(item.record_kind for item in transaction.records) != self._expected_kinds
        ):
            raise CaseBriefStatusSynthesisError(
                "status second-phase transaction does not contain exactly one Brief, receipt, and projection"
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
                raise CaseBriefStatusSynthesisError(
                    "status second-phase transaction references missing or changed material"
                )
            records.append(stored)
        try:
            brief = BriefV1Alpha1.model_validate(records[0].payload)
            receipt = CaseBriefSynthesisReceiptV1Alpha1.model_validate(records[1].payload)
            projection = self.profile.projection_model.model_validate(records[2].payload)
            self.profile.append_model(
                synthesis_key=synthesis_key,
                request_id=receipt.request_id,
                request_digest=receipt.request_digest,
                brief=brief,
                synthesis_receipt=receipt,
                status_projection=projection,
                submitted_at=receipt.created_at,
            )
        except Exception:
            raise CaseBriefStatusSynthesisError(
                "status second-phase transaction failed exact contract replay"
            ) from None
        if receipt.request_id != request_id or receipt.request_digest != request_digest:
            raise CaseBriefStatusSynthesisReplayConflict(
                "status synthesis key already binds different Brief request material"
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
            or records[2].record_key != projection.projection_id
            or records[2].payload_contract != projection.contract
            or records[2].as_of != projection.as_of
            or records[2].available_at != projection.generated_at
            or transaction.committed_at != brief.generated_at
            or transaction.committed_at != receipt.created_at
            or transaction.committed_at != projection.generated_at
        ):
            raise CaseBriefStatusSynthesisError("status second-phase envelopes do not match exact replayed contracts")
        try:
            reconstructed = AppendOnlyTransactionRequestV1(
                product_id=self.product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_status_transaction_key(synthesis_key, profile=self.profile),
                records=tuple(records),
                submitted_at=transaction.committed_at,
                governed_state_preconditions=transaction.governed_state_preconditions,
            )
        except Exception:
            reconstructed = None
        if reconstructed is None or transaction != reconstructed.receipt():
            raise CaseBriefStatusSynthesisError("status second-phase transaction identity failed closed")
        return PreparedStatusCaseBriefAppendAdmission(
            brief=brief,
            synthesis_receipt=receipt,
            status_projection=projection,
            transaction_receipt=transaction,
            replayed=True,
        )

    async def append(
        self,
        packet: PreparedStatusCaseBriefAppendV1Alpha1,
        *,
        state_preconditions: tuple[GovernedStateHeadPreconditionV1Alpha1, ...],
    ) -> PreparedStatusCaseBriefAppendAdmission:
        try:
            exact = self.profile.append_model.model_validate(packet.model_dump(mode="python"))
        except Exception:
            raise CaseBriefStatusSynthesisError("prepared status Case Brief append failed exact revalidation") from None
        if exact.brief.product_id != self.product_id:
            raise CaseBriefStatusSynthesisError("prepared status Case Brief append crossed exact product scope")
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
            transaction_key=_status_transaction_key(exact.synthesis_key, profile=self.profile),
            records=(
                _brief_record(exact.brief),
                _synthesis_record(exact.synthesis_receipt),
                _projection_record(exact.status_projection, profile=self.profile),
            ),
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
                raise CaseBriefStatusSynthesisReplayConflict(
                    "concurrent status second-phase append did not expose exact durable material"
                ) from None
            return replay
        except ImmutableRecordPersistenceError:
            replay = await self.replay(
                synthesis_key=exact.synthesis_key,
                request_id=exact.request_id,
                request_digest=exact.request_digest,
            )
            if replay is None:
                raise CaseBriefStatusSynthesisError(
                    "atomic Brief, receipt, and status-projection append failed closed"
                ) from None
            return replay
        except Exception:
            raise CaseBriefStatusSynthesisError(
                "atomic Brief, receipt, and status-projection append failed closed"
            ) from None
        if transaction != request.receipt():
            raise CaseBriefStatusSynthesisError("Core append receipt does not bind the exact second-phase request")
        return PreparedStatusCaseBriefAppendAdmission(
            brief=exact.brief,
            synthesis_receipt=exact.synthesis_receipt,
            status_projection=exact.status_projection,
            transaction_receipt=transaction,
            replayed=False,
        )


class CaseBriefStatusSynthesisService(CaseBriefSynthesisService):
    """Case-bound synthesis that also binds and persists per-statement status."""

    #: Which status-module version, contract family, and record kind this
    #: service writes. Subclasses override it; the code path is shared.
    _PROFILE: StatusAppendProfile = STATUS_PROFILE_V1ALPHA1

    # -- Pack-declared status vocabulary ---------------------------------

    @classmethod
    def _status_policy(
        cls,
        *,
        binding,
        policy: ResolvedBriefSynthesisPolicy,
    ) -> ResolvedEpistemicStatusPolicy:
        try:
            resolved = resolve_epistemic_status_policy(binding, template_id=policy.template.template_id)
        except PreparedActivationBindingError as exc:
            raise CaseBriefStatusSynthesisError(
                "the routed Brief template is not governed by exactly one declared epistemic status set"
            ) from exc
        if resolved.module_contract != cls._PROFILE.module_contract:
            raise CaseBriefStatusSynthesisError(
                "the governing epistemic status module does not match this synthesis service version"
            )
        return resolved

    @staticmethod
    def _status_instructions(
        policy: ResolvedBriefSynthesisPolicy,
        status_policy: ResolvedEpistemicStatusPolicy,
        *,
        case: CaseV1Alpha1,
    ) -> str:
        """Publish the exact declared vocabulary the provider must choose from."""

        return canonical_json(
            {
                "brief_type": policy.template.brief_type,
                "case_boundary": {
                    "case_id": str(case.resource_id),
                    "case_type_ref": case.case_type_ref,
                    "member_ids": sorted(item.resource_id for item in case.lineage),
                },
                "claim_policy": policy.template.claim_policy,
                "epistemic_status_policy": {
                    "require_status_for_every_claim": (status_policy.status_set.require_status_for_every_claim),
                    "status_set_id": status_policy.status_set.status_set_id,
                    "statuses": [
                        {
                            "allowed_grounding_kinds": [item.value for item in declaration.allowed_grounding_kinds],
                            "allowed_support_kinds": [item.value for item in declaration.allowed_support_kinds],
                            "definition": declaration.definition,
                            "max_support_count": declaration.max_support_count,
                            "min_distinct_support_kinds": declaration.min_distinct_support_kinds,
                            "min_support_count": declaration.min_support_count,
                            "required_support_kinds": [item.value for item in declaration.required_support_kinds],
                            "requires_uncertainty": declaration.requires_uncertainty,
                            "status_id": declaration.status_id,
                        }
                        for declaration in status_policy.status_set.statuses
                    ],
                },
                "instruction_authority": "trusted_application",
                "objective": policy.template.objective,
                "output_contract": "ace.intelligence.brief-synthesis-draft/v1alpha2",
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

    @staticmethod
    def _support_kind_index(resolved: ResolvedCaseClosure) -> dict[str, LineageResourceKind]:
        return {
            str(item.resource_id): LineageResourceKind(resource_reference(item).resource_kind.value)
            for item in resolved.closure
        }

    # -- frozen Core request ---------------------------------------------

    async def _freeze_status_reasoning_request(
        self,
        *,
        request: CaseBriefSynthesisRequestV1Alpha1,
        ledger: PreparedIntelligenceLedgerService,
        activation_precondition: GovernedStateHeadPreconditionV1Alpha1,
        policy: ResolvedBriefSynthesisPolicy,
        status_policy: ResolvedEpistemicStatusPolicy,
        resolved: ResolvedCaseClosure,
    ) -> tuple[tuple, GovernedReasoningRequestV1Alpha1]:
        """Reconstruct the one exact authenticated Core request for live use or replay."""

        try:
            exact_execution_binding = ReasoningExecutionBindingV1Alpha1.model_validate(
                self.execution_binding.model_dump(mode="python")
            )
        except Exception:
            raise CaseBriefStatusSynthesisError("host reasoning binding failed exact revalidation") from None
        if exact_execution_binding.product_id != request.product_id:
            raise CaseBriefStatusSynthesisError("host reasoning binding crossed exact product scope")
        frozen = []
        for resource in resolved.closure:
            try:
                item = await ledger.freeze_exact(resource_reference(resource))
            except PreparedIntelligenceAdmissionError as exc:
                raise CaseBriefStatusSynthesisError("exact context freeze/revalidation failed") from exc
            except Exception:
                raise CaseBriefStatusSynthesisError("exact context freeze lower-port failure") from None
            if item is None:
                raise CaseBriefStatusSynthesisError("exact Case context disappeared before Core request reconstruction")
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
                instruction_json=self._status_instructions(policy, status_policy, case=resolved.case),
                context_items=tuple(frozen),
                cutoff_at=request.context_cutoff_at,
                requested_at=request.requested_at,
                required_state_preconditions=(
                    activation_precondition,
                    exact_execution_binding.state_head_precondition,
                ),
            )
        except Exception:
            raise CaseBriefStatusSynthesisError(
                "exact governed reasoning request reconstruction failed closed"
            ) from None
        return tuple(frozen), reasoning_request

    # -- status derivation -----------------------------------------------

    def _status_projection(
        self,
        *,
        request: CaseBriefSynthesisRequestV1Alpha1,
        status_policy: ResolvedEpistemicStatusPolicy,
        draft: BriefSynthesisDraftV1Alpha2,
        assembly,
        resolved: ResolvedCaseClosure,
        brief_id: str,
        brief_digest: str,
        receipt: CaseBriefSynthesisReceiptV1Alpha1,
        generated_at: datetime,
    ) -> BriefEpistemicStatusProjectionV1Alpha1:
        try:
            claim_statuses = derive_claim_epistemic_statuses(
                draft=draft,
                policy=status_policy,
                claim_supports=assembly.claim_supports,
                kind_by_record_id=self._support_kind_index(resolved),
            )
        except EpistemicStatusValidationError as exc:
            raise CaseBriefStatusSynthesisError(
                f"structured output violates the declared epistemic status policy: {exc}"
            ) from exc
        try:
            return BriefEpistemicStatusProjectionV1Alpha1(
                product_id=request.product_id,
                activation_revision=request.activation_revision,
                brief_id=brief_id,
                brief_digest=brief_digest,
                synthesis_receipt_contract=receipt.contract,
                synthesis_receipt_id=str(receipt.receipt_id),
                synthesis_receipt_digest=str(receipt.receipt_digest),
                module_id=status_policy.module_id,
                module_digest=status_policy.module_digest,
                status_set_id=status_policy.status_set.status_set_id,
                status_set_digest=status_policy.status_set_digest,
                template_id=status_policy.template_id,
                declared_status_ids=tuple(item.status_id for item in status_policy.status_set.statuses),
                claim_statuses=claim_statuses,
                as_of=request.brief_as_of,
                generated_at=generated_at,
            )
        except (TypeError, ValueError) as exc:
            raise CaseBriefStatusSynthesisError("durable status projection failed exact assembly") from exc

    # -- deterministic replay --------------------------------------------

    async def _validate_replayed_status_admission(
        self,
        admission: PreparedStatusCaseBriefAppendAdmission,
        request: CaseBriefSynthesisRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None,
    ) -> PreparedStatusCaseBriefAppendAdmission:
        receipt = admission.synthesis_receipt
        projection = admission.status_projection
        if (
            receipt.product_id != request.product_id
            or receipt.synthesis_key != request.synthesis_key
            or receipt.reasoning_attempt_key != request.reasoning_attempt_key
            or receipt.request_id != request.request_id
            or receipt.request_digest != request.request_digest
            or receipt.case != request.case
            or receipt.member_attention != request.member_attention
        ):
            raise CaseBriefStatusSynthesisReplayConflict(
                "status synthesis key crossed incoming request, Case, or attention identity"
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
                raise CaseBriefStatusSynthesisError("replayed synthesis lost its exact historical activation commit")
            binding = bind_committed_activation(pack=historical_pack, committed=historical)
        except (DomainActivationAdmissionError, ValueError):
            raise CaseBriefStatusSynthesisError("replayed historical activation failed exact validation") from None
        if (
            binding.prepared_binding.reference != request.activation_revision
            or binding.prepared_binding.revision.spec.pack != request.pack
        ):
            raise CaseBriefStatusSynthesisError("replayed synthesis crossed its historical activation or Pack IR")
        activation_precondition = _activation_precondition(binding)
        ledger = PreparedIntelligenceLedgerService(binding=binding, store=self.store)
        resolved = await self._resolve_case_closure(request=request, ledger=ledger)
        policy, persona_ids = self._compatible_route(
            binding=binding.prepared_binding,
            attention=resolved.attention,
        )
        status_policy = self._status_policy(binding=binding.prepared_binding, policy=policy)
        if (
            projection.module_id != status_policy.module_id
            or projection.module_digest != status_policy.module_digest
            or projection.status_set_id != status_policy.status_set.status_set_id
            or projection.status_set_digest != status_policy.status_set_digest
            or projection.template_id != status_policy.template_id
            or projection.declared_status_ids
            != tuple(sorted(item.status_id for item in status_policy.status_set.statuses))
        ):
            raise CaseBriefStatusSynthesisError(
                "replayed status projection crossed its exact declared Pack status policy"
            )
        if (
            receipt.activation_revision != request.activation_revision
            or receipt.pack != request.pack
            or receipt.case_member_ids != tuple(sorted(item.resource_id for item in resolved.case.lineage))
            or receipt.module_id != policy.module_id
            or receipt.module_digest != policy.module_digest
            or receipt.template_id != policy.template.template_id
            or receipt.template_digest != policy.template_digest
            or receipt.persona_ids != persona_ids
            or receipt.required_section_ids != policy.template.required_sections
        ):
            raise CaseBriefStatusSynthesisError(
                "replayed synthesis receipt crossed activation, Case membership, or template policy"
            )

        frozen, _ = await self._freeze_status_reasoning_request(
            request=request,
            ledger=ledger,
            activation_precondition=activation_precondition,
            policy=policy,
            status_policy=status_policy,
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
            raise CaseBriefStatusSynthesisError(
                "replayed selected resources do not match reconstructed Core frozen context"
            )
        try:
            current_delivery = delivery_context or request.authenticated_context
            outcome = await self.reasoning.execute_historical(
                product_id=request.product_id,
                attempt_key=request.reasoning_attempt_key,
                expected_request_id=receipt.reasoning_request_id,
                expected_request_digest=receipt.reasoning_request_digest,
                instruction_json=self._status_instructions(policy, status_policy, case=resolved.case),
                context_items=frozen,
                cutoff_at=request.context_cutoff_at,
                requested_at=request.requested_at,
                delivery_context=current_delivery,
                delivery_binding=self.execution_binding,
            )
        except GovernedReasoningError:
            raise CaseBriefStatusSynthesisError(
                "replayed status Brief failed exact governed Core request replay"
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
            raise CaseBriefStatusSynthesisError(
                "replayed synthesis receipt crossed exact Core context or terminal material"
            )

        lineage_by_id = {item.resource_id: item for item in admission.brief.lineage}
        expected_records = {str(item.resource_id): resource_reference(item) for item in resolved.closure}
        selected_records = {item.record.resource_id: item.record for item in receipt.selected_context}
        if selected_records != expected_records:
            raise CaseBriefStatusSynthesisError("replayed selected context differs from exact Case closure")
        for selected in receipt.selected_context:
            reference = selected.record
            lineage = lineage_by_id.get(reference.resource_id)
            if lineage is None or (
                lineage.resource_digest != reference.resource_digest
                or lineage.resource_as_of != reference.as_of
                or lineage.resource_available_at != reference.available_at
            ):
                raise CaseBriefStatusSynthesisError("replayed Brief lineage differs from selected context mapping")
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
                raise CaseBriefStatusSynthesisError("replayed selected record load failed closed") from None
            if stored is None or (
                stored.storage_id != selected.context.storage_id
                or stored.material_hash != selected.context.material_digest
                or stored.record_key != reference.resource_id
                or stored.payload_contract != reference.resource_contract
                or stored.as_of != reference.as_of
                or stored.available_at != reference.available_at
            ):
                raise CaseBriefStatusSynthesisError("replayed selected Intelligence record changed Core frozen mapping")
        if set(lineage_by_id) != {item.record.resource_id for item in receipt.selected_context}:
            raise CaseBriefStatusSynthesisError("replayed Brief contains lineage outside exact selected context")

        try:
            core_draft = BriefSynthesisDraftV1Alpha2.model_validate_json(outcome.result.structured_json)
            assembly = assemble_canonical_brief(
                product_id=request.product_id,
                activation_revision=request.activation_revision,
                brief_as_of=request.brief_as_of,
                generated_at=receipt.created_at,
                draft=core_draft,
                policy=policy,
                closure=resolved.closure,
                observations=resolved.observations,
                selected_context=receipt.selected_context,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise CaseBriefStatusSynthesisError("Core structured result fails replayed synthesis policy") from exc
        if (
            assembly.brief != admission.brief
            or assembly.selected_context != receipt.selected_context
            or assembly.required_section_ids != receipt.required_section_ids
            or assembly.actual_section_ids != receipt.actual_section_ids
            or assembly.section_claims != receipt.section_claims
            or assembly.recommendation_claim_id != receipt.recommendation_claim_id
            or assembly.claim_supports != receipt.claim_supports
        ):
            raise CaseBriefStatusSynthesisError("replayed Brief is not the canonical rendering of receipted claims")
        replayed_projection = self._status_projection(
            request=request,
            status_policy=status_policy,
            draft=core_draft,
            assembly=assembly,
            resolved=resolved,
            brief_id=str(assembly.brief.resource_id),
            brief_digest=str(assembly.brief.resource_digest),
            receipt=receipt,
            generated_at=receipt.created_at,
        )
        if replayed_projection != projection:
            raise CaseBriefStatusSynthesisError(
                "replayed per-statement epistemic status differs from the durable projection"
            )
        try:
            write_authorization = await self.reasoning.verify_action_reference(
                product_id=request.product_id,
                operation="append_immutable_records",
                subject_ref=receipt.write_intent_id,
                subject_digest=receipt.write_intent_digest,
                expected=receipt.write_authorization,
            )
        except GovernedReasoningError:
            raise CaseBriefStatusSynthesisError(
                "replayed status Brief lost exact private append authorization"
            ) from None
        intent = _status_append_intent(
            request=request,
            status_policy=status_policy,
            profile=self._PROFILE,
            semantic_input_digest=_authorization_neutral_payload_digest(
                brief=admission.brief,
                receipt=receipt,
                projection=projection,
                profile=self._PROFILE,
            ),
            governed_state_identities=tuple(
                sorted(
                    f"{item.state_kind}|{item.product_id}|{item.state_id}"
                    for item in write_authorization.state_preconditions
                )
            ),
        )
        if receipt.write_intent_id != intent.intent_id or receipt.write_intent_digest != intent.intent_digest:
            raise CaseBriefStatusSynthesisError("replayed append intent differs from exact historical synthesis")
        expected_preconditions = _assert_status_append_realizes_intent(
            intent=intent,
            profile=self._PROFILE,
            packet=self._PROFILE.append_model(
                synthesis_key=request.synthesis_key,
                request_id=str(request.request_id),
                request_digest=str(request.request_digest),
                brief=admission.brief,
                synthesis_receipt=receipt,
                status_projection=projection,
                submitted_at=receipt.created_at,
            ),
            authorization=write_authorization,
        )
        if (
            admission.transaction_receipt.governed_state_preconditions != expected_preconditions
            or admission.transaction_receipt.committed_at != receipt.created_at
            or receipt.created_at != admission.brief.generated_at
            or receipt.created_at != projection.generated_at
            or receipt.created_at != write_authorization.authorized_at
        ):
            raise CaseBriefStatusSynthesisError(
                "replayed status Brief append crossed exact governed heads or commit time"
            )
        return admission

    # -- public entry point ----------------------------------------------

    async def synthesize_with_status(
        self,
        request: CaseBriefSynthesisRequestV1Alpha1,
        *,
        delivery_context: AuthenticatedRuntimeContextV1Alpha1 | None = None,
    ) -> PreparedStatusCaseBriefAppendAdmission:
        """Bind one exact Case and persist one Brief with per-statement status."""

        validated = self._revalidate_request(request)
        append_service = _PreparedStatusCaseBriefAppendService(
            product_id=validated.product_id,
            store=self.store,
            profile=self._PROFILE,
        )
        replay = await append_service.replay(
            synthesis_key=validated.synthesis_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
        )
        if replay is not None:
            return await self._validate_replayed_status_admission(
                replay,
                validated,
                delivery_context=delivery_context,
            )

        binding = await self._load_binding(validated)
        activation_precondition = _activation_precondition(binding)
        ledger = PreparedIntelligenceLedgerService(binding=binding, store=self.store)
        resolved = await self._resolve_case_closure(request=validated, ledger=ledger)
        policy, persona_ids = self._compatible_route(
            binding=binding.prepared_binding,
            attention=resolved.attention,
        )
        status_policy = self._status_policy(binding=binding.prepared_binding, policy=policy)
        frozen, reasoning_request = await self._freeze_status_reasoning_request(
            request=validated,
            ledger=ledger,
            activation_precondition=activation_precondition,
            policy=policy,
            status_policy=status_policy,
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
            raise CaseBriefStatusSynthesisError("Core governed reasoning failed closed") from exc
        expected_context_ids = {str(item.context_id) for item in frozen}
        if set(outcome.result.referenced_context_ids) != expected_context_ids:
            raise CaseBriefStatusSynthesisError("structured output did not attribute every exact selected context item")
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
            raise CaseBriefStatusSynthesisError("Core terminal context uses do not match exact frozen mapping")
        try:
            draft = BriefSynthesisDraftV1Alpha2.model_validate_json(outcome.result.structured_json)
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise CaseBriefStatusSynthesisError(
                "provider output violates exact status-aware Brief synthesis policy"
            ) from exc

        post_binding = await self._load_binding(validated)
        post_precondition = _activation_precondition(post_binding)
        if post_precondition != activation_precondition:
            raise CaseBriefStatusSynthesisError("committed activation changed during Case Brief synthesis")
        post_resolved = await self._resolve_case_closure(request=validated, ledger=ledger)
        if post_resolved.closure != resolved.closure or post_resolved.attention != resolved.attention:
            raise CaseBriefStatusSynthesisError("the exact Case closure changed during governed reasoning")
        activation_commit = _activation_receipt_reference(binding)
        try:
            provisional_assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.brief_as_of,
                generated_at=outcome.result.completed_at,
                draft=draft,
                policy=policy,
                closure=resolved.closure,
                observations=resolved.observations,
                selected_context=context_mapping,
            )
            provisional_receipt = self._receipt(
                request=validated,
                resolved=resolved,
                activation_commit=activation_commit,
                policy=policy,
                persona_ids=persona_ids,
                outcome=outcome,
                assembly=provisional_assembly,
                write_intent_id=self._PROFILE.zero_intent_id,
                write_intent_digest=_ZERO_DIGEST,
                write_authorization=_ZERO_AUTHORIZATION,
                created_at=outcome.result.completed_at,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise CaseBriefStatusSynthesisError("Core draft failed provisional append-recipe assembly") from exc
        provisional_projection = self._status_projection(
            request=validated,
            status_policy=status_policy,
            draft=draft,
            assembly=provisional_assembly,
            resolved=resolved,
            brief_id=str(provisional_assembly.brief.resource_id),
            brief_digest=str(provisional_assembly.brief.resource_digest),
            receipt=provisional_receipt,
            generated_at=outcome.result.completed_at,
        )
        semantic_input_digest = _authorization_neutral_payload_digest(
            brief=provisional_assembly.brief,
            receipt=provisional_receipt,
            projection=provisional_projection,
            profile=self._PROFILE,
        )
        intent = _status_append_intent(
            request=validated,
            status_policy=status_policy,
            profile=self._PROFILE,
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
            raise CaseBriefStatusSynthesisError("current authority denied exact atomic append subject") from None
        generated_at = write_authorization.authorized_at
        if generated_at < outcome.result.completed_at:
            raise CaseBriefStatusSynthesisError("durable append authorization predates Core reasoning completion")
        try:
            assembly = assemble_canonical_brief(
                product_id=validated.product_id,
                activation_revision=validated.activation_revision,
                brief_as_of=validated.brief_as_of,
                generated_at=generated_at,
                draft=draft,
                policy=policy,
                closure=resolved.closure,
                observations=resolved.observations,
                selected_context=context_mapping,
            )
        except (TypeError, ValueError, BriefDraftValidationError) as exc:
            raise CaseBriefStatusSynthesisError("Core draft failed canonical Brief assembly") from exc
        synthesis_receipt = self._receipt(
            request=validated,
            resolved=resolved,
            activation_commit=activation_commit,
            policy=policy,
            persona_ids=persona_ids,
            outcome=outcome,
            assembly=assembly,
            write_intent_id=str(intent.intent_id),
            write_intent_digest=str(intent.intent_digest),
            write_authorization=write_authorization.authorization_ref,
            created_at=generated_at,
        )
        status_projection = self._status_projection(
            request=validated,
            status_policy=status_policy,
            draft=draft,
            assembly=assembly,
            resolved=resolved,
            brief_id=str(assembly.brief.resource_id),
            brief_digest=str(assembly.brief.resource_digest),
            receipt=synthesis_receipt,
            generated_at=generated_at,
        )
        packet = self._PROFILE.append_model(
            synthesis_key=validated.synthesis_key,
            request_id=str(validated.request_id),
            request_digest=str(validated.request_digest),
            brief=assembly.brief,
            synthesis_receipt=synthesis_receipt,
            status_projection=status_projection,
            submitted_at=generated_at,
        )
        state_preconditions = _assert_status_append_realizes_intent(
            intent=intent,
            packet=packet,
            authorization=write_authorization,
            profile=self._PROFILE,
        )
        admission = await append_service.append(packet, state_preconditions=state_preconditions)
        if admission.replayed:
            return await self._validate_replayed_status_admission(
                admission,
                validated,
                delivery_context=delivery_context,
            )
        return admission


__all__ = [
    "CaseBriefStatusSynthesisError",
    "CaseBriefStatusSynthesisReplayConflict",
    "CaseBriefStatusSynthesisService",
    "PreparedStatusCaseBriefAppendAdmission",
]
