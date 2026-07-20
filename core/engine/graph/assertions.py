"""Relational assertions, deterministic resolution, and operational projection.

Models create proposal events.  Assertion identity and resolution depend only on
semantic inputs and versioned policy, never provider, arrival order, or model
confidence.  Persistence functions use the same pure resolver exercised by
replay and permutation tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.engine.core.db import parse_one, parse_record_id, parse_rows, serialize_record
from core.engine.graph.ontology import ONTOLOGY_VERSION, RELATIONSHIPS, normalize_predicate, type_allowed

RESOLVER_VERSION = "ace.assertion-resolver.v1"
_PERSIST_LOCK = asyncio.Lock()
AssertionStatus = Literal[
    "proposed", "provisional", "accepted", "contested", "rejected", "superseded", "stale", "retired"
]
ReviewDepth = Literal["none", "light", "standard", "deep", "human-required"]


def _stable_id(prefix: str, value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"{prefix}:{hashlib.sha256(raw).hexdigest()[:32]}"


async def _query_or_raise(db, query: str, params: dict | None = None):
    """SurrealDB can return statement failures as strings; kernel writes fail closed."""
    result = await db.query(query, params or {})
    if isinstance(result, str):
        raise RuntimeError(f"relational assertion persistence failed: {result}")
    return result


class RelationshipProposal(BaseModel):
    subject: str
    predicate: str
    object: str
    subject_type: str | None = None
    object_type: str | None = None
    polarity: Literal["positive", "negative"] = "positive"
    scope: dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    source_records: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    rationale: str = ""
    proposal_confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_strength: float | None = Field(default=None, ge=0, le=1)
    provenance_quality: float | None = Field(default=None, ge=0, le=1)
    freshness: float | None = Field(default=None, ge=0, le=1)
    origin_type: str = "model"
    proposer: str | None = None
    model: str | None = None
    provider: str | None = None
    workflow: str | None = None
    prompt_version: str | None = None
    ontology_version: str = ONTOLOGY_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)

    def event_id(self) -> str:
        return _stable_id("relationship_proposal", self.model_dump(mode="json", exclude_none=True))


class AssertionReview(BaseModel):
    target_assertion: str
    reviewer_role: str = "critic"
    model: str | None = None
    provider: str | None = None
    path: str | None = None
    verdict: Literal["support", "object", "refine", "unavailable"]
    objections: list[str] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    alternative_predicates: list[str] = Field(default_factory=list)
    missing_assumptions: list[str] = Field(default_factory=list)
    proposed_scope: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    confidence: float = Field(default=0.5, ge=0, le=1)
    ontology_version: str = ONTOLOGY_VERSION
    reviewer_policy_version: str = "ace.assertion-review.v1"

    def review_id(self) -> str:
        return _stable_id("assertion_review", self.model_dump(mode="json", exclude_none=True))


class CanonicalAssertion(BaseModel):
    id: str
    subject: str
    predicate: str
    object: str
    family: str
    polarity: str
    scope: dict[str, Any]
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: AssertionStatus
    proposal_confidence: float
    evidence_strength: float
    resolver_certainty: float
    provenance_quality: float
    freshness: float
    evidence_refs: list[str]
    supporting_assertions: list[str] = Field(default_factory=list)
    contradicting_assertions: list[str] = Field(default_factory=list)
    assumptions: list[str]
    proposal_ids: list[str]
    ontology_version: str
    resolver_version: str
    projection_eligible: bool
    review_depth: ReviewDepth
    explanation: str
    degraded_reason: str | None = None


def _semantic_key(subject: str, predicate: str, object_: str, polarity: str, scope: dict, valid_from, valid_to) -> dict:
    return {
        "subject": subject,
        "predicate": predicate,
        "object": object_,
        "polarity": polarity,
        "scope": scope,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "ontology_version": ONTOLOGY_VERSION,
    }


def review_depth_for(
    proposal: RelationshipProposal,
    *,
    conflict: bool = False,
    high_centrality: bool = False,
    sensitive: bool = False,
    privacy_mode: bool = False,
    budget: Literal["low", "standard", "high"] = "standard",
) -> ReviewDepth:
    normalized = normalize_predicate(proposal.predicate)
    if not normalized:
        return "standard" if budget != "low" else "light"
    contract = RELATIONSHIPS[normalized[0]]
    if contract.human_confirmation or sensitive:
        return "human-required"
    if conflict or high_centrality or contract.causal or len(proposal.evidence_refs) < contract.minimum_evidence:
        if privacy_mode:
            return "standard"
        return "deep" if budget == "high" else ("standard" if budget == "standard" else "light")
    return "none"


def resolve_proposals(
    proposals: list[RelationshipProposal],
    reviews: list[AssertionReview] | None = None,
    human_confirmed: set[str] | None = None,
) -> list[CanonicalAssertion]:
    """Resolve proposal events into an order-independent canonical assertion set."""
    reviews = reviews or []
    human_confirmed = human_confirmed or set()
    grouped: dict[str, tuple[dict, list[RelationshipProposal], Any]] = {}
    invalid: list[CanonicalAssertion] = []
    for p in proposals:
        normalized = normalize_predicate(p.predicate)
        if normalized is None:
            aid = _stable_id(
                "relationship_assertion",
                _semantic_key(p.subject, p.predicate, p.object, p.polarity, p.scope, p.valid_from, p.valid_to),
            )
            invalid.append(
                CanonicalAssertion(
                    id=aid,
                    subject=p.subject,
                    predicate=p.predicate,
                    object=p.object,
                    family="unknown",
                    polarity=p.polarity,
                    scope=p.scope,
                    valid_from=p.valid_from,
                    valid_to=p.valid_to,
                    status="rejected",
                    proposal_confidence=p.proposal_confidence,
                    evidence_strength=p.evidence_strength or 0,
                    resolver_certainty=1,
                    provenance_quality=p.provenance_quality or 0,
                    freshness=p.freshness or 1,
                    evidence_refs=sorted(set(p.evidence_refs)),
                    assumptions=sorted(set(p.assumptions)),
                    proposal_ids=[p.event_id()],
                    ontology_version=p.ontology_version,
                    resolver_version=RESOLVER_VERSION,
                    projection_eligible=False,
                    review_depth=review_depth_for(p),
                    explanation="Invalid: predicate is not declared by the ontology.",
                )
            )
            continue
        predicate, swap = normalized
        subject, object_ = (p.object, p.subject) if swap else (p.subject, p.object)
        contract = RELATIONSHIPS[predicate]
        key = _semantic_key(subject, predicate, object_, p.polarity, p.scope, p.valid_from, p.valid_to)
        aid = _stable_id("relationship_assertion", key)
        grouped.setdefault(aid, (key, [], contract))[1].append(p)

    result = invalid
    for aid in sorted(grouped):
        key, ps, contract = grouped[aid]
        ps = sorted(ps, key=lambda p: p.event_id())
        evidence = sorted({e for p in ps for e in p.evidence_refs})
        assumptions = sorted({a for p in ps for a in p.assumptions})
        typed = type_allowed(contract.subject_types, key["subject"]) and type_allowed(
            contract.object_types, key["object"]
        )
        enough_evidence = len(evidence) >= contract.minimum_evidence
        related_reviews = [r for r in reviews if r.target_assertion == aid]
        objected = any(r.verdict == "object" and r.severity in {"high", "critical"} for r in related_reviews)
        unavailable = any(r.verdict == "unavailable" for r in related_reviews)
        confirmed = aid in human_confirmed
        depth = max(
            (review_depth_for(p) for p in ps), key=("none", "light", "standard", "deep", "human-required").index
        )
        if not typed:
            status, explanation = "rejected", "Invalid: subject/object types violate the ontology contract."
        elif objected:
            status, explanation = (
                "contested",
                "Contested: a persisted high-severity review objection requires resolution.",
            )
        elif contract.human_confirmation and not confirmed:
            status, explanation = (
                "provisional",
                "Provisional: this consequential predicate requires explicit human confirmation.",
            )
        elif not enough_evidence:
            status, explanation = "provisional", "Provisional: the deterministic evidence requirement is not met."
        else:
            status, explanation = (
                "accepted",
                "Accepted by deterministic ontology, typing, evidence, and confirmation policy.",
            )
        result.append(
            CanonicalAssertion(
                id=aid,
                subject=key["subject"],
                predicate=key["predicate"],
                object=key["object"],
                family=contract.family,
                polarity=key["polarity"],
                scope=key["scope"],
                valid_from=key["valid_from"],
                valid_to=key["valid_to"],
                status=status,
                proposal_confidence=max(p.proposal_confidence for p in ps),
                evidence_strength=min(1.0, len(evidence) / max(1, contract.minimum_evidence)),
                resolver_certainty=1.0 if typed else 0.0,
                provenance_quality=max((p.provenance_quality or 0.5) for p in ps),
                freshness=min((p.freshness or 1.0) for p in ps),
                evidence_refs=evidence,
                assumptions=assumptions,
                proposal_ids=sorted({p.event_id() for p in ps}),
                ontology_version=ONTOLOGY_VERSION,
                resolver_version=RESOLVER_VERSION,
                projection_eligible=status == "accepted" and contract.projectable and key["polarity"] == "positive",
                review_depth=depth,
                explanation=explanation,
                degraded_reason="reviewer_unavailable" if unavailable else None,
            )
        )

    # Exclusivity is evaluated after canonical grouping and is scope-specific.
    by_pair: dict[tuple, list[CanonicalAssertion]] = {}
    for a in result:
        by_pair.setdefault(
            (a.subject, a.object, json.dumps(a.scope, sort_keys=True), str(a.valid_from), str(a.valid_to)), []
        ).append(a)
    for assertions in by_pair.values():
        names = {a.predicate for a in assertions if a.status not in {"rejected", "retired", "superseded"}}
        for a in assertions:
            own_exclusive = RELATIONSHIPS.get(a.predicate, RelationshipContractStub()).exclusive
            mutually_exclusive = any(
                other in own_exclusive or a.predicate in RELATIONSHIPS.get(other, RelationshipContractStub()).exclusive
                for other in names
                if other != a.predicate
            )
            if mutually_exclusive:
                a.status, a.projection_eligible = "contested", False
                a.explanation = "Contested: mutually exclusive assertions exist in the same scope."
    return sorted(result, key=lambda a: a.id)


class RelationshipContractStub:
    exclusive = frozenset()


LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"provisional", "accepted", "contested", "rejected", "retired"}),
    "provisional": frozenset({"accepted", "contested", "rejected", "stale", "retired"}),
    "accepted": frozenset({"contested", "superseded", "stale", "retired"}),
    "contested": frozenset({"provisional", "accepted", "rejected", "superseded", "retired"}),
    "rejected": frozenset({"proposed", "retired"}),
    "superseded": frozenset({"retired"}),
    "stale": frozenset({"provisional", "accepted", "contested", "superseded", "retired"}),
    "retired": frozenset(),
}


def transition_status(current: str, target: str, *, actor: str) -> None:
    if target not in LEGAL_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"illegal assertion transition: {current} -> {target}")
    if target == "accepted" and actor not in {"resolver", "human"}:
        raise ValueError("only deterministic resolver policy or a human may accept an assertion")


async def persist_resolution(
    proposals: list[RelationshipProposal], *, pool=None, reviews=None, human_confirmed=None
) -> list[CanonicalAssertion]:
    """Idempotently persist proposal events and resolved assertions; rebuild projection."""
    if pool is None:
        from core.engine.core.db import pool as pool
    # One process may receive many Cognify/API completions concurrently. Replay
    # and projection are a single critical section so an earlier, smaller event
    # snapshot cannot overwrite a later resolution. Stable event IDs still make
    # the database writes idempotent; multi-process deployments must place this
    # service behind one assertion-writer worker until a distributed CAS lands.
    async with _PERSIST_LOCK:
        async with pool.connection() as db:
            for p in proposals:
                await _query_or_raise(
                    db,
                    "UPSERT $id CONTENT $content",
                    {"id": parse_record_id(p.event_id()), "content": p.model_dump(mode="json")},
                )
            # Replay is the correctness path: authoritative state is recomputed from
            # the persisted event set, never patched according to arrival order.
            persisted = parse_rows(await db.query("SELECT * FROM relationship_proposal"))
            replay_proposals = [RelationshipProposal.model_validate(row) for row in persisted]
            resolved = resolve_proposals(replay_proposals, reviews=reviews, human_confirmed=human_confirmed)
            for a in resolved:
                content = a.model_dump(mode="json")
                content.pop("id", None)  # record id is supplied by the UPSERT target
                content["updated_at"] = datetime.now(timezone.utc)
                await _query_or_raise(
                    db, "UPSERT $id MERGE $content", {"id": parse_record_id(a.id), "content": content}
                )
            await rebuild_projection(db=db)
    return resolved


async def rebuild_projection(*, pool=None, db=None) -> int:
    """Rebuild only ACE-owned materialized edges from eligible assertions."""
    if db is None:
        if pool is None:
            from core.engine.core.db import pool as pool
        async with pool.connection() as conn:
            return await rebuild_projection(db=conn)
    assertions = parse_rows(
        await db.query("SELECT * FROM relationship_assertion WHERE projection_eligible = true AND status = 'accepted'")
    )
    wanted = {str(a["id"]): a for a in assertions}
    existing = parse_rows(await db.query("SELECT id, assertion_id FROM operational_relationship"))
    for edge in existing:
        if str(edge.get("assertion_id")) not in wanted:
            await db.query("DELETE $id", {"id": edge["id"]})
    for aid, a in sorted(wanted.items()):
        eid = _stable_id("operational_relationship", {"assertion_id": aid, "projection_version": RESOLVER_VERSION})
        await db.query(
            "UPSERT $id SET in = $in, out = $out, predicate = $predicate, assertion_id = $assertion, ontology_version = $ontology, resolver_version = $resolver, projection_version = $resolver, projected_at = time::now()",
            {
                "id": parse_record_id(eid),
                "in": parse_record_id(str(a["subject"])),
                "out": parse_record_id(str(a["object"])),
                "predicate": a["predicate"],
                "assertion": parse_record_id(aid),
                "ontology": ONTOLOGY_VERSION,
                "resolver": RESOLVER_VERSION,
            },
        )
    return len(wanted)


async def persist_review(review: AssertionReview, *, pool=None) -> str:
    """Persist critic output as evidence only; operational state is untouched."""
    if pool is None:
        from core.engine.core.db import pool as pool
    review_id = review.review_id()
    content = review.model_dump(mode="json")
    content["target_assertion"] = parse_record_id(review.target_assertion)
    async with pool.connection() as db:
        await db.query("UPSERT $id CONTENT $content", {"id": parse_record_id(review_id), "content": content})
    return review_id


async def link_assertion_dependency(
    source_assertion: str, dependent_assertion: str, *, dependency_type: str = "derives_from", pool=None
) -> None:
    """Idempotently record why a downstream assertion must be reconsidered."""
    if pool is None:
        from core.engine.core.db import pool as pool
    async with pool.connection() as db:
        existing = parse_rows(
            await db.query(
                "SELECT id FROM assertion_dependency WHERE in = $source AND out = $dependent AND dependency_type = $kind LIMIT 1",
                {
                    "source": parse_record_id(source_assertion),
                    "dependent": parse_record_id(dependent_assertion),
                    "kind": dependency_type,
                },
            )
        )
        if not existing:
            await db.query(
                "RELATE $source -> assertion_dependency -> $dependent SET dependency_type = $kind, created_at = time::now()",
                {
                    "source": parse_record_id(source_assertion),
                    "dependent": parse_record_id(dependent_assertion),
                    "kind": dependency_type,
                },
            )


async def inspect_assertion(assertion_id: str, *, pool=None) -> dict | None:
    if pool is None:
        from core.engine.core.db import pool as pool
    async with pool.connection() as db:
        assertion = parse_one(await db.query("SELECT * FROM $id", {"id": parse_record_id(assertion_id)}))
        if not assertion:
            return None
        proposals = parse_rows(
            await db.query(
                "SELECT * FROM relationship_proposal WHERE id IN $ids", {"ids": assertion.get("proposal_ids", [])}
            )
        )
        reviews = parse_rows(
            await db.query(
                "SELECT * FROM assertion_review WHERE target_assertion = $id", {"id": parse_record_id(assertion_id)}
            )
        )
        history = parse_rows(
            await db.query(
                "SELECT * FROM assertion_event WHERE assertion_id = $id ORDER BY created_at",
                {"id": parse_record_id(assertion_id)},
            )
        )
        projection = parse_rows(
            await db.query(
                "SELECT * FROM operational_relationship WHERE assertion_id = $id", {"id": parse_record_id(assertion_id)}
            )
        )
    return serialize_record(
        {
            "assertion": assertion,
            "proposals": proposals,
            "reviews": reviews,
            "history": history,
            "operational_projection": projection,
        }
    )


async def mark_dependents_stale(changed_assertion_id: str, *, reason: str, pool=None) -> list[str]:
    """Bounded truth-maintenance walk from one changed assumption/assertion."""
    if pool is None:
        from core.engine.core.db import pool as pool
    changed = parse_record_id(changed_assertion_id)
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT out AS id FROM assertion_dependency WHERE in = $id",
                {"id": changed},
            )
        )
        affected = sorted({str(row["id"]) for row in rows})
        for aid in affected:
            rec = parse_record_id(aid)
            await db.query(
                "UPDATE $id SET status = 'stale', projection_eligible = false, updated_at = time::now()", {"id": rec}
            )
            event_id = _stable_id(
                "assertion_event",
                {"assertion_id": aid, "event_type": "dependency_stale", "reason": reason, "resolver": RESOLVER_VERSION},
            )
            await db.query(
                "UPSERT $event SET assertion_id = $id, event_type = 'dependency_stale', actor = 'truth-maintenance', rationale = $reason, to_status = 'stale', created_at = time::now()",
                {"event": parse_record_id(event_id), "id": rec, "reason": reason},
            )
        await rebuild_projection(db=db)
    return affected


async def invalidate_evidence(evidence_id: str, *, reason: str, pool=None) -> list[str]:
    """Contest beliefs using changed evidence, then stale only their dependents."""
    if pool is None:
        from core.engine.core.db import pool as pool
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query("SELECT id FROM relationship_assertion WHERE evidence_refs CONTAINS $e", {"e": evidence_id})
        )
        roots = sorted(str(row["id"]) for row in rows)
        for aid in roots:
            await db.query(
                "UPDATE $id SET status = 'contested', projection_eligible = false, updated_at = time::now()",
                {"id": parse_record_id(aid)},
            )
        await rebuild_projection(db=db)
    affected: set[str] = set()
    for root in roots:
        affected.update(await mark_dependents_stale(root, reason=reason, pool=pool))
    return roots + sorted(affected)
