from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.engine.cognition import instrument_registry
from core.engine.extensions import loader, registry
from core.engine.sentinel import registry as sentinel_registry

pytestmark = pytest.mark.unit


class _EntryPoint:
    def __init__(self, name: str, extension: object, *, value: str | None = None) -> None:
        self.name = name
        self.value = value or f"test_extensions:{name}"
        self.dist = SimpleNamespace(name="test-distribution", version="1.0.0")
        self._extension = extension

    def load(self) -> object:
        return self._extension


def _isolate_loader(monkeypatch, *entry_points: _EntryPoint) -> None:
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    monkeypatch.delenv("ACE_EXTENSIONS", raising=False)
    monkeypatch.setattr(loader, "_loaded", set())
    monkeypatch.setattr(loader, "_ensured", False)
    monkeypatch.setattr(loader, "entry_points", lambda **kwargs: list(entry_points))


def test_partial_provider_registration_rolls_back_and_retry_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})

    class RetryableExtension:
        name = "retryable"
        version = "1.0.0"
        attempts = 0

        def register(self, reg: registry.Registry) -> None:
            type(self).attempts += 1
            reg.register_intelligence_resource_projection_provider(
                "reader",
                lambda records: records,
                supported_kinds=frozenset({"semantic_revision"}),
            )
            if self.attempts == 1:
                raise RuntimeError("fail after partial registration")

    _isolate_loader(monkeypatch, _EntryPoint("retryable", RetryableExtension))

    assert loader.load_extensions() == []
    assert registry._intelligence_resource_projection_providers == {}

    assert loader.load_extensions() == ["retryable"]
    assert list(registry._intelligence_resource_projection_providers) == [("retryable", "reader")]
    assert RetryableExtension.attempts == 2


def test_existing_capabilities_are_preserved_across_rollback_then_retry(monkeypatch) -> None:
    def existing_check(_files: list[dict]) -> list[dict]:
        return []

    existing_tool = {"fn": object(), "title": "existing"}
    existing_unsupported = registry.UnsupportedRegistration(
        extension_id="existing", extension_version="1.0.0", capability="schema", stable_key="existing.surql"
    )
    existing_briefing = {"builder": object(), "metrics_key": "existing", "timeout": 1.0}
    monkeypatch.setattr(registry, "_recipes", {"existing": "existing.module"})
    monkeypatch.setattr(registry, "_recipe_metadata", {"existing": object()})
    monkeypatch.setattr(registry, "_recipe_disciplines", {"existing": "existing"})
    monkeypatch.setattr(registry, "_recipe_task_types", {"existing": "existing"})
    monkeypatch.setattr(registry, "_tools", [existing_tool])
    monkeypatch.setattr(registry, "_verify_checks", [existing_check])
    monkeypatch.setattr(registry, "_unsupported_registrations", [existing_unsupported])
    monkeypatch.setattr(registry, "_briefing_sections", [existing_briefing])
    monkeypatch.setattr(instrument_registry, "_REGISTRY", {"existing": "existing.module"})
    monkeypatch.setattr(instrument_registry, "_REGISTRATION_METADATA", {"existing": object()})
    monkeypatch.setattr(
        sentinel_registry,
        "engine_registry",
        {"existing": {"fn": object(), "cron": "0 * * * *", "description": "existing", "trigger": None}},
    )

    async def sentinel(_product_id: str) -> dict:
        return {}

    async def briefing(_db) -> dict:
        return {}

    def tool() -> None:
        return None

    def verify(_files: list[dict]) -> list[dict]:
        return []

    class RetryableExtension:
        name = "capability-retry"
        version = "1.0.0"
        attempts = 0

        def register(self, reg: registry.Registry) -> None:
            type(self).attempts += 1
            reg.register_recipe(
                "partial",
                "partial.module",
                disciplines=["partial"],
                task_types=["partial-task"],
            )
            reg.register_tool(tool)
            reg.register_verify_check(verify)
            reg.register_schema("partial.surql")
            reg.register_briefing_section(briefing, metrics_key="partial")
            reg.register_instrument("partial-instrument", "core.engine.extensions.loader")
            reg.register_sentinel(
                "partial-sentinel",
                cron="0 * * * *",
                description="partial",
                fn=sentinel,
            )
            if self.attempts == 1:
                raise RuntimeError("fail after existing capability mutations")

    _isolate_loader(monkeypatch, _EntryPoint("capability-retry", RetryableExtension))

    assert loader.load_extensions() == []
    assert registry._recipes == {"existing": "existing.module"}
    assert registry._recipe_disciplines == {"existing": "existing"}
    assert registry._recipe_task_types == {"existing": "existing"}
    assert registry._tools == [existing_tool]
    assert registry._verify_checks == [existing_check]
    assert registry._unsupported_registrations == [existing_unsupported]
    assert registry._briefing_sections == [existing_briefing]
    assert instrument_registry._REGISTRY == {"existing": "existing.module"}
    assert list(instrument_registry._REGISTRATION_METADATA) == ["existing"]
    assert list(sentinel_registry.engine_registry) == ["existing"]

    assert loader.load_extensions() == ["capability-retry"]
    assert set(registry._recipes) == {"existing", "partial"}
    assert set(instrument_registry._REGISTRY) == {"existing", "partial-instrument"}
    assert set(sentinel_registry.engine_registry) == {"existing", "partial-sentinel"}
    assert RetryableExtension.attempts == 2


def test_installed_entry_points_register_in_stable_metadata_order(monkeypatch) -> None:
    order: list[str] = []

    class Extension:
        version = "1.0.0"

        def __init__(self, name: str) -> None:
            self.name = name

        def register(self, _reg: registry.Registry) -> None:
            order.append(self.name)

    _isolate_loader(
        monkeypatch,
        _EntryPoint("zeta", Extension("zeta"), value="zeta:Extension"),
        _EntryPoint("alpha", Extension("alpha"), value="alpha:Extension"),
    )

    assert loader.load_extensions() == ["alpha", "zeta"]
    assert order == ["alpha", "zeta"]


@pytest.mark.parametrize(
    ("name", "version"),
    [
        ("x" * 121, "1.0.0"),
        ("invalid name", "1.0.0"),
        ("valid-name", "x" * 121),
        ("valid-name", object()),
    ],
)
def test_malformed_extension_identity_is_skipped_before_registration(monkeypatch, name, version) -> None:
    calls = 0

    class Extension:
        def register(self, _reg: registry.Registry) -> None:
            nonlocal calls
            calls += 1

    extension = Extension()
    extension.name = name
    extension.version = version
    _isolate_loader(monkeypatch, _EntryPoint("malformed", extension))

    assert loader.load_extensions() == []
    assert calls == 0
