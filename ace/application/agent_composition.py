"""Application ports for lifecycle-wide agent composition.

The application boundary coordinates planning, Context Manifest resolution,
manifest compilation, execution, deterministic joins, and prepared handoffs.
Adapters supply all persistence, provider, source, destination, and host work.
No port may infer activation or delivery authority from model output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ace.core.agent_composition import (
    ExactArtifactReferenceV1Alpha1,
    StageHandoffContractV1Alpha1,
    StageHandoffReceiptV1Alpha1,
    StageRunManifestV1Alpha1,
    StageRunReceiptV1Alpha1,
    TaskCompositionPlanV1Alpha1,
)
from ace.intelligence.contracts.agent_composition import (
    CompositionCandidateV1Alpha1,
    CompositionRequirementV1Alpha1,
    InstructionContributionV1Alpha1,
    InstructionResolutionReceiptV1Alpha1,
    RosterSelectionReceiptV1Alpha1,
)


class AgentCompositionError(RuntimeError):
    """Raised when a composition precondition fails before execution."""


@dataclass(frozen=True)
class PlanningOutcome:
    plan: TaskCompositionPlanV1Alpha1
    roster_receipt: RosterSelectionReceiptV1Alpha1


@dataclass(frozen=True)
class ContextResolutionOutcome:
    """Opaque I3-compatible Context Manifest and its selection receipt."""

    context_manifest: ExactArtifactReferenceV1Alpha1
    context_selection_receipt: ExactArtifactReferenceV1Alpha1


@dataclass(frozen=True)
class JoinOutcome:
    output_artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...]
    join_receipt: ExactArtifactReferenceV1Alpha1


class CompositionPlanningPort(Protocol):
    async def plan(
        self,
        *,
        requirement: CompositionRequirementV1Alpha1,
        candidates: tuple[CompositionCandidateV1Alpha1, ...],
        instruction_contributions: tuple[InstructionContributionV1Alpha1, ...],
    ) -> PlanningOutcome: ...


class ContextManifestResolutionPort(Protocol):
    async def resolve(
        self,
        *,
        plan: TaskCompositionPlanV1Alpha1,
        node_id: str,
        composition_participant_id: str,
    ) -> ContextResolutionOutcome: ...


class StageRunManifestCompilerPort(Protocol):
    async def compile(
        self,
        *,
        plan: TaskCompositionPlanV1Alpha1,
        node_id: str,
        context: ContextResolutionOutcome,
        instructions: InstructionResolutionReceiptV1Alpha1,
    ) -> StageRunManifestV1Alpha1: ...


class StageExecutionPort(Protocol):
    async def execute(self, manifest: StageRunManifestV1Alpha1) -> StageRunReceiptV1Alpha1: ...


class DeterministicJoinPort(Protocol):
    async def join(
        self,
        *,
        plan: TaskCompositionPlanV1Alpha1,
        node_id: str,
        run_receipts: tuple[StageRunReceiptV1Alpha1, ...],
    ) -> JoinOutcome: ...


class PreparedStageHandoffPort(Protocol):
    async def prepare(
        self,
        *,
        handoff_contract: StageHandoffContractV1Alpha1,
        plan: TaskCompositionPlanV1Alpha1,
        run_receipts: tuple[StageRunReceiptV1Alpha1, ...],
        artifacts: tuple[ExactArtifactReferenceV1Alpha1, ...],
    ) -> StageHandoffReceiptV1Alpha1: ...


class DeliveryEffectPort(Protocol):
    """Separate effect seam; intentionally has no AC1 implementation."""

    async def deliver(self, prepared_handoff: StageHandoffReceiptV1Alpha1) -> ExactArtifactReferenceV1Alpha1: ...


__all__ = [
    "AgentCompositionError",
    "CompositionPlanningPort",
    "ContextManifestResolutionPort",
    "ContextResolutionOutcome",
    "DeliveryEffectPort",
    "DeterministicJoinPort",
    "JoinOutcome",
    "PlanningOutcome",
    "PreparedStageHandoffPort",
    "StageExecutionPort",
    "StageRunManifestCompilerPort",
]
