"""Pure, domain-neutral supersession-impact traversal.

Given one admitted superseding record and one exact authorized closure, this
module enumerates every resource in that closure whose admitted lineage reaches
the superseded target, directly or transitively. It performs no I/O, no clock
read, no persistence, and no provider call.

Direction
---------
Lineage points *backwards*: a resource records which records it used. Impact
flows *forwards*: a superseded record reaches everything that used it. The walk
therefore builds a reverse index over the closure. That is also why the
superseder itself may legitimately sit **outside** the closure — a correction
usually arrives after the work it affects — while its target must sit inside it.

Dependency, not falsehood
-------------------------
Being in scope means "your grounding included a record that has since been
superseded". It does not mean the statement is wrong. ACE cannot judge that, and
never pretends to: the result carries the exact path and relation that put each
resource in scope, plus the exact set it found unaffected, so a reader sees the
boundary instead of inferring one.

Fail-closed conditions
----------------------
* the named target is absent from the closure,
* the superseder declares no ``supersedes`` edge to the named target (wrong
  direction, or no supersession at all),
* the declared edge's digest, ``as_of``, or availability disagrees with the
  admitted target,
* the supersession would predate the record it supersedes,
* a closure resource became available after the cutoff (future leakage),
* the closure contains duplicate resource identities,
* the superseder is the target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ace.intelligence.contracts.ledger import resource_reference
from ace.intelligence.contracts.resources import LineageRelation, LineageResourceKind

#: Stable name of the rule this module implements, disclosed durably so an
#: auditor can tell exactly which traversal produced a result.
SUPERSESSION_IMPACT_POLICY = "lineage_dependency_closure/v1alpha1"

#: Every lineage relation expresses "this resource used that one", so every one
#: of them propagates impact. The relation that carried each step is recorded so
#: a consumer can weigh a ``derived_from`` dependency differently from a
#: ``contradicts`` one without ACE having to guess on its behalf.
IMPACT_RELATIONS = frozenset(LineageRelation)

#: The relation that asserts supersession, and the only one accepted as a cause.
SUPERSEDING_RELATION = LineageRelation.SUPERSEDES


class SupersessionImpactError(ValueError):
    """Supersession-impact projection failed closed."""


@dataclass(frozen=True, slots=True)
class ImpactedResource:
    """One downstream resource and the exact edge that put it in scope."""

    resource_id: str
    resource_kind: LineageResourceKind
    resource_digest: str
    depth: int
    via_resource_id: str
    via_relation: LineageRelation


@dataclass(frozen=True, slots=True)
class SupersessionImpact:
    """The complete, ordered result of one impact traversal."""

    superseder_resource_id: str
    superseded_resource_id: str
    impacted: tuple[ImpactedResource, ...]
    unaffected_resource_ids: tuple[str, ...]
    closure_resource_ids: tuple[str, ...]

    @property
    def direct(self) -> tuple[ImpactedResource, ...]:
        return tuple(item for item in self.impacted if item.depth == 1)

    @property
    def transitive(self) -> tuple[ImpactedResource, ...]:
        return tuple(item for item in self.impacted if item.depth > 1)


def _index(closure: tuple) -> dict[str, object]:
    by_id: dict[str, object] = {}
    for item in closure:
        identity = str(item.resource_id)
        if identity in by_id:
            raise SupersessionImpactError(f"closure contains duplicate resource identity {identity}")
        by_id[identity] = item
    if not by_id:
        raise SupersessionImpactError("supersession impact requires a non-empty closure")
    return by_id


def _assert_supersedes(
    superseder,
    *,
    superseded_resource_id: str,
    target,
) -> None:
    """Require an exact, correctly directed supersession edge on the superseder."""

    edges = tuple(
        edge
        for edge in superseder.lineage
        if edge.relation is SUPERSEDING_RELATION and edge.resource_id == superseded_resource_id
    )
    if not edges:
        declared = tuple(edge.resource_id for edge in superseder.lineage if edge.relation is SUPERSEDING_RELATION)
        if declared:
            raise SupersessionImpactError(
                f"{superseder.resource_id} supersedes {sorted(declared)}, not {superseded_resource_id}"
            )
        raise SupersessionImpactError(
            f"{superseder.resource_id} declares no supersedes edge; a supersession must be "
            "asserted by the superseding record, not inferred"
        )
    if len(edges) != 1:
        raise SupersessionImpactError(
            f"{superseder.resource_id} declares an ambiguous supersession of {superseded_resource_id}"
        )
    edge = edges[0]
    reference = resource_reference(target)
    if (
        edge.resource_digest != reference.resource_digest
        or edge.resource_as_of != reference.as_of
        or edge.resource_available_at != reference.available_at
    ):
        raise SupersessionImpactError("the supersedes edge crossed the exact admitted material it names")
    if edge.resource_kind is not LineageResourceKind(reference.resource_kind.value):
        raise SupersessionImpactError("the supersedes edge crossed the target resource kind")


def project_supersession_impact(
    *,
    superseder,
    superseded_resource_id: str,
    closure: tuple,
    cutoff_at: datetime,
) -> SupersessionImpact:
    """Enumerate everything in the closure that depended on the superseded record."""

    by_id = _index(closure)
    superseder_id = str(superseder.resource_id)
    if superseder_id == superseded_resource_id:
        raise SupersessionImpactError("a record cannot supersede itself")
    target = by_id.get(superseded_resource_id)
    if target is None:
        raise SupersessionImpactError(f"superseded record {superseded_resource_id} is absent from the exact closure")
    _assert_supersedes(
        superseder,
        superseded_resource_id=superseded_resource_id,
        target=target,
    )
    superseder_reference = resource_reference(superseder)
    target_reference = resource_reference(target)
    if superseder_reference.as_of < target_reference.as_of:
        raise SupersessionImpactError("a supersession cannot semantically precede the record it supersedes")
    for identity, item in by_id.items():
        if resource_reference(item).available_at > cutoff_at:
            raise SupersessionImpactError(
                f"{identity} became available after the projection cutoff; the closure must not "
                "leak resources from the future"
            )

    # Reverse index: for each closure resource, the exact edges it declares.
    impacted: dict[str, ImpactedResource] = {}
    frontier: list[tuple[str, int]] = [(superseded_resource_id, 0)]
    while frontier:
        current_id, current_depth = frontier.pop(0)
        for identity in sorted(by_id):
            if identity in impacted or identity in {superseded_resource_id, superseder_id}:
                continue
            candidate = by_id[identity]
            edges = tuple(
                edge
                for edge in candidate.lineage
                if edge.resource_id == current_id and edge.relation in IMPACT_RELATIONS
            )
            if not edges:
                continue
            # Deterministic reason when a resource depends on the same record
            # through more than one relation.
            edge = sorted(edges, key=lambda item: item.relation.value)[0]
            reference = resource_reference(candidate)
            impacted[identity] = ImpactedResource(
                resource_id=identity,
                resource_kind=LineageResourceKind(reference.resource_kind.value),
                resource_digest=reference.resource_digest,
                depth=current_depth + 1,
                via_resource_id=current_id,
                via_relation=edge.relation,
            )
            frontier.append((identity, current_depth + 1))

    ordered = tuple(sorted(impacted.values(), key=lambda item: (item.depth, item.resource_id)))
    unaffected = tuple(sorted(set(by_id) - set(impacted) - {superseded_resource_id}))
    return SupersessionImpact(
        superseder_resource_id=superseder_id,
        superseded_resource_id=superseded_resource_id,
        impacted=ordered,
        unaffected_resource_ids=unaffected,
        closure_resource_ids=tuple(sorted(by_id)),
    )


def project_claim_impact(
    *,
    impact: SupersessionImpact,
    brief_id: str,
    claim_supports: tuple,
) -> tuple[tuple[str, tuple[str, ...], int, bool], ...]:
    """Map one Brief's claim support bindings onto an impact result.

    Returns ``(claim_id, impacted_support_ids, total_supports, fully_impacted)``
    for every claim with at least one impacted support. A claim whose grounding
    never touches the superseded record is simply absent, so the caller cannot
    accidentally report impact where lineage does not support it.
    """

    reachable = {item.resource_id for item in impact.impacted} | {impact.superseded_resource_id}
    results = []
    for support in claim_supports:
        touched = tuple(sorted(set(support.support_record_ids) & reachable))
        if not touched:
            continue
        total = len(support.support_record_ids)
        results.append((str(support.claim_id), touched, total, len(touched) == total))
    if not brief_id.startswith("brief:"):
        raise SupersessionImpactError("claim impact requires one exact Brief identity")
    return tuple(sorted(results, key=lambda item: item[0]))


__all__ = [
    "IMPACT_RELATIONS",
    "SUPERSEDING_RELATION",
    "SUPERSESSION_IMPACT_POLICY",
    "ImpactedResource",
    "SupersessionImpact",
    "SupersessionImpactError",
    "project_claim_impact",
    "project_supersession_impact",
]
