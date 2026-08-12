"""Production host authority adapter for AC3 lifecycle composition.

This is the only legacy-host import edge into the provider-neutral AC3
application contracts.  It reuses AC2's post-authentication context, current
grant loader, capability-use evaluator, authority-use evaluator, immutable
record store, and exact governed-head validation.  The only additional state
is a generic governed-operation configuration selecting an existing lifecycle
service artifact for one exact stage and operation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, field_validator, model_validator

from ace.application.agent_composition_lifecycle import (
    LifecycleCompositionRuntimeAuthorityBundle,
    LifecycleStage,
    LifecycleStageCompatibilityProfile,
    lifecycle_exact_reference,
)
from ace.application.agent_composition_runtime import CompositionAuthorityResolutionReceiptV1Alpha1
from ace.core.agent_composition import AuthorityCoordinateV1Alpha1, StageRunManifestV1Alpha1
from ace.core.contracts import FrozenContract
from ace.core.reasoning import GOVERNED_OPERATION_CONFIGURATION_STATE_KIND, GovernedOperationBindingV1Alpha1
from ace.core.records import AppendOnlyTransactionRequestV1, ImmutableRecordStore, ImmutableRecordV1
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    capability_state_ref_for_artifact,
)
from core.engine.core.agent_composition_runtime import (
    COMPOSITION_RECORD_SPACE,
    BoundedReasoningArtifactRegistry,
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
)

LIFECYCLE_CONFIGURATION_PAYLOAD_CONTRACT = "ace.host.lifecycle-composition-configuration/v1alpha1"


class _Payload(FrozenContract):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class LifecycleCompositionConfigurationMaterial(_Payload):
    contract: Literal["ace.host.lifecycle-composition-configuration/v1alpha1"] = (
        LIFECYCLE_CONFIGURATION_PAYLOAD_CONTRACT
    )
    product_id: str
    configuration_ref: str
    profile_ref: str
    stage: LifecycleStage
    operation: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    authority: str
    grant_ref: str
    lifecycle: Literal["active", "suspended", "retired"]

    @field_validator("product_id", "configuration_ref", "profile_ref", "authority", "grant_ref")
    @classmethod
    def validate_refs(cls, value: str) -> str:
        if not value or value != value.strip() or len(value) > 240:
            raise ValueError("lifecycle configuration references must be bounded")
        return value

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        if not value or value != value.strip() or len(value) > 120:
            raise ValueError("operation must be a bounded stable identifier")
        return value

    @model_validator(mode="after")
    def validate_artifact_type(self) -> Self:
        if not isinstance(self.artifact, CapabilityArtifactIdentityV1Alpha1):
            raise ValueError("lifecycle configuration requires an exact capability artifact")
        return self


class GovernedLifecycleCompositionAuthorityPort:
    """Current-use resolver for existing lifecycle service artifacts."""

    def __init__(
        self,
        *,
        records: ImmutableRecordStore,
        runtime_use: GovernedStateRuntimeUseResolver,
        registry: BoundedReasoningArtifactRegistry,
        configuration_refs: dict[LifecycleStage, str],
        token_authorities: tuple[str, ...] | None = None,
    ) -> None:
        self.records = records
        self.runtime_use = runtime_use
        self.registry = registry
        self.configuration_refs = dict(configuration_refs)
        self.token_authorities = frozenset(token_authorities) if token_authorities is not None else None

    async def _resolve(
        self,
        *,
        phase: Literal["planning", "pre_execution"],
        context: AuthenticatedRuntimeContextV1Alpha1,
        subject,
        profile: LifecycleStageCompatibilityProfile,
        participant_principal_ref: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> LifecycleCompositionRuntimeAuthorityBundle:
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise GovernedCompositionAuthorityError("lifecycle authority evaluation requires an aware time")
        evaluated_at = evaluated_at.astimezone(UTC)
        if evaluated_at >= context.expires_at:
            raise GovernedCompositionAuthorityError("authentication evidence expired before lifecycle evaluation")
        if self.token_authorities is not None and profile.authority_class.value not in self.token_authorities:
            raise GovernedCompositionAuthorityError("token authority attenuation excludes the lifecycle grant")
        configuration_ref = self.configuration_refs.get(profile.stage)
        if configuration_ref is None:
            raise GovernedCompositionAuthorityError("missing lifecycle operation configuration")
        grant, grant_material = await self.runtime_use.load_grant(
            context=context,
            participant_principal_ref=participant_principal_ref,
            authority_class=profile.authority_class,
            operation=profile.operation,
            grant_ref=grant_ref,
            scope_ref=scope_ref,
            policy_ref=policy_ref,
            evaluated_at=evaluated_at,
        )
        configuration_material = await self.runtime_use._load(
            state_kind=GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
            product_id=context.product_id,
            state_id=configuration_ref,
        )
        if configuration_material.revision.payload_contract != LIFECYCLE_CONFIGURATION_PAYLOAD_CONTRACT:
            raise GovernedCompositionAuthorityError("lifecycle configuration uses an unsupported payload")
        try:
            configuration = LifecycleCompositionConfigurationMaterial.model_validate(
                configuration_material.revision.payload
            )
        except ValueError as exc:
            raise GovernedCompositionAuthorityError("lifecycle configuration failed exact validation") from exc
        if (
            configuration.product_id != context.product_id
            or configuration.configuration_ref != configuration_ref
            or configuration.profile_ref != profile.coordinate_ref
            or configuration.stage is not profile.stage
            or configuration.operation != profile.operation
            or configuration.authority != profile.authority_class.value
            or configuration.grant_ref != grant_ref
            or configuration.lifecycle != "active"
        ):
            raise GovernedCompositionAuthorityError("lifecycle configuration is inactive or mismatched")
        installed = self.registry.resolve(configuration.artifact)
        if installed is None:
            raise GovernedCompositionAuthorityError("configured lifecycle service artifact is not exactly installed")
        binding = GovernedOperationBindingV1Alpha1(
            product_id=context.product_id,
            artifact=installed,
            configuration_ref=configuration_ref,
            authority=profile.authority_class.value,
            grant_ref=grant_ref,
            state_head_precondition=configuration_material.head,
        )
        capability = await self.runtime_use.resolve_capability_use(
            context=context,
            use_subject_ref=subject.artifact_id,
            use_subject_digest=subject.artifact_digest,
            operation=profile.operation,
            artifact=installed,
            capability_state_ref=capability_state_ref_for_artifact(installed),
            configuration_ref=configuration_ref,
            evaluated_at=evaluated_at,
        )
        authority = await self.runtime_use.resolve_authority_use(
            context=context,
            use_subject_ref=subject.artifact_id,
            use_subject_digest=subject.artifact_digest,
            operation=profile.operation,
            authority=profile.authority_class.value,
            grant_ref=grant_ref,
            evaluated_at=evaluated_at,
        )
        coordinate = AuthorityCoordinateV1Alpha1(
            product_id=context.product_id,
            principal_ref=participant_principal_ref,
            authority_class=profile.authority_class,
            grant_ref=grant_ref,
            scope_ref=grant.scope_ref,
            policy_ref=grant.policy_ref,
            expires_at=grant.expires_at,
        )
        capability_material = await self.runtime_use._load(
            state_kind="capability_state",
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
            execution_binding=lifecycle_exact_reference(binding),
            capability_use=lifecycle_exact_reference(capability),
            authority_use=(lifecycle_exact_reference(authority),),
            authority_coordinates=(coordinate,),
            current_heads=heads,
            evaluated_at=evaluated_at,
        )
        bundle = LifecycleCompositionRuntimeAuthorityBundle(
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
                record_key=str(value.receipt_id),
                payload_contract=str(value.contract),
                payload=value.model_dump(mode="python"),
                as_of=evaluated_at,
                available_at=evaluated_at,
                processing_order=index,
            )
            for index, (kind, value) in enumerate(
                (
                    ("lifecycle_capability_use", values[0]),
                    ("lifecycle_authority_use", values[1]),
                    ("lifecycle_authority_resolution", values[2]),
                )
            )
        )
        await self.records.append(
            AppendOnlyTransactionRequestV1(
                product_id=context.product_id,
                record_space=COMPOSITION_RECORD_SPACE,
                transaction_key=f"lifecycle_composition_authority:{resolution.receipt_id}",
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
        use_subject,
        profile: LifecycleStageCompatibilityProfile,
        participant_principal_ref: str,
        grant_ref: str,
        scope_ref: str,
        policy_ref: str,
        evaluated_at: datetime,
    ) -> LifecycleCompositionRuntimeAuthorityBundle:
        return await self._resolve(
            phase="planning",
            context=authenticated_context,
            subject=use_subject,
            profile=profile,
            participant_principal_ref=participant_principal_ref,
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
        profile: LifecycleStageCompatibilityProfile,
        evaluated_at: datetime,
    ) -> LifecycleCompositionRuntimeAuthorityBundle:
        if manifest.stage_id != profile.stage.value or len(manifest.authority) != 1:
            raise GovernedCompositionAuthorityError("lifecycle manifest crossed the exact stage profile")
        coordinate = manifest.authority[0]
        bundle = await self._resolve(
            phase="pre_execution",
            context=authenticated_context,
            subject=lifecycle_exact_reference(manifest),
            profile=profile,
            participant_principal_ref=coordinate.principal_ref,
            grant_ref=coordinate.grant_ref,
            scope_ref=coordinate.scope_ref,
            policy_ref=coordinate.policy_ref,
            evaluated_at=evaluated_at,
        )
        if (
            manifest.product_id != bundle.authenticated_context.product_id
            or manifest.execution_binding != lifecycle_exact_reference(bundle.execution_binding)
            or manifest.authority != bundle.authority_coordinates
            or bundle.resolution_receipt.use_subject != lifecycle_exact_reference(manifest)
        ):
            raise GovernedCompositionAuthorityError("lifecycle manifest differs from current-use resolution")
        return bundle


__all__ = [
    "LIFECYCLE_CONFIGURATION_PAYLOAD_CONTRACT",
    "GovernedLifecycleCompositionAuthorityPort",
    "LifecycleCompositionConfigurationMaterial",
]
