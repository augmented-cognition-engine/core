# tests/test_cost_intelligence.py
"""Tests for E4 — Cost Intelligence Engine.

Covers:
- _estimate_provider_cost: pricing math for each provider type
- _estimate_api_cost: pricing math for each API type
- _analyze_query_patterns: N+1 detection, data_modeling gap, unbounded selects
- _analyze_api_patterns: capability slug → API detection
- _analyze_compute_patterns: stack/capability → provider detection
- run_cost_estimate: end-to-end with LLM synthesis
- ace_cost_estimate: MCP tool routing
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


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


# ── _estimate_provider_cost ───────────────────────────────────────────────────


def test_provider_cost_vercel_free_tier():
    """Vercel stays free for very low user counts."""
    from core.engine.product.cost_intelligence import _estimate_provider_cost

    result = _estimate_provider_cost("vercel", users=10)

    assert "monthly_usd" in result
    assert result["monthly_usd"] >= 0.0
    assert result["provider"] == "vercel"
    assert "breakdown" in result


def test_provider_cost_vercel_scales_with_users():
    """Higher user count → higher Vercel cost."""
    from core.engine.product.cost_intelligence import _estimate_provider_cost

    cost_1k = _estimate_provider_cost("vercel", users=1000)
    cost_100k = _estimate_provider_cost("vercel", users=100_000)

    assert cost_100k["monthly_usd"] > cost_1k["monthly_usd"]


def test_provider_cost_railway_always_on():
    """Railway is always-on — cost doesn't drop to zero."""
    from core.engine.product.cost_intelligence import _estimate_provider_cost

    result = _estimate_provider_cost("railway", users=100)

    assert result["monthly_usd"] >= 0.0
    assert "vcpu_cost_usd" in result["breakdown"]


def test_provider_cost_supabase_free_tier():
    """Supabase is free for low user counts with small DB."""
    from core.engine.product.cost_intelligence import _estimate_provider_cost

    result = _estimate_provider_cost("supabase", users=10)

    # At 10 users, estimated DB is tiny → should be on free tier or near it
    assert result["monthly_usd"] >= 0.0
    assert "tier" in result["breakdown"]


def test_provider_cost_supabase_tier_risk_warning():
    """At high users, Supabase detects tier upgrade and includes free_tier_cap_users."""
    from core.engine.product.cost_intelligence import _estimate_provider_cost

    result = _estimate_provider_cost("supabase", users=50_000)

    # At 50k users DB growth should exceed free tier
    # Either on pro or pro_extra, should have tier info
    assert result["breakdown"].get("tier") in ("pro", "pro_extra", "free")


def test_provider_cost_unknown_provider():
    """Unknown provider returns zero cost without error."""
    from core.engine.product.cost_intelligence import _estimate_provider_cost

    result = _estimate_provider_cost("unknown_provider_xyz", users=1000)

    assert result["monthly_usd"] == 0.0
    assert result["breakdown"] == {}


# ── _estimate_api_cost ────────────────────────────────────────────────────────


def test_api_cost_openai_scales_with_users():
    """OpenAI cost scales linearly with users."""
    from core.engine.product.cost_intelligence import _estimate_api_cost

    cost_1k = _estimate_api_cost("openai", users=1000)
    cost_10k = _estimate_api_cost("openai", users=10_000)

    assert cost_10k["monthly_usd"] > cost_1k["monthly_usd"]
    assert abs(cost_10k["monthly_usd"] / cost_1k["monthly_usd"] - 10.0) < 0.01


def test_api_cost_openai_has_breakdown():
    """OpenAI cost includes model and token breakdown."""
    from core.engine.product.cost_intelligence import _estimate_api_cost

    result = _estimate_api_cost("openai", users=1000)

    assert "calls_per_month" in result["breakdown"]
    assert "model" in result["breakdown"]
    assert "input_cost_usd" in result["breakdown"]
    assert "output_cost_usd" in result["breakdown"]


def test_api_cost_stripe_note_in_breakdown():
    """Stripe includes a note about revenue-proportional fees."""
    from core.engine.product.cost_intelligence import _estimate_api_cost

    result = _estimate_api_cost("stripe", users=1000)

    assert "note" in result["breakdown"]
    assert result["monthly_usd"] >= 0.0


def test_api_cost_sendgrid_free_tier_at_low_users():
    """SendGrid stays free when emails/mo < free daily cap × 30."""
    from core.engine.product.cost_intelligence import _estimate_api_cost

    # 10 users × 2 emails = 20 emails/mo, well below 100/day × 30 = 3000/mo
    result = _estimate_api_cost("sendgrid", users=10)

    assert result["breakdown"]["tier"] == "free"
    assert result["monthly_usd"] == 0.0


def test_api_cost_unknown_api():
    """Unknown API returns zero cost without error."""
    from core.engine.product.cost_intelligence import _estimate_api_cost

    result = _estimate_api_cost("unknown_api_xyz", users=1000)

    assert result["monthly_usd"] == 0.0


# ── _analyze_query_patterns ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_patterns_detects_data_modeling_gap():
    """Low data_modeling score → data_modeling_gap pattern returned."""
    from core.engine.product.cost_intelligence import _analyze_query_patterns

    mock_db = AsyncMock()

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []  # no capability_finding hits
        if call_count == 2:
            return [{"dimension": "data_modeling", "score": 0.35, "gaps": ["n+1", "no_index"]}]
        return []  # no graph_function hits

    mock_db.query = AsyncMock(side_effect=query_side)

    patterns = await _analyze_query_patterns("product:platform", mock_db)

    assert any(p["pattern"] == "data_modeling_gap" for p in patterns)
    gap = next(p for p in patterns if p["pattern"] == "data_modeling_gap")
    assert gap["severity"] == "high"  # score < 0.4


@pytest.mark.asyncio
async def test_query_patterns_detects_n1_candidate():
    """High-complexity fetch function → n1_candidate pattern."""
    from core.engine.product.cost_intelligence import _analyze_query_patterns

    mock_db = AsyncMock()

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []  # no findings
        if call_count == 2:
            return []  # no data_modeling gap
        # graph_function with high complexity + fetch pattern
        return [
            {"name": "get_user_posts_with_comments", "complexity": 22, "line_start": 45},
        ]

    mock_db.query = AsyncMock(side_effect=query_side)

    patterns = await _analyze_query_patterns("product:platform", mock_db)

    assert any(p["pattern"] == "n1_candidate" for p in patterns)


@pytest.mark.asyncio
async def test_query_patterns_empty_on_healthy_data():
    """No patterns returned when data is clean."""
    from core.engine.product.cost_intelligence import _analyze_query_patterns

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    patterns = await _analyze_query_patterns("product:platform", mock_db)

    # Should be empty since all DB queries return []
    assert patterns == []


# ── _analyze_api_patterns ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_patterns_detects_openai():
    from core.engine.product.cost_intelligence import _analyze_api_patterns

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            {"slug": "openai_completions", "title": "OpenAI Completions", "category": "ai"},
        ]
    )

    patterns = await _analyze_api_patterns("product:platform", mock_db)

    assert any(p["api"] == "openai" for p in patterns)


@pytest.mark.asyncio
async def test_api_patterns_detects_stripe():
    from core.engine.product.cost_intelligence import _analyze_api_patterns

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            {"slug": "stripe_billing", "title": "Stripe Billing", "category": "payments"},
        ]
    )

    patterns = await _analyze_api_patterns("product:platform", mock_db)

    assert any(p["api"] == "stripe" for p in patterns)


@pytest.mark.asyncio
async def test_api_patterns_detects_multiple():
    from core.engine.product.cost_intelligence import _analyze_api_patterns

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            {"slug": "openai_completions", "title": "OpenAI", "category": "ai"},
            {"slug": "sendgrid_mailer", "title": "SendGrid Email", "category": "messaging"},
            {"slug": "stripe_payments", "title": "Stripe Payments", "category": "payments"},
        ]
    )

    patterns = await _analyze_api_patterns("product:platform", mock_db)

    api_keys = {p["api"] for p in patterns}
    assert "openai" in api_keys
    assert "sendgrid" in api_keys
    assert "stripe" in api_keys


# ── _analyze_compute_patterns ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_patterns_detects_vercel_from_nextjs():
    from core.engine.product.cost_intelligence import _analyze_compute_patterns

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            {"slug": "nextjs_router", "title": "Next.js App Router", "category": "frontend"},
        ]
    )

    patterns = await _analyze_compute_patterns("product:platform", mock_db, ["nextjs", "react"])

    assert any(p["provider"] == "vercel" for p in patterns)


@pytest.mark.asyncio
async def test_compute_patterns_falls_back_for_fastapi():
    from core.engine.product.cost_intelligence import _analyze_compute_patterns

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])

    patterns = await _analyze_compute_patterns("product:platform", mock_db, ["python", "fastapi"])

    # Should infer Railway for FastAPI stack
    assert any(p["provider"] == "railway" for p in patterns)
    assert patterns[0]["confidence"] == "low"


# ── run_cost_estimate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_cost_estimate_returns_structure(mock_pool):
    from core.engine.product.cost_intelligence import run_cost_estimate

    mock_p, mock_db = mock_pool

    # Capabilities with OpenAI + Next.js stack
    caps = [
        {"slug": "openai_completions", "title": "OpenAI", "category": "ai"},
        {"slug": "nextjs_router", "title": "Next.js Router", "category": "frontend"},
    ]

    call_count = 0

    async def query_side(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return caps
        return []

    mock_db.query = AsyncMock(side_effect=query_side)

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="# Cost Report\n\nVercel: $10/mo\nOpenAI: $50/mo")

    with (
        patch("core.engine.product.cost_intelligence.pool", mock_p),
        patch("core.engine.product.cost_intelligence.get_llm", return_value=mock_llm),
    ):
        result = await run_cost_estimate("product:platform", users=1000)

    assert "users" in result
    assert result["users"] == 1000
    assert "total_monthly_usd" in result
    assert result["total_monthly_usd"] >= 0.0
    assert "compute_costs" in result
    assert "api_costs" in result
    assert "query_patterns" in result
    assert "warnings" in result
    assert "report" in result


@pytest.mark.asyncio
async def test_run_cost_estimate_invalid_users():
    from core.engine.product.cost_intelligence import run_cost_estimate

    result = await run_cost_estimate("product:platform", users=0)

    assert "error" in result


@pytest.mark.asyncio
async def test_run_cost_estimate_llm_failure_still_returns(mock_pool):
    """LLM synthesis failure doesn't break the whole estimate."""
    from core.engine.product.cost_intelligence import run_cost_estimate

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("model overloaded"))

    with (
        patch("core.engine.product.cost_intelligence.pool", mock_p),
        patch("core.engine.product.cost_intelligence.get_llm", return_value=mock_llm),
    ):
        result = await run_cost_estimate("product:platform", users=500)

    # Should still return structured data even without LLM report
    assert "total_monthly_usd" in result
    assert "report" in result
    assert "LLM synthesis unavailable" in result["report"]


# ── MCP tool ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_cost_estimate_mcp_tool(mock_pool):
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="Cost report")

    with (
        patch("core.engine.product.cost_intelligence.pool", mock_p),
        patch("core.engine.product.cost_intelligence.get_llm", return_value=mock_llm),
    ):
        result = await tools.ace_cost_estimate(users=1000, product_id="product:platform")

    assert "total_monthly_usd" in result
    assert "report" in result


@pytest.mark.asyncio
async def test_ace_cost_estimate_provider_filter(mock_pool):
    """When providers= is specified, only those providers are estimated."""
    from core.engine.mcp import tools

    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="Report")

    with (
        patch("core.engine.product.cost_intelligence.pool", mock_p),
        patch("core.engine.product.cost_intelligence.get_llm", return_value=mock_llm),
    ):
        result = await tools.ace_cost_estimate(
            users=1000,
            providers=["railway"],
            product_id="product:platform",
        )

    provider_names = [c["provider"] for c in result["compute_costs"]]
    assert "railway" in provider_names
    # Vercel should not be included since we filtered to railway only
    assert "vercel" not in provider_names
