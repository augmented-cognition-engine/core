"""Extension discovery + loading.

Extensions expose themselves via the ``ace.extensions`` entry-point group::

    # an extension package's pyproject.toml
    [project.entry-points."ace.extensions"]
    marketing = "ace_extension_marketing:MarketingExtension"

``pip install ace-extension-marketing`` → auto-discovered here, no kernel edits.
For local/dev extensions, set ``ACE_EXTENSIONS="pkg.module:ExtensionClass,other:Extension"``.

``load_extensions()`` is idempotent and never raises on a single bad extension — a
broken extension is logged and skipped so it can't take down the kernel.
"""

from __future__ import annotations

import logging
import os
from importlib import import_module
from importlib.metadata import entry_points

from core.engine.extensions.registry import Registry

logger = logging.getLogger(__name__)

_loaded: set[str] = set()
_registry = Registry()
_ensured = False


def _resolve(spec: str):
    """Resolve a ``module.path:Attr`` (or bare ``module.path``) spec to an object."""
    module_path, _, attr = spec.partition(":")
    obj = import_module(module_path)
    return getattr(obj, attr) if attr else obj


def load_extensions() -> list[str]:
    """Discover and register all extensions. Returns the sorted list of loaded names.

    Sources, in order: the ``ace.extensions`` entry-point group, then the
    ``ACE_EXTENSIONS`` env list (for local/dev extensions not pip-installed).
    Idempotent: an extension already loaded is skipped. Never raises.
    """
    # Kill switch: boot the kernel with zero extensions. Used by the
    # naked-kernel CI lane (`make test-naked-kernel`) and for debugging a
    # broken extension without uninstalling it.
    if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1":
        return sorted(_loaded)

    specs: list[tuple[str, object]] = []

    # 1) installed extension packages (entry points)
    try:
        for ep in entry_points(group="ace.extensions"):
            try:
                specs.append((ep.name, ep.load()))
            except Exception:
                logger.warning("extension entry point %r failed to load", ep.name, exc_info=True)
    except Exception:
        logger.warning("extension entry-point discovery failed", exc_info=True)

    # 2) explicit dev list
    for spec in (s.strip() for s in os.environ.get("ACE_EXTENSIONS", "").split(",")):
        if not spec:
            continue
        try:
            specs.append((spec, _resolve(spec)))
        except Exception:
            logger.warning("could not resolve ACE_EXTENSIONS entry %r", spec, exc_info=True)

    for name, extension_obj in specs:
        if name in _loaded:
            continue
        try:
            extension = extension_obj() if isinstance(extension_obj, type) else extension_obj
            extension.register(_registry)
            _loaded.add(name)
            logger.info("loaded extension: %s", getattr(extension, "name", name))
        except Exception:
            logger.warning("extension %r failed to register; skipped", name, exc_info=True)

    return sorted(_loaded)


def ensure_loaded() -> None:
    """Run ``load_extensions()`` exactly once, cheaply on repeat calls.

    Consume-side accessors (recipe loader, committee resolver, MCP tool list,
    schema migrator) call this so an extension's capabilities are registered before
    the kernel reads them — without re-scanning entry points on every lookup.
    Never raises. Tests that need a fresh scan call ``load_extensions()`` directly.

    Note: ``_ensured`` latches even when ``ACE_DISABLE_EXTENSIONS=1`` short-
    circuits discovery — unsetting the env later in the same process will
    not re-trigger loading. The kill switch is process-lifetime.
    """
    global _ensured
    if _ensured:
        return
    _ensured = True  # set first: guards re-entrant reads during load
    load_extensions()


def loaded_extensions() -> list[str]:
    """Names of extensions registered so far (diagnostics)."""
    return sorted(_loaded)
