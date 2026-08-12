"""No-authority external-agent capability and identity handshake."""

from __future__ import annotations

from datetime import datetime

from ace.application.agent_governance import AgentGovernanceService, _payload_revision_id
from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.intelligence.contracts.agent_governance import (
    AgentBindingLifecycleRevisionV1Alpha1,
    AgentDefinitionLifecycleRevisionV1Alpha1,
    AgentPrincipalLifecycleRevisionV1Alpha1,
    AgentRuntimeHealthRevisionV1Alpha1,
    GovernedContentState,
    PrincipalLifecycleState,
    RuntimeHealthState,
)
from ace.intelligence.contracts.external_agent import (
    ExternalAgentHandshakeDisposition,
    ExternalAgentHandshakeV1Alpha1,
    ExternalAgentProtocolIdentityV1Alpha1,
)


class ExternalAgentHandshakeError(RuntimeError):
    """External-agent handshake failed closed without granting authority."""


class ExternalAgentHandshakeService:
    def __init__(self, *, governance_service: AgentGovernanceService) -> None:
        self.governance_service = governance_service

    async def handshake(
        self,
        *,
        governance: AgentGovernanceCoordinateV1Alpha1,
        binding_key: str,
        protocol: ExternalAgentProtocolIdentityV1Alpha1,
        offered_protocol_ref: str,
        offered_capability_refs: tuple[str, ...],
        checked_at: datetime,
    ) -> ExternalAgentHandshakeV1Alpha1:
        try:
            protocol = ExternalAgentProtocolIdentityV1Alpha1.model_validate(protocol.model_dump(mode="python"))
        except Exception:
            raise ExternalAgentHandshakeError("external-agent protocol identity failed exact revalidation") from None
        service = self.governance_service
        try:
            view = await service.inspect(governance=governance, binding_keys=(binding_key,))
        except Exception:
            raise ExternalAgentHandshakeError("current external-agent governance is unavailable") from None
        principal = view.principal_lifecycle
        definition = view.definition_lifecycle
        binding = view.binding_lifecycles[0] if len(view.binding_lifecycles) == 1 else None
        health = view.runtime_health
        if (
            not isinstance(principal, AgentPrincipalLifecycleRevisionV1Alpha1)
            or not isinstance(definition, AgentDefinitionLifecycleRevisionV1Alpha1)
            or not isinstance(binding, AgentBindingLifecycleRevisionV1Alpha1)
            or not isinstance(health, AgentRuntimeHealthRevisionV1Alpha1)
        ):
            raise ExternalAgentHandshakeError("external-agent handshake requires all current identity heads")
        disposition = ExternalAgentHandshakeDisposition.COMPATIBLE
        if (
            principal.state is not PrincipalLifecycleState.ACTIVE
            or definition.state is not GovernedContentState.ACTIVE
            or binding.state is not GovernedContentState.ACTIVE
            or health.state is not RuntimeHealthState.HEALTHY
        ):
            disposition = ExternalAgentHandshakeDisposition.INELIGIBLE_PARTICIPANT
        elif (
            offered_protocol_ref != protocol.protocol_ref
            or offered_protocol_ref not in principal.registration_protocol_refs
        ):
            disposition = ExternalAgentHandshakeDisposition.UNSUPPORTED_PROTOCOL
        elif not set(protocol.capability_contract_refs).issubset(offered_capability_refs):
            disposition = ExternalAgentHandshakeDisposition.CAPABILITY_MISMATCH
        return ExternalAgentHandshakeV1Alpha1(
            governance=governance,
            registration_snapshot=principal.registration_snapshot,
            definition=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(definition.definition.definition_revision_id),
                artifact_digest=str(definition.definition.definition_digest),
                artifact_contract=definition.definition.contract,
            ),
            binding=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(binding.binding.binding_revision_id),
                artifact_digest=str(binding.binding.binding_digest),
                artifact_contract=binding.binding.contract,
            ),
            lifecycle_revision_id=_payload_revision_id(principal),
            health_revision_id=_payload_revision_id(health),
            protocol=ExactArtifactReferenceV1Alpha1(
                artifact_id=str(protocol.protocol_id),
                artifact_digest=str(protocol.protocol_digest),
                artifact_contract=protocol.contract,
            ),
            offered_capability_refs=offered_capability_refs,
            required_capability_refs=protocol.capability_contract_refs,
            disposition=disposition,
            checked_at=checked_at,
        )


__all__ = ["ExternalAgentHandshakeError", "ExternalAgentHandshakeService"]
