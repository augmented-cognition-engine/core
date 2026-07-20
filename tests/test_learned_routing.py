# tests/test_learned_routing.py
"""Phase 1 #2 — learned model-tier routing (wire the dormant escalation signal).

CascadeRouter already tracks how often each task_type escalates from a cheap tier
to a more expensive one, and its docstring states the rule ("if >30% escalate,
reassign to the higher model") — but nothing implemented it, and the counts were
in-process only. This wires the loop:

  * cascade_router.persist_escalation_counts / load_escalation_counts make the
    counts durable across restarts (table: routing_perf).
  * model_config.refresh_learned_routing seeds an in-memory cache from that table.
  * route_model reads the cache synchronously and up-routes (one tier) any task
    that has chronically escalated. Up-route only — never auto-downgrade.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.engine.runtime import model_config
from core.engine.runtime.model_config import (
    MIN_ROUTING_SAMPLES,
    REASSIGN_ESCALATION_RATE,
    refresh_learned_routing,
    route_model,
)


@pytest.fixture(autouse=True)
def _clean_routing_cache():
    """Isolate the module-level learned-routing cache between tests."""
    saved = dict(model_config._LEARNED_ROUTING)
    model_config._LEARNED_ROUTING.clear()
    yield
    model_config._LEARNED_ROUTING.clear()
    model_config._LEARNED_ROUTING.update(saved)


# --- sanity: constants are sane ------------------------------------------------


def test_constants_match_documented_rule():
    assert MIN_ROUTING_SAMPLES == 5
    assert REASSIGN_ESCALATION_RATE == pytest.approx(0.3)


# --- the up-route blend (pure / synchronous) -----------------------------------


def test_empty_cache_is_pure_static():
    # code_analysis is statically routed to haiku
    assert route_model("code_analysis") == model_config.MODEL_TIERS["haiku"]


def test_chronic_escalation_uproutes_one_tier():
    """>= MIN_SAMPLES observations and >= REASSIGN_RATE escalation → start one tier up."""
    model_config._LEARNED_ROUTING["code_analysis"] = (0.5, 10)  # 50% escalation over 10 calls
    assert route_model("code_analysis") == model_config.MODEL_TIERS["sonnet"]


def test_no_uproute_below_sample_floor():
    model_config._LEARNED_ROUTING["code_analysis"] = (0.9, 3)  # n=3 < 5
    assert route_model("code_analysis") == model_config.MODEL_TIERS["haiku"]


def test_no_uproute_below_rate_threshold():
    model_config._LEARNED_ROUTING["code_analysis"] = (0.2, 50)  # rate 0.2 < 0.3
    assert route_model("code_analysis") == model_config.MODEL_TIERS["haiku"]


def test_uproute_still_respects_ceiling():
    """Up-route cannot exceed the caller's ceiling."""
    model_config._LEARNED_ROUTING["code_analysis"] = (0.9, 20)
    assert route_model("code_analysis", ceiling="haiku") == model_config.MODEL_TIERS["haiku"]


def test_uproute_can_reach_opus_when_ceiling_allows():
    """A sonnet task that chronically escalates → opus, but only with ceiling=opus."""
    model_config._LEARNED_ROUTING["implementation"] = (0.8, 20)  # implementation is static sonnet
    assert route_model("implementation", ceiling="opus") == model_config.MODEL_TIERS["opus"]
    # default ceiling (sonnet) keeps it at sonnet
    assert route_model("implementation") == model_config.MODEL_TIERS["sonnet"]


def test_learned_can_be_disabled():
    model_config._LEARNED_ROUTING["code_analysis"] = (0.9, 20)
    assert route_model("code_analysis", learned=False) == model_config.MODEL_TIERS["haiku"]


def test_classifier_bump_then_learned_then_ceiling():
    """Combined path: 2 opus signals → opus, learned no-ops on already-opus,
    default ceiling caps to sonnet; ceiling=opus lets it through."""
    model_config._LEARNED_ROUTING["code_analysis"] = (0.9, 20)
    cls = {"complexity": "complex", "archetype": "researcher"}  # 2 opus signals
    assert route_model("code_analysis", classification=cls) == model_config.MODEL_TIERS["sonnet"]
    assert route_model("code_analysis", classification=cls, ceiling="opus") == model_config.MODEL_TIERS["opus"]


def test_unknown_tier_is_not_promoted():
    assert model_config._up_tier("mystery") == "mystery"


# --- cascade start tier also applies the learned bump (issue #5) ----------------


def test_cascade_start_tier_applies_learned_uproute():
    from core.engine.intelligence.cascade_router import resolve_start_tier

    model_config._LEARNED_ROUTING["code_analysis"] = (0.5, 10)  # static haiku → up to sonnet
    assert resolve_start_tier("code_analysis", None, "sonnet") == "sonnet"


def test_cascade_start_tier_respects_ceiling():
    from core.engine.intelligence.cascade_router import resolve_start_tier

    model_config._LEARNED_ROUTING["code_analysis"] = (0.9, 20)
    assert resolve_start_tier("code_analysis", None, "haiku") == "haiku"


def test_cascade_start_tier_pure_static_without_learned():
    from core.engine.intelligence.cascade_router import resolve_start_tier

    assert resolve_start_tier("code_analysis", None, "sonnet") == "haiku"


# --- refresh_learned_routing (DB → cache) --------------------------------------


@pytest.mark.asyncio
async def test_refresh_populates_cache_from_routing_perf():
    async def fake_query(sql, params=None):
        return [
            [
                {"task_type": "code_analysis", "total": 10, "escalated": 5},
                {"task_type": "zero_task", "total": 0, "escalated": 0},  # skipped (no samples)
            ]
        ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    loaded = await refresh_learned_routing("product:test", db=mock_db)

    assert loaded == 1
    assert model_config._LEARNED_ROUTING["code_analysis"] == (0.5, 10)
    assert "zero_task" not in model_config._LEARNED_ROUTING


@pytest.mark.asyncio
async def test_refresh_is_non_fatal_on_db_error():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("boom"))
    model_config._LEARNED_ROUTING["preexisting"] = (0.4, 9)

    loaded = await refresh_learned_routing("product:test", db=mock_db)

    assert loaded == 0
    # cache left intact on failure
    assert model_config._LEARNED_ROUTING["preexisting"] == (0.4, 9)


# --- cascade_router persist / load (in-process counts <-> routing_perf) ---------


@pytest.fixture
def _clean_escalation_counts():
    from core.engine.intelligence import cascade_router

    saved = dict(cascade_router._escalation_counts)
    cascade_router._escalation_counts.clear()
    yield cascade_router
    cascade_router._escalation_counts.clear()
    cascade_router._escalation_counts.update(saved)


@pytest.mark.asyncio
async def test_persist_upserts_one_row_per_task(_clean_escalation_counts):
    cr = _clean_escalation_counts
    cr._escalation_counts["code_analysis"] = {"total": 10, "escalated": 4}

    captured: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        captured.append((sql, params or {}))
        return [[{}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await cr.persist_escalation_counts("product:test", db=mock_db)

    assert len(captured) == 1
    _sql, params = captured[0]
    assert params["task_type"] == "code_analysis"
    assert params["total"] == 10
    assert params["escalated"] == 4
    assert params["product"] == "product:test"


@pytest.mark.asyncio
async def test_persist_noop_when_no_counts(_clean_escalation_counts):
    cr = _clean_escalation_counts
    mock_db = AsyncMock()
    mock_db.query = AsyncMock()

    await cr.persist_escalation_counts("product:test", db=mock_db)

    mock_db.query.assert_not_called()


@pytest.mark.asyncio
async def test_persist_is_non_fatal_on_db_error(_clean_escalation_counts):
    cr = _clean_escalation_counts
    cr._escalation_counts["code_analysis"] = {"total": 3, "escalated": 1}
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("boom"))

    # must not raise
    await cr.persist_escalation_counts("product:test", db=mock_db)


@pytest.mark.asyncio
async def test_load_seeds_escalation_counts(_clean_escalation_counts):
    cr = _clean_escalation_counts

    async def fake_query(sql, params=None):
        return [[{"task_type": "code_analysis", "total": 8, "escalated": 3}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    loaded = await cr.load_escalation_counts("product:test", db=mock_db)

    assert loaded == 1
    assert cr._escalation_counts["code_analysis"] == {"total": 8, "escalated": 3}
    # and the in-process escalation rate is now derivable
    assert cr.get_escalation_rates()["code_analysis"] == pytest.approx(3 / 8)


@pytest.mark.asyncio
async def test_load_is_non_fatal_on_db_error(_clean_escalation_counts):
    cr = _clean_escalation_counts
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("boom"))

    loaded = await cr.load_escalation_counts("product:test", db=mock_db)
    assert loaded == 0


# --- runtime lifecycle wiring (warm on first turn, flush on close) -------------


@pytest.mark.asyncio
async def test_runtime_warm_is_idempotent(monkeypatch):
    """_warm_learned_routing seeds counts + cache exactly once per runtime."""
    from core.engine.runtime.runtime import Runtime

    rt = Runtime.__new__(Runtime)  # skip heavy __init__; exercise the method in isolation
    rt._routing_warmed = False
    rt._product_id = "product:test"

    calls = {"load": 0, "refresh": 0}

    async def fake_load(pid, db=None):
        calls["load"] += 1
        return 0

    async def fake_refresh(pid, db=None):
        calls["refresh"] += 1
        return 0

    monkeypatch.setattr("core.engine.intelligence.cascade_router.load_escalation_counts", fake_load)
    monkeypatch.setattr("core.engine.runtime.model_config.refresh_learned_routing", fake_refresh)

    await rt._warm_learned_routing()
    await rt._warm_learned_routing()  # second call is a no-op

    assert calls == {"load": 1, "refresh": 1}


@pytest.mark.asyncio
async def test_runtime_warm_is_fail_safe(monkeypatch):
    """A warm failure must not propagate (routing degrades to the static table)."""
    from core.engine.runtime.runtime import Runtime

    rt = Runtime.__new__(Runtime)
    rt._routing_warmed = False
    rt._product_id = "product:test"

    async def boom(pid, db=None):
        raise RuntimeError("db down")

    monkeypatch.setattr("core.engine.intelligence.cascade_router.load_escalation_counts", boom)

    await rt._warm_learned_routing()  # must not raise


@pytest.mark.asyncio
async def test_runtime_close_flushes_escalation_counts(monkeypatch):
    """close() persists the escalation counts so learning survives the session."""
    from core.engine.runtime.runtime import Runtime

    rt = Runtime.__new__(Runtime)
    rt._product_id = "product:test"
    rt._session_memory = None

    class _Registry:
        _tools: dict = {}

    rt._registry = _Registry()

    persisted = {"n": 0, "pid": None}

    async def fake_persist(pid, db=None):
        persisted["n"] += 1
        persisted["pid"] = pid

    monkeypatch.setattr("core.engine.intelligence.cascade_router.persist_escalation_counts", fake_persist)

    await rt.close()

    assert persisted["n"] == 1
    assert persisted["pid"] == "product:test"
