# tests/test_mcp_graph_tools.py
"""Tests for MCP graph tools — ace_impact, ace_history, ace_related."""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.code_intelligence.impact import IMPACT_MAX_PATH_CHARS, IMPACT_MAX_REF_CHARS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool_mock(side_effects):
    """Return a pool mock where db.query returns successive side_effects."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=side_effects)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def test_impact_formatter_does_not_turn_unknown_safety_into_safe_or_breaking() -> None:
    from core.engine.mcp.server import _fmt_impact

    rendered = _fmt_impact(
        {
            "safe_to_delete": False,
            "deletion_safety": "not_assessed",
            "impact_evidence_basis": "direct_static_importers",
            "importers": [],
            "uncertainties": ["Dynamic imports are not resolved."],
        },
        "engine/utils/leaf.py",
    )

    assert "NO DIRECT STATIC IMPORTERS OBSERVED" in rendered
    assert "deletion safety was not assessed" in rendered
    assert "No direct static importers observed" in rendered
    assert "Dynamic imports are not resolved" in rendered
    assert "✓ SAFE" not in rendered
    assert "BREAKING" not in rendered


def test_impact_formatter_reports_observed_importers_without_predicting_breakage() -> None:
    from core.engine.mcp.server import _fmt_impact

    rendered = _fmt_impact(
        {
            "safe_to_delete": False,
            "deletion_safety": "not_assessed",
            "importers": ["core/engine/mcp/tools.py"],
        },
        "core/engine/core/db.py",
    )

    assert "IMPACT OBSERVED" in rendered
    assert "Direct static importers observed" in rendered
    assert "BREAKING" not in rendered


def test_impact_formatter_consumes_the_structured_tool_shape() -> None:
    from core.engine.mcp.server import _fmt_impact

    rendered = _fmt_impact(
        {
            "functions": [{"name": "parse_rows", "kind": "function"}],
            "importers": [{"path": "core/engine/mcp/tools.py"}],
            "capabilities": [{"slug": "graph-tools", "name": "Graph Tools"}],
            "uncertainties": ["Runtime dispatch is not resolved."],
        },
        "core/engine/core/db.py",
    )

    assert "1 importers  ·  1 functions  ·  1 capabilities" in rendered
    assert "Capabilities declaring this file: Graph Tools" in rendered
    assert "Runtime dispatch is not resolved" in rendered
    assert "BREAKING" not in rendered
    # The structured rows are rendered by their identifying columns, not as
    # repr'd dictionaries.
    assert "  core/engine/mcp/tools.py" in rendered
    assert "  parse_rows" in rendered
    assert "{'path'" not in rendered


def test_impact_formatter_renders_an_unavailable_observation_as_its_own_outcome() -> None:
    from core.engine.mcp.server import _fmt_impact

    rendered = _fmt_impact({"error": "File 'engine/gone.py' not found in graph"}, "engine/gone.py")

    assert "OBSERVATION UNAVAILABLE" in rendered
    assert "not found in graph" in rendered
    assert "No dependent-graph observation was produced" in rendered
    # An absent node must never be rendered as a file that was looked at and
    # found to have no importers.
    assert "0 importers" not in rendered
    assert "IMPACT OBSERVED" not in rendered
    assert "NO DIRECT STATIC IMPORTERS OBSERVED" not in rendered
    assert "BREAKING" not in rendered
    assert "✓ SAFE" not in rendered


def test_impact_formatter_distinguishes_unobserved_cochange_from_zero() -> None:
    from core.engine.mcp.server import _fmt_impact

    importer_only = _fmt_impact(
        {"impact_evidence_basis": "direct_static_importers", "importers": [], "cochange_partners": []},
        "engine/utils/leaf.py",
    )
    with_cochange = _fmt_impact(
        {
            "impact_evidence_basis": "direct_static_importers_and_cochange",
            "importers": [],
            "cochange_partners": [],
        },
        "engine/utils/leaf.py",
    )

    assert "Co-change partners not observed by this adapter" in importer_only
    assert "0 co-change partner(s) observed" in with_cochange


def test_impact_formatter_discloses_bounded_truncation() -> None:
    from core.engine.mcp.server import _fmt_impact

    rendered = _fmt_impact(
        {
            "importers": [{"path": "a.py"}],
            "truncated_collections": ["importers"],
            "uncertainties": ["Bounded traversal stopped at the declared per-collection limit for importers."],
        },
        "core/engine/core/db.py",
    )

    assert "Bounded traversal stopped at its limit for: importers" in rendered
    assert "remainder is unknown and uncounted" in rendered


# ---------------------------------------------------------------------------
# ace_impact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_impact_returns_dependents():
    """ace_impact() returns dependent files and functions as a dict."""
    from core.engine.mcp.tools import ace_impact

    file_row = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
        "change_frequency": 7,
    }
    importer_rows = [
        {"path": "core/engine/mcp/tools.py", "name": "tools", "language": "python"},
        {"path": "core/engine/api/graph_traverse.py", "name": "graph_traverse", "language": "python"},
    ]
    function_rows = [
        {"name": "pool", "kind": "variable", "line_start": 10, "line_end": 10},
        {"name": "parse_rows", "kind": "function", "line_start": 20, "line_end": 30},
    ]
    capability_rows = [
        {"slug": "graph-tools", "name": "Graph Tools"},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # path lookup → parse_one returns file_row
                importer_rows,  # importers traversal
                function_rows,  # functions traversal
                capability_rows,  # capabilities query
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("core/engine/core/db.py")

    assert isinstance(result, dict)
    assert result["file"] == "core/engine/core/db.py"
    assert result["importer_count"] == 2
    assert result["function_count"] == 2
    assert result["safe_to_delete"] is False
    assert result["deletion_safety"] == "not_assessed"
    assert result["impact_evidence_basis"] == "direct_static_importers"
    assert len(result["uncertainties"]) == 3
    assert any("core/engine/mcp/tools.py" in str(r) for r in result["importers"])
    assert any("core/engine/api/graph_traverse.py" in str(r) for r in result["importers"])
    assert any("parse_rows" in str(f) for f in result["functions"])
    assert "summary" in result
    # This adapter never reads co-change edges, so it says so rather than
    # publishing a zero count it did not observe.
    assert result["cochange_partners"] == []
    assert result["observation_windows"]["cochange_partners"]["observed"] is False
    assert "co-change partners not observed" in result["summary"]
    assert result["target_node_id"] == "graph_file:engine_core_db_py"
    assert result["product_ref"] == "product:platform"
    # Exact structured rows carrying the established compatibility columns.
    assert result["importers"][0]["path"] == "core/engine/api/graph_traverse.py"
    assert result["importers"][0]["language"] == "python"
    assert result["importers"][0]["establishes_breakage"] is False
    parse_rows_row = next(row for row in result["functions"] if row["name"] == "parse_rows")
    assert parse_rows_row["kind"] == "function"
    assert parse_rows_row["line_start"] == 20
    assert parse_rows_row["line_end"] == 30
    assert result["capabilities"][0]["slug"] == "graph-tools"
    assert result["capabilities"][0]["product_ref"] == "product:platform"


@pytest.mark.asyncio
async def test_ace_impact_queries_are_bounded_at_limit_bound_plus_one():
    """Every collection query stops one row past its declared bound."""
    from core.engine.code_intelligence.impact import (
        IMPACT_MAX_CAPABILITIES,
        IMPACT_MAX_FUNCTIONS,
        IMPACT_MAX_IMPORTERS,
    )
    from core.engine.mcp.tools import ace_impact

    file_row = {"id": "graph_file:leaf", "path": "engine/utils/leaf.py"}
    mock_pool, mock_conn = _make_pool_mock([[file_row], [], [], []])

    with patch("core.engine.mcp.tools.pool", mock_pool):
        await ace_impact("engine/utils/leaf.py")

    queries = [call.args[0] for call in mock_conn.query.await_args_list]
    assert f"LIMIT {IMPACT_MAX_IMPORTERS + 1}" in queries[1]
    assert f"LIMIT {IMPACT_MAX_FUNCTIONS + 1}" in queries[2]
    assert f"LIMIT {IMPACT_MAX_CAPABILITIES + 1}" in queries[3]
    # The product is always a bound parameter, never interpolated into the text.
    assert mock_conn.query.await_args_list[3].args[1]["product"] == "product:platform"
    assert "product:platform" not in queries[3]


@pytest.mark.asyncio
async def test_ace_impact_trims_dedupes_and_discloses_overflowing_importers():
    """Overflow past the bound is trimmed and disclosed, never silently dropped."""
    from core.engine.code_intelligence.impact import IMPACT_MAX_IMPORTERS
    from core.engine.mcp.tools import ace_impact

    file_row = {"id": "graph_file:db", "path": "core/engine/core/db.py"}
    overflowing = [
        {"id": f"graph_file:i{index:04d}", "path": f"pkg/i{index:04d}.py"} for index in range(IMPACT_MAX_IMPORTERS + 1)
    ]
    overflowing.append(dict(overflowing[0]))
    mock_pool, _ = _make_pool_mock([[file_row], overflowing, [], []])

    with patch("core.engine.mcp.tools.pool", mock_pool):
        result = await ace_impact("core/engine/core/db.py")

    assert result["importer_count"] == IMPACT_MAX_IMPORTERS
    window = result["observation_windows"]["importers"]
    assert window["truncated"] is True
    assert window["undisclosed_remainder"] == "unknown"
    assert result["truncated_collections"] == ["importers"]
    assert "bounded traversal truncated in: importers" in result["summary"]


@pytest.mark.asyncio
async def test_ace_impact_names_its_provenance_and_refuses_every_authority():
    from core.engine.mcp.tools import ace_impact

    file_row = {"id": "graph_file:leaf", "path": "engine/utils/leaf.py"}
    mock_pool, _ = _make_pool_mock([[file_row], [], [], []])

    with patch("core.engine.mcp.tools.pool", mock_pool):
        result = await ace_impact("engine/utils/leaf.py")

    assert result["contract"] == "ace.code-intelligence.impact-observation/v1alpha1"
    assert result["graph_id"] == "default"
    assert result["evidence_id"].startswith("code_impact_evidence:")
    assert result["graph_revision"] == "unestablished"
    assert result["graph_revision_established"] is False
    assert result["graph_freshness"] == "unestablished"
    assert result["graph_freshness_established"] is False
    assert result["fragility_assessed"] is False
    assert result["breakage_assessed"] is False
    for authority in (
        "source_authority",
        "reasoning_authority",
        "change_authority",
        "approval_authority",
        "delivery_authority",
        "execution_authority",
        "effect_authority",
    ):
        assert result[authority] is False, authority


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"file_path": 7}, "file_path must be a string"),
        ({"file_path": ["engine/core/db.py"]}, "file_path must be a string"),
        ({"file_path": {"path": "engine/core/db.py"}}, "file_path must be a string"),
        ({"file_path": None}, "file_path must be a string"),
        ({"file_path": True}, "file_path must be a string"),
        ({"file_path": ""}, "file_path must not be empty"),
        ({"file_path": "a" * (IMPACT_MAX_PATH_CHARS + 1)}, f"file_path must be at most {IMPACT_MAX_PATH_CHARS}"),
        ({"file_path": "engine/../secrets.py"}, "file_path must not contain"),
        ({"file_path": "engine/core/db.py", "product_id": 7}, "product_id must be a string"),
        ({"file_path": "engine/core/db.py", "product_id": ["product:platform"]}, "product_id must be a string"),
        ({"file_path": "engine/core/db.py", "product_id": ""}, "product_id must not be empty"),
        (
            {"file_path": "engine/core/db.py", "product_id": "p" * (IMPACT_MAX_REF_CHARS + 1)},
            f"product_id must be at most {IMPACT_MAX_REF_CHARS}",
        ),
        ({"file_path": "engine/core/db.py", "product_id": "platform"}, "product_id must be a record id"),
    ],
)
async def test_ace_impact_refuses_unshaped_arguments_before_any_db_call(kwargs, expected):
    """An MCP argument arrives unshaped, so it is admitted before a connection is opened."""
    from core.engine.core.exceptions import ValidationError
    from core.engine.mcp.tools import ace_impact

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=AssertionError("no query may run for a rejected argument"))
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ValidationError) as excinfo:
            await ace_impact(**kwargs)

        # No connection was opened and no query ran.
        assert mock_pool.connection.call_args_list == []
        assert mock_conn.query.await_args_list == []

    message = str(excinfo.value)
    unwrapped = re.sub(r"^\[[0-9a-f]{12}\] ", "", message)
    assert unwrapped.startswith(expected)
    # Bounded and non-echoing: the refusal names the field and its rule, and
    # never reflects the rejected value back into a response the model reads.
    assert len(message) < 120
    for value in kwargs.values():
        if isinstance(value, str) and len(value) > IMPACT_MAX_REF_CHARS:
            assert value not in message


@pytest.mark.asyncio
async def test_ace_impact_admits_a_selector_at_the_central_bound():
    """The bound is a limit, not a trim: a selector exactly at it is still read as sent."""
    from core.engine.mcp.tools import ace_impact

    at_bound = "a" * IMPACT_MAX_PATH_CHARS

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact(at_bound)

    # The caller's material reached the query whole — nothing was truncated.
    assert mock_conn.query.await_args_list[0].args[1]["path"] == at_bound
    assert "error" in result


@pytest.mark.asyncio
async def test_ace_impact_file_not_found():
    """ace_impact() returns an error dict when the file isn't in the graph."""
    from core.engine.mcp.tools import ace_impact

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                # path lookup — not found
                [],
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("engine/nonexistent/file.py")

    assert isinstance(result, dict)
    assert "error" in result
    assert "not found" in result["error"].lower()
    assert "engine/nonexistent/file.py" in result["error"]


@pytest.mark.asyncio
async def test_ace_impact_no_dependents_does_not_claim_safe_deletion():
    """No observed static importers is evidence, not proof of safe deletion."""
    from core.engine.mcp.tools import ace_impact

    file_row = {
        "id": "graph_file:engine_utils_leaf_py",
        "path": "engine/utils/leaf.py",
        "change_frequency": 1,
    }

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # path lookup
                [],  # no importers
                [],  # no functions
                [],  # no capabilities
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("engine/utils/leaf.py")

    assert isinstance(result, dict)
    assert result["file"] == "engine/utils/leaf.py"
    assert result["importer_count"] == 0
    assert result["safe_to_delete"] is False
    assert result["deletion_safety"] == "not_assessed"
    assert result["impact_evidence_basis"] == "direct_static_importers"
    assert result["summary"].startswith("NO DIRECT STATIC IMPORTERS OBSERVED")
    assert "deletion safety not assessed" in result["summary"]
    assert any("Dynamic imports" in uncertainty for uncertainty in result["uncertainties"])
    assert result["importers"] == []


@pytest.mark.asyncio
async def test_ace_impact_fragility_score_high_with_many_dependents():
    """ace_impact() reports high importer count when file has many dependents."""
    from core.engine.mcp.tools import ace_impact

    file_node = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
        "change_frequency": 15,
    }
    # 12 importers
    importer_rows = [{"path": f"engine/module_{i}.py", "name": f"module_{i}", "language": "python"} for i in range(12)]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_node],  # path lookup
                importer_rows,  # importers traversal (12 rows)
                [],  # no functions
                [],  # no capabilities
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_impact("core/engine/core/db.py")

    assert isinstance(result, dict)
    assert result["importer_count"] == 12
    assert result["safe_to_delete"] is False
    # Summary should mention 12 file(s)
    assert "12 file(s)" in result["summary"]


# ---------------------------------------------------------------------------
# ace_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_history_returns_decisions():
    """ace_history() returns the decision trail for a file."""
    from core.engine.mcp.tools import ace_history

    file_row = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
    }
    decision_rows = [
        {
            "id": "graph_decision:d1",
            "title": "Add connection pooling",
            "description": "Single connection caused blocking; replaced with pool.",
            "outcome": "Throughput improved 10x",
            "created_at": "2026-02-10T12:00:00Z",
            "tags": ["performance", "db"],
        },
        {
            "id": "graph_decision:d2",
            "title": "Add watchdog task",
            "description": "Pool connections leaked under load.",
            "outcome": "Zero leaked connections after watchdog",
            "created_at": "2026-02-15T09:00:00Z",
            "tags": ["reliability"],
        },
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # slug lookup
                decision_rows,  # improves decisions
                [],  # informed_by decisions
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("core/engine/core/db.py")

    assert "core/engine/core/db.py" in result
    assert "Add connection pooling" in result
    assert "Throughput improved 10x" in result
    assert "Add watchdog task" in result
    assert "performance" in result
    assert "Decision History" in result


@pytest.mark.asyncio
async def test_ace_history_file_not_found():
    """ace_history() returns a helpful message when file isn't in the graph."""
    from core.engine.mcp.tools import ace_history

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("engine/ghost/file.py")

    assert "not found" in result.lower()
    assert "engine/ghost/file.py" in result


@pytest.mark.asyncio
async def test_ace_history_no_decisions():
    """ace_history() returns appropriate message when no decisions exist."""
    from core.engine.mcp.tools import ace_history

    file_row = {
        "id": "graph_file:engine_utils_new_py",
        "path": "engine/utils/new.py",
    }

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[file_row], [], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("engine/utils/new.py")

    assert "engine/utils/new.py" in result
    assert "No decisions" in result or "no decisions" in result.lower()


@pytest.mark.asyncio
async def test_ace_history_includes_informed_by():
    """ace_history() includes decisions connected via informed_by edges."""
    from core.engine.mcp.tools import ace_history

    file_row = {"id": "graph_file:engine_core_config_py", "path": "core/engine/core/config.py"}
    informed_rows = [
        {
            "id": "graph_decision:d5",
            "title": "Use pydantic-settings for config",
            "description": "Typed env loading",
            "outcome": "No more KeyError on missing env vars",
            "created_at": "2026-01-05T10:00:00Z",
        }
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],
                [],  # no improves decisions
                informed_rows,  # informed_by decisions
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_history("core/engine/core/config.py")

    assert "Use pydantic-settings for config" in result
    assert "Also informed by" in result


# ---------------------------------------------------------------------------
# ace_related
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ace_related_returns_connections():
    """ace_related() returns imports, importers, co-changed files, and decisions."""
    from core.engine.mcp.tools import ace_related

    file_row = {
        "id": "graph_file:engine_core_db_py",
        "path": "core/engine/core/db.py",
    }
    import_rows = [
        {"id": "graph_file:engine_core_config_py", "path": "core/engine/core/config.py"},
    ]
    importer_rows = [
        {"id": "graph_file:engine_mcp_tools_py", "path": "core/engine/mcp/tools.py"},
        {"id": "graph_file:engine_api_graph_traverse_py", "path": "core/engine/api/graph_traverse.py"},
    ]
    related_rows = [
        {"id": "graph_file:engine_core_auth_py", "path": "core/engine/core/auth.py"},
    ]
    function_rows = [
        {"id": "graph_function:parse_rows", "name": "parse_rows"},
        {"id": "graph_function:pool", "name": "pool"},
    ]
    decision_rows = [
        {"id": "graph_decision:d1", "title": "Connection pooling", "created_at": "2026-02-10T12:00:00Z"},
    ]

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            side_effect=[
                [file_row],  # slug lookup
                import_rows,  # outgoing imports
                importer_rows,  # incoming imports
                related_rows,  # related_to
                function_rows,  # functions
                decision_rows,  # decisions
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_related("core/engine/core/db.py")

    assert "core/engine/core/db.py" in result
    assert "core/engine/core/config.py" in result
    assert "core/engine/mcp/tools.py" in result
    assert "core/engine/core/auth.py" in result
    assert "parse_rows" in result
    assert "Connection pooling" in result
    assert "Imports" in result
    assert "Imported by" in result
    assert "Co-changed" in result


@pytest.mark.asyncio
async def test_ace_related_file_not_found():
    """ace_related() returns a helpful message when the file isn't in the graph."""
    from core.engine.mcp.tools import ace_related

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_related("engine/does/not/exist.py")

    assert "not found" in result.lower()
    assert "engine/does/not/exist.py" in result


@pytest.mark.asyncio
async def test_ace_related_isolated_file():
    """ace_related() handles a file with no connections."""
    from core.engine.mcp.tools import ace_related

    file_row = {"id": "graph_file:engine_scratch_py", "path": "engine/scratch.py"}

    with patch("core.engine.mcp.tools.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(side_effect=[[file_row], [], [], [], [], []])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await ace_related("engine/scratch.py")

    assert "engine/scratch.py" in result
    assert "0 connections" in result or "isolated" in result.lower()


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_server_has_twenty_two_tools():
    """Server registers expected number of tools."""
    from core.engine.mcp.server import mcp

    tools = await mcp.list_tools()
    assert len(tools) >= 30


@pytest.mark.asyncio
async def test_mcp_server_graph_tool_names():
    """The 3 new graph tool names are registered."""
    from core.engine.mcp.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "ace_impact" in tool_names
    assert "ace_history" in tool_names
    assert "ace_related" in tool_names
