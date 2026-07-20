"""SessionAdapter registry — maps source strings to adapter instances."""

from __future__ import annotations

from core.engine.session.adapter import SessionAdapter
from core.engine.session.adapters.claude_code import ClaudeCodeAdapter
from core.engine.session.adapters.generic import GenericAdapter

_registry: dict[str, type] = {
    "claude_code": ClaudeCodeAdapter,
}


def resolve(source: str) -> SessionAdapter:
    """Return an adapter instance for the given source string.

    Falls back to GenericAdapter for unrecognized sources — never raises.
    """
    cls = _registry.get(source, GenericAdapter)
    return cls()


def register(source: str, adapter_cls: type) -> None:
    """Register a new adapter. Used by future tool integrations."""
    _registry[source] = adapter_cls
