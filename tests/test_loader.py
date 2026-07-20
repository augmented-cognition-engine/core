# tests/test_loader.py
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_loader_returns_empty_when_no_insights():
    """Loader returns empty snapshot when no insights exist."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(discipline="engineering", product_id="product:test")

    assert snapshot["discipline"] == "engineering"
    assert snapshot["specialties"] == []
    assert snapshot["insights"] == []
    assert snapshot["total_count"] == 0
    assert snapshot["recent_signals"] == []
    assert snapshot["raw_context"] == []


@pytest.mark.asyncio
async def test_loader_formats_snapshot():
    """Loader returns properly formatted intelligence snapshot."""
    from core.engine.orchestrator.loader import load_intelligence

    mock_insights = [
        {"id": "insight:1", "content": "Use pytest", "confidence": 0.9, "tier": "subdomain", "insight_type": "fact"},
        {
            "id": "insight:2",
            "content": "CI uses GitHub Actions",
            "confidence": 0.8,
            "tier": "domain",
            "insight_type": "fact",
        },
    ]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[mock_insights])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(discipline="engineering", product_id="product:test")

    assert snapshot["total_count"] == 2
    assert len(snapshot["insights"]) == 2
    assert snapshot["insights"][0]["content"] == "Use pytest"


@pytest.mark.asyncio
async def test_loader_ranks_by_trust_weighted_confidence():
    """A high-confidence LOW-trust insight (self-generated) ranks BELOW a lower-confidence HIGH-trust
    one (human capture) after trust-weighting — confidence alone would invert this. This is the active
    loop's echo-chamber guard made load-bearing at retrieval."""
    from core.engine.orchestrator.loader import load_intelligence

    mock_insights = [
        {
            "id": "insight:self",
            "content": "self-generated",
            "confidence": 0.95,
            "trust": 0.5,
            "tier": "subdomain",
            "insight_type": "fact",
            "tags": ["engineering"],
        },
        {
            "id": "insight:human",
            "content": "human capture",
            "confidence": 0.7,
            "trust": 0.95,
            "tier": "subdomain",
            "insight_type": "fact",
            "tags": ["engineering"],
        },
    ]
    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[mock_insights])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        snapshot = await load_intelligence(discipline="engineering", product_id="product:test")

    contents = [i["content"] for i in snapshot["insights"]]
    # human 0.7×0.95=0.665 outranks self 0.95×0.5=0.475
    assert contents.index("human capture") < contents.index("self-generated")


@pytest.mark.asyncio
async def test_loader_trust_none_preserves_confidence_order():
    """Un-reconciled insights (no trust field) keep pure-confidence ordering — missing trust data is
    never penalized, only known-low-trust content is demoted."""
    from core.engine.orchestrator.loader import load_intelligence

    mock_insights = [
        {
            "id": "insight:a",
            "content": "high conf",
            "confidence": 0.9,
            "tier": "subdomain",
            "insight_type": "fact",
            "tags": ["engineering"],
        },
        {
            "id": "insight:b",
            "content": "low conf",
            "confidence": 0.6,
            "tier": "subdomain",
            "insight_type": "fact",
            "tags": ["engineering"],
        },
    ]
    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[mock_insights])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        snapshot = await load_intelligence(discipline="engineering", product_id="product:test")

    contents = [i["content"] for i in snapshot["insights"]]
    assert contents == ["high conf", "low conf"]


@pytest.mark.asyncio
async def test_loader_reactive_skips_observations():
    """Reactive mode does NOT load recent observations."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(discipline="engineering", product_id="product:test", mode="reactive")

    assert snapshot["recent_signals"] == []
    assert snapshot["raw_context"] == []


@pytest.mark.asyncio
async def test_loader_deliberative_loads_observations():
    """Deliberative mode loads recent observations."""
    from core.engine.orchestrator.loader import load_intelligence

    mock_observations = [{"content": "PKCE required by IdP", "observation_type": "discovery", "confidence": 0.9}]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        # Calls: insights, observations
        mock_conn.query = AsyncMock(side_effect=[[[]], [mock_observations]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(discipline="architecture", product_id="product:test", mode="deliberative")

    assert len(snapshot["recent_signals"]) == 1
    assert snapshot["recent_signals"][0]["content"] == "PKCE required by IdP"


@pytest.mark.asyncio
async def test_loader_deliberative_empty_observations():
    """Deliberative mode with no recent observations returns empty list, no error."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        # Calls: insights, observations (empty)
        mock_conn.query = AsyncMock(side_effect=[[[]], [[]]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(discipline="architecture", product_id="product:test", mode="deliberative")

    assert snapshot["recent_signals"] == []


@pytest.mark.asyncio
async def test_loader_exploratory_loads_memory():
    """Exploratory mode loads raw memory in addition to observations."""
    from core.engine.orchestrator.loader import load_intelligence

    mock_observations = [{"content": "obs", "observation_type": "fact", "confidence": 0.8}]
    mock_memory = [{"content": "raw chunk", "memory_type": "chunk"}]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        # Calls: insights, observations, memory
        mock_conn.query = AsyncMock(side_effect=[[[]], [mock_observations], [mock_memory]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(discipline="architecture", product_id="product:test", mode="exploratory")

    assert len(snapshot["recent_signals"]) == 1
    assert len(snapshot["raw_context"]) == 1


@pytest.mark.asyncio
async def test_loader_backward_compat_domain_path():
    """Passing domain_path still works — discipline derived from first segment."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(domain_path="architecture", product_id="product:test")

    assert snapshot["discipline"] == "architecture"


@pytest.mark.asyncio
async def test_loader_with_specialties():
    """Specialties are stored in snapshot and passed to the query."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(
            discipline="engineering",
            product_id="product:test",
            specialties=["python", "testing"],
        )

    assert snapshot["specialties"] == ["python", "testing"]
    assert snapshot["discipline"] == "engineering"


@pytest.mark.asyncio
async def test_loader_adjacent_disciplines_included_in_snapshot():
    """When adjacent_disciplines is provided, they appear in the snapshot."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        snapshot = await load_intelligence(
            discipline="security",
            product_id="product:test",
            adjacent_disciplines=["error_handling", "testing"],
        )

    assert snapshot["adjacent_disciplines"] == ["error_handling", "testing"]
    assert "security" in snapshot["disciplines_loaded"]
    assert "error_handling" in snapshot["disciplines_loaded"]
    assert "testing" in snapshot["disciplines_loaded"]


@pytest.mark.asyncio
async def test_loader_includes_recent_decisions():
    """load_intelligence includes recent decisions in snapshot."""
    from core.engine.orchestrator.loader import load_intelligence

    mock_decisions = [
        {
            "title": "Use circuit breaker for async phase failures",
            "decision_type": "architecture",
            "rationale": "prevents cascade amplification",
            "outcome": "adopted",
            "created_at": "2026-04-01T00:00:00Z",
        }
    ]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("core.engine.orchestrator.loader._load_star_traces", return_value=[]),
            patch("core.engine.orchestrator.loader._load_recent_decisions", new=AsyncMock(return_value=mock_decisions)),
        ):
            snapshot = await load_intelligence(discipline="error_handling", product_id="product:test")

    assert "decisions" in snapshot
    assert len(snapshot["decisions"]) == 1
    assert snapshot["decisions"][0]["title"] == "Use circuit breaker for async phase failures"


@pytest.mark.asyncio
async def test_loader_decisions_empty_when_none_exist():
    """load_intelligence returns empty decisions list when none exist."""
    from core.engine.orchestrator.loader import load_intelligence

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("core.engine.orchestrator.loader._load_star_traces", return_value=[]),
            patch("core.engine.orchestrator.loader._load_recent_decisions", new=AsyncMock(return_value=[])),
        ):
            snapshot = await load_intelligence(discipline="error_handling", product_id="product:test")

    assert snapshot.get("decisions", []) == []


@pytest.mark.asyncio
async def test_loader_adjacent_disciplines_expands_query():
    """When adjacent disciplines are provided, the DB query uses the expanded list."""
    from core.engine.orchestrator.loader import load_intelligence

    captured_params = {}

    async def capture_query(query, params):
        captured_params.update(params)
        return [[]]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = capture_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await load_intelligence(
            discipline="security",
            product_id="product:test",
            adjacent_disciplines=["error_handling"],
        )

    # The query should use a 'disciplines' list, not a single 'discipline' string
    assert "disciplines" in captured_params
    assert "security" in captured_params["disciplines"]
    assert "error_handling" in captured_params["disciplines"]


@pytest.mark.asyncio
async def test_loader_no_adjacent_keeps_single_discipline_query():
    """Without adjacent_disciplines, the query stays focused on one discipline."""
    from core.engine.orchestrator.loader import load_intelligence

    captured_params = {}

    async def capture_query(query, params):
        captured_params.update(params)
        return [[]]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = capture_query
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await load_intelligence(discipline="security", product_id="product:test")

    assert captured_params.get("disciplines") == ["security"]
    assert "error_handling" not in captured_params.get("disciplines", [])


@pytest.mark.asyncio
async def test_failure_memory_aggregates_recurring_gaps():
    """_load_failure_memory groups duplicate gaps by frequency."""
    from core.engine.orchestrator.loader import _load_failure_memory

    raw_entries = [
        {"gaps": ["missing error propagation", "no logging on async path"], "verdict": "gaps_found"},
        {"gaps": ["missing error propagation", "no circuit breaker"], "verdict": "gaps_found"},
        {"gaps": ["missing error propagation"], "verdict": "gaps_found"},
    ]

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[raw_entries])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        patterns = await _load_failure_memory("observability", "product:test")

    assert patterns[0]["pattern"] == "missing error propagation"
    assert patterns[0]["count"] == 3
    assert patterns[1]["count"] == 1


@pytest.mark.asyncio
async def test_failure_memory_returns_empty_list_when_no_entries():
    from core.engine.orchestrator.loader import _load_failure_memory

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(return_value=[[]])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        patterns = await _load_failure_memory("observability", "product:test")

    assert patterns == []


@pytest.mark.asyncio
async def test_load_recent_observations_uses_status_not_synthesized_field():
    """_load_recent_observations must filter by status='pending', not the non-existent synthesized field.

    SurrealDB does not have a `synthesized` boolean on observation records — the field
    is `status` ('pending'/'processed'/'failed'). Querying `synthesized = false` always
    returns empty because NONE != false in SurrealDB.
    """
    from core.engine.orchestrator.loader import _load_recent_observations

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [
                    {
                        "content": "chose async over sync for DB writes",
                        "observation_type": "decision",
                        "confidence": 0.9,
                        "created_at": "2026-04-13T00:00:00Z",
                    },
                ]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        results = await _load_recent_observations("architecture", "product:test")

    assert len(results) == 1
    # Sentinel: the query must use status = 'pending', not synthesized = false
    query_text = str(mock_conn.query.call_args)
    assert "synthesized" not in query_text, (
        "Query still references 'synthesized' field which does not exist on observation records"
    )
    assert "status" in query_text and "pending" in query_text, "Query must filter by status = 'pending'"


@pytest.mark.asyncio
async def test_durable_human_guidance_includes_processed_preferences():
    from core.engine.orchestrator.loader import _load_durable_human_guidance

    with patch("core.engine.orchestrator.loader.pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.query = AsyncMock(
            return_value=[
                [{"id": "observation:1", "content": "prefer proof", "insight_type": "preference", "confidence": 1.0}]
            ]
        )
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        results = await _load_durable_human_guidance("product_strategy", "product:test")

    assert results == [
        {
            "id": "observation:1",
            "content": "prefer proof",
            "confidence": 1.0,
            "tier": "human_guidance",
            "insight_type": "preference",
        }
    ]
    query_text = str(mock_conn.query.call_args)
    assert "status = 'pending'" not in query_text
    assert "domain_path" in query_text
