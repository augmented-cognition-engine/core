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
import re
from importlib import import_module
from importlib.metadata import entry_points
from threading import RLock

from core.engine.extensions.registry import Registry, atomic_extension_registration

logger = logging.getLogger(__name__)

_loaded: set[str] = set()
_ensured = False
_load_lock = RLock()
_EXTENSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_EXTENSION_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.!+_-]{0,119}$")


def _resolve(spec: str):
    """Resolve a ``module.path:Attr`` (or bare ``module.path``) spec to an object."""
    module_path, _, attr = spec.partition(":")
    obj = import_module(module_path)
    return getattr(obj, attr) if attr else obj


def _entry_point_sort_key(entry_point: object) -> tuple[str, str, str, str]:
    distribution = getattr(entry_point, "dist", None)
    return (
        str(getattr(entry_point, "name", "")),
        str(getattr(entry_point, "value", "")),
        str(getattr(distribution, "name", "")),
        str(getattr(distribution, "version", "")),
    )


def _extension_identity(extension: object, *, fallback_name: str) -> tuple[str, str]:
    extension_id = getattr(extension, "name", fallback_name)
    extension_version = getattr(extension, "version", "0.0.0")
    if not isinstance(extension_id, str) or not _EXTENSION_ID.fullmatch(extension_id):
        raise ValueError("extension name must be a bounded stable identifier")
    if not isinstance(extension_version, str) or not _EXTENSION_VERSION.fullmatch(extension_version):
        raise ValueError("extension version must be a bounded stable version")
    return extension_id, extension_version


def load_extensions() -> list[str]:
    """Discover and register all extensions. Returns the sorted list of loaded names.

    Sources, in order: the ``ace.extensions`` entry-point group, then the
    ``ACE_EXTENSIONS`` env list (for local/dev extensions not pip-installed).
    Idempotent: an extension already loaded is skipped. Never raises.
    """
    with _load_lock:
        return _load_extensions_unlocked()


def _load_extensions_unlocked() -> list[str]:
    # Kill switch: boot the kernel with zero extensions. Used by the
    # naked-kernel CI lane (`make test-naked-kernel`) and for debugging a
    # broken extension without uninstalling it.
    if os.environ.get("ACE_DISABLE_EXTENSIONS") == "1":
        return sorted(_loaded)

    specs: list[tuple[str, object]] = []

    # 1) installed extension packages (entry points)
    try:
        installed = sorted(entry_points(group="ace.extensions"), key=_entry_point_sort_key)
        for ep in installed:
            try:
                specs.append((str(ep.name), ep.load()))
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
            extension_id, extension_version = _extension_identity(extension, fallback_name=name)
            with atomic_extension_registration():
                extension.register(Registry(extension_id=extension_id, extension_version=extension_version))
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
    with _load_lock:
        if _ensured:
            return
        _ensured = True  # set first: guards re-entrant reads during load
        _load_extensions_unlocked()


def loaded_extensions() -> list[str]:
    """Names of extensions registered so far (diagnostics)."""
    return sorted(_loaded)
