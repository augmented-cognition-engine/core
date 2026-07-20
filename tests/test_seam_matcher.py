"""Tests for seam route matcher + field comparator."""

from core.engine.seam.matcher import match_and_compare, normalize_route
from core.engine.seam.types import FieldShape, SeamContract, SeamExpectation

# --- normalize_route ---


def test_normalize_simple():
    assert normalize_route("/graph/overview") == "graph/overview"


def test_normalize_strips_query():
    assert normalize_route("/items?org=default") == "items"


def test_normalize_collapses_params():
    assert normalize_route("/graph/explore/{node_id}") == "graph/explore/{}"


def test_normalize_strips_trailing_slash():
    assert normalize_route("/items/") == "items"


# --- match_and_compare ---


def test_matching_fields_no_errors():
    """Exact field match produces no error gaps."""
    contracts = [
        SeamContract(
            route="/graph/overview",
            method="GET",
            source_file="api/graph.py",
            response_fields=[
                FieldShape(name="nodes"),
                FieldShape(name="edges"),
            ],
        )
    ]
    expectations = [
        SeamExpectation(
            route="/graph/overview",
            method="GET",
            consumer_file="pages/Graph.tsx",
            expected_fields=[
                FieldShape(name="nodes"),
                FieldShape(name="edges"),
            ],
        )
    ]
    gaps = match_and_compare(contracts, expectations)
    assert len(gaps) == 0


def test_missing_field_is_error():
    """Frontend expects fields the backend doesn't provide -> errors."""
    contracts = [
        SeamContract(
            route="/graph/edges",
            method="GET",
            source_file="api/graph.py",
            response_fields=[
                FieldShape(name="in"),
                FieldShape(name="out"),
            ],
        )
    ]
    expectations = [
        SeamExpectation(
            route="/graph/edges",
            method="GET",
            consumer_file="pages/Graph.tsx",
            expected_fields=[
                FieldShape(name="from"),
                FieldShape(name="to"),
            ],
        )
    ]
    gaps = match_and_compare(contracts, expectations)
    errors = [g for g in gaps if g.severity == "error"]
    assert len(errors) == 2
    assert all(g.gap_type == "missing_field" for g in errors)
    error_details = {g.detail for g in errors}
    assert any("'from'" in d for d in error_details)
    assert any("'to'" in d for d in error_details)


def test_extra_field_is_warning():
    """Backend returns a field the frontend doesn't use -> warning."""
    contracts = [
        SeamContract(
            route="/items",
            method="GET",
            source_file="api/items.py",
            response_fields=[
                FieldShape(name="id"),
                FieldShape(name="name"),
                FieldShape(name="debug_info"),
            ],
        )
    ]
    expectations = [
        SeamExpectation(
            route="/items",
            method="GET",
            consumer_file="pages/Items.tsx",
            expected_fields=[
                FieldShape(name="id"),
                FieldShape(name="name"),
            ],
        )
    ]
    gaps = match_and_compare(contracts, expectations)
    warnings = [g for g in gaps if g.severity == "warning"]
    assert len(warnings) == 1
    assert warnings[0].gap_type == "extra_field"
    assert "'debug_info'" in warnings[0].detail


def test_unmatched_frontend_route():
    """No backend match for a frontend expectation -> info gap."""
    contracts = []
    expectations = [
        SeamExpectation(
            route="/dashboard/stats",
            method="GET",
            consumer_file="pages/Dashboard.tsx",
        )
    ]
    gaps = match_and_compare(contracts, expectations)
    assert len(gaps) == 1
    assert gaps[0].severity == "info"
    assert gaps[0].gap_type == "unmatched_route"
    assert gaps[0].frontend_file == "pages/Dashboard.tsx"


def test_parameterized_route_matching():
    """Routes with different param names match after normalization."""
    contracts = [
        SeamContract(
            route="/items/{item_id}",
            method="GET",
            source_file="api/items.py",
            response_fields=[
                FieldShape(name="id"),
                FieldShape(name="title"),
            ],
        )
    ]
    expectations = [
        SeamExpectation(
            route="/items/{id}",
            method="GET",
            consumer_file="pages/ItemDetail.tsx",
            expected_fields=[
                FieldShape(name="id"),
                FieldShape(name="title"),
            ],
        )
    ]
    gaps = match_and_compare(contracts, expectations)
    assert len(gaps) == 0


def test_empty_backend_fields_skips_comparison():
    """When backend has no extracted fields, skip comparison to avoid false positives."""
    contracts = [
        SeamContract(
            route="/graph/overview",
            method="GET",
            source_file="api/graph.py",
            response_fields=[],  # empty — extractor couldn't determine fields
        )
    ]
    expectations = [
        SeamExpectation(
            route="/graph/overview",
            method="GET",
            consumer_file="pages/Graph.tsx",
            expected_fields=[
                FieldShape(name="nodes"),
                FieldShape(name="edges"),
            ],
        )
    ]
    gaps = match_and_compare(contracts, expectations)
    assert len(gaps) == 0
