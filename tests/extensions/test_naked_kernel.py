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
    monkeypatch.setenv("ACE_DISABLE_EXTENSIONS", "1")
    monkeypatch.setattr(loader, "_loaded", set())
    monkeypatch.setattr(loader, "_ensured", False)
    assert loader.load_extensions() == []
    assert loader.loaded_extensions() == []


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
    # Assert only what is true in BOTH trees: "product" is the reference
    # extension and ships publicly; any private extensions would make this
    # test fail-by-construction under the exported tree, where only "product"
    # is installed. The real intent — the kill switch off means built-ins
    # load — is preserved by asserting product loads.
    loaded = loader.load_extensions()
    assert "product" in loaded
