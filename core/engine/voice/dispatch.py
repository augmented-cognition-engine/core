"""VoiceDispatch — deferred render container for v2 dispatch inversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


@dataclass
class VoiceDispatch:
    """Deferred render descriptor returned by _dispatch_to_voice.

    Callers build RenderContext (with thread state) and invoke renderer(render_input, ctx).
    """

    renderer: Callable[[Any, Any], "str | None"]
    render_input: Any
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    topic: str
    thread_bearing: bool
