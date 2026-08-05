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

from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable

# The kernel ships EMPTY of extension instruments. Extensions register theirs on load
# via the extension API (engine.extensions) and self-register — the kernel never
# needs to know which instruments an extension brings.
_REGISTRY: dict[str, str] = {}
_REGISTRATION_METADATA: dict[str, "InstrumentRegistration"] = {}


@dataclass(frozen=True)
class InstrumentRegistration:
    slug: str
    module_path: str
    extension_id: str | None = None
    extension_version: str | None = None
    module_digest: str = ""
    contract_version: str = "legacy-python-instrument/v1"
    trusted_in_process: bool = True


def _module_digest(module_path: str) -> str:
    spec = find_spec(module_path)
    origin = spec.origin if spec is not None else None
    if origin and Path(origin).is_file():
        return sha256(Path(origin).read_bytes()).hexdigest()
    return sha256(module_path.encode("utf-8")).hexdigest()


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


def register_instrument(
    slug: str,
    module_path: str,
    *,
    extension_id: str | None = None,
    extension_version: str | None = None,
    contract_version: str = "legacy-python-instrument/v1",
    trusted_in_process: bool = True,
) -> None:
    """Register a new Python instrument.

    Called by extension tools (Sentinel, Foresight, etc.) to make their
    instruments dispatchable by the orchestrator.

    Module at `module_path` must expose a public `run(**kwargs)` function.
    """
    if contract_version not in {"legacy-python-instrument/v1", "ace.cognition.instrument/v1"}:
        raise RuntimeError("unsupported_instrument_contract_version")
    if not trusted_in_process:
        raise RuntimeError("untrusted_in_process_extension_code_is_unsupported")
    registration = InstrumentRegistration(
        slug=slug,
        module_path=module_path,
        extension_id=extension_id,
        extension_version=extension_version,
        module_digest=_module_digest(module_path),
        contract_version=contract_version,
        trusted_in_process=trusted_in_process,
    )
    existing_path = _REGISTRY.get(slug)
    if existing_path is not None and existing_path != module_path:
        raise RuntimeError(f"Instrument '{slug}' is already registered by module '{existing_path}'")
    existing_metadata = _REGISTRATION_METADATA.get(slug)
    if existing_metadata is not None and existing_metadata != registration:
        raise RuntimeError(f"Instrument '{slug}' has conflicting registration provenance")
    _REGISTRY[slug] = module_path
    _REGISTRATION_METADATA[slug] = registration


def list_registered_instruments() -> list[str]:
    """Return all registered Python instrument slugs (for diagnostics / tools)."""
    return sorted(_REGISTRY.keys())


def registered_instrument_metadata() -> dict[str, InstrumentRegistration]:
    """Return typed registration provenance for governed-cognition adapters."""
    _ensure_extensions_loaded()
    return dict(_REGISTRATION_METADATA)
