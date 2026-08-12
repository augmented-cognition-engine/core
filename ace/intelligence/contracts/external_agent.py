"""Provider-neutral external-agent handshake and conformance contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import ExactArtifactReferenceV1Alpha1
from ace.core.agent_governance import AgentGovernanceCoordinateV1Alpha1
from ace.core.contracts import FrozenContract, canonical_hash

EXTERNAL_AGENT_PROTOCOL_IDENTITY_VERSION = "ace.intelligence.external-agent-protocol-identity/v1alpha1"
EXTERNAL_AGENT_HANDSHAKE_VERSION = "ace.intelligence.external-agent-handshake/v1alpha1"


class _Contract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _bounded(value: str, *, name: str) -> str:
    if not value or value != value.strip() or len(value) > 240:
        raise ValueError(f"{name} must be a bounded stable reference")
    return value


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _derive(instance: _Contract, *, prefix: str, id_field: str, digest_field: str) -> None:
    digest = canonical_hash(instance.model_dump(mode="json", exclude={id_field, digest_field}))
    expected_id = f"{prefix}:{digest[:32]}"
    expected_digest = f"sha256:{digest}"
    if getattr(instance, id_field) not in {None, expected_id} or getattr(instance, digest_field) not in {
        None,
        expected_digest,
    }:
        raise ValueError("external-agent identity does not match exact material")
    object.__setattr__(instance, id_field, expected_id)
    object.__setattr__(instance, digest_field, expected_digest)


class ExternalAgentHandshakeDisposition(StrEnum):
    COMPATIBLE = "compatible"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    INELIGIBLE_PARTICIPANT = "ineligible_participant"
    CAPABILITY_MISMATCH = "capability_mismatch"


class ExternalAgentProtocolIdentityV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.external-agent-protocol-identity/v1alpha1"] = (
        EXTERNAL_AGENT_PROTOCOL_IDENTITY_VERSION
    )
    protocol_ref: str
    participant_identity_contract: str
    capability_contract_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    handshake_contract: str = EXTERNAL_AGENT_HANDSHAKE_VERSION
    protocol_id: str | None = None
    protocol_digest: str | None = None

    @field_validator("protocol_ref", "participant_identity_contract", "handshake_contract")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("capability_contract_refs")
    @classmethod
    def normalize_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(_bounded(item, name="capability_contract_refs") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("capability contract references must be unique")
        return normalized

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        _derive(self, prefix="external_agent_protocol", id_field="protocol_id", digest_field="protocol_digest")
        return self


class ExternalAgentHandshakeV1Alpha1(_Contract):
    contract: Literal["ace.intelligence.external-agent-handshake/v1alpha1"] = EXTERNAL_AGENT_HANDSHAKE_VERSION
    governance: AgentGovernanceCoordinateV1Alpha1
    registration_snapshot: ExactArtifactReferenceV1Alpha1
    definition: ExactArtifactReferenceV1Alpha1
    binding: ExactArtifactReferenceV1Alpha1
    lifecycle_revision_id: str
    health_revision_id: str
    protocol: ExactArtifactReferenceV1Alpha1
    offered_capability_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    required_capability_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    disposition: ExternalAgentHandshakeDisposition
    checked_at: datetime
    installation_grants_authority: Literal[False] = False
    handshake_grants_execution: Literal[False] = False
    handshake_grants_delivery: Literal[False] = False
    conformance_grants_authority: Literal[False] = False
    reusable_authority: Literal[False] = False
    receipt_id: str | None = None
    receipt_digest: str | None = None

    @field_validator("lifecycle_revision_id", "health_revision_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return _bounded(value, name=info.field_name)

    @field_validator("offered_capability_refs", "required_capability_refs")
    @classmethod
    def normalize_capabilities(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = tuple(sorted(_bounded(item, name=info.field_name) for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("checked_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value, name="checked_at")

    @model_validator(mode="after")
    def validate_disposition_and_identity(self) -> Self:
        capabilities_match = set(self.required_capability_refs).issubset(self.offered_capability_refs)
        if self.disposition is ExternalAgentHandshakeDisposition.COMPATIBLE and not capabilities_match:
            raise ValueError("compatible external-agent handshake lacks required capabilities")
        if self.disposition is ExternalAgentHandshakeDisposition.CAPABILITY_MISMATCH and capabilities_match:
            raise ValueError("capability mismatch requires an actual missing capability")
        _derive(self, prefix="external_agent_handshake", id_field="receipt_id", digest_field="receipt_digest")
        return self


__all__ = [
    "EXTERNAL_AGENT_HANDSHAKE_VERSION",
    "EXTERNAL_AGENT_PROTOCOL_IDENTITY_VERSION",
    "ExternalAgentHandshakeDisposition",
    "ExternalAgentHandshakeV1Alpha1",
    "ExternalAgentProtocolIdentityV1Alpha1",
]
