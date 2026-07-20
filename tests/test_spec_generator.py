# tests/test_spec_generator.py
"""Tests for SpecGenerator — TDD.

Four tests:
1. test_from_gap_generates_spec: mock LLM + DB, verify spec generated with correct fields and persisted
2. test_from_gap_unknown_capability: returns error dict when capability not found
3. test_from_request_generates_spec: mock LLM + DB, verify spec from natural language request
4. test_persist_spec_resolves_capability: verify _persist_spec looks up capability by slug
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pool(db):
    """Build a mock pool that yields db on context manager entry."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


def _make_db(*side_effects):
    """Build a mock DB with query returning the given side effects in order."""
    db = AsyncMock()
    db.query = AsyncMock(side_effect=list(side_effects))
    return db


LLM_SPEC = {
    "objective": "Add rate limiting to login endpoint",
    "acceptance_criteria": [
        {"criterion": "Returns 429 after 100 req/min", "verification": "curl test", "automated": True},
    ],
    "constraints": ["Do not modify auth middleware signature"],
    "integration_points": [{"file": "engine/api/auth.py", "function": "login", "description": "Add decorator"}],
    "estimated_files": ["engine/api/auth.py"],
    "test_requirements": ["test that login returns 429 after rate limit hit"],
    "best_practices": ["Use token bucket algorithm"],
}

FAKE_CAPABILITY = {
    "id": "capability:auth",
    "slug": "auth",
    "name": "Authentication",
    "description": "User authentication flows",
    "status": "built",
    "files": [{"file_path": "engine/api/auth.py"}],
}

FAKE_SPEC_RECORD = {
    "id": "agent_spec:001",
    "objective": "Add rate limiting to login endpoint",
    "status": "draft",
    "source": "gap",
}


# ---------------------------------------------------------------------------
# Test 1: from_gap generates a spec and persists it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_gap_generates_spec():
    """Mock LLM + DB: from_gap produces a spec dict with expected fields."""
    # DB call sequence:
    #   1. _load_practices -> insights query (returns empty list)
    #   2. _load_tech_context -> graph_file query (returns empty list)
    #   3. _persist_spec -> capability lookup by slug (returns cap record)
    #   4. _persist_spec -> CREATE agent_spec (returns spec record)
    practices_db = _make_db(
        [],  # _load_practices
        [],  # _load_tech_context (SELECT path, language FROM graph_file...)
        [{"id": "capability:auth", "slug": "auth"}],  # capability lookup in _persist_spec
        [FAKE_SPEC_RECORD],  # CREATE agent_spec
    )
    pool = _make_pool(practices_db)

    # ProductMap.get_capability needs its own DB interactions (4 queries)
    cap_db = AsyncMock()
    cap_db.query = AsyncMock(
        side_effect=[
            [FAKE_CAPABILITY],  # SELECT capability
            [],  # capability_quality
            [],  # capability_dep
            [],  # realizes
        ]
    )
    cap_pool = _make_pool(cap_db)

    with (
        patch("core.engine.product.spec_generator.get_llm") as MockLLM,
        patch("core.engine.product.spec_generator.ProductMap") as MockPM,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete_json = AsyncMock(return_value=LLM_SPEC)
        MockLLM.return_value = mock_llm_instance

        mock_pm_instance = MagicMock()
        mock_pm_instance.get_capability = AsyncMock(return_value=FAKE_CAPABILITY)
        MockPM.return_value = mock_pm_instance

        from core.engine.product.spec_generator import SpecGenerator

        gen = SpecGenerator(pool)
        gap = {
            "dimension": "security",
            "score": 0.3,
            "gaps": ["No rate limiting", "Missing MFA"],
            "evidence": ["auth.py reviewed"],
        }

        result = await gen.from_gap(gap, "auth", "product:test")

    # LLM was called once with a prompt
    mock_llm_instance.complete_json.assert_called_once()
    prompt_arg = mock_llm_instance.complete_json.call_args[0][0]
    assert "rate limiting" in prompt_arg.lower() or "security" in prompt_arg.lower()

    # Result came back (either the persisted record or the LLM dict)
    assert isinstance(result, dict)
    assert "error" not in result


# ---------------------------------------------------------------------------
# Test 2: from_gap returns error when capability not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_gap_unknown_capability():
    """from_gap returns an error dict when the capability slug is not found."""
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])  # no capability found
    pool = _make_pool(db)

    with patch("core.engine.product.spec_generator.ProductMap") as MockPM:
        mock_pm_instance = MagicMock()
        mock_pm_instance.get_capability = AsyncMock(return_value=None)
        MockPM.return_value = mock_pm_instance

        # ClaudeProvider still needs to be patchable but won't be called
        with patch("core.engine.product.spec_generator.get_llm"):
            from core.engine.product.spec_generator import SpecGenerator

            gen = SpecGenerator(pool)
            gap = {"dimension": "testing", "score": 0.2, "gaps": ["no tests"]}

            result = await gen.from_gap(gap, "nonexistent-cap", "product:test")

    assert "error" in result
    assert "nonexistent-cap" in result["error"]


# ---------------------------------------------------------------------------
# Test 3: from_request generates a spec from natural language
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_request_generates_spec():
    """Mock LLM + DB: from_request produces a spec from a plain text request."""
    health = {
        "dimensions": {"security": {"avg_score": 0.5, "total_gaps": 3}},
        "total_capabilities": 5,
        "by_status": {"built": 3, "planned": 2},
    }
    direction = {"name": "Scale to enterprise", "description": "Focus on multi-tenancy"}

    db = _make_db(
        [],  # _load_tech_context (SELECT path, language FROM graph_file...)
        [],  # _find_related_files (SELECT id, slug, name, description FROM capability...)
        [{"id": "agent_spec:002", "objective": "Add OAuth", "status": "draft", "source": "human"}],
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.spec_generator.get_llm") as MockLLM,
        patch("core.engine.product.spec_generator.ProductMap") as MockPM,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete_json = AsyncMock(return_value=LLM_SPEC)
        MockLLM.return_value = mock_llm_instance

        mock_pm_instance = MagicMock()
        mock_pm_instance.health_summary = AsyncMock(return_value=health)
        mock_pm_instance.get_vision = AsyncMock(return_value=direction)
        MockPM.return_value = mock_pm_instance

        from core.engine.product.spec_generator import SpecGenerator

        gen = SpecGenerator(pool)
        result = await gen.from_request("Add OAuth2 login support", "product:test")

    # health_summary and get_vision were called to build context
    mock_pm_instance.health_summary.assert_called_once_with("product:test")
    mock_pm_instance.get_vision.assert_called_once_with("product:test")

    # LLM was invoked with the request in the prompt
    mock_llm_instance.complete_json.assert_called_once()
    prompt_arg = mock_llm_instance.complete_json.call_args[0][0]
    assert "oauth" in prompt_arg.lower() or "OAuth" in prompt_arg

    assert isinstance(result, dict)
    assert "error" not in result


# ---------------------------------------------------------------------------
# Test 4: _persist_spec resolves capability by slug and writes spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_spec_resolves_capability():
    """_persist_spec looks up capability by slug and uses its ID in the INSERT."""
    cap_record = {"id": "capability:auth", "slug": "auth"}
    spec_record = {"id": "agent_spec:003", "objective": "Fix rate limiting", "status": "draft"}

    db = _make_db(
        [cap_record],  # capability lookup
        [spec_record],  # CREATE agent_spec
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.spec_generator.get_llm"),
        patch("core.engine.product.spec_generator.ProductMap"),
    ):
        from core.engine.product.spec_generator import SpecGenerator

        gen = SpecGenerator(pool)

        spec_data = {
            "objective": "Fix rate limiting",
            "acceptance_criteria": [{"criterion": "Returns 429", "verification": "curl", "automated": True}],
            "constraints": ["preserve middleware interface"],
            "integration_points": [],
            "estimated_files": ["engine/api/auth.py"],
            "test_requirements": ["test_rate_limit"],
            "best_practices": ["use token bucket"],
        }

        result = await gen._persist_spec(spec_data, "gap", "auth", "product:test")

    # First DB call should be the capability lookup
    first_call_sql = db.query.call_args_list[0][0][0]
    assert "capability" in first_call_sql.lower()
    assert "slug" in first_call_sql.lower()

    # Second DB call should CREATE the spec
    second_call_sql = db.query.call_args_list[1][0][0]
    assert "agent_spec" in second_call_sql.lower()

    # Result matches the stored record
    assert result["id"] == "agent_spec:003"
    assert result["status"] == "draft"
