"""The scaffold copies the reference extension — template and worked example
cannot drift (extension-api.md 'Starting point' contract)."""

from __future__ import annotations

import pytest

from scripts.scaffold_extension import scaffold


def test_scaffold_generates_standalone_package(tmp_path):
    root = scaffold("green_energy", tmp_path)
    pkg = root / "green_energy_extension"
    assert (pkg / "extension.py").exists()
    assert (pkg / "instruments" / "framing.py").exists()
    # The MCP tool module is renamed with the extension — the kernel MCP
    # server registers tools by function name, so an un-namespaced
    # ace_product_pulse would silently shadow the built-in product tool.
    assert (pkg / "tools" / "green_energy_pulse.py").exists()
    assert not (pkg / "tools" / "product_pulse.py").exists()
    assert (root / "pyproject.toml").exists()
    assert (root / "README.md").exists()
    text = (pkg / "extension.py").read_text(encoding="utf-8")
    assert "GreenEnergyExtension" in text
    assert 'name = "green_energy"' in text
    # The docstring's entry-point example must show the scaffold's own key,
    # not `product = ...` (it must match the generated pyproject).
    assert 'green_energy = "green_energy_extension.extension:GreenEnergyExtension"' in text
    markers = (
        "extensions.reference",  # dotted module paths
        "extensions/reference",  # slash-form paths in comments/docstrings
        "ace_product_pulse",  # MCP tool fn name (MCP registers by fn name)
        "Product Pulse",  # MCP tool title
    )
    leftovers = [p for p in pkg.rglob("*.py") if any(m in p.read_text(encoding="utf-8") for m in markers)]
    assert leftovers == []
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '[project.entry-points."ace.extensions"]' in pyproject
    assert 'green_energy = "green_energy_extension.extension:GreenEnergyExtension"' in pyproject


def test_scaffolded_extension_loads_via_dev_env(tmp_path, monkeypatch):
    root = scaffold("green_energy", tmp_path)
    monkeypatch.syspath_prepend(str(root))
    spec = "green_energy_extension.extension:GreenEnergyExtension"
    monkeypatch.setenv("ACE_EXTENSIONS", spec)
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    from core.engine.extensions import loader

    loaded = loader.load_extensions()
    assert spec in loaded


@pytest.mark.requires_extensions
def test_dual_load_isolation_with_builtin_product_extension(tmp_path, monkeypatch):
    """A scaffolded extension and the built-in `product` reference extension
    must coexist in one process: every shared-registry key (instrument slugs,
    recipe slugs, MCP tool function names) stays in its own namespace — no
    duplicate-key exceptions, no silent shadowing."""
    root = scaffold("green_energy", tmp_path)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv("ACE_EXTENSIONS", "green_energy_extension.extension:GreenEnergyExtension")
    monkeypatch.delenv("ACE_DISABLE_EXTENSIONS", raising=False)
    from core.engine.extensions import loader, registry

    loaded = loader.load_extensions()
    assert "product" in loaded  # the built-in reference extension really loaded
    assert "green_energy_extension.extension:GreenEnergyExtension" in loaded

    # (a) instrument slugs resolve to their OWN module paths — no shadow
    # routing (register_instrument is last-write-wins, so a shared slug
    # would silently redirect the reference extension's instruments).
    from core.engine.cognition.instrument_registry import _REGISTRY

    assert _REGISTRY["product-framing"] == "extensions.reference.instruments.framing"
    assert _REGISTRY["green_energy-framing"] == "green_energy_extension.instruments.framing"

    # (b) both recipes registered under distinct slugs.
    recipes = registry.registered_recipes()
    assert "product_decision_intelligence" in recipes
    assert "green_energy_decision_intelligence" in recipes

    # (c) both MCP tools present under distinct function names — the MCP
    # server registers by fn.__name__ and a duplicate name replaces silently.
    tool_names = [t["fn"].__name__ for t in registry.registered_tools()]
    assert "ace_product_pulse" in tool_names
    assert "ace_green_energy_pulse" in tool_names


def test_scaffold_rejects_bad_names(tmp_path):
    with pytest.raises(SystemExit):
        scaffold("Green-Energy", tmp_path)


def test_scaffold_refuses_to_overwrite(tmp_path):
    scaffold("green_energy", tmp_path)
    with pytest.raises(SystemExit):
        scaffold("green_energy", tmp_path)
