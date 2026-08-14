"""Exact durable Builder artifacts for the activation boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import field_validator, model_validator

from ace.application.domain_activation_plan_contracts import DomainActivationCommitReferenceV1Alpha2
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderContract,
    aware_datetime,
    derive_builder_identity,
)
from ace.intelligence.contracts.activation import CompiledPackRefV1
from ace.intelligence.contracts.common import validate_digest, validate_reference
from ace.intelligence.contracts.resources import ActivationRevisionReferenceV1Alpha1

BUILDER_ACTIVATION_PLAN_ARTIFACT_VERSION = "ace.application.builder-activation-plan-artifact/v1alpha1"
BUILDER_ACTIVATION_RECEIPT_ARTIFACT_VERSION = "ace.application.builder-activation-receipt-artifact/v1alpha1"


class BuilderActivationPlanArtifactV1(IntelligenceBuilderContract):
    """Exact committed v1alpha2 plan linked to its Builder session and Pack ref."""

    contract: Literal["ace.application.builder-activation-plan-artifact/v1alpha1"] = (
        BUILDER_ACTIVATION_PLAN_ARTIFACT_VERSION
    )
    session_id: str
    session_revision_id: str
    session_revision_digest: str
    source_commit: DomainActivationCommitReferenceV1Alpha2
    spec_id: str
    spec_digest: str
    pack: CompiledPackRefV1
    created_at: datetime
    artifact_id: str | None = None
    artifact_digest: str | None = None

    @field_validator("session_id", "session_revision_id", "spec_id", "artifact_id")
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator("session_revision_digest", "spec_digest", "artifact_digest")
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("created_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="created_at")

    @model_validator(mode="after")
    def derive_identity(self):
        if self.created_at < self.source_commit.committed_at:
            raise ValueError("activation-plan artifact cannot predate its governed commit")
        derive_builder_identity(
            self,
            prefix="builder_activation_plan_artifact",
            id_field="artifact_id",
            digest_field="artifact_digest",
        )
        return self


class BuilderActivationReceiptArtifactV1(IntelligenceBuilderContract):
    """Non-authorizing linkage from a Builder plan to canonical activation."""

    contract: Literal["ace.application.builder-activation-receipt-artifact/v1alpha1"] = (
        BUILDER_ACTIVATION_RECEIPT_ARTIFACT_VERSION
    )
    session_id: str
    activation_plan_artifact_id: str
    activation_plan_artifact_digest: str
    source_commit: DomainActivationCommitReferenceV1Alpha2
    canonical_revision: ActivationRevisionReferenceV1Alpha1
    canonical_state_kind: Literal["domain_activation_v1alpha1", "domain_activation"]
    canonical_commit_receipt_id: str
    canonical_commit_receipt_digest: str
    activated_at: datetime
    artifact_id: str | None = None
    artifact_digest: str | None = None

    @field_validator(
        "session_id",
        "activation_plan_artifact_id",
        "canonical_commit_receipt_id",
        "artifact_id",
    )
    @classmethod
    def validate_refs(cls, value: str | None, info) -> str | None:
        return validate_reference(value, name=info.field_name) if value is not None else None

    @field_validator(
        "activation_plan_artifact_digest",
        "canonical_commit_receipt_digest",
        "artifact_digest",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info) -> str | None:
        return validate_digest(value) if value is not None else None

    @field_validator("activated_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return aware_datetime(value, name="activated_at")

    @model_validator(mode="after")
    def validate_linkage_and_derive(self):
        if (
            self.source_commit.product_id != self.canonical_revision.product_id
            or self.source_commit.activation_key != self.canonical_revision.activation_key
            or self.source_commit.activation_id != self.canonical_revision.activation_id
            or self.activated_at < self.source_commit.committed_at
        ):
            raise ValueError("activation receipt crossed its exact source/canonical scope")
        derive_builder_identity(
            self,
            prefix="builder_activation_receipt_artifact",
            id_field="artifact_id",
            digest_field="artifact_digest",
        )
        return self


__all__ = [
    "BUILDER_ACTIVATION_PLAN_ARTIFACT_VERSION",
    "BUILDER_ACTIVATION_RECEIPT_ARTIFACT_VERSION",
    "BuilderActivationPlanArtifactV1",
    "BuilderActivationReceiptArtifactV1",
]
