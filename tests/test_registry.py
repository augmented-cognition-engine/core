# tests/test_registry.py
import pytest


def test_register_engine_adds_to_registry():
    """Decorating a function with @register_engine adds it to the registry dict."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="test_engine", cron="0 3 * * *", description="A test engine")
    async def run(product_id: str) -> dict:
        return {"tested": True}

    assert "test_engine" in engine_registry
    entry = engine_registry["test_engine"]
    assert entry["cron"] == "0 3 * * *"
    assert entry["description"] == "A test engine"
    assert callable(entry["fn"])


def test_register_engine_duplicate_raises():
    """Registering the same engine name twice raises ValueError."""
    from core.engine.sentinel.registry import engine_registry, register_engine

    engine_registry.clear()

    @register_engine(name="dupe", cron="0 1 * * *", description="First")
    async def run_a(product_id: str) -> dict:
        return {}

    with pytest.raises(ValueError, match="already registered"):

        @register_engine(name="dupe", cron="0 2 * * *", description="Second")
        async def run_b(product_id: str) -> dict:
            return {}


def test_get_engine_returns_entry():
    """get_engine returns the registered entry by name."""
    from core.engine.sentinel.registry import engine_registry, get_engine, register_engine

    engine_registry.clear()

    @register_engine(name="lookup_test", cron="0 4 * * *", description="Lookup")
    async def run(product_id: str) -> dict:
        return {}

    entry = get_engine("lookup_test")
    assert entry is not None
    assert entry["description"] == "Lookup"


def test_get_engine_missing_returns_none():
    """get_engine returns None for unregistered engine name."""
    from core.engine.sentinel.registry import engine_registry, get_engine

    engine_registry.clear()
    assert get_engine("nonexistent") is None


def test_list_engines_returns_all():
    """list_engines returns metadata for all registered engines."""
    from core.engine.sentinel.registry import engine_registry, list_engines, register_engine

    engine_registry.clear()

    @register_engine(name="eng_a", cron="0 1 * * *", description="Alpha")
    async def run_a(product_id: str) -> dict:
        return {}

    @register_engine(name="eng_b", cron="0 2 * * *", description="Beta")
    async def run_b(product_id: str) -> dict:
        return {}

    engines = list_engines()
    assert len(engines) == 2
    names = {e["name"] for e in engines}
    assert names == {"eng_a", "eng_b"}
