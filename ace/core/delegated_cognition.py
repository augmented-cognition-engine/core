"""Public delegated-cognition authority vocabulary.

The application provisioning service and legacy host adapters share these
pure contracts. Keeping the vocabulary in ``ace.core`` prevents the public
application layer from depending inward on ``core.engine`` implementation
modules while preserving the exact serialized grant contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.agent_composition import AuthorityClass
from ace.core.contracts import FrozenContract

GRANT_PAYLOAD_CONTRACT = "ace.host.composition-authority-grant/v1alpha1"

REVIEW_OPERATION = "review_governed_cognition_capture"
ACTIVATION_OPERATION = "activate_governed_cognition_revision"
REVIEW_AUTHORITY_CLASS = AuthorityClass.DECIDE_APPROVE
ACTIVATION_AUTHORITY_CLASS = AuthorityClass.MUTATE_INTERNAL


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class CompositionAuthorityGrantMaterial(FrozenContract):
    """Exact governed material for one bounded composition authority grant."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")

    contract: Literal["ace.host.composition-authority-grant/v1alpha1"] = GRANT_PAYLOAD_CONTRACT
    grant_ref: str
    product_id: str
    actor_ref: str
    participant_principal_ref: str
    delegator_ref: str | None = None
    authority_class: AuthorityClass
    operations: tuple[str, ...] = Field(min_length=1, max_length=32)
    scope_ref: str
    policy_ref: str
    grant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lifecycle: Literal["active", "revoked", "expired"]
    effective_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    delegation_ceiling: tuple[AuthorityClass, ...] = ()

    @field_validator("effective_at", "expires_at", "revoked_at")
    @classmethod
    def validate_times(cls, value: datetime | None, info) -> datetime | None:
        return _aware(value, info.field_name) if value is not None else None

    @field_validator("operations")
    @classmethod
    def normalize_operations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("grant operations must be unique")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValueError("grant expiry must follow its effective time")
        if self.lifecycle == "revoked" and self.revoked_at is None:
            raise ValueError("revoked grant requires revoked_at")
        if self.delegator_ref is not None and self.authority_class not in self.delegation_ceiling:
            raise ValueError("delegated grant exceeds its declared delegation ceiling")
        return self


__all__ = [
    "ACTIVATION_AUTHORITY_CLASS",
    "ACTIVATION_OPERATION",
    "GRANT_PAYLOAD_CONTRACT",
    "REVIEW_AUTHORITY_CLASS",
    "REVIEW_OPERATION",
    "CompositionAuthorityGrantMaterial",
]
