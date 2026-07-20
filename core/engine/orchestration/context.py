"""Active EventBus context variable — threaded through async call stacks without
explicit parameter passing. Set by the WS handler per-run; read by LLM providers."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.engine.orchestration.events import EventBus

_active_bus: contextvars.ContextVar[Optional["EventBus"]] = contextvars.ContextVar("active_event_bus", default=None)


def set_active_bus(bus: Optional["EventBus"]) -> contextvars.Token:
    return _active_bus.set(bus)


def reset_active_bus(token: "contextvars.Token") -> None:
    _active_bus.reset(token)


def get_active_bus() -> Optional["EventBus"]:
    return _active_bus.get()
