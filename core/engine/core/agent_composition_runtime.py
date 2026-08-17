"""Production host adapters for AC2 governed composition authority.

This host edge is deliberately internal.  It reads the existing Core governed
state plane, validates strict private payloads, persists append-only evidence,
and implements the existing ``RuntimeUseResolver`` protocol.  It neither
creates grants nor changes any public task or MCP contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Literal

from pydantic import ConfigDict, Field

from ace.application.agent_composition_runtime import (
    CompositionAuthorityResolutionReceiptV1Alpha1,
    ReasoningCompositionRuntimeAuthorityBundle,
    ReasoningCompositionRuntimeAuthorityPort,
    TaskAuthenticationReceiptV1Alpha1,
    exact_reference,
    validate_bundle_for_manifest,
)
from ace.core.agent_composition import (
    AuthorityClass,
    AuthorityCoordinateV1Alpha1,
    CompositionBudgetV1Alpha1,
    CompositionNodeKind,
    CompositionNodeV1Alpha1,
    CompositionParticipantV1Alpha1,
    ContextUseState,
    DomainActivationLineageV1Alpha1,
    ExactArtifactReferenceV1Alpha1,
    HandoffState,
    ParticipantKind,
    RunState,
    StageHandoffContractV1Alpha1,
    StageHandoffReceiptV1Alpha1,
    StageRunManifestV1Alpha1,
    StageRunReceiptV1Alpha1,
    TaskCompositionPlanV1Alpha1,
    UsageV1Alpha1,
    validate_run_receipt_against_manifest,
)
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.delegated_cognition import GRANT_PAYLOAD_CONTRACT, CompositionAuthorityGrantMaterial
from ace.core.reasoning import REASONING_CONFIGURATION_STATE_KIND, ReasoningExecutionBindingV1Alpha1
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordStore, ImmutableRecordV1
from ace.core.runtime_use import (
    AUTHORITY_GRANT_STATE_KIND,
    CAPABILITY_STATE_KIND,
    AuthenticatedRuntimeContextV1Alpha1,
    AuthorityUseReceiptV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    CapabilityUseReceiptV1Alpha1,
    RuntimeUseResolver,
    capability_state_ref_for_artifact,
)
from ace.core.state import (
    GovernedStateCommitReceiptV1,
    GovernedStateHeadPreconditionV1Alpha1,
    GovernedStateRevisionV1,
    GovernedStateStore,
)

COMPOSITION_RECORD_SPACE = "governed_agent_composition"
AUTH_PAYLOAD_CONTRACT = "ace.host.task-authentication-evidence/v1alpha1"
CAPABILITY_PAYLOAD_CONTRACT = "ace.host.composition-capability-state/v1alpha1"
CONFIGURATION_PAYLOAD_CONTRACT = "ace.host.reasoning-composition-configuration/v1alpha1"


class GovernedCompositionAuthorityError(RuntimeError):
    """Current composition authority was unavailable or inconsistent."""


class _Payload(FrozenContract):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class CompositionCapabilityStateMaterial(_Payload):
    contract: Literal["ace.host.composition-capability-state/v1alpha1"] = CAPABILITY_PAYLOAD_CONTRACT
    product_id: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    lifecycle: Literal["active", "suspended", "retired"]
    permitted_configuration_refs: tuple[str, ...] = Field(min_length=1, max_length=32)


class ReasoningCompositionConfigurationMaterial(_Payload):
    contract: Literal["ace.host.reasoning-composition-configuration/v1alpha1"] = CONFIGURATION_PAYLOAD_CONTRACT
    product_id: str
    configuration_ref: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    authority: AuthorityClass
    grant_ref: str
    lifecycle: Literal["active", "suspended", "retired"]


class BoundedReasoningArtifactRegistry:
    """Exact constructor-registered host capability identities."""

    def __init__(self, artifacts: Iterable[CapabilityArtifactIdentityV1Alpha1] = ()) -> None:
        self._artifacts: dict[tuple[str, str, str, str, str], CapabilityArtifactIdentityV1Alpha1] = {}
        for artifact in artifacts:
            self.register(artifact)

    @staticmethod
    def _key(artifact: CapabilityArtifactIdentityV1Alpha1) -> tuple[str, str, str, str, str]:
        return (
            artifact.capability,
            artifact.contract,
            artifact.implementation_id,
            artifact.implementation_version,
            artifact.artifact_digest,
        )

    def register(self, artifact: CapabilityArtifactIdentityV1Alpha1) -> None:
        exact = CapabilityArtifactIdentityV1Alpha1.model_validate(artifact.model_dump(mode="python"))
        key = self._key(exact)
        if key in self._artifacts:
            raise GovernedCompositionAuthorityError("reasoning artifact is already registered")
        self._artifacts[key] = exact

    def resolve(self, artifact: CapabilityArtifactIdentityV1Alpha1) -> CapabilityArtifactIdentityV1Alpha1 | None:
        return self._artifacts.get(self._key(artifact))


class _GovernedMaterial:
    def __init__(
        self,
        *,
        revision: GovernedStateRevisionV1,
        receipt: GovernedStateCommitReceiptV1,
        head: GovernedStateHeadPreconditionV1Alpha1,
    ) -> None:
        self.revision = revision
        self.receipt = receipt
        self.head = head


class GovernedStateRuntimeUseResolver(RuntimeUseResolver):
    """The single current-use evaluator backed by exact Core governed heads."""

    def __init__(self, *, governed_state: GovernedStateStore) -> None:
        self.governed_state = governed_state

    async def _load(self, *, state_kind: str, product_id: str, state_id: str) -> _GovernedMaterial:
        head = await self.governed_state.load_head(
            state_kind=state_kind,
            product_id=product_id,
            state_id=state_id,
        )
        if head is None:
            raise GovernedCompositionAuthorityError(f"missing current {state_kind} head")
        revision = await self.governed_state.load_revision(head.revision_id, product_id=product_id)
        receipt = await self.governed_state.load_receipt(head.commit_receipt_id, product_id=product_id)
        if revision is None or receipt is None:
            raise GovernedCompositionAuthorityError(f"incomplete current {state_kind} lineage")
        if (
            revision.state_kind != state_kind
            or revision.product_id != product_id
            or revision.state_id != state_id
            or revision.sequence != head.sequence
            or revision.revision_id != head.revision_id
            or receipt.state_kind != state_kind
            or receipt.product_id != product_id
            or receipt.state_id != state_id
            or receipt.sequence != head.sequence
            or receipt.revision_id != head.revision_id
            or receipt.receipt_id != head.commit_receipt_id
            or receipt.material_hash != revision.material_hash
        ):
            raise GovernedCompositionAuthorityError(f"current {state_kind} lineage is cross-wired")
        try:
            exact_head = GovernedStateHeadPreconditionV1Alpha1.from_head(head)
        except ValueError as exc:
            raise GovernedCompositionAuthorityError(f"current {state_kind} head failed exact validation") from exc
        return _GovernedMaterial(revision=revision, receipt=receipt, head=exact_head)

    async def load_grant(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        participant_principal_ref: str,
        authority_class: AuthorityClass,
        operation: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> tuple[CompositionAuthorityGrantMaterial, _GovernedMaterial]:
        material = await self._load(
            state_kind=AUTHORITY_GRANT_STATE_KIND,
            product_id=context.product_id,
            state_id=grant_ref,
        )
        if material.revision.payload_contract != GRANT_PAYLOAD_CONTRACT:
            raise GovernedCompositionAuthorityError("authority grant uses an unsupported private payload")
        try:
            # Durable stores return JSON-shaped values (lists, enum strings, and
            # decoded datetimes) rather than the strict Python construction shape.
            # Normalize that wire representation before the exact scope, operation,
            # lifecycle, head, and commit-receipt comparisons below fail closed.
            grant = CompositionAuthorityGrantMaterial.model_validate(material.revision.payload, strict=False)
        except ValueError as exc:
            raise GovernedCompositionAuthorityError("authority grant payload failed exact validation") from exc
        expected_grant_hash = canonical_hash(grant.model_dump(mode="json", exclude={"grant_hash"}))
        if (
            grant.grant_hash != expected_grant_hash
            or canonical_hash(grant.model_dump(mode="json")) != material.revision.material_hash
        ):
            raise GovernedCompositionAuthorityError(
                "authority grant payload no longer matches its admitted material hash"
            )
        if (
            grant.grant_ref != grant_ref
            or grant.product_id != context.product_id
            or grant.actor_ref != context.actor_ref
            or grant.participant_principal_ref != participant_principal_ref
            or grant.authority_class != authority_class
            or operation not in grant.operations
            or grant.scope_ref != scope_ref
            or grant.policy_ref != policy_ref
            or grant.lifecycle != "active"
            or grant.effective_at > evaluated_at
            or (grant.expires_at is not None and grant.expires_at <= evaluated_at)
            or grant.revoked_at is not None
        ):
            raise GovernedCompositionAuthorityError("authority grant is inactive, expired, revoked, or mismatched")
        matching = [item for item in material.receipt.authority_grants if item.grant_ref == grant_ref]
        if len(matching) != 1:
            raise GovernedCompositionAuthorityError("grant commit receipt lacks one exact resolved grant")
        resolved = matching[0]
        if (
            resolved.product_id != grant.product_id
            or resolved.authority != grant.authority_class.value
            or resolved.grant_hash != grant.grant_hash
            or resolved.state != "active"
            or resolved.effective_at != grant.effective_at
            or resolved.expires_at != grant.expires_at
        ):
            raise GovernedCompositionAuthorityError("grant payload disagrees with its exact commit receipt")
        return grant, material

    async def resolve_capability_use(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject_ref: str,
        use_subject_digest: str,
        operation: str,
        artifact: CapabilityArtifactIdentityV1Alpha1,
        capability_state_ref: str,
        configuration_ref: str,
        evaluated_at: datetime,
    ) -> CapabilityUseReceiptV1Alpha1:
        material = await self._load(
            state_kind=CAPABILITY_STATE_KIND,
            product_id=context.product_id,
            state_id=capability_state_ref,
        )
        if material.revision.payload_contract != CAPABILITY_PAYLOAD_CONTRACT:
            raise GovernedCompositionAuthorityError("capability state uses an unsupported private payload")
        try:
            # See load_grant: durable stores return JSON-shaped values (lists in
            # place of tuples, enum strings, decoded datetimes) rather than the
            # strict Python construction shape. Normalize that wire representation
            # before the exact artifact, lifecycle, and configuration comparisons
            # below fail closed.
            state = CompositionCapabilityStateMaterial.model_validate(material.revision.payload, strict=False)
        except ValueError as exc:
            raise GovernedCompositionAuthorityError("capability-state payload failed exact validation") from exc
        if canonical_hash(state.model_dump(mode="json")) != material.revision.material_hash:
            raise GovernedCompositionAuthorityError(
                "capability-state payload no longer matches its admitted material hash"
            )
        if (
            state.product_id != context.product_id
            or state.artifact != artifact
            or state.lifecycle != "active"
            or configuration_ref not in state.permitted_configuration_refs
            or capability_state_ref != capability_state_ref_for_artifact(artifact)
        ):
            raise GovernedCompositionAuthorityError("capability state is inactive or mismatched")
        return CapabilityUseReceiptV1Alpha1(
            product_id=context.product_id,
            actor_ref=context.actor_ref,
            authenticated_context=context,
            use_subject_ref=use_subject_ref,
            use_subject_digest=use_subject_digest,
            operation=operation,
            artifact=artifact,
            capability_state_ref=capability_state_ref,
            configuration_ref=configuration_ref,
            evaluated_at=evaluated_at,
            resolved_at=evaluated_at,
            state_head_precondition=material.head,
        )

    async def resolve_authority_use(
        self,
        *,
        context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject_ref: str,
        use_subject_digest: str,
        operation: str,
        authority: str,
        grant_ref: str,
        evaluated_at: datetime,
    ) -> AuthorityUseReceiptV1Alpha1:
        material = await self._load(
            state_kind=AUTHORITY_GRANT_STATE_KIND,
            product_id=context.product_id,
            state_id=grant_ref,
        )
        if material.revision.payload_contract != GRANT_PAYLOAD_CONTRACT:
            raise GovernedCompositionAuthorityError("authority grant uses an unsupported private payload")
        try:
            # See load_grant: current-use authorization reads the same durable JSON
            # representation and retains every semantic authority check below.
            grant = CompositionAuthorityGrantMaterial.model_validate(material.revision.payload, strict=False)
        except ValueError as exc:
            raise GovernedCompositionAuthorityError("authority grant payload failed exact validation") from exc
        expected_grant_hash = canonical_hash(grant.model_dump(mode="json", exclude={"grant_hash"}))
        if (
            grant.grant_hash != expected_grant_hash
            or canonical_hash(grant.model_dump(mode="json")) != material.revision.material_hash
        ):
            raise GovernedCompositionAuthorityError(
                "authority grant payload no longer matches its admitted material hash"
            )
        if (
            grant.product_id != context.product_id
            or grant.actor_ref != context.actor_ref
            or grant.authority_class.value != authority
            or operation not in grant.operations
            or grant.lifecycle != "active"
            or grant.effective_at > evaluated_at
            or (grant.expires_at is not None and grant.expires_at <= evaluated_at)
            or grant.revoked_at is not None
        ):
            raise GovernedCompositionAuthorityError("authority use is inactive, expired, revoked, or mismatched")
        return AuthorityUseReceiptV1Alpha1(
            product_id=context.product_id,
            actor_ref=context.actor_ref,
            authenticated_context=context,
            use_subject_ref=use_subject_ref,
            use_subject_digest=use_subject_digest,
            operation=operation,
            authority=authority,
            grant_ref=grant_ref,
            grant_hash=grant.grant_hash,
            evaluated_at=evaluated_at,
            expires_at=grant.expires_at,
            state_head_precondition=material.head,
        )


async def persist_task_authentication_receipt(
    *,
    claims: dict,
    verified_at: datetime,
    store: ImmutableRecordStore,
    verification_policy_ref: str,
    credential_fingerprint: str | None = None,
) -> TaskAuthenticationReceiptV1Alpha1:
    """Persist exact post-verification evidence without storing a credential."""

    actor_ref = claims.get("sub")
    product_id = claims.get("product")
    expires_claim = claims.get("exp")
    if not isinstance(actor_ref, str) or not isinstance(product_id, str):
        raise GovernedCompositionAuthorityError("verified claims lack exact actor or product")
    if not isinstance(expires_claim, (int, float)) or isinstance(expires_claim, bool):
        raise GovernedCompositionAuthorityError("verified claims lack an exact numeric expiry")
    verified_at = _aware(verified_at, "verified_at")
    receipt = TaskAuthenticationReceiptV1Alpha1(
        product_id=product_id,
        actor_ref=actor_ref,
        verification_policy_ref=verification_policy_ref,
        authenticated_at=verified_at,
        expires_at=datetime.fromtimestamp(expires_claim, tz=UTC),
        credential_fingerprint=credential_fingerprint,
    )
    record = ImmutableRecordV1(
        product_id=product_id,
        record_space=COMPOSITION_RECORD_SPACE,
        record_kind="task_authentication",
        record_key=str(receipt.receipt_id),
        payload_contract=receipt.contract,
        payload=receipt.model_dump(mode="python"),
        as_of=verified_at,
        available_at=verified_at,
        processing_order=0,
    )
    await store.append(
        AppendOnlyTransactionRequestV1(
            product_id=product_id,
            record_space=COMPOSITION_RECORD_SPACE,
            transaction_key=f"task_authentication:{receipt.receipt_id}",
            records=(record,),
            submitted_at=verified_at,
        )
    )
    return receipt


class GovernedReasoningCompositionAuthorityPort:
    """Two-phase AC2 resolver composed from the existing current-use port."""

    def __init__(
        self,
        *,
        governed_state: GovernedStateStore,
        records: ImmutableRecordStore,
        runtime_use: GovernedStateRuntimeUseResolver,
        registry: BoundedReasoningArtifactRegistry,
        configuration_ref: str,
        token_authorities: tuple[str, ...] | None = None,
    ) -> None:
        self.governed_state = governed_state
        self.records = records
        self.runtime_use = runtime_use
        self.registry = registry
        self.configuration_ref = configuration_ref
        self.token_authorities = frozenset(token_authorities) if token_authorities is not None else None

    async def _resolve(
        self,
        *,
        phase: Literal["planning", "pre_execution"],
        context: AuthenticatedRuntimeContextV1Alpha1,
        subject: ExactArtifactReferenceV1Alpha1,
        participant_principal_ref: str,
        authority_class: AuthorityClass,
        operation: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> ReasoningCompositionRuntimeAuthorityBundle:
        evaluated_at = _aware(evaluated_at, "evaluated_at")
        if evaluated_at >= context.expires_at:
            raise GovernedCompositionAuthorityError("authentication evidence expired before authority evaluation")
        if self.token_authorities is not None and authority_class.value not in self.token_authorities:
            raise GovernedCompositionAuthorityError("token authority attenuation excludes the governed grant")
        grant, grant_material = await self.runtime_use.load_grant(
            context=context,
            participant_principal_ref=participant_principal_ref,
            authority_class=authority_class,
            operation=operation,
            grant_ref=grant_ref,
            scope_ref=scope_ref,
            policy_ref=policy_ref,
            evaluated_at=evaluated_at,
        )
        configuration_material = await self.runtime_use._load(
            state_kind=REASONING_CONFIGURATION_STATE_KIND,
            product_id=context.product_id,
            state_id=self.configuration_ref,
        )
        if configuration_material.revision.payload_contract != CONFIGURATION_PAYLOAD_CONTRACT:
            raise GovernedCompositionAuthorityError("reasoning configuration uses an unsupported private payload")
        try:
            configuration = ReasoningCompositionConfigurationMaterial.model_validate(
                configuration_material.revision.payload
            )
        except ValueError as exc:
            raise GovernedCompositionAuthorityError("reasoning configuration failed exact validation") from exc
        if (
            configuration.product_id != context.product_id
            or configuration.configuration_ref != self.configuration_ref
            or configuration.authority != authority_class
            or configuration.grant_ref != grant_ref
            or configuration.lifecycle != "active"
        ):
            raise GovernedCompositionAuthorityError("reasoning configuration is inactive or mismatched")
        installed = self.registry.resolve(configuration.artifact)
        if installed is None:
            raise GovernedCompositionAuthorityError("configured reasoning artifact is not exactly installed")
        binding = ReasoningExecutionBindingV1Alpha1(
            product_id=context.product_id,
            artifact=installed,
            configuration_ref=self.configuration_ref,
            authority=authority_class.value,
            grant_ref=grant_ref,
            state_head_precondition=configuration_material.head,
        )
        capability = await self.runtime_use.resolve_capability_use(
            context=context,
            use_subject_ref=subject.artifact_id,
            use_subject_digest=subject.artifact_digest,
            operation=operation,
            artifact=installed,
            capability_state_ref=capability_state_ref_for_artifact(installed),
            configuration_ref=self.configuration_ref,
            evaluated_at=evaluated_at,
        )
        authority = await self.runtime_use.resolve_authority_use(
            context=context,
            use_subject_ref=subject.artifact_id,
            use_subject_digest=subject.artifact_digest,
            operation=operation,
            authority=authority_class.value,
            grant_ref=grant_ref,
            evaluated_at=evaluated_at,
        )
        coordinate = AuthorityCoordinateV1Alpha1(
            product_id=context.product_id,
            principal_ref=participant_principal_ref,
            authority_class=authority_class,
            grant_ref=grant_ref,
            scope_ref=grant.scope_ref,
            policy_ref=grant.policy_ref,
            expires_at=grant.expires_at,
        )
        capability_material = await self.runtime_use._load(
            state_kind=CAPABILITY_STATE_KIND,
            product_id=context.product_id,
            state_id=capability.capability_state_ref,
        )
        heads = tuple(
            sorted(
                (configuration_material.head, capability_material.head, grant_material.head),
                key=lambda item: (item.state_kind, item.product_id, item.state_id),
            )
        )
        resolution = CompositionAuthorityResolutionReceiptV1Alpha1(
            phase=phase,
            product_id=context.product_id,
            actor_ref=context.actor_ref,
            participant_principal_ref=participant_principal_ref,
            use_subject=subject,
            authentication_receipt_ref=context.authentication_receipt_ref,
            execution_binding=exact_reference(binding),
            capability_use=exact_reference(capability),
            authority_use=(exact_reference(authority),),
            authority_coordinates=(coordinate,),
            current_heads=heads,
            evaluated_at=evaluated_at,
        )
        bundle = ReasoningCompositionRuntimeAuthorityBundle(
            authenticated_context=context,
            execution_binding=binding,
            capability_use=capability,
            authority_use=(authority,),
            authority_coordinates=(coordinate,),
            current_heads=heads,
            resolution_receipt=resolution,
        )
        values = (capability, authority, resolution)
        records = tuple(
            ImmutableRecordV1(
                product_id=context.product_id,
                record_space=COMPOSITION_RECORD_SPACE,
                record_kind=kind,
                record_key=str(getattr(value, "receipt_id")),
                payload_contract=str(getattr(value, "contract")),
                payload=value.model_dump(mode="python"),
                as_of=evaluated_at,
                available_at=evaluated_at,
                processing_order=index,
            )
            for index, (kind, value) in enumerate(
                (("capability_use", values[0]), ("authority_use", values[1]), ("authority_resolution", values[2]))
            )
        )
        await self.records.append(
            AppendOnlyTransactionRequestV1(
                product_id=context.product_id,
                record_space=COMPOSITION_RECORD_SPACE,
                transaction_key=f"composition_authority:{resolution.receipt_id}",
                records=records,
                submitted_at=evaluated_at,
                governed_state_preconditions=heads,
            )
        )
        return bundle

    async def resolve_planning(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        use_subject: ExactArtifactReferenceV1Alpha1,
        participant_principal_ref: str,
        authority_class: str,
        operation: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> ReasoningCompositionRuntimeAuthorityBundle:
        return await self._resolve(
            phase="planning",
            context=authenticated_context,
            subject=use_subject,
            participant_principal_ref=participant_principal_ref,
            authority_class=AuthorityClass(authority_class),
            operation=operation,
            grant_ref=grant_ref,
            scope_ref=scope_ref,
            policy_ref=policy_ref,
            evaluated_at=evaluated_at,
        )

    async def resolve_pre_execution(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        manifest: StageRunManifestV1Alpha1,
        evaluated_at: datetime,
    ) -> ReasoningCompositionRuntimeAuthorityBundle:
        if len(manifest.authority) != 1:
            raise GovernedCompositionAuthorityError("compatibility manifest requires one exact authority coordinate")
        coordinate = manifest.authority[0]
        bundle = await self._resolve(
            phase="pre_execution",
            context=authenticated_context,
            subject=exact_reference(manifest),
            participant_principal_ref=coordinate.principal_ref,
            authority_class=coordinate.authority_class,
            operation="structured_reasoning",
            grant_ref=coordinate.grant_ref,
            scope_ref=coordinate.scope_ref,
            policy_ref=coordinate.policy_ref,
            evaluated_at=evaluated_at,
        )
        validate_bundle_for_manifest(manifest, bundle)
        return bundle


__all__ = [
    "AUTH_PAYLOAD_CONTRACT",
    "CAPABILITY_PAYLOAD_CONTRACT",
    "COMPOSITION_RECORD_SPACE",
    "CONFIGURATION_PAYLOAD_CONTRACT",
    "GRANT_PAYLOAD_CONTRACT",
    "BoundedReasoningArtifactRegistry",
    "AuthorityClass",
    "AuthorityCoordinateV1Alpha1",
    "AuthenticatedRuntimeContextV1Alpha1",
    "CompositionBudgetV1Alpha1",
    "CompositionNodeKind",
    "CompositionNodeV1Alpha1",
    "CompositionParticipantV1Alpha1",
    "ContextUseState",
    "DomainActivationLineageV1Alpha1",
    "ExactArtifactReferenceV1Alpha1",
    "HandoffState",
    "ImmutableRecordStore",
    "ParticipantKind",
    "ReasoningCompositionRuntimeAuthorityBundle",
    "ReasoningCompositionRuntimeAuthorityPort",
    "RunState",
    "StageHandoffContractV1Alpha1",
    "StageHandoffReceiptV1Alpha1",
    "StageRunManifestV1Alpha1",
    "StageRunReceiptV1Alpha1",
    "TaskCompositionPlanV1Alpha1",
    "UsageV1Alpha1",
    "CompositionAuthorityGrantMaterial",
    "CompositionCapabilityStateMaterial",
    "GovernedCompositionAuthorityError",
    "GovernedReasoningCompositionAuthorityPort",
    "GovernedStateRuntimeUseResolver",
    "ReasoningCompositionConfigurationMaterial",
    "persist_task_authentication_receipt",
    "canonical_hash",
    "exact_reference",
    "validate_run_receipt_against_manifest",
]
