# engine/capture/cognify.py
"""Cognify — ACE's knowledge-forming relationship proposal stage.

When new insights land, find related existing insights (injected candidate-finder),
ask one structured LLM call which declared relationships may connect them, then
persist evidence-bearing proposals for deterministic resolution.  Model output
never writes authoritative graph edges. Non-fatal throughout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from core.engine.core.llm import get_llm
from core.engine.graph.assertions import RelationshipProposal, persist_resolution
from core.engine.graph.ontology import RELATIONSHIPS

logger = logging.getLogger(__name__)

# Insight-relationship RELATION tables defined in v031_graph.surql.
EDGE_TYPES = tuple(RELATIONSHIPS)

CandidateFinder = Callable[[dict], Awaitable[list[dict]]]

__all__ = ["EdgeProposal", "EDGE_TYPES", "extract_relationships", "cognify"]


@dataclass(frozen=True)
class EdgeProposal:
    from_id: str
    to_id: str
    edge_type: str
    confidence: float
    evidence_refs: tuple[str, ...] = ()
    rationale: str = ""
    model: str | None = None
    provider: str | None = None
    workflow: str = "cognify.v2"


class _Relation(BaseModel):
    candidate_index: int = Field(description="0-based index into the candidate list")
    edge_type: str = Field(description=f"one of {EDGE_TYPES}, or 'none'")
    new_is_source: bool = Field(default=True, description="True: new -> candidate; False: candidate -> new")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = Field(default="", description="Why the supplied evidence supports this relationship")


class _Extraction(BaseModel):
    relations: list[_Relation] = Field(default_factory=list)


def _prompt(new_insight: dict, candidates: list[dict]) -> str:
    cand_block = "\n".join(f"[{i}] {c.get('content', '')}" for i, c in enumerate(candidates))
    return (
        "You are mapping relationships in a knowledge graph. Given a NEW insight and a list of "
        "candidate existing insights, identify which candidates the new insight has a TYPED "
        f"relationship with. Relationship types: {', '.join(EDGE_TYPES)}. Use 'none' when there is no "
        "real relationship — most pairs have none. Give each a 0-1 confidence and the direction "
        "(new_is_source=true means new -> candidate).\n\n"
        f"NEW insight:\n{new_insight.get('content', '')}\n\n"
        f"CANDIDATES:\n{cand_block}"
    )


async def extract_relationships(
    new_insights: list[dict],
    find_candidates: CandidateFinder,
    min_confidence: float = 0.6,
    candidate_k: int = 8,
) -> list[EdgeProposal]:
    """Extract typed edge proposals between each new insight and its candidates. Non-fatal."""
    proposals: list[EdgeProposal] = []
    for insight in new_insights:
        try:
            candidates = (await find_candidates(insight))[:candidate_k]
            if not candidates:
                continue
            extraction = await get_llm().complete_structured(_prompt(insight, candidates), schema=_Extraction)
            for rel in extraction.relations:
                if rel.edge_type not in EDGE_TYPES:
                    continue  # 'none' / unknown
                if rel.confidence < min_confidence:
                    continue
                if not (0 <= rel.candidate_index < len(candidates)):
                    continue  # hallucinated index
                cand_id = candidates[rel.candidate_index].get("id")
                new_id = insight.get("id")
                if not cand_id or not new_id or cand_id == new_id:
                    continue  # self / missing
                frm, to = (new_id, cand_id) if rel.new_is_source else (cand_id, new_id)
                proposals.append(
                    EdgeProposal(
                        from_id=frm,
                        to_id=to,
                        edge_type=rel.edge_type,
                        confidence=rel.confidence,
                        evidence_refs=tuple(sorted({str(insight.get("id")), str(cand_id)})),
                        rationale=getattr(rel, "rationale", ""),
                    )
                )
        except Exception as exc:  # never break capture
            logger.debug("Cognify extraction failed for insight %s (non-fatal): %s", insight.get("id"), exc)
    return proposals


async def cognify(
    new_insights: list[dict],
    find_candidates: CandidateFinder,
    min_confidence: float = 0.6,
    candidate_k: int = 8,
) -> int:
    """Extract relationships and persist proposals/assertions. Returns proposals processed.

    Fully non-fatal — capture must never break.  The deterministic resolver and
    projection own operational graph mutation; critic/model output cannot do so.
    """
    proposals = await extract_relationships(
        new_insights, find_candidates, min_confidence=min_confidence, candidate_k=candidate_k
    )
    assertions = [
        RelationshipProposal(
            subject=p.from_id,
            predicate=p.edge_type,
            object=p.to_id,
            evidence_refs=list(p.evidence_refs),
            source_records=list(p.evidence_refs),
            rationale=p.rationale,
            proposal_confidence=p.confidence,
            origin_type="model",
            model=p.model,
            provider=p.provider,
            workflow=p.workflow,
            prompt_version="cognify.relationship-extraction.v2",
        )
        for p in proposals
    ]
    if not assertions:
        return 0
    try:
        await persist_resolution(assertions)
        return len(assertions)
    except Exception as exc:
        logger.debug("Cognify assertion ingestion failed for %d proposal(s): %s", len(assertions), exc)
        return 0
