"""Thin HTTP host contracts for the WS3 Builder-session progression API.

Per the frozen Builder-session progression addendum (PI13 addendum 9), the
production coordinators in ``local_source_connect_progression``,
``intelligence_builder_concept_progression``, and
``intelligence_builder_intelligence_progression`` already own every
governed transition. This module adds only the two request envelopes those
coordinators do not already define (bundling one exact recorded Connect
request/result with the Builder-side material each route needs) and one
stable, limited response envelope per route -- exposing only the relevant
exact artifact(s), a reviewed approval when one was made, and the resulting
session revision. It never exposes a raw admission/store object.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from ace.application.briefing_agent_contracts import FirstBriefingPreviewV1
from ace.application.intelligence_agent_contracts import IntelligenceModelDispositionV1, IntelligenceModelProposalV1
from ace.application.intelligence_builder_contracts import (
    IntelligenceBuilderSessionRevisionV1,
    OnboardingBlockReason,
    SourceProfileProposalV1,
    SourceScopeProposalV1,
)
from ace.application.local_source_connect import (
    LocalSourceConnectAuthorizationRequest,
    LocalSourceConnectAuthorizationResult,
)
from ace.application.ontology_agent_contracts import ConceptModelDispositionV1, ConceptModelProposalV1
from core.engine.core.intelligence_builder_disposition_authority import (
    BuilderDispositionApprovalResultV1Alpha1,
    BuilderSourceScopeApproveRequestV1Alpha1,
)


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class BuilderSourceScopeProposeRequestV1Alpha1(BaseModel):
    """One explicit request to propose the source scope from one exact recorded Connect result."""

    model_config = ConfigDict(extra="forbid")

    connect_request: LocalSourceConnectAuthorizationRequest
    connect_result: LocalSourceConnectAuthorizationResult
    current: IntelligenceBuilderSessionRevisionV1
    occurred_at: datetime

    @field_validator("connect_request", "connect_result", "current", mode="before")
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = {
                "connect_request": LocalSourceConnectAuthorizationRequest,
                "connect_result": LocalSourceConnectAuthorizationResult,
                "current": IntelligenceBuilderSessionRevisionV1,
            }[info.field_name]
            return model.model_validate(value, strict=False)
        return value

    @field_validator("occurred_at")
    @classmethod
    def _occurred_time(cls, value: datetime) -> datetime:
        return _aware(value, name="occurred_at")


class BuilderSourceScopeApproveConnectRequestV1Alpha1(BaseModel):
    """One explicit source-scope owner approval, immediately followed by connect.

    Bundles the same exact recorded Connect request/result the proposal used
    with one explicit ``BuilderSourceScopeApproveRequestV1Alpha1`` decision.
    This is exactly one source-scope owner decision followed by connect: it
    exposes no approval-only shortcut and bundles no other approval.
    """

    model_config = ConfigDict(extra="forbid")

    connect_request: LocalSourceConnectAuthorizationRequest
    connect_result: LocalSourceConnectAuthorizationResult
    approval: BuilderSourceScopeApproveRequestV1Alpha1

    @field_validator("connect_request", "connect_result", "approval", mode="before")
    @classmethod
    def _json_material(cls, value, info):
        if isinstance(value, dict):
            model = {
                "connect_request": LocalSourceConnectAuthorizationRequest,
                "connect_result": LocalSourceConnectAuthorizationResult,
                "approval": BuilderSourceScopeApproveRequestV1Alpha1,
            }[info.field_name]
            return model.model_validate(value, strict=False)
        return value


class BuilderSourceScopeProposeResultV1Alpha1(BaseModel):
    """The proposed source-scope artifact and the resulting session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-source-scope-propose-result/v1alpha1"
    proposal: SourceScopeProposalV1
    session_revision: IntelligenceBuilderSessionRevisionV1


class BuilderSourceScopeApproveConnectResultV1Alpha1(BaseModel):
    """The reviewed source-scope approval, the resulting connect profile, and the session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-source-scope-approve-connect-result/v1alpha1"
    reviewed_approval: BuilderDispositionApprovalResultV1Alpha1
    profile: SourceProfileProposalV1 | None
    session_revision: IntelligenceBuilderSessionRevisionV1
    blocked_reason: OnboardingBlockReason | None


class BuilderConceptModelProposeResultV1Alpha1(BaseModel):
    """The proposed concept-model artifact and the resulting session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-concept-model-propose-result/v1alpha1"
    proposal: ConceptModelProposalV1
    session_revision: IntelligenceBuilderSessionRevisionV1


class BuilderConceptModelApproveResultV1Alpha1(BaseModel):
    """The reviewed concept-model approval, its disposition, and the resulting session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-concept-model-approve-result/v1alpha1"
    reviewed_approval: BuilderDispositionApprovalResultV1Alpha1
    proposal: ConceptModelProposalV1
    disposition: ConceptModelDispositionV1
    session_revision: IntelligenceBuilderSessionRevisionV1


class BuilderIntelligenceModelProposeResultV1Alpha1(BaseModel):
    """The proposed intelligence-model artifact and the resulting session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-intelligence-model-propose-result/v1alpha1"
    proposal: IntelligenceModelProposalV1
    session_revision: IntelligenceBuilderSessionRevisionV1


class BuilderIntelligenceModelApproveResultV1Alpha1(BaseModel):
    """The reviewed intelligence-model approval, its disposition, and the resulting session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-intelligence-model-approve-result/v1alpha1"
    reviewed_approval: BuilderDispositionApprovalResultV1Alpha1
    proposal: IntelligenceModelProposalV1
    disposition: IntelligenceModelDispositionV1
    session_revision: IntelligenceBuilderSessionRevisionV1


class BuilderFirstBriefPrepareResultV1Alpha1(BaseModel):
    """The prepared first-Brief artifact and the resulting session revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = "ace.http.builder-first-brief-prepare-result/v1alpha1"
    brief: FirstBriefingPreviewV1
    session_revision: IntelligenceBuilderSessionRevisionV1


__all__ = [
    "BuilderConceptModelApproveResultV1Alpha1",
    "BuilderConceptModelProposeResultV1Alpha1",
    "BuilderFirstBriefPrepareResultV1Alpha1",
    "BuilderIntelligenceModelApproveResultV1Alpha1",
    "BuilderIntelligenceModelProposeResultV1Alpha1",
    "BuilderSourceScopeApproveConnectRequestV1Alpha1",
    "BuilderSourceScopeApproveConnectResultV1Alpha1",
    "BuilderSourceScopeProposeRequestV1Alpha1",
    "BuilderSourceScopeProposeResultV1Alpha1",
]
