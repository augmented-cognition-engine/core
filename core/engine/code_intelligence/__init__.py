"""Bounded Code Intelligence solution surface.

This package composes the existing repository scanner, code graph, context,
decision-memory, and handoff foundations.  It is intentionally outside the
domain-neutral :mod:`ace.core` and :mod:`ace.intelligence` contract layers.
"""

from core.engine.code_intelligence.contracts import (
    AtriumCodeLensV1Alpha1,
    BoundedCodeHandoffV1Alpha1,
    CodeIntelligenceJourneyV1Alpha1,
    CodeIntelligenceReplayExpectationV1Alpha1,
    CodeIntelligenceSingleChainLivingRunV1Alpha1,
    CodingAgentReturnReceiptV1Alpha1,
    CodingAgentReturnV1Alpha1,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return
from core.engine.code_intelligence.incident_index_binding import (
    ExactCoordinateArtifactV1Alpha1,
    ExactLocalRepositoryIndexV1Alpha1,
    ExactLocalRepositorySnapshotV1Alpha1,
    IncidentIndexBindingError,
    IncidentLocalIndexBindingReceiptV1Alpha1,
    bind_incident_projection_to_local_index,
    capture_exact_local_repository_snapshot,
    revalidate_exact_local_repository_snapshot,
    validate_incident_local_index_binding,
)
from core.engine.code_intelligence.incidents import (
    IncidentProjectionError,
    IncidentSourceEnvelopeV1Alpha1,
    IncidentToCodeProjectionV1Alpha1,
    project_public_incident_to_code,
    validate_incident_projection_against_source,
)
from core.engine.code_intelligence.journey import CodeIntelligenceJourney
from core.engine.code_intelligence.living_run import (
    validate_single_chain_living_run,
    validate_single_chain_replay_envelope,
)
from core.engine.code_intelligence.ownership import (
    CodeOwnershipProjectionV1Alpha1,
    GitHubCodeownersAdapter,
    OwnershipProjectionStatus,
)
from core.engine.code_intelligence.snapshot_store import (
    DurablePhase1IndexSnapshotV1Alpha1,
    DurablePhase1IndexStore,
    ReopenedPhase1Index,
)

__all__ = [
    "AtriumCodeLensV1Alpha1",
    "BoundedCodeHandoffV1Alpha1",
    "CodeIntelligenceJourney",
    "CodeIntelligenceJourneyV1Alpha1",
    "CodeIntelligenceReplayExpectationV1Alpha1",
    "CodeIntelligenceSingleChainLivingRunV1Alpha1",
    "CodeOwnershipProjectionV1Alpha1",
    "CodingAgentReturnReceiptV1Alpha1",
    "CodingAgentReturnV1Alpha1",
    "DurablePhase1IndexSnapshotV1Alpha1",
    "DurablePhase1IndexStore",
    "ExactCoordinateArtifactV1Alpha1",
    "ExactLocalRepositoryIndexV1Alpha1",
    "ExactLocalRepositorySnapshotV1Alpha1",
    "GitHubCodeownersAdapter",
    "IncidentIndexBindingError",
    "IncidentLocalIndexBindingReceiptV1Alpha1",
    "IncidentProjectionError",
    "IncidentSourceEnvelopeV1Alpha1",
    "IncidentToCodeProjectionV1Alpha1",
    "OwnershipProjectionStatus",
    "ReopenedPhase1Index",
    "bind_incident_projection_to_local_index",
    "capture_exact_local_repository_snapshot",
    "project_public_incident_to_code",
    "revalidate_exact_local_repository_snapshot",
    "validate_coding_agent_return",
    "validate_incident_local_index_binding",
    "validate_incident_projection_against_source",
    "validate_single_chain_living_run",
    "validate_single_chain_replay_envelope",
]
