"""ACE_DISABLE_EXTENSIONS=1 boots the kernel with zero extensions loaded.

This is what the naked-kernel CI lane uses: built-in extensions are entry
points in this repo's own pyproject, so the only way to test the kernel
"with no extensions installed" is a loader-level switch.
"""

from __future__ import annotations

import os

import pytest

import core.engine.extensions.loader as loader


@pytest.mark.unit
def test_disable_extensions_env_skips_all_discovery(monkeypatch):
    from core.engine.extensions import registry

    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    monkeypatch.setattr(loader, "_loaded", set())
    monkeypatch.setattr(loader, "_ensured", False)
    monkeypatch.setattr(registry, "_task_actions", {})
    monkeypatch.setattr(registry, "_grounded_state_adapters", {})
    monkeypatch.setattr(registry, "_intelligence_resource_projection_providers", {})
    assert loader.load_extensions() == []
    assert loader.loaded_extensions() == []
    assert registry.registered_task_actions() == {}
    assert registry.registered_grounded_state_adapters() == {}
    assert registry.registered_intelligence_resource_projection_providers() == ()


@pytest.mark.unit
def test_extensions_load_normally_without_env(monkeypatch):
    if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1":
        pytest.skip("naked-kernel lane: built-in extensions deliberately absent")
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    # No state reset: load_extensions() is idempotent. Whether extensions were
    # already loaded by an earlier test or load fresh here, the built-ins
    # must be present when the kill switch is off. (Resetting _loaded and
    # re-loading would re-register recipes and trip the duplicate guard.)
    # Constraint: this relies on _loaded and the registry stores staying in
    # sync — true for anything that loads through the loader. If a future
    # test registers extension content directly on Registry() without going
    # through load_extensions(), add a registry reset fixture instead.
    # Assert only public built-ins. The kill switch off means installed
    # product/solution contributions load through the same entry-point seam.
    loaded = loader.load_extensions()
    assert "code-intelligence" in loaded
    assert "product" in loaded
