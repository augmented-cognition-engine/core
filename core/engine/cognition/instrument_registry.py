"""Registry mapping instrument slugs to Python module paths.

Used by the executor's dispatch layer to find Python instruments (instruments
backed by callable modules) vs DB-backed framework instruments (the existing
path).

A Python instrument is a module exposing a single public `run(**kwargs)`
function plus a `_call_llm()` indirection for monkeypatching.

Extension tools (Sentinel, Foresight, etc.) register their own instruments
via `register_instrument(slug, module_path)` — the registry is
extension-agnostic.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

# The kernel ships EMPTY of extension instruments. Extensions register theirs on load
# via the extension API (engine.extensions) and self-register — the kernel never
# needs to know which instruments an extension brings.
_REGISTRY: dict[str, str] = {}


def _ensure_extensions_loaded() -> None:
    """Load extensions once before serving instrument lookups, so an extension's
    instruments are registered before the executor dispatches them.

    Delegates to the loader's single load-once guard (shared with the other
    consume-side accessors). Lazy import avoids pulling the extension chain at
    module-import time. Never raises — a broken extension must not take down dispatch.
    """
    from core.engine.extensions.loader import ensure_loaded

    ensure_loaded()


def is_python_instrument(slug: str) -> bool:
    """Return True if `slug` is a registered Python instrument (vs DB framework)."""
    _ensure_extensions_loaded()
    return slug in _REGISTRY


def get_instrument_run(slug: str) -> Callable[..., Any]:
    """Resolve a registered instrument's `run` callable.

    Raises KeyError if the slug is not registered. Callers should check
    `is_python_instrument` first when fallback to DB-framework dispatch is desired.
    """
    _ensure_extensions_loaded()
    module_path = _REGISTRY[slug]
    module = import_module(module_path)
    return module.run


def register_instrument(slug: str, module_path: str) -> None:
    """Register a new Python instrument.

    Called by extension tools (Sentinel, Foresight, etc.) to make their
    instruments dispatchable by the orchestrator.

    Module at `module_path` must expose a public `run(**kwargs)` function.
    """
    _REGISTRY[slug] = module_path


def list_registered_instruments() -> list[str]:
    """Return all registered Python instrument slugs (for diagnostics / tools)."""
    return sorted(_REGISTRY.keys())
