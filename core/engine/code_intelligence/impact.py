"""Bounded, calibrated static impact observation shared by both structured adapters.

Two surfaces answer the same question from the same code graph: the REST
``/graph/impact-by-path`` endpoint and the internal
``core.engine.mcp.tools.ace_impact`` tool.  They authenticate differently and
they legitimately fetch differently — the REST endpoint binds a product from a
verified principal and also reads co-change edges, the internal tool does
neither — so the *fetch* stays with each adapter.  What must never diverge is
the *contract*: what an observation is permitted to claim, how much of the
graph it is permitted to materialize, and how the omitted remainder is
disclosed.  That lives here.

Nothing in this module establishes deletion safety.  A static import edge is
observed evidence about one graph revision, not a proof about the running
program: dynamic imports, runtime dispatch, reflection, generated code, and
consumers outside this repository are all invisible to it.  ``safe_to_delete``
is therefore a fixed ``False`` and ``deletion_safety`` a fixed
``"not_assessed"`` — they are retained as established response keys, not as
answers.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from core.engine.code_intelligence.contracts import (
    ConfidenceBand,
    DerivationKind,
    FrozenContract,
    stable_id,
)

# ---------------------------------------------------------------------------
# Conservative per-collection bounds
# ---------------------------------------------------------------------------
# Every collection an impact observation can carry has an explicit finite bound
# below, and every adapter query is written with ``LIMIT bound + 1``.  The extra
# row is never returned; it exists so a hit against the window is *detected*
# rather than inferred, which is what makes the truncation disclosure exact.
# These are deliberately small.  A hub file in a large repository has thousands
# of importers, and neither serializing thousands of database rows into a tool
# response nor rendering them into an agent's context is useful work.

IMPACT_MAX_IMPORTERS = 100
IMPACT_MAX_FUNCTIONS = 100
# Co-change is the union of the outgoing and incoming ``related_to`` edges, so
# each direction is fetched with this same bound and the union is re-bounded.
IMPACT_MAX_COCHANGE_PARTNERS = 50
IMPACT_MAX_CAPABILITIES = 25

# The target path is caller-supplied and is echoed into identifiers, summaries,
# and query parameters, so it is length-bounded before any of that happens.
IMPACT_MAX_PATH_CHARS = 4_096
IMPACT_MAX_REF_CHARS = 512

# Bounds on the rendered uncertainty tuple, held independent of how many
# collections truncated, so an observation can never expand into an unbounded
# text payload.
IMPACT_MAX_UNCERTAINTY_ITEMS = 8
IMPACT_MAX_UNCERTAINTY_ITEM_CHARS = 600
IMPACT_MAX_UNCERTAINTY_TOTAL_CHARS = 3_000

IMPACT_COLLECTION_BOUNDS: dict[str, int] = {
    "importers": IMPACT_MAX_IMPORTERS,
    "functions": IMPACT_MAX_FUNCTIONS,
    "cochange_partners": IMPACT_MAX_COCHANGE_PARTNERS,
    "capabilities": IMPACT_MAX_CAPABILITIES,
}

ImpactCollection = Literal["importers", "functions", "cochange_partners", "capabilities"]

# ``direct_static_importers`` is what an adapter that reads only ``imports``
# edges observed; ``direct_static_importers_and_cochange`` additionally read
# ``related_to`` edges.  The basis is part of the claim, so it is named rather
# than assumed.
ImpactEvidenceBasis = Literal["direct_static_importers", "direct_static_importers_and_cochange"]

UNESTABLISHED = "unestablished"

IMPACT_BASE_UNCERTAINTIES: tuple[str, ...] = (
    "Dynamic imports, runtime dispatch, reflection, generated code, and consumers outside this repository "
    "are not resolved by static import edges.",
    "Observed import and co-change edges do not grant source, reasoning, change, approval, delivery, "
    "execution, or effect authority.",
    "Graph revision and index freshness are unestablished, so this observation may lag the working tree.",
)


def _bounded_uncertainties(uncertainties: tuple[str, ...]) -> tuple[str, ...]:
    if not uncertainties:
        raise ValueError("an impact observation must retain uncertainty")
    if len(uncertainties) > IMPACT_MAX_UNCERTAINTY_ITEMS:
        raise ValueError(f"uncertainties exceed {IMPACT_MAX_UNCERTAINTY_ITEMS} items")
    if any(len(item) > IMPACT_MAX_UNCERTAINTY_ITEM_CHARS for item in uncertainties):
        raise ValueError(f"uncertainty entries exceed {IMPACT_MAX_UNCERTAINTY_ITEM_CHARS} characters")
    if sum(len(item) for item in uncertainties) > IMPACT_MAX_UNCERTAINTY_TOTAL_CHARS:
        raise ValueError(f"uncertainties exceed {IMPACT_MAX_UNCERTAINTY_TOTAL_CHARS} total characters")
    return uncertainties


def observed_uncertainties(truncated_collections: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Render the exact uncertainty tuple one observation is permitted to carry.

    The base tuple is unconditional — it is what static import edges cannot see,
    what the observation does not authorize, and the fact that the graph
    revision is unestablished.  Exactly one further entry is admissible, and
    only when a bounded window was actually hit; it names the truncated
    collections and refuses to guess the remainder.  Both the projection and the
    contract's own validator derive from here, so a deserialized observation
    cannot substitute a softer or an invented uncertainty for the real one.
    """

    if not truncated_collections:
        return IMPACT_BASE_UNCERTAINTIES
    return IMPACT_BASE_UNCERTAINTIES + (
        "Bounded traversal stopped at the declared per-collection limit for "
        f"{', '.join(truncated_collections)}; the remainder is unknown and uncounted.",
    )


# ---------------------------------------------------------------------------
# Caller-supplied selectors, admitted before anything is read
# ---------------------------------------------------------------------------


class ImpactSelectorRejected(ValueError):
    """One caller-supplied impact selector is not admissible.

    Raised *before* any database connection is opened, so an unusable selector
    never reaches a query, a connection pool, or a log line. The message names
    the field and the bound it violated and never echoes the value back: the
    caller already knows what it sent, and reflecting an arbitrary-length or
    arbitrary-content value into an error string, a tool response, or a server
    log is how a rejected input becomes an injection or a disclosure surface.
    """


def validate_impact_selector(value: Any, *, field: str, limit: int, allow_empty: bool = False) -> str:
    """Admit one selector as an exactly-bounded string, or refuse it outright.

    A non-string — an int, a list, a dict, ``None``, a bool — is a type
    confusion, not a value to coerce: ``str()`` on a list would happily produce
    a query parameter no caller intended. An overlong value is refused rather
    than trimmed, because silently truncating caller material would substitute
    a different target for the one that was asked about and then answer
    confidently about it.
    """

    if isinstance(value, bool) or not isinstance(value, str):
        raise ImpactSelectorRejected(f"{field} must be a string")
    if not value and not allow_empty:
        raise ImpactSelectorRejected(f"{field} must not be empty")
    if len(value) > limit:
        raise ImpactSelectorRejected(f"{field} must be at most {limit} characters")
    return value


# ---------------------------------------------------------------------------
# Bounded observation window
# ---------------------------------------------------------------------------


class BoundedObservationWindowV1Alpha1(FrozenContract):
    """Exactly how much of one collection was looked at, and what was omitted."""

    contract: Literal["ace.code-intelligence.impact-observation-window/v1alpha1"] = (
        "ace.code-intelligence.impact-observation-window/v1alpha1"
    )
    collection: ImpactCollection
    observed: bool
    bound: int = Field(ge=1)
    fetched: int = Field(ge=0)
    returned: int = Field(ge=0)
    truncated: bool
    # Present only when the window was hit.  The exact remainder is unknown
    # because the query deliberately stopped one row past the bound instead of
    # counting the whole edge set.
    undisclosed_remainder: Literal["unknown"] | None = None
    unidentifiable_rows_dropped: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def window_is_exact(self) -> Self:
        if not self.observed:
            if self.fetched or self.returned or self.truncated or self.unidentifiable_rows_dropped:
                raise ValueError(f"{self.collection} was not observed but carries observed material")
            if self.undisclosed_remainder is not None:
                raise ValueError(f"{self.collection} was not observed but discloses a remainder")
            return self
        if self.returned > self.bound:
            raise ValueError(f"{self.collection} returned more rows than its bound of {self.bound}")
        if self.returned > self.fetched:
            raise ValueError(f"{self.collection} returned more rows than it fetched")
        # The adapter's query is always `LIMIT bound + 1`, so a fetch can never
        # report more than one row past the bound, and truncation can only ever
        # be true because that exact sentinel row was hit — never because a
        # window merely claims it. A zero-row fetch is bound - 0, which is never
        # greater than the bound, so it falls out of the same inequality rather
        # than needing its own case.
        if self.fetched > self.bound + 1:
            raise ValueError(f"{self.collection} fetched more rows than one past its bound of {self.bound}")
        if self.truncated != (self.fetched > self.bound):
            raise ValueError(f"{self.collection} truncation disagrees with its fetched count against the bound")
        if self.truncated != (self.undisclosed_remainder == "unknown"):
            raise ValueError(f"{self.collection} truncation and disclosed remainder disagree")
        return self


# ---------------------------------------------------------------------------
# Structured rows
# ---------------------------------------------------------------------------


class ObservedImporterV1Alpha1(FrozenContract):
    """One file observed to statically import the target.

    ``path``, ``name``, and ``language`` are the established compatibility
    columns both legacy surfaces already returned; ``node_id`` names the graph
    record the row came from so the claim is traceable.
    """

    contract: Literal["ace.code-intelligence.observed-importer/v1alpha1"] = (
        "ace.code-intelligence.observed-importer/v1alpha1"
    )
    path: str | None = Field(default=None, max_length=IMPACT_MAX_PATH_CHARS)
    name: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    language: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    node_id: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    edge: Literal["imports"] = "imports"
    derivation: Literal[DerivationKind.GRAPH] = DerivationKind.GRAPH
    confidence: Literal[ConfidenceBand.OBSERVED] = ConfidenceBand.OBSERVED
    establishes_breakage: Literal[False] = False

    @model_validator(mode="after")
    def row_is_nameable(self) -> Self:
        if not (self.path or self.node_id):
            raise ValueError("an observed importer must carry a path or a node id")
        return self


class ObservedDefinedFunctionV1Alpha1(FrozenContract):
    """One function the target file is observed to define."""

    contract: Literal["ace.code-intelligence.observed-defined-function/v1alpha1"] = (
        "ace.code-intelligence.observed-defined-function/v1alpha1"
    )
    name: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    kind: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    node_id: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    derivation: Literal[DerivationKind.GRAPH] = DerivationKind.GRAPH
    confidence: Literal[ConfidenceBand.OBSERVED] = ConfidenceBand.OBSERVED
    establishes_breakage: Literal[False] = False

    @model_validator(mode="after")
    def row_is_nameable_and_ordered(self) -> Self:
        if not (self.name or self.node_id):
            raise ValueError("an observed defined function must carry a name or a node id")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("observed defined function line span is reversed")
        return self


class ObservedCochangePartnerV1Alpha1(FrozenContract):
    """One file observed to change alongside the target.

    Co-change is a correlation recorded on the graph.  It is not a dependency
    and it is not causation, which is why it carries its own refusal flag.
    """

    contract: Literal["ace.code-intelligence.observed-cochange-partner/v1alpha1"] = (
        "ace.code-intelligence.observed-cochange-partner/v1alpha1"
    )
    path: str | None = Field(default=None, max_length=IMPACT_MAX_PATH_CHARS)
    name: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    node_id: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    edge: Literal["related_to"] = "related_to"
    derivation: Literal[DerivationKind.GRAPH] = DerivationKind.GRAPH
    confidence: Literal[ConfidenceBand.OBSERVED] = ConfidenceBand.OBSERVED
    establishes_dependency: Literal[False] = False
    establishes_causation: Literal[False] = False

    @model_validator(mode="after")
    def row_is_nameable(self) -> Self:
        if not (self.path or self.node_id):
            raise ValueError("an observed co-change partner must carry a path or a node id")
        return self


class ObservedCapabilityV1Alpha1(FrozenContract):
    """One product capability whose declared reality lists the target path."""

    contract: Literal["ace.code-intelligence.observed-capability/v1alpha1"] = (
        "ace.code-intelligence.observed-capability/v1alpha1"
    )
    slug: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    name: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    status: str | None = Field(default=None, max_length=IMPACT_MAX_REF_CHARS)
    product_ref: str = Field(min_length=1, max_length=IMPACT_MAX_REF_CHARS)
    derivation: Literal[DerivationKind.DECLARED] = DerivationKind.DECLARED
    confidence: Literal[ConfidenceBand.OBSERVED] = ConfidenceBand.OBSERVED
    establishes_breakage: Literal[False] = False

    @model_validator(mode="after")
    def row_is_nameable(self) -> Self:
        if not (self.slug or self.name):
            raise ValueError("an observed capability must carry a slug or a name")
        return self


# ---------------------------------------------------------------------------
# The observation
# ---------------------------------------------------------------------------


class CodeImpactObservationV1Alpha1(FrozenContract):
    """One bounded, product-scoped static impact observation over the code graph."""

    contract: Literal["ace.code-intelligence.impact-observation/v1alpha1"] = (
        "ace.code-intelligence.impact-observation/v1alpha1"
    )
    status: Literal["observed"] = "observed"
    graph_id: str = Field(min_length=1, max_length=IMPACT_MAX_REF_CHARS)
    product_ref: str = Field(min_length=1, max_length=IMPACT_MAX_REF_CHARS)
    target_path: str = Field(min_length=1, max_length=IMPACT_MAX_PATH_CHARS)
    target_node_id: str = Field(min_length=1, max_length=IMPACT_MAX_REF_CHARS)
    evidence_basis: ImpactEvidenceBasis

    # Freshness is a claim like any other.  Neither adapter can currently read a
    # graph revision or an index timestamp, so both are pinned to the literal
    # ``"unestablished"`` and their paired flags are pinned to ``False`` — not
    # merely defaulted to those values, but typed so that no construction path,
    # tampered ``model_dump``, or future adapter change can relabel a graph
    # revision or freshness as established without a deliberate contract change
    # here first.
    graph_revision: Literal[UNESTABLISHED] = UNESTABLISHED
    graph_revision_established: Literal[False] = False
    graph_freshness: Literal[UNESTABLISHED] = UNESTABLISHED
    graph_freshness_established: Literal[False] = False

    importers: tuple[ObservedImporterV1Alpha1, ...] = ()
    functions: tuple[ObservedDefinedFunctionV1Alpha1, ...] = ()
    cochange_partners: tuple[ObservedCochangePartnerV1Alpha1, ...] = ()
    capabilities: tuple[ObservedCapabilityV1Alpha1, ...] = ()
    windows: tuple[BoundedObservationWindowV1Alpha1, ...]

    summary: str = Field(min_length=1, max_length=IMPACT_MAX_UNCERTAINTY_ITEM_CHARS)
    uncertainties: tuple[str, ...]

    safe_to_delete: Literal[False] = False
    deletion_safety: Literal["not_assessed"] = "not_assessed"
    fragility_assessed: Literal[False] = False
    breakage_assessed: Literal[False] = False

    source_authority: Literal[False] = False
    reasoning_authority: Literal[False] = False
    change_authority: Literal[False] = False
    approval_authority: Literal[False] = False
    delivery_authority: Literal[False] = False
    execution_authority: Literal[False] = False
    effect_authority: Literal[False] = False

    @model_validator(mode="after")
    def observation_is_bounded_and_consistent(self) -> Self:
        _bounded_uncertainties(self.uncertainties)

        if not self.graph_revision_established and self.graph_revision != UNESTABLISHED:
            raise ValueError("an unestablished graph revision must be reported as unestablished")
        if not self.graph_freshness_established and self.graph_freshness != UNESTABLISHED:
            raise ValueError("an unestablished graph freshness must be reported as unestablished")

        by_collection = {window.collection: window for window in self.windows}
        if len(by_collection) != len(self.windows):
            raise ValueError("impact observation repeats an observation window")
        if set(by_collection) != set(IMPACT_COLLECTION_BOUNDS):
            raise ValueError("impact observation must carry one window per bounded collection")

        materialized: dict[str, tuple[Any, ...]] = {
            "importers": self.importers,
            "functions": self.functions,
            "cochange_partners": self.cochange_partners,
            "capabilities": self.capabilities,
        }
        for collection, rows in materialized.items():
            window = by_collection[collection]
            bound = IMPACT_COLLECTION_BOUNDS[collection]
            if window.bound != bound:
                raise ValueError(f"{collection} window declares a bound other than {bound}")
            if len(rows) > bound:
                raise ValueError(f"{collection} exceeds its bound of {bound}")
            if len(rows) != window.returned:
                raise ValueError(f"{collection} rows disagree with the declared window")

        # Co-change is the one collection an adapter may legitimately decline to
        # read, and it must then say so and carry nothing. The other three are
        # always read by both adapters, so a window claiming one of them was
        # never observed is a false disclosure, not a narrower observation.
        for collection in ("importers", "functions", "capabilities"):
            if not by_collection[collection].observed:
                raise ValueError(f"{collection} must be observed by any impact observation")
        if self.evidence_basis == "direct_static_importers":
            if self.cochange_partners or by_collection["cochange_partners"].observed:
                raise ValueError("importer-only evidence cannot carry co-change material")
        elif not by_collection["cochange_partners"].observed:
            raise ValueError("co-change evidence basis requires an observed co-change window")

        # The rendered claim is derived, never carried. Both the summary
        # sentence and the uncertainty tuple are recomputed here from the
        # material this observation actually holds and the windows it actually
        # declares, so a payload that is reassembled — by a tampered
        # ``model_dump``, a hand-written body, or a future adapter — cannot
        # narrate counts, a co-change scope, or a truncation that its own rows
        # and windows do not support.
        truncated = self.truncated_collections
        expected_summary = observed_evidence_summary(
            importer_count=len(self.importers),
            function_count=len(self.functions),
            cochange_observed=by_collection["cochange_partners"].observed,
            cochange_count=len(self.cochange_partners),
            truncated_collections=truncated,
        )
        if self.summary != expected_summary:
            raise ValueError("impact summary does not restate the observed material exactly")
        if self.uncertainties != observed_uncertainties(truncated):
            raise ValueError("impact uncertainties do not restate the observation's exact limits")
        return self

    @property
    def observation_id(self) -> str:
        return stable_id("code_impact_observation", self)

    @property
    def evidence_id(self) -> str:
        return stable_id(
            "code_impact_evidence",
            {
                "graph_id": self.graph_id,
                "product_ref": self.product_ref,
                "target_node_id": self.target_node_id,
                "evidence_basis": self.evidence_basis,
                "importers": [row.model_dump(mode="json") for row in self.importers],
                "functions": [row.model_dump(mode="json") for row in self.functions],
                "cochange_partners": [row.model_dump(mode="json") for row in self.cochange_partners],
                "capabilities": [row.model_dump(mode="json") for row in self.capabilities],
            },
        )

    @property
    def importer_count(self) -> int:
        return len(self.importers)

    @property
    def function_count(self) -> int:
        return len(self.functions)

    @property
    def cochange_partner_count(self) -> int:
        return len(self.cochange_partners)

    @property
    def capability_count(self) -> int:
        return len(self.capabilities)

    @property
    def truncated_collections(self) -> tuple[str, ...]:
        return tuple(sorted(window.collection for window in self.windows if window.truncated))


# ---------------------------------------------------------------------------
# Bounded queries — written once so both adapters share the same window
# ---------------------------------------------------------------------------


def importer_query(target_node_id: str) -> str:
    """Files that statically import the target, bounded at one row past the cap.

    Ordered by ``id`` so the bound+1 window is deterministic: an adapter that
    defensively re-trims this result gets the same rows cut, call to call.
    """
    return (
        f"SELECT id, path, name, language FROM ({target_node_id})<-imports<-graph_file "
        f"WHERE graph_id = $gid ORDER BY id LIMIT {IMPACT_MAX_IMPORTERS + 1}"
    )


def function_query(target_node_id: str) -> str:
    """Functions the target defines, bounded at one row past the cap.

    Ordered by ``id`` for the same reason as ``importer_query``.
    """
    return (
        f"SELECT id, name, kind, line_start, line_end FROM ({target_node_id})->depends_on->graph_function "
        f"WHERE graph_id = $gid ORDER BY id LIMIT {IMPACT_MAX_FUNCTIONS + 1}"
    )


def cochange_query(target_node_id: str, direction: Literal["out", "in"]) -> str:
    """One direction of the co-change relation, bounded at one row past the cap.

    Both directions carry the same bound; the union is re-bounded on projection,
    so a hit on either direction is disclosed as a truncation of the union.
    Ordered by ``id`` for the same reason as ``importer_query``.
    """
    traversal = (
        f"({target_node_id})->related_to->graph_file"
        if direction == "out"
        else f"({target_node_id})<-related_to<-graph_file"
    )
    return (
        f"SELECT id, path, name FROM {traversal} WHERE graph_id = $gid "
        f"ORDER BY id LIMIT {IMPACT_MAX_COCHANGE_PARTNERS + 1}"
    )


def capability_query() -> str:
    """Capabilities whose declared reality lists ``$path`` within ``$product``.

    The product is always bound by the caller — the adapter never interpolates
    it — so this query can never read across a product boundary. Ordered by
    ``slug`` for the same determinism reason as ``importer_query``.
    """
    return (
        "SELECT slug, name, status FROM capability "
        "WHERE reality.files CONTAINS $path AND product = <record>$product "
        f"ORDER BY slug LIMIT {IMPACT_MAX_CAPABILITIES + 1}"
    )


# ---------------------------------------------------------------------------
# Adapter-side defensive bounding — the central projection stays strict
# ---------------------------------------------------------------------------
# ``project_code_impact`` intentionally rejects a collection fetched beyond one
# row past its bound: that strictness is what makes the ``BoundedObservationWindow``
# contract trustworthy against a caller that hands it unbounded material
# directly. Adapters don't get that luxury — they sit in front of a real
# backend (or, in tests, a mock) that can hand back more rows than the
# ``LIMIT bound + 1`` query asked for. The helpers below are where that gap is
# closed: every adapter takes at most one bound+1 window from its own query
# result before the material ever reaches the strict projection.


def bound_fetched_rows(rows: list[dict] | None, collection: ImpactCollection) -> list[dict]:
    """Cap one adapter's raw query result at one row past its declared bound.

    Against a well-behaved backend this is a no-op — the query already carries
    ``LIMIT bound + 1``. It exists for the backend or test double that hands
    back more than that: the adapter boundary is where that gets clamped, not
    the shared contract.
    """
    bound = IMPACT_COLLECTION_BOUNDS[collection]
    return list(rows or [])[: bound + 1]


def _cochange_identity(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    return _text(row, "id") or _text(row, "path", IMPACT_MAX_PATH_CHARS)


def merge_cochange_directions(out_rows: list[dict] | None, in_rows: list[dict] | None) -> list[dict]:
    """Merge both co-change directions into one deterministic, bounded window.

    Each direction is independently bounded at ``LIMIT bound + 1``, so their
    concatenation can be up to twice that — always finite, but too large to
    hand the strict central projection directly. This dedupes by the stable
    partner identity (graph node id, falling back to path), orders the result
    deterministically, and re-bounds the union to one row past the bound.

    If either direction alone hit its own bound, that direction's true edge
    set continues past what was fetched — even if deduping against the other
    direction happens to bring the *visible* union back under the bound. That
    signal must not be lost, so in that case the returned window is padded
    back up to exactly the bound+1 sentinel with duplicates of an
    already-included row. It has to reach bound+1 and not merely one row
    further, because ``fetched > bound`` is the *only* thing the central
    window contract accepts as evidence that a window was hit: 51 rows that
    dedupe to a single partner, or two directions whose rows are largely the
    same files, would otherwise arrive as a short, untruncated-looking window
    and the known overflow would vanish. The duplicates never become extra
    partners: the central projection dedupes by the same identity before
    counting anything, so they only ever restore the "this window was hit"
    disclosure that a plain re-bound would have silently dropped.
    """
    bound = IMPACT_MAX_COCHANGE_PARTNERS
    out_rows = bound_fetched_rows(out_rows, "cochange_partners")
    in_rows = bound_fetched_rows(in_rows, "cochange_partners")
    direction_overflowed = len(out_rows) > bound or len(in_rows) > bound

    seen: set[str] = set()
    merged: list[dict] = []
    for row in sorted(
        out_rows + in_rows, key=lambda row: (_text(row, "path", IMPACT_MAX_PATH_CHARS) or "", _text(row, "id") or "")
    ):
        key = _cochange_identity(row)
        if key is None:
            merged.append(row)
            continue
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)

    union_overflowed = len(merged) > bound
    bounded = merged[: bound + 1]
    if (direction_overflowed or union_overflowed) and bounded and len(bounded) <= bound:
        bounded = bounded + [bounded[-1]] * (bound + 1 - len(bounded))

    return bounded


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def _text(row: dict, key: str, limit: int = IMPACT_MAX_REF_CHARS) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    rendered = str(value)
    return rendered[:limit] or None


def _line(row: dict, key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 1 else None


def _bounded(
    raw_rows: list[dict] | None,
    *,
    collection: ImpactCollection,
    observed: bool,
    identity,
    build,
    order,
) -> tuple[tuple[Any, ...], BoundedObservationWindowV1Alpha1]:
    """Dedupe, order, and trim one fetched collection into its declared window.

    ``raw_rows`` is whatever the adapter's ``LIMIT bound + 1`` query returned.
    Fetching one row past the bound is what lets truncation be *observed*: if
    the adapter came back with more rows than the bound, the edge set continues
    past the window and the remainder is honestly unknown.
    """
    bound = IMPACT_COLLECTION_BOUNDS[collection]
    if not observed:
        return (), BoundedObservationWindowV1Alpha1(
            collection=collection, observed=False, bound=bound, fetched=0, returned=0, truncated=False
        )

    rows = list(raw_rows or [])
    fetched = len(rows)
    truncated = fetched > bound

    seen: set[str] = set()
    built: list[Any] = []
    dropped = 0
    for row in rows:
        if not isinstance(row, dict):
            dropped += 1
            continue
        key = identity(row)
        if not key:
            dropped += 1
            continue
        if key in seen:
            continue
        seen.add(key)
        built.append(build(row))

    built.sort(key=order)
    if len(built) > bound:
        truncated = True
        built = built[:bound]

    return tuple(built), BoundedObservationWindowV1Alpha1(
        collection=collection,
        observed=True,
        bound=bound,
        fetched=fetched,
        returned=len(built),
        truncated=truncated,
        undisclosed_remainder="unknown" if truncated else None,
        unidentifiable_rows_dropped=dropped,
    )


def observed_evidence_summary(
    *,
    importer_count: int,
    function_count: int,
    cochange_observed: bool,
    cochange_count: int,
    truncated_collections: tuple[str, ...] = (),
) -> str:
    """Render the one deterministic sentence both adapters report.

    The lead is the only thing that varies with the evidence: importers were
    observed, or they were not.  Neither branch upgrades to a verdict — a file
    with no observed importers is a file with no observed importers, not a file
    that is safe to delete.
    """
    lead = "IMPACT OBSERVED" if importer_count else "NO DIRECT STATIC IMPORTERS OBSERVED"
    cochange = f"{cochange_count} co-change partner(s)" if cochange_observed else "co-change partners not observed"
    truncation = (
        f", bounded traversal truncated in: {', '.join(truncated_collections)}" if truncated_collections else ""
    )
    return (
        f"{lead}: {importer_count} file(s) import this, "
        f"{function_count} function(s) defined, {cochange}{truncation}; "
        "deletion safety not assessed"
    )


def project_code_impact(
    *,
    graph_id: str,
    product_ref: str,
    target_path: str,
    target_node_id: str,
    importer_rows: list[dict] | None = None,
    function_rows: list[dict] | None = None,
    cochange_rows: list[dict] | None = None,
    capability_rows: list[dict] | None = None,
    cochange_observed: bool = True,
) -> CodeImpactObservationV1Alpha1:
    """Project fetched graph rows into one bounded, calibrated impact observation.

    The adapter owns the fetch; this owns everything that can be claimed about
    it.  Rows are expected to come from the ``LIMIT bound + 1`` queries above —
    an adapter that fetches unbounded rows still cannot produce an unbounded
    observation, because every collection is trimmed to its declared bound here
    and the overflow is disclosed rather than dropped silently.
    """
    importers, importer_window = _bounded(
        importer_rows,
        collection="importers",
        observed=True,
        identity=lambda row: _text(row, "id") or _text(row, "path", IMPACT_MAX_PATH_CHARS) or "",
        build=lambda row: ObservedImporterV1Alpha1(
            path=_text(row, "path", IMPACT_MAX_PATH_CHARS),
            name=_text(row, "name"),
            language=_text(row, "language"),
            node_id=_text(row, "id"),
        ),
        order=lambda row: (row.path or "", row.node_id or ""),
    )
    functions, function_window = _bounded(
        function_rows,
        collection="functions",
        observed=True,
        identity=lambda row: _text(row, "id") or _text(row, "name") or "",
        build=lambda row: ObservedDefinedFunctionV1Alpha1(
            name=_text(row, "name"),
            kind=_text(row, "kind"),
            line_start=_line(row, "line_start"),
            line_end=_line(row, "line_end"),
            node_id=_text(row, "id"),
        ),
        order=lambda row: (row.name or "", -1 if row.line_start is None else row.line_start, row.node_id or ""),
    )
    partners, cochange_window = _bounded(
        cochange_rows,
        collection="cochange_partners",
        observed=cochange_observed,
        identity=lambda row: _text(row, "id") or _text(row, "path", IMPACT_MAX_PATH_CHARS) or "",
        build=lambda row: ObservedCochangePartnerV1Alpha1(
            path=_text(row, "path", IMPACT_MAX_PATH_CHARS),
            name=_text(row, "name"),
            node_id=_text(row, "id"),
        ),
        order=lambda row: (row.path or "", row.node_id or ""),
    )
    capabilities, capability_window = _bounded(
        capability_rows,
        collection="capabilities",
        observed=True,
        identity=lambda row: _text(row, "slug") or _text(row, "name") or "",
        build=lambda row: ObservedCapabilityV1Alpha1(
            slug=_text(row, "slug"),
            name=_text(row, "name"),
            status=_text(row, "status"),
            product_ref=product_ref,
        ),
        order=lambda row: (row.slug or "", row.name or ""),
    )

    windows = (importer_window, function_window, cochange_window, capability_window)
    truncated = tuple(sorted(window.collection for window in windows if window.truncated))

    return CodeImpactObservationV1Alpha1(
        graph_id=graph_id,
        product_ref=product_ref,
        target_path=target_path[:IMPACT_MAX_PATH_CHARS],
        target_node_id=target_node_id,
        evidence_basis="direct_static_importers_and_cochange" if cochange_observed else "direct_static_importers",
        importers=importers,
        functions=functions,
        cochange_partners=partners,
        capabilities=capabilities,
        windows=windows,
        summary=observed_evidence_summary(
            importer_count=len(importers),
            function_count=len(functions),
            cochange_observed=cochange_observed,
            cochange_count=len(partners),
            truncated_collections=truncated,
        ),
        uncertainties=observed_uncertainties(truncated),
    )


def impact_payload(observation: CodeImpactObservationV1Alpha1) -> dict:
    """Render the observation as the additive wire shape both adapters return.

    The established keys both legacy surfaces already published — ``importers``,
    ``importer_count``, ``functions``, ``function_count``, ``cochange_partners``,
    ``capabilities``, ``safe_to_delete``, ``deletion_safety``,
    ``impact_evidence_basis``, ``uncertainties`` — keep their names and their
    meanings.  ``summary`` and ``impact_summary`` are both emitted with the same
    text so neither surface's existing consumers have to change to gain parity.
    """
    return {
        "contract": observation.contract,
        "status": observation.status,
        "observation_id": observation.observation_id,
        "evidence_id": observation.evidence_id,
        "graph_id": observation.graph_id,
        "graph_revision": observation.graph_revision,
        "graph_revision_established": observation.graph_revision_established,
        "graph_freshness": observation.graph_freshness,
        "graph_freshness_established": observation.graph_freshness_established,
        "product_ref": observation.product_ref,
        "target_path": observation.target_path,
        "target_node_id": observation.target_node_id,
        "importers": [row.model_dump(mode="json") for row in observation.importers],
        "importer_count": observation.importer_count,
        "functions": [row.model_dump(mode="json") for row in observation.functions],
        "function_count": observation.function_count,
        "cochange_partners": [row.model_dump(mode="json") for row in observation.cochange_partners],
        "cochange_partner_count": observation.cochange_partner_count,
        "capabilities": [row.model_dump(mode="json") for row in observation.capabilities],
        "capability_count": observation.capability_count,
        "observation_windows": {window.collection: window.model_dump(mode="json") for window in observation.windows},
        "truncated_collections": list(observation.truncated_collections),
        "safe_to_delete": observation.safe_to_delete,
        "deletion_safety": observation.deletion_safety,
        "fragility_assessed": observation.fragility_assessed,
        "breakage_assessed": observation.breakage_assessed,
        "impact_evidence_basis": observation.evidence_basis,
        "uncertainties": list(observation.uncertainties),
        "summary": observation.summary,
        "impact_summary": observation.summary,
        "source_authority": observation.source_authority,
        "reasoning_authority": observation.reasoning_authority,
        "change_authority": observation.change_authority,
        "approval_authority": observation.approval_authority,
        "delivery_authority": observation.delivery_authority,
        "execution_authority": observation.execution_authority,
        "effect_authority": observation.effect_authority,
    }
