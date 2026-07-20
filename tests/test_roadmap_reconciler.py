"""Tests for the roadmap_reconciler sentinel — docs->graph sync + drift surfacing, non-fatal."""

from __future__ import annotations

import pytest


def test_roadmap_reconciler_is_registered():
    """Importing the module fires @register_engine — the engine must be discoverable by the scheduler."""
    import core.engine.sentinel.engines.roadmap_reconciler  # noqa: F401
    from core.engine.sentinel.registry import get_engine

    eng = get_engine("roadmap_reconciler")
    assert eng is not None, "roadmap_reconciler not registered"


def test_roadmap_reconciler_wired_into_scheduler_startup():
    """Registration is necessary but NOT sufficient: scheduler.start() builds cron jobs from
    engine_registry, populated ONLY by the explicit import block in api/main.py (pkgutil discovery
    is lazy/post-start). Guard that our engine is imported there, or it registers but never fires."""
    import pathlib

    main_src = pathlib.Path("core/engine/api/main.py").read_text()
    assert "engines.roadmap_reconciler" in main_src, (
        "roadmap_reconciler is not imported in api/main.py lifespan — it will register but never be "
        "scheduled (the registered-but-unreachable orphan class)"
    )


@pytest.mark.asyncio
async def test_roadmap_reconciler_run_returns_synced_and_drift(monkeypatch):
    import core.engine.sentinel.engines.roadmap_reconciler as rr

    async def fake_seed(product_id, pool=None):
        return {"phases": 6, "specs": 3, "decisions": 0, "supersedes": 0}

    async def fake_drift(product_id, pool=None):
        return {"total": 35, "by_status": {"shipped": 17}, "open_for_review": 18}

    # run() does a lazy `from ... import seed_session_strategy`, so patch the source module attr
    monkeypatch.setattr("core.engine.product.strategy_ingest.seed_session_strategy", fake_seed)
    monkeypatch.setattr(rr, "_drift_summary", fake_drift)

    out = await rr.run("product:platform")
    assert out["synced"]["specs"] == 3
    assert out["drift"]["open_for_review"] == 18


@pytest.mark.asyncio
async def test_roadmap_reconciler_non_fatal(monkeypatch):
    """A sync or drift failure must not crash the scheduler — degrade to empties."""
    import core.engine.sentinel.engines.roadmap_reconciler as rr

    async def boom(*a, **k):
        raise RuntimeError("graph down")

    monkeypatch.setattr("core.engine.product.strategy_ingest.seed_session_strategy", boom)
    monkeypatch.setattr(rr, "_drift_summary", boom)

    out = await rr.run("product:platform")
    assert out == {"synced": {}, "drift": {}}


@pytest.mark.asyncio
async def test_drift_summary_groups_by_status():
    import core.engine.sentinel.engines.roadmap_reconciler as rr

    class _DB:
        async def query(self, q, params=None):
            return [
                {"status": "shipped"},
                {"status": "shipped"},
                {"status": "draft"},
                {"status": "approved"},
                {"status": "draft"},
            ]

    class _Pool:
        def connection(self):
            class Ctx:
                async def __aenter__(self):
                    return _DB()

                async def __aexit__(self, *a):
                    return False

            return Ctx()

    out = await rr._drift_summary("product:platform", pool=_Pool())
    assert out["total"] == 5
    assert out["by_status"]["shipped"] == 2
    assert out["open_for_review"] == 3  # 2 draft + 1 approved
