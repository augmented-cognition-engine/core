# tests/test_spec_decision_hook.py
"""Tests for post-spec decision hook — spec generation auto-captures decisions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
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

FAKE_DECISION_RECORD = {
    "id": "decision:abc",
    "title": "Spec: Add rate limiting to login endpoint",
    "decision_type": "architecture",
    "outcome": "accepted",
}


# ---------------------------------------------------------------------------
# Test 1: from_gap creates a decision after generating a spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_gap_creates_decision():
    """create_decision is called after spec generation via from_gap."""
    db = _make_db(
        [],  # _load_practices
        [],  # _load_tech_context (SELECT path, language FROM graph_file...)
        [{"id": "capability:auth", "slug": "auth"}],  # capability lookup in _persist_spec
        [FAKE_SPEC_RECORD],  # CREATE agent_spec
        [],  # addresses edge query (no cq found — best-effort)
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.spec_generator.get_llm") as MockLLM,
        patch("core.engine.product.spec_generator.ProductMap") as MockPM,
        patch("core.engine.product.spec_generator.create_decision", new_callable=AsyncMock) as mock_create_decision,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete_json = AsyncMock(return_value=LLM_SPEC)
        MockLLM.return_value = mock_llm_instance

        mock_pm_instance = MagicMock()
        mock_pm_instance.get_capability = AsyncMock(return_value=FAKE_CAPABILITY)
        MockPM.return_value = mock_pm_instance

        mock_create_decision.return_value = FAKE_DECISION_RECORD

        from core.engine.product.spec_generator import SpecGenerator

        gen = SpecGenerator(pool)
        gap = {
            "dimension": "security",
            "score": 0.3,
            "gaps": ["No rate limiting", "Missing MFA"],
            "evidence": ["auth.py reviewed"],
        }

        result = await gen.from_gap(gap, "auth", "product:test")

    # Spec still returned successfully
    assert isinstance(result, dict)
    assert "error" not in result

    # create_decision was called once with the right arguments
    mock_create_decision.assert_called_once()
    call_kwargs = mock_create_decision.call_args[1]
    assert call_kwargs["decision_type"] == "architecture"
    assert call_kwargs["source"] == "spec_generator"
    assert call_kwargs["product_id"] == "product:test"
    assert "Add rate limiting" in call_kwargs["title"]


# ---------------------------------------------------------------------------
# Test 2: from_idea creates a decision after generating a spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_from_idea_creates_decision():
    """create_decision is called after spec generation via from_idea."""
    idea = {
        "id": "idea:xyz",
        "title": "Cache API responses",
        "description": "Use Redis to cache expensive API calls",
        "capability_slug": None,
    }

    db = _make_db(
        [],  # _load_tech_context (SELECT path, language FROM graph_file...)
        [],  # _find_related_files (SELECT id, slug, name, description FROM capability...)
        [
            {
                "id": "agent_spec:002",
                "objective": "Cache API responses",
                "status": "draft",
                "source": "idea",
            }
        ],  # CREATE agent_spec
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.spec_generator.get_llm") as MockLLM,
        patch("core.engine.product.spec_generator.ProductMap") as MockPM,
        patch("core.engine.product.spec_generator.create_decision", new_callable=AsyncMock) as mock_create_decision,
        patch("core.engine.graph.edge_writer.create_edge", new_callable=AsyncMock),
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.complete_json = AsyncMock(return_value=LLM_SPEC)
        MockLLM.return_value = mock_llm_instance

        mock_pm_instance = MagicMock()
        mock_pm_instance.get_capability = AsyncMock(return_value=None)
        MockPM.return_value = mock_pm_instance

        mock_create_decision.return_value = FAKE_DECISION_RECORD

        from core.engine.product.spec_generator import SpecGenerator

        gen = SpecGenerator(pool)
        result = await gen.from_idea(idea, "product:test")

    # Spec still returned successfully
    assert isinstance(result, dict)
    assert "error" not in result

    # create_decision was called once
    mock_create_decision.assert_called_once()
    call_kwargs = mock_create_decision.call_args[1]
    assert call_kwargs["decision_type"] == "architecture"
    assert call_kwargs["source"] == "spec_generator"
    assert call_kwargs["product_id"] == "product:test"


# ---------------------------------------------------------------------------
# Test 3: decision hook failure does not break spec generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_hook_failure_doesnt_break_spec():
    """If create_decision raises, from_gap still returns the spec successfully."""
    db = _make_db(
        [],  # _load_practices (SELECT insight...)
        [],  # _load_tech_context (SELECT path, language FROM graph_file...)
        [{"id": "capability:auth", "slug": "auth"}],  # capability lookup in _persist_spec
        [FAKE_SPEC_RECORD],  # CREATE agent_spec
        [],  # addresses edge query (no cq found — best-effort)
    )
    pool = _make_pool(db)

    with (
        patch("core.engine.product.spec_generator.get_llm") as MockLLM,
        patch("core.engine.product.spec_generator.ProductMap") as MockPM,
        patch(
            "core.engine.product.spec_generator.create_decision",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ),
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
            "gaps": ["No rate limiting"],
            "evidence": ["auth.py reviewed"],
        }

        # Must not raise despite create_decision failing
        result = await gen.from_gap(gap, "auth", "product:test")

    assert isinstance(result, dict)
    assert "error" not in result
    assert result.get("id") == "agent_spec:001"
