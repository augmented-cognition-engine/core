#!/usr/bin/env python3
"""Deterministic Lane F0 scenario; no database or paid model is required."""

from __future__ import annotations

import json

from core.engine.graph.assertions import RelationshipProposal, resolve_proposals


def main() -> None:
    proposals = [
        RelationshipProposal(
            subject="decision:cache",
            predicate="enhances",
            object="capability:latency",
            model="fixture-a",
            provider="api",
            evidence_refs=["observation:benchmark"],
            rationale="The cache reduces measured latency.",
        ),
        RelationshipProposal(
            subject="decision:cache",
            predicate="improves",
            object="capability:latency",
            model="fixture-b",
            provider="local",
            evidence_refs=["observation:benchmark"],
            rationale="The cache improves latency.",
        ),
    ]
    before = resolve_proposals(proposals)
    replay = resolve_proposals(list(reversed(proposals)))
    correction = RelationshipProposal(
        subject="decision:cache",
        predicate="breaks",
        object="capability:latency",
        model="fixture-critic",
        provider="subscription",
        evidence_refs=["observation:incident"],
    )
    after = resolve_proposals(proposals + [correction])
    print(
        json.dumps(
            {
                "proposals": [p.model_dump(mode="json") | {"proposal_id": p.event_id()} for p in proposals],
                "canonical_assertions": [a.model_dump(mode="json") for a in before],
                "operational_projection": [[a.subject, a.predicate, a.object] for a in before if a.projection_eligible],
                "replay_identical": before == replay,
                "later_observation": correction.model_dump(mode="json"),
                "post_correction": [a.model_dump(mode="json") for a in after],
                "dependent_consequences": ["relationship_assertion:fixture-capacity-plan"],
                "truth_maintenance_action": "A persisted assertion_dependency walk marks the capacity-plan assertion stale and removes its projection.",
                "post_correction_replay_identical": after == resolve_proposals([correction, *reversed(proposals)]),
                "explanation": "The incident conflicts with the prior improvement claim in the same scope. Both assertions become contested; neither remains operational.",
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
