"""Narrow AC2/AC3/AC4 pre-execution convergence adapter.

The adapter consumes a durably recorded AC4 activation and compatibility
replacement, reloads all five current governance heads, re-resolves every
current requested grant, then invokes AC2's current-use resolver for the exact
new AC3 plan and manifest.  Historical receipts remain evidence only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.application.agent_composition_runtime import (
    CompositionAuthorityResolutionReceiptV1Alpha1,
    ReasoningCompositionRuntimeAuthorityBundle,
    ReasoningCompositionRuntimeAuthorityPort,
    exact_reference,
    validate_bundle_for_manifest,
)
from ace.application.agent_governance import (
    ADMINISTER_LIFECYCLE_AUTHORITY,
    AGENT_BINDING_LIFECYCLE_STATE_KIND,
    AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
    AGENT_GOVERNANCE_RECORD_SPACE,
    AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND,
    AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
    AGENT_RUNTIME_HEALTH_STATE_KIND,
    AgentGovernanceService,
    _binding_state_id,
    _payload_revision_id,
)
from ace.core.agent_composition import (
    ExactArtifactReferenceV1Alpha1,
    ParticipantKind,
    StageRunManifestV1Alpha1,
    TaskCompositionPlanV1Alpha1,
)
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.agent_governance import (
    AgentActivationReceiptV1Alpha1,
    AgentBindingLifecycleRevisionV1Alpha1,
    AgentCompatibilityReplacementReceiptV1Alpha1,
    AgentDefinitionLifecycleRevisionV1Alpha1,
    AgentGrantRequestLifecycleRevisionV1Alpha1,
    AgentPrincipalLifecycleRevisionV1Alpha1,
    AgentRuntimeHealthRevisionV1Alpha1,
    GovernedContentState,
    GrantRequestState,
    PrincipalLifecycleState,
    RuntimeHealthState,
)

GOVERNED_AGENT_PRE_EXECUTION_ADMISSION_VERSION = "ace.application.governed-agent-pre-execution-admission/v1alpha1"


class _Contract(FrozenContract):
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


def _identity(instance: _Contract) -> None:
    material = instance.model_dump(mode="json", exclude={"receipt_id", "receipt_digest"})
    digest = canonical_hash(material)
    expected_id = f"governed_agent_pre_execution:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if instance.receipt_id not in {None, expected_id} or instance.receipt_digest not in {None, expected_digest}:
        raise ValueError("pre-execution admission identity does not match exact convergence material")
    object.__setattr__(instance, "receipt_id", expected_id)
    object.__setattr__(instance, "receipt_digest", expected_digest)


class GovernedAgentPreExecutionAdmissionV1Alpha1(_Contract):
    contract: Literal["ace.application.governed-agent-pre-execution-admission/v1alpha1"] = (
        GOVERNED_AGENT_PRE_EXECUTION_ADMISSION_VERSION
    )
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    definition: ExactArtifactReferenceV1Alpha1
    binding: ExactArtifactReferenceV1Alpha1
    activation: ExactArtifactReferenceV1Alpha1
    compatibility_replacement: ExactArtifactReferenceV1Alpha1
    new_plan: ExactArtifactReferenceV1Alpha1
    new_manifest: ExactArtifactReferenceV1Alpha1
    historical_compatibility_participant: ExactArtifactReferenceV1Alpha1
    composition_authority: CompositionAuthorityResolutionReceiptV1Alpha1
    governance_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=5, max_length=5)
    runtime_heads: tuple[GovernedStateHeadPreconditionV1Alpha1, ...] = Field(min_length=3, max_length=64)
    evaluated_at: datetime
    rewrites_history: Literal[False] = False
    carries_authority_forward: Literal[False] = False
    reusable_authority: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("evaluated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="evaluated_at")

    @field_validator("governance_heads", "runtime_heads")
    @classmethod
    def normalize_heads(
        cls, value: tuple[GovernedStateHeadPreconditionV1Alpha1, ...]
    ) -> tuple[GovernedStateHeadPreconditionV1Alpha1, ...]:
        keys = [(item.state_kind, item.product_id, item.state_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("pre-execution heads must be unique")
        return tuple(sorted(value, key=lambda item: (item.state_kind, item.product_id, item.state_id)))

    @model_validator(mode="after")
    def validate_exact_convergence(self) -> Self:
        if self.new_plan == self.historical_compatibility_participant:
            raise ValueError("governed participation requires a new plan identity")
        if self.composition_authority.phase != "pre_execution":
            raise ValueError("governed participation requires AC2 pre-execution resolution")
        if self.composition_authority.current_heads != self.runtime_heads:
            raise ValueError("AC2 resolution does not bind the exact runtime heads")
        if any(item.product_id != self.governance.product_id for item in (*self.governance_heads, *self.runtime_heads)):
            raise ValueError("governed pre-execution admission crossed product scope")
        required = {
            AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND,
            AGENT_DEFINITION_LIFECYCLE_STATE_KIND,
            AGENT_BINDING_LIFECYCLE_STATE_KIND,
            AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND,
            AGENT_RUNTIME_HEALTH_STATE_KIND,
        }
        if {item.state_kind for item in self.governance_heads} != required:
            raise ValueError("governed pre-execution admission requires all five AC4 heads")
        _identity(self)
        return self


class GovernedAgentPreExecutionError(RuntimeError):
    """AC2/AC3/AC4 convergence failed closed before participant execution."""


class GovernedAgentPreExecutionResolver:
    """Stack AC4 current governance onto the existing AC2 runtime resolver."""

    def __init__(
        self,
        *,
        governance_service: AgentGovernanceService,
        runtime_authority: ReasoningCompositionRuntimeAuthorityPort,
    ) -> None:
        self.governance_service = governance_service
        self.runtime_authority = runtime_authority

    async def resolve(
        self,
        *,
        authenticated_context: AuthenticatedRuntimeContextV1Alpha1,
        governance: AgentGovernanceCoordinateV1Alpha1,
        binding_key: str,
        plan: TaskCompositionPlanV1Alpha1,
        manifest: StageRunManifestV1Alpha1,
        activation: AgentActivationReceiptV1Alpha1,
        replacement: AgentCompatibilityReplacementReceiptV1Alpha1,
        evaluated_at: datetime,
    ) -> tuple[GovernedAgentPreExecutionAdmissionV1Alpha1, ReasoningCompositionRuntimeAuthorityBundle]:
        try:
            now = _aware(evaluated_at, name="evaluated_at")
            plan = TaskCompositionPlanV1Alpha1.model_validate(plan.model_dump(mode="python"))
            manifest = StageRunManifestV1Alpha1.model_validate(manifest.model_dump(mode="python"))
            activation = AgentActivationReceiptV1Alpha1.model_validate(activation.model_dump(mode="python"))
            replacement = AgentCompatibilityReplacementReceiptV1Alpha1.model_validate(
                replacement.model_dump(mode="python")
            )
        except Exception:
            raise GovernedAgentPreExecutionError("governed pre-execution material failed exact revalidation") from None
        if authenticated_context.product_id != governance.product_id or plan.product_id != governance.product_id:
            raise GovernedAgentPreExecutionError("governed pre-execution crossed authenticated product scope")
        if manifest.product_id != plan.product_id or manifest.plan != exact_reference(plan):
            raise GovernedAgentPreExecutionError("manifest does not bind the exact new composition plan")
        if plan.created_at < replacement.replaced_at or manifest.created_at < replacement.replaced_at:
            raise GovernedAgentPreExecutionError(
                "governed participation requires a fresh post-replacement plan and manifest"
            )
        participants = [
            item for item in plan.participants if item.composition_participant_id == manifest.composition_participant_id
        ]
        if len(participants) != 1:
            raise GovernedAgentPreExecutionError("manifest participant is not unique in the new plan")
        participant = participants[0]
        if (
            participant.participant_kind not in {ParticipantKind.MODEL_AGENT, ParticipantKind.EXTERNAL_AGENT}
            or participant.participant_ref != replacement.registration_snapshot.artifact_id
            or participant.definition_revision != replacement.definition
            or participant.role_binding != replacement.binding
            or manifest.definition_revision != replacement.definition
            or manifest.role_binding != replacement.binding
            or manifest.composition_participant_id != participant.composition_participant_id
            or any(item.principal_ref != replacement.registration_snapshot.artifact_id for item in manifest.authority)
        ):
            raise GovernedAgentPreExecutionError(
                "new governed plan does not bind exact registration, definition, binding, and runtime principal"
            )

        service = self.governance_service
        try:
            recorded_activation = await service._load_exact_record(
                product_id=governance.product_id,
                kind="activation_receipt",
                key=str(activation.receipt_id),
                model=AgentActivationReceiptV1Alpha1,
            )
            recorded_replacement = await service._load_exact_record(
                product_id=governance.product_id,
                kind="compatibility_replacement_receipt",
                key=str(replacement.receipt_id),
                model=AgentCompatibilityReplacementReceiptV1Alpha1,
            )
            activation_tx = await service.audit_store.load_transaction_receipt(
                product_id=governance.product_id,
                record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                transaction_key=str(activation.receipt_id),
            )
            replacement_tx = await service.audit_store.load_transaction_receipt(
                product_id=governance.product_id,
                record_space=AGENT_GOVERNANCE_RECORD_SPACE,
                transaction_key=str(replacement.receipt_id),
            )
        except Exception:
            raise GovernedAgentPreExecutionError("durable activation or replacement evidence is unavailable") from None
        if recorded_activation != activation or recorded_replacement != replacement:
            raise GovernedAgentPreExecutionError("pre-execution requires exact durable activation and replacement")
        if (
            activation_tx is None
            or {item.record_kind for item in activation_tx.records}
            != {"compatibility_receipt", "conformance_receipt", "dry_run_receipt", "activation_receipt"}
            or replacement_tx is None
            or len(replacement_tx.records) != 1
            or replacement_tx.records[0].record_kind != "compatibility_replacement_receipt"
            or replacement.activation_receipt
            != ExactArtifactReferenceV1Alpha1(
                artifact_id=str(activation.receipt_id),
                artifact_digest=str(activation.receipt_digest),
                artifact_contract=activation.contract,
            )
            or replacement.governance != governance
            or replacement.rewrites_history
            or replacement.carries_authority_forward
            or replacement.reusable_authority
        ):
            raise GovernedAgentPreExecutionError("activation and replacement durable lineage is incomplete or unsafe")

        loaded = []
        for state_kind, state_id in (
            (AGENT_PRINCIPAL_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_DEFINITION_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (
                AGENT_BINDING_LIFECYCLE_STATE_KIND,
                _binding_state_id(str(governance.governance_id), binding_key),
            ),
            (AGENT_GRANT_REQUEST_LIFECYCLE_STATE_KIND, str(governance.governance_id)),
            (AGENT_RUNTIME_HEALTH_STATE_KIND, str(governance.governance_id)),
        ):
            try:
                current = await service._load_current(
                    state_kind=state_kind,
                    governance=governance,
                    state_id=state_id,
                )
            except Exception:
                raise GovernedAgentPreExecutionError("current AC4 governance head resolution failed closed") from None
            if current is None:
                raise GovernedAgentPreExecutionError("all five current AC4 governance heads are required")
            loaded.append(current)

        principal, definition, binding, grants, health = (item[1] for item in loaded)
        if (
            not isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1)
            or principal.state is not PrincipalLifecycleState.ACTIVE
            or not isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1)
            or definition.state is not GovernedContentState.ACTIVE
            or not isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1)
            or binding.state is not GovernedContentState.ACTIVE
            or not isinstance(grants, AgentGrantRequestLifecycleRevisionV1Alpha1)
            or grants.state is not GrantRequestState.REQUESTED
            or not isinstance(health, AgentRuntimeHealthRevisionV1Alpha1)
            or health.state is not RuntimeHealthState.HEALTHY
        ):
            raise GovernedAgentPreExecutionError("current AC4 lifecycle or health blocks runtime participation")
        if (
            activation.governance != governance
            or activation.principal_lifecycle_revision_id != _payload_revision_id(principal)
            or activation.definition_lifecycle_revision_id != _payload_revision_id(definition)
            or activation.binding_lifecycle_revision_id != _payload_revision_id(binding)
            or activation.grant_request_lifecycle_revision_id != _payload_revision_id(grants)
            or activation.runtime_health_revision_id != _payload_revision_id(health)
            or replacement.registration_snapshot != principal.registration_snapshot
            or replacement.definition != participant.definition_revision
            or replacement.binding != participant.role_binding
        ):
            raise GovernedAgentPreExecutionError("activation or replacement is stale against current AC4 heads")

        requirements = (
            (activation.lifecycle_authority.grant_ref, ADMINISTER_LIFECYCLE_AUTHORITY),
            *((item.requested_grant_ref, item.authority_class.value) for item in grants.requests),
        )
        for grant_ref, authority in requirements:
            try:
                current_grant = await service.authority.resolve_grant(
                    grant_ref=grant_ref,
                    product_id=governance.product_id,
                    authority=authority,
                    effective_at=now,
                )
            except Exception:
                raise GovernedAgentPreExecutionError("every current AC4 grant must be freshly re-resolved") from None
            if (
                current_grant.grant_ref != grant_ref
                or current_grant.product_id != governance.product_id
                or current_grant.authority != authority
                or current_grant.effective_at != now
                or (current_grant.expires_at is not None and current_grant.expires_at <= now)
            ):
                raise GovernedAgentPreExecutionError("current AC4 grant resolution is expired, revoked, or mismatched")

        try:
            runtime = await self.runtime_authority.resolve_pre_execution(
                authenticated_context=authenticated_context,
                manifest=manifest,
                evaluated_at=now,
            )
            validate_bundle_for_manifest(manifest, runtime)
        except Exception:
            raise GovernedAgentPreExecutionError(
                "AC2 capability, configuration, and runtime-grant pre-execution resolution failed closed"
            ) from None
        admission = GovernedAgentPreExecutionAdmissionV1Alpha1(
            governance=governance,
            registration_snapshot=principal.registration_snapshot,
            definition=replacement.definition,
            binding=replacement.binding,
            activation=replacement.activation_receipt,
            compatibility_replacement=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(replacement.receipt_id),
                artifact_digest=str(replacement.receipt_digest),
                artifact_contract=replacement.contract,
            ),
            new_plan=exact_reference(plan),
            new_manifest=exact_reference(manifest),
            historical_compatibility_participant=replacement.compatibility_participant,
            composition_authority=runtime.resolution_receipt,
            governance_heads=tuple(GovernedStateHeadPreconditionV1Alpha1.from_head(item[0]) for item in loaded),
            runtime_heads=runtime.current_heads,
            evaluated_at=now,
        )
        return admission, runtime


__all__ = [
    "GOVERNED_AGENT_PRE_EXECUTION_ADMISSION_VERSION",
    "GovernedAgentPreExecutionAdmissionV1Alpha1",
    "GovernedAgentPreExecutionError",
    "GovernedAgentPreExecutionResolver",
]
