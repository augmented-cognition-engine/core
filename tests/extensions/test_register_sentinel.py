"""register_sentinel — extensions contribute 24/7 sentinel engines.

Delegation contract: the syscall writes into the SAME engine_registry the
kernel's own engines use (mirroring how register_instrument delegates to
instrument_registry), so extension sentinels appear in list_engines(), honor
schedule overrides, and need no separate consume path.
"""

from __future__ import annotations

import pytest

from core.engine.extensions.registry import Registry
from core.engine.sentinel.registry import engine_registry, get_engine


@pytest.fixture
def _clean_engine(request):
    """Remove the test engine from the global registry after the test."""
    name = "test_extension_sentinel"
    yield name
    engine_registry.pop(name, None)


@pytest.mark.unit
def test_register_sentinel_lands_in_engine_registry(_clean_engine):
    async def run_test_sentinel(product_id: str = "product:platform") -> dict:
        return {"ok": True, "product": product_id}

    reg = Registry()
    reg.register_sentinel(
        _clean_engine,
        cron="0 6 * * *",
        description="test sentinel from an extension",
        fn=run_test_sentinel,
    )

    entry = get_engine(_clean_engine)
    assert entry is not None
    assert entry["cron"] == "0 6 * * *"
    assert entry["fn"] is run_test_sentinel
    assert entry["trigger"] is None


@pytest.mark.unit
def test_register_sentinel_duplicate_name_raises(_clean_engine):
    async def run_a(product_id: str = "product:platform") -> dict:
        return {}

    async def run_b(product_id: str = "product:platform") -> dict:
        return {}

    reg = Registry()
    reg.register_sentinel(_clean_engine, cron="0 6 * * *", description="a", fn=run_a)
    with pytest.raises(ValueError):
        reg.register_sentinel(_clean_engine, cron="0 7 * * *", description="b", fn=run_b)


@pytest.mark.unit
def test_register_sentinel_stores_trigger_predicate(_clean_engine):
    async def run_watched(product_id: str = "product:platform") -> dict:
        return {}

    async def only_when_changed(product_id: str) -> bool:
        return True

    reg = Registry()
    reg.register_sentinel(
        _clean_engine,
        cron="0 6 * * *",
        description="sentinel with a meaningful-change trigger",
        fn=run_watched,
        trigger=only_when_changed,
    )

    entry = get_engine(_clean_engine)
    assert entry is not None
    assert entry["trigger"] is only_when_changed


@pytest.mark.unit
async def test_scheduler_start_ensures_extensions_loaded(monkeypatch):
    """start() must trigger extension discovery so extension sentinels get scheduled."""
    from core.engine.sentinel.scheduler import SentinelScheduler

    calls: list[bool] = []

    import core.engine.extensions.loader as loader

    monkeypatch.setattr(loader, "ensure_loaded", lambda: calls.append(True))

    scheduler = SentinelScheduler(db_pool=None)
    scheduler.start(overrides={})
    try:
        assert calls == [True]
    finally:
        scheduler._scheduler.shutdown(wait=False)
