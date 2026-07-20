# tests/test_decisions.py
"""Tests for decision CRUD."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


@pytest.mark.asyncio
async def test_create_decision(mock_pool):
    """create_decision writes to DB and returns a decision record."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        return_value=[
            {
                "id": "decision:abc",
                "title": "Use PostgreSQL",
                "decision_type": "architecture",
                "rationale": "Better JSON support",
                "outcome": "accepted",
            }
        ]
    )

    from core.engine.product.decisions import create_decision

    result = await create_decision(
        title="Use PostgreSQL",
        decision_type="architecture",
        rationale="Better JSON support",
        product_id="product:default",
        pool=mock_p,
    )

    assert result["title"] == "Use PostgreSQL"
    assert result["decision_type"] == "architecture"
    all_queries = [c[0][0] for c in mock_db.query.call_args_list]
    assert any("CREATE decision SET" in q for q in all_queries)


@pytest.mark.asyncio
async def test_create_decision_with_edges(mock_pool):
    """create_decision creates affected and led_to edges when IDs provided."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        return_value=[
            {
                "id": "decision:abc",
                "title": "Adopt TDD",
                "decision_type": "convention",
                "rationale": "Fewer regressions",
                "outcome": "accepted",
            }
        ]
    )

    from core.engine.product.decisions import create_decision

    with patch("core.engine.product.decisions.create_edge", new_callable=AsyncMock) as mock_edge:
        await create_decision(
            title="Adopt TDD",
            decision_type="convention",
            rationale="Fewer regressions",
            product_id="product:default",
            affected_capabilities=["capability:testing"],
            led_to_ids=["agent_spec:s1"],
            pool=mock_p,
        )

        edge_calls = [c[0][0] for c in mock_edge.call_args_list]
        assert "affected" in edge_calls
        assert "led_to" in edge_calls


@pytest.mark.asyncio
async def test_supersede_decision(mock_pool):
    """supersede_decision marks old as superseded and creates supersedes edge."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        side_effect=[
            # First query: existing decision lookup (not yet superseded)
            [{"id": "decision:old", "outcome": "accepted"}],
            # Second query: UPDATE old decision
            [],
            # Third query: CREATE new decision
            [
                {
                    "id": "decision:new",
                    "title": "New approach",
                    "decision_type": "architecture",
                    "rationale": "Better",
                    "outcome": "accepted",
                }
            ],
        ]
    )

    from core.engine.product.decisions import supersede_decision

    with patch("core.engine.product.decisions.create_edge", new_callable=AsyncMock) as mock_edge:
        result = await supersede_decision(
            old_id="decision:old",
            title="New approach",
            decision_type="architecture",
            rationale="Better",
            product_id="product:default",
            pool=mock_p,
        )

        assert result["title"] == "New approach"
        mock_edge.assert_called_once_with("supersedes", "decision:new", "decision:old", pool=mock_p)


@pytest.mark.asyncio
async def test_supersede_already_superseded_decision_raises(mock_pool):
    """supersede_decision raises ValidationError if old decision is already superseded."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        side_effect=[
            [{"id": "decision:old", "outcome": "superseded"}],
        ]
    )

    from core.engine.core.exceptions import ValidationError
    from core.engine.product.decisions import supersede_decision

    with pytest.raises(ValidationError, match="already superseded"):
        await supersede_decision(
            old_id="decision:old",
            title="New approach",
            decision_type="architecture",
            rationale="Better",
            product_id="product:default",
            pool=mock_p,
        )


@pytest.mark.asyncio
async def test_list_decisions(mock_pool):
    """list_decisions returns filtered results."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        return_value=[
            {"id": "decision:a", "title": "A", "decision_type": "architecture"},
            {"id": "decision:b", "title": "B", "decision_type": "architecture"},
        ]
    )

    from core.engine.product.decisions import list_decisions

    result = await list_decisions("product:default", decision_type="architecture", pool=mock_p)

    assert len(result) == 2
    call_query = mock_db.query.call_args[0][0]
    assert "decision_type" in call_query


@pytest.mark.asyncio
async def test_get_decision(mock_pool):
    """get_decision returns a single decision with edges."""
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(
        side_effect=[
            [
                {
                    "id": "decision:abc",
                    "title": "Use SurrealDB",
                    "decision_type": "architecture",
                    "rationale": "Graph + document in one",
                    "outcome": "accepted",
                }
            ],
            [{"affected": [], "led_to": [], "supersedes": []}],
        ]
    )

    from core.engine.product.decisions import get_decision

    result = await get_decision("decision:abc", pool=mock_p)

    assert result["title"] == "Use SurrealDB"
    assert "edges" in result


# -----------------------------------------------------------------------------
# Layer 5 forward-write: affected_capabilities populated atomically in CREATE.
# Integration tests against real SurrealDB — the schema-write needs to be
# verified at the boundary, not just in mocks.
# decision:lv6stu70piemfwypde2e — Stage 2 capture-write fix.
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_decision_writes_capability_fields_when_caps_provided(db_pool):
    """When caller passes affected_capabilities, the CREATE writes all three
    capability columns atomically: the list, inferred_at (= now), and
    confidence (= 1.0 default for caller-supplied = ground truth)."""
    from core.engine.core.db import parse_one
    from core.engine.product.decisions import create_decision

    result = await create_decision(
        title="L5 forward-write test A",
        decision_type="architecture",
        rationale="Verify caps land in the row, not just on the edges",
        product_id="product:test_l5_capture",
        affected_capabilities=["auth", "session-management"],
        pool=db_pool,
    )
    assert result.get("id"), f"create_decision returned no id: {result}"
    decision_id = str(result["id"])

    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                """SELECT affected_capabilities,
                          affected_capabilities_inferred_at,
                          affected_capabilities_confidence
                   FROM decision WHERE id = <record>$id""",
                {"id": decision_id},
            )
        )
    assert row is not None
    assert row["affected_capabilities"] == ["auth", "session-management"]
    assert row["affected_capabilities_inferred_at"] is not None
    assert row["affected_capabilities_confidence"] == 1.0


@pytest.mark.asyncio
async def test_create_decision_uses_caller_confidence_when_provided(db_pool):
    """When caller passes affected_capabilities_confidence, that overrides the
    1.0 default. This is the path the forward-inference Stage 2 work would
    eventually use to thread through a real LLM-confidence score."""
    from core.engine.core.db import parse_one
    from core.engine.product.decisions import create_decision

    result = await create_decision(
        title="L5 forward-write test B",
        decision_type="architecture",
        rationale="Verify confidence threading from caller",
        product_id="product:test_l5_capture",
        affected_capabilities=["auth"],
        affected_capabilities_confidence=0.73,
        pool=db_pool,
    )
    decision_id = str(result["id"])

    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                "SELECT affected_capabilities_confidence FROM decision WHERE id = <record>$id",
                {"id": decision_id},
            )
        )
    assert row is not None
    assert row["affected_capabilities_confidence"] == 0.73


@pytest.mark.asyncio
async def test_create_decision_leaves_caps_none_when_not_provided(db_pool):
    """When the caller passes no capability info, the row's three columns
    remain NONE so the nightly sentinel / one-time backfill picks it up.
    This is the safety net for callers that haven't been updated yet."""
    from core.engine.core.db import parse_one
    from core.engine.product.decisions import create_decision

    result = await create_decision(
        title="L5 forward-write test C",
        decision_type="architecture",
        rationale="Verify NONE is preserved (sentinel-deferred path)",
        product_id="product:test_l5_capture",
        pool=db_pool,
    )
    decision_id = str(result["id"])

    async with db_pool.connection() as db:
        row = parse_one(
            await db.query(
                """SELECT affected_capabilities,
                          affected_capabilities_inferred_at,
                          affected_capabilities_confidence
                   FROM decision WHERE id = <record>$id""",
                {"id": decision_id},
            )
        )
    assert row is not None
    assert row.get("affected_capabilities") is None
    assert row.get("affected_capabilities_inferred_at") is None
    assert row.get("affected_capabilities_confidence") is None
