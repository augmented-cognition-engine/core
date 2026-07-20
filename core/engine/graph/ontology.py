"""Versioned semantic contracts for ACE relationship assertions.

The registry is deliberately code-native and dependency-free.  A relationship
name has exactly one meaning per ontology version; model vocabulary is accepted
only through explicit aliases and inverse aliases.
"""

from __future__ import annotations

from dataclasses import dataclass

ONTOLOGY_VERSION = "ace.relationships.v1"


@dataclass(frozen=True)
class RelationshipContract:
    name: str
    meaning: str
    family: str
    subject_types: frozenset[str]
    object_types: frozenset[str]
    inverse: str | None = None
    symmetric: bool = False
    transitive: bool = False
    aliases: tuple[str, ...] = ()
    inverse_aliases: tuple[str, ...] = ()
    compatible: frozenset[str] = frozenset()
    exclusive: frozenset[str] = frozenset()
    human_confirmation: bool = False
    minimum_evidence: int = 1
    causal: bool = False
    projectable: bool = True
    examples: tuple[str, ...] = ()
    counterexamples: tuple[str, ...] = ()


ANY = frozenset({"*"})
INSIGHT_LIKE = frozenset(
    {
        "insight",
        "graph_insight",
        "decision",
        "graph_decision",
        "requirement",
        "capability",
        "work_item",
        "milestone",
        "initiative",
    }
)

RELATIONSHIPS: dict[str, RelationshipContract] = {
    "depends_on": RelationshipContract(
        "depends_on",
        "The subject requires the object to remain valid or achievable.",
        "dependency",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        inverse="enables",
        inverse_aliases=("enables",),
        compatible=frozenset({"informed_by"}),
        aliases=("requires",),
        examples=("Feature depends_on authentication service",),
        counterexamples=("A merely improves B",),
    ),
    "informed_by": RelationshipContract(
        "informed_by",
        "The object supplied evidence or rationale used by the subject; it is not causation.",
        "provenance",
        INSIGHT_LIKE,
        ANY,
        inverse="informs",
        inverse_aliases=("informs", "supports"),
        compatible=frozenset({"depends_on", "improves", "causes"}),
    ),
    "solves": RelationshipContract(
        "solves",
        "The subject fully resolves the object problem within the assertion scope.",
        "outcome",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        aliases=("resolves_problem",),
        compatible=frozenset({"improves"}),
        human_confirmation=True,
        counterexamples=("Partially mitigates or merely addresses a problem",),
    ),
    "addresses": RelationshipContract(
        "addresses",
        "The subject materially mitigates or responds to the object without claiming full resolution.",
        "outcome",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        aliases=("mitigates",),
        compatible=frozenset({"improves"}),
    ),
    "causes": RelationshipContract(
        "causes",
        "Within the declared context, the subject is asserted to produce the object outcome.",
        "causal",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        aliases=("leads_to",),
        compatible=frozenset({"informed_by"}),
        human_confirmation=True,
        minimum_evidence=2,
        causal=True,
        counterexamples=("Correlation or influence without adequate causal evidence",),
    ),
    "improves": RelationshipContract(
        "improves",
        "The subject increases a declared measure of the object under the assertion context.",
        "effect",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        aliases=("enhances",),
        compatible=frozenset({"addresses", "solves"}),
    ),
    "breaks": RelationshipContract(
        "breaks",
        "The subject makes the object invalid, unavailable, or unable to satisfy its contract in scope.",
        "negative_effect",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        aliases=("invalidates",),
        exclusive=frozenset({"improves"}),
    ),
    "reverts": RelationshipContract(
        "reverts",
        "The subject intentionally restores state that existed before the object change.",
        "change_history",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        aliases=("rolls_back",),
        counterexamples=("A newer decision merely supersedes an older decision",),
    ),
    "supersedes": RelationshipContract(
        "supersedes",
        "The subject replaces the object as the current applicable belief or decision.",
        "change_history",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        inverse="superseded_by",
        inverse_aliases=("superseded_by",),
    ),
    "decomposes": RelationshipContract(
        "decomposes",
        "The subject is explicitly divided into the object as a constituent part.",
        "composition",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        inverse="part_of",
        inverse_aliases=("part_of", "contained_by"),
        aliases=("has_part",),
    ),
    "contradicts": RelationshipContract(
        "contradicts",
        "The subject and object cannot both be true in the same scope and validity interval.",
        "epistemic_conflict",
        INSIGHT_LIKE,
        INSIGHT_LIKE,
        symmetric=True,
        aliases=("conflicts_with",),
        projectable=False,
    ),
}


def record_type(record_id: str) -> str:
    return record_id.split(":", 1)[0] if ":" in record_id else ""


def normalize_predicate(label: str) -> tuple[str, bool] | None:
    """Return ``(canonical_name, swap_endpoints)`` for a declared label."""
    candidate = label.strip().lower().replace("-", "_").replace(" ", "_")
    if candidate in RELATIONSHIPS:
        return candidate, False
    for name, contract in RELATIONSHIPS.items():
        if candidate in contract.aliases:
            return name, False
        if candidate in contract.inverse_aliases:
            return name, True
    return None


def type_allowed(allowed: frozenset[str], record_id: str) -> bool:
    return "*" in allowed or record_type(record_id) in allowed
