"""Contract tests for the shared bounded impact projection and its two adapters."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from core.engine.code_intelligence.impact import (
    IMPACT_BASE_UNCERTAINTIES,
    IMPACT_MAX_CAPABILITIES,
    IMPACT_MAX_COCHANGE_PARTNERS,
    IMPACT_MAX_FUNCTIONS,
    IMPACT_MAX_IMPORTERS,
    IMPACT_MAX_PATH_CHARS,
    IMPACT_MAX_REF_CHARS,
    IMPACT_MAX_UNCERTAINTY_ITEM_CHARS,
    BoundedObservationWindowV1Alpha1,
    CodeImpactObservationV1Alpha1,
    ImpactSelectorRejected,
    ObservedDefinedFunctionV1Alpha1,
    ObservedImporterV1Alpha1,
    capability_query,
    cochange_query,
    function_query,
    impact_payload,
    importer_query,
    merge_cochange_directions,
    observed_evidence_summary,
    observed_uncertainties,
    project_code_impact,
    validate_impact_selector,
)

pytestmark = pytest.mark.unit


def _project(**overrides):
    kwargs = {
        "graph_id": "default",
        "product_ref": "product:platform",
        "target_path": "engine/core/db.py",
        "target_node_id": "graph_file:engine_core_db_py",
    }
    kwargs.update(overrides)
    return project_code_impact(**kwargs)


# ---------------------------------------------------------------------------
# Deterministic observed evidence summaries
# ---------------------------------------------------------------------------


def test_zero_importers_is_reported_as_absence_of_observation_not_as_safety():
    observation = _project(cochange_observed=False)

    assert observation.summary == (
        "NO DIRECT STATIC IMPORTERS OBSERVED: 0 file(s) import this, 0 function(s) defined, "
        "co-change partners not observed; deletion safety not assessed"
    )
    assert observation.safe_to_delete is False
    assert observation.deletion_safety == "not_assessed"
    assert "SAFE" not in observation.summary
    assert "BREAKING" not in observation.summary


def test_nonzero_importers_is_reported_as_observation_not_as_breakage():
    observation = _project(
        importer_rows=[{"id": "graph_file:a", "path": "a.py"}, {"id": "graph_file:b", "path": "b.py"}],
        function_rows=[{"id": "graph_function:f", "name": "f"}],
        cochange_observed=False,
    )

    assert observation.summary == (
        "IMPACT OBSERVED: 2 file(s) import this, 1 function(s) defined, "
        "co-change partners not observed; deletion safety not assessed"
    )
    assert observation.breakage_assessed is False
    assert observation.fragility_assessed is False


def test_cochange_is_counted_when_observed_and_named_absent_when_not():
    observed = _project(cochange_rows=[{"id": "graph_file:peer", "path": "peer.py"}], cochange_observed=True)
    unobserved = _project(cochange_observed=False)

    assert "1 co-change partner(s)" in observed.summary
    assert observed.evidence_basis == "direct_static_importers_and_cochange"
    assert "co-change partners not observed" in unobserved.summary
    assert unobserved.evidence_basis == "direct_static_importers"

    # Co-change is a correlation on the graph, and the row says so.
    assert observed.cochange_partners[0].establishes_dependency is False
    assert observed.cochange_partners[0].establishes_causation is False


def test_summary_helper_discloses_truncated_collections():
    rendered = observed_evidence_summary(
        importer_count=3,
        function_count=0,
        cochange_observed=True,
        cochange_count=0,
        truncated_collections=("functions", "importers"),
    )

    assert "bounded traversal truncated in: functions, importers" in rendered
    assert rendered.endswith("deletion safety not assessed")


# ---------------------------------------------------------------------------
# Bounded queries
# ---------------------------------------------------------------------------


def test_every_query_stops_one_row_past_its_declared_bound():
    assert f"LIMIT {IMPACT_MAX_IMPORTERS + 1}" in importer_query("graph_file:x")
    assert f"LIMIT {IMPACT_MAX_FUNCTIONS + 1}" in function_query("graph_file:x")
    assert f"LIMIT {IMPACT_MAX_COCHANGE_PARTNERS + 1}" in cochange_query("graph_file:x", "out")
    assert f"LIMIT {IMPACT_MAX_COCHANGE_PARTNERS + 1}" in cochange_query("graph_file:x", "in")
    assert f"LIMIT {IMPACT_MAX_CAPABILITIES + 1}" in capability_query()


def test_capability_query_binds_the_product_rather_than_interpolating_it():
    query = capability_query()

    assert "$product" in query and "$path" in query
    assert "product:" not in query


def test_cochange_query_directions_are_distinct_traversals():
    assert "->related_to->graph_file" in cochange_query("graph_file:x", "out")
    assert "<-related_to<-graph_file" in cochange_query("graph_file:x", "in")


# ---------------------------------------------------------------------------
# Dedupe, order, trim, disclose
# ---------------------------------------------------------------------------


def test_rows_are_deduped_and_ordered_deterministically():
    shuffled = [
        {"id": "graph_file:c", "path": "c.py"},
        {"id": "graph_file:a", "path": "a.py"},
        {"id": "graph_file:c", "path": "c.py"},
        {"id": "graph_file:b", "path": "b.py"},
    ]

    observation = _project(importer_rows=shuffled, cochange_observed=False)

    assert [row.path for row in observation.importers] == ["a.py", "b.py", "c.py"]
    window = next(w for w in observation.windows if w.collection == "importers")
    assert window.fetched == 4
    assert window.returned == 3
    assert window.truncated is False
    assert window.undisclosed_remainder is None


def test_hitting_the_window_trims_and_discloses_an_unknown_remainder():
    overflowing = [
        {"id": f"graph_file:i{index:04d}", "path": f"i{index:04d}.py"} for index in range(IMPACT_MAX_IMPORTERS + 1)
    ]

    observation = _project(importer_rows=overflowing, cochange_observed=False)

    assert observation.importer_count == IMPACT_MAX_IMPORTERS
    window = next(w for w in observation.windows if w.collection == "importers")
    assert window.truncated is True
    assert window.undisclosed_remainder == "unknown"
    assert observation.truncated_collections == ("importers",)
    assert any("remainder is unknown and uncounted" in item for item in observation.uncertainties)


def test_cochange_union_is_rebounded_across_both_directions():
    both_directions = [
        {"id": f"graph_file:p{index:04d}", "path": f"p{index:04d}.py"}
        for index in range(IMPACT_MAX_COCHANGE_PARTNERS + 1)
    ]

    observation = _project(cochange_rows=both_directions, cochange_observed=True)

    assert observation.cochange_partner_count == IMPACT_MAX_COCHANGE_PARTNERS
    assert observation.truncated_collections == ("cochange_partners",)


# ---------------------------------------------------------------------------
# Co-change direction merge — a known overflow survives deduplication
# ---------------------------------------------------------------------------


def _merged_window(out_rows, in_rows):
    merged = merge_cochange_directions(out_rows, in_rows)
    observation = _project(cochange_rows=merged, cochange_observed=True)
    return merged, next(w for w in observation.windows if w.collection == "cochange_partners"), observation


def test_a_direction_that_hit_its_bound_stays_truncated_after_deduplication():
    """51 rows naming one partner is still a direction whose edge set continues past the window."""
    duplicate_heavy = [{"id": "graph_file:peer", "path": "peer.py"}] * (IMPACT_MAX_COCHANGE_PARTNERS + 1)

    merged, window, observation = _merged_window(duplicate_heavy, [])

    # The union carries the exact bound+1 sentinel, which is the only evidence
    # the central window contract accepts that a window was hit.
    assert len(merged) == IMPACT_MAX_COCHANGE_PARTNERS + 1
    assert window.fetched == IMPACT_MAX_COCHANGE_PARTNERS + 1
    assert window.truncated is True
    assert window.undisclosed_remainder == "unknown"
    # ...and the sentinel never becomes an extra partner.
    assert window.returned == 1
    assert observation.cochange_partner_count == 1
    assert observation.truncated_collections == ("cochange_partners",)


def test_cross_direction_duplicates_do_not_collapse_a_known_overflow():
    """Both directions returning the same files is not evidence that neither overflowed."""
    shared = [
        {"id": f"graph_file:p{index:04d}", "path": f"p{index:04d}.py"}
        for index in range(IMPACT_MAX_COCHANGE_PARTNERS + 1)
    ]

    merged, window, observation = _merged_window(shared, list(shared))

    assert len(merged) == IMPACT_MAX_COCHANGE_PARTNERS + 1
    assert window.truncated is True
    assert window.undisclosed_remainder == "unknown"
    assert observation.cochange_partner_count == IMPACT_MAX_COCHANGE_PARTNERS


def test_a_direction_overflow_survives_a_union_that_dedupes_back_under_the_bound():
    """A partly duplicate-heavy direction plus a shared partner still discloses the hit window."""
    unique = [{"id": f"graph_file:p{index:04d}", "path": f"p{index:04d}.py"} for index in range(40)]
    # 51 fetched rows, 40 distinct partners: the direction hit its own bound.
    out_rows = unique + [dict(unique[0]) for _ in range(IMPACT_MAX_COCHANGE_PARTNERS + 1 - len(unique))]
    in_rows = [dict(unique[3])]

    merged, window, observation = _merged_window(out_rows, in_rows)

    assert len(out_rows) == IMPACT_MAX_COCHANGE_PARTNERS + 1
    assert len(merged) == IMPACT_MAX_COCHANGE_PARTNERS + 1
    assert window.truncated is True
    assert observation.cochange_partner_count == 40
    assert any("remainder is unknown and uncounted" in item for item in observation.uncertainties)


def test_two_directions_under_their_bounds_are_merged_without_a_false_overflow():
    out_rows = [{"id": "graph_file:a", "path": "a.py"}, {"id": "graph_file:b", "path": "b.py"}]
    in_rows = [{"id": "graph_file:b", "path": "b.py"}, {"id": "graph_file:c", "path": "c.py"}]

    merged, window, observation = _merged_window(out_rows, in_rows)

    assert [row["id"] for row in merged] == ["graph_file:a", "graph_file:b", "graph_file:c"]
    assert window.truncated is False
    assert window.undisclosed_remainder is None
    assert observation.cochange_partner_count == 3


def test_a_union_that_overflows_only_together_is_truncated():
    """Neither direction hit its own bound, but the merged partner set does."""
    half = IMPACT_MAX_COCHANGE_PARTNERS // 2 + 1
    out_rows = [{"id": f"graph_file:o{index:04d}", "path": f"o{index:04d}.py"} for index in range(half)]
    in_rows = [{"id": f"graph_file:i{index:04d}", "path": f"i{index:04d}.py"} for index in range(half)]

    merged, window, observation = _merged_window(out_rows, in_rows)

    assert len(out_rows) <= IMPACT_MAX_COCHANGE_PARTNERS
    assert len(in_rows) <= IMPACT_MAX_COCHANGE_PARTNERS
    assert len(merged) == IMPACT_MAX_COCHANGE_PARTNERS + 1
    assert window.truncated is True
    assert observation.cochange_partner_count == IMPACT_MAX_COCHANGE_PARTNERS


def test_unidentifiable_rows_are_dropped_and_counted_rather_than_guessed():
    observation = _project(
        importer_rows=[{"language": "python"}, "not-a-row", {"id": "graph_file:a", "path": "a.py"}],
        cochange_observed=False,
    )

    window = next(w for w in observation.windows if w.collection == "importers")
    assert observation.importer_count == 1
    assert window.unidentifiable_rows_dropped == 2


def test_unobserved_collection_carries_no_material_and_no_truncation():
    observation = _project(cochange_observed=False)

    window = next(w for w in observation.windows if w.collection == "cochange_partners")
    assert window.observed is False
    assert (window.fetched, window.returned, window.truncated) == (0, 0, False)
    assert window.undisclosed_remainder is None


# ---------------------------------------------------------------------------
# Caller-supplied selectors are admitted, not coerced
# ---------------------------------------------------------------------------


def test_a_selector_is_admitted_within_the_central_bound():
    assert validate_impact_selector("engine/core/db.py", field="file_path", limit=IMPACT_MAX_PATH_CHARS) == (
        "engine/core/db.py"
    )
    assert validate_impact_selector("", field="product", limit=IMPACT_MAX_REF_CHARS, allow_empty=True) == ""


@pytest.mark.parametrize("value", [7, 1.5, True, False, None, ["a"], {"a": 1}, ("a",), b"a"])
def test_a_non_string_selector_is_refused_rather_than_coerced(value):
    with pytest.raises(ImpactSelectorRejected, match="must be a string"):
        validate_impact_selector(value, field="file_path", limit=IMPACT_MAX_PATH_CHARS)


def test_an_overlong_selector_is_refused_rather_than_truncated():
    overlong = "a" * (IMPACT_MAX_REF_CHARS + 1)

    with pytest.raises(ImpactSelectorRejected) as excinfo:
        validate_impact_selector(overlong, field="product_id", limit=IMPACT_MAX_REF_CHARS)

    message = str(excinfo.value)
    assert message == f"product_id must be at most {IMPACT_MAX_REF_CHARS} characters"
    # Bounded and non-echoing: no part of the rejected value is reflected back.
    assert overlong[:64] not in message


def test_an_empty_selector_is_refused_unless_emptiness_is_meaningful():
    with pytest.raises(ImpactSelectorRejected, match="must not be empty"):
        validate_impact_selector("", field="graph_id", limit=IMPACT_MAX_REF_CHARS)


# ---------------------------------------------------------------------------
# Malformed and oversized models are rejected
# ---------------------------------------------------------------------------


def test_a_window_cannot_return_more_than_its_bound():
    with pytest.raises(ValidationError):
        BoundedObservationWindowV1Alpha1(
            collection="importers",
            observed=True,
            bound=10,
            fetched=20,
            returned=11,
            truncated=True,
            undisclosed_remainder="unknown",
        )


def test_a_window_cannot_fetch_more_than_one_past_its_bound():
    with pytest.raises(ValidationError):
        BoundedObservationWindowV1Alpha1(
            collection="importers",
            observed=True,
            bound=10,
            fetched=12,
            returned=10,
            truncated=True,
            undisclosed_remainder="unknown",
        )


def test_a_truncated_window_must_disclose_its_unknown_remainder():
    with pytest.raises(ValidationError):
        BoundedObservationWindowV1Alpha1(
            collection="importers", observed=True, bound=10, fetched=11, returned=10, truncated=True
        )


def test_an_unobserved_window_cannot_carry_observed_material():
    with pytest.raises(ValidationError):
        BoundedObservationWindowV1Alpha1(
            collection="cochange_partners", observed=False, bound=10, fetched=3, returned=3, truncated=False
        )


def test_an_unnameable_row_is_rejected():
    with pytest.raises(ValidationError):
        ObservedImporterV1Alpha1(language="python")
    with pytest.raises(ValidationError):
        ObservedDefinedFunctionV1Alpha1(kind="function")


def test_a_reversed_function_span_is_rejected():
    with pytest.raises(ValidationError):
        ObservedDefinedFunctionV1Alpha1(name="f", line_start=30, line_end=20)


def test_an_oversized_observation_is_rejected():
    valid = _project(cochange_observed=False)
    payload = valid.model_dump(mode="json")

    payload["uncertainties"] = ["x" * (IMPACT_MAX_UNCERTAINTY_ITEM_CHARS + 1)]
    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(payload)

    payload["uncertainties"] = ["item"] * 9
    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(payload)


def test_an_observation_cannot_claim_authority_or_deletion_safety():
    valid = _project(cochange_observed=False)
    payload = valid.model_dump(mode="json")

    for field, value in (
        ("safe_to_delete", True),
        ("deletion_safety", "safe"),
        ("change_authority", True),
        ("effect_authority", True),
        ("breakage_assessed", True),
    ):
        mutated = dict(payload, **{field: value})
        with pytest.raises(ValidationError):
            CodeImpactObservationV1Alpha1.model_validate(mutated)


def test_an_observation_cannot_report_an_absent_revision_as_a_real_one():
    payload = _project(cochange_observed=False).model_dump(mode="json")

    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(dict(payload, graph_revision="git:abc"))
    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(dict(payload, graph_freshness="2026-08-15T00:00:00Z"))


def test_an_observation_must_restate_its_own_counts_and_truncation_exactly():
    """The summary is derived on every load, so a reassembled body cannot narrate a different observation."""
    observation = _project(
        importer_rows=[{"id": "graph_file:a", "path": "a.py"}],
        function_rows=[{"id": "graph_function:f", "name": "f"}],
        cochange_observed=False,
    )
    payload = observation.model_dump(mode="json")

    # The exact derived summary round-trips.
    assert CodeImpactObservationV1Alpha1.model_validate(payload).summary == observation.summary

    for substituted in (
        # Inflated and deflated counts.
        "IMPACT OBSERVED: 9 file(s) import this, 1 function(s) defined, "
        "co-change partners not observed; deletion safety not assessed",
        "IMPACT OBSERVED: 1 file(s) import this, 0 function(s) defined, "
        "co-change partners not observed; deletion safety not assessed",
        # A co-change count this observation never observed.
        "IMPACT OBSERVED: 1 file(s) import this, 1 function(s) defined, "
        "0 co-change partner(s); deletion safety not assessed",
        # A truncation that no window declares.
        "IMPACT OBSERVED: 1 file(s) import this, 1 function(s) defined, co-change partners not observed, "
        "bounded traversal truncated in: importers; deletion safety not assessed",
        # Verdicts in place of the observation.
        "SAFE TO DELETE: 1 file(s) import this, 1 function(s) defined, "
        "co-change partners not observed; deletion safety not assessed",
        "BREAKING CHANGE: 1 file(s) import this, 1 function(s) defined, "
        "co-change partners not observed; deletion safety not assessed",
        # The refusal clause quietly dropped.
        "IMPACT OBSERVED: 1 file(s) import this, 1 function(s) defined, co-change partners not observed",
    ):
        with pytest.raises(ValidationError):
            CodeImpactObservationV1Alpha1.model_validate(dict(payload, summary=substituted))


def test_a_truncated_observation_must_disclose_that_truncation_in_its_summary():
    overflowing = [
        {"id": f"graph_file:i{index:04d}", "path": f"i{index:04d}.py"} for index in range(IMPACT_MAX_IMPORTERS + 1)
    ]
    truncated = _project(importer_rows=overflowing, cochange_observed=False)
    payload = truncated.model_dump(mode="json")

    assert "bounded traversal truncated in: importers" in truncated.summary
    assert CodeImpactObservationV1Alpha1.model_validate(payload).summary == truncated.summary

    # The truncation clause cannot be dropped from either the summary or the
    # uncertainties while the window still declares the window was hit.
    undisclosed = truncated.summary.replace(", bounded traversal truncated in: importers", "")
    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(dict(payload, summary=undisclosed))
    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(dict(payload, uncertainties=payload["uncertainties"][:3]))


def test_uncertainties_are_derived_and_cannot_be_replaced_or_softened():
    payload = _project(cochange_observed=False).model_dump(mode="json")

    # One helper renders the exact tuple; the projection and the contract's own
    # validator both derive from it, so neither can drift from the other.
    assert observed_uncertainties() == IMPACT_BASE_UNCERTAINTIES
    assert observed_uncertainties(("importers",))[:3] == IMPACT_BASE_UNCERTAINTIES
    assert len(observed_uncertainties(("importers",))) == 4
    assert tuple(payload["uncertainties"]) == IMPACT_BASE_UNCERTAINTIES
    assert CodeImpactObservationV1Alpha1.model_validate(payload).uncertainties == IMPACT_BASE_UNCERTAINTIES

    for substituted in (
        # An arbitrary replacement, however plausible.
        ["This observation is complete."],
        # A softened base entry.
        [IMPACT_BASE_UNCERTAINTIES[0], IMPACT_BASE_UNCERTAINTIES[1], "Graph revision and freshness are current."],
        # A dropped base entry.
        list(IMPACT_BASE_UNCERTAINTIES[:2]),
        # A reordered base tuple.
        list(reversed(IMPACT_BASE_UNCERTAINTIES)),
        # A truncation uncertainty no window supports.
        [
            *IMPACT_BASE_UNCERTAINTIES,
            "Bounded traversal stopped at the declared per-collection limit for importers; "
            "the remainder is unknown and uncounted.",
        ],
    ):
        with pytest.raises(ValidationError):
            CodeImpactObservationV1Alpha1.model_validate(dict(payload, uncertainties=substituted))


def test_a_window_cannot_claim_a_collection_was_never_observed():
    """Only co-change may go unobserved, and only by naming an importer-only basis."""
    payload = _project(cochange_observed=False).model_dump(mode="json")

    for collection in ("importers", "functions", "capabilities"):
        mutated = {
            key: (dict(value, observed=False) if key == collection else value)
            for key, value in ((w["collection"], w) for w in payload["windows"])
        }
        with pytest.raises(ValidationError):
            CodeImpactObservationV1Alpha1.model_validate(dict(payload, windows=list(mutated.values())))


def test_an_unobserved_cochange_window_cannot_sit_under_a_cochange_evidence_basis():
    payload = _project(cochange_observed=False).model_dump(mode="json")

    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(
            dict(payload, evidence_basis="direct_static_importers_and_cochange")
        )


def test_an_observation_cannot_relabel_its_revision_or_freshness_as_established():
    payload = _project(cochange_observed=False).model_dump(mode="json")

    for field, value in (
        ("graph_revision_established", True),
        ("graph_freshness_established", True),
        ("graph_revision", "current"),
        ("graph_freshness", "current"),
    ):
        with pytest.raises(ValidationError):
            CodeImpactObservationV1Alpha1.model_validate(dict(payload, **{field: value}))


def test_importer_only_evidence_cannot_carry_cochange_material():
    payload = _project(cochange_rows=[{"id": "graph_file:peer", "path": "peer.py"}], cochange_observed=True).model_dump(
        mode="json"
    )

    with pytest.raises(ValidationError):
        CodeImpactObservationV1Alpha1.model_validate(dict(payload, evidence_basis="direct_static_importers"))


def test_the_payload_names_its_graph_product_target_and_evidence():
    payload = impact_payload(_project(cochange_observed=False))

    assert payload["graph_id"] == "default"
    assert payload["product_ref"] == "product:platform"
    assert payload["target_path"] == "engine/core/db.py"
    assert payload["target_node_id"] == "graph_file:engine_core_db_py"
    assert payload["observation_id"].startswith("code_impact_observation:")
    assert payload["evidence_id"].startswith("code_impact_evidence:")
    assert set(payload["observation_windows"]) == {
        "importers",
        "functions",
        "cochange_partners",
        "capabilities",
    }
    assert payload["uncertainties"][0].startswith("Dynamic imports, runtime dispatch, reflection, generated code")
    assert "consumers outside this repository" in payload["uncertainties"][0]


def test_the_evidence_identifier_tracks_the_observed_rows():
    empty = _project(cochange_observed=False)
    loaded = _project(importer_rows=[{"id": "graph_file:a", "path": "a.py"}], cochange_observed=False)

    assert empty.evidence_id != loaded.evidence_id
    assert (
        loaded.evidence_id
        == _project(importer_rows=[{"id": "graph_file:a", "path": "a.py"}], cochange_observed=False).evidence_id
    )


# ---------------------------------------------------------------------------
# REST / internal MCP semantic parity
# ---------------------------------------------------------------------------

_FILE_NODE = {"id": "graph_file:engine_core_db_py", "path": "core/engine/core/db.py"}
_IMPORTERS = [{"id": "graph_file:caller", "path": "caller.py", "name": "caller", "language": "python"}]
_FUNCTIONS = [{"id": "graph_function:f", "name": "f", "kind": "function", "line_start": 1, "line_end": 4}]
_CAPABILITIES = [{"slug": "graph-tools", "name": "Graph Tools", "status": "live"}]


def _pool(side_effects):
    db = AsyncMock()
    db.query = AsyncMock(side_effect=side_effects)
    pool = MagicMock()

    @asynccontextmanager
    async def _conn():
        yield db

    pool.connection = _conn
    return pool


async def _rest_payload():
    from core.engine.api.graph_traverse import impact_by_path

    # The REST adapter resolves the graph↔product mapping first, then reads.
    pool = _pool([[{"graph_id": "default"}], [_FILE_NODE], _IMPORTERS, _FUNCTIONS, [], [], _CAPABILITIES])
    with patch("core.engine.api.graph_traverse.pool", pool):
        return await impact_by_path(
            "core/engine/core/db.py",
            graph_id="default",
            product="",
            user={"sub": "user:test", "product": "product:platform"},
        )


async def _mcp_payload():
    from core.engine.mcp.tools import ace_impact

    pool = MagicMock()
    conn = AsyncMock()
    conn.query = AsyncMock(side_effect=[[_FILE_NODE], _IMPORTERS, _FUNCTIONS, _CAPABILITIES])
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("core.engine.mcp.tools.pool", pool):
        return await ace_impact("core/engine/core/db.py", product_id="product:platform")


@pytest.mark.asyncio
async def test_rest_and_internal_mcp_make_the_same_calibrated_claims():
    """The same observed material yields the same claim on both structured surfaces."""
    rest = await _rest_payload()
    mcp = await _mcp_payload()

    shared = (
        "contract",
        "status",
        "graph_id",
        "product_ref",
        "target_path",
        "target_node_id",
        "graph_revision",
        "graph_revision_established",
        "graph_freshness",
        "graph_freshness_established",
        "importers",
        "importer_count",
        "functions",
        "function_count",
        "capabilities",
        "capability_count",
        "safe_to_delete",
        "deletion_safety",
        "fragility_assessed",
        "breakage_assessed",
        "truncated_collections",
        "source_authority",
        "reasoning_authority",
        "change_authority",
        "approval_authority",
        "delivery_authority",
        "execution_authority",
        "effect_authority",
    )
    for key in shared:
        assert rest[key] == mcp[key], key

    # Both publish the summary under both established keys.
    assert rest["summary"] == rest["impact_summary"]
    assert mcp["summary"] == mcp["impact_summary"]


@pytest.mark.asyncio
async def test_the_only_divergence_between_the_surfaces_is_disclosed_cochange_scope():
    rest = await _rest_payload()
    mcp = await _mcp_payload()

    divergent = {key for key in set(rest) & set(mcp) if rest[key] != mcp[key]}
    assert divergent == {
        # Each surface keeps the `file` value its existing consumers already
        # receive: the serialized start node over REST, the requested path
        # string from the tool.
        "file",
        "impact_evidence_basis",
        "observation_windows",
        "summary",
        "impact_summary",
        "observation_id",
        "evidence_id",
    }

    # ...and the divergence is exactly the co-change scope each adapter fetched.
    assert rest["impact_evidence_basis"] == "direct_static_importers_and_cochange"
    assert mcp["impact_evidence_basis"] == "direct_static_importers"
    assert rest["observation_windows"]["cochange_partners"]["observed"] is True
    assert mcp["observation_windows"]["cochange_partners"]["observed"] is False
    assert "0 co-change partner(s)" in rest["summary"]
    assert "co-change partners not observed" in mcp["summary"]
    assert rest["uncertainties"] == mcp["uncertainties"]
