# tests/test_product_conversation.py
"""Tests for ProductConversation — intent detection and routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_pool(mock_db):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.connection.return_value = cm
    return pool


@pytest.fixture
def conversation(mock_pool):
    from core.engine.product.conversation import ProductConversation

    return ProductConversation(mock_pool)


# ---------------------------------------------------------------------------
# detect_intent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_intent_health(conversation):
    """'how's the product?' → intent='health'"""
    result = await conversation.detect_intent("how's the product?")
    assert result is not None
    assert result["intent"] == "health"


@pytest.mark.asyncio
async def test_detect_intent_health_variant(conversation):
    """'product health' → intent='health'"""
    result = await conversation.detect_intent("product health")
    assert result is not None
    assert result["intent"] == "health"


@pytest.mark.asyncio
async def test_detect_intent_gaps(conversation):
    """'show me my gaps' → intent='gaps'"""
    result = await conversation.detect_intent("show me my gaps")
    assert result is not None
    assert result["intent"] == "gaps"


@pytest.mark.asyncio
async def test_detect_intent_gaps_variant(conversation):
    """'what are my gaps?' → intent='gaps'"""
    result = await conversation.detect_intent("what are my gaps?")
    assert result is not None
    assert result["intent"] == "gaps"


@pytest.mark.asyncio
async def test_detect_intent_prioritize(conversation):
    """'what should I work on?' → intent='prioritize'"""
    result = await conversation.detect_intent("what should I work on?")
    assert result is not None
    assert result["intent"] == "prioritize"


@pytest.mark.asyncio
async def test_detect_intent_prioritize_variant(conversation):
    """'what to work on' → intent='prioritize'"""
    result = await conversation.detect_intent("what to work on")
    assert result is not None
    assert result["intent"] == "prioritize"


@pytest.mark.asyncio
async def test_detect_intent_capability(conversation):
    """'state of authentication' → intent='capability_detail', params.query='authentication'"""
    result = await conversation.detect_intent("state of authentication")
    assert result is not None
    assert result["intent"] == "capability_detail"
    assert result["params"]["query"] == "authentication"


@pytest.mark.asyncio
async def test_detect_intent_capability_show(conversation):
    """'show me payments' → intent='capability_detail'"""
    result = await conversation.detect_intent("show me payments")
    assert result is not None
    assert result["intent"] == "capability_detail"
    assert result["params"]["query"] == "payments"


@pytest.mark.asyncio
async def test_detect_intent_scan(conversation):
    """'scan my repo' → intent='scan'"""
    result = await conversation.detect_intent("scan my repo")
    assert result is not None
    assert result["intent"] == "scan"


@pytest.mark.asyncio
async def test_detect_intent_set_direction(conversation):
    """'set direction to focus on enterprise' → intent='set_direction'"""
    result = await conversation.detect_intent("set direction to focus on enterprise")
    assert result is not None
    assert result["intent"] == "set_direction"
    assert "enterprise" in result["params"]["query"]


@pytest.mark.asyncio
async def test_detect_intent_generate_spec(conversation):
    """'generate spec for user notifications' → intent='generate_spec'"""
    result = await conversation.detect_intent("generate spec for user notifications")
    assert result is not None
    assert result["intent"] == "generate_spec"
    assert "user notifications" in result["params"]["query"]


@pytest.mark.asyncio
async def test_detect_no_intent(conversation):
    """'hello' → None (no product intent)"""
    result = await conversation.detect_intent("hello")
    assert result is None


@pytest.mark.asyncio
async def test_detect_no_intent_general(conversation):
    """'how are you doing today?' → None"""
    result = await conversation.detect_intent("how are you doing today?")
    assert result is None


# ---------------------------------------------------------------------------
# handle_product_intent — health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_health_intent(conversation, mock_pool):
    """Mock DB, verify structured response with health data."""
    fake_health = {
        "total_capabilities": 5,
        "dimensions": {
            "security": {"avg_score": 0.3, "count": 3},
            "performance": {"avg_score": 0.5, "count": 2},
            "reliability": {"avg_score": 0.7, "count": 4},
        },
    }
    with patch.object(
        conversation._product_map,
        "health_summary",
        new=AsyncMock(return_value=fake_health),
    ):
        result = await conversation.handle_product_intent({"intent": "health", "params": {}}, "product:test")

    assert result["handled"] is True
    assert "5" in result["response"]
    assert "security" in result["response"]
    assert result["data"] == fake_health


# ---------------------------------------------------------------------------
# handle_product_intent — gaps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_gaps_intent(conversation, mock_db):
    """Mock DB gaps query, verify count and summary in response."""
    fake_gaps = [
        {"dimension": "security", "score": 0.2},
        {"dimension": "testing", "score": 0.35},
        {"dimension": "docs", "score": 0.38},
        {"dimension": "observability", "score": 0.39},
    ]
    mock_db.query = AsyncMock(return_value=fake_gaps)

    result = await conversation.handle_product_intent({"intent": "gaps", "params": {}}, "product:test")

    assert result["handled"] is True
    assert "4" in result["response"]
    assert result["data"]["count"] == 4


# ---------------------------------------------------------------------------
# handle_product_intent — prioritize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_prioritize_intent(conversation):
    """Mock ProductPrioritizer, verify top recommendations in response."""
    fake_recs = [
        {"capability_slug": "auth", "dimension": "security", "current_score": 0.2},
        {"capability_slug": "billing", "dimension": "reliability", "current_score": 0.3},
    ]
    with patch("core.engine.product.conversation.ProductPrioritizer") as MockPrioritizer:
        instance = MockPrioritizer.return_value
        instance.prioritize = AsyncMock(return_value=fake_recs)

        result = await conversation.handle_product_intent({"intent": "prioritize", "params": {}}, "product:test")

    assert result["handled"] is True
    assert "2" in result["response"]
    assert "auth" in result["response"]
    assert result["data"]["recommendations"] == fake_recs


# ---------------------------------------------------------------------------
# handle_product_intent — capability_detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_capability_detail_found(conversation):
    """Mock get_capability returning a record, verify response includes name."""
    fake_cap = {
        "name": "Authentication",
        "status": "built",
        "description": "User login and session management.",
        "quality": {"security": {"score": 0.9}},
    }
    with patch.object(
        conversation._product_map,
        "get_capability",
        new=AsyncMock(return_value=fake_cap),
    ):
        result = await conversation.handle_product_intent(
            {"intent": "capability_detail", "params": {"query": "authentication"}},
            "product:test",
        )

    assert result["handled"] is True
    assert "Authentication" in result["response"]
    assert "built" in result["response"]


@pytest.mark.asyncio
async def test_handle_capability_detail_not_found(conversation):
    """get_capability returns None → falls through to orchestration (handled=False)."""
    with patch.object(
        conversation._product_map,
        "get_capability",
        new=AsyncMock(return_value=None),
    ):
        result = await conversation.handle_product_intent(
            {"intent": "capability_detail", "params": {"query": "unknown_thing"}},
            "product:test",
        )

    assert result["handled"] is False


# ---------------------------------------------------------------------------
# handle_product_intent — set_direction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_set_direction(conversation):
    """Mock set_vision, verify direction text echoed in response."""
    fake_result = {"id": "product_vision:1", "name": "focus on enterprise"}
    with patch.object(
        conversation._product_map,
        "set_vision",
        new=AsyncMock(return_value=fake_result),
    ):
        result = await conversation.handle_product_intent(
            {"intent": "set_direction", "params": {"query": "focus on enterprise"}},
            "product:test",
        )

    assert result["handled"] is True
    assert "focus on enterprise" in result["response"]


# ---------------------------------------------------------------------------
# handle_product_intent — scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_scan_intent(conversation):
    """Scan intent returns handled response with action key."""
    result = await conversation.handle_product_intent({"intent": "scan", "params": {}}, "product:test")
    assert result["handled"] is True
    assert result["data"]["action"] == "scan_requested"


# ---------------------------------------------------------------------------
# handle_product_intent — generate_spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_generate_spec_intent(conversation):
    """generate_spec intent echoes description in response."""
    result = await conversation.handle_product_intent(
        {"intent": "generate_spec", "params": {"query": "payment webhooks"}},
        "product:test",
    )
    assert result["handled"] is True
    assert "payment webhooks" in result["response"]
    assert result["data"]["action"] == "spec_requested"


@pytest.mark.asyncio
async def test_handle_generate_spec_returns_artifact_fields(conversation):
    """generate_spec response includes artifact_id and artifact_type for produced edge creation."""
    result = await conversation.handle_product_intent(
        {"intent": "generate_spec", "params": {"query": "user notifications"}},
        "product:test",
    )
    assert result["handled"] is True
    assert "artifact_type" in result
    assert result["artifact_type"] == "agent_spec"
    # artifact_id is None for the stub (no actual spec created yet)
    assert "artifact_id" in result


# ---------------------------------------------------------------------------
# handle_product_intent — unknown falls through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_unknown_intent_not_handled(conversation):
    """Unknown intent returns handled=False."""
    result = await conversation.handle_product_intent({"intent": "unknown_xyz", "params": {}}, "product:test")
    assert result["handled"] is False
