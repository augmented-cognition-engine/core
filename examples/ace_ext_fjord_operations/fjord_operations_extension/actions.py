"""Fjord-owned action wrappers over ACE's shipped grounded-state reference behavior."""

from __future__ import annotations

from extensions.reference.evidence_query import (
    OUTCOME_CONTRACT as EVIDENCE_QUERY_OUTCOME_CONTRACT,
)
from extensions.reference.evidence_query import prepare_evidence_query as _prepare_evidence_query
from extensions.reference.evidence_query import project_evidence_query
from extensions.reference.promotion import (
    OUTCOME_CONTRACT as PROMOTION_OUTCOME_CONTRACT,
)
from extensions.reference.promotion import prepare_promotion_review, project_promotion_review


async def prepare_evidence_query(envelope, actor):
    """Retain the reference contract while adding one product acceptance hook."""

    plan = await _prepare_evidence_query(envelope, actor)
    if envelope.parameters.get("restart_interruption") is True:
        plan = plan.model_copy(update={"description": ("Fjord restart interruption acceptance. " + plan.description)})
    return plan


__all__ = [
    "EVIDENCE_QUERY_OUTCOME_CONTRACT",
    "PROMOTION_OUTCOME_CONTRACT",
    "prepare_evidence_query",
    "prepare_promotion_review",
    "project_evidence_query",
    "project_promotion_review",
]
