"""Stable Core lookup coordinates for governed agent onboarding.

The coordinate in this module is deliberately content-free.  Registration
snapshots, lifecycle, grants, health, and authority remain exact evidence in
separate governed records and must never influence this stable identity.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import ConfigDict, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash

AGENT_GOVERNANCE_COORDINATE_VERSION = "ace.core.agent-governance-coordinate/v1alpha1"


class AgentGovernanceCoordinateV1Alpha1(FrozenContract):
    """Stable product/principal-key coordinate; neither evidence nor authority."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )

    contract: Literal["ace.core.agent-governance-coordinate/v1alpha1"] = AGENT_GOVERNANCE_COORDINATE_VERSION
    product_id: str
    principal_key: str
    governance_id: str | None = None

    @field_validator("product_id", "principal_key")
    @classmethod
    def validate_coordinate(cls, value: str, info) -> str:
        if not value or value != value.strip() or len(value) > 240:
            raise ValueError(f"{info.field_name} must be non-empty, trimmed, and at most 240 characters")
        return value

    @model_validator(mode="after")
    def derive_identity(self) -> Self:
        digest = canonical_hash([self.product_id, self.principal_key])
        expected = f"agent_governance:{digest[:32]}"
        if self.governance_id is not None and self.governance_id != expected:
            raise ValueError("governance_id must derive only from product_id and principal_key")
        object.__setattr__(self, "governance_id", expected)
        return self


__all__ = [
    "AGENT_GOVERNANCE_COORDINATE_VERSION",
    "AgentGovernanceCoordinateV1Alpha1",
]
