"""Domain-neutral derivation-family closure and independence predicate.

This module answers one question about already-admitted material: *which
Observations trace back to the same origin?* It is pure — no I/O, no clock, no
persistence, no provider call — and it operates only on an exact resource
closure the caller already holds (in practice, the frozen Case context).

How a family root is derived
----------------------------
A family is **derived**, never declared. ACE walks each Observation's admitted
lineage upward through Observation-kind edges whose relation collapses
(:data:`COLLAPSING_RELATIONS`) and takes the terminal ancestor as the family
root. The family identity is that root Observation's exact ``resource_id``.

This makes repetition, syndication, quotation, and simple derivative chains
collapse to the origin they came from: a syndicated copy that declares
``derived_from`` the report it copied resolves to the report's root, and so adds
no independence to anything the report asserts.

What is deliberately NOT independence
-------------------------------------
* **Publisher count.** Two Observations carrying different ``source_ref``
  values that share a derivation root are one family. Distinct publishers do
  not manufacture independence.
* **Textual variation.** Payload content is never inspected. A reworded
  syndication is exactly as dependent as a verbatim one.
* **Acquisition path.** ``acquisition_mode`` and receipt references are not
  consulted; re-acquiring the same origin twice is still one family.

Only declared derivation structure collapses, and only admitted structure
counts. An Observation that declares no collapsing parent is its own root.

Fail-closed conditions
----------------------
Every one of these raises :class:`DerivationFamilyError` rather than degrading
to a weaker answer:

* a collapsing lineage edge naming a resource outside the exact closure,
* a collapsing lineage edge whose digest, ``as_of``, or availability disagrees
  with the admitted resource it names,
* a collapsing lineage edge naming a resource that is not an Observation,
* a cycle anywhere in the collapsing graph,
* an ambiguous root: an Observation whose collapsing parents resolve to more
  than one distinct root,
* a support identity that is not an Observation in the closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ace.intelligence.contracts.ledger import resource_reference
from ace.intelligence.contracts.resources import (
    LineageRelation,
    LineageResourceKind,
    ObservationV1Alpha1,
)

#: Lineage relations that mean "this record came from that record". Only these
#: collapse a child into its parent's family. ``SUPPORTS``, ``CONTRADICTS``, and
#: ``CONTEXT`` deliberately do not: a record that merely supports or contradicts
#: another is not derived from it and may be genuinely independent.
COLLAPSING_RELATIONS = frozenset(
    {
        LineageRelation.DERIVED_FROM,
        LineageRelation.SUPERSEDES,
    }
)

#: Stable name of the rule this module implements, disclosed in durable
#: projections so an auditor can tell exactly which predicate produced a result.
DERIVATION_FAMILY_POLICY = "observation_lineage_root_closure/v1alpha1"


class DerivationFamilyError(ValueError):
    """Derivation-family closure or the independence predicate failed closed."""


@dataclass(frozen=True, slots=True)
class DerivationFamilyClosure:
    """Exact family assignment for every Observation in one admitted closure."""

    root_by_record_id: Mapping[str, str]
    members_by_root: Mapping[str, tuple[str, ...]]

    def root_of(self, record_id: str) -> str:
        """Return the exact family root of one Observation, or fail closed."""

        root = self.root_by_record_id.get(record_id)
        if root is None:
            raise DerivationFamilyError(f"{record_id} is not an exact admitted Observation in this closure")
        return root


def _collapsing_parents(observation: ObservationV1Alpha1) -> tuple[str, ...]:
    parents = tuple(
        edge.resource_id
        for edge in observation.lineage
        if edge.relation in COLLAPSING_RELATIONS and edge.resource_kind is LineageResourceKind.OBSERVATION
    )
    if len(parents) != len(set(parents)):
        raise DerivationFamilyError(f"{observation.resource_id} declares a duplicate collapsing lineage edge")
    return parents


def _assert_edges_bind_exact_material(
    observation: ObservationV1Alpha1,
    *,
    by_id: dict[str, object],
) -> None:
    """Reject a collapsing edge that names missing, changed, or non-Observation material."""

    for edge in observation.lineage:
        if edge.relation not in COLLAPSING_RELATIONS:
            continue
        if edge.resource_kind is not LineageResourceKind.OBSERVATION:
            # A non-Observation collapsing parent cannot carry a family root.
            raise DerivationFamilyError(
                f"{observation.resource_id} collapses into a non-Observation resource {edge.resource_id}"
            )
        parent = by_id.get(edge.resource_id)
        if parent is None:
            raise DerivationFamilyError(
                f"{observation.resource_id} names collapsing parent {edge.resource_id} "
                "outside the exact admitted closure"
            )
        reference = resource_reference(parent)
        if (
            edge.resource_digest != reference.resource_digest
            or edge.resource_as_of != reference.as_of
            or edge.resource_available_at != reference.available_at
        ):
            raise DerivationFamilyError(
                f"{observation.resource_id} collapsing edge to {edge.resource_id} crossed exact admitted material"
            )


def derive_observation_families(*, closure: tuple) -> DerivationFamilyClosure:
    """Assign every Observation in an exact closure to one derived family root."""

    observations: dict[str, ObservationV1Alpha1] = {}
    for item in closure:
        if isinstance(item, ObservationV1Alpha1):
            identity = str(item.resource_id)
            if identity in observations:
                raise DerivationFamilyError(f"closure contains duplicate Observation identity {identity}")
            observations[identity] = item
    if not observations:
        raise DerivationFamilyError("derivation-family closure requires at least one Observation")

    by_id: dict[str, object] = dict(observations)
    for observation in observations.values():
        _assert_edges_bind_exact_material(observation, by_id=by_id)

    root_by_record_id: dict[str, str] = {}
    visiting: set[str] = set()

    def resolve(identity: str) -> str:
        cached = root_by_record_id.get(identity)
        if cached is not None:
            return cached
        if identity in visiting:
            raise DerivationFamilyError(f"derivation lineage contains a cycle through {identity}")
        visiting.add(identity)
        parents = _collapsing_parents(observations[identity])
        if not parents:
            root = identity
        else:
            roots = {resolve(parent) for parent in parents}
            if len(roots) != 1:
                raise DerivationFamilyError(f"{identity} has an ambiguous derivation root: {sorted(roots)}")
            root = next(iter(roots))
        visiting.discard(identity)
        root_by_record_id[identity] = root
        return root

    for identity in sorted(observations):
        resolve(identity)

    members: dict[str, list[str]] = {}
    for identity in sorted(root_by_record_id):
        members.setdefault(root_by_record_id[identity], []).append(identity)
    return DerivationFamilyClosure(
        root_by_record_id=dict(sorted(root_by_record_id.items())),
        members_by_root={root: tuple(value) for root, value in sorted(members.items())},
    )


def independent_family_roots(
    *,
    support_record_ids: tuple[str, ...],
    families: DerivationFamilyClosure,
) -> tuple[str, ...]:
    """Return the exact distinct family roots behind one claim's supports."""

    if not support_record_ids:
        raise DerivationFamilyError("independence requires at least one exact support")
    return tuple(sorted({families.root_of(item) for item in support_record_ids}))


__all__ = [
    "COLLAPSING_RELATIONS",
    "DERIVATION_FAMILY_POLICY",
    "DerivationFamilyClosure",
    "DerivationFamilyError",
    "derive_observation_families",
    "independent_family_roots",
]
