# engine/canvas/surface_adapter.py
"""Surface adapter pattern (vision-doc §4.2).

A SurfaceAdapter is a thin shim that an event-emitting surface (canvas,
Claude Code hook, IDE plugin, meeting transcript) uses to publish
canonical CanvasEvents to the engine. The adapter stamps the `surface`
field; the engine consumer remains surface-blind.

The Claude Code hook lifecycle in engine/capture/observer.py predates
this abstraction and continues to feed engine/capture/pipeline.py
directly. v1.1 will retrofit the hook to use SurfaceAdapter; v1 leaves
it untouched. THIS MODULE MUST NOT IMPORT FROM THE HOOK CODE PATH.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from core.engine.canvas.event_protocol import is_surface_agnostic

EventConsumer = Callable[[dict[str, Any]], Awaitable[None]]


class SurfaceAdapter(ABC):
    """Abstract base. Each surface implements `surface_name`."""

    def __init__(self, consumer: EventConsumer):
        self._consumer = consumer

    @property
    @abstractmethod
    def surface_name(self) -> str:
        """e.g. 'canvas', 'ide_jetbrains', 'transcript_zoom', 'cli_hook'."""
        ...

    async def emit(
        self,
        session_id: str,
        event_type: str,
        payload: BaseModel | dict[str, Any],
    ) -> None:
        payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
        event = {
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload_dict,
            "surface": self.surface_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if not is_surface_agnostic(event):
            raise ValueError(f"Event fails surface-agnostic invariants: {event}")
        await self._consumer(event)


class CanvasSurfaceAdapter(SurfaceAdapter):
    @property
    def surface_name(self) -> str:
        return "canvas"
