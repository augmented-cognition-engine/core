"""Governed, append-only durable supersession-impact projection.

This service computes one impact projection with
:mod:`ace.intelligence.supersession` and appends it as a **single** immutable
record under governed authorization. It is deliberately the smallest durable
surface in the codebase: one record, one transaction key, no reasoning provider,
no Brief, no Case mutation.

Append-only, never rewriting
----------------------------
The projection names the artifacts it explains and carries them in
``preserved_artifact_ids``. It never touches them. A Brief written before the
correction keeps its exact identity and replays under its original cutoff; this
record is simply a later, additive statement about what has since been
superseded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from ace.application.brief_synthesis import (
    _activation_precondition,
    _authorization_attempt_key,
    _operation_state_identities,
)
from ace.application.domain_activation import (
    DomainActivationAdmissionService,
    bind_committed_activation,
)
from ace.application.intelligence_ledger import PREPARED_RECORD_SPACE
from ace.core.contracts import canonical_hash
from ace.core.reasoning import (
    GovernedActionAuthorizationRequestV1Alpha1,
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningError,
    GovernedReasoningService,
)
from ace.core.records import (
    AppendOnlyTransactionReceiptV1,
    AppendOnlyTransactionRequestV1,
    ImmutableRecordPersistenceError,
    ImmutableRecordReplayConflict,
    ImmutableRecordStore,
    ImmutableRecordV1,
)
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.ledger import resource_reference
from ace.intelligence.contracts.pack import CompiledDomainPackV1
from ace.intelligence.contracts.resources import IntelligenceResourceMode, LineageResourceKind
from ace.intelligence.contracts.supersession import (
    SUPERSESSION_IMPACT_PROJECTION_KIND,
    SupersessionClaimImpactV1Alpha1,
    SupersessionImpactPathV1Alpha1,
    SupersessionImpactProjectionV1Alpha1,
)
from ace.intelligence.supersession import (
    IMPACT_RELATIONS,
    SUPERSESSION_IMPACT_POLICY,
    SupersessionImpactError,
    project_claim_impact,
    project_supersession_impact,
)


class SupersessionImpactAdmissionError(ValueError):
    """Durable supersession-impact projection or replay failed closed."""


class SupersessionImpactReplayConflict(SupersessionImpactAdmissionError):
    """A stable impact key already binds different projection material."""


@dataclass(frozen=True, slots=True)
class SupersessionImpactAdmission:
    """Exact replayable durable impact projection."""

    projection: SupersessionImpactProjectionV1Alpha1
    transaction_receipt: AppendOnlyTransactionReceiptV1
    replayed: bool
    mode: Literal[IntelligenceResourceMode.PREPARED] = IntelligenceResourceMode.PREPARED


def _transaction_key(impact_key: str) -> str:
    return f"supersession_impact:{canonical_hash([impact_key, 'supersession_impact'])[:32]}"


def supersession_impact_record(
    projection: SupersessionImpactProjectionV1Alpha1,
) -> ImmutableRecordV1:
    """Materialize the exact durable envelope for one impact projection."""

    return ImmutableRecordV1(
        product_id=projection.product_id,
        record_space=PREPARED_RECORD_SPACE,
        record_kind=SUPERSESSION_IMPACT_PROJECTION_KIND,
        record_key=str(projection.projection_id),
        payload_contract=projection.contract,
        payload=projection.model_dump(mode="python"),
        as_of=projection.as_of,
        available_at=projection.generated_at,
        processing_order=0,
    )


class SupersessionImpactService:
    """Project and durably append what depended on a superseded record."""

    def __init__(
        self,
        *,
        activation_service: DomainActivationAdmissionService,
        pack: CompiledDomainPackV1,
        store: ImmutableRecordStore,
        reasoning: GovernedReasoningService,
        append_binding: GovernedOperationBindingV1Alpha1,
        clock: Callable[[], datetime],
    ) -> None:
        self.activation_service = activation_service
        self.pack = CompiledDomainPackV1.model_validate(pack.model_dump(mode="python"))
        self.store = store
        self.reasoning = reasoning
        self.append_binding = GovernedOperationBindingV1Alpha1.model_validate(append_binding.model_dump(mode="python"))
        self.clock = clock

    # -- pure projection --------------------------------------------------

    @staticmethod
    def build_projection(
        *,
        product_id: str,
        activation_revision,
        superseder,
        superseded_resource_id: str,
        closure: tuple,
        cutoff_at: datetime,
        generated_at: datetime,
        as_of: datetime,
        brief_id: str | None = None,
        claim_supports: tuple = (),
        preserved_artifact_ids: tuple[str, ...] = (),
    ) -> SupersessionImpactProjectionV1Alpha1:
        """Compute one exact impact projection, or fail closed."""

        try:
            impact = project_supersession_impact(
                superseder=superseder,
                superseded_resource_id=superseded_resource_id,
                closure=closure,
                cutoff_at=cutoff_at,
            )
        except SupersessionImpactError as exc:
            raise SupersessionImpactAdmissionError(f"supersession impact failed closed: {exc}") from exc
        claim_impacts: tuple[SupersessionClaimImpactV1Alpha1, ...] = ()
        if brief_id is not None and claim_supports:
            try:
                claim_impacts = tuple(
                    SupersessionClaimImpactV1Alpha1(
                        brief_id=brief_id,
                        claim_id=claim_id,
                        impacted_support_record_ids=touched,
                        total_support_count=total,
                        fully_impacted=full,
                    )
                    for claim_id, touched, total, full in project_claim_impact(
                        impact=impact,
                        brief_id=brief_id,
                        claim_supports=claim_supports,
                    )
                )
            except (SupersessionImpactError, TypeError, ValueError) as exc:
                raise SupersessionImpactAdmissionError("Brief claim impact failed exact assembly") from exc
        superseder_reference = resource_reference(superseder)
        target_reference = resource_reference(
            next(item for item in closure if str(item.resource_id) == superseded_resource_id)
        )
        try:
            return SupersessionImpactProjectionV1Alpha1(
                product_id=product_id,
                activation_revision=activation_revision,
                superseder_resource_id=impact.superseder_resource_id,
                superseder_resource_digest=superseder_reference.resource_digest,
                superseder_available_at=superseder_reference.available_at,
                superseded_resource_id=impact.superseded_resource_id,
                superseded_resource_digest=target_reference.resource_digest,
                superseded_resource_kind=LineageResourceKind(target_reference.resource_kind.value),
                impact_policy=SUPERSESSION_IMPACT_POLICY,
                eligible_relations=tuple(item.value for item in IMPACT_RELATIONS),
                closure_cutoff_at=cutoff_at,
                closure_resource_ids=impact.closure_resource_ids,
                impacted=tuple(
                    SupersessionImpactPathV1Alpha1(
                        resource_id=item.resource_id,
                        resource_kind=item.resource_kind,
                        resource_digest=item.resource_digest,
                        depth=item.depth,
                        via_resource_id=item.via_resource_id,
                        via_relation=item.via_relation,
                    )
                    for item in impact.impacted
                ),
                unaffected_resource_ids=impact.unaffected_resource_ids,
                claim_impacts=claim_impacts,
                preserved_artifact_ids=preserved_artifact_ids,
                as_of=as_of,
                generated_at=generated_at,
            )
        except (TypeError, ValueError) as exc:
            raise SupersessionImpactAdmissionError(
                "durable supersession-impact projection failed exact assembly"
            ) from exc

    # -- durable append ---------------------------------------------------

    async def _replay(
        self,
        *,
        product_id: str,
        impact_key: str,
        expected_projection_id: str | None,
    ) -> SupersessionImpactAdmission | None:
        try:
            transaction = await self.store.load_transaction_receipt(
                product_id=product_id,
                record_space=PREPARED_RECORD_SPACE,
                transaction_key=_transaction_key(impact_key),
            )
        except Exception:
            raise SupersessionImpactAdmissionError("impact transaction load failed closed") from None
        if transaction is None:
            return None
        if len(transaction.records) != 1 or transaction.records[0].record_kind != (SUPERSESSION_IMPACT_PROJECTION_KIND):
            raise SupersessionImpactAdmissionError("impact transaction does not contain exactly one projection record")
        reference = transaction.records[0]
        try:
            stored = await self.store.load_record(
                reference.storage_id,
                product_id=product_id,
                record_space=PREPARED_RECORD_SPACE,
                record_kind=reference.record_kind,
            )
        except Exception:
            stored = None
        if stored is None or stored.reference() != reference:
            raise SupersessionImpactAdmissionError("impact transaction references missing or changed material")
        try:
            projection = SupersessionImpactProjectionV1Alpha1.model_validate(stored.payload)
        except Exception:
            raise SupersessionImpactAdmissionError("impact transaction failed exact contract replay") from None
        if (
            stored.record_key != projection.projection_id
            or stored.payload_contract != projection.contract
            or stored.as_of != projection.as_of
            or stored.available_at != projection.generated_at
            or transaction.committed_at != projection.generated_at
        ):
            raise SupersessionImpactAdmissionError("impact envelope does not match its exact replayed contract")
        if expected_projection_id is not None and projection.projection_id != expected_projection_id:
            raise SupersessionImpactReplayConflict("impact key already binds a different exact projection")
        return SupersessionImpactAdmission(
            projection=projection,
            transaction_receipt=transaction,
            replayed=True,
        )

    @staticmethod
    def _authorization_neutral_digest(projection: SupersessionImpactProjectionV1Alpha1) -> str:
        """Digest the semantic inputs, excluding everything authorization sets."""

        material = {
            "recipe": "ace.intelligence.supersession-impact-neutral-payload/v1alpha1",
            "projection": projection.model_dump(
                mode="json",
                exclude={"generated_at", "projection_id", "projection_digest"},
            ),
        }
        return f"sha256:{canonical_hash(material)}"

    async def project_and_append(
        self,
        *,
        impact_key: str,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        activation_key: str,
        **build: object,
    ) -> SupersessionImpactAdmission:
        """Authorize, stamp, and durably append one exact impact projection.

        The append time is the governed authorization time, exactly as for Brief
        synthesis, so the projection cannot claim to exist before authority
        granted it. The authorization subject is therefore an
        authorization-neutral digest of the semantic inputs.
        """

        product_id = str(build["product_id"])
        provisional = self.build_projection(generated_at=self.clock(), **build)  # type: ignore[arg-type]
        neutral = self._authorization_neutral_digest(provisional)
        replay = await self._replay(
            product_id=product_id,
            impact_key=impact_key,
            expected_projection_id=None,
        )
        if replay is not None:
            if self._authorization_neutral_digest(replay.projection) != neutral:
                raise SupersessionImpactReplayConflict("impact key already binds different exact projection material")
            return replay

        try:
            committed = await self.activation_service.reload(
                product_id=product_id,
                activation_key=activation_key,
            )
            if committed is None:
                raise SupersessionImpactAdmissionError("current committed activation is missing")
            binding = bind_committed_activation(pack=self.pack, committed=committed)
        except SupersessionImpactAdmissionError:
            raise
        except Exception:
            raise SupersessionImpactAdmissionError("current committed activation failed exact reload") from None
        if binding.prepared_binding.reference != provisional.activation_revision:
            raise SupersessionImpactAdmissionError("impact projection does not bind the current committed activation")
        activation_precondition = _activation_precondition(binding)
        required = (activation_precondition, self.append_binding.state_head_precondition)
        authorization_request = GovernedActionAuthorizationRequestV1Alpha1(
            authorization_key=_authorization_attempt_key(
                synthesis_key=impact_key,
                context=authenticated_context,
                binding=self.append_binding,
                required_preconditions=required,
            ),
            product_id=product_id,
            authenticated_context=authenticated_context,
            execution_binding=self.append_binding,
            operation="append_immutable_records",
            subject_ref=f"supersession_impact_subject:{neutral.removeprefix('sha256:')[:32]}",
            subject_digest=neutral,
            requested_at=max(provisional.superseder_available_at, authenticated_context.authenticated_at),
            required_state_preconditions=required,
        )
        try:
            authorization = await self.reasoning.authorize_action(authorization_request)
        except GovernedReasoningError:
            raise SupersessionImpactAdmissionError("current authority denied the exact impact append subject") from None
        identities = tuple(
            sorted(f"{item.state_kind}|{item.product_id}|{item.state_id}" for item in authorization.state_preconditions)
        )
        if identities != _operation_state_identities(
            activation=activation_precondition,
            binding=self.append_binding,
        ):
            raise SupersessionImpactAdmissionError("authorized governed heads do not match the exact append binding")
        exact = self.build_projection(generated_at=authorization.authorized_at, **build)  # type: ignore[arg-type]
        if self._authorization_neutral_digest(exact) != neutral:
            raise SupersessionImpactAdmissionError(
                "authorized impact material changed between authorization and append"
            )
        request = AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=PREPARED_RECORD_SPACE,
            transaction_key=_transaction_key(impact_key),
            records=(supersession_impact_record(exact),),
            submitted_at=exact.generated_at,
            governed_state_preconditions=authorization.state_preconditions,
        )
        try:
            transaction = await self.store.append(request)
        except (ImmutableRecordReplayConflict, ImmutableRecordPersistenceError):
            replay = await self._replay(
                product_id=product_id,
                impact_key=impact_key,
                expected_projection_id=str(exact.projection_id),
            )
            if replay is None:
                raise SupersessionImpactAdmissionError("atomic impact projection append failed closed") from None
            return replay
        except Exception:
            raise SupersessionImpactAdmissionError("atomic impact projection append failed closed") from None
        if transaction != request.receipt():
            raise SupersessionImpactAdmissionError("Core append receipt does not bind the exact impact request")
        return SupersessionImpactAdmission(
            projection=exact,
            transaction_receipt=transaction,
            replayed=False,
        )


__all__ = [
    "SupersessionImpactAdmission",
    "SupersessionImpactAdmissionError",
    "SupersessionImpactReplayConflict",
    "SupersessionImpactService",
    "supersession_impact_record",
]
