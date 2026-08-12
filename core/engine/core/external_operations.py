"""Internal host resolver for current destination and operation authority."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.external_operations import ExternalOperationAuthorityPort
from ace.core.contracts import FrozenContract
from ace.core.external_operations import (
    DestinationLifecycle,
    DestinationPolicyKind,
    DestinationRevisionV1Alpha1,
    ExternalOperation,
    ExternalOperationAuthorityV1Alpha1,
    exact_external_reference,
)
from ace.core.runtime_use import (
    AuthenticatedRuntimeContextV1Alpha1,
    CapabilityArtifactIdentityV1Alpha1,
    capability_state_ref_for_artifact,
)
from core.engine.core.agent_composition_runtime import GovernedStateRuntimeUseResolver

DESTINATION_REVISION_STATE_KIND = "destination_revision"
DESTINATION_POLICY_STATE_KIND = "destination_policy"
EXTERNAL_OPERATION_CONFIGURATION_STATE_KIND = "external_operation_configuration"
DESTINATION_REVISION_PAYLOAD_CONTRACT = "ace.host.destination-revision-state/v1alpha1"
DESTINATION_POLICY_PAYLOAD_CONTRACT = "ace.host.destination-policy-state/v1alpha1"
EXTERNAL_OPERATION_CONFIGURATION_PAYLOAD_CONTRACT = "ace.host.external-operation-configuration/v1alpha1"


class _Payload(FrozenContract):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class DestinationRevisionStateMaterial(_Payload):
    contract: Literal["ace.host.destination-revision-state/v1alpha1"] = DESTINATION_REVISION_PAYLOAD_CONTRACT
    product_id: str
    destination_revision: DestinationRevisionV1Alpha1
    lifecycle: DestinationLifecycle


class DestinationPolicyStateMaterial(_Payload):
    contract: Literal["ace.host.destination-policy-state/v1alpha1"] = DESTINATION_POLICY_PAYLOAD_CONTRACT
    product_id: str
    destination_revision_id: str
    kind: DestinationPolicyKind
    policy_ref: str
    material_digest: str
    lifecycle: Literal["active", "revoked", "expired"]
    tenant_ref: str
    principal_ref: str
    recipient_ref: str | None = None
    effective_at: datetime
    expires_at: datetime | None = None

    @field_validator("effective_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, name=info.field_name) if value is not None else None

    @model_validator(mode="after")
    def validate_window(self):
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("destination policy expiry must follow effective time")
        return self


class ExternalOperationConfigurationMaterial(_Payload):
    contract: Literal["ace.host.external-operation-configuration/v1alpha1"] = (
        EXTERNAL_OPERATION_CONFIGURATION_PAYLOAD_CONTRACT
    )
    product_id: str
    operation: ExternalOperation
    configuration_ref: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    grant_ref: str
    destination_revision_id: str | None = None
    policy_state_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=6)
    lifecycle: Literal["active", "suspended", "retired"]

    @field_validator("policy_state_ids")
    @classmethod
    def normalize_policy_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("destination policy state identities must be unique")
        return normalized


class GovernedExternalOperationAuthorityError(RuntimeError):
    """Current host authority, capability, destination, or policy failed closed."""


class GovernedExternalOperationAuthorityResolver(ExternalOperationAuthorityPort):
    """Resolve every external operation through the existing RuntimeUseResolver."""

    def __init__(
        self,
        *,
        runtime_use: GovernedStateRuntimeUseResolver,
        bindings: tuple[ExternalOperationConfigurationMaterial, ...],
    ) -> None:
        self.runtime_use = runtime_use
        self.bindings = {item.operation: item for item in bindings}
        if len(self.bindings) != len(bindings):
            raise GovernedExternalOperationAuthorityError("each external operation requires one exact binding")

    async def resolve(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        operation: ExternalOperation,
        use_subject,
        destination_revision: DestinationRevisionV1Alpha1 | None,
        recipient_ref: str | None,
        evaluated_at: datetime,
    ) -> ExternalOperationAuthorityV1Alpha1:
        now = _aware(evaluated_at, name="evaluated_at")
        binding = self.bindings.get(operation)
        if binding is None or binding.lifecycle != "active" or binding.product_id != authenticated_context.product_id:
            raise GovernedExternalOperationAuthorityError("external-operation configuration is unavailable")
        configuration = await self.runtime_use._load(
            state_kind=EXTERNAL_OPERATION_CONFIGURATION_STATE_KIND,
            product_id=authenticated_context.product_id,
            state_id=binding.configuration_ref,
        )
        if configuration.revision.payload_contract != EXTERNAL_OPERATION_CONFIGURATION_PAYLOAD_CONTRACT:
            raise GovernedExternalOperationAuthorityError("external-operation configuration uses unsupported payload")
        try:
            current_binding = ExternalOperationConfigurationMaterial.model_validate(configuration.revision.payload)
        except Exception:
            raise GovernedExternalOperationAuthorityError(
                "external-operation configuration failed exact validation"
            ) from None
        if current_binding != binding:
            raise GovernedExternalOperationAuthorityError("external-operation configuration drifted")

        heads = [configuration.head]
        exact_destination = None
        if operation is ExternalOperation.ADMIN_EXPORT:
            if (
                destination_revision is not None
                or binding.destination_revision_id is not None
                or binding.policy_state_ids
            ):
                raise GovernedExternalOperationAuthorityError(
                    "administrative export cannot inherit destination authority"
                )
        else:
            if destination_revision is None:
                raise GovernedExternalOperationAuthorityError("delivery and external effect require exact destination")
            try:
                destination_revision = DestinationRevisionV1Alpha1.model_validate(
                    destination_revision.model_dump(mode="python")
                )
            except Exception:
                raise GovernedExternalOperationAuthorityError("destination revision failed exact validation") from None
            destination_material = await self.runtime_use._load(
                state_kind=DESTINATION_REVISION_STATE_KIND,
                product_id=authenticated_context.product_id,
                state_id=str(destination_revision.revision_id),
            )
            if destination_material.revision.payload_contract != DESTINATION_REVISION_PAYLOAD_CONTRACT:
                raise GovernedExternalOperationAuthorityError("destination revision uses unsupported host payload")
            try:
                current_destination = DestinationRevisionStateMaterial.model_validate(
                    destination_material.revision.payload
                )
            except Exception:
                raise GovernedExternalOperationAuthorityError(
                    "destination revision head failed exact validation"
                ) from None
            if (
                current_destination.product_id != authenticated_context.product_id
                or current_destination.destination_revision != destination_revision
                or current_destination.lifecycle is not DestinationLifecycle.ACTIVE
                or binding.destination_revision_id != destination_revision.revision_id
            ):
                raise GovernedExternalOperationAuthorityError("destination revision is stale, suspended, or mismatched")
            heads.append(destination_material.head)
            exact_destination = exact_external_reference(destination_revision)
            expected_policy_ids = {item.state_id for item in destination_revision.policies}
            if set(binding.policy_state_ids) != expected_policy_ids:
                raise GovernedExternalOperationAuthorityError(
                    "external-operation binding omits exact destination policies"
                )
            for coordinate in destination_revision.policies:
                policy_material = await self.runtime_use._load(
                    state_kind=DESTINATION_POLICY_STATE_KIND,
                    product_id=authenticated_context.product_id,
                    state_id=coordinate.state_id,
                )
                if policy_material.revision.payload_contract != DESTINATION_POLICY_PAYLOAD_CONTRACT:
                    raise GovernedExternalOperationAuthorityError("destination policy uses unsupported host payload")
                try:
                    policy = DestinationPolicyStateMaterial.model_validate(policy_material.revision.payload)
                except Exception:
                    raise GovernedExternalOperationAuthorityError(
                        "destination policy failed exact validation"
                    ) from None
                if (
                    policy.product_id != authenticated_context.product_id
                    or policy.destination_revision_id != destination_revision.revision_id
                    or policy.kind is not coordinate.kind
                    or policy.policy_ref != coordinate.policy_ref
                    or policy.material_digest != coordinate.material_digest
                    or policy.lifecycle != "active"
                    or policy.tenant_ref != authenticated_context.product_id
                    or policy.principal_ref != authenticated_context.actor_ref
                    or (policy.recipient_ref is not None and policy.recipient_ref != recipient_ref)
                    or policy.effective_at > now
                    or (policy.expires_at is not None and policy.expires_at <= now)
                ):
                    raise GovernedExternalOperationAuthorityError(
                        "destination capability, compatibility, entitlement, consent, redaction, or data-class policy failed"
                    )
                heads.append(policy_material.head)

        try:
            capability = await self.runtime_use.resolve_capability_use(
                context=authenticated_context,
                use_subject_ref=use_subject.artifact_id,
                use_subject_digest=use_subject.artifact_digest,
                operation=operation.value,
                artifact=binding.artifact,
                capability_state_ref=capability_state_ref_for_artifact(binding.artifact),
                configuration_ref=binding.configuration_ref,
                evaluated_at=now,
            )
            authority = await self.runtime_use.resolve_authority_use(
                context=authenticated_context,
                use_subject_ref=use_subject.artifact_id,
                use_subject_digest=use_subject.artifact_digest,
                operation=operation.value,
                authority=operation.value,
                grant_ref=binding.grant_ref,
                evaluated_at=now,
            )
            capability_material = await self.runtime_use._load(
                state_kind=capability.state_head_precondition.state_kind,
                product_id=authenticated_context.product_id,
                state_id=capability.state_head_precondition.state_id,
            )
            grant_material = await self.runtime_use._load(
                state_kind=authority.state_head_precondition.state_kind,
                product_id=authenticated_context.product_id,
                state_id=authority.state_head_precondition.state_id,
            )
        except Exception:
            raise GovernedExternalOperationAuthorityError(
                "external-operation capability or current grant resolution failed closed"
            ) from None
        heads.extend((capability_material.head, grant_material.head))
        return ExternalOperationAuthorityV1Alpha1(
            operation=operation,
            product_id=authenticated_context.product_id,
            actor_ref=authenticated_context.actor_ref,
            authenticated_context=authenticated_context,
            use_subject=use_subject,
            destination_revision=exact_destination,
            capability_use=capability,
            authority_use=authority,
            current_heads=tuple(heads),
            evaluated_at=now,
        )


__all__ = [
    "DESTINATION_POLICY_PAYLOAD_CONTRACT",
    "DESTINATION_POLICY_STATE_KIND",
    "DESTINATION_REVISION_PAYLOAD_CONTRACT",
    "DESTINATION_REVISION_STATE_KIND",
    "EXTERNAL_OPERATION_CONFIGURATION_PAYLOAD_CONTRACT",
    "EXTERNAL_OPERATION_CONFIGURATION_STATE_KIND",
    "DestinationPolicyStateMaterial",
    "DestinationRevisionStateMaterial",
    "ExternalOperationConfigurationMaterial",
    "GovernedExternalOperationAuthorityError",
    "GovernedExternalOperationAuthorityResolver",
]
